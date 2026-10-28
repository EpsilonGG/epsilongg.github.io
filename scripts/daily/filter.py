"""按账号的降噪规则筛条目（M2.7）。

日报里有两种账号天然刷屏：

* **情报站**（Moepedia）—— 一天几十条，大多是转发抽奖、店铺特典、周年回顾；
* **大厂官号** —— 新作公告之外还有大量活动预告与客服式回复。

这些条目不是「不重要」，是**重复**或**没有信息**：同一场抽奖隔三天再发一遍，
同一批「○年前的本日发售」在三分钟里连发十条。让它们进 `generate.json` 的代价
不是页面变长（页面每人只有一句话），而是模型要在两百条里挑四十句——挑出来的
平均质量必然下降，而且很容易挑中「抽奖还剩两天」这种最像新闻的废话。

## 为什么在抓取后

抓取侧（X-Reader）拿到的是 Nitter 的时间线，没有「只要公告」这种服务端过滤；
而 `data/items/x.jsonl` 是**只追加的原始库**，一旦在抓取时丢掉就再也拿不回来。
规则写在展示侧，意味着改一条正则、重跑一次 `daily build` 就能重出历史任何一期，
不用重新抓。规则存在名单里（`daily-roster.json` 的 `filter` 段）而不是代码里：
谁该降噪是编辑决定，改 JSON 不用改脚本。

## 四条规则，按顺序判

1. `drop_kinds` —— 整类丢掉。`repost` 最常用：转发的内容原作者那条也在，
   而 Nitter 的 RSS 路由给不出「转的是谁」，留着只会把别人的话记在这个号名下。
2. `drop_if` —— 正文命中任一正则就丢。用于抽奖、促销、周年回顾这类固定句式。
3. `prefer_if` —— 命中任一正则的**排前面**，封顶时优先保它们。注意这是排序，
   不是必要条件：写成必要条件会漏掉「只写了作品名和链接」的真公告。
4. `max_items` —— 一期最多留几条，按 `prefer_if` 命中 → 发布时间倒序取。

`drop_if` 先于一切：一条「新作发售，转发抽奖」两个都命中，应该丢——
抽奖部分是这条里唯一会过期的东西。

## 匹配用的正文

先去掉 URL 再匹配：链接里常带 `sale`、`campaign` 这类词，拿它当证据会误伤。
`text` 里的换行折成空格，正则不用考虑排版。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .model import Item

_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")

# 丢掉的条目在 generate.json 里留一条记录，正文只留开头这么多字：
# 够看出「丢的是哪条」，又不至于让 generate.json 变成第二份原始库。
PREVIEW = 80


@dataclass(frozen=True)
class Rule:
    """一个账号的降噪规则。全部为空等于没规则（不会被 `apply_rules` 用到）。"""

    handle: str = ""
    drop_kinds: frozenset[str] = frozenset()
    drop_if: tuple[re.Pattern, ...] = ()
    prefer_if: tuple[re.Pattern, ...] = ()
    max_items: int | None = None

    @property
    def empty(self) -> bool:
        return not (self.drop_kinds or self.drop_if or self.prefer_if or self.max_items)


def _compile(handle: str, patterns: Iterable[str]) -> tuple[re.Pattern, ...]:
    out: list[re.Pattern] = []
    for raw in patterns or ():
        try:
            # 大小写不敏感：名单里写 `PR` 也能命中正文的 `pr`。
            out.append(re.compile(str(raw), re.IGNORECASE))
        except re.error as exc:
            raise ValueError(f"{handle} 的 filter 里有非法正则 {raw!r}：{exc}") from exc
    return tuple(out)


def parse_rule(handle: str, data: dict) -> Rule:
    """把名单里的 `filter` 段变成规则。非法正则在**构建时**就报错，不留到线上。"""
    kinds = data.get("drop_kinds") or ()
    if isinstance(kinds, str):  # 写成一个字符串时不要按字符拆
        kinds = [kinds]
    limit = data.get("max_items")
    return Rule(
        handle=handle,
        drop_kinds=frozenset(str(k).strip().lower() for k in kinds if str(k).strip()),
        drop_if=_compile(handle, data.get("drop_if") or ()),
        prefer_if=_compile(handle, data.get("prefer_if") or ()),
        max_items=int(limit) if limit else None,
    )


def plain_text(item: Item) -> str:
    """去掉 URL、折平换行。正则只对着这个串跑。"""
    return _WS_RE.sub(" ", _URL_RE.sub(" ", item.text or "")).strip()


def drop_reason(item: Item, rule: Rule) -> str:
    """这一条该不该丢。空串表示留下。"""
    if item.kind.lower() in rule.drop_kinds:
        return f"{item.kind}"
    text = plain_text(item)
    for pattern in rule.drop_if:
        if pattern.search(text):
            return f"命中「{pattern.pattern}」"
    return ""


def _row(item: Item, reason: str) -> dict:
    return {
        "key": item.key,
        "account": item.account,
        "reason": reason,
        "text": plain_text(item)[:PREVIEW],
    }


def _rank(item: Item, rule: Rule) -> tuple:
    """封顶时的取舍顺序：命中 `prefer_if` 的先留，同档里后发的先留。

    为什么「后发」优先：同一天里改期、延期的公告才是定稿，先发的那条已经过期。
    """
    if rule.prefer_if:
        text = plain_text(item)
        preferred = 1 if any(p.search(text) for p in rule.prefer_if) else 0
    else:
        preferred = 0
    return (preferred, item.published_at or "", item.key)


def _cap(kept: list[Item], rules: dict[str, Rule]) -> tuple[list[Item], list[dict]]:
    """每期每号封顶。"""
    grouped: dict[str, list[int]] = {}
    for i, item in enumerate(kept):
        rule = rules.get((item.account or "").lower())
        if rule and rule.max_items:
            grouped.setdefault(item.account.lower(), []).append(i)

    drop: dict[int, str] = {}
    for handle, idx in grouped.items():
        limit = rules[handle].max_items or 0
        if len(idx) <= limit:
            continue
        rule = rules[handle]
        ranked = sorted(idx, key=lambda i: _rank(kept[i], rule), reverse=True)
        for i in ranked[limit:]:
            drop[i] = f"超过 {limit} 条上限"
    if not drop:
        return kept, []
    survivors = [item for i, item in enumerate(kept) if i not in drop]
    removed = [_row(kept[i], drop[i]) for i in sorted(drop)]
    return survivors, removed


def apply_rules(items: list[Item], filters: dict[str, dict] | None) -> tuple[list[Item], list[dict]]:
    """按名单里的 `filter` 段筛一遍。返回（留下的，丢掉的）。

    `filters` 是 `{handle: 原始 dict}`，键大小写不敏感。
    """
    rules = {
        str(handle).lower(): parse_rule(str(handle), data)
        for handle, data in (filters or {}).items()
        if isinstance(data, dict)
    }
    rules = {h: r for h, r in rules.items() if not r.empty}
    if not rules:
        return list(items), []

    kept: list[Item] = []
    dropped: list[dict] = []
    for item in items:
        rule = rules.get((item.account or "").lower())
        reason = drop_reason(item, rule) if rule else ""
        if reason:
            dropped.append(_row(item, reason))
        else:
            kept.append(item)

    kept, capped = _cap(kept, rules)
    dropped.extend(capped)
    return kept, dropped
