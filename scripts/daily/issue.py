"""期号规则。

期号 = **被覆盖的那一天 + 哪一版**：`YYMMDD`（JST）。2026-10-29 起日报一天出两份，
所以期号多了一个类型后缀：

    261029      声优版（声优 + 音声社团）
    261029-g    Galgame 版（游戏制造商 + 信息号）
    261029-2    同一天的第二期声优版
    261029-g2   同一天的第二个 Galgame 版

不带后缀的永远是声优版，因为 10-29 之前的所有期号都是声优版——旧档不用迁移，
`261025` 照旧读得出来，`kind_of()` 给 `voice`。

为什么不再带小时（旧格式是 `YYMMDDHH`）：一天的数据要到 JST 24:00 才闭合
（X-Reader 的 CI 每天 15:00 UTC 抓最后一次），真实出稿必然落在次日凌晨。
把小时写进期号只有两条路，两条都不对：

* 写真实时间 → 次日 01 点，期号比内容晚一天，归档会把 10-27 的日报排到 10-28 下面；
* 钉一个假时间 → 旧格式就是这么做的（固定 22:00），于是页面上的「发布于 22:00」
  比实际早约 3.5 小时。

所以期号只说「这是哪一天、哪一版」，发布时间另有字段（`issue.published_at`），
那个是真的。同一天出第二期是例外，用 `-2` / `-g2` 表示，仍然不引入「小时」这个维度。
"""
from __future__ import annotations

import re
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

# 日报内容是日本声优的一天，用 JST 才不会把深夜的推分错天
JST = timezone(timedelta(hours=9))

VOICE = "voice"
GALGAME = "galgame"
KINDS = (VOICE, GALGAME)

# 类型后缀 → 页面上的名字。标题、按钮、归档都用这一份，别在别处再写一遍。
KIND_LABEL = {VOICE: "声优", GALGAME: "Galgame"}

# `261029` / `261029-2` / `261029-g` / `261029-g2`。用 `-` 而不是直接接数字：
# `2610292` 分不清是「10-29 第 2 期」还是「10-29 02 时」（旧格式的读法）。
# 序号限 2 位（2–99）：一天出到第 100 期不存在，限住才能和
# `schemas/report.schema.json` / `content.config.ts` 的正则保持同一套接受集
# （`tests/test_daily_schema_limits.py` 盯着这三处）。
ID_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})(?:-(g?)(\d{0,2}))?$")


def issue_id_for(day: date_cls, seq: int = 1, kind: str = VOICE) -> str:
    """`2026-10-29` + 声优第 1 期 → `261029`；Galgame 第 1 期 → `261029-g`。"""
    if kind not in KINDS:
        raise ValueError(f"期号类型只能是 {'/'.join(KINDS)}，收到 {kind!r}")
    if seq < 1:
        raise ValueError(f"期序号从 1 开始，收到 {seq}")
    base = day.strftime("%y%m%d")
    if kind == GALGAME:
        return f"{base}-g{seq if seq > 1 else ''}"
    return base if seq == 1 else f"{base}-{seq}"


def parse_issue_id(text: str) -> tuple[date_cls, str, int]:
    """`261029-g2` → `(date(2026,10,29), "galgame", 2)`。格式不对就抛 ValueError。"""
    raw = text.strip()
    match = ID_RE.match(raw)
    if not match:
        raise ValueError(f"期号 {raw!r} 不是 YYMMDD / YYMMDD-N / YYMMDD-g / YYMMDD-gN")
    year, month, day = (int(match.group(i)) for i in (1, 2, 3))

    kind = GALGAME if match.group(4) == "g" else VOICE
    digits = match.group(5) or ""
    if match.group(4) is None:
        seq = 1
    elif digits == "":
        if match.group(4) == "":
            raise ValueError(f"期号 {raw!r} 的 `-` 后面是空的")
        seq = 1  # `-g` = Galgame 第 1 期
    else:
        seq = int(digits)
        if seq < 2:
            raise ValueError(f"期号 {raw!r} 的序号要从 2 起（第 1 期不写后缀）")

    try:
        covered = date_cls(2000 + year, month, day)
    except ValueError:
        raise ValueError(f"期号 {raw!r} 里没有这一天（{2000 + year}-{month:02d}-{day:02d}）") from None
    return covered, kind, seq


def day_of(issue_id: str) -> date_cls:
    """期号覆盖的那一天。"""
    return parse_issue_id(issue_id)[0]


def kind_of(issue_id: str) -> str:
    """`261029` → `voice`；`261029-g` → `galgame`。"""
    return parse_issue_id(issue_id)[1]


def seq_of(issue_id: str) -> int:
    """同一天同一版里的第几期（第 1 期是 1）。"""
    return parse_issue_id(issue_id)[2]


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
