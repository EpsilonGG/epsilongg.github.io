#!/usr/bin/env python
"""M4.8 金文件：把已构建页面里 `.prose` 那一段的**纯文本**抽出来，和快照比对。

为什么比对纯文本而不是 HTML：M4 只换数据源，版式一个字都不改，但换源会顺手
重排属性顺序、增删 `class`，比 HTML 会永远有噪音。纯文本相同就说明「读者看到的字
一个没变」，这正是这次迁移要保证的东西。

**基准期是可换的**，不写死在代码里：`tests/golden/current.json` 只有一个字段
`{"id": "261025"}`，`--check` 读它决定比哪一期。换基准是一条命令：

    python scripts/daily_golden.py --switch              # 换成 data/daily 里最新的一期
    python scripts/daily_golden.py --switch --id 261025

`--switch` 做两件事：从 `dist` 重新抓一份快照、把 `current.json` 指过去。
旧快照**保留不删**——切回去是免费的，删了就得重新 build 才能抓。

用法：

    python scripts/daily_golden.py --capture      # 只写快照，不动指针
    python scripts/daily_golden.py --check        # 按 current.json 比对
    python scripts/daily_golden.py --switch       # 换基准（重抓 + 改指针）
    python scripts/daily_golden.py --check --id 261023   # 临时比另一期

`--check` 在有差异时打印 unified diff 并以 1 退出，方便直接塞进 CI。
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "golden"
POINTER = GOLDEN_DIR / "current.json"
DATA = ROOT / "data" / "daily"

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


def newest_issue() -> str:
    """`data/daily/` 里期号最大的一期。期号是 `YYMMDD`（同日第二期 `-2`），字典序即时间序。"""
    ids = sorted(p.parent.name for p in DATA.glob("*/report.json"))
    if not ids:
        raise SystemExit(f"{DATA} 里没有已发布的期号，无法自动选基准。用 --id 指定。")
    return ids[-1]


def current_issue() -> str:
    if not POINTER.exists():
        raise SystemExit(
            f"缺少 {POINTER.relative_to(ROOT)}（金文件基准指针）。"
            "先跑 `python scripts/daily_golden.py --switch`。"
        )
    try:
        data = json.loads(POINTER.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{POINTER.relative_to(ROOT)} 不是合法 JSON：{exc}") from None
    issue_id = str(data.get("id") or "").strip()
    if not issue_id:
        raise SystemExit(f"{POINTER.relative_to(ROOT)} 里没有 id 字段。")
    return issue_id


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


def point_at(issue_id: str) -> dict:
    """把指针挪到 `issue_id`。快照内容没变时保留原来的 `captured_at`，免得白改一次 git。"""
    previous: dict = {}
    if POINTER.exists():
        try:
            previous = json.loads(POINTER.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}

    same_id = str(previous.get("id") or "") == issue_id
    stamp = (
        previous.get("captured_at")
        if same_id and previous.get("captured_at")
        else datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    payload = {
        "id": issue_id,
        "captured_at": stamp,
        "note": "金文件基准期。`daily_golden.py --check` 比这一期；换基准用 `--switch`。",
    }
    POINTER.parent.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def check(issue_id: str | None, dist: Path) -> int:
    issue_id = issue_id or current_issue()
    target = golden_path(issue_id)
    if not target.exists():
        print(f"缺少快照 {target.relative_to(ROOT)}，先跑 --capture / --switch。")
        return 1
    page = page_path(dist, issue_id)
    if not page.exists():
        print(f"找不到构建产物：{page}。先跑 `npm run build`。")
        return 1

    expected = target.read_text(encoding="utf-8").splitlines(keepends=True)
    actual = extract(page.read_text(encoding="utf-8")).splitlines(keepends=True)
    if expected == actual:
        print(f"金文件一致：/daily/{issue_id}/ 的正文纯文本与基准逐字相同（{len(actual)} 行）")
        return 0

    diff = difflib.unified_diff(
        expected, actual, fromfile=f"golden/{target.name}", tofile=f"dist/daily/{issue_id}/index.html"
    )
    sys.stdout.writelines(diff)
    return 1


def switch(issue_id: str | None, dist: Path) -> int:
    issue_id = issue_id or newest_issue()
    target = capture(issue_id, dist)
    payload = point_at(issue_id)
    print(f"基准期已切到 {issue_id}：{target.relative_to(ROOT)}（{len(target.read_text(encoding='utf-8').splitlines())} 行）")
    print(f"指针：{POINTER.relative_to(ROOT)} → {payload['id']}（{payload['captured_at']}）")
    others = sorted(p.stem.removeprefix("daily-") for p in GOLDEN_DIR.glob("daily-*.txt"))
    others = [o for o in others if o != issue_id]
    if others:
        print(f"其它快照仍在，check 不看它们：{'、'.join(others)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="日报正文纯文本金文件比对")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", action="store_true", help="从 dist 抓取并写入快照（不动指针）")
    mode.add_argument("--check", action="store_true", help="与快照比对，有差异退出 1")
    mode.add_argument("--switch", action="store_true", help="换基准期：重抓快照 + 改 current.json")
    parser.add_argument("--id", default=None, help="期号（默认：--check 读 current.json，--switch 取最新一期）")
    parser.add_argument("--dist", default=str(ROOT / "dist"), help="构建产物目录")
    args = parser.parse_args(argv)

    dist = Path(args.dist)
    if args.switch:
        return switch(args.id, dist)
    if args.capture:
        saved = capture(args.id or current_issue(), dist)
        print(f"已写入 {saved.relative_to(ROOT)}（指针未动）")
        return 0
    return check(args.id, dist)


if __name__ == "__main__":
    raise SystemExit(main())
