#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""术语一致性检查。

术语表是 `data/glossary.json`：每条给出日文原词、本站统一译法（`zh`）、
以及明确不该出现的写法（`avoid`）。这个脚本只做两件事：

1. 校验表本身（字段齐、没有重复、avoid 里不能出现 zh 自己）。
2. 统计每条的 zh 与 avoid 在 `src/content/blog/*.md` 里的出现次数，
   把「avoid 出现 > 0」的条目列出来。

默认只报告、退出码 0；加 `--strict` 时只要有异形就退出 1，可接进 CI。

用法：
    python scripts/check_glossary.py
    python scripts/check_glossary.py --strict
    python scripts/check_glossary.py --term 声优     # 只看一条
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "data" / "glossary.json"
ARTICLES = sorted(glob.glob(str(ROOT / "src" / "content" / "blog" / "*.md")))


def load(path: Path) -> dict:
    with io.open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema_version") != 1:
        raise SystemExit(f"不认识的 schema_version：{data.get('schema_version')!r}")
    return data


def validate(terms: list[dict]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for index, term in enumerate(terms):
        where = f"terms[{index}]"
        for field in ("ja", "zh"):
            if not str(term.get(field, "")).strip():
                problems.append(f"{where}: 缺 {field}")
        ja = str(term.get("ja", "")).strip()
        if ja in seen:
            problems.append(f"{where}: 日文原词「{ja}」重复")
        seen.add(ja)
        zh = str(term.get("zh", "")).strip()
        for bad in term.get("avoid", []):
            if bad == zh:
                problems.append(f"{where}: avoid 里出现了 zh 自己（{zh}）")
    return problems


def count(text: str, needle: str) -> int:
    return text.count(needle) if needle else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="术语一致性检查")
    parser.add_argument("--strict", action="store_true", help="发现异形时退出码 1")
    parser.add_argument("--term", default="", help="只检查指定的一条（按 zh 或 ja 匹配）")
    args = parser.parse_args()

    data = load(GLOSSARY)
    terms = data.get("terms", [])
    problems = validate(terms)
    if problems:
        for line in problems:
            print("✗", line)
        return 1

    corpus = {}
    for path in ARTICLES:
        with io.open(path, encoding="utf-8") as handle:
            corpus[Path(path).stem] = handle.read()
    whole = "\n".join(corpus.values())

    rows = []
    hits = 0
    for term in terms:
        zh = term["zh"]
        if args.term and args.term not in (zh, term["ja"]):
            continue
        used = count(whole, zh)
        bad = [(item, count(whole, item)) for item in term.get("avoid", [])]
        bad = [(item, n) for item, n in bad if n]
        if bad:
            hits += len(bad)
        rows.append((zh, term["ja"], used, bad))

    width = max((len(row[0]) for row in rows), default=4)
    print(f"{'译法':<{width}}  {'原文':<14}{'出现':>5}  异形")
    print("-" * (width + 34))
    for zh, ja, used, bad in rows:
        mark = "  ".join(f"{item}×{n}" for item, n in bad) if bad else "—"
        print(f"{zh:<{width}}  {ja:<14}{used:>5}  {mark}")

    print()
    print(f"共 {len(terms)} 条术语，{len(ARTICLES)} 篇文章，{len(whole)} 字。")
    if hits:
        print(f"发现 {hits} 处异形写法。统一它们，或在 glossary 里把该写法记为正式译法。")
        return 1 if args.strict else 0
    print("没有发现异形写法。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
