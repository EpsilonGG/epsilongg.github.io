"""确定性排序（M2.4）。

排序键写死在这里，别在调用处另写一份：

    items    : (published_at, source, native_id)   三级，同一秒内也稳定
    accounts : roster.index(handle)                名单序，**不按当日条数**
    people   : (category.index, roster.index)      类内按名单序

**刻意不把互动数放进主排序键。** 样例数据的 `stats` 全是空的，真数据里也经常缺失；
把一个可能为空的字段放进排序键，等于让输出顺序随抓取质量漂移。
互动数只在选「哪几条值得写」时作参考，不影响输出的结构。

M1 的 `build_briefing` 按条数排序，于是同一天的账号顺序取决于当天谁话多——
这不是错误，但没有意义：同一份数据两次运行的顺序会随抓取顺序变，diff 全是噪音。
"""
from __future__ import annotations

from datetime import datetime, timezone

from .model import Item, parse_dt

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def timestamp(item: Item) -> datetime:
    """发布时间；缺失的排最前（`_EPOCH`），而不是随机位置。"""
    moment = parse_dt(item.published_at)
    if moment is None:
        return _EPOCH
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def item_sort_key(item: Item) -> tuple:
    return (timestamp(item), item.source, item.native_id)


def sort_items(items) -> list[Item]:
    return sorted(items, key=item_sort_key)


def sort_accounts(handles, roster=None) -> list[str]:
    """按名单序；名单里没有的排最后，彼此按字母序（仍然确定）。"""
    unique = sorted({h for h in handles if h})
    if roster is None:
        return unique
    return sorted(unique, key=lambda h: (roster.index_of(h), h))


def sort_people(people, roster=None) -> list[dict]:
    """`people` 是 `[{handle, ...}]`，类内按名单序。"""
    rows = list(people)
    if roster is None:
        return sorted(rows, key=lambda r: r.get("handle") or "")
    return sorted(rows, key=lambda r: (roster.index_of(r.get("handle") or ""), r.get("handle") or ""))
