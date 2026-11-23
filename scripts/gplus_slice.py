r"""Slice Gplus raw RSS fetch into per-JST-day JSONL (rolling store).

Raw fetch lives in out/gplus/raw/ (gitignored). This script writes the
committed store data/xreader/gplus/<JST date>.jsonl using the same shape as
data/xreader/galgame/*.jsonl, then drops days older than --keep.

Since 2026-11-23 it also merges out/gplus/replies/ (from gplus_replies.py)
into the same day files. Reply items carry is_reply/reply_to metadata that
RSS items can never have. Existing lines are preserved verbatim: a raw fetch
only carries ~20 items per account, while the committed store holds weeks of
history, so re-slicing must never drop older items.

Usage:
    python scripts/gplus_slice.py --raw out/gplus/raw --keep 40
    python scripts/gplus_slice.py --replies out/gplus/replies   # replies only
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
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


def item_key(item: dict) -> str:
    return str(item.get("item_id") or item.get("identity_key") or "")


def load_items(directory: Path) -> dict[str, dict[str, dict]]:
    """Read raw/replies payloads into {day: {key: item}}."""
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    if not directory.exists():
        return by_day
    for f in sorted(directory.glob("*.json")):
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
            by_day[dt.date().isoformat()][item_key(item)] = item
    return by_day


def write_day(path: Path, items: dict[str, dict]) -> int:
    """Merge into the existing day file; keep old lines byte-for-byte.

    Re-slicing from a fresh 20-item-per-account raw fetch must not erase the
    weeks of history already committed. An authored-reply item (route=html)
    replaces its RSS counterpart so the richer metadata wins; a status-page
    reply (route=status-html) never replaces an existing item, because Nitter
    status markup only has minute precision and drops the RSS line breaks.
    Duplicate legacy lines are preserved, not collapsed.
    """
    replacements = {
        key: json.dumps(item, ensure_ascii=False)
        for key, item in items.items()
        if (item.get("metadata") or {}).get("route") != "status-html"
    }
    additions = {
        key: json.dumps(item, ensure_ascii=False)
        for key, item in items.items()
        if key not in replacements
    }
    output: list[str] = []
    existing_keys: set[str] = set()
    if path.exists():
        # str.splitlines() also splits on U+2028/U+2029, which occur inside
        # real tweet text. Only '\n' separates JSONL records.
        for line in path.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            try:
                key = item_key(json.loads(line))
            except json.JSONDecodeError:
                output.append(line)
                continue
            existing_keys.add(key)
            if key in replacements:
                output.append(replacements[key])
            else:
                output.append(line)
    output.extend(line for key, line in replacements.items() if key not in existing_keys)
    output.extend(line for key, line in additions.items() if key not in existing_keys)
    path.write_text(
        "".join(line + "\n" for line in output),
        encoding="utf-8",
        newline="\n",
    )
    return len(output)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Slice Gplus raw fetch into JST-day JSONL")
    ap.add_argument("--raw", type=Path, default=ROOT / "out" / "gplus" / "raw")
    ap.add_argument("--replies", type=Path, default=ROOT / "out" / "gplus" / "replies")
    ap.add_argument("--threads", type=Path, default=ROOT / "out" / "gplus" / "thread_replies")
    ap.add_argument("--dest", type=Path, default=ROOT / "data" / "xreader" / "gplus")
    ap.add_argument("--keep", type=int, default=40)
    args = ap.parse_args(argv)

    args.dest.mkdir(parents=True, exist_ok=True)
    # RSS feeds hold the newest ~20 tweets per account, so inactive accounts
    # contribute items from years ago, and a mid-day fetch already carries a
    # few items from today. Anchor the retention window to the committed store
    # *and* the fresh raw fetch, then ignore anything outside it instead of
    # materialising 800 day files.
    #
    # 2026-11-23 修：原先只按已落盘日锚定，库停在昨天时新抓到的今天整天都会被
    # 窗口挡掉（跑完 2026-11-23 一片都没写，看起来像「没数据」）。现在两边取
    # 并集，并把上界钉在「JST 昨天」——当天的半截数据不落盘，等次日抓全再切。
    raw_by_day = load_items(args.raw)
    existing_days = {p.stem for p in args.dest.glob("????-??-??.jsonl")}
    anchor_days = existing_days | set(raw_by_day)
    if anchor_days:
        newest = max(date.fromisoformat(day) for day in anchor_days)
        keep_to = min(newest, datetime.now(JST).date() - timedelta(days=1))
        keep_from = keep_to - timedelta(days=max(args.keep, 1) - 1)
    else:
        keep_to = keep_from = None

    def in_window(day: str) -> bool:
        return keep_from is None or keep_from <= date.fromisoformat(day) <= keep_to

    by_day = {day: items for day, items in raw_by_day.items() if in_window(day)}
    reply_count = 0
    for directory in (args.replies, args.threads):
        for day, items in load_items(directory).items():
            if not in_window(day):
                continue
            by_day.setdefault(day, {}).update(items)
            reply_count += len(items)

    written = {}
    for day, items in by_day.items():
        written[day] = write_day(args.dest / f"{day}.jsonl", items)

    # Rolling retention, keep the newest N days by filename.
    files = sorted(args.dest.glob("????-??-??.jsonl"))
    for old in files[: max(0, len(files) - args.keep)]:
        old.unlink()

    for day in sorted(written):
        if day >= "2026-11-18":
            print(f"{day}: {written[day]} items")
    print(f"merged {reply_count} replies; wrote {len(written)} day files to {args.dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
