r"""Build the Gplus daily digest (one Markdown file per JST day) from the day slice.

The Gplus line has no X-Reader prompt like the other two dailies: 247 items across
105 accounts are too many to paste raw, and the interesting bits are「谁转了谁」
「今天哪些词高频」——so the writer gets this digest instead:

    # Gplus digest 2026-11-19
    items=247 accounts=105 originals=234

    ## RT clusters (target -> retweeters)

    ## Reposts (retweeter -> [id] @original: body)
    ### @kionachi x2
    - [2123414594740003293] -> @smee_official: あかん、眠すぎる。明日何とかします

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


def attribution(item: dict) -> tuple[str, str]:
    """Return (original author, retweeter) for a retweet.

    New fetch data has publisher=author and metadata.account=retweeter. Legacy
    slices stored publisher=retweeter with `RT @author:` in the body, so fall
    back to that shape when account/retweeted_by are missing.
    """
    meta = item.get("metadata") or {}
    author = str(item.get("publisher") or "").lower()
    retweeter = str(meta.get("account") or meta.get("retweeted_by") or "").lower()
    if not retweeter:
        match = re.match(r"RT\s+@([A-Za-z0-9_]{1,15})\s*:", flatten(item.get("content") or ""))
        if match:
            author, retweeter = match.group(1).lower(), author
    return author, retweeter


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

    # 谁转了谁：publisher 是原作者，metadata.account 是转发者（RSS title 的 by @…）。
    clusters: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if not (item.get("metadata") or {}).get("is_retweet"):
            continue
        author, retweeter = attribution(item)
        if not retweeter:
            continue
        clusters[author].add(retweeter)

    lines: list[str] = [
        f"# Gplus digest {day}",
        f"items={len(items)} accounts={len(publishers)} originals={len(originals)}",
        "",
        "归属铁律：`## Accounts` 只列本人原创；`## Reposts` / `## Quotes` 里的正文属于原作者，",
        "不算该账号本人发言。写 people 时 sources 至少要有一条该 handle 本人原创的 [id]。",
        "",
        "## RT clusters (target -> retweeters)",
    ]
    # 次数多的在前；同数保持「第一次出现」的顺序（dict 插入序），跟抓取顺序一致
    for target, retweeters in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        name = display(target, roster) if target in roster else "?"
        lines.append(f"- @{target} ({name}) x{len(retweeters)}: {','.join(sorted(retweeters))}")

    # 2026-11-24：转发条目在「Accounts」里是看不到的（originals only），写稿就容易
    # 把被转的内容记到转发者名下。这里给每条转单列一段，带 [id] 与原作者 handle，
    # 写 highlights/interactions 时可以直接引用并写「X 转发了 Y 的消息」。
    # 2026-11-28：Nitter RSS 的 title 是 `RT @orig (by @viewer)`，抓取端现在把
    # publisher 设成 orig、account 设成 viewer；不能再把 publisher 当转发者。
    reposts: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        meta = item.get("metadata") or {}
        if not meta.get("is_retweet"):
            continue
        original, retweeter = attribution(item)
        body = flatten(item.get("content") or "")
        reposts[retweeter or "?"].append({"id": item.get("item_id"), "original": original or "?", "body": body})

    lines.extend(["", "## Reposts (retweeter -> [id] @original: body)"])
    for retweeter, rows in sorted(reposts.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### @{retweeter} x{len(rows)}")
        for row in rows:
            lines.append(f"- [{row['id']}] -> @{row['original']}: {row['body'][:BODY_LIMIT]}")

    # 引用推：本人的话在 Accounts 里（带「引用自 @xxx」标记），引用的正文在这里单列并
    # 明确署名原作者，避免「A 引用 B 的公告」被写成「A 公布」。
    quotes: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        meta = item.get("metadata") or {}
        if not meta.get("is_quote"):
            continue
        quoter = str(item.get("publisher") or "").lower()
        quotes[quoter].append(
            {
                "id": item.get("item_id"),
                "author": str(meta.get("quoted_author") or "?").lower(),
                "own": flatten(item.get("content") or ""),
                "body": flatten(meta.get("quoted_text") or ""),
            }
        )
    lines.extend(["", "## Quotes (quoter -> [id] @quoted_author: quoted body)"])
    for quoter, rows in sorted(quotes.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### @{quoter} x{len(rows)}")
        for row in rows:
            lines.append(f"- [{row['id']}] {row['own'][:80]} || @{row['author']}: {row['body'][:BODY_LIMIT]}")

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
            # 分片压缩只保留 `### 账号` 与 `- [id]` 两种行，Reposts/Quotes 段会被丢掉；
            # 归属标记必须内联在 bullet 上，写稿时才不会把引用内容算成本人原创。
            meta = row.get("metadata") or {}
            if meta.get("is_quote"):
                body = f"· 引用了 @{str(meta.get('quoted_author') or '?').lower()}（引用正文见 Quotes 段）：{body}"
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
