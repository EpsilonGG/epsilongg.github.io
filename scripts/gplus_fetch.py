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
ENDPOINTS = [
    "https://nitter.jaydenha.uk",
    "https://nitter.meowing.monster",
    "https://nitter.cf",
]
UA = "Mozilla/5.0 (compatible; GplusFetch/1.0)"


def pick_proxy(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    # 7897 is the local proxy that can reach Nitter; the default 65312 cannot.
    probe = "https://nitter.jaydenha.uk"
    handler = urllib.request.ProxyHandler({"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"})
    opener = urllib.request.build_opener(handler)
    try:
        with opener.open(urllib.request.Request(probe, headers={"User-Agent": UA}), timeout=8):
            return "http://127.0.0.1:7897"
    except Exception:
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


def parse_rss(raw: bytes, handle: str) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    for it in root.findall("./channel/item"):
        link = it.findtext("link") or ""
        m = re.search(r"/status/(\d+)", link)
        source_id = m.group(1) if m else (it.findtext("guid") or "")
        desc = strip_html(it.findtext("description") or "")
        title = (it.findtext("title") or "").strip()
        # Nitter RSS title duplicates the text when there is no link card;
        # description is the cleaner source of the tweet body.
        text = desc if desc else html_mod.unescape(title)
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
                "publisher": handle,
                "canonical_url": f"https://x.com/{handle}/status/{source_id}" if source_id else "",
                "published_at": published.isoformat(),
                "content": text,
                "metadata": {
                    "is_retweet": text.startswith("RT "),
                    "is_quote": False,
                    "is_reply": False,
                    "provider": "nitter-rss",
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(fetch_one, h, proxy, args.out, args.retries): h for h in handles}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            res = fut.result()
            results.append(res)
            if i % 50 == 0:
                print(f"  {i}/{len(handles)} done", file=sys.stderr)

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
        "items": sum(r["items"] for r in ok + cached),
        "errors": [{"handle": r["handle"], "detail": r.get("errors")} for r in err[:20]],
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if ok or cached else 1


if __name__ == "__main__":
    raise SystemExit(main())
