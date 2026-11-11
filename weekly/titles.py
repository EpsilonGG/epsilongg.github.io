"""作品名规整：缩写 ↔ 全称、波浪号前后缀、5+ 字共同前缀系列。

设计口径（2026-11-09 用户补充）：
* 三个栏目＝大标题，品牌＝中标题，游戏名＝小标题，`- ` 之后的正文＝小条目。
* 同一个游戏必须收进同一个小标题，所以先把缩写/全称折叠成同一个 canonical。
* 三条启发式全部留证据，不静默改写：
  A. 仅 4 个日文字符的标题常是缩写 —— 登记 abbreviation_candidates；
  B. 波浪号前字符相同 —— 前缀 + 副标题分隔符视为同游戏缩写/全称，自动合并；
  C. 开头 5 字以上相同、结尾不同 —— 视为「系列」，只做相邻排序与提示，
     默认 **不自动合并**（SummerDays / SummerPockets、ToHeart / ToHeart2 就是反例）。
     要合并可在 rules.json 打开 auto_merge_long_prefix，或往 canonical_aliases 加一行。
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

# 副标题/全称分隔符：这些符号后面的部分视为同一游戏的展开，不是另一部作品。
# 故意不含 `:` `：` `・` `×` —— `マブラヴ：ディメンションズ` 是另一部作品。
SUBTITLE_SEP = frozenset("~(（―-－")
CJK_KANA = re.compile(r"^[\u3040-\u30ff\u4e00-\u9fff]+$")
WAVES = {"～": "~", "〜": "~", "‾": "~"}


def normalize(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or ""))
    for a, b in WAVES.items():
        s = s.replace(a, b)
    s = s.replace("―", "-").replace("－", "-").replace("‐", "-")
    return "".join(s.split()).casefold()


class TitleNormalizer:
    def __init__(self, titles: list[str], rules: dict):
        cfg = rules.get("title_merge") or {}
        self.long_prefix = max(2, int(cfg.get("long_prefix_chars") or 5))
        self.auto_merge_long = bool(cfg.get("auto_merge_long_prefix", False))
        self.mergeable_suffixes = [normalize(x) for x in
                                   (cfg.get("mergeable_suffixes") or []) if x]
        self.aliases = {normalize(k): normalize(v)
                        for k, v in (cfg.get("canonical_aliases") or {}).items()}
        self.no_auto_merge = {normalize(x) for x in
                              (cfg.get("no_auto_merge") or []) if x}

        self.display: dict[str, str] = {}
        for title in titles:
            n = normalize(title)
            if n and (n not in self.display or len(title) > len(self.display[n])):
                self.display[n] = title
        self.parent: dict[str, str] = {n: n for n in self.display}
        self.merge_reason: dict[str, str] = {}
        self.abbreviation_candidates: list[dict] = []
        self.family_candidates: list[dict] = []
        self._build()

    # ---- 并查集：合并时永远挂到更长的全称上 ----
    def _find(self, n: str) -> str:
        while self.parent.get(n, n) != n:
            self.parent[n] = self.parent.get(self.parent[n], self.parent[n])
            n = self.parent[n]
        return n

    def _union(self, short: str, long: str, reason: str) -> None:
        rs, rl = self._find(short), self._find(long)
        if rs == rl:
            return
        if (len(rs), rs) < (len(rl), rl):
            rs, rl = rl, rs
        self.parent[rl] = rs
        self.merge_reason.setdefault(normalize(self.display[rl]), reason)

    def _build(self) -> None:
        norms = sorted(self.display)

        # ① 人工登记的跨文字缩写（前缀规则覆盖不到）
        for short, long in self.aliases.items():
            if short in self.display and long in self.display:
                self._union(short, long, "explicit_alias")

        # ② 波浪号前字符相同 / 全称副标题：前缀 + 分隔符 → 同一游戏
        by_length = sorted(norms, key=lambda n: (len(n), n))
        for short in by_length:
            if short in self.no_auto_merge:
                continue
            for long in norms:
                if long == short or len(long) <= len(short) or not long.startswith(short):
                    continue
                suffix = long[len(short):]
                if suffix and suffix[0] in SUBTITLE_SEP:
                    self._union(short, long, "波浪号前相同/全称副标题")

        # ③ 4 字缩写：只登记候选；带分隔符的已在 ② 合并
        for short in norms:
            raw = self.display[short]
            if len(raw) != 4 or not CJK_KANA.match(raw):
                continue
            longer = [self.display[x] for x in norms
                      if x != short and x.startswith(short)]
            if not longer:
                continue
            merged = [x for x in longer if self._find(normalize(x)) == self._find(short)]
            self.abbreviation_candidates.append({
                "abbreviation": raw, "longer": sorted(longer),
                "merged": sorted(merged),
                "unmerged": sorted(set(longer) - set(merged)),
                "note": "未自动合并的可能是同系列另一部作品（版本/衍生），避免误并",
            })

        # ④ 5+ 字共同前缀 → 系列（相邻排序用）+ 可选严格前缀合并
        families: dict[str, list[str]] = defaultdict(list)
        for n in norms:
            root = self._find(n)
            families[n[:self.long_prefix]].append(root)
        for prefix, roots in sorted(families.items()):
            distinct = sorted(set(roots))
            if len(distinct) < 2:
                continue
            members = sorted(self.display[r] for r in distinct)
            self.family_candidates.append({
                "family": prefix, "titles": members,
                "merged": len(distinct) == 1,
                "note": "开头 5 字以上相同、结尾不同：同系列不同版本 / 舶来词缩写 / 单部与全集，默认只相邻排序",
            })
            if self.auto_merge_long:
                for a in distinct:
                    for b in distinct:
                        if a == b or len(b) <= len(a) or not b.startswith(a):
                            continue
                        suffix = b[len(a):]
                        if suffix in self.mergeable_suffixes:
                            self._union(a, b, "auto_merge_long_prefix")

    def canonical(self, title: str) -> str:
        n = normalize(title)
        if not n:
            return ""
        return self.display.get(self._find(n), str(title))

    def canonical_norm(self, title: str) -> str:
        return normalize(self.canonical(title))

    def aliases_of(self, canonical: str) -> list[str]:
        root = self._find(normalize(canonical))
        return sorted(self.display[n] for n in self.display
                      if n != root and self._find(n) == root)

    def family_of(self, canonical: str) -> str:
        return normalize(canonical)[:self.long_prefix]

    def rank(self, canonical: str) -> tuple:
        """同学系的小标题排在一起。"""
        return (self.family_of(canonical), normalize(canonical))

    def evidence(self) -> dict:
        merges = []
        for n, display in sorted(self.display.items()):
            root = self._find(n)
            if root != n:
                merges.append({
                    "alias": display,
                    "canonical": self.display[root],
                    "reason": self.merge_reason.get(n, "auto"),
                })
        return {
            "generator": "weekly/titles/1",
            "long_prefix_chars": self.long_prefix,
            "auto_merge_long_prefix": self.auto_merge_long,
            "canonical_aliases": self.aliases,
            "no_auto_merge": sorted(self.no_auto_merge),
            "merges": merges,
            "merged_title_count": len(merges),
            "abbreviation_candidates": self.abbreviation_candidates,
            "family_candidates": self.family_candidates,
        }
