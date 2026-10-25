#!/usr/bin/env python3
"""X-Reader 每日推特日报的「本地组装」脚本（站点仓库内唯一可信副本）。

这是混合方案里"无 LLM"的那一半：读取 X-Reader 产出的 NormalizedItem JSONL
（data/items/<source_id>.jsonl），确定性地组装出：

    * <out>/<date>.briefing.txt  — 喂给 LLM 的原始事实摘要（含推文原文与互动数）
  * <date>.md                 — 写入站点 src/content/daily/<date>.md
                                的日报骨架（frontmatter 三段：今日看点 / 互动 /
                                详细，全部留空待填；副标题留一句占位简报）

三段内容由**本地 WorkBuddy（LLM）**填写，本脚本不碰 LLM / 不调 API。
站点只渲染 frontmatter，不展示互动数——那些数字只留在 briefing 里供模型判断轻重。

用法：
    # 直接生成当日日报（md-out 默认指向仓库内的 src/content/daily/<今天>.md）
    python scripts/daily_digest.py --items-dir /path/to/X-Reader/data/items

    # 指定日期、指定输出
    python scripts/daily_digest.py --items-dir ... --date 2026-10-24
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path


def _load_items(items_dir: Path) -> list[dict]:
    items: list[dict] = []
    if not items_dir.exists():
        return items
    for path in sorted(items_dir.glob("*.jsonl")):
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if data.get("is_meaningful") is False:
                continue
            items.append(data)
    return items


def _display_handle(item: dict) -> str:
    pub = (item.get("publisher") or "").strip()
    if pub:
        return pub
    return (item.get("metadata") or {}).get("account") or item.get("source_id") or "unknown"


def _date_of(item: dict, fallback: date_cls) -> date_cls:
    for key in ("published_at", "fetched_at"):
        val = item.get(key)
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).date()
            except ValueError:
                continue
    return fallback


def _engagement(item: dict) -> int:
    stats = (item.get("metadata") or {}).get("stats") or {}
    return int(stats.get("likes") or 0) + int(stats.get("retweets") or 0)


def _fmt_stat(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def build_briefing(records: list[dict], report_date: date_cls) -> str:
    lines: list[str] = []
    lines.append(f"# Daily briefing — {report_date.isoformat()}")
    lines.append(f"Total items: {len(records)}")
    lines.append("")
    by_acc: dict[str, list[dict]] = {}
    for r in records:
        by_acc.setdefault(_display_handle(r), []).append(r)
    for acc, recs in sorted(by_acc.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"## @{acc}  ({len(recs)} tweets)")
        top = sorted(recs, key=_engagement, reverse=True)[:5]
        for r in top:
            stats = (r.get("metadata") or {}).get("stats") or {}
            lines.append(
                f"- [❤{_fmt_stat(stats.get('likes'))} "
                f"🔁{_fmt_stat(stats.get('retweets'))}] "
                f"{(r.get('content') or r.get('title') or '')}".strip()
            )
            url = r.get("canonical_url") or ""
            if url:
                lines.append(f"    {url}")
        lines.append("")
    return "\n".join(lines)


def build_markdown(records: list[dict], report_date: date_cls) -> str:
    """站点 src/content/daily/<date>.md 的骨架：frontmatter 三段 + 待填提示。

    三段全部是结构化字段（highlights / interactions / people），不写进 Markdown 正文：
    链接由 handle 拼（模型写不错网址）、summary 为空自动省略（天然满足「当日没活动就不列」）、
    上百人时还要拿去做分类视图与 JSON 输出。

    这里只产出「事实」——今天谁发了多少条；具体写什么由本地 WorkBuddy 填。
    推文原文与互动数只进 briefing.txt（本地中间产物），不再进站点内容。
    """
    by_acc: dict[str, list[dict]] = {}
    for r in records:
        by_acc.setdefault(_display_handle(r), []).append(r)

    # 当日推文多的排前面：人读起来有主次，LLM 也更容易抓住重点
    ordered = sorted(by_acc.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    accounts = [acc for acc, _ in ordered]

    # 副标题是「今日看点」的 50 字以内简报，不是日期 + 账号名。
    # 脚本还看不到内容，所以先放一句占位，由本地 WorkBuddy 连同 highlights 一起改写。
    desc = f"今日 {len(accounts)} 位账号有更新，看点待补"

    lines: list[str] = ["---"]
    lines.append(f'title: "X 日报 · {report_date.isoformat()}"')
    lines.append("# 副标题：≤50 字，概括今日看点；不要写日期，不要罗列账号名")
    lines.append(f'description: "{desc}"')
    lines.append(f"pubDate: {report_date.isoformat()}")
    lines.append("source: ai")
    lines.append("accounts:")
    for a in accounts:
        lines.append(f"  - {a}")
    lines.append("")
    lines.append("# 今日看点：今日热点概括，2–4 段，每项一段（第一顺位）")
    lines.append("highlights: []")
    lines.append("")
    lines.append("# 名单内多人之间的互动，每项一条；没有就保持空数组")
    lines.append("interactions: []")
    lines.append("")
    lines.append("# 每人一句话（句子本身要能看出是谁）；summary 留空 = 当日无活动，不渲染")
    lines.append("people:")
    for a in accounts:
        lines.append(f"  - handle: {a}")
        lines.append('    summary: ""')
    lines.append("---")
    lines.append("")
    lines.append("<!--")
    lines.append("待填（本地 WorkBuddy 完成，脚本不调 LLM）：")
    lines.append("  highlights        今日看点，2–4 段")
    lines.append("  interactions      多人互动，每项一条")
    lines.append("  people[].summary  每人一句话")
    lines.append("依据：out/<date>.briefing.txt（推文原文 + 互动数都在那里）")
    lines.append("-->")
    return "\n".join(lines)


def main() -> int:
    here = Path(__file__).resolve().parent
    repo_root = here.parent  # scripts/.. = 仓库根

    p = argparse.ArgumentParser(description="X-Reader 每日日报本地组装脚本")
    p.add_argument("--items-dir", required=True, help="X-Reader data/items 目录")
    p.add_argument("--date", help="报告日期 YYYY-MM-DD（默认：最新一条数据的日期）")
    p.add_argument("--out", default="out", help="HTML 预览 + briefing 的输出目录")
    p.add_argument(
        "--md-out",
        default=None,
        help="日报 Markdown 输出路径（默认：<仓库>/src/content/daily/<date>.md）",
    )
    args = p.parse_args()

    items_dir = Path(args.items_dir)
    records = _load_items(items_dir)
    if not records:
        print("未找到任何条目。请先运行 X-Reader（CI 或本地），或检查 --items-dir。", file=sys.stderr)
        return 2

    if args.date:
        report_date = date_cls.fromisoformat(args.date)
    else:
        report_date = max(_date_of(r, date_cls.today()) for r in records)

    day_records = [r for r in records if _date_of(r, report_date) == report_date]
    if not day_records:
        day_records = records

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = report_date.isoformat()
    (out / f"{stem}.briefing.txt").write_text(build_briefing(day_records, report_date), encoding="utf-8")
    print(f"Wrote {out / stem}.briefing.txt ({len(day_records)} items)")

    md_out = Path(args.md_out) if args.md_out else (
        repo_root / "src" / "content" / "daily" / f"{stem}.md"
    )
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(build_markdown(day_records, report_date), encoding="utf-8")
    print(f"Wrote Markdown -> {md_out}")
    print(
        "下一步：让本地 WorkBuddy 读 briefing，填写该 .md 里的 "
        "highlights（今日看点）/ interactions（互动）/ people[].summary（每人一句）三段。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
