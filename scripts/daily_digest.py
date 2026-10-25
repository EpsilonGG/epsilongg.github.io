#!/usr/bin/env python3
"""X-Reader 每日推特日报的「本地组装」脚本（薄壳）。

真正的实现已经搬到 `scripts/daily/`（见 `public/docs/dailyrp-projectstatus.html` 的 M1）。
这个文件只保留**旧的导入路径与命令行参数**，一行逻辑都不写：

    python scripts/daily_digest.py --items-dir /path/to/X-Reader/data/items
    python scripts/daily_digest.py --items-dir ... --at "2026-10-31 22:00"
    python scripts/daily_digest.py --items-dir ... --date 2026-10-24
    python scripts/daily_digest.py --items-dir ... --check-reproducible

三段内容由**本地 WorkBuddy（LLM）**填写，脚本不碰 LLM / 不调 API。
站点只渲染 frontmatter，不展示互动数——那些数字只留在 briefing 里供模型判断轻重。

`tests/test_daily_digest.py` 仍然按老接口导入本文件，所以下面这些名字要留着：
`JST` / `issue_id_for` / `_parse_at` / `build_markdown` / `build_briefing`。
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
from daily.build import build_markdown as _build_markdown  # noqa: E402
from daily.cli import main as _cli_main  # noqa: E402
from daily.issue import JST, issue_id_for  # noqa: E402
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


def build_markdown(records: list, issue_id: str) -> str:
    return _build_markdown(_as_items(records), issue_id)


def main() -> int:
    return _cli_main(["build"] + sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
