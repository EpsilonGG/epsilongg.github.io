"""命令行入口。

    python -m weekly build              从 Galgame 全集重建语料、筛选、出稿（weekly.md / weekly.html）
    python -m weekly backfill-media     方案 C：回填候选源推的图片 URL 到 sidecar（联网）
    python -m weekly check              守恒 / 隔离 / 版式 / 事实 / 分流 / JS-Python parity
    python -m weekly check-site         发布正本 / 站点出口 / 内容闸门（CI 也跑这条）
    python -m weekly publish            出 data/weekly/<vol_XXX>/report.json（正式上线）
    python -m weekly apply-decisions    把 out/decisions.json 落成 draft-selected.md

出稿默认仍是「Galgame 日报全集」（本地回测）。按周出稿给 `build --last-days 7`，
窗口末端是 JST 昨天；`--since/--until` 可显式指定。
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import (COLUMNS, DISPLAY_COLUMNS, EVIDENCE, MOVEMENT, NEW, OUT,
                     PACKAGE, WORK, read_json, write_json, write_text, load_rules)
from . import (corpus, pipeline, render, editor, image_preview,
               media_backfill, taxonomy_preview, game_routing, draft_export,
               brackets, publish as weekly_publish)


def cmd_build(args) -> int:
    rules = load_rules()
    data_set = corpus.build(since=args.since, until=args.until,
                            last_days=args.last_days)
    write_json(OUT / "corpus.json", data_set)
    result = pipeline.run(data_set, rules)
    data = render.render_all(result, OUT)
    editor.render_html(data, OUT / "filter.html")
    preview = image_preview.build(rules)
    taxonomy = taxonomy_preview.build(rules)
    routing = game_routing.build(rules)
    s = result["stats"]
    print(f"build: {data['title']} → {OUT}")
    print(f"  窗口 {data_set['window']['start']} – {data_set['window']['end']} / "
          f"{len(data_set['issues'])} 期 / 源索引 {len(data_set['source_refs'])} 键")
    print(f"  记录 {s['raw_records']} → 去重 {s['after_dedupe']}；"
          f"结论 {s['verdicts']}；四类 {s['classes']}")
    print(f"  归栏 {s['columns']}；品牌中标题 {s['sections']} / 游戏小标题 {s['game_groups']} / "
          f"小条目 {s['items']} / 看点互动 {s['feed_items']}")
    print(f"  作品名合并 {s['title_merges']}；强制词 {s['forced_records']} 条"
          f"（让位 {s.get('forced_yielded', 0)} 条）；"
          f"生日词 {s['birthday_records']} 条 → 隐藏 {s.get('birthday_hidden', 0)} / "
          f"豁免 {s.get('birthday_exempt', 0)}；无主体观后感 {s.get('no_subject_records', 0)} 条")
    print(f"  内容组 {s['content_groups']}（重复 {s['duplicate_groups']}）；"
          f"转发提升 {s['promoted_records']} 条")
    ip = preview["stats"]
    print(f"  图片栏目（试验·独立 HTML）：带图推文 {ip['image_tweets']} "
          f"（抓取 {ip['crawl_image_tweets']} + sidecar {ip.get('backfill_tweets', 0)}）/ "
          f"进源索引 {ip['image_tweets_in_source_index']} / 合格条目 "
          f"{ip['qualified_items']} 条（{ip['qualified_images']} 张图，"
          f"省下多余图片 {ip.get('dropped_extra_images', 0)} 张）")
    ts = taxonomy["stats"]
    print(f"  分类预览（试验·独立 HTML·按条目，已废弃）：{len(taxonomy['items'])} 条 / "
          f"本体 {ts['scope'].get('core', 0)} · 周边 {ts['scope'].get('peripheral', 0)} · "
          f"未归类 {ts['scope'].get('unclassified', 0)}；"
          f"按条目算的 A 方案冲突 {ts['option_a']['conflict']} 条")
    rs = routing["stats"]
    print(f"  按游戏分流（试验·独立 HTML·本轮裁决）：{rs['games_total']} 游戏组 → "
          f"新作 {rs['games_labeled']} 组 / {rs['new_items_in_draft']} 条，"
          f"作品情报 {rs['games_rest']} 组 / {rs['work_items_in_draft']} 条；"
          f"跨两栏重复 {rs['split_items']} 条；自动建议 {rs['auto_suggested']} 组")
    drafts = draft_export.build(rules)
    ds = drafts["stats"]
    dropped = [c for c in DISPLAY_COLUMNS if c not in ds["order"]]
    print("  正式版："
          + " / ".join(c + " " + str(ds["columns"][c]["brands"]) + " 品牌 · "
                       + str(ds["columns"][c]["items"]) + " 条" for c in ds["order"])
          + (("；" + " / ".join(dropped) + " 空栏，整节不输出") if dropped else "")
          + f"；带图版插 {ds['images']} 张（每推首图）→ weekly.md / weekly.html")
    return 0


def cmd_backfill(args) -> int:
    """方案 C：只回填图片 URL，不改 X-Reader / 原始切片 / 日报管线。"""
    rules = load_rules()
    cfg = (rules.get("image_preview") or {}).get("media_backfill") or {}
    if not cfg.get("enabled", True):
        print("rules.json: image_preview.media_backfill.enabled = false，已跳过")
        return 0
    data = read_json(OUT / "filter-data.json")
    corpus_data = read_json(OUT / "corpus.json")
    crawl, _ = image_preview.load_media()
    scope = "all" if args.all else str(cfg.get("scope") or "candidates")
    sidecar, stats = media_backfill.backfill(
        rules, data, corpus_data, scope=scope, refresh=args.refresh,
        known=set(crawl), workers=args.workers)
    print(f"backfill-media: scope={scope} / 候选 {stats['candidate_keys']} 条 / "
          f"本次联网 {stats['probed_this_run']} 条 / sidecar 累计 "
          f"{stats['sidecar_entries']} 条（有图 {stats['sidecar_hits']} 条、"
          f"{stats['sidecar_images']} 张）/ 失败 {stats['probe_errors']} 条")
    print(f"  → {media_backfill.sidecar_path(rules)}")
    if args.no_preview:
        return 0
    preview = image_preview.build(rules)
    taxonomy_preview.build(rules)
    game_routing.build(rules)
    ip = preview["stats"]
    print(f"  预览重出：合格 {ip['qualified_items']} 条 / {ip['qualified_images']} 张图 "
          f"（回填来的 {ip.get('qualified_from_backfill', 0)} 条），缓存样图 "
          f"{ip.get('cached_images', 0)} 张")
    st = preview.get("storage") or {}
    for row in st.get("strategies") or []:
        n = row["bytes"]
        size = (f"{n / 1024 ** 3:.2f} GB" if n >= 1024 ** 3 else
                f"{n / 1024 ** 2:.2f} MB" if n >= 1024 ** 2 else
                f"{n / 1024:.1f} KB" if n >= 1024 else f"{n} B")
        print(f"  存储 · {row['name']}：{size} / 期")
    return 0


def _node() -> str:
    found = shutil.which("node")
    if found:
        return found
    for candidate in (r"C:\Program Files\nodejs\node.exe", "/c/Program Files/nodejs/node.exe"):
        if Path(candidate).is_file():
            return candidate
    return ""


def cmd_check(_args) -> int:
    problems: list[str] = []
    draft = (OUT / "draft.md").read_text(encoding="utf-8")
    corpus_data = read_json(OUT / "corpus.json")
    records = read_json(OUT / "records.json")
    data = read_json(OUT / "filter-data.json")
    manifest = read_json(OUT / "manifest.json")
    decisions = read_json(OUT / "decisions.json")

    # 空栏整节省略（2026-11-10 裁决）：某一栏一条都不剩就不写 `## ` 标题。
    # 所以这里先算出「这一期实际会有哪几栏」，再按它校验标题，而不是硬要求三栏。
    deleted_items = set(decisions.get("deleted_items") or [])
    deleted_sections = set(decisions.get("deleted_sections") or [])
    live_columns: dict[str, int] = {c: 0 for c in DISPLAY_COLUMNS}
    for section in data["sections"]:
        if section["key"] in deleted_sections:
            continue
        for item in section["items"]:
            if item["key"] in deleted_items or not str(item.get("sentence") or "").strip():
                continue
            column = str(item.get("display_column")
                         or (DISPLAY_COLUMNS[1] if section["column"] == MOVEMENT
                             else section["column"]))
            if column not in live_columns:
                column = section["column"]
            live_columns[column] += 1
    expect_columns = [c for c in DISPLAY_COLUMNS if live_columns[c]]

    positions = [draft.find("## " + c) for c in expect_columns]
    if not all(p >= 0 for p in positions) or positions != sorted(positions):
        problems.append("draft.md 栏目缺失或顺序不对：" + " → ".join(expect_columns))
    draft_headings = [line for line in draft.splitlines() if line.startswith("## ")]
    if len(draft_headings) != len(expect_columns):
        problems.append(f"draft.md 的 ## 栏数是 {len(draft_headings)}"
                        f"（应为 {len(expect_columns)}：{' / '.join(expect_columns)}）")
    empty_but_printed = [h for h in draft_headings if h[3:].strip() not in expect_columns]
    if empty_but_printed:
        problems.append("draft.md 输出了空栏：" + " / ".join(empty_but_printed))
    for banned in ("## 商业信息", "## 其它", "## 行业 / 动态"):
        if any(line.startswith(banned) for line in draft_headings):
            problems.append(f"draft.md 不该出现 {banned}")
    # 看点 / 互动（2026-11-10 正式版裁决）：栏目删除，出稿里一条都不许有。
    if any(h.startswith("## 看点") for h in draft_headings):
        problems.append("draft.md 仍输出了「看点 / 互动」栏目（正式版已删除）")
    # 外链白名单（2026-11-10）：只允许名单外账号前缀里的 Markdown 链接，
    # 且目标 URL 必须逐字来自 source_refs.url；裸 URL 一律拦下。
    allowed_urls = {str(v.get("url") or "") for v in corpus_data["source_refs"].values()
                    if v.get("url")}
    # 品牌中标题的官号主页链接（`https://x.com/<handle>`）不是推文、不在源索引里，
    # 但 handle 必须来自名单，所以按「名单 handle 拼出的主页 URL」单独放行。
    profile_urls = {str(s.get("brand_url") or "") for s in data["sections"]
                    if s.get("brand_url")}
    allowed_urls |= profile_urls
    link_re = re.compile(r"\]\((https?://[^)\s]+)\)")
    link_targets = link_re.findall(draft)
    bad_links = [u for u in link_targets if u not in allowed_urls]
    if bad_links:
        problems.append(f"draft.md 出现不在源索引里的链接：{bad_links[:3]}")
    bare = link_re.sub("](URL)", draft)
    if "https://" in bare or "http://" in bare:
        problems.append("draft.md 出现裸外链（只允许名单外前缀的 Markdown 链接）")
    leaked_keys = [k for k in corpus_data["source_refs"] if k in draft]
    if leaked_keys:
        problems.append(f"draft.md 漏出了出处键：{leaked_keys[:3]}")

    # 守恒：去重丢掉的记录 + 存活记录 = 原始记录；三种结论之和 = 存活记录。
    dedupe_ev = read_json(EVIDENCE / "dedupe.json")["dropped_records"]
    dropped = sum(len(x["dropped"]) for x in dedupe_ev)
    raw = manifest["stats"]["raw_records"]
    after = manifest["stats"]["after_dedupe"]
    if dropped + after != raw:
        problems.append(f"去重守恒失败：{raw} ≠ {after} + {dropped}")
    verdicts = manifest["stats"]["verdicts"]
    if sum(verdicts.values()) != after:
        problems.append(f"筛除池守恒失败：{verdicts} 之和 ≠ {after}")
    if len(records) != after:
        problems.append(f"records.json 条数 {len(records)} ≠ {after}")

    # 去重：重复组必须选到时间戳最新的键，且所有键都留在源索引里。
    groups = read_json(EVIDENCE / "dedupe.json")["content_groups"]
    refs = corpus_data["source_refs"]
    for group in groups:
        if not group["duplicate"]:
            continue
        newest = max(group["keys"], key=lambda k: (str((refs[k] or {}).get("published_at") or ""), k))
        if newest != group["display_key"]:
            problems.append(f"{group['gid']} 展示项不是最新：{group['display_key']} ≠ {newest}")
        material = (OUT / "material.md").read_text(encoding="utf-8")
        missing = [k for k in group["keys"] if f"`{k}`" not in material]
        if missing:
            problems.append(f"{group['gid']} 源索引漏键：{missing[:3]}")

    # 账号类不得出现在归栏依据里（两套判定正交）。
    classification = read_json(EVIDENCE / "classification.json")
    for row in classification:
        if any(f"class={c}" in row["reason"] for c in ("manufacturer", "info", "creator", "other")):
            problems.append(f"{row['rid']} 归栏依据混进了账号类")
            break

    # 三组键、section_order 与 item key 唯一。
    keys = [s["key"] for s in data["sections"]]
    if len(keys) != len(set(keys)):
        problems.append("大单元 key 不唯一")
    item_keys = [i["key"] for s in data["sections"] for i in s["items"]]
    if len(item_keys) != len(set(item_keys)):
        problems.append("小单元 key 不唯一")
    if set(s["column"] for s in data["sections"]) - set(COLUMNS):
        problems.append("出现三组之外的 column")

    # 四层结构 + 新规则：小标题 key 唯一、强制词 / 生日词 / 作品名规整证据齐全。
    rules_snapshot = read_json(EVIDENCE / "rules-snapshot.json")
    for entry in rules_snapshot.get("column_forced") or []:
        if entry.get("column") not in COLUMNS:
            problems.append(f"column_forced 出现三组之外的栏目：{entry.get('column')}")
    if set(rules_snapshot.get("switch_columns") or []) - set(COLUMNS):
        problems.append("switch_columns 出现三组之外的栏目")
    if "#### " not in draft:
        problems.append("draft.md 缺少游戏小标题（####）")
    group_set = {i["group_key"] for s in data["sections"] for i in s["items"]}
    bad_switch = {k: v for k, v in (decisions.get("group_column") or {}).items()
                  if k not in group_set or v not in COLUMNS}
    if bad_switch:
        problems.append(f"group_column 含无效键或栏目：{list(bad_switch)[:3]}")
    defaults = {i["key"] for s in data["sections"] for i in s["items"]
                if i.get("default_deleted")}
    defaults |= {h["key"] for h in (data.get("highlights") or []) if h.get("default_deleted")}
    defaults |= {x["key"] for x in (data.get("interactions") or []) if x.get("default_deleted")}
    all_deleted = set(decisions.get("deleted_items") or []) \
        | set(decisions.get("deleted_highlights") or []) \
        | set(decisions.get("deleted_interactions") or [])
    if defaults - all_deleted:
        problems.append(f"默认排除条目未勾删：{sorted(defaults - all_deleted)[:3]}")
    # 「未标注作品」条目必须全部默认不入初稿（仍在筛选页、可点恢复）。
    excl_cfg = rules_snapshot.get("default_excluded") or {}
    excluded_groups = set(excl_cfg.get("group_labels") or [])
    excl_columns = set(excl_cfg.get("columns") or [])
    unlabeled = {i["key"] for s in data["sections"] for i in s["items"]
                 if i["group_label"] in excluded_groups
                 and (not excl_columns or s["column"] in excl_columns)}
    if unlabeled - defaults:
        problems.append(f"「未标注作品」条目未默认排除：{sorted(unlabeled - defaults)[:3]}")
    # 小标题里的半角 ~ 必须走展示层拆对：group_label 等于 _display_title(原归一名)，
    # 归并键 work_canonical 保持不带空格的原名。避免 `『A~B~』` 被渲染成删除线。
    from .pipeline import _display_title
    for section in data["sections"]:
        for item in section["items"]:
            canonical = str(item.get("work_canonical") or "")
            if "~" in canonical and item.get("group_label") != f"『{_display_title(canonical)}』":
                problems.append(f"作品小标题未做 ~ 拆对：{item.get('group_label')}")
                break
        else:
            continue
        break
    for line in (x for x in draft.splitlines() if x.startswith("#### ")):
        # 危险形态：连续的 ~~，或 `~` 两侧都紧贴非空白（例如 `2~Egoism~`）。
        if "~~" in line or re.search(r"\S~\S", line):
            problems.append(f"作品小标题仍可能被渲染成删除线：{line[:60]}")
            break
    # 裸题名兜底必须真有发售信号，且不许命中「一天转介五条」这类汇整。
    bare_cfg = rules_snapshot.get("bare_title") or {}
    if bare_cfg.get("enabled"):
        bare_sig = [re.compile(p) for p in (bare_cfg.get("signals") or [])]
        bare_skip = [re.compile(p) for p in (bare_cfg.get("skip_if") or [])]
        for rec in records:
            if str(rec.get("work_basis") or "") != "bare+release":
                continue
            text = str(rec.get("text") or "")
            if not any(p.search(text) for p in bare_sig):
                problems.append(f"{rec.get('rid')} 裸题名命中但没有发售信号：{text[:50]}")
                break
            if any(p.search(text) for p in bare_skip):
                problems.append(f"{rec.get('rid')} 汇整条目被裸题名兜底命中：{text[:50]}")
                break
    # 书名号归一：作品『』/ 角色「」/ 乐曲书籍《》。归一函数是幂等的，
    # 所以「再跑一遍没有任何改动」＝初稿里已经没有该改的括号。
    bcfg = rules_snapshot.get("brackets") or {}
    titles = set(corpus_data.get("titles") or [])
    for line in draft.splitlines():
        if not line.startswith(("- ", "### ", "#### ")):
            continue
        fixed, changes = brackets.normalize(line, titles, bcfg)
        if changes:
            problems.append("初稿书名号未归一：" + str(changes[0])[:80])
            break
    if excluded_groups:
        leaked = [line for line in draft.splitlines()
                  if line.startswith("#### ") and any(g in line for g in excluded_groups)]
        if leaked:
            problems.append(f"初稿仍出现默认排除的小标题：{leaked[:2]}")
    # 「未标注作品」仍在筛选页 / 数据里，只是默认不入初稿。
    if not unlabeled:
        problems.append("筛选页里找不到「未标注作品」条目（应保留可恢复）")

    # 2026-11-10 三组新增默认排除：未标注品牌 / 生日豁免 / 无主体观后感。
    for brand in (excl_cfg.get("brands") or []):
        if any(l.strip() == "### " + brand for l in draft.splitlines()):
            problems.append(f"初稿仍出现默认排除的品牌中标题：{brand}")
    no_subject_cols = set((rules_snapshot.get("no_subject") or {}).get("apply_to") or ())
    for row in classification:
        # 豁免只能给「有实质内容」的生日条目；没有发售/更新/特典就不许豁免。
        if row.get("birthday_exempt") and not row.get("substantive"):
            problems.append(f"{row['rid']} 生日豁免缺少实质内容依据")
            break
    # 无主体观后感一旦命中，在生效栏目里必须默认勾删（留在筛选页可恢复）。
    ns_items = {i["key"] for s in data["sections"] for i in s["items"]
                if i.get("no_subject")
                and (not no_subject_cols or s["column"] in no_subject_cols)}
    if ns_items - defaults:
        problems.append(f"无主体观后感未默认排除：{sorted(ns_items - defaults)[:3]}")
    # 端到端：初稿的任何小条目都不许是「空话词命中且无实质内容」。
    ns_pat = [re.compile(p) for p in (rules_snapshot.get("no_subject") or {}).get("patterns") or []]
    sub_pat = [re.compile(p) for p in (rules_snapshot.get("substantive") or {}).get("patterns") or []]
    if ns_pat:
        for line in draft.splitlines():
            if not line.startswith("- "):
                continue
            body = line[2:]
            if any(p.search(body) for p in ns_pat) and not any(p.search(body) for p in sub_pat):
                problems.append(f"初稿仍出现无主体观后感：{body[:50]}")
                break

    # 账号原推链接：标签用真实名称（handle_style=name 时不许再是 @handle），
    # 且品牌号转发的条目必须挂链接、主语必须是被转发账号而不是品牌自己。
    style = str((rules_snapshot.get("off_roster_links") or {}).get("handle_style") or "name")
    acct_links = [(m.group(1).strip(), m.group(2))
                  for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", draft)]
    if not acct_links:
        problems.append("初稿里没有任何账号原推 Markdown 链接")
    for label, url in acct_links:
        if not label:
            problems.append(f"账号链接标签为空：{url}")
        elif style == "name" and label.startswith("@") \
                and not re.fullmatch(r"@[A-Za-z0-9_]{1,15}", label):
            problems.append(f"账号链接标签既不是真实名称、也不是 @handle：{label}")
        elif style == "at_handle" and not re.fullmatch(r"@[A-Za-z0-9_]+", label):
            problems.append(f"账号链接标签格式异常：{label}")
    for section in data["sections"]:
        for item in section["items"]:
            if item.get("default_deleted") or not item.get("retweeted"):
                continue
            # 链接要么挂在前缀上，要么由 sentence_md 把正文里的原作者名原地挂上。
            has_link = ("](" in str(item.get("prefix_md") or "")
                        or "](" in str(item.get("sentence_md") or ""))
            if not has_link:
                problems.append(f"{item['key']} 品牌号转发但没有原推链接")
                break
            if str(item.get("subject_prefix") or "") == str(section["label"]):
                problems.append(f"{item['key']} 转推主语仍是品牌自己：{section['label']}")
                break

    # 2026-11-10 用户裁决：账号标签是 `@handle`，handle 要按原样显示大小写。
    # 内部匹配一律小写（`airvelo2026`），但 X 上真实账号是 `AirVelo2026`；
    # 大小写只能从推文 URL 的路径段或 author 还原，忘了还原就会印成全小写。
    # 只拦「同一个 handle 的大小写写错」；label 是被转发者、URL 是转发者那条
    # 的 10 条属另一类（nitter 不给被转发者的 URL），不在这里判。
    for label, url_handle in re.findall(
            r"\[@([A-Za-z0-9_]+)\]\(https://x\.com/([A-Za-z0-9_]+)/status/", draft):
        if label.lower() == url_handle.lower() and label != url_handle:
            problems.append(f"账号标签大小写与链接不一致：@{label} ≠ {url_handle}")

    # 2026-11-10 用户裁决：主语是账号的条目，前缀一律得是 Markdown 链接。
    # 正文里出现裸 `@handle：` 就说明链接丢了（名单外退回 @handle 也一样要挂链）。
    bare_subject = re.compile(r"(?m)^- (@[^\s：]*)：")
    for hit in bare_subject.findall(draft):
        problems.append(f"draft.md 出现没有链接的账号主语：{hit}")
        break

    # 2026-11-10 用户裁决：品牌中标题要挂官号主页链接 `### [品牌名](https://x.com/handle)`。
    # 同一品牌在两栏各有一节，官号可能不同，所以按 label 收齐「这一品牌该挂的链接」，
    # 再逐条核对：有链接的必须落在允许集合里，没链接的必须确实没有官号条目。
    wanted: dict[str, set[str]] = {}
    for section in data["sections"]:
        label = str(section.get("label") or "")
        wanted.setdefault(label, set())
        if section.get("brand_url"):
            wanted[label].add(str(section["brand_url"]))
    for raw in re.findall(r"(?m)^### (.+)$", draft):
        match = re.fullmatch(r"\[(.+?)\]\((https?://[^)\s]+)\)", raw)
        if match:
            label, url = match.group(1), match.group(2)
            if not wanted.get(label):
                problems.append(f"{label} 没有官号条目却挂了链接：{url}")
            elif url not in wanted[label]:
                problems.append(f"{label} 的官号链接不对：{url}（应为 "
                                + " / ".join(sorted(wanted[label])) + "）")
        else:
            label = raw.strip()
            if wanted.get(label):
                problems.append(f"{label} 的中标题没挂官号链接（应为 "
                                + " / ".join(sorted(wanted[label])) + "）")

    # 试验性图片栏目必须是独立产物，绝不渗进初稿与筛选页。
    for name in ("image-preview.html", "image-preview-data.json"):
        if not (OUT / name).is_file():
            problems.append(f"缺少试验性产物 {name}")
    if (OUT / "image-preview-data.json").is_file():
        ip = read_json(OUT / "image-preview-data.json")
        if not ip.get("experimental") or ip.get("integrated_into_draft") \
                or ip.get("integrated_into_filter"):
            problems.append("image-preview-data.json 的隔离标记不对")
        tiers = set(ip["rule"]["tiers"])
        for row in ip["eligible"]:
            if row["tier"] not in tiers or not row["game"] or not row["images"]:
                problems.append(f"图片栏目出现不合格条目：{row['item_key']}")
                break
            if row.get("media_source") not in ("crawl", "backfill"):
                problems.append(f"图片栏目条目缺图片来源标记：{row['item_key']}")
                break
    # 2026-11-10：有图推文不论几张只取第一张；sidecar 原始数据不裁剪。
    if (OUT / "image-preview-data.json").is_file():
        ipd = read_json(OUT / "image-preview-data.json")
        if ipd["rule"].get("first_image_only"):
            bad = [r["item_key"] for r in ipd["eligible"]
                   if len(r["images"]) != 1 or len(r["photo_links"]) != 1]
            if bad:
                problems.append(f"未遵守每推只取第一张：{bad[:3]}")
            stray = [r["item_key"] for r in ipd["eligible"]
                     if any(not str(u).rstrip("/").endswith("/photo/1")
                            for u in r["photo_links"])]
            if stray:
                problems.append(f"图片入口不是 /photo/1：{stray[:3]}")
            if (OUT / "image-preview.html").is_file() and re.search(
                    r'href="[^"]*/photo/[2-9]',
                    (OUT / "image-preview.html").read_text(encoding="utf-8")):
                problems.append("image-preview.html 仍链到 /photo/2 及以上的图片")
            if ipd["stats"].get("dropped_extra_images", 0) < 0:
                problems.append("省下的多余图片数为负")
        # 分类预览：独立产物、条目守恒、类型键合法、绝不改出稿。
        for name in ("taxonomy-preview.html", "taxonomy-preview-data.json"):
            if not (OUT / name).is_file():
                problems.append(f"缺少试验性产物 {name}")
        if (OUT / "taxonomy-preview-data.json").is_file():
            tp = read_json(OUT / "taxonomy-preview-data.json")
            if not tp.get("experimental") or tp.get("integrated_into_draft") \
                    or tp.get("integrated_into_filter"):
                problems.append("taxonomy-preview-data.json 的隔离标记不对")
            expected_items = sum(len(s["items"]) for s in data["sections"])
            if len(tp["items"]) != expected_items:
                problems.append(f"分类预览条目 {len(tp['items'])} ≠ 筛选页 {expected_items}")
            valid = set(tp["orders"]["stages"]) | set(tp["orders"]["forms"])
            for row in tp["items"]:
                if set(row["stages"]) - valid or set(row["forms"]) - valid:
                    problems.append(f"分类预览出现词表外的类型键：{row['key']}")
                    break
    for name in ("draft.md", "draft-selected.md", "filter.html"):
        text = (OUT / name).read_text(encoding="utf-8")
        if "## 新作情报" in text or "## 周边信息" in text:
            problems.append(f"{name} 混进了试验性分类栏目")
    # 2026-11-10 正式版：新作是第一栏，品牌动向并入作品情报，不再有「品牌动向」栏。
    for name in ("draft.md", "draft-selected.md"):
        text = (OUT / name).read_text(encoding="utf-8")
        if re.search(r"(?m)^## 品牌动向\s*$", text):
            problems.append(f"{name} 仍有独立的「品牌动向」栏（应并入作品情报）")
        if not re.search(r"(?m)^## " + re.escape(DISPLAY_COLUMNS[0]) + r"\s*$", text):
            problems.append(f"{name} 缺少第一栏「{DISPLAY_COLUMNS[0]}」")
    # 方案 D：按「游戏」分流，分流单位不是小条目。构造上必须零跨栏重复。
    for name in ("game-routing-preview.html", "game-routing-preview-data.json",
                 "game-routing-draft.md"):
        if not (OUT / name).is_file():
            problems.append(f"缺少试验性产物 {name}")
    if (OUT / "game-routing-preview-data.json").is_file():
        gr = read_json(OUT / "game-routing-preview-data.json")
        if not gr.get("experimental") or gr.get("integrated_into_draft") \
                or gr.get("integrated_into_filter"):
            problems.append("game-routing-preview-data.json 的隔离标记不对")
        gs = gr["stats"]
        if gs["split_items"] != 0:
            problems.append(f"按游戏分流出现跨两栏重复条目：{gs['split_items']}")
        if gs["games_labeled"] + gs["games_rest"] != gs["games_total"]:
            problems.append("按游戏分流的游戏组不守恒")
        if gs["new_items"] + gs["work_items"] != gs["items_total"]:
            problems.append("按游戏分流的条目不守恒")
        keys = [r["key"] for g in gr["games"] for r in g["items"]]
        if len(keys) != len(set(keys)):
            problems.append("按游戏分流把同一个条目算了两次")
        for g in gr["games"]:
            if g["game"] == game_routing.NO_GAME and g["labeled"]:
                problems.append("「未标注作品」被当成新作游戏")
            if not g["items"]:
                problems.append(f"空游戏组：{g['game']}")
        live_keys = {i["key"] for s in data["sections"] if s["column"] == COLUMNS[0]
                     for i in s["items"]}
        if set(keys) != live_keys:
            problems.append("按游戏分流的条目集合 ≠ 作品情报条目集合")
    for name in ("draft.md", "draft-selected.md", "filter.html"):
        text = (OUT / name).read_text(encoding="utf-8")
        if re.search(r"(?m)^#{2,3}\s*新作情报", text):
            problems.append(f"{name} 混进了试验性「新作情报」栏")
    # 正式版两件产物：weekly.md 与 draft.md 逐字节一致；weekly.html 必须有首图、
    # 三栏顺序与正文一致、插图片不改变条目数。
    for name in ("weekly.md", "weekly.html"):
        if not (OUT / name).is_file():
            problems.append(f"缺少正式版产物 {name}")
    wm, wh = OUT / "weekly.md", OUT / "weekly.html"
    if wm.is_file():
        plain = wm.read_text(encoding="utf-8")
        if plain != draft:
            problems.append("weekly.md 与 draft.md 不一致（正式版正文必须逐字节相同）")
        if "![首图]" in plain or "pbs.twimg.com" in plain:
            problems.append("weekly.md 混进了图片（正文版不带图）")
    if wh.is_file():
        imaged = wh.read_text(encoding="utf-8")
        if "首图" not in imaged or "/photo/1" not in imaged:
            problems.append("weekly.html 没有首图或没有 /photo/1 入口")
        if re.search(r'href="[^"]*/photo/[2-9]', imaged):
            problems.append("weekly.html 仍链到 /photo/2 及以上的图片")
        # 2026-11-11 上线闸门：首图是外站热链，碎图必须能退化成纯文字。
        img_tags = re.findall(r"<img\b[^>]*>", imaged)
        if not img_tags or any("onerror=" not in tag for tag in img_tags):
            problems.append(f"weekly.html 的 {len(img_tags)} 张 <img> 有缺少 onerror 兜底的")
        for column in expect_columns:
            if f">{column}</h2>" not in imaged:
                problems.append(f"weekly.html 缺少栏目「{column}」")
        for column in DISPLAY_COLUMNS:
            if column not in expect_columns and f">{column}</h2>" in imaged:
                problems.append(f"weekly.html 输出了空栏「{column}」")
        pos = [imaged.find(">" + c + "</h2>") for c in expect_columns]
        if all(p >= 0 for p in pos) and pos != sorted(pos):
            problems.append("weekly.html 栏目顺序不对：" + " → ".join(expect_columns))
        if imaged.count("<li>") < len(re.findall(r"(?m)^- ", draft)):
            problems.append("weekly.html 的小条目数少于 draft.md")
    # 方案 C 的 sidecar 是**跨周复用的全局缓存**（`scope: candidates` 只说明它是
    # 给候选源推查的，不代表只服务当前窗口）。按 7 天窗口出稿时，缓存里留着上周
    # 的键是正常的；真正要防的是「给源索引里不存在的推文插图」——所以校验落在
    # **本轮真正拿去插图的那批候选**上，而不是整个缓存。
    ip_path = OUT / "image-preview-data.json"
    if ip_path.is_file():
        ip = read_json(ip_path)
        # 候选行的 `item_key` 是作品行键（`w:品牌::日::hash`），配图真正的来源是
        # `tweet_key`（`x:<推文 id>`）；要验的是后者在不在源索引里。
        used = {str(r.get("tweet_key") or "") for r in (ip.get("eligible") or [])}
        invented = {k for k in used if k and k not in corpus_data["source_refs"]}
        if invented:
            problems.append(f"图片候选出现源索引外的键：{sorted(invented)[:3]}")
    for name in ("draft.md", "draft-selected.md", "filter.html"):
        text = (OUT / name).read_text(encoding="utf-8")
        if "/photo/1" in text or "pbs.twimg.com" in text:
            problems.append(f"{name} 混进了试验性图片栏目内容")
    for row in classification:
        if not row.get("forced_column") or row["column"] == row["forced_column"]:
            continue
        # 强制词让位（2026-11-10）：只允许「发售信号更靠前」时退回内容判定栏，
        # 且只能退回 base_column，不许借让位之名跑到第三栏。
        if row.get("forced_yielded") and row["column"] == row.get("column_base"):
            continue
        problems.append(f"{row['rid']} 栏目强制词未生效：{row['column']} ≠ {row['forced_column']}")
        break
    from .titles import normalize
    title_groups = read_json(EVIDENCE / "title-groups.json")
    blocked = set(title_groups.get("no_auto_merge") or [])
    for merge in title_groups.get("merges") or []:
        if normalize(merge["alias"]) in blocked and merge["reason"] != "explicit_alias":
            problems.append(f"作品名误并了 no_auto_merge 例外：{merge['alias']}")

    # 2026-11-10 正式版版式：三栏都走四层（没有铺平栏）；官号条目只写正文。
    fmt = data.get("format") or {}
    flat_cols = set(fmt.get("flat") or [])
    no_prefix = set(fmt.get("official_no_prefix") or [])
    space_prefix = set(fmt.get("official_space_prefix") or [])
    if flat_cols:
        problems.append(f"正式版不应再有铺平栏：{sorted(flat_cols)}")
    by_col: dict[str, str] = {}
    for column in expect_columns:
        head = "## " + column
        start = draft.find(head)
        if start < 0:
            continue
        nxt = draft.find("\n## ", start + len(head))
        by_col[column] = draft[start:(nxt if nxt >= 0 else len(draft))]
    for column in expect_columns:
        block = by_col.get(column, "")
        if block and "#### " not in block:
            problems.append(f"{column} 没有输出游戏小标题（####）")

    c = render.collect(data, decisions)
    item_by_key = {i["key"]: i for s in data["sections"] for i in s["items"]}
    official_lines: set[str] = set()
    plain_lines: set[str] = set()
    for column in DISPLAY_COLUMNS:
        for groups in c["brands"][column].values():
            for group in groups.values():
                for ln in group["lines"]:
                    (official_lines if ln["official"] else plain_lines).add(ln["text"])
                    item = item_by_key.get(ln["key"])
                    if not item:
                        continue  # 看点 / 互动的逐字行块
                    # 名单外前缀在初稿里是 Markdown 链接，校验期望值必须用 prefix_md；
                    # 转推条目原作者名已写进正文时，正文用的是 sentence_md（带链接）。
                    prefix = str(item.get("prefix_md") or item.get("subject_prefix") or "")
                    sentence = str(item.get("sentence_md") or item["sentence"])
                    # 新作是作品情报的子集，版式规则按作品情报读（与 render.line 同口径）。
                    rule_col = WORK if column == NEW else column
                    if ln["official"] and rule_col in no_prefix:
                        expected = "- " + sentence
                    elif ln["official"] and rule_col in space_prefix:
                        expected = "- " + ((prefix + " ") if prefix else "") + sentence
                    else:
                        expected = "- " + ((prefix + "：") if prefix else "") + sentence
                    if ln["text"] != expected:
                        problems.append(f"{column} 条目版式不符：{ln['text'][:60]} ≠ {expected[:60]}")
                        break

    for column in (fmt.get("official_first") or []):
        block = by_col.get(column) or ""
        for brand in c["brand_order"].get(column, []):
            bstart = block.find("### " + brand + "\n")
            if bstart < 0:
                continue
            nxt = block.find("\n### ", bstart + 1)
            seg = block[bstart:(nxt if nxt >= 0 else len(block))]
            segments = [seg] if column in flat_cols else re.split(r"(?m)^#### .*$", seg)[1:]
            for piece in segments:
                seen_plain = False
                for line in (x for x in piece.splitlines() if x.startswith("- ")):
                    is_off = line in official_lines and line not in plain_lines
                    is_plain = line in plain_lines and line not in official_lines
                    if is_plain:
                        seen_plain = True
                    elif is_off and seen_plain:
                        problems.append(f"{column}/{brand} 官号条目未前置")
                        break

    # JS buildMarkdown 与 Python 逐字节一致。
    node = _node()
    if not node:
        problems.append("找不到 node，跳过 parity（需 Node 24）")
    else:
        proc = subprocess.run(
            [node, str(PACKAGE / "parity.js"), str(OUT)],
            capture_output=True, text=True, encoding="utf-8",
        )
        if proc.returncode != 0:
            problems.append(f"parity 执行失败：{proc.stderr.strip()[:200]}")
        else:
            expected = (OUT / "draft-selected.md").read_text(encoding="utf-8")
            if proc.stdout != expected:
                problems.append("筛选页 buildMarkdown 与 Python 输出不一致")
                a, b = proc.stdout.splitlines(), expected.splitlines()
                for i, (x, y) in enumerate(zip(a, b), start=1):
                    if x != y:
                        problems.append(f"  首处差异第 {i} 行：JS={x[:80]!r} PY={y[:80]!r}")
                        break

    if problems:
        print("check: FAILED")
        for problem in problems:
            print("  - " + problem)
        return 1
    print("check: OK · 守恒 / 隔离 / 版式 / 事实 / 分流 / JS-Python parity 全通过")
    print("  守恒：去重与筛除池、key 唯一、栏目取值合法、品牌中标题 / 游戏小标题 / 小条目计数")
    print("  隔离：试验性栏目（图片 / 分类 / 分流）不进正文、媒体键不越源索引、正文无出处键与裸外链")
    print("  版式：栏目顺序与栏数（空栏整节不输出）、无看点与独立品牌动向栏、铺平栏为空、"
          "每栏 ####、官号前置、品牌中标题必挂官号链接、账号主语必带链接（无裸 @handle）、"
          "账号标签大小写与链接一致、"
          "书名号归一、~ 拆对、@handle 兜底、weekly.md = draft.md、weekly.html 首图与栏目顺序")
    print("  事实：源索引全留且最新、归栏正交、强制词（含让位）、生日词与豁免、"
          "未标注作品默认排除、无主体观后感、转推挂原推链接、裸题名需发售信号")
    print("  分流：新作 ⊂ 作品情报、跨栏重复 0、未标注不当新作、空游戏组、切栏决策为空")
    print(f"  {manifest['stats']['sections']} 品牌中标题 / {manifest['stats']['game_groups']} 游戏小标题 / "
          f"{manifest['stats']['items']} 小条目 / {len(corpus_data['issues'])} 期 / "
          f"{len(corpus_data['source_refs'])} 源键")
    return 0


def cmd_apply(_args) -> int:
    data = read_json(OUT / "filter-data.json")
    decisions = read_json(OUT / "decisions.json")
    text = render.render_markdown(data, decisions)
    write_text(OUT / "draft-selected.md", text)
    print(f"apply-decisions: 已写 {OUT / 'draft-selected.md'}（{len(text.splitlines())} 行）")
    return 0


def cmd_drafts(_args) -> int:
    """只重出正式版两件产物（只读 draft.md，不动其它正式产物）。"""
    res = draft_export.build(load_rules())
    s = res["stats"]
    print("drafts: "
          + " / ".join(c + " " + str(v["items"]) + " 条" for c, v in s["columns"].items())
          + f"；带图版插 {s['images']} 张（每推首图）")
    for name in res["outputs"]:
        print(f"  → {OUT / name}")
    return 0


def cmd_publish(args) -> int:
    """出一份站点正本。发布前先跑一次 check-site 的「正本自检」由 publish 自己保证。"""
    res = weekly_publish.publish(load_rules(), published_at=args.issued_at,
                                 issue_id=args.issue, dry_run=args.dry_run,
                                 force=args.force)
    if res.get("skipped"):
        print(f"skip: {res['reason']}")
        return 0
    r = res["report"]
    tag = "[dry-run] " if res["dry_run"] else ""
    print(f"{tag}publish: {res['issue_id']} → {res['path']}")
    print(f"  窗口 {r['issue']['window']['start']} – {r['issue']['window']['end']} / "
          f"来源 {r['stats']['source_issues']} 期日报 / "
          f"{r['stats']['brands']} 品牌 · {r['stats']['items']} 条 · "
          f"{r['stats']['images']} 张首图")
    print("  栏目 " + " / ".join(c["label"] + " " + str(c["items"]) + " 条"
                                for c in r["columns"]))
    print(f"  策略 新作标签={r['policy']['new_work_label_source']} · "
          f"人工确认={r['policy']['decisions_human_confirmed']} · "
          f"未上线栏目={'、'.join(r['policy']['disabled_display_columns']) or '无'}")
    return 0


def cmd_check_site(_args) -> int:
    """发布出口闸门。与 CI 的 `npm run check:weekly` 是同一条命令。"""
    script = PACKAGE.parent / "scripts" / "check_weekly_publish.py"
    return subprocess.call([sys.executable, str(script)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weekly", description="Galgame 周报正式版：四类筛选 / 三栏展示 / 带图 HTML")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="从 Galgame 日报重建并出稿（不联网）")
    b.add_argument("--since", help="窗口起始日 YYYY-MM-DD（含）")
    b.add_argument("--until", help="窗口结束日 YYYY-MM-DD（含）")
    b.add_argument("--last-days", type=int, default=None,
                   help="取 JST 昨天往前 N 个自然日（每周六出稿用 7）")
    b.set_defaults(func=cmd_build)
    bf = sub.add_parser("backfill-media", help="方案 C：回填候选源推的图片 URL 到 sidecar")
    bf.add_argument("--all", action="store_true", help="扩到全部 source_refs（默认只查候选）")
    bf.add_argument("--refresh", action="store_true", help="已查过的键也重新联网")
    bf.add_argument("--workers", type=int, default=0, help="并发数（0＝用 rules.json）")
    bf.add_argument("--no-preview", action="store_true", help="只写 sidecar，不重出预览")
    bf.set_defaults(func=cmd_backfill)
    sub.add_parser("check", help="守恒与一致性校验").set_defaults(func=cmd_check)
    sub.add_parser("check-site", help="发布正本 / 站点出口 / 内容闸门").set_defaults(func=cmd_check_site)
    pub = sub.add_parser("publish", help="出 data/weekly/<vol_XXX>/report.json（正式上线）")
    pub.add_argument("--issue", help="指定期号 vol_XXX；不给则自动续号")
    pub.add_argument("--issued-at", help="发布时间 ISO 8601；不给则用当前 UTC 时刻")
    pub.add_argument("--force", action="store_true",
                     help="窗口没前进也强制出一期（默认跳过，避免重复稿）")
    pub.add_argument("--dry-run", action="store_true", help="只算不写")
    pub.set_defaults(func=cmd_publish)
    sub.add_parser("apply-decisions", help="把 decisions.json 落成筛选稿").set_defaults(func=cmd_apply)
    sub.add_parser("drafts", help="出无图 / 有图两版周报试稿").set_defaults(func=cmd_drafts)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
