"""期号规则（从 `scripts/daily_digest.py` 迁入，行为不变）。

期号 = 发布时间 = 网址：`YYMMDDHH`（JST）。只到天的话一天只能一期，重跑会冲掉上一期；
精确到小时后每跑一次都是新文件，旧的一期自动留档。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 日报内容是日本声优的一天，用 JST 才不会把深夜的推分错天
JST = timezone(timedelta(hours=9))


def issue_id_for(moment: datetime) -> str:
    """把时刻写成期号 `YYMMDDHH`（JST）。"""
    return moment.astimezone(JST).strftime("%y%m%d%H")


def parse_at(text: str) -> datetime:
    """解析 `--at`，接受 `2026-10-31 22:00` / `2026-10-31T22:00` / `2026-10-31`。"""
    raw = text.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    raise SystemExit(f"--at 解析不了：{text!r}（用 2026-10-31 22:00 这种写法）")
