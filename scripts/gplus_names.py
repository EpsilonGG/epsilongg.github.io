r"""Cache display names of retweeted authors that are outside the Gplus roster.

`gplus_digest.py` writes 「转发了某人的消息」 material into its Reposts/Quotes
sections.  The roster covers only scraped accounts; the original author of a
retweet is often outside it, so their display name has to be looked up once and
kept in `data/gplus-author-names.json`.

Usage:
    python scripts/gplus_names.py --date 2026-11-27 --proxy http://127.0.0.1:7897
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import urllib.request
from pathlib import Path

# fxtwitter 的 name 常带 emoji 与「@接稿中」这类尾巴；叙述里只要干净的人名。
_NAME_TAIL = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF@#【】\[\]「」『』（）()]")

ROOT = Path(__file__).resolve().parents[1]
SLICES = ROOT / "data" / "xreader" / "gplus"
ROSTER = ROOT / "src" / "config" / "gplus-roster.json"
NAMES = ROOT / "data" / "gplus-author-names.json"


def clean_name(value: str) -> str:
    name = _NAME_TAIL.split(value, 1)[0].strip()
    return name or value.strip()


def roster_handles() -> set[str]:
    data = json.loads(ROSTER.read_text(encoding="utf-8"))
    return {str(a.get("handle", "")).lower() for a in data.get("accounts", []) if a.get("handle")}


def retweet_authors(day: str) -> set[str]:
    path = SLICES / f"{day}.jsonl"
    if not path.exists():
        return set()
    authors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        meta = item.get("metadata") or {}
        if not (meta.get("is_retweet") or meta.get("is_quote")):
            continue
        author = str(item.get("publisher") or "").lower()
        if author:
            authors.add(author)
        quoted = str(meta.get("quoted_author") or "").lower()
        if quoted:
            authors.add(quoted)
    return authors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cache display names for Gplus retweet authors")
    ap.add_argument("--date", required=True, help="JST date YYYY-MM-DD")
    ap.add_argument("--proxy", default="http://127.0.0.1:7897")
    args = ap.parse_args(argv)

    cached = {}
    if NAMES.exists():
        try:
            cached = json.loads(NAMES.read_text(encoding="utf-8"))
        except Exception:
            cached = {}
    names = {str(k).lower(): clean_name(str(v)) for k, v in cached.items() if v}
    targets = sorted(retweet_authors(args.date) - roster_handles() - set(names))
    if not targets:
        print(f"gplus-names: no new authors for {args.date}; cache={len(names)}")
        return 0

    proxy = urllib.request.ProxyHandler({"http": args.proxy, "https": args.proxy}) if args.proxy else None
    opener = urllib.request.build_opener(proxy) if proxy else urllib.request.build_opener()

    def lookup(handle: str) -> tuple[str, str]:
        for _ in range(2):
            try:
                payload = json.load(opener.open(f"https://api.fxtwitter.com/{handle}", timeout=12))
                display_name = clean_name(str((payload.get("user") or {}).get("name") or ""))
                if display_name:
                    return handle, display_name
            except Exception:
                continue
        return handle, ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for handle, display_name in pool.map(lookup, targets):
            if display_name:
                names[handle] = display_name

    NAMES.parent.mkdir(parents=True, exist_ok=True)
    NAMES.write_text(
        json.dumps(names, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"gplus-names: {len(targets)} looked up, cache={len(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
