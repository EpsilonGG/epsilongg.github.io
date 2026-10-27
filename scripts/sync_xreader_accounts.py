#!/usr/bin/env python3
"""把站点名单里**在用的账号**同步成 X-Reader 的 `accounts.yaml`。

为什么要有这一步：抓取侧（X-Reader）和展示侧（本站日报）各有一份账号清单，
两边不一致时会出现两种都很难查的现象——

* X-Reader 抓了名单外的号 → 日报里冒出没人认领的推文；
* 名单里的人 X-Reader 没抓 → 「当日无活动」，看起来像她那天真没发推。

所以这里只做一件事：`daily-roster.json` 里 `active != false` 的 handle，
按名单顺序写成 `accounts.yaml`。分类（声优 / 制造商）不参与判断——
它决定的是条目落在页面哪个栏目，而栏目由日报页的筛选按钮分开看。
社团号现在仍是 `active: false`，不会被写进去。

用法：

    python scripts/sync_xreader_accounts.py \
        --out "../X-rss-workspace/X-Reader/accounts.yaml"

    python scripts/sync_xreader_accounts.py --out ... --check   # 只比对，不写

`--check` 在两边不一致时以退出码 1 结束，适合放进 CI 或提交前的手检。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROSTER = REPO_ROOT / "src" / "config" / "daily-roster.json"

HEADER = """\
# Accounts that X-Reader tracks over time.
#
# GENERATED FILE -- do not edit by hand.
# Source of truth: src/config/daily-roster.json in the site repository
# (EpsilonGG/epsilongg.github.io). Regenerate with:
#
#   python scripts/sync_xreader_accounts.py --out <this file>
#
# Only entries with `active != false` are written, in roster order. The roster's
# `category` field is *not* a filter here: it decides which column an entry shows
# up in on the site, and the daily page's filter buttons separate the columns.
#
# 名单里每个 handle 的 role（main / sub / announce）不写进这个文件——抓取侧不
# 关心它是主号还是小号，抓全就行；role 只在站点侧决定展示顺序。

accounts:
"""


def load_handles(path: Path = ROSTER) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    handles: list[str] = []
    seen: set[str] = set()
    for account in data.get("accounts", []):
        # 只按 `active` 判断要不要抓：分类决定它在页面上落在哪个栏目，
        # 不决定抓不抓。2026-10-27 起制造商也是 active，栏目用筛选按钮分开看。
        if account.get("active", True) is False:
            continue
        handle = str(account.get("handle") or "").strip()
        if not handle:
            continue
        key = handle.lower()
        if key in seen:
            continue
        seen.add(key)
        handles.append(handle)
    return handles


def render(handles: list[str]) -> str:
    body = "".join(f"  - username: {handle}\n" for handle in handles)
    return HEADER + body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync the roster into X-Reader's accounts.yaml")
    parser.add_argument("--out", required=True, type=Path, help="path to X-Reader/accounts.yaml")
    parser.add_argument("--roster", type=Path, default=ROSTER, help="override the roster path")
    parser.add_argument("--check", action="store_true", help="report drift and exit 1 instead of writing")
    args = parser.parse_args(argv)

    handles = load_handles(args.roster)
    if not handles:
        print("名单里没有可用的声优账号，拒绝写空文件", file=sys.stderr)
        return 2

    expected = render(handles)
    out: Path = args.out
    current = out.read_text(encoding="utf-8") if out.exists() else ""

    if args.check:
        if current == expected:
            print(f"一致：{len(handles)} 个账号")
            return 0
        print(f"不一致：名单 {len(handles)} 个账号，文件里 {current.count('- username:')} 个", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(expected, encoding="utf-8", newline="\n")
    print(f"写入 {out}：{len(handles)} 个账号")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
