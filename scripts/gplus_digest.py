r"""Build the Gplus daily digest (one Markdown file per JST day) from the day slice.

The Gplus line has no X-Reader prompt like the other two dailies: 247 items across
105 accounts are too many to paste raw, and the interesting bits are「谁转了谁」
「今天哪些词高频」——so the writer gets this digest instead:

    # Gplus digest 2026-11-19
    items=247 accounts=105 originals=234

    ## RT clusters (target -> retweeters)
    ## Keyword topics
    ## Accounts (originals only, group | name | handle | brand)
    ### creator | 木緒なち | @kionachi | — | n=8
    - [2123414594740003293] あかん、眠すぎる。明日何とかします

Format is fixed on purpose: it is read by the model that writes
`out/gplus/reports/Gplus_NNN.json`, and by a human debugging that draft.

Usage:
    python scripts/gplus_digest.py --date 2026-11-19
    python scripts/gplus_digest.py                 # 昨天（JST）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
SLICES = ROOT / "data" / "xreader" / "gplus"
DIGESTS = ROOT / "out" / "gplus" / "digest"
ROSTER = ROOT / "src" / "config" / "gplus-roster.json"

# 观察「今天业界在说什么」用的固定词表。不去猜新词：同一个词表才能和昨天的数字比。
KEYWORDS = [
    "発売", "予約", "公開", "決定", "OP", "新作", "締切", "CV", "Steam", "コラボ",
    "イベント", "DLsite", "抽選", "原画", "受賞", "体験版", "FANZA", "シナリオ",
    "キャスト", "出展",
]
BODY_LIMIT = 260


def load_roster() -> tuple[dict[str, dict], dict[str, int]]:
    data = json.loads(ROSTER.read_text(encoding="utf-8"))
    accounts = data.get("accounts") or []
    info: dict[str, dict] = {}
    order: dict[str, int] = {}
    for index, account in enumerate(accounts):
        handle = str(account.get("handle") or "").lower()
        if not handle:
            continue
        info[handle] = account
        order.setdefault(handle, index)
    return info, order


def flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def display(handle: str, roster: dict[str, dict]) -> str:
    account = roster.get(handle) or {}
    name = str(account.get("name") or "").strip()
    return name or f"@{handle}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Gplus daily digest")
    ap.add_argument("--date", default=None, help="JST 日期 YYYY-MM-DD，默认昨天")
    ap.add_argument("--dest", type=Path, default=DIGESTS)
    args = ap.parse_args(argv)

    day = args.date or (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
    src = SLICES / f"{day}.jsonl"
    if not src.exists():
        print(f"missing slice: {src}", file=sys.stderr)
        return 2

    items = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not items:
        print(f"empty slice: {src}", file=sys.stderr)
        return 2

    roster, order = load_roster()
    originals = [item for item in items if not (item.get("metadata") or {}).get("is_retweet")]

    publishers = Counter(str(item.get("publisher") or "").lower() for item in items)
    by_account: dict[str, list[dict]] = defaultdict(list)
    for item in originals:
        by_account[str(item.get("publisher") or "").lower()].append(item)

    # 谁转了谁：`RT @handle:` 开头的那批，按被转次数排；同数按 handle 排，输出才稳定
    clusters: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if not (item.get("metadata") or {}).get("is_retweet"):
            continue
        match = re.match(r"RT\s+@([A-Za-z0-9_]+)\s*:", flatten(item.get("content") or ""))
        if not match:
            continue
        clusters[match.group(1).lower()].add(str(item.get("publisher") or "").lower())

    lines: list[str] = [
        f"# Gplus digest {day}",
        f"items={len(items)} accounts={len(publishers)} originals={len(originals)}",
        "",
        "## RT clusters (target -> retweeters)",
    ]
    # 次数多的在前；同数保持「第一次出现」的顺序（dict 插入序），跟抓取顺序一致
    for target, retweeters in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        name = display(target, roster) if target in roster else "?"
        lines.append(f"- @{target} ({name}) x{len(retweeters)}: {','.join(sorted(retweeters))}")

    lines.extend(["", "## Keyword topics"])
    hits = Counter()
    for word in KEYWORDS:
        count = sum(1 for item in items if word in (item.get("content") or ""))
        if count:
            hits[word] = count
    # 词表顺序就是同数时的顺序（stable sort）
    ranked = sorted(KEYWORDS, key=lambda word: -hits.get(word, 0))
    lines.append(", ".join(f"{word}:{hits[word]}" for word in ranked if hits.get(word)))

    lines.extend(["", "## Accounts (originals only, group | name | handle | brand)"])
    for handle, rows in sorted(by_account.items(), key=lambda kv: (-len(kv[1]), order.get(kv[0], 9999))):
        account = roster.get(handle) or {}
        group = str(account.get("group") or "—")
        brand = str(account.get("brand") or "").strip() or "—"
        lines.append(f"### {group} | {display(handle, roster)} | @{handle} | {brand} | n={len(rows)}")
        # 保持切片里的顺序（抓取时就是新→旧），不另外排序：
        # 排过序反而和原文的「先说了什么」对不上，写稿时会误判时间线
        for row in rows:
            body = flatten(row.get("content") or "")[:BODY_LIMIT]
            lines.append(f"- [{row.get('item_id')}] {body}")

    args.dest.mkdir(parents=True, exist_ok=True)
    target = args.dest / f"{day}.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    try:
        shown = target.resolve().relative_to(ROOT)
    except ValueError:
        shown = target
    # 覆盖到几点：出稿前要一眼看出抓取是不是只抓了半天
    last = max(
        (datetime.fromisoformat(str(item.get("published_at")).replace("Z", "+00:00")) for item in items),
        default=None,
    )
    tail = last.astimezone(JST).strftime("%H:%M") if last else "?"
    print(
        f"{shown}  items={len(items)} accounts={len(publishers)} originals={len(originals)} last={tail} JST"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
