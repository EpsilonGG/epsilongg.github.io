#!/usr/bin/env python
"""M4 出口闸门：日报的 HTML / JSON / TXT / RSS 四个出口是不是都从同一份数据出来了。

`npm run links` 管的是「站内链接指向的东西存不存在」，它看不见 JSON 与 TXT：
那两个出口没有别处链接，靠的是「有一份 report.json 就必须有三份产物」。
这个脚本就是那条规则的可执行版本，也顺手钉住两个容易悄悄坏掉的性质：

1. `/daily/<期号>.json` 与 `data/daily/<期号>/report.json` **逐字节相同**。
   只要有人在 Zod schema 里给字段加默认值、或者在出口里补字段，这条立刻红——
   而「出口是正本的一份 encoding」正是 M4 的全部意义。
2. `/rss.xml`（笔记）里不许出现 `/daily/` 链接。两个 Feed 分开是刻意的：
   日报每天一期，混进主 feed 会改变既有订阅者收到的东西。

用法（先 build）：

    python scripts/check_daily_site.py
    python scripts/check_daily_site.py --dist dist
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import daily_golden  # noqa: E402  —— 同目录的小工具，复用它的 .prose 抽取

DATA = ROOT / "data" / "daily"


class Failure(Exception):
    pass


def _count_items(xml: str) -> int:
    return xml.count("<item>")


def check(dist: Path) -> list[str]:
    notes: list[str] = []
    sources = sorted(p.parent.name for p in DATA.glob("*/report.json"))
    if not sources:
        raise Failure(f"{DATA} 里没有任何 report.json")

    for issue_id in sources:
        page = dist / "daily" / issue_id / "index.html"
        json_out = dist / "daily" / f"{issue_id}.json"
        text_out = dist / "daily" / f"{issue_id}.txt"
        for path in (page, json_out, text_out):
            if not path.exists():
                raise Failure(f"缺产物：{path.relative_to(ROOT)}")

        source = (DATA / issue_id / "report.json").read_bytes()
        if json_out.read_bytes() != source:
            raise Failure(
                f"/daily/{issue_id}.json 与 data/daily/{issue_id}/report.json 不是逐字节相同——"
                "出口不该增删字段，加默认值也不行"
            )
        if not text_out.read_text(encoding="utf-8").strip():
            raise Failure(f"/daily/{issue_id}.txt 是空的")

    notes.append(f"{len(sources)} 期：HTML + JSON + TXT 三种出口齐全，JSON 与正本逐字节相同")

    # 日语版（Ci-en 用）是可选的：有 `report.ja.json` 就必须有 `.ja.txt`，
    # 反过来没有的期号不许冒出空文件——否则页面上会多一个点开是空的按钮。
    # 顺便钉住记法：Ci-en 只认 `##` 见标题、`[..](..)` 链接、`<span style="font-size: 150%">`，
    # 混进 `**`、`- ` 或 `<a>` 的话，贴过去当场变形。
    ja_sources = sorted(p.parent.name for p in DATA.glob("*/report.ja.json"))
    for issue_id in ja_sources:
        ja_out = dist / "daily" / f"{issue_id}.ja.txt"
        if not ja_out.exists():
            raise Failure(f"缺产物：{ja_out.relative_to(ROOT)}（有 report.ja.json 就必须有 .ja.txt）")
        body = ja_out.read_text(encoding="utf-8")
        if not body.startswith('<span style="font-size: 150%">'):
            raise Failure(f"/daily/{issue_id}.ja.txt 开头不是 Ci-en 的字号写法（<span style=...>）")
        if "**" in body:
            raise Failure(f"/daily/{issue_id}.ja.txt 里出现了 `**`，Ci-en 会原样显示")
        if re.search(r"^\s*[-*+] ", body, re.M):
            raise Failure(f"/daily/{issue_id}.ja.txt 里出现了 `-` 列表，改用 `・`")
        if "<a " in body:
            raise Failure(f"/daily/{issue_id}.ja.txt 里出现了 `<a>`，链接要写成 `[文字](URL)`")
        if "## " not in body:
            raise Failure(f"/daily/{issue_id}.ja.txt 没有任何 `##` 小标题")

    stray = sorted(
        p.name for p in (dist / "daily").glob("*.ja.txt") if p.name.split(".")[0] not in set(ja_sources)
    )
    if stray:
        raise Failure(f"这些日语版出口没有对应的 report.ja.json：{'、'.join(stray)}")
    if ja_sources:
        notes.append(f"{len(ja_sources)} 期有日语版出口（Ci-en 记法：## / [..](..) / <span>）")

    daily_rss = dist / "daily" / "rss.xml"
    if not daily_rss.exists():
        raise Failure("缺 /daily/rss.xml")
    daily_count = _count_items(daily_rss.read_text(encoding="utf-8"))
    if daily_count != len(sources):
        raise Failure(f"/daily/rss.xml 有 {daily_count} 条，report.json 有 {len(sources)} 份，两者应相等")
    notes.append(f"/daily/rss.xml {daily_count} 条，与 report.json 份数一致")

    main_rss = dist / "rss.xml"
    if not main_rss.exists():
        raise Failure("缺 /rss.xml")
    main_xml = main_rss.read_text(encoding="utf-8")
    if "/daily/" in main_xml:
        raise Failure("/rss.xml（笔记 Feed）里出现了 /daily/ 链接——两个 Feed 必须分开")
    notes.append(f"/rss.xml 仍只收笔记（{_count_items(main_xml)} 条，无 /daily/ 链接）")

    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="日报出口闸门（M4）")
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    parser.add_argument("--id", default=None, help="金文件比对的期号（默认读 tests/golden/current.json）")
    parser.add_argument("--skip-golden", action="store_true", help="跳过金文件比对")
    args = parser.parse_args(argv)

    dist = Path(args.dist)
    try:
        for note in check(dist):
            print(f"  ✓ {note}")
        if not args.skip_golden:
            code = daily_golden.check(args.id, dist)
            if code != 0:
                return code
    except Failure as exc:
        print(f"  ✗ {exc}")
        return 1
    print("日报出口检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
