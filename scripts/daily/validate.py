"""M3.2 / M3.4 判卷：结构 + 三条硬规则，报错指到字段路径。

判卷比出题严格是故意的。模型答错一次只浪费一次生成，**判卷放过一次**却会让
一句没有出处的话进正本，之后再没人能分辨它是转述还是编的。

检查顺序（先便宜后贵）：

1. 形状：走 `schemas/generation.schema.json`（M1.4 的极简校验器，零依赖）。
2. 语言：整句写成日文的回答直接作废（2026-11-05 261105 事故）。
3. 来源：每条 claim 至少一个 `sources`，且每个 key 都真实存在于本期材料里。
4. 归属：`handle` 必须在名单内，且必须是本题 `handles` 里的（防止把 A 的话写进 B 的名下）。
5. 唯一：同一个 handle 不许出现两次。

第 2 条不是靠提示词自觉：`scripts/daily_lang.py` 数日语语法信号与中文独有标记，
只在「日文信号 ≥ 2 且中文标记 == 0」时判日文，所以日文作品名／人名不会误杀。
它和题面里的简体中文硬规则是一对——提示词会漂移，判卷不会。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# `daily_lang` 与 `daily` 包同在 scripts/ 下；包能被 import 就说明 scripts/ 在 sys.path。
# 判卷层不依赖统一内容层，也不依赖任何第三方包。
import daily_lang  # noqa: E402

from .roster import Roster  # noqa: E402
from .schema import DESCRIPTION_MAX, SchemaError, load_schema, validate  # noqa: E402


@dataclass
class Problem:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass
class ValidationError(ValueError):
    problems: list[Problem] = field(default_factory=list)

    def __str__(self) -> str:
        head = f"回答不合格（{len(self.problems)} 处）："
        return "\n".join([head] + [f"  - {p}" for p in self.problems])


# B 站句柄是 `bili_<uid>`。名单里本来有显示名，但出题材料只带句柄，
# 模型会照抄进叙述——261118-g 的两条互动因此把「被炒的炒饭 / 33祖传上色」
# 写成了 `bili_16302815` / `bili_138256`。题面已加显示名表，这里再兜一道机械闸门。
_BILI_UID_RE = re.compile(r"(?<![A-Za-z0-9_])bili_\d{4,}(?![A-Za-z0-9_])")


def _uid_in_prose(answer: dict) -> list[tuple[str, str]]:
    """叙述字段里漏出的 `bili_<uid>`。handle 字段不算——那是它的正经写法。"""
    hits: list[tuple[str, str]] = []
    if isinstance(answer.get("summary"), str):
        hits.extend(
            (f"$.summary", m.group(0))
            for m in _BILI_UID_RE.finditer(answer["summary"])
        )
    works = answer.get("works") or []
    for i, line in enumerate(works if isinstance(works, list) else []):
        if isinstance(line, str):
            hits.extend(
                (f"$.works[{i}]", m.group(0))
                for m in _BILI_UID_RE.finditer(line)
            )
    for field_name in ("highlights", "interactions"):
        for i, claim in enumerate(answer.get(field_name) or []):
            text = claim.get("text") if isinstance(claim, dict) else None
            if isinstance(text, str):
                hits.extend(
                    (f"$.{field_name}[{i}]", m.group(0))
                    for m in _BILI_UID_RE.finditer(text)
                )
    for i, person in enumerate(answer.get("people") or []):
        text = person.get("summary") if isinstance(person, dict) else None
        if isinstance(text, str):
            hits.extend(
                (f"$.people[{i}].summary", m.group(0))
                for m in _BILI_UID_RE.finditer(text)
            )
    return hits


def _claims(answer: dict) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for i, claim in enumerate(answer.get("highlights") or []):
        out.append((f"$.highlights[{i}]", claim))
    for i, claim in enumerate(answer.get("interactions") or []):
        out.append((f"$.interactions[{i}]", claim))
    for i, person in enumerate(answer.get("people") or []):
        out.append((f"$.people[{i}]", person))
    return out


def validate_answer(
    answer: dict,
    *,
    roster: Roster,
    known_keys: set[str],
    handles: set[str] | None = None,
    category: str | None = None,
) -> None:
    """不合格抛 `ValidationError`，合格返回 None。"""
    problems: list[Problem] = []

    try:
        validate(answer, load_schema("generation"))
    except SchemaError as exc:
        problems.append(Problem(exc.path, exc.message))
        # 形状都不对，后面的检查没有意义（字段可能是字符串而不是列表）
        raise ValidationError(problems) from None

    # 语言闸门：材料全是日文推文，模型有时会顺着材料把整篇中文稿写成日文。
    # 单靠题面那句「请用简体中文」拦不住——这里是 apply 之前的机械判卷。
    drift = daily_lang.scan_answer(answer)
    for path, text in drift[:8]:
        problems.append(
            Problem(path, f"整句写成了日文，中文日报只收简体中文叙述：{text[:48]}")
        )
    if len(drift) > 8:
        problems.append(
            Problem("$", f"另有 {len(drift) - 8} 句日文漂移（本期合计 {len(drift)} 句）")
        )

    # 显示名闸门：句柄只许出现在 people[].handle，叙述里必须写名单里的显示名。
    for path, token in _uid_in_prose(answer)[:8]:
        problems.append(
            Problem(path, f"叙述里不要写 {token}，用账号显示名（句柄只放在 people[].handle）")
        )

    cid = str(answer.get("category") or category or "")
    if category and cid and cid != category:
        problems.append(Problem("$.category", f"本题是 {category}，回答写的是 {cid}"))

    # 「全局题」的 summary 会变成页面的 description，按副标题的上限判
    if cid == "all":
        summary = str(answer.get("summary") or "")
        if len(summary) > DESCRIPTION_MAX:
            problems.append(
                Problem(
                    "$.summary",
                    f"全局摘要会当成 description，上限 {DESCRIPTION_MAX} 字，实际 {len(summary)}",
                )
            )

    for path, claim in _claims(answer):
        sources = claim.get("sources")
        if not isinstance(sources, list) or not sources:
            problems.append(Problem(f"{path}.sources", "没有来源。每句话都必须能指回一条推文"))
            continue
        for j, key in enumerate(sources):
            if str(key) not in known_keys:
                problems.append(Problem(f"{path}.sources[{j}]", f"来源不存在：{key}"))

    seen: dict[str, int] = {}
    for i, person in enumerate(answer.get("people") or []):
        handle = str(person.get("handle") or "").strip()
        path = f"$.people[{i}].handle"
        if not roster.is_known(handle):
            problems.append(Problem(path, f"不在名单里：{handle}（模型不许发明账号）"))
        elif handles is not None and handle not in handles:
            problems.append(Problem(path, f"不在本题的 handles 里：{handle}"))
        if handle in seen:
            problems.append(Problem(path, f"重复出现：{handle}（第一次在 people[{seen[handle]}]）"))
        else:
            seen[handle] = i

    if problems:
        raise ValidationError(problems)
