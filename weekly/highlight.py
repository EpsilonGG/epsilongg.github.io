"""本期「当前亮点」归纳（≤70 字）与窗口短标签。

2026-11-11 用户裁决：周报开头（新作栏目之前）要一句亮点归纳，归档页第三行
也用同一句。这句话**必须可复现**——发布链上没有模型，同一份正文重跑必须
得到同一句话，否则每期都「看起来不一样」却说不清为什么。

所以这里全是确定性规则：

1. 取第一栏（有「新作」就是「新作」）里条目最多的两个游戏组；
2. 每个组取第一条小条目，剥掉开头的『作品名』，剩下的就是「发生了什么」；
3. 前面挂品牌名（品牌名短，比动辄 30 字的长作品名更适合当主语）；
4. 拼起来超过 70 字就依次降级：先砍第二条、再砍句长、最后退成统计口径。

为什么用品牌而不是作品名：`『SummerPocketsSunnysideStories』` 一个名字就
吃掉一半预算，而 `SMEE`、`Key` 读起来一样清楚。
"""
from __future__ import annotations

import re

LIMIT = 70

# 行内链接 / 加粗 → 纯文字（正文里 `[@handle](url)` 这类不能带进摘要）
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")

# 『作品名』/「作品名」——摘要里一律剥掉，主语用品牌名
_TITLE = re.compile(r"『[^』]{0,60}』|「[^」]{0,60}」")

_LEAD_PUNCT = re.compile(r"^[\s，、。；：:,.!?！？\-—]+")


def window_label(start: str, end: str) -> str:
    """`2026-11-04` + `2026-11-10` → `26-1104 – 26-1110`（用户指定格式）。"""

    def one(day: str) -> str:
        year, month, dd = str(day).split("-")
        return f"{year[2:]}-{month}{dd}"

    return f"{one(start)} – {one(end)}"


def _plain(text: str) -> str:
    return _BOLD.sub(r"\1", _LINK.sub(r"\1", text)).strip()


def _sections(md: str) -> list[dict]:
    """按 `## 栏目 / ### 品牌 / #### 游戏 / - 条目` 切一层结构。"""
    cols: list[dict] = []
    cur: dict | None = None
    brand = ""
    game: dict | None = None
    for line in md.splitlines():
        if line.startswith("## "):
            cur = {"label": line[3:].strip(), "items": 0, "games": []}
            cols.append(cur)
            brand, game = "", None
        elif cur is None:
            continue
        elif line.startswith("### "):
            brand, game = _plain(line[4:]), None
        elif line.startswith("#### "):
            game = {"brand": brand, "name": _plain(line[5:]), "bullets": []}
            cur["games"].append(game)
        elif line.startswith("- ") and not line.startswith("- （"):
            cur["items"] += 1
            if game is not None:
                game["bullets"].append(_plain(line[2:]))
    return cols


def _clause(bullet: str) -> str:
    """`『ワンナイトアフター』定档 11/27，官网放出体验版` → `定档 11/27，官网放出体验版`"""
    text = _LEAD_PUNCT.sub("", _TITLE.sub("", bullet))
    return re.sub(r"\s+", " ", text).strip()


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("，", "；", "、", "。", " "):
        pos = cut.rfind(sep)
        if pos >= limit // 2:
            return cut[:pos]
    return cut.rstrip() + "…"


def _ranked(games: list[dict]) -> list[dict]:
    """按条目数排序；同名游戏只留条目最多的那一组（跨品牌重复报道很常见）。"""
    best: dict[str, dict] = {}
    for order, game in enumerate(games):
        key = re.sub(r"[\s\-–—―~〜・·:：]", "", game["name"])
        if not key:
            continue
        held = best.get(key)
        if held is None:
            best[key] = {**game, "_order": order}
        elif len(game["bullets"]) > len(held["bullets"]):
            best[key] = {**game, "_order": held["_order"]}
    return sorted(best.values(), key=lambda g: (-len(g["bullets"]), g["_order"]))


def _fallback(stats: dict, order: list[str]) -> str:
    return (f"本期 {stats['brands']} 个品牌 {stats['items']} 条动态，"
            f"按「{' / '.join(order)}」整理。")


def build(md: str, stats: dict, order: list[str]) -> str:
    """从对外正文算出本期亮点句，长度保证 ≤70 字。"""
    if not order:
        return _fallback(stats, order)
    by_label = {c["label"]: c for c in _sections(md)}
    column = by_label.get(order[0])
    if column is None:
        return _fallback(stats, order)

    picks: list[tuple[str, str]] = []
    for game in _ranked(column["games"]):
        if not game["bullets"]:
            continue
        clause = _clause(game["bullets"][0])
        if not clause:
            continue
        picks.append((game["brand"], clause))
        if len(picks) >= 3:
            break

    if picks:
        head = f"{column['label']} {column['items']} 条"
        for clause_budget in (24, 18, 12):
            parts = [(f"{brand} {_trim(clause, clause_budget)}").strip()
                     for brand, clause in picks[:2]]
            text = head + "：" + "；".join(parts) + "。"
            if len(text) <= LIMIT:
                return text
        brand, clause = picks[0]
        text = head + "：" + _trim(clause, 40) + "。"
        if len(text) <= LIMIT:
            return text

    return _fallback(stats, order)


def build_toc(md: str) -> list[dict]:
    """只给大标题（栏目）做定位，品牌与游戏不进目录。"""
    toc: list[dict] = []
    for line in md.splitlines():
        if line.startswith("## "):
            toc.append({"id": f"section-{len(toc) + 1}", "label": line[3:].strip()})
    return toc
