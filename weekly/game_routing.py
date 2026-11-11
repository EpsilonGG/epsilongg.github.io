"""试验性：按「游戏」分流的预览（方案 D），独立 HTML，不进初稿 / 筛选页。

2026-11-10 用户裁决：
* 「新作」是「作品」的子集；先做完「作品情报」（按游戏分组），再把**含新作标签
  的游戏整组**拉到「新作」栏，组内全部条目一起走，绝不分到两个栏。
* 分流单位是游戏，不是小条目。所以上一版按小条目算出的「A 方案冲突 24 条」
  是伪命题：游戏级路由下不存在同一条消息两边都放。
* 小条目的 stage / form 关键词标签**不参与归栏**。『クナド国記』OP・ED 主题歌
  正在配信，只因命中「配信」就被打成 `stage=release`（游戏发售），正是反例。

本模块只读 `filter-data.json` / `decisions.json` / `taxonomy` 词表，只写
`out/game-routing-preview.{html,json}` + `out/game-routing-draft.md`；
不改 draft.md / draft-selected.md / filter.html / decisions.json / records.json。
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .config import OUT, WORK, read_json, write_json, write_text

GENERATOR = "weekly/game-routing/1"
NO_GAME = "未标注作品"

_CSS = """
:root{--bg:#fafafa;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e3e5e9;--blue:#1d4ed8;--green:#065f46}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:28px 20px 80px}
header{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:18px}
h1{font-size:24px;margin:0 0 6px}h2{font-size:17px;margin:32px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:14px;margin:16px 0 8px}
.sub{color:var(--muted);font-size:12px}
.badge{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;color:var(--muted);margin:8px 6px 0 0}
.badge.warn{border-color:#9ca3af;color:#374151;background:#f6f7f9}
.note{border-left:3px solid #9ca3af;padding:9px 12px;background:#f6f7f9;border-radius:0 6px 6px 0;font-size:13px;color:#374151;margin:12px 0}
.note b{color:var(--ink)}
.note.good{border-left-color:#10b981;background:#f0fdf6}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.stat{border:1px solid var(--line);border-radius:6px;background:#fff;padding:8px 12px;min-width:120px}
.stat b{display:block;font-size:20px;line-height:1.3}.stat span{font-size:11px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:12px;background:#fff;margin:8px 0}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;word-break:break-word}
th{background:#f6f7f9;font-weight:600}td.num,th.num{text-align:right;white-space:nowrap}
code{background:#f1f2f4;border-radius:4px;padding:1px 5px;font-size:12px}
.tg{display:inline-block;font-size:10px;border-radius:4px;padding:1px 5px;margin:0 3px 2px 0;border:1px solid var(--line);white-space:nowrap}
.tg.sig{background:#eff6ff;border-color:#bfdbfe;color:#1e40af}
.tg.bad{background:#fef2f2;border-color:#fecaca;color:#991b1b}
.tg.ok{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
.lab{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;align-items:start}
.pane{border:1px solid var(--line);border-radius:6px;background:#fff;padding:12px}
.games{max-height:620px;overflow:auto;border:1px solid var(--line);border-radius:6px;background:#fff}
.g{padding:7px 10px;border-bottom:1px solid var(--line);font-size:12px;display:flex;gap:8px;align-items:flex-start}
.g:last-child{border-bottom:0}.g.on{background:#f0fdf6}.g.case{background:#fffbeb}
.g label{flex:1;cursor:pointer;min-width:0}.g .nm{font-weight:600;word-break:break-all}
.g .mt{color:var(--muted);font-size:11px}.g input{margin-top:4px}
.bar{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.bar button,.bar a{border:1px solid var(--line);background:#fff;border-radius:6px;padding:5px 10px;font-size:12px;cursor:pointer;color:var(--ink);text-decoration:none}
.bar button.on{background:#111827;color:#fff;border-color:#111827}
.md{font:12px/1.85 ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-word;background:#f6f7f9;border:1px solid var(--line);border-radius:6px;padding:10px;margin:0;max-height:560px;overflow:auto}
.md .h2{color:#1e40af;font-weight:700}
.row{border:1px solid var(--line);border-radius:6px;background:#fff;padding:8px 10px;margin:6px 0;font-size:12px}
.row .txt{font-size:13px}.row .meta{font-size:11px;color:var(--muted);margin-top:3px}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:26px}
@media(max-width:980px){.lab{grid-template-columns:1fr}}
"""


def _esc(x: object) -> str:
    return html.escape(str(x if x is not None else ""))


def _compile(cfg: dict) -> tuple[list[tuple[str, re.Pattern]], re.Pattern]:
    pos = [(str(k), re.compile(str(v), re.I)) for k, v in (cfg.get("signals") or {}).items()]
    return pos, re.compile(str(cfg.get("negative") or "(?!)"), re.I)


def _line(item: dict, fmt: dict) -> str:
    """与 render.line() 同口径：新作是作品情报的子集，沿用作品情报的前缀规则。"""
    prefix = str(item.get("prefix_md") or item.get("subject_prefix") or "")
    official = bool(item.get("is_official"))
    sentence = str(item.get("sentence") or "")
    if official and WORK in fmt.get("official_no_prefix", []):
        body = sentence
    elif official and WORK in fmt.get("official_space_prefix", []):
        body = (prefix + " " if prefix else "") + sentence
    else:
        body = (prefix + "：" if prefix else "") + sentence
    return "- " + body


def new_work_labels(sections: list[dict], cfg: dict) -> set[str]:
    """哪些游戏带「新作」标签——出稿分流与分流预览共用这一份口径。

    单位是**游戏**（`group_label`），不是小条目：一个游戏一旦带标签，它的全部
    条目一起走，所以「同一条消息两边都放」在构造上不可能发生。
    标签来源按 `rules.json:game_routing.label_source`：
    `auto_suggestion`（默认，关键词信号）/ `manual`（只认人工清单）。
    """
    pos, neg = _compile(cfg)
    apply_to = cfg.get("apply_to") or [WORK]
    by_game: dict[str, list[dict]] = defaultdict(list)
    for sec in sections:
        if sec["column"] not in apply_to:
            continue
        for item in sec["items"]:
            by_game[str(item.get("group_label") or NO_GAME)].append(item)

    manual = set(cfg.get("new_work_games") or [])
    never = set(cfg.get("never_new_work_games") or [])
    source = str(cfg.get("label_source") or "auto_suggestion")
    labels: set[str] = set()
    for game, rows in by_game.items():
        if game == NO_GAME or game in never:
            continue
        if source == "manual":
            suggested = False
        else:
            suggested = False
            for r in rows:
                sentence = str(r.get("sentence") or "")
                if neg.search(sentence):
                    continue
                if any(rex.search(sentence) for _, rex in pos):
                    suggested = True
                    break
        if game in manual or suggested:
            labels.add(game)
    return labels


def build_preview(rules: dict) -> dict:
    cfg = rules["game_routing"]
    pos, neg = _compile(cfg)
    data = read_json(OUT / "filter-data.json")
    decisions = read_json(OUT / "decisions.json")
    deleted = set(decisions.get("deleted_items") or [])
    fmt = data.get("format") or {}

    by_game: dict[str, list[dict]] = defaultdict(list)
    for sec in data["sections"]:
        if sec["column"] not in (cfg.get("apply_to") or [WORK]):
            continue
        for it in sec["items"]:
            game = str(it.get("group_label") or NO_GAME)
            by_game[game].append({
                "key": it["key"], "brand": sec["label"], "game": game,
                "sentence": str(it.get("sentence") or ""),
                "prefix": str(it.get("prefix_md") or it.get("subject_prefix") or ""),
                "official": bool(it.get("is_official")),
                "in_draft": it["key"] not in deleted and not it.get("default_deleted"),
                "day": str(it.get("day") or ""),
                "line": _line(it, fmt),
            })

    manual = set(cfg.get("new_work_games") or [])
    never = set(cfg.get("never_new_work_games") or [])
    source = str(cfg.get("label_source") or "auto_suggestion")
    case = str(cfg.get("case_study") or "")
    # 与出稿分流共用同一份判定，避免预览和初稿各算一遍。
    labels = new_work_labels(data["sections"], cfg)

    games: list[dict] = []
    for game, rows in sorted(by_game.items(), key=lambda x: (-len(x[1]), x[0])):
        evidence: list[dict] = []
        signals: list[str] = []
        for r in rows:
            hit = [name for name, rex in pos if rex.search(r["sentence"])]
            if hit and not neg.search(r["sentence"]):
                evidence.append({"sentence": r["sentence"], "signals": hit,
                                 "day": r["day"]})
                signals.extend(hit)
        signals = sorted(set(signals))
        if game in never or game == NO_GAME:
            suggested = False
        elif source == "manual":
            suggested = game in manual
        else:
            suggested = bool(signals)
        labeled = game in labels
        games.append({
            "game": game, "brand": rows[0]["brand"],
            "items": rows, "item_count": len(rows),
            "draft_count": sum(1 for r in rows if r["in_draft"]),
            "signals": signals, "evidence": evidence,
            "suggested": suggested, "labeled": labeled,
            "label_source": ("人工清单" if game in manual else
                             "强制排除" if game in never or game == NO_GAME else
                             "自动建议" if suggested else "—"),
            "is_case": bool(case and case in game),
        })

    labeled = [g for g in games if g["labeled"]]
    rest = [g for g in games if not g["labeled"]]
    split = 0  # 游戏整组路由，按构造恒为 0；下面仍逐条复核
    seen: dict[str, str] = {}
    for g in games:
        col = cfg["new_column"] if g["labeled"] else WORK
        for r in g["items"]:
            if r["key"] in seen and seen[r["key"]] != col:
                split += 1
            seen[r["key"]] = col

    # 反例：按小条目打标签会错在哪（真实条目 + 真实命中词）
    tax = read_json(OUT / "taxonomy-preview-data.json")
    by_key = {i["key"]: i for i in tax["items"]}
    misfire_marks = ("クナド国記", "抱枕套", "转 CLOWN 新作", "15 周年", "新作《異世界孕ませ")
    misfires: list[dict] = []
    for g in games:
        for r in g["items"]:
            t = by_key.get(r["key"])
            if not t or not any(m in r["sentence"] for m in misfire_marks):
                continue
            misfires.append({
                "game": g["game"], "sentence": r["sentence"],
                "stages": t["stages"], "forms": t["forms"],
                "scope": t["scope"],
                "evidence": [f"{e['key']}←{e['match']}" for e in t["evidence"]],
                "routed_to": cfg["new_column"] if g["labeled"] else WORK,
                "game_labeled": g["labeled"],
            })

    # 自动建议的已知误差：关键词只作起步，必须让人看得见哪里不靠谱。
    weak = {"预约", "定档", "店铺特典", "临发售"}
    known: dict[str, list[dict]] = {
        "missed_explicit_new": [], "weak_only": [], "negative_hits": []}
    for g in games:
        surface = " ".join(r["sentence"] for r in g["items"])
        brief = {"game": g["game"], "items": g["item_count"],
                 "signals": g["signals"],
                 "sample": next((r["sentence"] for r in g["items"]
                                 if "新作" in r["sentence"]),
                                g["items"][0]["sentence"])}
        if not g["labeled"] and "新作" in surface:
            known["missed_explicit_new"].append(brief)
        if g["labeled"] and len(g["signals"]) == 1 \
                and g["signals"][0] in weak and g["item_count"] <= 2:
            known["weak_only"].append(brief)
        if g["labeled"] and re.search(r"\d+\s*周年|旧作|往年|复刻", surface):
            known["negative_hits"].append(brief)

    stats = {
        "games_total": len(games),
        "games_labeled": len(labeled),
        "games_rest": len(rest),
        "items_total": sum(g["item_count"] for g in games),
        "items_in_draft": sum(g["draft_count"] for g in games),
        "new_items": sum(g["item_count"] for g in labeled),
        "new_items_in_draft": sum(g["draft_count"] for g in labeled),
        "work_items": sum(g["item_count"] for g in rest),
        "work_items_in_draft": sum(g["draft_count"] for g in rest),
        "split_items": split,
        "auto_suggested": sum(1 for g in games if g["suggested"]),
        "manual_forced": len(manual & {g["game"] for g in games}),
        "case_labeled": any(g["labeled"] for g in games if g["is_case"]),
        "misfires": len(misfires),
    }
    return {
        "schema_version": 1, "generator": GENERATOR,
        "experimental": True,
        "integrated_into_draft": False, "integrated_into_filter": False,
        "columns": list(data["columns"]),
        "config": {
            "new_column": cfg["new_column"], "mode": cfg.get("mode"),
            "label_source": source, "apply_to": cfg.get("apply_to"),
            "case_study": case, "note": cfg["note"],
            "mode_note": cfg.get("mode_note"),
            "label_source_note": cfg.get("label_source_note"),
            "isolation_note": cfg.get("isolation_note"),
        },
        "stats": stats, "games": games, "misfires": misfires,
        "known_issues": known, "old_preview": "taxonomy-preview.html",
    }


def _markdown(payload: dict, labels: set[str], mode: str) -> str:
    cfg = payload["config"]
    new_col = cfg["new_column"]
    groups = [("new", [g for g in payload["games"] if g["game"] in labels]),
              ("work", [g for g in payload["games"] if g["game"] not in labels])]

    def block(gs: list[dict], heading: str, level: int) -> list[str]:
        out = [heading, ""]
        by_brand: dict[str, list[dict]] = defaultdict(list)
        for g in gs:
            by_brand[g["brand"]].append(g)
        for brand, rows in sorted(by_brand.items(), key=lambda x: x[0]):
            out += [f"{'#' * (level + 1)} {brand}", ""]
            for g in sorted(rows, key=lambda x: x["game"]):
                out += [f"{'#' * (level + 2)} {g['game']}", ""]
                for r in g["items"]:
                    if r["in_draft"]:
                        out.append(r["line"])
                out.append("")
        return out

    if mode == "subgroup":
        out = [f"## {WORK}", "", f"### {new_col}", ""]
        for brand, rows in sorted(
                ((b, [g for g in groups[0][1] if g["brand"] == b])
                 for b in {g["brand"] for g in groups[0][1]}), key=lambda x: x[0]):
            out += [f"#### {brand} · 新作", ""]
            for g in sorted(rows, key=lambda x: x["game"]):
                out += [f"##### {g['game']}", ""]
                out += [r["line"] for r in g["items"] if r["in_draft"]] + [""]
        out += ["### 其它作品", ""]
        for brand, rows in sorted(
                ((b, [g for g in groups[1][1] if g["brand"] == b])
                 for b in {g["brand"] for g in groups[1][1]}), key=lambda x: x[0]):
            out += [f"#### {brand}", ""]
            for g in sorted(rows, key=lambda x: x["game"]):
                out += [f"##### {g['game']}", ""]
                out += [r["line"] for r in g["items"] if r["in_draft"]] + [""]
        return "\n".join(out).rstrip() + "\n"

    out = block(groups[0][1], f"## {new_col}", 2) + [""] + \
          block(groups[1][1], f"## {WORK}", 2)
    return "\n".join(out).rstrip() + "\n"


def render_html(payload: dict, path: Path) -> str:
    s = payload["stats"]
    cfg = payload["config"]
    esc = _esc
    badges = "".join(
        f'<span class="badge{" warn" if w else ""}">{esc(t)}</span>'
        for t, w in (("方案 D · 按游戏分流（本轮裁决）", True),
                     ("独立 HTML · 试验", False), ("不进 draft.md", False),
                     ("不进 filter.html", False), ("标签可勾选", False),
                     ("上一版按条目打标签 → 已废弃", True)))

    tiles = "".join(
        f'<div class="stat"><b>{esc(v)}</b><span>{esc(k)}</span></div>'
        for v, k in ((s["games_total"], "作品情报游戏组"),
                     (s["games_labeled"], "带新作标签的游戏"),
                     (s["new_items_in_draft"], "→ 新作栏条目（初稿）"),
                     (s["work_items_in_draft"], "→ 作品情报栏条目（初稿）"),
                     (s["split_items"], "跨两栏重复条目"),
                     (s["auto_suggested"], "自动建议组数"),
                     (s["misfires"], "逐条打标签反例")))

    # 反例表
    mis_rows = "".join(
        f'<tr><td>{esc(m["game"])}</td><td>{esc(m["sentence"])}</td>'
        f'<td>{" / ".join(esc(x) for x in m["stages"]) or "—"}'
        f'{"/" if m["stages"] and m["forms"] else ""}'
        f'{" / ".join(esc(x) for x in m["forms"])}</td>'
        f'<td>{" ".join(esc(e) for e in m["evidence"]) or "—"}</td>'
        f'<td><span class="tg {"bad" if not m["game_labeled"] else "ok"}">'
        f'{esc(m["routed_to"])}</span></td></tr>'
        for m in payload["misfires"])

    # 游戏清单
    grows = []
    for i, g in enumerate(payload["games"]):
        sigs = "".join(f'<span class="tg sig">{esc(x)}</span>' for x in g["signals"])
        src = f'<span class="tg {"ok" if g["labeled"] else ""}">{esc(g["label_source"])}</span>'
        grows.append(
            f'<div class="g{" on" if g["labeled"] else ""}{" case" if g["is_case"] else ""}" '
            f'data-i="{i}"><input type="checkbox" id="g{i}" '
            f'{"checked" if g["labeled"] else ""} data-game="{esc(g["game"])}">'
            f'<label for="g{i}"><div class="nm">{esc(g["game"])}</div>'
            f'<div class="mt">{esc(g["brand"])} · {g["item_count"]} 条'
            f'（初稿 {g["draft_count"]}） {src} {sigs}</div></label></div>')
        if g["is_case"]:
            grows[-1] = grows[-1].replace('<div class="nm">',
                                          '<div class="nm">⭐ 案例 · ')

    def issue_list(rows: list[dict], why: str) -> str:
        if not rows:
            return '<div class="note">无</div>'
        return "".join(
            f'<div class="row"><div class="txt">{esc(r["game"])}</div>'
            f'<div class="meta">{esc(r["sample"][:90])} · {r["items"]} 条 · '
            f'{"+".join(esc(x) for x in r["signals"]) or "无信号"} · {esc(why)}</div></div>'
            for r in rows[:12])

    known = payload["known_issues"]
    doc = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>按游戏分流 · 新作 / 作品情报 预览</title>'
        f'<style>{_CSS}</style></head><body><div class="wrap">'
        f'<header><h1>按游戏分流 · 「新作」是「作品」的子集</h1>'
        '<div class="sub">weekly / game-routing · 独立试验页，用于判断分流单位，不是出稿</div>'
        f'{badges}</header>'
        '<div class="note good"><b>你这一轮改的是「分类单位」，我上一版搞错了。</b>'
        '上一版按<b>小条目</b>的 stage / form 标签算冲突，得出「A 方案有 24 条两边都放」——'
        '那是伪命题。按<b>游戏</b>整组路由时，游戏一旦带新作标签，它的全部条目一起进新作栏，'
        '<b>不存在同一条消息分到新作和作品两个栏</b>。新作消息会不断宣发，所以 OP、主题歌、'
        '特典、周边也都随游戏留在该栏，不需要逐条判断「这条算不算新作内容」。</div>'
        f'<div class="note">{esc(cfg["note"])}</div>'
        f'<div class="stats">{tiles}</div>'
        '<h2>一、为什么不能按小条目打标签：真实反例</h2>'
        '<div class="note">下表全是本期真实条目与真实命中词。逐条关键词会把「主题歌配信」'
        '打成<b>游戏发售</b>（命中「配信」）、把「抱枕套预约」打成发售、把「转 CLOWN 新作体验版」'
        '打成体验版公开。游戏级路由完全不用这些标签决定归栏，所以这些误判不再影响栏目。</div>'
        '<table><thead><tr><th>游戏</th><th>条目正文</th><th>旧版逐条标签</th>'
        '<th>命中词</th><th>新版归栏</th></tr></thead>'
        f'<tbody>{mis_rows or "<tr><td colspan=5>无</td></tr>"}</tbody></table>'
        '<h2>二、给游戏勾「新作」标签（可交互）</h2>'
        '<div class="note">默认勾选项来自 <code>rules.json:game_routing.signals</code> '
        '的<b>自动建议</b>，仅供起步：它仍会误中「抱枕套预约」「转别家新作」，也会漏掉'
        '显式的「新作《異世界孕ませハーレム》上架」。请直接勾选 / 取消，右边两栏排版与统计'
        '会实时重算；满意后点「导出标签集」把清单粘回 <code>new_work_games</code>。'
        f'案例 <code>{esc(cfg["case_study"])}</code> 已用 ⭐ 标出。</div>'
        '<div class="bar">'
        '<button type="button" id="b-reset">恢复自动建议</button>'
        '<button type="button" id="b-all">全选</button>'
        '<button type="button" id="b-none">全不选</button>'
        '<button type="button" id="b-export">导出标签集</button>'
        '<button type="button" class="on" id="m-column" data-mode="column">独立栏（两栏并列）</button>'
        '<button type="button" id="m-subgroup" data-mode="subgroup">作品情报下分组</button>'
        f'<a href="{esc(payload["old_preview"])}">看上一版（按条目打标签）</a>'
        '</div>'
        '<div class="lab"><div class="pane"><h3>游戏标签清单 '
        f'（{s["games_total"]} 组）</h3><div class="games">{"".join(grows)}</div></div>'
        '<div class="pane"><h3>实时排版</h3>'
        '<div class="stats" id="live-stats"></div>'
        '<pre class="md" id="live-md"></pre></div></div>'
        '<h2>三、自动建议的已知误差（必须人工裁定）</h2>'
        '<div class="note"><b>关键词初值不能当事实。</b>下面三类都是本期真实游戏组：'
        '显式的「新作《…》上架」反而漏掉，只有一个弱信号的 1～2 条小组、或带周年字样的旧作'
        '反而被建议成新作。请直接用上一节的勾选框修正，或把标签来源换成 '
        '<code>VNDB 发售日</code> / 纯人工清单。这也正是「标签挂在游戏上、可人工裁定」'
        '比「逐条关键词判定」稳的原因。</div>'
        '<h3>疑似漏判：正文出现「新作」但未勾（'
        f'{len(known["missed_explicit_new"])} 组）· 多数是提到别家新作，属正确不勾</h3>'
        + issue_list(known["missed_explicit_new"], "建议补勾") +
        '<h3>疑似误判：只有一个弱信号且条目 ≤2（'
        f'{len(known["weak_only"])} 组）</h3>'
        + issue_list(known["weak_only"], "建议复核") +
        '<h3>疑似误判：组内出现周年 / 旧作字样（'
        f'{len(known["negative_hits"])} 组）</h3>'
        + issue_list(known["negative_hits"], "建议取消") +
        '<h2>四、自动建议的证据（可核对关键词靠不靠谱）</h2>'
        '<div class="note">每行的「信号」是游戏组内<b>所有条目</b>汇总出来的，'
        '同一句命中 <code>negative</code>（抱枕 / 周年 / 转别家新作 …）就不计。'
        '这一层故意做得很保守、很透明，方便你决定要不要换成 VNDB 发售日或纯人工清单。</div>'
        '<table><thead><tr><th>游戏</th><th class="num">条目</th><th>信号</th>'
        '<th>命中句（最多 3 条）</th><th>标签</th></tr></thead><tbody>'
        + "".join(
            f'<tr><td>{esc(g["game"])}</td><td class="num">{g["item_count"]}</td>'
            f'<td>{"".join(f"<span class=\"tg sig\">{esc(x)}</span>" for x in g["signals"]) or "—"}</td>'
            f'<td>{"<br>".join(esc(e["sentence"][:60]) for e in g["evidence"][:3]) or "—"}</td>'
            f'<td>{esc(g["label_source"])}</td></tr>'
            for g in payload["games"] if g["evidence"]) +
        '</tbody></table>'
        f'<div class="note"><b>隔离声明</b>：{esc(cfg["isolation_note"])}'
        '<br>标签来源口径：' + esc(cfg["label_source_note"]) +
        '<br>排版口径：' + esc(cfg["mode_note"]) + '</div>'
        '<footer>试验产物 · 分类单位＝游戏 · 标签可人工裁定 · 是否落地进初稿与筛选页待你拍板</footer>'
        '</div><script>'
        'var GAMES=' + json.dumps(
            [{"game": g["game"], "brand": g["brand"],
              "items": [r for r in g["items"] if r["in_draft"]]}
             for g in payload["games"]], ensure_ascii=False) + ';'
        'var CFG=' + json.dumps({"new": cfg["new_column"], "work": cfg_columns(payload)},
                                ensure_ascii=False) + ';'
        'var SUGGEST=' + json.dumps([g["game"] for g in payload["games"] if g["labeled"]],
                                    ensure_ascii=False) + ';'
        'var labels=new Set(SUGGEST),mode="column";'
        'function esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")'
        '.replace(/>/g,"&gt;").replace(/"/g,"&quot;");}'
        'function md(){'
        'var A=[],B=[];GAMES.forEach(function(g){ (labels.has(g.game)?A:B).push(g); });'
        'function block(gs,title,lv,out){'
        'out.push(title,"");var by={};gs.forEach(function(g){(by[g.brand]=by[g.brand]||[]).push(g)});'
        'Object.keys(by).sort().forEach(function(b){'
        'out.push("#".repeat(lv+1)+" "+b,"");'
        'by[b].sort(function(x,y){return x.game<y.game?-1:1}).forEach(function(g){'
        'out.push("#".repeat(lv+2)+" "+g.game,"");'
        'g.items.forEach(function(r){out.push(r.line)});out.push("")});});}'
        'if(mode==="subgroup"){'
        'var out=["## "+CFG.work,"","### "+CFG.new,""];'
        'var by={};A.forEach(function(g){(by[g.brand]=by[g.brand]||[]).push(g)});'
        'Object.keys(by).sort().forEach(function(b){out.push("#### "+b+" · "+CFG.new,"");'
        'by[b].forEach(function(g){out.push("##### "+g.game,"");'
        'g.items.forEach(function(r){out.push(r.line)});out.push("")})});'
        'out.push("### 其它作品","");by={};B.forEach(function(g){(by[g.brand]=by[g.brand]||[]).push(g)});'
        'Object.keys(by).sort().forEach(function(b){out.push("#### "+b,"");'
        'by[b].forEach(function(g){out.push("##### "+g.game,"");'
        'g.items.forEach(function(r){out.push(r.line)});out.push("")})});'
        'return out.join("\\n").replace(/\\n+$/,"")+"\\n"}'
        'var out=[];block(A,"## "+CFG.new,2,out);out.push("");block(B,"## "+CFG.work,2,out);'
        'return out.join("\\n").replace(/\\n+$/,"")+"\\n"}'
        'function statsHtml(A,B){'
        'var ai=A.reduce(function(n,g){return n+g.items.length},0),'
        'bi=B.reduce(function(n,g){return n+g.items.length},0);'
        'return [["新作栏游戏",A.length],["新作栏条目",ai],["作品情报游戏",B.length],'
        '["作品情报条目",bi],["跨栏重复",0]].map(function(x){'
        'return "<div class=\\"stat\\"><b>"+x[1]+"</b><span>"+x[0]+"</span></div>"}).join("")}'
        'function render(){var A=[],B=[];GAMES.forEach(function(g){(labels.has(g.game)?A:B).push(g)});'
        'document.getElementById("live-stats").innerHTML=statsHtml(A,B);'
        'document.getElementById("live-md").textContent=md();'
        'document.querySelectorAll(".g").forEach(function(el){'
        'var cb=el.querySelector("input");el.classList.toggle("on",cb.checked)});}'
        'document.querySelectorAll(".g input").forEach(function(cb){'
        'cb.addEventListener("change",function(){if(cb.checked)labels.add(cb.dataset.game);'
        'else labels.delete(cb.dataset.game);render()})});'
        'function setAll(v){document.querySelectorAll(".g input").forEach(function(cb){cb.checked=v;'
        'if(v)labels.add(cb.dataset.game);else labels.delete(cb.dataset.game)});render()}'
        'function reset(){setAll(false);SUGGEST.forEach(function(g){labels.add(g);'
        'document.querySelectorAll(".g input").forEach(function(cb){'
        'if(cb.dataset.game===g)cb.checked=true})});render()}'
        'document.getElementById("b-all").onclick=function(){setAll(true)};'
        'document.getElementById("b-none").onclick=function(){setAll(false)};'
        'document.getElementById("b-reset").onclick=reset;'
        'document.getElementById("b-export").onclick=function(){'
        'var data={new_work_games:Array.from(labels).sort(),'
        'never_new_work_games:["'+NO_GAME+'"],label_source:"manual"};'
        'var b=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});'
        'var a=document.createElement("a");a.href=URL.createObjectURL(b);'
        'a.download="game_routing_labels.json";a.click()};'
        'document.querySelectorAll("[data-mode]").forEach(function(b){b.onclick=function(){'
        'mode=b.dataset.mode;document.querySelectorAll("[data-mode]").forEach(function(x){'
        'x.classList.toggle("on",x===b)});render()}});'
        'render();document.body.setAttribute("data-js-ok","1");'
        '</script></body></html>'
    )
    write_text(Path(path), doc)
    return doc


def cfg_columns(payload: dict) -> str:
    cols = payload.get("columns") or []
    return str(cols[0]) if cols else WORK


def build(rules: dict | None = None) -> dict:
    from .config import load_rules
    rules = rules or load_rules()
    payload = build_preview(rules)
    write_json(OUT / "game-routing-preview-data.json", payload)
    render_html(payload, OUT / "game-routing-preview.html")
    labels = {g["game"] for g in payload["games"] if g["labeled"]}
    write_text(OUT / "game-routing-draft.md",
               _markdown(payload, labels, str(payload["config"]["mode"] or "column")))
    return payload
