"""按 JST 自然日切时间窗（M2.1）。

**为什么必须自己切**：X-Reader 给的时间戳是 UTC，旧脚本直接 `dt.date()` 分天，
于是「一天」实际是 JST 09:00 → 次日 08:59，边界整体偏了 9 小时：

  * 10-23 凌晨 00:10–07:53 JST 发的推，时间戳是 10-22 15:10–22:53 UTC → 被算进 10-22；
  * 10-24 凌晨 00:19–05:09 JST 发的推，时间戳是 10-23 16:19–20:09 UTC → 被算进 10-23。

日报写的是日本声优的一天，边界必须落在 JST 00:00。实测样例数据 10-23 窗口：
UTC 分天 26 条、JST 分天 28 条，账号集合相同、条目集合差 8 条。

窗口是**半开区间** `[当天 00:00, 次日 00:00)`：跨零点的推只属于一天，不会两头都算。

## 精度不足的条目

`precision: day` 的条目只知道「哪一天」，不知道几点。这类条目**不参与**窗口判定，
单独放进 `Selection.unsure`——由调用方决定是丢弃、标注还是人工确认。
判定规则：只认「日期 = 窗口当天」与「日期 = 窗口前一天」两种。
理由：来源要么按 UTC 要么按 JST 写日期，UTC 写的 D 日最晚能落到 JST 的 D+1 日
00:00–08:59，所以只有 D-1、D 能进入 D 日的窗口，D+1 不可能。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from .issue import JST
from .model import Item

# 精度只到「日」的条目无法判定落在哪个自然日窗口里
IMPRECISE = frozenset({"day"})


def _aware(moment: datetime, tz: timezone) -> datetime:
    """没带时区的时间戳当 JST 处理（脚本自己写的都带时区，这条只是兜底）。"""
    return moment if moment.tzinfo else moment.replace(tzinfo=tz)


@dataclass(frozen=True)
class IssueWindow:
    """一个 JST 自然日 `[start, end)`。"""

    day: date
    tz: timezone = JST

    def __post_init__(self) -> None:
        if isinstance(self.day, datetime) or not isinstance(self.day, date):
            raise TypeError(f"IssueWindow.day 要 date，收到 {type(self.day).__name__}")

    # -- 构造 ----------------------------------------------------------
    @classmethod
    def for_day(cls, day: date, tz: timezone = JST) -> "IssueWindow":
        return cls(day=day, tz=tz)

    @classmethod
    def containing(cls, moment: datetime, tz: timezone = JST) -> "IssueWindow":
        """某个时刻落在哪个窗口（按该时刻换算到 `tz` 后的自然日）。"""
        return cls(day=_aware(moment, tz).astimezone(tz).date(), tz=tz)

    # -- 边界 ----------------------------------------------------------
    @property
    def start(self) -> datetime:
        return datetime.combine(self.day, time(0, 0), tzinfo=self.tz)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(days=1)

    @property
    def label(self) -> str:
        return f"{self.day.isoformat()}（JST）"

    # -- 判定 ----------------------------------------------------------
    def contains(self, moment: datetime) -> bool:
        return self.start <= _aware(moment, self.tz) < self.end

    def select(self, items) -> "Selection":
        exact: list[Item] = []
        unsure: list[Item] = []
        undated: list[Item] = []
        for item in items:
            moment = item.published_dt()
            if moment is None:
                undated.append(item)
                continue
            moment = _aware(moment, self.tz)
            if item.precision in IMPRECISE:
                stated = moment.date()
                if self.day - timedelta(days=1) <= stated <= self.day:
                    unsure.append(item)
                continue
            if self.contains(moment):
                exact.append(item)
        return Selection(self, tuple(exact), tuple(unsure), tuple(undated))


@dataclass(frozen=True)
class Selection:
    """一次窗口切分的结果。四个桶互不重叠，加起来就是全部输入。"""

    window: IssueWindow
    items: tuple[Item, ...] = ()
    unsure: tuple[Item, ...] = ()
    undated: tuple[Item, ...] = ()

    @property
    def all_items(self) -> tuple[Item, ...]:
        """确定在窗内 + 精度不足但可能在窗内。生成日报时用这个，别丢数据。"""
        return self.items + self.unsure

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)
