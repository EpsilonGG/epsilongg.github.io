r"""Fetch replies authored by the Gplus info-section accounts from Nitter HTML.

Why a separate fetcher
----------------------
`gplus_fetch.py` uses Nitter RSS. RSS has no reply metadata at all (the item
shape hardcodes ``is_reply: False``), so replies posted by an account are
invisible to the Gplus store. Nitter's profile HTML does carry them:
``<div class="replying-to">Replying to <a>@user</a></div>`` sits inside each
reply's ``div.timeline-item``. X-Reader's HTML parser already knows this
markup (``.xreader/parsers/nitter_html.py``), but its production config tries
RSS first, so the running X-Reader stores contain zero replies.

This script fetches **only** the 10 accounts flagged ``reply_scope: true`` in
``src/config/gplus-roster.json`` (player / commentary / summary voices; the
Japanese official media and store accounts are excluded). It writes two kinds
of reply items in the same shape as ``gplus_fetch.py`` so ``gplus_slice.py``
can merge them into ``data/xreader/gplus/<JST day>.jsonl``:

* profile HTML -> replies authored by those accounts (``route: html``);
* status HTML  -> replies authored by a scope account inside its own comment
  section (``route: status-html``, with ``parent_tweet_id`` / ``parent_author``).

Only replies authored by a scope account are kept. Generic comments left by
other people under a scope account's tweet are dropped, even when fetched from
the status page; a scope account replying inside its own comment section is
kept. Cached status payloads are re-filtered on every run, so a narrowing of
the scope does not leave old comments behind.

Limits (important): a Nitter profile page shows roughly the newest 20 items,
so this is "replies visible in the current timeline window", not a complete
comment archive. Status pages only expose minute-precision dates and flatten
line breaks, so those items are added but never overwrite RSS items. Some
public instances answer 403/429/challenge for HTML; the endpoint list below
puts the instances that served HTML in the 2026-11-23 probe first.

Usage
-----
    python scripts/gplus_replies.py --out out/gplus/replies
    python scripts/gplus_replies.py --handles youtan0309,cloud668 --proxy http://127.0.0.1:7897
    python scripts/gplus_replies.py --no-threads   # authored replies only
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROSTER = ROOT / "src" / "config" / "gplus-roster.json"
# HTML-capable instances first. Probed through 127.0.0.1:7897 on 2026-11-25:
# nitter.cf, nitter.gq, xitter.gq and teapawt.org all returned 200 with 15
# timeline-item divs on /akibablog. Not reused here: jaydenha.uk is dead,
# meowing.monster serves an Anubis challenge, goyimx.com answers 418 on HTML.
ENDPOINTS = [
    "https://nitter.cf",
    "https://nitter.gq",
    "https://xitter.gq",
    "https://teapawt.org",
]
STATUS_RE = re.compile(r"/status/(\d+)")
HANDLE_RE = re.compile(r"@([A-Za-z0-9_]{1,15})")
DATE_RE = re.compile(
    r"^([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})\s+·\s+"
    r"(\d{1,2}):(\d{2})\s+(AM|PM)\s+(UTC|GMT|JST)$"
)
_DATE_SENTINEL = re.compile(r"^[A-Z][a-z]{2}\s+\d{1,2},")


# Imported from the sibling module so proxy detection stays a single source of
# truth. Running as a script puts scripts/ on sys.path; tests do the same.
from gplus_fetch import UA, build_opener, pick_proxy  # noqa: E402


def parse_nitter_date(raw: str) -> str | None:
    """Nitter's ``Nov 19, 2026 · 9:00 AM UTC`` -> ISO-8601 with timezone.

    ``email.utils.parsedate`` silently reads ``11:35 PM`` as 11:35, so the
    12-hour form is parsed explicitly. Items with only a relative date (``3h``)
    have no absolute timestamp and are skipped by the caller.
    """
    text = (raw or "").strip()
    match = DATE_RE.match(text)
    if not match:
        return None
    mon, day, year, hour, minute, ampm, zone = match.groups()
    try:
        parsed = datetime.strptime(f"{mon} {day} {year}", "%b %d %Y")
    except ValueError:
        return None
    twelve = int(hour) % 12
    parsed = parsed.replace(
        hour=twelve + (12 if ampm == "PM" else 0),
        minute=int(minute),
        tzinfo=timezone(timedelta(hours=9)) if zone == "JST" else timezone.utc,
    )
    return parsed.isoformat()


class _TimelineParser(HTMLParser):
    """Collect reply items from Nitter HTML (profile or status page).

    ``parent=None``: profile mode, keep only items with a ``replying-to`` marker
    authored by the tracked handle. ``parent={...}``: status-page mode, every
    item except the focal tweet is a reply to that parent.
    """

    def __init__(self, parent: dict | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.parent = parent
        self.replies: list[dict] = []
        self._divs: list[set[str]] = []
        self._item: dict | None = None
        self._item_depth = 0
        self._capture: str | None = None  # content | reply | username
        self._capture_depth = 0
        self._buf: list[str] = []

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        return set((dict(attrs).get("class") or "").split())

    def _start_capture(self, kind: str) -> None:
        self._capture = kind
        self._capture_depth = len(self._divs)
        self._buf = []

    def _end_capture(self) -> str:
        text = "".join(self._buf)
        self._capture = None
        self._buf = []
        return text.strip()

    def _in_quote(self) -> bool:
        return any("quote" in classes for classes in self._divs)

    # -- HTMLParser --------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = self._classes(attrs)
        if tag == "div":
            self._divs.append(classes)
            if "timeline-item" in classes and self._item is None:
                self._item_depth = len(self._divs)
                self._item = {"link": "", "date_href": "", "date_title": "",
                              "author": "", "content": "", "reply_text": "",
                              "quote": False}
            if self._item is not None:
                if "tweet-content" in classes:
                    self._start_capture("content")
                elif "replying-to" in classes:
                    self._start_capture("reply")
                elif "quote" in classes:
                    self._item["quote"] = True
            return

        if self._item is None:
            return
        if tag == "br" and self._capture == "content":
            self._buf.append("\n")
            return
        if tag != "a" or self._in_quote():
            return
        href = attr.get("href") or ""
        if "tweet-link" in classes:
            self._item["link"] = href
        elif self._capture == "reply" and href:
            self._item.setdefault("reply_href", href)
        if "username" in classes and not self._item["author"]:
            self._start_capture("username")
        title = attr.get("title") or ""
        if _DATE_SENTINEL.match(title):
            self._item["date_title"] = title
            self._item["date_href"] = href

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture == "username":
            self._item["author"] = self._end_capture().lstrip("@")
            return
        if tag != "div" or not self._divs:
            return
        if self._capture and len(self._divs) == self._capture_depth:
            kind = self._capture
            text = self._end_capture()
            if self._item is not None:
                if kind == "content":
                    self._item["content"] = text
                elif kind == "reply":
                    self._item["reply_text"] = text
        closing_depth = len(self._divs)
        self._divs.pop()
        if self._item is not None and closing_depth == self._item_depth:
            self._finish_item()

    def _finish_item(self) -> None:
        item = self._item
        self._item = None
        href = item["link"] or item["date_href"]
        match = STATUS_RE.search(href)
        if not match:
            return
        item_id = match.group(1)
        if self.parent is not None and item_id == self.parent["id"]:
            return
        if self.parent is not None:
            # Nitter status pages render the conversation without a
            # "replying-to" marker; the parent link comes from the URL.
            reply_to = self.parent["handle"]
            route = "status-html"
        else:
            reply_match = HANDLE_RE.search(item["reply_text"])
            reply_to = ""
            if reply_match:
                reply_to = reply_match.group(1)
            elif item.get("reply_href"):
                reply_to = item["reply_href"].strip("/").split("/")[-1]
            if not reply_to:
                return
            route = "html"
        published = parse_nitter_date(item["date_title"])
        if not published:
            return
        handle = item["author"] or ""
        metadata = {
            "is_retweet": False,
            "is_quote": item["quote"],
            "is_reply": True,
            "reply_to": reply_to,
            "provider": "nitter-html",
            "route": route,
        }
        if self.parent is not None:
            metadata["parent_tweet_id"] = self.parent["id"]
            metadata["parent_author"] = self.parent["handle"]
        self.replies.append(
            {
                "identity_key": f"x:{item_id}",
                "source_id": "x",
                "item_id": item_id,
                "publisher": handle,
                "canonical_url": f"https://x.com/{handle}/status/{item_id}" if handle else "",
                "published_at": published,
                "content": item["content"],
                "metadata": metadata,
            }
        )


def parse_profile(raw: str, handle: str | None = None, parent: dict | None = None) -> list[dict]:
    """Parse Nitter HTML into reply items.

    Profile mode filters to ``handle``; status-page mode keeps every author.
    """
    parser = _TimelineParser(parent=parent)
    parser.feed(raw)
    parser.close()
    if handle is None:
        return parser.replies
    return [item for item in parser.replies if item["publisher"].lower() == handle.lower()]


def fetch_one(handle: str, proxy: str | None, out_dir: Path, retries: int = 1) -> dict:
    dest = out_dir / f"{handle.lower()}.json"
    if dest.exists():
        try:
            payload = json.loads(dest.read_text(encoding="utf-8"))
            return {"handle": handle, "status": "cached",
                    "items": len(payload.get("items", []))}
        except Exception:
            pass
    opener = build_opener(proxy)
    errors: list[str] = []
    for base in ENDPOINTS:
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(
                    f"{base}/{handle}",
                    headers={"User-Agent": UA, "Accept": "text/html"},
                )
                with opener.open(req, timeout=20) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                if "timeline-item" not in raw:
                    raise ValueError("not a Nitter timeline page")
                items = parse_profile(raw, handle)
                dest.write_text(
                    json.dumps({"handle": handle, "status": "ok", "items": items},
                               ensure_ascii=False),
                    encoding="utf-8",
                    newline="\n",
                )
                return {"handle": handle, "status": "ok", "items": len(items)}
            except Exception as exc:
                errors.append(f"{base}: {type(exc).__name__}")
                time.sleep(0.4 * (attempt + 1))
    dest.write_text(
        json.dumps({"handle": handle, "status": "error", "items": [], "errors": errors},
                   ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    return {"handle": handle, "status": "error", "items": 0, "errors": errors[:2]}


def reply_scope_handles(roster: Path) -> list[str]:
    """Handles flagged for reply scraping (player / commentary / summary only)."""
    accounts = json.loads(roster.read_text(encoding="utf-8"))["accounts"]
    return [a["handle"] for a in accounts if a.get("reply_scope") is True]


def scope_replies(items: list[dict], scope: set[str]) -> list[dict]:
    """Keep only replies authored by a scope account; drop other people's comments."""
    return [it for it in items if (it.get("publisher") or "").lower() in scope]


def prune_cache(directories: list[Path], scope: set[str]) -> int:
    """Drop cached payloads for accounts no longer in reply scope.

    Both cache directories are read wholesale by ``gplus_slice.py``; leaving a
    stale file behind would re-merge old comments even though the fetcher no
    longer targets that account.
    """
    removed = 0
    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            if path.name == "summary.json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            handle = (payload.get("handle")
                      or (payload.get("parent") or {}).get("handle") or "").lower()
            if handle and handle not in scope:
                path.unlink()
                removed += 1
    return removed


def thread_targets(raw_dir: Path, handles: list[str], limit: int) -> list[dict]:
    """Newest own tweets of each scope account, at most ``limit`` per account.

    The Gplus RSS fetch already stores those ids; reusing them avoids walking
    the whole 40-day slice store and keeps the number of status requests
    bounded (10 scope accounts x 3 tweets = 30 by default).
    """
    targets: list[dict] = []
    for handle in handles:
        path = raw_dir / f"{handle.lower()}.json"
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8")).get("items") or []
        except Exception:
            continue
        own = [
            it for it in items
            if (it.get("publisher") or "").lower() == handle.lower()
            and not (it.get("metadata") or {}).get("is_retweet")
            and it.get("item_id")
        ]
        own.sort(key=lambda it: it.get("published_at", ""), reverse=True)
        for item in own[:limit]:
            targets.append({"id": item["item_id"], "handle": handle,
                            "published_at": item.get("published_at", "")})
    return targets


def fetch_thread(parent: dict, proxy: str | None, out_dir: Path,
                 scope: set[str], retries: int = 1) -> dict:
    """Fetch one status page; keep only replies authored by a scope account.

    A cached payload is re-filtered and rewritten too, so narrowing the roster
    scope removes previously stored comments without a re-fetch. ``scope`` is
    the full reply-scope set, not just the handles in the current run.
    """
    dest = out_dir / f"{parent['id']}.json"
    if dest.exists():
        try:
            payload = json.loads(dest.read_text(encoding="utf-8"))
            if payload.get("status") == "ok":
                items = scope_replies(payload.get("items") or [], scope)
                if len(items) != len(payload.get("items") or []):
                    payload["items"] = items
                    dest.write_text(
                        json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8", newline="\n",
                    )
                return {"id": parent["id"], "status": "cached", "items": len(items)}
        except Exception:
            pass
    opener = build_opener(proxy)
    errors: list[str] = []
    for base in ENDPOINTS:
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(
                    f"{base}/{parent['handle']}/status/{parent['id']}",
                    headers={"User-Agent": UA, "Accept": "text/html"},
                )
                with opener.open(req, timeout=20) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                if "timeline-item" not in raw:
                    raise ValueError("not a Nitter status page")
                items = scope_replies(parse_profile(raw, parent=parent), scope)
                dest.write_text(
                    json.dumps({"parent": parent, "status": "ok", "items": items},
                               ensure_ascii=False),
                    encoding="utf-8",
                    newline="\n",
                )
                return {"id": parent["id"], "status": "ok", "items": len(items)}
            except Exception as exc:
                errors.append(f"{base}: {type(exc).__name__}")
                time.sleep(0.4 * (attempt + 1))
    dest.write_text(
        json.dumps({"parent": parent, "status": "error", "items": [], "errors": errors},
                   ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    return {"id": parent["id"], "status": "error", "items": 0, "errors": errors[:2]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch Gplus info-account replies from Nitter HTML")
    ap.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "gplus" / "replies")
    ap.add_argument("--threads-dir", type=Path, default=ROOT / "out" / "gplus" / "thread_replies")
    ap.add_argument("--raw", type=Path, default=ROOT / "out" / "gplus" / "raw")
    ap.add_argument("--handles", default=None, help="comma-separated subset for a pilot run")
    ap.add_argument("--per-account", type=int, default=3, help="recent tweets per account to open")
    ap.add_argument("--no-threads", action="store_true", help="skip status-page reply fetching")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--proxy", default="auto", help="proxy URL, 'auto', or 'none'")
    ap.add_argument("--retries", type=int, default=1)
    args = ap.parse_args(argv)

    proxy = pick_proxy(None if args.proxy == "auto" else (None if args.proxy == "none" else args.proxy))
    scope_handles = reply_scope_handles(args.roster)
    scope = {h.lower() for h in scope_handles}
    handles = scope_handles
    if args.handles:
        wanted = {h.strip().lower() for h in args.handles.split(",") if h.strip()}
        handles = [h for h in handles if h.lower() in wanted]
    args.out.mkdir(parents=True, exist_ok=True)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(fetch_one, h, proxy, args.out, args.retries): h for h in handles}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    thread_results: list[dict] = []
    if not args.no_threads:
        targets = thread_targets(args.raw, handles, args.per_account)
        args.threads_dir.mkdir(parents=True, exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {
                pool.submit(fetch_thread, t, proxy, args.threads_dir, scope, args.retries): t
                for t in targets
            }
            for fut in concurrent.futures.as_completed(futures):
                thread_results.append(fut.result())

    pruned = prune_cache([args.out, args.threads_dir], scope)

    ok = [r for r in results if r["status"] == "ok"]
    cached = [r for r in results if r["status"] == "cached"]
    err = [r for r in results if r["status"] == "error"]
    th_ok = [r for r in thread_results if r["status"] in ("ok", "cached")]
    th_err = [r for r in thread_results if r["status"] == "error"]
    summary = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "proxy": proxy,
        "profiles": {"total": len(results), "ok": len(ok), "cached": len(cached),
                     "error": len(err), "replies": sum(r["items"] for r in ok + cached)},
        "threads": {"total": len(thread_results), "ok": len(th_ok), "error": len(th_err),
                    "replies": sum(r["items"] for r in th_ok)},
        "pruned_cache": pruned,
        "errors": ([{"handle": r["handle"], "detail": r.get("errors")} for r in err]
                   + [{"tweet": r["id"], "detail": r.get("errors")} for r in th_err])[:20],
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if ok or cached or th_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
