"""从标准化条目生成两份产物。

  * `<out>/<期号>.briefing.txt`  — 喂给 LLM 的原始事实摘要（含推文原文与互动数）
  * `<out>/<期号>/report.json`   — 日报骨架（四段全空，等本地 WorkBuddy 填）

M4 之前第二份产物是 `src/content/daily/<期号>.md`（Markdown frontmatter）。
换成 JSON 之后，骨架落在**工作区** `out/` 里，和 `apply` / `confirm` 用的是同一个文件；
要上线再 `daily publish` 把它搬到 `data/daily/`。这样「编辑中的一期」和「已经发布的一期」
在磁盘上就是两个位置，不会出现「改了一半的稿子被构建读进去」。

这里**不调模型**，也不决定写什么。推文原文与互动数只进 briefing，不进站点内容。
"""
from __future__ import annotations

from datetime import date

from .model import Item
from .roster import Roster
from .window import IssueWindow


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


def build_report(
    items: list[Item],
    issue_id: str,
    *,
    accounts: list[str] | None = None,
    roster: Roster | None = None,
    published_at: str = "",
    window: IssueWindow | None = None,
    counts: dict | None = None,
) -> dict:
    """一期日报的正本骨架（四段全空，等本地 WorkBuddy 填）。

    四段全部是结构化字段（highlights / works / interactions / people），不写进正文：
    链接由 handle 拼（模型写不错网址）、summary 为空自动省略（当日没活动就不列）、
    上百人时还要拿去做分类视图与 JSON 输出。

    标题与发布时间不写进数据——它们由期号推导，少一个字段就少一处能和 URL 对不上的地方。

    传了 `roster` 就**按人合并**：同一个人（名单里同 `name`）的主号、小号、社团号
    只出一行，其余号记进 `via`，页面在句末渲染成小一号的账号名链接。
    不传 `roster` 就退回「一个 handle 一行」——老的导入接口还这么用。

    产出的形状和 `apply.new_report()` 一致：`apply` 会直接读这份文件往里合并，
    所以两边字段名必须对得上（`schemas/report.schema.json` 是唯一裁判）。
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

    tally = {"items": 0, "accounts": len(accounts), "late": 0, "skipped_duplicate": 0}
    if counts:
        tally.update({k: v for k, v in counts.items() if k in tally})

    return {
        "schema_version": 1,
        "issue": {
            "id": issue_id,
            "published_at": published_at,
            "window": (
                {"start": window.start.isoformat(), "end": window.end.isoformat()} if window else {}
            ),
            # 骨架一定是草稿：`publish` 会拒绝非 confirmed 的正本，这是上线前的最后一道门
            "status": "draft",
            "confirmed_at": None,
        },
        "counts": tally,
        "description": desc,
        "highlights": [],
        "insights": [],
        "interactions": [],
        "works": "",
        "categories": [],
        "accounts": accounts,
        "people": [
            {"handle": handle, "category": "", "summary": "", "via": via, "sources": []}
            for handle, via in rows
        ],
        "provenance": {
            "generator": "daily.build",
            "prompt_version": 1,
            "cache_key": "",
            "generated_at": "",
        },
    }
