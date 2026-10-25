"""从标准化条目生成两份产物（M1.1：从 `daily_digest.py` 迁入，输出逐字节不变）。

  * `<out>/<期号>.briefing.txt`   — 喂给 LLM 的原始事实摘要（含推文原文与互动数）
  * `src/content/daily/<期号>.md` — 日报骨架（三段全空，等本地 WorkBuddy 填）

这里**不调模型**，也不决定写什么。推文原文与互动数只进 briefing，不进站点内容。
"""
from __future__ import annotations

from datetime import date

from .model import Item


def _fmt_stat(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def build_briefing(items: list[Item], report_date: date, accounts: list[str] | None = None) -> str:
    """喂给模型的原始事实摘要。

    `accounts` 是名单序（M2.4）。不传就退回「按当日条数」——那是 M1 的旧行为，
    只给老接口与测试用：条数顺序会随抓取顺序漂移，不适合当输出契约。
    """
    lines: list[str] = []
    lines.append(f"# Daily briefing — {report_date.isoformat()}")
    lines.append(f"Total items: {len(items)}")
    lines.append("")
    by_acc: dict[str, list[Item]] = {}
    for it in items:
        by_acc.setdefault(it.account, []).append(it)
    if accounts is None:
        accounts = [acc for acc, _ in sorted(by_acc.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    for acc in accounts:
        recs = by_acc.get(acc) or []
        if not recs:
            continue
        lines.append(f"## @{acc}  ({len(recs)} tweets)")
        top = sorted(recs, key=lambda it: it.engagement.score(), reverse=True)[:5]
        for it in top:
            lines.append(
                f"- [❤{_fmt_stat(it.engagement.likes)} "
                f"🔁{_fmt_stat(it.engagement.reposts)}] "
                f"{it.text}".strip()
            )
            if it.url:
                lines.append(f"    {it.url}")
        lines.append("")
    return "\n".join(lines)


def build_markdown(items: list[Item], issue_id: str, accounts: list[str] | None = None) -> str:
    """站点 `src/content/daily/<期号>.md` 的骨架：frontmatter 三段 + 待填提示。

    三段全部是结构化字段（highlights / interactions / people），不写进 Markdown 正文：
    链接由 handle 拼（模型写不错网址）、summary 为空自动省略（当日没活动就不列）、
    上百人时还要拿去做分类视图与 JSON 输出。

    标题与发布时间不在这里写——它们由文件名推导，少一个字段就少一处能和 URL 对不上的地方。
    """
    by_acc: dict[str, list[Item]] = {}
    for it in items:
        by_acc.setdefault(it.account, []).append(it)

    # 名单序（M2.4）：谁先谁后是编辑决定，不是当天谁话多决定的。
    # 不传就退回「按条数」——M1 的旧行为，只给老接口用。
    if accounts is None:
        accounts = [acc for acc, _ in sorted(by_acc.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    else:
        accounts = [a for a in accounts if a in by_acc]

    # 副标题是「今日看点」的 50 字以内简报，不是日期 + 账号名。
    # 脚本还看不到内容，所以先放一句占位，由本地 WorkBuddy 连同 highlights 一起改写。
    desc = f"今日 {len(accounts)} 位账号有更新，看点待补"

    lines: list[str] = ["---"]
    lines.append("# 副标题：≤50 字，概括今日看点；不要写日期，不要罗列账号名")
    lines.append(f'description: "{desc}"')
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
    lines.append(f"期号 {issue_id}（YYMMDDHH，JST），标题与发布时间由文件名推导，不用手写。")
    lines.append("待填（本地 WorkBuddy 完成，脚本不调 LLM）：")
    lines.append("  highlights        今日看点，2–4 段")
    lines.append("  interactions      多人互动，每项一条")
    lines.append("  people[].summary  每人一句话")
    lines.append(f"依据：out/{issue_id}.briefing.txt（推文原文 + 互动数都在那里）")
    lines.append("-->")
    return "\n".join(lines)
