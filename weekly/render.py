"""展示层：四栏（新作 / 作品情报 / 业界动向 / B站动态）+ `tier_order` 默认顺序 + 与筛选页逐字节一致的 Markdown。

2026-11-10 正式版裁决：品牌动向并入作品情报、新作整组上提为第一栏、
看点 / 互动栏目删除。归栏三值仍是证据（`sections[].column`），展示用
`item["display_column"]`——两端读同一份，不各算一遍。
2026-11-12 裁决：B 站动态作为第二数据源单独成行走第四栏（不经 X 侧归栏），
命中游戏级「新作」规则的那几组仍上提到第一栏。

正文不写出处键；名单外账号条目按裁决保留一条指向原推 URL 的
Markdown 链接（URL 取自源索引），其余来源账号、候选分句与完整源索引只在素材库与筛选页。
"""
from __future__ import annotations

import hashlib
from collections import Counter

from .config import (COLUMNS, DISPLAY_COLUMNS, INDUSTRY, MOVEMENT, NEW, WORK,
                     GENERATOR, DEFAULT_FORMAT, display_format, write_json, write_text)
from .pipeline import _norm_text


def build_lead(result: dict) -> str:
    """导语：窗口 + 语料规模 + 筛选结果。

    这里给的是**默认排除前**的池子（品牌中标题 / 游戏小标题 / 小条目），与 `check`
    打印的那组一致；正文实际行数更少，因为生日词、「未标注作品」等会在渲染时被勾掉。
    别把这两个数混着写——读稿的人会以为正文少了一大块。
    """
    c = result["corpus"]
    s = result["stats"]
    win = c["window"]
    return (
        f"汇总窗口 {win['start']} – {win['end']} 共 {len(c['issues'])} 期 Galgame 日报正本"
        f"（{len(c['indexed_issues'])} 期带 M1 分句索引，{len(c['prose_only_issues'])} 期仅正本散文）；"
        f"源索引 {len(c['source_refs'])} 键 / 候选分句 {len(c['candidates'])} 条。"
        f"四类筛选后入稿 {s['verdicts']['admit']} 条，排除前折成 {s['sections']} 个品牌中标题 / "
        f"{s['game_groups']} 个游戏小标题 / {s['items']} 条小条目，按展示栏目分流。"
    )


def default_decisions(data: dict) -> dict:
    """生日词 /「未标注作品」条目默认勾删（仍在筛选页，可点「恢复」）；group_column 默认不切栏。

    `schema_version` 跟随编辑器数据（现为 7），别再写死 6 —— 两边对不上时，
    浏览器里导出的 decisions.json 与 build 生成的默认 decisions.json 会互不认。
    """
    version = data.get("schema_version") or 7
    return {
        "schema_version": version,
        "generator": f"weekly/selection/{version}",
        "source": data["id"],
        "deleted_sections": [],
        "deleted_items": [i["key"] for s in data["sections"] for i in s["items"]
                          if i.get("default_deleted")],
        "deleted_highlights": [h["key"] for h in (data.get("highlights") or [])
                               if h.get("default_deleted")],
        "deleted_interactions": [x["key"] for x in (data.get("interactions") or [])
                                 if x.get("default_deleted")],
        "section_order": [s["key"] for s in data["sections"]],
        "item_order": {s["key"]: [i["key"] for i in s["items"]] for s in data["sections"]},
        "highlight_order": [h["key"] for h in data["highlights"]],
        "group_column": dict(data.get("group_column") or {}),
        # 2026-11-11 上线裁决：这不叫「人工确认 0 的半成品」，而是**确定性策略输出**。
        # 规则固定 → 同一份语料永远得到同一份 decisions；不做人工看稿，所以
        # human_confirmed 恒为 0 是设计值，不是缺口。改口径要改 rules.json，
        # 不是往这份文件里手填几个 key（下一次 build 会覆盖）。
        "policy": {
            "mode": "deterministic_default",
            "human_confirmed": 0,
            "human_review_required": False,
            "note": "按 rules.json 的生日词 / 未标注作品默认排除、栏目默认顺序、不切栏，确定性生成。发布前无需人工确认。",
        },
    }


def build_feeds(result: dict) -> tuple[list[dict], list[dict]]:
    """看点 / 互动：逐字取自日报，按内容归栏，但走筛选页的专用行块。"""
    identity, refs = result["identity"], result["corpus"]["source_refs"]
    highlights: list[dict] = []
    interactions: list[dict] = []
    for rec in result["feeds"]:
        digest = hashlib.md5((rec["day"] + _norm_text(rec["text"])).encode("utf-8")).hexdigest()[:8]
        sources = []
        for key in rec["source_index_all"]:
            ref = refs.get(key) or {}
            eff = identity.effective_handle(key, refs)
            sources.append({
                "key": key, "url": ref.get("url") or "", "text": ref.get("text") or "",
                "author": ref.get("author") or "", "handle": eff["handle"],
                "display_name": identity.names.get(eff["handle"], ""),
                "mapped": eff["in_roster"], "class": eff["class"],
                "promoted": eff["promoted"], "published_at": ref.get("published_at") or "",
            })
        entry = {
            "key": ("h:" if rec["origin"] == "highlight" else "i:") + rec["day"] + ":" + digest,
            "day": rec["day"], "text": rec["text"], "column": rec["column"],
            "account_class": rec["account_class"], "sources": sources,
            "default_deleted": bool(rec["birthday"] and not rec.get("birthday_exempt")),
        }
        (highlights if rec["origin"] == "highlight" else interactions).append(entry)
    return highlights, interactions


def _format_of(data: dict) -> dict:
    fmt = dict(DEFAULT_FORMAT)
    fmt.update(data.get("format") or {})
    return fmt


def _ordered(lines: list[dict], column: str, fmt: dict) -> list[dict]:
    """官号条目前置：稳定分区，同区内保留筛选页的手动顺序。"""
    if column not in fmt["official_first"]:
        return list(lines)
    return [x for x in lines if x["official"]] + [x for x in lines if not x["official"]]


def collect(data: dict, decisions: dict) -> dict:
    """把决策折算成 栏目 → 品牌 → 游戏小标题 → 行 的四层桶。

    行是 `{"text": "- ...", "official": bool}`。版式规则（前缀 / 前置）全部在
    这里按 `data.format` 一次定死；Python 出稿与 `cli.check` 共用此结果，
    筛选页内联 JS 按同一份 `format` 与同一条 `display_column` 逐字节复刻。
    """
    columns = list(DISPLAY_COLUMNS)
    fmt = _format_of(data)
    by_section = {s["key"]: s for s in data["sections"]}
    items = {i["key"]: i for s in data["sections"] for i in s["items"]}
    ds = set(decisions.get("deleted_sections") or [])
    di = set(decisions.get("deleted_items") or [])

    brand_order: dict[str, list[str]] = {c: [] for c in columns}
    brands: dict[str, dict] = {c: {} for c in columns}
    # 品牌中标题要挂官号主页链接：同一品牌在两栏各有一节，各算各的官号。
    brand_urls: dict[str, dict[str, str]] = {c: {} for c in columns}
    counts: dict[str, dict] = {c: {"sections": 0, "items": 0} for c in columns}

    def register(column: str, brand: str, gkey: str, glabel: str) -> list[dict]:
        if brand not in brands[column]:
            brands[column][brand] = {}
            brand_order[column].append(brand)
        if gkey not in brands[column][brand]:
            brands[column][brand][gkey] = {"label": glabel, "lines": []}
        return brands[column][brand][gkey]["lines"]

    def line(item: dict, column: str) -> dict:
        prefix = str(item.get("subject_prefix") or "")
        prefix_md = str(item.get("prefix_md") or prefix)
        official = bool(item.get("is_official"))
        # 新作是作品情报的子集，版式规则一律按作品情报读，不另立一套。
        rule_col = WORK if column == NEW else column
        # 转推条目里原作者名已写进正文时，用带链接的版本（可见文字不变）。
        sentence = str(item.get("sentence_md") or item["sentence"])
        if official and rule_col in fmt["official_no_prefix"]:
            # 官号自己发的条目：不写账号名/品牌名，只写正文。
            body = sentence
        elif official and rule_col in fmt["official_space_prefix"]:
            body = (prefix_md + " " if prefix_md else "") + sentence
        else:
            # 非官号 / 名单外 / manufacturer 转发的原作者：沿用「前缀：」，
            # 名单外前缀里带指向原推 URL 的 Markdown 链接。
            body = (prefix_md + "：" if prefix_md else "") + sentence
        return {"text": "- " + body, "official": official, "key": item["key"]}

    for key in decisions.get("section_order") or []:
        if key in ds:
            continue
        section = by_section.get(key)
        if not section:
            continue
        for item_key in (decisions.get("item_order") or {}).get(key) or []:
            item = items.get(item_key)
            if item_key in di or not item or not str(item.get("sentence") or "").strip():
                continue
            # 展示栏目已经算好（合并 + 新作上提），这里只做兜底。
            column = str(item.get("display_column")
                         or (WORK if section["column"] == MOVEMENT else section["column"]))
            if column not in columns:
                column = section["column"]
            target = register(column, section["label"], item["group_key"], item["group_label"])
            target.append(line(item, column))
            counts[column]["items"] += 1
            if section.get("brand_url") and not brand_urls[column].get(section["label"]):
                brand_urls[column][section["label"]] = section["brand_url"]

    # 第四栏「B站动态」：行已经由 weekly/bilibili.py 算好（含游戏级新作分流），
    # 这里只按 column 注册，Python 与筛选页内联 JS 都不再各自判断。B 站品牌
    # 中标题故意不带官号链接——它没有 X 官号，check 的链接白名单也不认。
    for row in data.get("bilibili_lines") or []:
        column = str(row.get("column") or "")
        key = str(row.get("key") or "")
        if key in di or column not in columns:
            continue
        target = register(column, str(row["brand"]), str(row["gkey"]), str(row["glabel"]))
        target.append({"text": str(row["text"]), "official": False, "key": key})
        counts[column]["items"] += 1

    for column in columns:
        counts[column]["sections"] = len(brand_order[column])
    return {"format": fmt, "columns": columns, "brand_order": brand_order,
            "brands": brands, "brand_urls": brand_urls, "counts": counts}


def brand_heading(brand: str, url: str = "") -> str:
    """品牌中标题：有官号就挂主页链接，没有就纯文本。

    2026-11-10 用户裁决：`### [品牌名](官方推特链接)`。链接是账号主页
    `x.com/<handle>`，不是某条推文——品牌是一个主体，不是一条内容。
    """
    if url:
        return "### [" + brand + "](" + url + ")"
    return "### " + brand


def render_markdown(data: dict, decisions: dict) -> str:
    """四层结构：`## 栏目` → `### 品牌` → `#### 游戏` → `- 小条目`。

    展示栏由 `DISPLAY_COLUMNS` 给（现为四栏）；全部走四层，没有铺平栏。
    空栏不输出：没有条目的栏目连 `## ` 标题都不写（2026-11-10 用户裁决）。
    必须与 `editor.py` 内联 JS 的 buildMarkdown 逐字节一致（check 会复核）。
    """
    c = collect(data, decisions)
    columns = c["columns"]
    brand_order, brands, counts = c["brand_order"], c["brands"], c["counts"]
    brand_urls = c["brand_urls"]
    lines = ["# " + data["title"], "", "> " + data["stage"]]
    if data.get("note"):
        lines.append("> " + data["note"])
    lines += ["", "**导语**：" + data["lead"], "", "---", ""]

    for column in columns:
        body: list[str] = []
        for brand in brand_order[column]:
            body += [brand_heading(brand, brand_urls[column].get(brand, "")), ""]
            for group in brands[column][brand].values():
                body += ["#### " + group["label"], ""]
                body += [x["text"] for x in _ordered(group["lines"], column, c["format"])] + [""]
        while body and body[-1] == "":
            body.pop()
        # 空栏整节省略：业界动向常常一条不剩，留个「（没有条目）」占位只是噪音。
        if body:
            lines += ["## " + column, ""] + body + [""]
    lines += [
        "---", "",
        "> 本稿由周报选材输出："
        + "；".join(column + " " + str(counts[column]["sections"]) + " 个品牌大单元 / "
                   + str(counts[column]["items"]) + " 条"
                   for column in columns if counts[column]["items"])
        + "。候选分句与出处链接在选材区的「源」里，不写进正文。",
        "> 工作台选材稿；四套筛选的证据见 material.md 与 evidence/。对外正本由 weekly publish 出到 data/weekly/。", "",
    ]
    return "\n".join(lines)


def build_editor_data(result: dict, title: str, lead: str) -> dict:
    from . import bilibili

    corpus = result["corpus"]
    highlights, interactions = build_feeds(result)
    snapshot = result["rules_snapshot"]
    return {
        "schema_version": 7,
        "generator": "weekly/editor/7",
        "id": title,
        "title": title,
        "lead": lead,
        "stage": "正式版 · 本地工作台输出；对外正本见 /weekly/。",
        "note": "栏目(大) → 品牌(中) → 游戏(小) → 短横线后的小条目。栏目＝新作 / 作品情报 / 业界动向 / B站动态：品牌动向并入作品情报，品牌级条目落在该品牌下的「品牌动向」小标题里；带新作标签的游戏整组提到第一栏；**某一栏没有条目就整节不输出**（业界动向常为空）。品牌中标题挂官号主页链接（`###` 后面的品牌名做成指向 `x.com/<handle>` 的链接），该品牌在这一栏没有官号条目时退回纯文本。官号条目只写正文、不写账号名或品牌名（品牌名已是中标题）。非官号保留「主语：」；名单外账号主语用 @handle 并挂原推链接；品牌号转发的条目署被转发账号的真实名称并挂原推链接（账号名已写进正文时，原地给那个名字挂链）。书名号：作品『』、角色「」、乐曲与书籍《》。生日词与「未标注作品」条目默认不入稿、可在筛选页点「恢复」；看点 / 互动栏目已删除。B 站动态是第二数据源，只读 `data/bilibili/galgame/<日>.jsonl`，不进 X 侧归栏；按同一份游戏级规则命中「新作」的组上提到第一栏，其余留在第四栏。",
        "columns": list(DISPLAY_COLUMNS),
        # B 站动态：第二数据源的展示行，游戏级「新作」过滤已算好并写进 column。
        # 筛选页内联 JS 只读不算，parity 才不会两边各判一遍。
        "bilibili_lines": bilibili.build_lines(corpus, snapshot),
        # 筛选页左侧按「归栏三值」分盒（那是证据），右侧出稿按 display_columns。
        "section_columns": list(COLUMNS),
        "format": display_format(snapshot),
        "switch_columns": list(snapshot.get("switch_columns") or []),
        "feed_fallback": dict(snapshot.get("feed_fallback") or {}),
        "group_column": {},
        "title_groups": result["evidence"]["title_groups"],
        "account_names": result["identity"].names,
        "sections": result["sections"],
        "highlights": highlights,
        "interactions": interactions,
        "repeats": [
            {"title": g["norm_text"][:40], "days": [g["display_published_at"][:10]],
             "keys": len(g["keys"])}
            for g in result["content_groups"] if g["duplicate"]
        ],
        "stats": result["stats"],
        "window": corpus["window"],
        "issues": corpus["issues"],
    }


def _source_line(src: dict) -> str:
    who = src["display_name"] or ("@" + src["handle"] if src["handle"] else "名单外")
    extra = f" · {src['class']}" + (" · 转发提升" if src["promoted"] else "")
    return (f"    - `{src['key']}` → {src['url'] or '（URL 未解析）'}"
            f"（{who} · @{src['handle']}{extra} · {src['published_at'] or '时间未知'}）"
            f"｜原文：{src['text'][:220] or '（无原文）'}")


def render_material(result: dict, data: dict) -> str:
    from . import bilibili

    corpus, stats = result["corpus"], result["stats"]
    lines = [
        "# 周报选材库 · " + data["title"],
        "",
        "> 工作台选材库 · 不发布；候选分句与情报源索引只在本地工作区可见，正文不外显链接。",
        "",
        "## 一、筛选链证据",
        "",
        f"- 窗口 {corpus['window']['start']} – {corpus['window']['end']}；"
        f"期号 {len(corpus['issues'])} 个：{', '.join(corpus['issues'])}。",
        f"- 仅正本散文（无 M1 索引）：{', '.join(corpus['prose_only_issues']) or '无'}。",
        f"- 原始记录 {stats['raw_records']} 条 → 去重后 {stats['after_dedupe']} 条；"
        f"原推内容组 {stats['content_groups']} 组，其中重复 {stats['duplicate_groups']} 组。",
        f"- 四类计数：{stats['classes']}；转发提升记录 {stats['promoted_records']} 条。",
        f"- 筛除池结论：{stats['verdicts']}。",
        f"- 三栏归栏：{stats['columns']}；大单元 {stats['sections']} / 小单元 {stats['items']}。",
        f"- `works[]` 无出处整行 {stats['prose_only_rows']} 条，未自动入稿（见第五节）。",
        "",
        "四类口径：manufacturer / info / creator / other（含名单外）；"
        "manufacturer 与 creator 转发的推文视同转发者类别；账号类只管准入，不参与归栏。",
        "",
        "## 二、三组选材（含全量源索引）",
        "",
    ]
    for section in data["sections"]:
        lines += [f"### [{section['column']}] {section['label']}", ""]
        for item in section["items"]:
            lines += [
                f"- **{item['label']}**：{item['sentence']}",
                f"  - 日期 {item['day']} · 类别 {item['account_class']} · "
                f"结论 {item['verdict']} · 归栏依据 {item['classify_reason']}",
            ]
            for cand in item["candidates"]:
                lines.append(f"  - 候选 `{cand['clause_id']}`（{cand['precision']}）：{cand['text']}"
                             f" ｜出处 {', '.join(cand['sources']) or '（无）'}")
            lines.append(f"  - 情报源索引（{len(item['sources'])} 条，去重后仍保留全部键）：")
            lines += [_source_line(src) for src in item["sources"]] or ["    - （无）"]
            lines.append("")
    lines += ["### 逐字取自日报的看点 / 互动（按内容归栏）", ""]
    for entry in data["highlights"] + data["interactions"]:
        lines += [
            f"- **{entry['day']}** → `{entry['column']}`（{entry['account_class']}）{entry['text']}",
            f"  - 情报源索引（{len(entry['sources'])} 条）：",
        ]
        lines += [_source_line(src) for src in entry["sources"]] or ["    - （无）"]
    lines += [
        "",
        "## 三、待人工候选池（review，未入稿）", "",
    ]
    review = [r for r in result["records"] if r["verdict"] == "review"]
    for rec in review:
        lines.append(f"- **{rec['day']}**（{rec['account_class']}）{rec['text']}"
                     f" ｜{rec['verdict_reason']} ｜出处 {', '.join(rec['sources']) or '（无）'}")
    if not review:
        lines.append("- （无）")
    lines += ["", "## 四、已剔除（drop）", ""]
    dropped = [r for r in result["records"] if r["verdict"] == "drop"]
    for rec in dropped:
        lines.append(f"- **{rec['day']}**（{rec['account_class']}）{rec['text']}"
                     f" ｜{rec['verdict_reason']}")
    if not dropped:
        lines.append("- （无）")
    lines += ["", "## 五、日报正本 works[] 整行（无出处，未自动入稿）", ""]
    for row in result["prose_only"]:
        lines.append(f"- **{row['day']}** {row['text']}")
    lines += ["", "## 六、全量源索引", ""]
    identity = result["identity"]
    for key, ref in sorted(corpus["source_refs"].items()):
        eff = identity.effective_handle(key, corpus["source_refs"])
        lines.append(
            f"- `{key}` → {ref.get('url') or '（URL 未解析）'}"
            f"（{identity.names.get(eff['handle'], '') or '名单外'} · @{eff['handle']}"
            f" · {eff['class']}" + (" · 转发提升" if eff["promoted"] else "") + "）"
            f" ｜{ref.get('published_at') or '时间未知'} ｜原文：{str(ref.get('text') or '')[:180]}"
        )
    lines += ["", "## 七、跨日重复扫描（只暴露，不自动合并）", ""]
    for group in result["content_groups"]:
        if group["duplicate"]:
            lines.append(f"- `{group['gid']}` {len(group['keys'])} 键；展示取最新 "
                         f"`{group['display_key']}`（{group['display_published_at']}）："
                         f"{group['norm_text'][:80]}")
    lines += ["", "## 八、作品名规整（缩写 / 全称 / 同系列）", ""]
    tg = result["evidence"]["title_groups"]
    lines.append(f"- 自动合并 {tg['merged_title_count']} 条别名 → 全称；"
                 f"4 字缩写候选 {len(tg['abbreviation_candidates'])} 组，"
                 f"5+ 字共同前缀系列 {len(tg['family_candidates'])} 组"
                 f"（`auto_merge_long_prefix={tg['auto_merge_long_prefix']}`）。")
    for m in tg["merges"]:
        lines.append(f"- `{m['alias']}` → `{m['canonical']}`（{m['reason']}）")
    for a in tg["abbreviation_candidates"]:
        lines.append(f"- 4 字候选 `{a['abbreviation']}`：已并 {a['merged'] or '无'}；"
                     f"未并 {a['unmerged'] or '无'}（{a['note']}）")
    for f in tg["family_candidates"]:
        lines.append(f"- 系列 `{f['family']}`：{'、'.join(f['titles'])}（{f['note']}）")
    lines += ["", "## 九、栏目强制词 / 生日词标注（优先于筛除池）", ""]
    for a in result["evidence"]["annotation"]:
        flags = []
        if a["forced_column"]:
            flags.append("强制归 " + a["forced_column"])
        if a["birthday"]:
            flags.append("生日默认不入初稿")
        lines.append(f"- **{a['rid']}** {' / '.join(flags)}：{a['text']}")
    if not result["evidence"]["annotation"]:
        lines.append("- （无）")
    lines.append("")
    lines += bilibili.material_lines(corpus)
    return "\n".join(lines)


def render_all(result: dict, out_dir) -> dict:
    from .config import EVIDENCE

    title = "Galgame 周报"
    lead = build_lead(result)
    data = build_editor_data(result, title, lead)
    decisions = default_decisions(data)
    draft = render_markdown(data, decisions)

    write_json(out_dir / "filter-data.json", data)
    write_json(out_dir / "decisions.json", decisions)
    write_text(out_dir / "draft.md", draft)
    write_text(out_dir / "draft-selected.md", draft)
    write_text(out_dir / "material.md", render_material(result, data))

    write_json(EVIDENCE / "identity.json", {
        "class_priority": list(result["rules_snapshot"]["class_priority"]),
        "promotion_classes": list(result["rules_snapshot"]["promotion_classes"]),
        "overrides": result["rules_snapshot"]["account_class_overrides"],
        "override_note": result["rules_snapshot"]["override_note"],
        "account_brands_size": len(result["identity"].brands),
        "account_names_size": len(result["identity"].names),
        "promotions": result["evidence"]["promotions"],
    })
    write_json(EVIDENCE / "dedupe.json", {
        "content_groups": result["content_groups"],
        "dropped_records": result["evidence"]["dedupe"],
    })
    write_json(EVIDENCE / "prefilter.json", result["evidence"]["prefilter"])
    write_json(EVIDENCE / "annotation.json", result["evidence"]["annotation"])
    write_json(EVIDENCE / "title-groups.json", result["evidence"]["title_groups"])
    write_json(EVIDENCE / "classification.json", result["evidence"]["classification"])
    write_json(EVIDENCE / "rules-snapshot.json", result["rules_snapshot"])
    write_json(out_dir / "records.json", [
        {k: v for k, v in r.items() if k != "identity"} | {"identity": r["identity"]}
        for r in result["records"]
    ])
    write_json(out_dir / "manifest.json", {
        "generator": GENERATOR, "title": title, "window": result["corpus"]["window"],
        "issues": result["corpus"]["issues"], "stats": result["stats"],
        "columns": list(DISPLAY_COLUMNS),
        "outputs": ["draft.md", "draft-selected.md", "material.md", "filter.html",
                    "image-preview.html", "image-preview-data.json",
                    "taxonomy-preview.html", "taxonomy-preview-data.json",
                    "game-routing-preview.html", "game-routing-preview-data.json",
                    "game-routing-draft.md",
                    "weekly.md", "weekly.html",
                    "media-sidecar.json", "images/",
                    "filter-data.json", "decisions.json", "records.json", "corpus.json",
                    "evidence/title-groups.json", "evidence/annotation.json"],
        "verdict_counts": dict(Counter(r["verdict"] for r in result["records"])),
    })
    return data
