#!/usr/bin/env python3
"""X-Reader 每日推特日报的「本地组装」脚本（薄壳）。

真正的实现已经搬到 `scripts/daily/`（见 `public/docs/dailyrp-projectstatus.html` 的 M1）。
这个文件只保留**旧的导入路径与命令行参数**，一行逻辑都不写：

    python scripts/daily_digest.py --items-dir /path/to/X-Reader/data/items
    python scripts/daily_digest.py --items-dir ... --at "2026-10-31 22:00"
    python scripts/daily_digest.py --items-dir ... --date 2026-10-24
    python scripts/daily_digest.py --items-dir ... --check-reproducible

四段内容由**本地 WorkBuddy（LLM）**填写，脚本不碰 LLM / 不调 API。
站点只渲染 frontmatter，不展示互动数——那些数字只留在 briefing 里供模型判断轻重。

`tests/test_daily_digest.py` 仍然按老接口导入本文件，所以下面这些名字要留着：
`JST` / `issue_id_for` / `_parse_at` / `build_report` / `build_briefing`。
期号改到「只到天」之后，`parse_issue_id` / `day_of` / `seq_of` / `is_issue_id` 也一并转出去。
"""
from __future__ import annotations

import sys
from datetime import date as date_cls
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily.adapters.xreader import load_raw  # noqa: E402
from daily.build import build_briefing as _build_briefing  # noqa: E402
from daily.build import build_report as _build_report  # noqa: E402
from daily.cli import main as _cli_main  # noqa: E402
from daily.issue import JST, day_of, is_issue_id, issue_id_for, parse_issue_id, seq_of  # noqa: E402
from daily.issue import parse_at as _parse_at  # noqa: E402
from daily.model import Item  # noqa: E402


def _as_items(records: list) -> list[Item]:
    """老接口吃的是原始 dict，这里统一转成 `Item`。"""
    return [r if isinstance(r, Item) else Item.from_xreader(r) for r in records]


def _load_items(items_dir: Path) -> list[dict]:
    """兼容旧接口：返回原始 dict 列表。"""
    return load_raw(items_dir)


def _display_handle(item: dict) -> str:
    return Item.from_xreader(item).account


def _date_of(item: dict, fallback: date_cls) -> date_cls:
    return Item.from_xreader(item).date() or fallback


def _engagement(item: dict) -> int:
    return Item.from_xreader(item).engagement.score()


def build_briefing(records: list, report_date: date_cls) -> str:
    return _build_briefing(_as_items(records), report_date)


def build_report(records: list, issue_id: str) -> dict:
    """老的「出骨架」接口。M4 之前返回 Markdown 文本，现在返回 report.json 的内容。"""
    return _build_report(_as_items(records), issue_id)


def main() -> int:
    # 老接口是 `daily_digest.py --items-dir ...`（等于 build 的参数）。
    # M3 之后多了 prompt / apply / confirm，M4 又加了 publish / migrate，
    # 这些子命令不能在前面塞 "build"。
    argv = sys.argv[1:]
    if argv and argv[0] in {
        "build",
        "prompt",
        "apply",
        "audit",
        "confirm",
        "publish",
        "migrate",
        "ja",
        "state",
        "version",
    }:
        return _cli_main(argv)
    return _cli_main(["build"] + argv)


if __name__ == "__main__":
    raise SystemExit(main())
