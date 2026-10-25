"""导出「待生成数据」（M2.6）。

产物是 `out/<期号>/generate.json`，给 M3 出题用。**不含一句人写的总结**——
这一步只把结构摆好：按分类分组、互动候选、每条的低价值标记。

为什么按分类分组：M3 的出题是「一个分类一份 prompt」。分类不是页面的分类，
是**模型的上下文窗口**——把 40 个人的一天塞进一次请求，模型只会写出 40 句废话。

为什么互动只抽结构：写成句子是 M3 的事。这里只给「谁 → 谁、哪条推」，
模型才有机会写出「A 转发了 B 的说明」而不是「两人互相扩散」（§1 问题②）。

**只在名单内建边。** 名单外的人可能出现在正文里（@ 了别人），但那是外部互动，
写进日报会引出一个日报里没有的人，读者点不到、也搜不到。
"""
from __future__ import annotations

import re

from .incremental import Classification
from .model import Item
from .roster import Roster

_URL_RE = re.compile(r"https?://\S+")
_MENTION_RE = re.compile(r"@([A-Za-z0-9_]{2,20})")

MIN_TEXT = 10


def low_value_reason(item: Item) -> str:
    """低价值不是「不重要」，是「撑不起一句话」。空串表示没意见。"""
    text = _URL_RE.sub("", item.text or "").strip()
    if not text:
        return "只有链接或空正文"
    if len(text) < MIN_TEXT:
        return "正文过短"
    if item.kind == "reply" and len(text) < MIN_TEXT * 2:
        return "回复且过短"
    return ""


def _item_row(item: Item, roster: Roster) -> dict:
    reason = low_value_reason(item)
    return {
        "key": item.key,
        "account": item.account,
        "category": roster.category_of(item.account),
        "published_at": item.published_at,
        "kind": item.kind,
        "text": item.text,
        "url": item.url,
        "amplifiers": list(item.amplifiers),
        "low_value": bool(reason),
        "low_value_reason": reason,
    }


def interactions(items, roster: Roster) -> list[dict]:
    """互动候选：传播（同一内容多人出现）与提及（正文 @ 到名单内的人）。"""
    edges: dict[tuple, dict] = {}
    for item in items:
        people = [a for a in (item.amplifiers or [item.account]) if roster.is_known(a)]
        for src in people:
            for dst in people:
                if src != dst:
                    edges.setdefault(
                        ("amplify", src, dst, item.key),
                        {"kind": "amplify", "from": src, "to": dst, "item": item.key},
                    )
        for handle in _MENTION_RE.findall(item.text or ""):
            if handle != item.account and roster.is_known(handle):
                edges.setdefault(
                    ("mention", item.account, handle, item.key),
                    {"kind": "mention", "from": item.account, "to": handle, "item": item.key},
                )
    return [edges[k] for k in sorted(edges)]


def build(
    issue_id: str,
    classification: Classification,
    merged: list[Item],
    roster: Roster,
    published_at: str = "",
) -> dict:
    """组装 `generate.json`。`merged` 是已去重、已排序的条目。"""
    by_category: dict[str, list[Item]] = {}
    for item in merged:
        by_category.setdefault(roster.category_of(item.account), []).append(item)

    categories = []
    for cat in roster.categories:
        rows = by_category.get(cat["id"]) or []
        if not rows:
            continue
        categories.append(
            {
                "id": cat["id"],
                "label": roster.label_of(cat["id"]),
                "handles": sorted({i.account for i in rows}, key=roster.index_of),
                "items": [_item_row(i, roster) for i in rows],
            }
        )

    accounts = {i.account for i in merged}
    counts = classification.counts(accounts=len(accounts))
    # `items` 报**去重后**的条数：读者看到的条目数就是它，不是原始记录数。
    # `accounts` 只数「拥有条目的人」：纯转发的人不进 people 表（没有属于他的条目），
    # 但会出现在 interactions 里——「谁帮着扩散」照样写得出来，不会被当成独立发言。
    counts["items"] = len(merged)
    return {
        "schema_version": 1,
        "issue": {
            "id": issue_id,
            "published_at": published_at,
            "window": {
                "start": classification.window.start.isoformat(),
                "end": classification.window.end.isoformat(),
            },
        },
        "counts": counts,
        "categories": categories,
        "interactions": interactions(merged, roster),
        "low_value": [i.key for i in merged if low_value_reason(i)],
        "late": [i.key for i in classification.late],
        "future": [i.key for i in classification.future],
        "unknown": roster.unknown(accounts),
    }
