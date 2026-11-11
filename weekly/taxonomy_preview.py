"""试验性：新作消息分类预览（独立 HTML，不进初稿、不进筛选页）。

2026-11-10 用户在原六类之外又补了「体验版公开 / 主机版(NS·CS)公开 /
DLC 公开·更新 / OP 影像」，并问这些是否该单开一栏「新作情报」。

本模块**只做预览**，用于人工判断分类法，不改任何出稿链路：
* 只读 `out/filter-data.json` / `out/decisions.json` / `out/image-preview-data.json`
  / `out/corpus.json`；
* 只写 `out/taxonomy-preview.html` + `out/taxonomy-preview-data.json`；
* 不写 `draft.md` / `draft-selected.md` / `filter.html` / `decisions.json`
  / `records.json`，也不改 X-Reader、日报正本或名单。

核心结论（数据里量出来的，不是拍脑袋）：新增四类讲的不是「走到哪一步」
（生命周期 / stage），而是「说的是哪个发布物」（形态 / form）。两条轴正交，
所以「新作情报」更适合当筛选页的一个视图，而不是第四栏。
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .config import OUT, WORK, read_json, write_json, write_text

GENERATOR = "weekly/taxonomy-preview/1"
BASE_FORM = "base"
BASE_FORM_LABEL = "本篇本体"


def _compile_group(tax: dict, group: str, order: list[str]) -> dict:
    """rules.json 的词表 → {key: {label, patterns:[(原文, 正则)]}}。"""
    out: dict = {}
    for key in order:
        entry = (tax.get(group) or {}).get(key) or {}
        pats = entry.get("patterns") or []
        out[key] = {
            "label": str(entry.get("label") or key),
            "patterns": [(str(p), re.compile(str(p), re.I)) for p in pats],
        }
    return out


def compile_rules(tax: dict) -> dict:
    stage_order = list(tax["stage_order"])
    form_order = list(tax["form_order"])
    return {
        "stage_order": stage_order,
        "form_order": form_order,
        "stages": _compile_group(tax, "stages", stage_order),
        "forms": _compile_group(tax, "forms", form_order),
        "peripheral": [(str(p), re.compile(str(p), re.I))
                       for p in (tax.get("peripheral") or {}).get("patterns") or []],
        "override": [(str(p), re.compile(str(p), re.I))
                     for p in tax.get("peripheral_override") or []],
        "surfaces": set(tax.get("surfaces") or ["sentence"]),
    }


def _surface(item: dict, surfaces: set[str]) -> str:
    """只用日报中文正本：sentence + M1 分句 text/context，不扫日文原推全文。"""
    parts: list[str] = []
    if "sentence" in surfaces:
        parts.append(str(item.get("sentence") or ""))
    for c in item.get("candidates") or []:
        if "candidate_text" in surfaces:
            parts.append(str(c.get("text") or ""))
        if "candidate_context" in surfaces:
            parts.append(str(c.get("context") or ""))
    return "\n".join(parts)


def _hits(surface: str, group: dict) -> tuple[list[str], list[dict]]:
    keys: list[str] = []
    evidence: list[dict] = []
    for key, entry in group.items():
        for pattern, rex in entry["patterns"]:
            m = rex.search(surface)
            if m:
                keys.append(key)
                evidence.append({
                    "axis": "", "key": key, "pattern": pattern,
                    "match": m.group(0)[:48],
                })
                break
    return keys, evidence


def classify_item(item: dict, compiled: dict) -> dict:
    surface = _surface(item, compiled["surfaces"])
    stages, ev_stage = _hits(surface, compiled["stages"])
    forms, ev_form = _hits(surface, compiled["forms"])
    for row in ev_stage:
        row["axis"] = "stage"
    for row in ev_form:
        row["axis"] = "form"
    peri = next((p for p, rex in compiled["peripheral"] if rex.search(surface)), "")
    override = next((p for p, rex in compiled["override"] if rex.search(surface)), "")

    if (stages or forms) and not override:
        scope = "core"
    elif peri or override:
        scope = "peripheral"
    else:
        scope = "unclassified"

    stage_order = compiled["stage_order"]
    form_order = compiled["form_order"]
    primary_stage = max(stages, key=stage_order.index) if stages else ""
    primary_form = next((k for k in form_order if k in forms), BASE_FORM)
    evidence = ev_stage + ev_form
    if peri:
        evidence.append({"axis": "peripheral", "key": "peripheral",
                         "pattern": peri, "match": ""})
    if override:
        evidence.append({"axis": "override", "key": "peripheral",
                         "pattern": override, "match": ""})
    return {
        "stages": stages, "forms": forms, "scope": scope,
        "primary_stage": primary_stage, "primary_form": primary_form,
        "peripheral_hit": bool(peri), "override_hit": bool(override),
        "evidence": evidence,
    }


def _first_image_map() -> dict[str, dict]:
    """图片预览（已按「每推只取第一张」裁过）→ item_key 的首图信息。"""
    path = OUT / "image-preview-data.json"
    if not path.is_file():
        return {}
    payload = read_json(path)
    out: dict[str, dict] = {}
    for e in payload.get("eligible") or []:
        key = str(e.get("item_key") or "")
        if key and key not in out and e.get("images"):
            out[key] = {
                "url": e["images"][0],
                "photo_link": (e.get("photo_links") or [""])[0],
                "local": (e.get("local_images") or [None])[0],
            }
    return out


def build_preview(rules: dict) -> dict:
    tax = rules["taxonomy"]
    compiled = compile_rules(tax)
    data = read_json(OUT / "filter-data.json")
    decisions = read_json(OUT / "decisions.json")
    deleted = set(decisions.get("deleted_items") or [])
    first_images = _first_image_map()

    items: list[dict] = []
    for section in data["sections"]:
        for item in section["items"]:
            tags = classify_item(item, compiled)
            src = (item.get("sources") or [{}])[0]
            items.append({
                "key": item["key"], "column": section["column"],
                "brand": section["label"], "game": item.get("group_label") or "",
                "work": item.get("work_canonical") or "",
                "sentence": str(item.get("sentence") or ""),
                "in_initial_draft": item["key"] not in deleted,
                "default_deleted": bool(item.get("default_deleted")),
                "day": item.get("day") or "",
                "source_url": str(src.get("url") or ""),
                "first_image": first_images.get(item["key"]),
                **tags,
            })

    live = [i for i in items if i["in_initial_draft"]]
    stage_order = compiled["stage_order"]
    form_order = compiled["form_order"]

    stage_counts = Counter(s for i in live for s in i["stages"])
    form_counts = Counter(f for i in live for f in i["forms"])
    scope_counts = Counter(i["scope"] for i in live)
    # stage × form 正交矩阵（一条可同时落在多格）。
    cross = Counter((s, f) for i in live for s in i["stages"] for f in i["forms"])

    new_forms = set(tax["option_a"]["forms"])
    expanded_forms = set(tax["option_a"]["expanded_forms"])
    def a_split(keys: set[str]) -> dict:
        new_only = conflict = old_only = neither = 0
        for i in live:
            has_new = bool(set(i["forms"]) & keys)
            has_old = bool(i["stages"])
            if has_new and has_old:
                conflict += 1
            elif has_new:
                new_only += 1
            elif has_old:
                old_only += 1
            else:
                neither += 1
        return {"new_only": new_only, "conflict": conflict,
                "old_only": old_only, "neither": neither}

    # 方案 C：按游戏小标题再分形态小节，会多出多少标题 / 其中多少是空的。
    by_game: dict[str, list[dict]] = defaultdict(list)
    for i in live:
        if i["column"] == WORK and i["game"] and i["game"] != "未标注作品":
            by_game[i["game"]].append(i)
    c_extra = 0
    c_empty = 0
    c_groups = 0
    for game, rows in by_game.items():
        seen = {f for r in rows for f in r["forms"]}
        if not seen:
            continue
        c_groups += 1
        c_extra += len(seen) + 1  # 每个形态一个小节 + 一个「本篇本体」
        c_empty += len(form_order) - len(seen)  # 未命中的形态小节会空着

    # 挑一个形态最丰富的游戏做三种方案的真实排版示例。
    sample_game = max(by_game, key=lambda g: (
        len({f for r in by_game[g] for f in r["forms"]}), len(by_game[g]))) if by_game else ""
    sample_rows = by_game.get(sample_game, [])[:8]

    stats = {
        "items_total": len(items),
        "items_in_initial_draft": len(live),
        "columns": Counter(i["column"] for i in live),
        "scope": scope_counts,
        "stages": dict(stage_counts),
        "forms": dict(form_counts),
        "multi_tag_items": sum(1 for i in live if len(i["stages"]) + len(i["forms"]) >= 2),
        "cross": {f"{s}|{f}": n for (s, f), n in cross.items()},
        "option_a": a_split(new_forms),
        "option_a_expanded": a_split(expanded_forms),
        "option_c": {"groups_with_forms": c_groups, "extra_headings": c_extra,
                     "empty_headings": c_empty, "game_groups": len(by_game)},
        "game_groups": len(by_game),
        "items_with_first_image": sum(1 for i in live if i["first_image"]),
    }
    payload = {
        "schema_version": 1,
        "generator": GENERATOR,
        "experimental": True,
        "deprecated": True,
        "superseded_by": "game-routing-preview.html",
        "deprecated_note": "2026-11-10 用户裁决：分流单位应是「游戏」而不是「小条目」。按条目算出的 A 方案冲突是伪命题；新作是作品的子集，游戏整组路由。",
        "integrated_into_draft": False,
        "integrated_into_filter": False,
        "columns": list(data["columns"]),
        "labels": {
            "stages": {k: v["label"] for k, v in compiled["stages"].items()},
            "forms": {k: v["label"] for k, v in compiled["forms"].items()},
            "forms_all": {BASE_FORM: BASE_FORM_LABEL,
                          **{k: v["label"] for k, v in compiled["forms"].items()}},
            "scope": {"core": "作品本体", "peripheral": "作品周边",
                      "unclassified": "未归类（人工）"},
        },
        "orders": {"stages": stage_order, "forms": form_order},
        "options": {
            "A": {"label": tax["option_a"]["label"],
                  "new_column": tax["option_a"]["new_column"],
                  "note": tax["option_a"]["note"],
                  "forms": sorted(new_forms),
                  "expanded_forms": sorted(expanded_forms)},
            "B": dict(tax["option_b"]),
            "C": dict(tax["option_c"]),
        },
        "sample_game": sample_game,
        "sample_rows": sample_rows,
        "stats": stats,
        "items": items,
        "notes": {
            "surfaces": tax["surface_note"],
            "scope": tax["scope_note"],
            "stage": tax["stage_note"],
            "form": tax["form_note"],
            "peripheral": tax["peripheral_note"],
            "taxonomy": tax["note"],
        },
    }
    return payload


_CSS = """
:root{--bg:#fafafa;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e3e5e9;--blue:#1d4ed8;--amber:#92400e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
header{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:18px}
h1{font-size:24px;margin:0 0 6px}
h2{font-size:17px;margin:30px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:14px;margin:16px 0 8px}
.sub{color:var(--muted);font-size:12px}
.badge{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;color:var(--muted);margin:8px 6px 0 0}
.badge.warn{border-color:#9ca3af;color:#374151;background:#f6f7f9}
.note{border-left:3px solid #9ca3af;padding:9px 12px;background:#f6f7f9;border-radius:0 6px 6px 0;font-size:13px;color:#374151;margin:12px 0}
.note b{color:var(--ink)}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.stat{border:1px solid var(--line);border-radius:6px;background:#fff;padding:8px 12px;min-width:128px}
.stat b{display:block;font-size:20px;line-height:1.3}
.stat span{font-size:11px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:12px;background:#fff;margin:8px 0}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;word-break:break-word}
th{background:#f6f7f9;font-weight:600}
td.num,th.num{text-align:right;white-space:nowrap}
tr.zero td{color:#9aa0aa}
code{background:#f1f2f4;border-radius:4px;padding:1px 5px;font-size:12px}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0}
.tab{border:1px solid var(--line);background:#fff;border-radius:6px;padding:6px 12px;font-size:13px;cursor:pointer;color:var(--ink)}
.tab.on{background:#111827;color:#fff;border-color:#111827}
.panel{display:none}.panel.on{display:block}
.split{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.split>div{border:1px solid var(--line);border-radius:6px;background:#fff;padding:10px}
.md{font:12px/1.8 ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-word;background:#f6f7f9;border:1px solid var(--line);border-radius:6px;padding:10px;margin:0}
.md .conflict{color:#a32d2d}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.chip{border:1px solid var(--line);background:#fff;border-radius:14px;padding:3px 10px;font-size:12px;cursor:pointer;color:var(--muted)}
.chip.on{background:#eef2ff;border-color:#a5b4fc;color:#1e3a8a}
.tg{display:inline-block;font-size:10px;border-radius:4px;padding:1px 5px;margin:0 3px 2px 0;border:1px solid var(--line);white-space:nowrap}
.tg.stage{background:#eff6ff;border-color:#bfdbfe;color:#1e40af}
.tg.form{background:#fffbeb;border-color:#fde68a;color:#92400e}
.tg.core{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
.tg.peripheral{background:#fff7ed;border-color:#fed7aa;color:#9a3412}
.tg.unclassified{background:#f3f4f6;color:#6b7280}
.tg.base{background:#f9fafb;color:#6b7280}
.row{border:1px solid var(--line);border-radius:6px;background:#fff;padding:9px 11px;margin:7px 0}
.row .txt{font-size:13px}
.row .meta{font-size:11px;color:var(--muted);margin-top:3px}
.row .thumb{float:right;width:104px;margin:0 0 6px 10px;border:1px solid var(--line);border-radius:6px;overflow:hidden;font-size:10px;color:var(--muted);text-align:center;background:#fff}
.row .thumb img{display:block;width:104px;height:76px;object-fit:cover;background:#f1f2f4}
.row:after{content:"";display:block;clear:both}
.row.off{opacity:.62}
.row a{color:var(--blue);text-decoration:none}.row a:hover{text-decoration:underline}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:26px}
@media(max-width:820px){.split{grid-template-columns:1fr}}
"""


def _esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""))


def _tag(key: str, label: str, kind: str) -> str:
    return f'<span class="tg {kind}">{_esc(label)}</span>'


def _tags_for(item: dict, labels: dict) -> str:
    out = [_tag(item["scope"], labels["scope"][item["scope"]], item["scope"])]
    for s in item["stages"]:
        out.append(_tag(s, labels["stages"][s], "stage"))
    for f in item["forms"]:
        out.append(_tag(f, labels["forms"][f], "form"))
    if not item["forms"]:
        out.append(_tag(BASE_FORM, BASE_FORM_LABEL, "base"))
    return "".join(out)


def _mock_a(labels: dict, sample_game: str, rows: list[dict], new_forms: set[str]) -> str:
    left: list[str] = [f"## {_esc('新作情报')}（试验栏）", ""]
    right: list[str] = ["## 作品情报", ""]
    for r in rows:
        line = "- " + r["sentence"]
        has_new = bool(set(r["forms"]) & new_forms)
        has_old = bool(r["stages"])
        if has_new:
            left.append(line + ("    ← 同时命中原六类" if has_old else ""))
        if has_old:
            right.append(line + ("    ← 同时命中新四类" if has_new else ""))
    if len(left) == 2:
        left.append("（本例无条目）")
    if len(right) == 2:
        right.append("（本例无条目）")
    return (
        '<div class="split"><div><h3>新开的「新作情报」栏</h3>'
        f'<pre class="md">{_esc(chr(10).join(left))}</pre>'
        '<div class="note">同一条消息同时是「体验版公开」和「发售 / 情报公开」，'
        '两栏都要放；只放一栏就丢信息，重复放就重复计条目。</div></div>'
        '<div><h3>留在「作品情报」栏</h3>'
        f'<pre class="md">{_esc(chr(10).join(right))}</pre></div></div>'
    )


def _mock_b(labels: dict, sample_game: str, rows: list[dict]) -> str:
    body = [f"### {_esc(rows[0]['brand']) if rows else '品牌'}", "",
            f"#### {_esc(sample_game)}", ""]
    body += ["- " + r["sentence"] for r in rows]
    badge_lines = []
    for r in rows:
        names = [labels["scope"][r["scope"]]]
        names += [labels["stages"][s] for s in r["stages"]]
        names += [labels["forms"][f] for f in r["forms"]]
        if not r["forms"]:
            names.append(BASE_FORM_LABEL)
        badge_lines.append(" / ".join(names))
    return (
        '<div class="split"><div><h3>出稿正文（与现在逐字相同）</h3>'
        f'<pre class="md">{_esc(chr(10).join(body))}</pre>'
        '<div class="note">栏目、中标题、小标题、短横线小条目一律不动；标签只存在'
        '数据层，用于筛选页徽标、复选与组内排序。</div></div>'
        '<div><h3>筛选页徽标视图（仅工作台可见）</h3>'
        f'<pre class="md">{_esc(chr(10).join(badge_lines))}</pre></div></div>'
    )


def _mock_c(labels: dict, sample_game: str, rows: list[dict]) -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        for f in (r["forms"] or [BASE_FORM]):
            grouped[f].append("- " + r["sentence"])
    body = [f"#### {_esc(sample_game)}", ""]
    for f, lines in grouped.items():
        body.append(f"##### {_esc(labels['forms_all'].get(f, f))}")
        body += lines
        body.append("")
    return (
        '<div class="split"><div><h3>按形态分小节的排版</h3>'
        f'<pre class="md">{_esc(chr(10).join(body))}</pre></div>'
        '<div><h3>代价</h3><div class="note">四层结构会变成五层；'
        '多形态条目要在多个小节重复；未命中的形态每周都是空标题。'
        '右侧统计给出实测会多出多少标题。</div></div></div>'
    )


def render_html(payload: dict, path: Path) -> str:
    s = payload["stats"]
    labels = payload["labels"]
    orders = payload["orders"]
    esc = _esc

    badges = "".join(
        f'<span class="badge{" warn" if warn else ""}">{esc(t)}</span>'
        for t, warn in (
            ("已废弃 · 按条目打标签", True),
            ("试验性 · 只做分类预览", True),
            ("独立 HTML", False),
            ("不进 draft.md", False),
            ("不进 filter.html", False),
            ("不参与归栏", False),
            ("十类词表在 rules.json", False),
            ("图片每推只取第一张", False),
        ))

    tiles = "".join(
        f'<div class="stat"><b>{esc(v)}</b><span>{esc(k)}</span></div>'
        for v, k in (
            (s["items_total"], "全部小条目"),
            (s["items_in_initial_draft"], "初稿中的条目"),
            (s["scope"].get("core", 0), "作品本体 core"),
            (s["scope"].get("peripheral", 0), "作品周边 peripheral"),
            (s["scope"].get("unclassified", 0), "未归类（人工）"),
            (s["multi_tag_items"], "命中 ≥2 类"),
            (s["items_with_first_image"], "带首图条目"),
            (s["game_groups"], "游戏小标题"),
        ))

    # 一、类型词表
    type_rows = []
    for axis, keys, counts, group in (
        ("stage 生命周期", orders["stages"], s["stages"], labels["stages"]),
        ("form 发布形态", orders["forms"], s["forms"], labels["forms"]),
    ):
        for k in keys:
            n = counts.get(k, 0)
            sample = next(
                (i["sentence"] for i in payload["items"] if i["in_initial_draft"]
                 and (k in i["stages"] or k in i["forms"])), "")
            type_rows.append(
                f'<tr class="{"zero" if not n else ""}">'
                f'<td>{esc(group[k])}</td><td>{esc(axis)}</td>'
                f'<td><code>{esc(k)}</code></td>'
                f'<td class="num">{n}</td>'
                f'<td class="num">{n / max(s["items_in_initial_draft"], 1) * 100:.1f}%</td>'
                f'<td>{esc(sample[:72])}</td></tr>'
            )

    # 二、正交矩阵
    cross = s["cross"]
    head = "".join(f'<th class="num">{esc(labels["forms"].get(f, f))}</th>'
                   for f in orders["forms"])
    cross_rows = []
    for st in orders["stages"]:
        cells = "".join(
            f'<td class="num">{cross.get(f"{st}|{f}", 0) or "·"}</td>'
            for f in orders["forms"])
        cross_rows.append(f'<tr><td>{esc(labels["stages"][st])}</td>{cells}</tr>')
    conflicts = s["option_a"]["conflict"]
    conflict_samples = [
        i for i in payload["items"]
        if i["in_initial_draft"] and i["stages"]
        and set(i["forms"]) & set(payload["options"]["A"]["forms"])
    ][:6]
    conflict_html = "".join(
        f'<div class="row"><div class="txt">{esc(i["sentence"])}</div>'
        f'<div class="meta">{_tags_for(i, labels)} · {esc(i["brand"])} / {esc(i["game"])}</div></div>'
        for i in conflict_samples)

    # 三、方案对照
    sample_game = payload["sample_game"]
    sample_rows = payload["sample_rows"]
    a = s["option_a"]
    ae = s["option_a_expanded"]
    c = s["option_c"]
    panels = (
        '<div class="panel on" id="pA">'
        '<div class="note"><b>方案 A · ' + esc(payload["options"]["A"]["label"]) + '</b>：'
        f'新补四类去「{esc(payload["options"]["A"]["new_column"])}」，原六类留「{esc(WORK)}」。'
        f'实测：只命中新四类 {a["new_only"]} 条 / <b>两栏都命中 {a["conflict"]} 条</b> / '
        f'只命中原六类 {a["old_only"]} 条 / 两类都不命中 {a["neither"]} 条。'
        f'若把候选形态也扩进新栏（共 {len(payload["options"]["A"]["forms"])} → '
        f'{len(payload["options"]["A"]["expanded_forms"])} 类），冲突升到 {ae["conflict"]} 条。'
        '</div>'
        + _mock_a(labels, sample_game, sample_rows, set(payload["options"]["A"]["forms"]))
        + '</div>'
        '<div class="panel" id="pB">'
        '<div class="note"><b>方案 B · ' + esc(payload["options"]["B"]["label"]) + '</b>：'
        + esc(payload["options"]["B"]["note"]) +
        ' 三条轴：scope（互斥：本体 / 周边 / 未归类）、stage（生命周期，多标签）、'
        'form（发布物形态，多标签）。「新作情报」变成筛选页的一个视图开关，'
        '而不是一个物理栏目。</div>'
        + _mock_b(labels, sample_game, sample_rows) + '</div>'
        '<div class="panel" id="pC">'
        '<div class="note"><b>方案 C · ' + esc(payload["options"]["C"]["label"]) + '</b>：'
        + esc(payload["options"]["C"]["note"]) +
        f' 实测有形态标签的游戏小标题 {c["groups_with_forms"]} 个（全部 {c["game_groups"]} 个），'
        f'会多出 {c["extra_headings"]} 个小节标题，其中约 {c["empty_headings"]} 个是空的。</div>'
        + _mock_c(labels, sample_game, sample_rows) + '</div>'
    )

    # 四、条目清单
    chips = ['<span class="chip on" data-f="all">全部</span>',
             '<span class="chip" data-f="core">作品本体</span>',
             '<span class="chip" data-f="peripheral">作品周边</span>',
             '<span class="chip" data-f="unclassified">未归类</span>']
    for k in orders["stages"]:
        chips.append(f'<span class="chip" data-f="stage:{esc(k)}">{esc(labels["stages"][k])}</span>')
    for k in orders["forms"]:
        chips.append(f'<span class="chip" data-f="form:{esc(k)}">{esc(labels["forms"][k])}</span>')

    rows_html = []
    for i in payload["items"]:
        tags = " ".join(["scope:" + i["scope"]]
                        + ["stage:" + x for x in i["stages"]]
                        + ["form:" + x for x in i["forms"]])
        thumb = ""
        fi = i.get("first_image")
        if fi:
            src = fi.get("local") or fi.get("url") or ""
            thumb = (
                f'<a class="thumb" href="{esc(fi.get("photo_link") or i["source_url"])}" '
                'target="_blank" rel="noopener">'
                f'<img src="{esc(src)}" alt="首图" loading="lazy" '
                f"onerror='this.style.display=\"none\"'>"
                '首图 · photo/1</a>'
            )
        state = "初稿" if i["in_initial_draft"] else "默认不入初稿（可在筛选页恢复）"
        rows_html.append(
            f'<div class="row{" off" if not i["in_initial_draft"] else ""}" data-tags="{esc(tags)}">'
            f'{thumb}<div class="txt">{esc(i["sentence"])}</div>'
            f'<div class="meta">{_tags_for(i, labels)} · {esc(i["column"])} / '
            f'{esc(i["brand"])} / {esc(i["game"])} · {esc(i["day"])} · {esc(state)}</div>'
            '</div>'
        )

    # 五、图片规则
    ip = read_json(OUT / "image-preview-data.json")
    ips = ip["stats"]
    image_tiles = "".join(
        f'<div class="stat"><b>{esc(v)}</b><span>{esc(k)}</span></div>'
        for v, k in (
            (ips.get("qualified_items", 0), "合格图片栏目条目"),
            (ips.get("qualified_images", 0), "实际使用图片"),
            (ips.get("qualified_raw_images", 0), "这些条目原有图片"),
            (ips.get("qualified_raw_images", 0) - ips.get("qualified_images", 0),
             "裁掉的多余图片"),
            (ips.get("cached_images", 0), "本地缓存样图"),
        ))
    storage = ip.get("storage") or {}
    st_rows = "".join(
        f'<tr><td>{esc(r["name"])}</td><td class="num">{r["bytes"] / 1024 / 1024:.2f} MB</td>'
        f'<td>{esc(r["note"])}</td></tr>'
        for r in storage.get("strategies") or [])

    doc = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>新作消息分类 · 试验性预览</title>'
        f'<style>{_CSS}</style></head><body><div class="wrap">'
        f'<header><h1>新作消息分类 · 试验性预览</h1>'
        '<div class="sub">weekly / taxonomy-preview · 独立文档，用于判断分类法，不是出稿</div>'
        f'{badges}</header>'
        '<div class="note"><b>⚠ 本页已废弃（2026-11-10 用户裁决）</b>：分流单位应是'
        '<b>游戏</b>，不是小条目。按小条目算出的「A 方案冲突 24 条」是伪命题 —— '
        '新作是作品的子集，游戏一旦带新作标签就整组进「新作」栏，不存在同一条消息两边都放。'
        '<a href="game-routing-preview.html"><b>看新版：按游戏分流 →</b></a>'
        '<br>本页保留只为对照「逐条关键词会错在哪」，不再作为推荐方案。</div>'
        '<div class="note"><b>这一版回答的问题</b>：你补的「体验版公开 / 主机版(NS·CS)公开 / '
        'DLC 公开·更新 / OP 影像」确实都算作品情报，但它们和原六类<b>不是同一条轴</b>。'
        '原六类问的是「这个作品走到哪一步」（生命周期 stage）；新四类问的是'
        '「说的是哪个发布物」（形态 form）。所以「主机版发售」天然同时是 stage=发售 + '
        'form=主机版，硬拆成「新作情报 / 作品情报」两栏会让同一条消息两边都要放。'
        '推荐把「新作情报」做成筛选页的一个<b>视图</b>，三栏物理结构保持不变。'
        '<br>判定只在日报中文正本（正文 + M1 分句）上做，逐字留证据；'
        '不扫日文原推全文是为了避开页脚 / 转推串词。词表全在 '
        '<code>rules.json:taxonomy</code>，改词不用改代码。'
        '<br><b>本页不改动</b> <code>draft.md</code> / <code>draft-selected.md</code> / '
        '<code>filter.html</code> / <code>decisions.json</code> / <code>records.json</code>。</div>'
        f'<div class="stats">{tiles}</div>'
        '<h2>一、类型词表与实测命中</h2>'
        '<div class="note">同一个条目可以命中多类，所以各列相加会超过 100%。'
        '<code>stage</code> 是生命周期、<code>form</code> 是发布物形态，两部分各自多标签。'
        '命中 0 条的条目不自动丢弃，落到 <code>unclassified</code> 交人工。</div>'
        '<table><thead><tr><th>类型</th><th>轴</th><th>键</th><th class="num">条数</th>'
        '<th class="num">占初稿</th><th>样例</th></tr></thead>'
        f'<tbody>{"".join(type_rows)}</tbody></table>'
        '<h2>二、为什么「似乎又不太一样」：两条轴是正交的</h2>'
        '<div class="note">下面是 stage × form 共现矩阵（格子里是「同时命中」的条目数）。'
        '只要矩阵非对角线上有数，说明两类不能互斥地分到两个栏里。'
        f'按你设想的 A 方案，初稿里有 <b>{conflicts}</b> 条同时命中新四类与原六类。</div>'
        '<table><thead><tr><th>生命周期 ＼ 发布形态</th>'
        f'{head}</tr></thead><tbody>{"".join(cross_rows)}</tbody></table>'
        '<h3>冲突条目实例</h3>' + (conflict_html or '<div class="note">无</div>') +
        '<h2>三、三种分组方案对照</h2>'
        '<div class="tabs">'
        '<button class="tab on" data-p="A" type="button">A · 新作情报独立成栏</button>'
        '<button class="tab" data-p="B" type="button">B · 三轴标签，栏目不变（推荐）</button>'
        '<button class="tab" data-p="C" type="button">C · 游戏下按形态分小节</button>'
        '</div>' + panels +
        f'<div class="note">以上排版用的是真实组：<code>{esc(sample_game)}</code>'
        f'（{len(sample_rows)} 条），不是造的示例文本。</div>'
        '<h2>四、真实条目清单（点徽标筛类型）</h2>'
        '<div class="chips">' + "".join(chips) + '</div>'
        f'<div id="rows">{"".join(rows_html)}</div>'
        '<h2>五、图片规则：每个源推只取第一张</h2>'
        '<div class="note">「有图片就只放第一张」已同步到图片栏目预览：'
        '<code>sidecar</code> 与原始 JSONL 的 URL 一条不删，只在生成预览时裁到 '
        '<code>[0:1]</code>，图片入口恒为 <code>/photo/1</code>，不再出现 '
        '<code>/photo/2</code> 及以上。上面的清单里带「首图」缩略图的条目就是命中者。'
        '完整对照与存储测算见 <a href="image-preview.html">image-preview.html</a>。</div>'
        f'<div class="stats">{image_tiles}</div>'
        + (f'<table><thead><tr><th>存储方案</th><th class="num">一期</th><th>口径</th>'
           f'</tr></thead><tbody>{st_rows}</tbody></table>' if st_rows else '') +
        '<footer>试验产物 · 分类仅供人工裁决 · 十类词表在 rules.json:taxonomy · '
        '决定是否落地后再谈接入初稿与筛选页</footer>'
        '</div><script>'
        'var tabs=document.querySelectorAll(".tab");'
        'tabs.forEach(function(t){t.addEventListener("click",function(){'
        'tabs.forEach(function(x){x.classList.remove("on")});t.classList.add("on");'
        'document.querySelectorAll(".panel").forEach(function(p){'
        'p.classList.toggle("on",p.id==="p"+t.dataset.p)});});});'
        'var chips=document.querySelectorAll(".chip"),rows=document.querySelectorAll("#rows .row");'
        'chips.forEach(function(c){c.addEventListener("click",function(){'
        'chips.forEach(function(x){x.classList.remove("on")});c.classList.add("on");'
        'var f=c.dataset.f;rows.forEach(function(r){'
        'r.style.display=(f==="all"||r.dataset.tags.split(" ").indexOf(f)>=0)?"":"none";});});});'
        'document.body.setAttribute("data-js-ok","1");'
        '</script></body></html>'
    )
    write_text(Path(path), doc)
    return doc


def build(rules: dict | None = None) -> dict:
    from .config import load_rules
    rules = rules or load_rules()
    payload = build_preview(rules)
    write_json(OUT / "taxonomy-preview-data.json", payload)
    render_html(payload, OUT / "taxonomy-preview.html")
    return payload
