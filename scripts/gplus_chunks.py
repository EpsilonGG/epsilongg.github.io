r"""Split a Gplus digest into writer-friendly chunk files.

The 2026-11-27 digest is 364 KB / 336 account sections — too large to hand to
one writer. This script keeps the attribution material (rules, RT clusters,
Reposts, Quotes, keyword topics) in one `global.md` and splits `## Accounts`
into fixed-size per-account chunks. Each chunk carries the full attribution
header, because the old ad-hoc compactor used to drop the Reposts section and
that is exactly how retweets got written as the scraped account's own words.

Usage:
    python scripts/gplus_chunks.py --date 2026-11-27 --per-chunk 42
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGESTS = ROOT / "out" / "gplus" / "digest"
CHUNKS = ROOT / "out" / "gplus" / "chunks"

RULES = """归属铁律（写稿必读）：
- 只写 `### group | 显示名 | @handle | brand | n=N` 下面 `- [id]` 的条目。
- 条目正文是 `@handle` 本人原创；带 `· 引用了 @xxx` 的是本人对别人推文的评论，引用正文本身属于被引用者。
- `## Reposts` / `## Quotes` 段的正文属于被转/被引用的作者，不算抓取账号原创。
- people 的 sources 只能挂该 handle 本人原创的 [id]；只有转发的账号不要写 people。
- 显示名用 `###` 行里的名字，不要在叙述里写 @handle；summary ≤60 个汉字。
"""


def split_sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in text.split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        out[title.split(" (", 1)[0]] = body.rstrip()
    return out


def account_chunks(accounts: str, per_chunk: int) -> list[list[str]]:
    chunks: list[list[str]] = [[]]
    for line in accounts.splitlines():
        if line.startswith("### ") and len(chunks[-1]) >= per_chunk:
            chunks.append([])
        chunks[-1].append(line)
    return [chunk for chunk in chunks if any(line.startswith("### ") for line in chunk)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Split a Gplus digest for chunked writing")
    ap.add_argument("--date", required=True)
    ap.add_argument("--per-chunk", type=int, default=42)
    ap.add_argument("--source", type=Path, default=None)
    ap.add_argument("--dest", type=Path, default=None)
    args = ap.parse_args(argv)

    src = args.source or DIGESTS / f"{args.date}.md"
    if not src.exists():
        print(f"missing digest: {src}", file=sys.stderr)
        return 2
    text = src.read_text(encoding="utf-8")
    sections = split_sections(text)
    required = {"RT clusters", "Reposts", "Quotes", "Keyword topics", "Accounts"}
    missing = required - set(sections)
    if missing:
        print(f"digest missing sections: {sorted(missing)}", file=sys.stderr)
        return 2

    dest = args.dest or CHUNKS / args.date
    dest.mkdir(parents=True, exist_ok=True)
    header = text.splitlines()[0]
    global_body = "\n\n".join(
        f"## {name}\n{sections[name]}"
        for name in ("RT clusters", "Reposts", "Quotes", "Keyword topics")
    )
    (dest / "global.md").write_text(f"{header}\n\n{RULES}\n{global_body}\n", encoding="utf-8", newline="\n")

    chunks = account_chunks(sections["Accounts"], args.per_chunk)
    for index, chunk in enumerate(chunks, 1):
        body = "\n".join(chunk)
        (dest / f"accounts_{index:02d}.md").write_text(
            f"{header}\n\n{RULES}\n## Accounts (originals only)\n{body}\n",
            encoding="utf-8", newline="\n",
        )
    print(f"{src.name}: {len(chunks)} account chunks + global.md -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
