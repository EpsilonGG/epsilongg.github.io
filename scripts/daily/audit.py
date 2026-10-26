"""M3.9 事后判卷：对**已经写好的正本**再核一遍来源与归属。

M3.2 的判卷发生在 `apply`——回答进正本之前就拦住。但日报实际最常用的那条路
（本地 WorkBuddy 直接改 `out/<期号>/report.json`）**绕过了 `apply`**，
于是「每句话都要能指回一条推文」这条硬规则在最常用的路上完全没生效：
七期已发布的正本里 `people[].sources` 全是空数组，没人发现，因为没人看。

这个模块补的就是那道门。它不回答「该怎么写」，只回答一个问题：
**写下来的这些字，能不能指回当天的推文、能不能对上一个真实账号。**

判卷放在两个地方用：

* `daily audit --issue`——随时手动查，能查已发布的期。
* `daily confirm` 定稿前自动跑——不通过就不许定稿。

两种严格度：`strict` 要求每条 claim 都有来源（新写的稿子）；
`lenient` 只查「写了来源但来源是假的」（迁移过来的旧正本没有来源，
它们已经上线了，不该因为补了个校验就把自己判死）。
"""
from __future__ import annotations

from dataclasses import dataclass

from .roster import Roster

ERROR = "error"
WARN = "warn"


@dataclass(frozen=True)
class Finding:
    path: str
    message: str
    level: str = ERROR

    def __str__(self) -> str:
        mark = "✗" if self.level == ERROR else "!"
        return f"{mark} {self.path}: {self.message}"


def _claim_paths(report: dict) -> list[tuple[str, dict]]:
    """所有「一句话 + 来源」的位置，含分类视图里的。"""
    out: list[tuple[str, dict]] = []
    for field in ("highlights", "interactions", "insights"):
        for i, claim in enumerate(report.get(field) or []):
            out.append((f"$.{field}[{i}]", claim))
    for ci, category in enumerate(report.get("categories") or []):
        cid = category.get("id") or ci
        for field in ("highlights", "interactions"):
            for i, claim in enumerate(category.get(field) or []):
                out.append((f"$.categories[{cid}].{field}[{i}]", claim))
    return out


def _sources(claim: dict) -> list[str]:
    raw = claim.get("sources")
    if not isinstance(raw, list):
        return []
    return [str(s) for s in raw]


def audit_report(
    report: dict,
    *,
    roster: Roster,
    known_keys: set[str] | None,
    accounts: set[str] | None = None,
    strict: bool = True,
) -> list[Finding]:
    """返回全部问题。空列表 = 通过。

    `known_keys` 为 None 表示拿不到本期材料（没有 `generate.json`），
    这时只查归属不查来源——**不能假装查过了**，调用方要自己说一句。
    """
    findings: list[Finding] = []

    for path, claim in _claim_paths(report):
        sources = _sources(claim)
        if not sources:
            findings.append(
                Finding(
                    f"{path}.sources",
                    "没有来源。日报是转述，每句话都该能指回一条推文",
                    ERROR if strict else WARN,
                )
            )
            continue
        if known_keys is None:
            continue
        for j, key in enumerate(sources):
            if key not in known_keys:
                findings.append(Finding(f"{path}.sources[{j}]", f"来源不存在：{key}"))

    seen: dict[str, int] = {}
    for i, person in enumerate(report.get("people") or []):
        handle = str(person.get("handle") or "").strip()
        path = f"$.people[{i}]"
        if not handle:
            findings.append(Finding(f"{path}.handle", "handle 是空的"))
            continue
        if not roster.is_known(handle):
            findings.append(Finding(f"{path}.handle", f"不在名单里：{handle}"))
        elif accounts is not None and handle not in accounts:
            # 只提醒，不算错。名单里有、当天却没条目，可能是重复判定把它当成了重复、
            # 也可能是编辑从「提及」里补的人——两者都合法。**凭空造人**会先撞上
            # `不在名单里`，再造一个名单内的人则会在 sources 上露馅。
            findings.append(
                Finding(
                    f"{path}.handle",
                    f"本期没有 {handle} 的条目——这个人是从哪来的？（重复判定 / 提及补录都合法）",
                    WARN,
                )
            )
        if handle in seen:
            findings.append(
                Finding(f"{path}.handle", f"重复出现：{handle}（第一次在 people[{seen[handle]}]）")
            )
        else:
            seen[handle] = i
        if not str(person.get("summary") or "").strip():
            findings.append(Finding(f"{path}.summary", "没有摘要，页面上不会出现这个人", WARN))
        sources = _sources(person)
        if not sources:
            findings.append(
                Finding(
                    f"{path}.sources",
                    "没有来源。至少该指回他自己那条推文",
                    ERROR if strict else WARN,
                )
            )
        elif known_keys is not None:
            for j, key in enumerate(sources):
                if key not in known_keys:
                    findings.append(Finding(f"{path}.sources[{j}]", f"来源不存在：{key}"))

    description = str(report.get("description") or "")
    if len(description) > 50:
        findings.append(Finding("$.description", f"副标题上限 50 字，实际 {len(description)}"))

    for i, handle in enumerate(report.get("accounts") or []):
        if not roster.is_known(str(handle)):
            findings.append(Finding(f"$.accounts[{i}]", f"不在名单里：{handle}", WARN))

    return findings


def has_errors(findings: list[Finding]) -> bool:
    return any(f.level == ERROR for f in findings)


def summarize(findings: list[Finding]) -> str:
    errors = sum(1 for f in findings if f.level == ERROR)
    warns = len(findings) - errors
    if not findings:
        return "判卷通过：来源与归属都能对上"
    head = f"判卷发现 {errors} 处错误"
    if warns:
        head += f"、{warns} 处提醒"
    return "\n".join([head + "："] + [f"  {f}" for f in findings])
