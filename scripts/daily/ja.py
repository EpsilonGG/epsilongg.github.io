"""M5 Ci-en 版：`report.json` → `report.ja.json`。

`/daily/<期号>.ja.txt` 是日报的六个出口之一，但它一直是**手写**的：261027 那份是
一句句翻出来的，261028 由 CI 出稿，于是当天就没有 Ci-en 稿可发。这不是「忘了」，
是流程里根本没有这一步。这个模块把它补成一道固定工序。

为什么不做成「构建时自动翻」：

    CI 不跑 LLM（模型调用只在本机），而日文版只能由模型翻。所以它必须是**显式**的
    两步：正本定稿后 `daily ja` 出题 → 模型答 → `daily ja --answer` 判卷落盘。
    把它藏在 build 里，只会得到一份没人看过、也没人负责的机器译文。

三条规矩：

* **只收声优栏目**。Ci-en 稿是发给声优粉丝的，厂商侧的看点要剔掉——用
  `highlight_indexes` 指定保留中文 `highlights` 的哪几条，`people` 只留 `category:
  seiyuu` 的人。剔哪几条是编辑判断，不交给脚本猜。
* **`description_zh` 要重写**。正本的副标题可能提了厂商（「CHAOS-R 新作完工」），
  日文版不收厂商，所以中文那句也得换一句——这也是它单独存一个字段的原因。
* **正文不许自带记法**。`**`、`- ` 列表、`<a>`、`<span>`、`#` 标题都由渲染器
  （`src/lib/cien.ts`）负责，数据里出现就会被原样打进 Ci-en，所以这里直接拦下。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import paths
from .roster import Roster

HOOK_MAX = 40
DESCRIPTION_MAX = 140
DESCRIPTION_ZH_MAX = 70

# 正文里不该出现的记法：渲染器负责排版，数据只存纯文本。
FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("**", "加粗只由渲染器加在人名链接上，正文里的 `**` 会原样显示"),
    ("<a ", "Ci-en 不支持 <a>，链接一律写成 [文字](URL)"),
    ("<iframe", "chobet 嵌入还没做，不要塞 iframe"),
    ("<span", "字号由渲染器统一处理，正文不要再写 span"),
    ("\n#", "标题由渲染器写，正文不要自带 #"),
    ("\n- ", "Ci-en 的列表符号是「・」，不要用 Markdown 的「- 」"),
)

ALLOWED_KEYS = {
    "schema_version",
    "hook",
    "description",
    "description_zh",
    "highlights",
    "highlight_indexes",
    "works",
    "interactions",
    "people",
    "insights",
}


class JaError(RuntimeError):
    """日文版不合格。消息里带全部问题，不要一条一条试。"""


def _strings(payload: object, prefix: str = "") -> list[tuple[str, str]]:
    """把 payload 里所有字符串摊平，带上路径，便于报错指到具体字段。"""
    out: list[tuple[str, str]] = []
    if isinstance(payload, str):
        out.append((prefix or "（根）", payload))
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            out.extend(_strings(item, f"{prefix}[{i}]"))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            out.extend(_strings(value, f"{prefix}.{key}" if prefix else str(key)))
    return out


def _seiyuu(roster: Roster) -> set[str]:
    return {a.handle for a in roster.accounts if a.category == "seiyuu"}


def _name(roster: Roster, handle: str) -> str:
    """名单里的显示名；名单外退回 `@handle`（和站点渲染保持一致的退化方式）。"""
    account = roster.account(handle)
    return account.name if account and account.name else f"@{handle}"


def validate(answer: object, report: dict, roster: Roster) -> None:
    """判卷。一次性把所有问题报出来，不要让人一条条试。"""
    problems: list[str] = []

    if not isinstance(answer, dict):
        raise JaError("日文版必须是 JSON 对象")

    unknown = set(answer) - ALLOWED_KEYS
    if unknown:
        problems.append(f"不认识的字段：{'、'.join(sorted(unknown))}（是不是拼错了？）")

    for key, limit in (
        ("hook", HOOK_MAX),
        ("description", DESCRIPTION_MAX),
        ("description_zh", DESCRIPTION_ZH_MAX),
    ):
        value = answer.get(key, "")
        if not isinstance(value, str):
            problems.append(f"{key} 必须是字符串")
            continue
        if len(value) > limit:
            problems.append(f"{key} 超长：{len(value)} > {limit}")

    zh_highlights = report.get("highlights") or []
    highlights = answer.get("highlights") or []
    indexes = answer.get("highlight_indexes") or []

    if not isinstance(highlights, list) or not all(isinstance(h, str) for h in highlights):
        problems.append("highlights 必须是字符串数组")
        highlights = []
    if not isinstance(indexes, list) or not all(isinstance(i, int) for i in indexes):
        problems.append("highlight_indexes 必须是整数数组")
        indexes = []

    if indexes:
        if indexes != sorted(set(indexes)):
            problems.append("highlight_indexes 要严格递增且不重复")
        out_of_range = [i for i in indexes if i < 0 or i >= len(zh_highlights)]
        if out_of_range:
            problems.append(
                f"highlight_indexes 越界：{out_of_range}（中文正本只有 {len(zh_highlights)} 条看点）"
            )
    if len(highlights) != len(indexes or zh_highlights):
        problems.append(
            f"highlights 条数对不上：给了 {len(highlights)} 条，"
            f"但 {'highlight_indexes 选了 ' + str(len(indexes)) + ' 条' if indexes else '中文正本有 ' + str(len(zh_highlights)) + ' 条'}"
        )

    people = answer.get("people") or []
    if not isinstance(people, list):
        problems.append("people 必须是数组")
        people = []

    report_people = [p.get("handle") for p in report.get("people") or []]
    order = {h: i for i, h in enumerate(report_people)}
    allowed = _seiyuu(roster)
    seen: set[str] = set()
    last = -1

    for i, person in enumerate(people):
        if not isinstance(person, dict):
            problems.append(f"people[{i}] 必须是对象")
            continue
        extra = set(person) - {"handle", "summary"}
        if extra:
            problems.append(f"people[{i}] 多了字段：{'、'.join(sorted(extra))}")
        handle = str(person.get("handle") or "")
        summary = person.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            problems.append(f"people[{i}] 缺 summary")
        if not handle:
            problems.append(f"people[{i}] 缺 handle")
            continue
        if handle in seen:
            problems.append(f"{handle} 出现了两次")
        seen.add(handle)
        if handle not in order:
            problems.append(f"{handle} 不在这一期的正本里（是不是把 handle 抄错了？）")
        elif handle not in allowed:
            problems.append(f"{handle} 不是声优（Ci-en 版只收声优栏目）")
        elif order[handle] < last:
            problems.append(f"{handle} 的顺序和中文正本不一致（要按正本的顺序）")
        else:
            last = order[handle]

    for where, text in _strings(answer):
        for needle, why in FORBIDDEN:
            if needle in text:
                problems.append(f"{where} 里有 {needle!r}：{why}")

    if problems:
        raise JaError("日文版不合格：\n  - " + "\n  - ".join(problems))


def _glossary_hits(text: str, limit: int = 12) -> list[dict]:
    """中文原文里出现过的术语，附进题面，避免同一个人两天两种译法。"""
    path = Path(__file__).resolve().parents[2] / "data" / "glossary.json"
    if not path.exists():
        return []
    terms = json.loads(path.read_text(encoding="utf-8")).get("terms") or []
    hits = [t for t in terms if isinstance(t, dict) and str(t.get("zh") or "") in text]
    return hits[:limit]


def build_task(issue_id: str, report: dict, roster: Roster) -> str:
    """出题：中文正本 + 规则 + 输出骨架，一份 Markdown。"""
    from .issue import day_of

    people_rows: list[str] = []
    for person in report.get("people") or []:
        handle = str(person.get("handle") or "")
        summary = str(person.get("summary") or "").strip()
        if not summary:
            continue
        category = roster.category_of(handle)
        mark = "声优" if category == "seiyuu" else f"跳过（{roster.label_of(category)}）"
        people_rows.append(f"- `{handle}`（{_name(roster, handle)}）｜{mark}｜{summary}")

    highlights = report.get("highlights") or []
    highlight_lines = [
        f"[{i}] {str(h.get('text') or '').strip()}" for i, h in enumerate(highlights)
    ]

    body = "\n".join(
        [
            f"# {issue_id} 日文版（Ci-en）出题",
            "",
            f"覆盖日：{day_of(issue_id).isoformat()}（日本时间 00:00–24:00）",
            "",
            "## 要做什么",
            "",
            "把下面这份**已定稿的中文正本**翻成日文版，写成一份 JSON。Ci-en 的读者是"
            "声优粉丝，所以厂商（制造商）相关的内容一概不收。",
            "",
            "## 规则",
            "",
            f"1. `hook` ≤ {HOOK_MAX} 字：接在 `【声優Xまとめ M/D】` 后面的一小句，写当天最具体的那件事。",
            f"2. `description` ≤ {DESCRIPTION_MAX} 字（日文副标题）、`description_zh` ≤ {DESCRIPTION_ZH_MAX} 字（中文副标题）。"
            "**两句都不能提厂商**——正本的副标题如果写了厂商，这里要换一句只说声优的。",
            "3. `highlights` 只放声优侧的看点；用 `highlight_indexes` 指明保留中文第几条（0 起算、递增）。"
            "两者条数必须相等。厂商侧的看点直接不选。",
            "4. `people` 只收**声优**（下面标了「跳过」的不要），顺序和中文正本一致，`handle` 原样照抄。",
            "5. 正文一律纯文本：不要 `**`、不要 `- ` 列表（要列就用「・」）、不要 `<a>`／`<span>`／`<iframe>`、不要 `#` 标题。"
            "加粗和字号由渲染器负责。",
            "6. 人名第一次出现用日文原名（名单里的 `name`），作品名保留日文原名（『』）。",
            "",
            "## 中文正本",
            "",
            f"- description：{report.get('description') or ''}",
            "",
            "### 今日看点",
            "",
            *highlight_lines,
            "",
            "### 作品动态",
            "",
            str(report.get("works") or "（无）"),
            "",
            "### 互动",
            "",
            *(
                [
                    f"- {i + 1}. {t.get('text') if isinstance(t, dict) else t}"
                    for i, t in enumerate(report.get("interactions") or [])
                ]
                or ["（无）"]
            ),
            "",
            "### 详细（每人的一句话）",
            "",
            *people_rows,
            "",
        ]
    )

    glossary = _glossary_hits(
        " ".join(
            [
                str(report.get("description") or ""),
                " ".join(str(h.get("text") or "") for h in highlights),
                str(report.get("works") or ""),
                " ".join(str(p.get("summary") or "") for p in report.get("people") or []),
            ]
        )
    )
    if glossary:
        body += "## 术语（中文 → 日文，保持一致）\n\n"
        body += "\n".join(f"- {t.get('zh')} → {t.get('ja')}" for t in glossary) + "\n\n"

    body += "\n".join(
        [
            "## 输出（存成 JSON，再跑 `daily ja --answer <文件>`）",
            "",
            "```json",
            json.dumps(
                {
                    "schema_version": 1,
                    "hook": "",
                    "description": "",
                    "description_zh": "",
                    "highlights": [],
                    "highlight_indexes": [],
                    "works": "",
                    "interactions": [],
                    "people": [{"handle": "", "summary": ""}],
                    "insights": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
        ]
    )
    return body


def write_task(issue_id: str, report: dict, roster: Roster, out_dir: str | Path) -> Path:
    path = Path(out_dir) / f"{issue_id}.ja-task.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_task(issue_id, report, roster), encoding="utf-8", newline="\n")
    return path


def apply(
    issue_id: str,
    answer_path: str | Path,
    report: dict,
    roster: Roster,
    out_dir: str | Path,
    *,
    force: bool = False,
) -> Path:
    """判卷并落到工作区 `out/<期号>/report.ja.json`。"""
    answer = json.loads(Path(answer_path).read_text(encoding="utf-8"))
    validate(answer, report, roster)

    payload = {
        "schema_version": int(answer.get("schema_version") or 1),
        "hook": str(answer.get("hook") or "").strip(),
        "description": str(answer.get("description") or "").strip(),
        "description_zh": str(answer.get("description_zh") or "").strip(),
        "highlights": [str(h).strip() for h in answer.get("highlights") or []],
        "highlight_indexes": [int(i) for i in answer.get("highlight_indexes") or []],
        "works": str(answer.get("works") or "").strip(),
        "interactions": [str(t).strip() for t in answer.get("interactions") or []],
        "people": [
            {"handle": str(p.get("handle") or ""), "summary": str(p.get("summary") or "").strip()}
            for p in answer.get("people") or []
        ],
        "insights": [str(t).strip() for t in answer.get("insights") or []],
    }

    target = paths.ja_report(paths.workspace(out_dir, issue_id))
    if target.exists() and not force:
        raise JaError(f"{target} 已存在，要覆盖加 --force")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return target
