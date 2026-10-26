#!/usr/bin/env python
"""M4.8 金文件：把已构建页面里 `.prose` 那一段的**纯文本**抽出来，和快照比对。

为什么比对纯文本而不是 HTML：M4 只换数据源，版式一个字都不改，但换源会顺手
重排属性顺序、增删 `class`，比 HTML 会永远有噪音。纯文本相同就说明「读者看到的字
一个没变」，这正是这次迁移要保证的东西。

用法：

    python scripts/daily_golden.py --capture      # 迁移前跑一次，写快照
    python scripts/daily_golden.py --check        # 迁移后跑，diff 无输出即通过

`--check` 在有差异时打印 unified diff 并以 1 退出，方便直接塞进 CI。
"""
from __future__ import annotations

import argparse
import difflib
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "golden"

# 这些标签结束时要断行，否则「今日看点」和正文会挤成一行
BLOCK_TAGS = {
    "p",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "section",
    "div",
    "br",
    "tr",
}
SKIP_TAGS = {"script", "style"}


class ProseExtractor(HTMLParser):
    """抓出 `<div class="prose">` 到它闭合为止的可见文本。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._buffer: list[str] = []
        self._depth = 0
        self._inside = False
        self._skip = 0

    # -- 内部 ---------------------------------------------------------
    def _flush(self) -> None:
        text = "".join(self._buffer).strip()
        if text:
            self.lines.append(" ".join(text.split()))
        self._buffer.clear()

    # -- HTMLParser 钩子 ----------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._inside:
            if tag == "div":
                self._depth += 1
            if tag in SKIP_TAGS:
                self._skip += 1
            if tag in BLOCK_TAGS:
                self._flush()
            return

        classes = (dict(attrs).get("class") or "").split()
        if tag == "div" and "prose" in classes:
            self._inside = True
            self._depth = 1

    def handle_endtag(self, tag: str) -> None:
        if not self._inside:
            return
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in BLOCK_TAGS:
            self._flush()
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self._inside = False
                self._flush()

    def handle_data(self, data: str) -> None:
        if self._inside and not self._skip:
            self._buffer.append(data)


def extract(html: str) -> str:
    parser = ProseExtractor()
    parser.feed(html)
    parser.close()
    parser._flush()
    return "\n".join(parser.lines) + "\n"


def golden_path(issue_id: str) -> Path:
    return GOLDEN_DIR / f"daily-{issue_id}.txt"


def page_path(dist: Path, issue_id: str) -> Path:
    return dist / "daily" / issue_id / "index.html"


def capture(issue_id: str, dist: Path) -> Path:
    page = page_path(dist, issue_id)
    if not page.exists():
        raise SystemExit(f"找不到构建产物：{page}。先跑 `npm run build`。")
    text = extract(page.read_text(encoding="utf-8"))
    if not text.strip():
        raise SystemExit(f"{page} 里没抓到 .prose 文本，选择器可能过期了。")
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    target = golden_path(issue_id)
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def check(issue_id: str, dist: Path) -> int:
    target = golden_path(issue_id)
    if not target.exists():
        print(f"缺少快照 {target}，先跑 --capture。")
        return 1
    page = page_path(dist, issue_id)
    if not page.exists():
        print(f"找不到构建产物：{page}。先跑 `npm run build`。")
        return 1

    expected = target.read_text(encoding="utf-8").splitlines(keepends=True)
    actual = extract(page.read_text(encoding="utf-8")).splitlines(keepends=True)
    if expected == actual:
        print(f"金文件一致：/daily/{issue_id}/ 的正文纯文本与迁移前逐字相同（{len(actual)} 行）")
        return 0

    diff = difflib.unified_diff(
        expected, actual, fromfile=f"golden/{target.name}", tofile=f"dist/daily/{issue_id}/index.html"
    )
    sys.stdout.writelines(diff)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="日报正文纯文本金文件比对")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", action="store_true", help="从 dist 抓取并写入快照")
    mode.add_argument("--check", action="store_true", help="与快照比对，有差异退出 1")
    parser.add_argument("--id", default="26102322", help="期号（默认 26102322，即 M4 的基准期）")
    parser.add_argument("--dist", default=str(ROOT / "dist"), help="构建产物目录")
    args = parser.parse_args(argv)

    dist = Path(args.dist)
    if args.capture:
        saved = capture(args.id, dist)
        print(f"已写入 {saved.relative_to(ROOT)}")
        return 0
    return check(args.id, dist)


if __name__ == "__main__":
    raise SystemExit(main())
