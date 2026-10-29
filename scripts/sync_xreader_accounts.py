#!/usr/bin/env python3
"""把站点名单里**在用的账号**同步成 X-Reader 的 `accounts.yaml`。

为什么要有这一步：抓取侧（X-Reader）和展示侧（本站日报）各有一份账号清单，
两边不一致时会出现两种都很难查的现象——

* X-Reader 抓了名单外的号 → 日报里冒出没人认领的推文；
* 名单里的人 X-Reader 没抓 → 「当日无活动」，看起来像她那天真没发推。

2026-10-29 起日报一天出两份，名单也拆成两份，所以这里**写两个文件**：

    src/config/daily-roster.json          → accounts.yaml          （声优版：声优 + 音声社团）
    src/config/daily-roster-galgame.json  → accounts.galgame.yaml  （Galgame 版：制造商 + 信息号）

X-Reader 那边用两个 workflow 分别跑（`--accounts` 指到各自的文件，
`--config` 指到各自的 data_dir），互不阻塞。

分类（声优 / 音声社团 / 制造商 / 信息号）不参与判断——它决定的是条目落在页面
哪个栏目，而栏目由日报页的筛选按钮分开看。

用法：

    python scripts/sync_xreader_accounts.py \
        --out "../X-rss-workspace/X-Reader/accounts.yaml"

    # 不给 --galgame-out 时，默认写在 --out 同目录的 accounts.galgame.yaml
    python scripts/sync_xreader_accounts.py --out ... --galgame-out ...

    python scripts/sync_xreader_accounts.py --out ... --check   # 只比对，不写

`--check` 在两边不一致时以退出码 1 结束，适合放进 CI 或提交前的手检。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROSTERS = {
    "voice": REPO_ROOT / "src" / "config" / "daily-roster.json",
    "galgame": REPO_ROOT / "src" / "config" / "daily-roster-galgame.json",
}

HEADER = """\
# Accounts that X-Reader tracks over time.
#
# GENERATED FILE -- do not edit by hand.
# Source of truth: {source} in the site repository
# (EpsilonGG/epsilongg.github.io). Regenerate with:
#
#   python scripts/sync_xreader_accounts.py --out <this file> --galgame-out <the other one>
#
# {note}
#
# Only entries with `active != false` are written, in roster order. The roster's
# `category` field is *not* a filter here: it decides which column an entry shows
# up in on the site, and the daily page's filter buttons separate the columns.
#
# 名单里每个 handle 的 role（main / sub / announce / circle / brand / info）不写进
# 这个文件——抓取侧不关心它是主号还是小号，抓全就行；role 只在站点侧决定展示顺序。

accounts:
"""

NOTES = {
    "voice": "This file is the VOICE edition: 声优 + 音声社团. "
    "The Galgame edition (制造商 + 信息号) is accounts.galgame.yaml.",
    "galgame": "This file is the GALGAME edition: 游戏制造商 + 信息号. "
    "The voice edition (声优 + 音声社团) is accounts.yaml.",
}


def load_handles(kind: str, path: Path | None = None) -> list[str]:
    source = Path(path) if path else ROSTERS[kind]
    data = json.loads(source.read_text(encoding="utf-8"))
    handles: list[str] = []
    seen: set[str] = set()
    for account in data.get("accounts", []):
        # 只按 `active` 判断要不要抓：分类决定它在页面上落在哪个栏目，
        # 不决定抓不抓。
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


def render(kind: str, handles: list[str], source: Path) -> str:
    try:
        rel = source.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = str(source)
    body = "".join(f"  - username: {handle}\n" for handle in handles)
    return HEADER.format(source=rel, note=NOTES[kind]) + body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync both rosters into X-Reader's accounts yaml")
    parser.add_argument("--out", type=Path, help="声优版输出路径（X-Reader/accounts.yaml）")
    parser.add_argument("--galgame-out", type=Path, help="Galgame 版输出路径（默认与 --out 同目录）")
    parser.add_argument("--roster", type=Path, help="覆盖声优版名单路径（默认 src/config/daily-roster.json）")
    parser.add_argument("--galgame-roster", type=Path, help="覆盖 Galgame 版名单路径")
    parser.add_argument("--check", action="store_true", help="report drift and exit 1 instead of writing")
    args = parser.parse_args(argv)

    if not args.out and not args.galgame_out:
        parser.error("至少给一个 --out / --galgame-out")

    jobs: list[tuple[str, Path, Path]] = []
    if args.out:
        jobs.append(("voice", args.out, args.roster or ROSTERS["voice"]))
    if args.galgame_out:
        jobs.append(("galgame", args.galgame_out, args.galgame_roster or ROSTERS["galgame"]))
    elif args.out:
        sibling = args.out.parent / "accounts.galgame.yaml"
        jobs.append(("galgame", sibling, args.galgame_roster or ROSTERS["galgame"]))
        print(f"未给 --galgame-out，Galgame 版写到同目录：{sibling}", file=sys.stderr)

    code = 0
    for kind, out, source in jobs:
        handles = load_handles(kind, source)
        if not handles:
            print(f"{kind}: 名单里没有可用的账号，拒绝写空文件", file=sys.stderr)
            code = 2
            continue

        expected = render(kind, handles, source)
        current = out.read_text(encoding="utf-8") if out.exists() else ""

        if args.check:
            if current == expected:
                print(f"{kind} 一致：{len(handles)} 个账号（{out}）")
            else:
                print(
                    f"{kind} 不一致：名单 {len(handles)} 个账号，"
                    f"文件里 {current.count('- username:')} 个（{out}）",
                    file=sys.stderr,
                )
                code = 1
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(expected, encoding="utf-8", newline="\n")
        print(f"写入 {out}（{kind}）：{len(handles)} 个账号")

    return code


if __name__ == "__main__":
    raise SystemExit(main())
