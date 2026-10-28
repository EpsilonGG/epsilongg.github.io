"""期号规则。

期号 = **被覆盖的那一天**：`YYMMDD`（JST）。同一天要出第二期时加 `-2`、`-3`——
`261027`、`261027-2`。

为什么不再带小时（旧格式是 `YYMMDDHH`）：一天的数据要到 JST 24:00 才闭合
（X-Reader 的 CI 每天 15:00 UTC 抓最后一次），真实出稿必然落在次日凌晨。
把小时写进期号只有两条路，两条都不对：

* 写真实时间 → 次日 01 点，期号比内容晚一天，归档会把 10-27 的日报排到 10-28 下面；
* 钉一个假时间 → 旧格式就是这么做的（固定 22:00），于是页面上的「发布于 22:00」
  比实际早约 3.5 小时。

所以期号只说「这是哪一天的日报」，发布时间另有字段（`issue.published_at`），
那个是真的。一天出两期是例外，用 `-2` 表示，仍然不引入「小时」这个维度。
"""
from __future__ import annotations

import re
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

# 日报内容是日本声优的一天，用 JST 才不会把深夜的推分错天
JST = timezone(timedelta(hours=9))

# `261027` / `261027-2`。用 `-` 而不是直接接数字：`2610272` 分不清是
# 「10-27 第 2 期」还是「10-27 02 时」（旧格式的读法）。
ID_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})(?:-(\d+))?$")


def issue_id_for(day: date_cls, seq: int = 1) -> str:
    """`2026-10-27` + 第 1 期 → `261027`；第 2 期 → `261027-2`。"""
    if seq < 1:
        raise ValueError(f"期序号从 1 开始，收到 {seq}")
    base = day.strftime("%y%m%d")
    return base if seq == 1 else f"{base}-{seq}"


def parse_issue_id(text: str) -> tuple[date_cls, int]:
    """`261027-2` → `(date(2026,10,27), 2)`。格式不对或日期不存在就抛 ValueError。"""
    raw = text.strip()
    match = ID_RE.match(raw)
    if not match:
        raise ValueError(f"期号 {raw!r} 不是 YYMMDD 或 YYMMDD-N")
    year, month, day = (int(match.group(i)) for i in (1, 2, 3))
    seq = int(match.group(4) or 1)
    if match.group(4) and seq < 2:
        raise ValueError(f"期号 {raw!r} 的序号要从 2 起（第 1 期不写后缀）")
    try:
        covered = date_cls(2000 + year, month, day)
    except ValueError:
        raise ValueError(f"期号 {raw!r} 里没有这一天（{2000 + year}-{month:02d}-{day:02d}）") from None
    return covered, seq


def day_of(issue_id: str) -> date_cls:
    """期号覆盖的那一天。"""
    return parse_issue_id(issue_id)[0]


def seq_of(issue_id: str) -> int:
    """同一天里的第几期（第 1 期是 1）。"""
    return parse_issue_id(issue_id)[1]


def is_issue_id(text: str) -> bool:
    try:
        parse_issue_id(text)
    except ValueError:
        return False
    return True


def parse_at(text: str) -> datetime:
    """解析 `--at`，接受 `2026-10-31 22:00` / `2026-10-31T22:00` / `2026-10-31`。"""
    raw = text.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    raise SystemExit(f"--at 解析不了：{text!r}（用 2026-10-31 22:00 这种写法）")
