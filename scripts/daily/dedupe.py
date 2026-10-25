"""跨源去重（M2.2）。

同一条内容可能被多个账号各转一次——X-Reader 会给**每个账号各写一条记录**，
`item_id` 相同、`publisher` 不同。也可能同一条内容同时出现在两个数据源里。
这一步的任务是：**同一条内容只留一条**，把「谁传播过它」收进 `amplifiers`。

身份键按优先级取第一个可用的：

1. `source + native_id` —— 最强。同一条推就是同一个 `native_id`。
2. 归一化后的 `canonical_url` —— 给没有稳定 id 的数据源兜底。
3. `sha256(正文)` —— 最后一道，只用于无 id 无 url 的情况。

前两条命中时**不丢数据**：重复项不参与输出，但它的账号进 `amplifiers`。
§1 问题②那条推文去重后是「1 条内容、2 个传播者」，不是「2 条内容、0 个互动」。

## `amplifiers` 的语义

**所有出现过这条内容的账号，含作者本人。** 一条普通原创推去重后是
`amplifiers == [作者]`（长度 1）；被两个人各转一次的那条长度 2。
长度 ≥ 2 就是一条可写的互动线索——不用再单独判断「谁转了谁」。
"""
from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit

from .model import Item, content_hash

# 同一条内容有多种形态时，优先留「更原始」的那条：
# 原创 > 引用 > 回复 > 纯转发。否则日报会把一次转发写成作者的发言。
_KIND_RANK = {"post": 0, "quote": 1, "reply": 2, "repost": 3}


def normalize_url(url: str) -> str:
    """去掉协议、`www.`、查询串、锚点与末尾斜杠，主机名小写。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw if "//" in raw else "//" + raw)
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parts.path or "").rstrip("/")
    return f"{host}{path}" if host else ""


def identity(item: Item) -> str:
    """一条内容的身份键。同键即同一条内容。"""
    if item.source and item.native_id:
        return f"{item.source}:{item.native_id}"
    url = normalize_url(item.url)
    if url:
        return f"url:{url}"
    return "text:" + (item.content_hash or content_hash(item.text))


def _canonical_rank(item: Item) -> tuple:
    return (
        _KIND_RANK.get(item.kind, 9),
        item.published_at or "",
        item.account,
    )


def group(items) -> dict[str, list[Item]]:
    """按身份键分组，保持首次出现的顺序（dict 保序，Python 3.7+）。"""
    out: dict[str, list[Item]] = {}
    for item in items:
        out.setdefault(identity(item), []).append(item)
    return out


def merge(items) -> list[Item]:
    """把同一条内容的多条记录并成一条。返回顺序 = 首次出现顺序。"""
    merged: list[Item] = []
    for recs in group(items).values():
        best = min(recs, key=_canonical_rank)
        involved: list[str] = []
        for rec in recs:
            involved.extend(rec.amplifiers or [rec.account])
        amplifiers = sorted({a for a in involved if a})
        if list(best.amplifiers) != amplifiers:
            best = replace(best, amplifiers=amplifiers)
        merged.append(best)
    return merged


def duplicates(items) -> dict[str, list[Item]]:
    """只看有重复的组，调试与报告用。"""
    return {key: recs for key, recs in group(items).items() if len(recs) > 1}
