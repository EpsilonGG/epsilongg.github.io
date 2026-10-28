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

RULES = """\
硬规则（判卷会逐条检查，违反即整份作废）：

1. 每句话都要有来源。`sources` 至少一条，且必须是下面列出的 item key。
   日报是转述不是创作——「补一句听起来合理的话」是最容易犯也最致命的错。
2. `handle` 必须来自本题的 `handles` 列表，不许发明账号，也不许写别人的号。
3. 长度：`summary` ≤ 60 字；`highlights` 2–4 条；`description` ≤ 70 字。
   超限直接判失败，不自动截断——截断会把一句话截成语义不通的半句。
4. 只输出 JSON，不要 Markdown 代码围栏，不要在 JSON 前后写解释。
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

1. 每句话都要有来源。`highlights` / `interactions` / `people[].sources` 至少一条，
   且必须是下面列出的 item key（形如 `x:2113…`）。日报是转述不是创作——
   「补一句听起来合理的话」是最容易犯也最致命的错。
2. `handle` 必须来自本题的 `handles` 列表，不许发明账号，也不许写别人的号。
3. 长度：`summary` ≤ 70 字（它会直接当页面副标题）；`highlights` 2–4 条；
   每人一句 ≤ 60 字。超限直接判失败，不自动截断——截断会把一句话截成语义不通的半句。
4. `summary` 优先写**具体的人或公司**（「柚木つばめ生誕祭前夜」「Qruppo 公布新作」）。
   不要写「声优侧 / 厂商侧」——读者看不到栏目边界，那是我们内部的叫法。
   只有当天整体趋势确实比任何单个事件都重要（例如全行业同日冲发售日）才写整体，
   那时直接说「厂商」「声优」，同样不加「侧」。
5. `works`（作品动态）是一段话：跨人汇总制作中 / 发售 / 销量里程碑。
   不逐条列、不写链接、不需要 sources——人名在 `people` 里已经链到主号。
6. 只输出 JSON，不要 Markdown 代码围栏，不要在 JSON 前后写解释。
"""

ANSWER_SKELETON_FLAT = """\
{
  "category": "all",
  "summary": "（≤70 字，会当页面副标题：今天最值得说的一件事，优先写具体的人或公司）",
  "works": "（作品动态：一段话）",
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
) -> Prompt:
    """整期一份题（`category="all"`）。

    材料是本期**全部条目**，`handles` 是本期所有出过条目的账号。
    回答里的 `summary` 会变成页面副标题，`works` 是作品动态那一段。

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

    digest = input_hash(items)
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
    digest = input_hash(material)

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
            "",
            RULES,
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
