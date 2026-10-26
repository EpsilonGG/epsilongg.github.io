"""M3.2 / M3.4 判卷：结构 + 三条硬规则，报错指到字段路径。

判卷比出题严格是故意的。模型答错一次只浪费一次生成，**判卷放过一次**却会让
一句没有出处的话进正本，之后再没人能分辨它是转述还是编的。

检查顺序（先便宜后贵）：

1. 形状：走 `schemas/generation.schema.json`（M1.4 的极简校验器，零依赖）。
2. 来源：每条 claim 至少一个 `sources`，且每个 key 都真实存在于本期材料里。
3. 归属：`handle` 必须在名单内，且必须是本题 `handles` 里的（防止把 A 的话写进 B 的名下）。
4. 唯一：同一个 handle 不许出现两次。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .roster import Roster
from .schema import SchemaError, load_schema, validate


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

    cid = str(answer.get("category") or category or "")
    if category and cid and cid != category:
        problems.append(Problem("$.category", f"本题是 {category}，回答写的是 {cid}"))

    # 「全局题」的 summary 会变成页面的 description，上限 50 而不是 60
    if cid == "all":
        summary = str(answer.get("summary") or "")
        if len(summary) > 50:
            problems.append(Problem("$.summary", f"全局摘要会当成 description，上限 50 字，实际 {len(summary)}"))

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
