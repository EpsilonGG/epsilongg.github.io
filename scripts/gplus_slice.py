r"""Slice Gplus raw RSS fetch into per-JST-day JSONL (rolling store).

Raw fetch lives in out/gplus/raw/ (gitignored). This script writes the
committed store data/xreader/gplus/<JST date>.jsonl using the same shape as
data/xreader/galgame/*.jsonl, then drops days older than --keep.

Usage:
    python scripts/gplus_slice.py --raw out/gplus/raw --keep 40
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))


def parse_dt(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Slice Gplus raw fetch into JST-day JSONL")
    ap.add_argument("--raw", type=Path, default=ROOT / "out" / "gplus" / "raw")
    ap.add_argument("--dest", type=Path, default=ROOT / "data" / "xreader" / "gplus")
    ap.add_argument("--keep", type=int, default=40)
    args = ap.parse_args(argv)

    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for f in sorted(args.raw.glob("*.json")):
        if f.name == "summary.json":
            continue
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("status") != "ok":
            continue
        for item in payload.get("items") or []:
            dt = parse_dt(item.get("published_at", ""))
            if not dt:
                continue
            day = dt.date().isoformat()
            key = item.get("item_id") or item.get("identity_key")
            by_day[day][key] = item

    args.dest.mkdir(parents=True, exist_ok=True)
    written = {}
    for day, items in by_day.items():
        path = args.dest / f"{day}.jsonl"
        path.write_text(
            "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items.values()),
            encoding="utf-8",
            newline="\n",
        )
        written[day] = len(items)

    # Rolling retention, keep the newest N days by filename.
    files = sorted(args.dest.glob("????-??-??.jsonl"))
    for old in files[: max(0, len(files) - args.keep)]:
        old.unlink()

    for day in sorted(written):
        if day >= "2026-11-18":
            print(f"{day}: {written[day]} items")
    print(f"wrote {len(written)} day files to {args.dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
