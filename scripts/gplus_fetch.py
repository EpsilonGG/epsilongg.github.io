r"""Fetch the Gplus daily universe (list 1-1, all X handles) from Nitter RSS.

The Gplus daily uses the full list 1-1 account set: creator / brand / info
handles, with the gal-daily "other" account (jita_gf) and all B站 accounts
excluded by construction (they are not in the roster).

The local machine cannot reach Nitter through the default proxy; the working
route is http://127.0.0.1:7897. CI runners reach Nitter directly. This script
therefore accepts --proxy and defaults to auto: use 7897 if it answers, else
no proxy.

Output: one JSONL per fetch run under out/gplus/raw/, keyed by handle. Parsing
is deliberately shared with the X-Reader RSS shape so the normalizer can
reuse the same field names.

Usage:
    python scripts/gplus_fetch.py --concurrency 12 --out out/gplus/raw
    python scripts/gplus_fetch.py --handles foo,bar --proxy http://127.0.0.1:7897
"""
from __future__ import annotations

import argparse
import concurrent.futures
import html as html_mod
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROSTER = ROOT / "src" / "config" / "gplus-roster.json"
# Order matters: the first endpoint is tried for every handle, so a dead host
# at the front costs one full timeout per account (403 x 20s / 12 threads ~ 11
# minutes). Probed through 127.0.0.1:7897 on 2026-11-25 with real roster handles:
# nitter.cf 1.5s, nitter.gq 1.5s, xitter.gq 1.5s, teapawt.org 1.7s all returned
# 20 RSS items; jaydenha.uk is dead and nitter.meowing.monster is slow (9s) and
# intermittently 404/429, so it stays last. The three new hosts are Teapawt
# siblings: host-level fallbacks, not independent upstreams.
ENDPOINTS = [
    "https://nitter.cf",
    "https://nitter.gq",
    "https://xitter.gq",
    "https://teapawt.org",
    "https://nitter.meowing.monster",
]
UA = "Mozilla/5.0 (compatible; GplusFetch/1.0)"
LOCAL_PROXY = "http://127.0.0.1:7897"


def pick_proxy(explicit: str | None) -> str | None:
    """Pick the Nitter proxy without trusting a single (often dead) host.

    2026-11-24 nightly: the auto-probe used ``nitter.jaydenha.uk``, which is
    dead, so it returned None even though 7897 was up. Every request then went
    direct, all 403 accounts timed out, and the fetch took ~64 minutes while
    writing 372 error files. Probe the instance that actually works instead.
    """
    if explicit:
        return explicit
    handler = urllib.request.ProxyHandler({"http": LOCAL_PROXY, "https": LOCAL_PROXY})
    opener = urllib.request.build_opener(handler)
    # Try the known-good instance first; any HTTP response (even 403/429) proves
    # the proxy tunnel works, so treat HTTPError as success too.
    for base in ENDPOINTS:
        try:
            with opener.open(urllib.request.Request(base, headers={"User-Agent": UA}), timeout=8):
                return LOCAL_PROXY
        except urllib.error.HTTPError:
            return LOCAL_PROXY
        except Exception:
            continue
    # Proxy not usable. Direct may work on CI (documented), so fall back to it.
    return None


def build_opener(proxy: str | None):
    if proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html_mod.unescape(s).strip()


# Nitter RSS title is the only place that records a retweet's real author:
#   RT @muninmumu (by @asou_ei): <original body>
# Historically we only looked at the description and set publisher=handle, so
# every retweet in a timeline was filed under the account being scraped. That
# is how 261127-gp ended up saying 浅生詠 announced her own role and sale when
# all three sources were retweets of mzn773 / sayuki_acp / tkwsnb.
RT_TITLE = re.compile(
    r"^RT\s+@([A-Za-z0-9_]{1,15})\s*(?:\(\s*by\s+@([A-Za-z0-9_]{1,15})\s*\))?\s*:\s*(.*)$",
    re.I | re.S,
)
BLOCKQUOTE = re.compile(r"<blockquote\b[^>]*>(.*?)</blockquote>", re.I | re.S)
QUOTE_NAME = re.compile(r"<b[^>]*>(.*?)</b>", re.I | re.S)
QUOTE_HANDLE = re.compile(r"@([A-Za-z0-9_]{1,15})")
QUOTE_STATUS = re.compile(r"/status/(\d+)")
IMG_AUTHOR = re.compile(r'alt="Image from (.*?) \(@([A-Za-z0-9_]{1,15})\)"', re.I)
PINNED = re.compile(r"^Pinned:\s*", re.I)


def _split_quote(desc_html: str) -> tuple[str, str | None, str | None, str | None]:
    """Return (own_html, quoted_author, quoted_tweet_id, quoted_text).

    A Nitter quote tweet appends `<hr/><blockquote>…<footer>— link</footer>`
    to the description. Keeping that block inside `content` makes the writer
    read somebody else's words as the timeline owner's, so split it out and
    keep the attribution as metadata instead.
    """
    parts = re.split(r"<hr\s*/?>", desc_html or "", maxsplit=1, flags=re.I)
    own_html = parts[0]
    if len(parts) == 1:
        return own_html, None, None, None
    block = BLOCKQUOTE.search(parts[1])
    if not block:
        return own_html, None, None, None
    inner = block.group(1)
    name = QUOTE_NAME.search(inner)
    handle = QUOTE_HANDLE.search(html_mod.unescape(strip_html(name.group(1)))) if name else None
    quoted_author = handle.group(1) if handle else None
    status = QUOTE_STATUS.search(inner)
    quoted_id = status.group(1) if status else None
    quoted_body = re.sub(r"<b[^>]*>.*?</b>", "", inner, flags=re.I | re.S)
    quoted_body = re.sub(r"<footer\b[^>]*>.*?</footer>", "", quoted_body, flags=re.I | re.S)
    quoted_text = strip_html(quoted_body) or None
    return own_html, quoted_author, quoted_id, quoted_text


def parse_rss(raw: bytes, handle: str) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    for it in root.findall("./channel/item"):
        link = it.findtext("link") or ""
        m = re.search(r"/status/(\d+)", link)
        source_id = m.group(1) if m else (it.findtext("guid") or "")
        desc_html = it.findtext("description") or ""
        title = (it.findtext("title") or "").strip()
        rt = RT_TITLE.match(title)
        if rt:
            # `publisher` is the original author, `metadata.account` is the
            # timeline owner who amplified it — same contract as X-Reader.
            author = rt.group(1).lower()
            retweeted_by = (rt.group(2) or handle).lower()
            text = desc_html and strip_html(desc_html) or html_mod.unescape(rt.group(3))
        else:
            author = handle.lower()
            retweeted_by = None
            pinned = PINNED.match(title)
            body = PINNED.sub("", title) if pinned else title
            text = desc_html and strip_html(desc_html) or html_mod.unescape(body)
        own_html, quoted_author, quoted_id, quoted_text = _split_quote(desc_html)
        if quoted_author or quoted_id:
            # The quote's body may be the *whole* description for a retweet of
            # a quote tweet; re-split the same HTML we just used for `text`.
            own_text = strip_html(own_html)
            if own_text:
                text = own_text
        img = IMG_AUTHOR.search(desc_html)
        canonical = re.sub(r"^https?://[^/]+", "https://x.com", link) if "/status/" in link else (
            f"https://x.com/{author}/status/{source_id}" if source_id else ""
        )
        try:
            published = parsedate_to_datetime(it.findtext("pubDate") or "")
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except Exception:
            published = datetime.now(timezone.utc)
        out.append(
            {
                "identity_key": f"x:{source_id}",
                "source_id": "x",
                "item_id": source_id,
                "publisher": author,
                "canonical_url": canonical,
                "published_at": published.isoformat(),
                "content": text,
                "metadata": {
                    "account": handle.lower(),
                    "author_name": (img.group(1).strip() if img else None),
                    "is_retweet": bool(rt),
                    "retweeted_by": retweeted_by,
                    "is_reply": False,
                    "reply_to": None,
                    "is_quote": bool(quoted_author or quoted_id),
                    "quoted_tweet_id": quoted_id,
                    "quoted_author": quoted_author,
                    "quoted_text": quoted_text,
                    "is_pinned": bool(not rt and PINNED.match(title)),
                    "provider": "nitter-rss",
                    "route": "rss",
                },
            }
        )
    return out


def fetch_one(handle: str, proxy: str | None, out_dir: Path, retries: int = 2) -> dict:
    dest = out_dir / f"{handle.lower()}.json"
    if dest.exists():
        try:
            return {"handle": handle, "status": "cached", "items": len(json.loads(dest.read_text(encoding="utf-8")).get("items", []))}
        except Exception:
            pass
    opener = build_opener(proxy)
    errors = []
    for base in ENDPOINTS:
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(
                    f"{base}/{handle}/rss", headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml"}
                )
                with opener.open(req, timeout=20) as resp:
                    raw = resp.read()
                items = parse_rss(raw, handle)
                dest.write_text(
                    json.dumps({"handle": handle, "status": "ok", "items": items}, ensure_ascii=False),
                    encoding="utf-8",
                    newline="\n",
                )
                return {"handle": handle, "status": "ok", "items": len(items)}
            except Exception as exc:
                errors.append(f"{base}: {type(exc).__name__}")
                time.sleep(0.4 * (attempt + 1))
    dest.write_text(
        json.dumps({"handle": handle, "status": "error", "items": [], "errors": errors}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    return {"handle": handle, "status": "error", "items": 0, "errors": errors[:2]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch Gplus roster from Nitter RSS in parallel")
    ap.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "gplus" / "raw")
    ap.add_argument("--handles", default=None, help="comma-separated subset for a pilot run")
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--proxy", default="auto", help="proxy URL, 'auto', or 'none'")
    ap.add_argument("--retries", type=int, default=1)
    args = ap.parse_args(argv)

    proxy = pick_proxy(None if args.proxy == "auto" else (None if args.proxy == "none" else args.proxy))
    roster = json.loads(args.roster.read_text(encoding="utf-8"))["accounts"]
    handles = [a["handle"] for a in roster]
    if args.handles:
        wanted = {h.strip().lower() for h in args.handles.split(",") if h.strip()}
        handles = [h for h in handles if h.lower() in wanted]
    args.out.mkdir(parents=True, exist_ok=True)

    results = []
    aborted = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(fetch_one, h, proxy, args.out, args.retries): h for h in handles}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results.append(res)
            if len(results) % 50 == 0:
                print(f"  {len(results)}/{len(handles)} done", file=sys.stderr)
            # Circuit breaker: if the first 24 accounts all failed, every
            # endpoint is unreachable (wrong proxy / down instance). Bail out
            # instead of burning an hour on 405 x 3 x 2 x 20s timeouts.
            if len(results) == 24 and not any(r["status"] == "ok" for r in results):
                aborted = True
                for pending in futures:
                    pending.cancel()
                print(
                    "abort: first 24 accounts all failed; check proxy/endpoints",
                    file=sys.stderr,
                )
                break
        if aborted:
            pool.shutdown(wait=False, cancel_futures=True)

    ok = [r for r in results if r["status"] == "ok"]
    cached = [r for r in results if r["status"] == "cached"]
    err = [r for r in results if r["status"] == "error"]
    summary = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "proxy": proxy,
        "total": len(results),
        "ok": len(ok),
        "cached": len(cached),
        "error": len(err),
        "aborted": aborted,
        "items": sum(r["items"] for r in ok + cached),
        "errors": [{"handle": r["handle"], "detail": r.get("errors")} for r in err[:20]],
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if ok or cached else 1


if __name__ == "__main__":
    raise SystemExit(main())
