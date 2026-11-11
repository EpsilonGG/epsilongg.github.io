"""书名号归一：游戏/视频作品用『』，角色用「」，乐曲与书籍用《》。

三类各有判据，顺序固定，先命中先生效：

1. 角色 → 「」：命中 `rules.brackets.characters` 名单（人工维护，宁缺勿滥）。
2. 乐曲 / 书籍 → 《》：命中 `rules.brackets.songs` / `books` 名单。
3. 作品 → 『』：归一名在语料 `titles` 里（`corpus.json:titles`，由日报正本
   与分句索引里的全部 `『』/《》` 抽取，不手工维护）。

三条都不命中的括注**原样保留**——它是引语、节目名、界面文案（「恢复」「前缀：」），
不是书名号误用，不该被机械改写。命中但括号已经正确的也不动，保证幂等。
"""
from __future__ import annotations

import re

# 三种书名号，逐个成对匹配；跨括号的嵌套（『A「B」』）按最内层先处理。
SPAN_RE = re.compile(r"[『《「]([^』》」]{1,80})[』》」]")

WORK, CHARACTER, MEDIA = "『", "「", "《"
CLOSERS = {"『": "』", "「": "」", "《": "》"}


def _norm(text: str) -> str:
    return "".join(str(text or "").split()).strip("『』《》「」 　")


def _target(name: str, works: set[str], songs: set[str],
            books: set[str], characters: set[str]) -> str:
    if name in characters:
        return CHARACTER
    if name in songs or name in books:
        return MEDIA
    if name in works:
        return WORK
    return ""


def normalize(text: str, titles: set[str], cfg: dict | None = None) -> tuple[str, list[dict]]:
    """把 `text` 里的书名号按三类判据改写，返回（新文本, 改动明细）。"""
    cfg = cfg or {}
    works = {_norm(x) for x in (titles or ()) if str(x).strip()}
    songs = {_norm(x) for x in (cfg.get("songs") or []) if str(x).strip()}
    books = {_norm(x) for x in (cfg.get("books") or []) if str(x).strip()}
    characters = {_norm(x) for x in (cfg.get("characters") or []) if str(x).strip()}
    changes: list[dict] = []

    def repl(match: re.Match) -> str:
        opener, inner = match.group(0)[0], match.group(1)
        name = _norm(inner)
        want = _target(name, works, songs, books, characters)
        if not want or want == opener:
            return match.group(0)
        changes.append({"from": match.group(0), "to": want + inner + CLOSERS[want],
                        "kind": {WORK: "work", CHARACTER: "character", MEDIA: "media"}[want]})
        return want + inner + CLOSERS[want]

    return SPAN_RE.sub(repl, str(text or "")), changes
