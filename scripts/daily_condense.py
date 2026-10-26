#!/usr/bin/env python3
"""把 briefing 压成「一眼能看完」的编辑视图，给写稿那一步用。

briefing 本身是全量留档（一个 128 人的日子约 9 万字 / 5 万 token），直接读进来
既慢又贵，而且大部分条目对成稿没有影响——日报最终只有 4 段加每人一句话。

这个脚本做四件事，全部是规则，不涉及模型：

1. 去掉每条推文后面的 status URL（成稿不需要逐条链接）
2. 去掉 `[❤N 🔁N]` 互动数（抓取里经常全是 0）
3. 默认丢掉纯转发（`RT by @` / `RT @`），只留本人发言
4. 每个账号挑「带公告关键词的」优先，其余按原顺序补到 `--per-account` 条

输出是给人读的，不是给站点读的；写完稿就可以删。

用法：

    python scripts/daily_condense.py out/26102522.briefing.txt > out/26102522.condensed.txt
    python scripts/daily_condense.py out/26102522.briefing.txt --per-account 3 --width 100
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

URL_LINE = re.compile(r"^\s+https://x\.com/\S+\s*$", re.M)
ENGAGE = re.compile(r"\[❤(\d+) 🔁(\d+)\] ")

# 「这条值得展开写」的判据。宁可宽一点：漏掉一条发售公告，比多读十条日常更糟。
KEY = re.compile(
    r"発売|予約|配信|販売|新作|お知らせ|告知|収録|登場|発売日|リリース|受注|特典|"
    r"発売中|体験版|アップデート|キャンペーン|イベント|生誕|誕生日|記念|投票|"
    r"出演|参加|決定|公開|開始|限定|予告|PV|トレーラー|セール|割引|ランキング|位"
)


def main() -> None:
    ap = argparse.ArgumentParser(description="把 briefing 压成编辑视图")
    ap.add_argument("briefing", type=Path)
    ap.add_argument("--per-account", type=int, default=3, help="每个账号最多显示几条（默认 3）")
    ap.add_argument("--width", type=int, default=90, help="每条截断到多少字（默认 90）")
    ap.add_argument("--keep-rt", action="store_true", help="保留纯转发（默认丢掉）")
    args = ap.parse_args()

    text = URL_LINE.sub("", ENGAGE.sub("", args.briefing.read_text(encoding="utf-8")))
    blocks = re.split(r"(?m)^## @(\S+)\s+\((\d+) tweets\)$", text)

    for i in range(1, len(blocks), 3):
        handle, count, body = blocks[i], blocks[i + 1], blocks[i + 2]
        items = ["- " + x.strip() for x in re.split(r"(?m)^- ", body)[1:]]
        plain = [x for x in items if args.keep_rt or not x.startswith("- RT")]
        rts = len(items) - len(plain)

        flagged, rest = [], []
        for item in plain:
            flat = re.sub(r"\s+", " ", item[2:]).strip()
            if not flat:
                continue
            (flagged if KEY.search(flat) else rest).append(flat)

        chosen = flagged + rest[: max(0, args.per_account - len(flagged))]
        if not chosen:
            continue
        print(f"\n## @{handle}  ({count} 条, RT {rts})")
        for line in chosen:
            print("  " + (line[: args.width] + "…" if len(line) > args.width else line))
        if len(plain) > len(chosen):
            print(f"  (+{len(plain) - len(chosen)} 条未显示)")


if __name__ == "__main__":
    main()
