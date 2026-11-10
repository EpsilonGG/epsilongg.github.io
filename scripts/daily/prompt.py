"""M3.1 出题：把「该问的问题」整理成文件，脚本不调模型。

形状是**出题与判卷分离**：这里只写题面（`.md` 给人贴、`.json` 算指纹），
模型读文件、写文件，脚本对它一无所知。所以整个生成过程可以重放——
出了问题能查到是题出错了还是答错了。

两份题：

* 分类题（map）——每个 `category` 一份，材料是这一类里所有人的条目。
* 全局题（reduce）——材料是已经写好的分类回答，产出 `description` 与 `highlights`。
  它必须在分类答完之后出，所以单独一个入口，不混在 `build()` 里。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .cache import FRESH, PROMPT_VERSION, PromptCache, input_hash
from .issue import parse_issue_id

RULES = """\
硬规则（判卷会逐条检查，违反即整份作废）：

1. **叙述一律用简体中文**。下面的材料几乎全是日文推文，但日报是写给中文读者的
   转述，不是原文的复制粘贴。日文作品名、人名、品牌名按术语表原样保留；
   除此之外不许出现日文助词、谓语词尾或成句的日文。判卷会逐句扫「整句写成日文」。
2. 每句话都要有来源。`sources` 至少一条，且必须是下面列出的 item key。
   日报是转述不是创作——「补一句听起来合理的话」是最容易犯也最致命的错。
3. `handle` 必须来自本题的 `handles` 列表，不许发明账号，也不许写别人的号。
4. 长度：`summary` ≤ 60 字；`highlights` 2–4 条；`description` ≤ 70 字。
   超限直接判失败，不自动截断——截断会把一句话截成语义不通的半句。
5. 只输出 JSON，不要 Markdown 代码围栏，不要在 JSON 前后写解释。
"""

ANSWER_SKELETON = """\
{
  "category": "%(category)s",
  "summary": "（这一类今天整体在做什么，≤60 字）",
  "highlights": [
    {"text": "（值得单独说的一件事）", "sources": ["x:…"]}
  ],
  "interactions": [
    {"text": "（名单内两人以上的互动）", "sources": ["x:…"]}
  ],
  "people": [
    {"handle": "（本题 handles 里的一个）", "summary": "（一句话，≤60 字）", "sources": ["x:…"]}
  ]
}
"""

# -- 整期一份题（flat）--------------------------------------------------------
# 现在的日报是「一人一句 + 三段汇总」，不分栏；分类出稿（上面那套 map/reduce）
# 是 M4 之后才要启用的形态。flat 是它的过渡版：**同一套判卷，只出一份题**。
RULES_FLAT = """\
硬规则（判卷会逐条检查，违反即整份作废）：

1. **所有叙述一律用简体中文。** 下面的材料（X 推文）几乎全是日文，但这是**中文日报**，
   写给中文读者的转述，不是原文复制。日文作品名（『』）、曲名（「」）、人名、
   品牌名按术语表**原样保留**；除此之外不许出现日文助词（が／を／の／に）、
   谓语词尾（ました／です／する…）或整句日文叙述。整段照抄材料不算转述：
   判卷会逐句扫「整句写成日文」，命中即整份作废。
2. 每句话都要有来源。`highlights` / `interactions` / `people[].sources` 至少一条，
   且必须是下面列出的 item key（形如 `x:2113…`）。日报是转述不是创作——
   「补一句听起来合理的话」是最容易犯也最致命的错。
3. `handle` 必须来自本题的 `handles` 列表，不许发明账号，也不许写别人的号。
4. 长度：`summary` ≤ 70 字（它会直接当页面副标题）；`highlights` 2–4 条；
   每人一句 ≤ 60 字。超限直接判失败，不自动截断——截断会把一句话截成语义不通的半句。
5. `summary` 优先写**具体的人或公司**（「柚木つばめ生誕祭前夜」「Qruppo 公布新作」）。
   不要写「声优侧 / 厂商侧」——读者看不到栏目边界，那是我们内部的叫法。
   只有当天整体趋势确实比任何单个事件都重要（例如全行业同日冲发售日）才写整体，
   那时直接说「厂商」「声优」，同样不加「侧」。
6. `works`（作品动态）是**数组，一条一个作品**，页面上按条渲染。每条写清
   「哪个作品 / 什么事」（制作中、发售、预约、销量里程碑），一条只说一件事，
   别把两三个作品塞进同一条。**作品开始发售或开放预约的那条必须写出作品名**——
   不许用「多部作品」「一批新作」「某系列」概括，读者要的是名字。
   不写链接、不需要 sources——人名在 `people` 里已经链到主号。最多 24 条，当天没有就空数组。
7. 术语照下面「## 术语」那张表写，`avoid` 列出的写法一律不许出现。
   最容易犯的是**按字面拆词**：`マスターアップ` 是「装盘完成」（母盘做完、进量产准备发售），
   不是「大师升级」。拿不准就照表，表里没有的保留原词并加一句解释。
8. **上两期用过的头条与看点一律降级。** 题面里那张「上两期已用过的头条与看点」列的是
   已经发过的选题，今天不许再当 `summary` 或 `highlights`。连载型事件（一个梗刷屏、
   一场赛事、一条销量倒计时）会连着几天都是「当天最大的一件事」，这正是最容易重复的
   地方。只有当天确实有新事实（新数字、新阶段、新决定）才值得再上一次，而且必须把
   「新在哪」写出来——只换措辞不算新进展。这些话题仍可以写进 `works` 和 `people`。
9. 只输出 JSON，不要 Markdown 代码围栏，不要在 JSON 前后写解释。
"""

# 术语表是 `data/glossary.json`：`ja` 原词、`zh` 本站统一写法、`avoid` 明确不许出现的写法。
# 以前只有日语版题面（`ja.py`）会带这张表，中文稿没有——「マスターアップ → 大师升级」
# 就是这么漏出去的。中文题面也带上，代价是题面长两行，收益是不用每次事后返工。
GLOSSARY = Path(__file__).resolve().parents[2] / "data" / "glossary.json"

# 上两期的头条与看点要进题面。连载型事件（一个梗刷屏、一场赛事、一条销量倒计时）
# 每天都是「当天最大的一件事」，题面里不说「昨天已经领过」，模型就会再领一次——
# 261107 / 261108 / 261109 连着三天同一个头条、同一批看点，就是这么来的。
# 只取**同一版**的前两期：声优版不该被 Galgame 版的头条影响，反之亦然。
PREVIOUS_ISSUES = 2
DAILY_DIR = Path(__file__).resolve().parents[2] / "data" / "daily"

ANSWER_SKELETON_FLAT = """\
{
  "category": "all",
  "summary": "（≤70 字，会当页面副标题：今天最值得说的一件事，优先写具体的人或公司）",
  "works": [
    "（作品动态：一条一个作品，写清作品名 + 制作中/发售/预约/销量里程碑）"
  ],
  "highlights": [
    {"text": "（今日看点，2–4 条，一条一件事）", "sources": ["x:…"]}
  ],
  "interactions": [
    {"text": "（名单内两人以上的互动）", "sources": ["x:…"]}
  ],
  "people": [
    {"handle": "（本题 handles 里的一个）", "summary": "（一句话，≤60 字）", "sources": ["x:…"]}
  ]
}
"""

# 整期题的缓存键。`all` 留给 `build_reduce`，两者写同一个 `all.md`，
# 但输入不同——共用键会让「先跑 flat 再跑 reduce」直接命中错误的缓存。
CACHE_FLAT = "all:flat"


@dataclass
class Prompt:
    category: str
    label: str
    input_hash: str
    md_path: Path
    json_path: Path
    cached: bool
    items: int


def _glossary_lines(limit: int = 80) -> str:
    """术语表 → 题面里那张对照表。读不到就返回空串（不让术语表挡住出题）。"""
    try:
        terms = json.loads(GLOSSARY.read_text(encoding="utf-8")).get("terms") or []
    except (OSError, ValueError):
        return ""
    lines: list[str] = []
    for term in terms[:limit]:
        ja = str(term.get("ja") or "").strip()
        zh = str(term.get("zh") or "").strip()
        if not ja or not zh:
            continue
        avoid = [str(a).strip() for a in (term.get("avoid") or []) if str(a).strip()]
        tail = f"（不要写：{'、'.join(avoid)}）" if avoid else ""
        lines.append(f"- `{ja}` → {zh}{tail}")
    return "\n".join(lines)


def _item_lines(items: list[dict]) -> str:
    lines: list[str] = []
    for item in items:
        head = f"- [{item.get('key')}] @{item.get('account')} · {item.get('published_at')} · {item.get('kind')}"
        lines.append(head)
        body = (item.get("text") or "").strip()
        for line in body.splitlines():
            lines.append(f"    {line}")
        lines.append("")
    return "\n".join(lines)


def _grouped_lines(items: list[dict], handles: list[str]) -> str:
    """按账号分组写材料。整期题的材料很长，分组是模型写「每人一句」的锚点。"""
    by_account: dict[str, list[dict]] = {}
    for item in items:
        by_account.setdefault(str(item.get("account") or ""), []).append(item)

    order = [h for h in handles if h in by_account]
    order += [a for a in by_account if a not in order]  # 名单外的账号排在最后，不丢

    blocks: list[str] = []
    for account in order:
        rows = by_account.get(account) or []
        blocks.append(f"### @{account}（{len(rows)} 条）")
        blocks.append("")
        blocks.append(_item_lines(rows))
    return "\n".join(blocks)


def _write(prompt: Prompt, payload: dict, markdown: str) -> None:
    prompt.json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prompt.md_path.write_text(markdown, encoding="utf-8")


def _previous_issues(
    issue_id: str,
    daily_dir: str | Path | None = None,
    limit: int = PREVIOUS_ISSUES,
) -> list[dict]:
    """同一版、排在当前期之前的最近 `limit` 期：`{id, description, highlights}`。

    读的是 `data/daily/<期号>/report.json`（已发布的定稿），所以**昨天手改过的
    头条也算数**——那正是最该被降级的一条。目录不存在、期号不合法、JSON 坏了
    都只是「没有上一期」，不让它挡住出题。
    """
    try:
        day, kind, seq = parse_issue_id(issue_id)
    except ValueError:
        return []

    root = Path(daily_dir) if daily_dir is not None else DAILY_DIR
    if not root.is_dir():
        return []

    rows: list[tuple[tuple, dict]] = []
    for path in root.glob("*/report.json"):
        other = path.parent.name
        try:
            other_day, other_kind, other_seq = parse_issue_id(other)
        except ValueError:
            continue
        if other_kind != kind or (other_day, other_seq) >= (day, seq):
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        description = str(report.get("description") or "").strip()
        highlights = [
            str(claim.get("text") or "").strip()
            for claim in report.get("highlights") or []
            if isinstance(claim, dict)
        ]
        rows.append(
            (
                (other_day, other_seq),
                {
                    "id": other,
                    "description": description,
                    "highlights": [text for text in highlights if text],
                },
            )
        )

    rows.sort(key=lambda row: row[0], reverse=True)
    return [block for _, block in rows[:limit]]


def _previous_material(blocks: list[dict]) -> list[dict]:
    """把上两期压成伪条目，好进 `input_hash`——换了上一期的头条，指纹就得变。"""
    material: list[dict] = []
    for block in blocks:
        material.append({"key": f"prev:{block['id']}#description", "text": block["description"]})
        for index, text in enumerate(block["highlights"]):
            material.append({"key": f"prev:{block['id']}#highlight{index}", "text": text})
    return material


def _previous_section(blocks: list[dict]) -> str:
    """题面里那张「上两期已用过的头条与看点」。没有上一期就整段不出现。"""
    if not blocks:
        return ""
    lines = ["## 上两期已用过的头条与看点（今天一律降级）", ""]
    for block in blocks:
        lines.append(f"**{block['id']}** 头条：{block['description'] or '（无）'}")
        lines.append("")
        for text in block["highlights"]:
            lines.append(f"- 看点：{text}")
        lines.append("")
    return "\n".join(lines)


def build(
    issue_id: str,
    generate: dict,
    out_dir: str | Path = "out",
    *,
    force: bool = False,
) -> list[Prompt]:
    """按分类各出一份题。输入没变就跳过（返回 `cached=True`）。"""
    ws = paths.ensure(paths.workspace(out_dir, issue_id))
    cache = PromptCache.load(paths.cache(ws))
    built: list[Prompt] = []

    for category in generate.get("categories") or []:
        cid = str(category.get("id") or "")
        label = str(category.get("label") or cid)
        items = list(category.get("items") or [])
        handles = [str(h) for h in category.get("handles") or []]
        digest = input_hash(items)

        prompt = Prompt(
            category=cid,
            label=label,
            input_hash=digest,
            md_path=paths.prompts(ws) / f"{cid}.md",
            json_path=paths.prompts(ws) / f"{cid}.json",
            cached=False,
            items=len(items),
        )

        state = cache.check(cid, digest)
        if state == FRESH and not force and prompt.md_path.exists() and prompt.json_path.exists():
            prompt.cached = True
            built.append(prompt)
            continue

        payload = {
            "issue": issue_id,
            "category": cid,
            "label": label,
            "prompt_version": PROMPT_VERSION,
            "input_hash": digest,
            "handles": handles,
            "items": items,
            "instructions": {
                "output": "纯 JSON，形状见 answer 模板",
                "rules": RULES.splitlines()[2:],
            },
        }
        markdown = "\n".join(
            [
                f"# 日报 {issue_id} · {label}（{cid}）",
                "",
                f"本期这一类共 **{len(items)} 条**、**{len(handles)} 个账号**。",
                "",
                "## 要求",
                "",
                RULES,
                "## 本题的 handles（`people[].handle` 只能从这里取）",
                "",
                "、".join(f"`{h}`" for h in handles) or "（空）",
                "",
                "## 材料",
                "",
                _item_lines(items) or "（这一类今天没有条目）",
                "## 回答模板",
                "",
                "```json",
                ANSWER_SKELETON % {"category": cid},
                "```",
                "",
                f"写好后存成 `{paths.answers(ws) / (cid + '.json')}`。",
                "",
            ]
        )
        _write(prompt, payload, markdown)
        cache.record(cid, digest, stale=(state != FRESH and state != "miss"))
        built.append(prompt)

    cache.save()
    return built


def build_flat(
    issue_id: str,
    generate: dict,
    out_dir: str | Path = "out",
    *,
    force: bool = False,
    daily_dir: str | Path | None = None,
) -> Prompt:
    """整期一份题（`category="all"`）。

    材料是本期**全部条目**，`handles` 是本期所有出过条目的账号。
    回答里的 `summary` 会变成页面副标题，`works` 是作品动态那几条（一条一个作品）。

    为什么不是分类题：现在的日报版式是「一人一句 + 三段汇总」，一期就是一篇，
    拆成两三个分类反而要再写一次 reduce 去拼。等真按「聊人 / 聊音声 / 聊事情」
    分栏出稿时再改用 `build()`，判卷（`validate_answer`）两边通用。
    """
    ws = paths.ensure(paths.workspace(out_dir, issue_id))
    cache = PromptCache.load(paths.cache(ws))

    items: list[dict] = []
    handles: list[str] = []
    for category in generate.get("categories") or []:
        for handle in category.get("handles") or []:
            handle = str(handle)
            if handle not in handles:
                handles.append(handle)
        items.extend(category.get("items") or [])

    # 上两期的头条与看点也进指纹：上一期改了头条，这一期的题面就得重出。
    previous = _previous_issues(issue_id, daily_dir)
    digest = input_hash(items + _previous_material(previous))
    prompt = Prompt(
        category="all",
        label="整期",
        input_hash=digest,
        md_path=paths.prompts(ws) / "all.md",
        json_path=paths.prompts(ws) / "all.json",
        cached=False,
        items=len(items),
    )

    state = cache.check(CACHE_FLAT, digest)
    if state == FRESH and not force and prompt.md_path.exists() and prompt.json_path.exists():
        prompt.cached = True
        return prompt

    payload = {
        "issue": issue_id,
        "category": "all",
        "label": "整期",
        "prompt_version": PROMPT_VERSION,
        "input_hash": digest,
        "handles": handles,
        "items": items,
        "previous_issues": previous,
        "instructions": {
            "output": "纯 JSON，形状见 answer 模板",
            "rules": RULES_FLAT.splitlines()[2:],
        },
    }
    markdown = "\n".join(
        [
            f"# 日报 {issue_id} · 整期（all）",
            "",
            f"本期共 **{len(items)} 条**、**{len(handles)} 个账号**。",
            "",
                "## 要求",
                "",
                RULES_FLAT,
                *([_previous_section(previous)] if previous else []),
                "## 术语（照这张表写，`avoid` 里的写法一律不许出现）",
            "",
            _glossary_lines() or "（术语表为空）",
            "",
            "## 本题的 handles（`people[].handle` 只能从这里取）",
            "",
            "、".join(f"`{h}`" for h in handles) or "（空）",
            "",
            "## 材料（按账号分组，方括号里是来源 key）",
            "",
            _grouped_lines(items, handles) or "（今天没有条目）",
            "## 回答模板",
            "",
            "```json",
            ANSWER_SKELETON_FLAT,
            "```",
            "",
            f"写好后存成 `{paths.answers(ws) / 'all.json'}`。",
            "",
        ]
    )
    _write(prompt, payload, markdown)
    cache.record(CACHE_FLAT, digest, stale=(state != FRESH and state != "miss"))
    cache.save()
    return prompt


def build_reduce(
    issue_id: str,
    answers: list[dict],
    out_dir: str | Path = "out",
    *,
    force: bool = False,
    daily_dir: str | Path | None = None,
) -> Prompt:
    """全局题（reduce）：材料是分类回答，产出 `description` 与 `highlights`。"""
    ws = paths.ensure(paths.workspace(out_dir, issue_id))
    cache = PromptCache.load(paths.cache(ws))

    material = [
        {
            "key": f"{a.get('category')}#summary",
            "account": a.get("category"),
            "published_at": "",
            "kind": "summary",
            "text": a.get("summary") or "",
        }
        for a in answers
    ]
    for answer in answers:
        for claim in answer.get("highlights") or []:
            material.append(
                {
                    "key": f"{answer.get('category')}#highlight",
                    "account": answer.get("category"),
                    "published_at": "",
                    "kind": "highlight",
                    "text": claim.get("text") or "",
                }
            )
    previous = _previous_issues(issue_id, daily_dir)
    digest = input_hash(material + _previous_material(previous))

    prompt = Prompt(
        category="all",
        label="全局",
        input_hash=digest,
        md_path=paths.prompts(ws) / "all.md",
        json_path=paths.prompts(ws) / "all.json",
        cached=False,
        items=len(material),
    )
    state = cache.check("all", digest)
    if state == FRESH and not force and prompt.md_path.exists():
        prompt.cached = True
        return prompt

    payload = {
        "issue": issue_id,
        "category": "all",
        "label": "全局",
        "prompt_version": PROMPT_VERSION,
        "input_hash": digest,
        "handles": [],
        "items": material,
        "previous_issues": previous,
        "instructions": {"output": "纯 JSON，产出 description 与 highlights"},
    }
    markdown = "\n".join(
        [
            f"# 日报 {issue_id} · 全局（reduce）",
            "",
            "下面是各分类已经写好的摘要与看点。请据此写：",
            "",
            "1. `description`：≤70 字，概括今天最值得说的一件事。不要写日期，不要罗列账号名；"
            "优先写具体的人或公司，不要写「声优侧 / 厂商侧」（读者看不到栏目边界），"
            "只有全行业同日的整体趋势才值得写整体，那时也直接说「厂商」「声优」。",
            "2. `highlights`：2–4 条，跨分类挑，每条带 `sources`。",
            "3. 上两期用过的头条与看点一律降级：下面那张表里的选题不许再当 `description` "
            "或 `highlights`，除非当天有新事实，并且要写清新在哪。",
            "",
            RULES,
            *([_previous_section(previous)] if previous else []),
            "## 各分类回答",
            "",
            "```json",
            json.dumps(answers, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 回答模板",
            "",
            "```json",
            '{\n  "category": "all",\n  "summary": "（≤60 字，一句话总述）",\n'
            '  "highlights": [{"text": "…", "sources": ["x:…"]}],\n'
            '  "interactions": [],\n  "people": []\n}',
            "```",
            "",
            f"写好后存成 `{paths.answers(ws) / 'all.json'}`。",
            "",
        ]
    )
    _write(prompt, payload, markdown)
    cache.record("all", digest, stale=(state != FRESH and state != "miss"))
    cache.save()
    return prompt
