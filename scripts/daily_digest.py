#!/usr/bin/env python3
"""X-Reader 每日推特日报的「本地组装」脚本（站点仓库内唯一可信副本）。

这是混合方案里"无 LLM"的那一半：读取 X-Reader 产出的 NormalizedItem JSONL
（data/items/<source_id>.jsonl），确定性地组装出：

    * <out>/<date>.briefing.txt  — 喂给 LLM 的原始事实摘要
  * <date>.md                 — 写入站点 src/content/daily/<date>.md
                                的日报正文（frontmatter + AI 摘要占位 +
                                按账号分组的推文列表）

"AI 摘要"这一段由**本地 WorkBuddy（LLM）**填写，本脚本不碰 LLM / 不调 API。

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
    """站点 src/content/daily/<date>.md 的正文：frontmatter + 摘要占位 + 分组推文。

    推文媒体渲染为纯链接（[媒体](url)），避免触发站点的本地图片优化流水线。
    """
    by_acc: dict[str, list[dict]] = {}
    for r in records:
        by_acc.setdefault(_display_handle(r), []).append(r)

    accounts = list(sorted(by_acc.keys()))
    lines: list[str] = []
    lines.append("---")
    lines.append(f'title: "X 日报 · {report_date.isoformat()}"')
    desc = (
        f"{report_date.isoformat()} 的 X 动态摘要（"
        + " / ".join(f"@{a}" for a in accounts)
        + "）"
    )
    lines.append(f'description: "{desc}"')
    lines.append(f"pubDate: {report_date.isoformat()}")
    lines.append("source: ai")
    lines.append("accounts:")
    for a in accounts:
        lines.append(f"  - {a}")
    lines.append("---")
    lines.append("")
    lines.append("## 今日 AI 摘要")
    lines.append("")
    lines.append("<!--AI_SUMMARY-->")
    lines.append("")
    for acc, recs in sorted(by_acc.items(), key=lambda kv: -len(kv[1])):
        recs_sorted = sorted(
            recs,
            key=lambda r: (r.get("published_at") or r.get("fetched_at") or ""),
            reverse=True,
        )
        lines.append(f"## @{acc}（{len(recs)} 条）")
        lines.append("")
        for r in recs_sorted:
            meta = r.get("metadata") or {}
            stats = meta.get("stats") or {}
            content = (r.get("content") or r.get("title") or "").replace("\n", " ")
            body = f"- {content}"
            url = r.get("canonical_url")
            suffix = ""
            if url:
                suffix += f" ([原文]({url}))"
            if stats:
                suffix += f" · ❤{_fmt_stat(stats.get('likes'))} 🔁{_fmt_stat(stats.get('retweets'))}"
            if suffix:
                body += suffix
            lines.append(body)
            for m in (r.get("media") or [])[:4]:
                murl = m.get("url") or ""
                if murl:
                    lines.append(f"  - [媒体]({murl})")
        lines.append("")
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
    print("下一步：把 briefing / 该 .md 交给本地 WorkBuddy 填写 AI 摘要（替换 <!--AI_SUMMARY-->）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
