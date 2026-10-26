"""从标准化条目生成两份产物（M1.1：从 `daily_digest.py` 迁入，输出逐字节不变）。

  * `<out>/<期号>.briefing.txt`   — 喂给 LLM 的原始事实摘要（含推文原文与互动数）
  * `src/content/daily/<期号>.md` — 日报骨架（四段全空，等本地 WorkBuddy 填）

这里**不调模型**，也不决定写什么。推文原文与互动数只进 briefing，不进站点内容。
"""
from __future__ import annotations

from datetime import date

from .model import Item
from .roster import Roster


def _fmt_stat(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _pick(recs: list[Item], per_account: int | None) -> list[Item]:
    """每个账号喂给模型的条目：按（互动, 发布时间）从高到低排，`per_account` 为空就不截。

    **截断默认关掉**，因为它以前是个坑：写死 5 条、且只按互动数排。
    互动数在抓取里经常全是 0，`sorted` 是稳定排序，于是「前 5 条」退化成
    「当天最早的 5 条」——下午发的推全被丢掉，写日报时看到的事实是残的。
    真要限流就显式给数，而且排序键里带上时间，至少丢的是「不重要且早」的。
    """
    ordered = sorted(
        recs,
        key=lambda it: (it.engagement.score(), it.published_at or ""),
        reverse=True,
    )
    return ordered[:per_account] if per_account else ordered


def build_briefing(
    items: list[Item],
    report_date: date,
    accounts: list[str] | None = None,
    per_account: int | None = None,
) -> str:
    """喂给模型的原始事实摘要。

    `accounts` 是名单序（M2.4）。不传就退回「按当日条数」——那是 M1 的旧行为，
    只给老接口与测试用：条数顺序会随抓取顺序漂移，不适合当输出契约。

    `per_account` 是每账号最多写几条，默认 `None` = 全写。传数字就截断，
    截断规则见 `_pick()`——**别再用「按互动排前 N」当默认**，理由在那边。
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
        for it in _pick(recs, per_account):
            lines.append(
                f"- [❤{_fmt_stat(it.engagement.likes)} "
                f"🔁{_fmt_stat(it.engagement.reposts)}] "
                f"{it.text}".strip()
            )
            if it.url:
                lines.append(f"    {it.url}")
        lines.append("")
    return "\n".join(lines)


def build_markdown(
    items: list[Item],
    issue_id: str,
    accounts: list[str] | None = None,
    roster: Roster | None = None,
) -> str:
    """站点 `src/content/daily/<期号>.md` 的骨架：frontmatter 四段 + 待填提示。

    四段全部是结构化字段（highlights / works / interactions / people），不写进 Markdown 正文：
    链接由 handle 拼（模型写不错网址）、summary 为空自动省略（当日没活动就不列）、
    上百人时还要拿去做分类视图与 JSON 输出。

    标题与发布时间不在这里写——它们由文件名推导，少一个字段就少一处能和 URL 对不上的地方。

    传了 `roster` 就**按人合并**：同一个人（名单里同 `name`）的主号、小号、社团号
    只出一行，其余号记进 `via`，页面在句末渲染成小一号的账号名链接。
    不传 `roster` 就退回「一个 handle 一行」——老的导入接口还这么用。
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

    # 按人分组：主号当行首，其余号进 via（只记真正有内容的号）
    rows: list[tuple[str, list[str]]] = []
    if roster is None:
        rows = [(handle, []) for handle in accounts]
    else:
        groups: dict[str, list[str]] = {}
        for handle in accounts:
            account = roster.account(handle)
            key = (account.name if account and account.name else handle)
            groups.setdefault(key, []).append(handle)
        for handles in groups.values():
            main = next(
                (h for h in handles if (roster.account(h) and roster.account(h).role == "main")),
                handles[0],
            )
            rows.append((main, [h for h in handles if h != main]))

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
    lines.append("# 今日看点：只写 ①名单前 9 的人提到的重点 ②本人对自己热度的讨论 ③特别活动")
    lines.append("# 其余的不要往这里塞，写进下面的 people 就够；一段一件事，别把五个人挤进一段")
    lines.append("highlights: []")
    lines.append("")
    lines.append("# 作品动态：一段话，汇总账号提到的制作中 / 发售 / 销量里程碑。可以点名是谁说的，")
    lines.append("# 但**不要加来源链接**——人名在「详细」里已经链到主号了")
    lines.append("works: \"\"")
    lines.append("")
    lines.append("# 名单内多人之间的互动，每项一条；没有就保持空数组")
    lines.append("interactions: []")
    lines.append("")
    lines.append("# 每人一句话。渲染成「声优名（链接） ：summary」，所以 summary 里不要再写 @handle")
    lines.append("# 一个人的主号/小号/社团号合并成一条叙述，其余号写进 via（页面句末显示小号链接）")
    lines.append("# summary 留空 = 当日无活动，不渲染")
    lines.append("people:")
    for handle, via in rows:
        lines.append(f"  - handle: {handle}")
        lines.append('    summary: ""')
        if via:
            lines.append("    via:")
            for other in via:
                lines.append(f"      - {other}")
    lines.append("---")
    lines.append("")
    lines.append("<!--")
    lines.append(f"期号 {issue_id}（YYMMDDHH，JST），标题与发布时间由文件名推导，不用手写。")
    lines.append("待填（本地 WorkBuddy 完成，脚本不调 LLM）：")
    lines.append("  highlights        今日看点：只写前 9 的重点、自述热度、特别活动")
    lines.append("  works             作品动态：一段话，不带来源链接")
    lines.append("  interactions      多人互动，每项一条")
    lines.append("  people[].summary  每人一句话，不写 @handle")
    lines.append(f"依据：out/{issue_id}.briefing.txt（推文原文 + 互动数都在那里）")
    lines.append("-->")
    return "\n".join(lines)
