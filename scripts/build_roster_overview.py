#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把日报名单导成一张总表（两版合并视图）。

正本是 `src/config/daily-roster.json`（声优版）与 `daily-roster-galgame.json`
（Galgame 版）；本表是它们的只读视图，外加
`README/reports/galgame-accounts-2026-10.html` 里已核过、但**还没写进 JSON** 的
候选（信息号 11 + 厂商侧个人号 14）。改名单请改 JSON，改完重跑：

    python scripts/build_roster_overview.py
    python scripts/build_roster_overview.py --out README/reports/xxx.html
"""

from __future__ import annotations

import argparse
import collections
import html
import io
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTERS = {
    "voice": ROOT / "src" / "config" / "daily-roster.json",
    "galgame": ROOT / "src" / "config" / "daily-roster-galgame.json",
}
DEFAULT_OUT = ROOT / "README" / "reports" / "daily-roster-2026-10.html"

ROLE_LABEL = {
    "main": "主号",
    "sub": "小号",
    "announce": "告知号",
    "circle": "社团号",
    "brand": "官号",
    "info": "信息号",
    "other": "其它",
}

# ── 未入册候选：来自 galgame-accounts-2026-10.html，2026-10-29 实查 ──────────
# 字段：handle, name, fans, last, tags, note, prio（"" / "优先" / "可缓"）
INFO_PERSONAL = [
    ("masanlive", "まさん -VisualNovel-", "5,223", "2026-10-28",
     ["游戏情报", "个人向"],
     "札幌的美少女游戏 YouTuber。新作／旧作感想、解说直播预告、业界杂谈；会直接在推上征集企划、和观众与品牌互动。", ""),
    ("erogehou", "なつまる（YouTube ラジオ）", "5,233", "2026-10-28",
     ["游戏情报", "个人向"],
     "YouTube『エロゲー放送局』主播的个人号。恋爱 ADV 的感想与推荐、配信告知，和听众来回聊。频道号 @erogehousou 只转推，收这个就够。", ""),
    ("RAGDIS27993204", "ねぷねぷギア", "5,011", "2026-10-28",
     ["游戏情报", "个人向"],
     "Leaf／アクアプラス／オーガスト／minori 老玩家。逐作回顾连载（#オーガストの作品を振り返る）、系列年表考据、旧作长文感想。", ""),
    ("seiya_saiga", "誠也の部屋@公式", "3,824", "2026-10-23",
     ["游戏情报", "个人向", "攻略站"],
     "攻略站「誠也の部屋」官方号。逐条发新作攻略更新与当周打折情报，几乎日更。与 @uitachibana4 同一人，视角互补。", ""),
    ("B2F_", "Ｂ２Ｆ（地下二階）", "1,046", "2026-10-29",
     ["游戏情报", "个人向"],
     "个人博客连动号。自制排行榜企划（#マスト幼馴染エロゲ100 之类）、新作感想、和玩家互相 @ 讨论评分标准。", ""),
    ("aikouka23", "エロゲ情報収集愛好家", "942", "2026-10-28",
     ["游戏情报", "个人向"],
     "「收藏侧」情报：初回版／修正版的刻印差异、流通撤退与廃盤动向、老作保存版考据。这类内容别的号不写。", ""),
]

INFO_PLATFORM = [
    ("DLsite", "DLsite公式", "101,843", "2026-10-27",
     ["游戏情报", "平台"],
     "同人／音声／漫画贩售平台官方。每日新作上架、期间特价、排行榜。量大，但同人比例高、galgame 占比低。", ""),
    ("akibablog", "geek@akibablog", "84,446", "2026-10-28",
     ["游戏情报", "平台"],
     "アキバBlog 运营者号。几乎全是转推（秋叶原／御宅新闻，含新作与发售话题），无原创，噪音偏高。", "可缓"),
    ("FANZA_NEWS", "FANZAニュース【公式／編集部】", "66,360", "2026-10-23",
     ["游戏情报", "媒体"],
     "FANZA 新闻编辑部。业界新闻、新作与销量话题、专栏转载，行业侧视角。", ""),
    ("getchucom", "Getchu.com（げっちゅ屋）", "26,167", "2026-10-28",
     ["游戏情报", "平台"],
     "新作预约开始、店铺特典、发售日倒数、体验版与 CG 更新——最接近「发售日历」的号。", "优先"),
    ("bugbug_info", "BugBug編集部", "24,666", "2026-10-28",
     ["游戏情报", "媒体"],
     "每天 2～4 条新作／同人漫画介绍并导流 bugbug.news，另有月度销量排行与特集。信息密度最高。", "优先"),
    ("megastore_info", "月刊メガストア", "6,319", "2026-10-01",
     ["游戏情报", "媒体"],
     "每月发卖号的特集与收录作告知。月更节奏，适合补「杂志侧」话题。", ""),
    ("newakiba", "newakiba", "1,885", "2026-10-28",
     ["游戏情报", "平台"],
     "秋叶原系新闻站。新作 18 禁 SLG／ADV 与漫画新刊的短讯，一条一作带链接，内容较杂。", ""),
]

VENDOR_PEOPLE = [
    ("Butch_Gen", "虚淵玄", "386,515", "2026-10-27", "剧作者",
     "Nitroplus／『まどか☆マギカ』『Fate/Zero』『沙耶の唄』",
     "本人号。近期几乎全是自制プラモ（スコープドッグ）进度与观影感想，作品告知很少。粉丝量最大、辨识度最高。", ""),
    ("Higashide_Yu", "東出祐一郎", "48,067", "2026-10-27", "剧作者",
     "『Fate/Grand Order』『装甲悪鬼村正』",
     "FGO 剧本进展、读书与三国志杂谈。原创比例低（20 条中 2 条原创，其余是回复）。", ""),
    ("kionachi", "木緒なち", "42,626", "2026-10-28", "剧作者",
     "『ぼくたちのリメイク』、Logo 设计",
     "杂谈为主：棒球、猫、业界吐槽，偶尔工作近况。噪声大，但确为本人。", ""),
    ("F_Maruto_staff", "丸戸史明(公式)", "36,841", "2026-10-19", "剧作者 · staff",
     "『この青空に約束を』『WHITE ALBUM2』",
     "staff 运营的公式号，几乎全是转推，只发作品告知（近期为『蓮ノ空』剧本）。不是自由发言的本人号。", ""),
    ("shimokura_vio", "下倉バイオ", "18,281", "2026-10-28", "剧作者",
     "Nitroplus／『君と彼女と彼女の恋。』",
     "日常为主：VRChat、フィギュア、模型；偶尔一句工作进度。更新频繁。", ""),
    ("Toshi_Ikebukuro", "王雀孫", "14,357", "2026-09-16", "剧作者",
     "Navel／『俺たちに翼はない』",
     "工作告知（プリコネ等）+ 杂谈。43 天未发原创，仍在 90 天活跃线内。", ""),
    ("hozumik", "保住圭", "8,223", "2026-10-22", "剧作者",
     "合同会社サッズ代表／漫画原作、galgame 脚本",
     "自家作品与 DLsite 折扣宣传、创作近况。重心已转向漫画原作。", ""),
    ("gyyuiuui", "瀬戸口廉也", "7,312", "2026-10-06", "剧作者",
     "『CROSS†CHANNEL』『MUSICUS!』『SWAN SONG』",
     "稀疏原创：制作中作品的暗示、日常抱怨。23 天前更新。", ""),
    ("uchikoshi", "打越鋼太郎", "12,391", "2026-10-17", "导演",
     "『Ever17』『999』『AI ソムニウムファイル』",
     "开发近况（含 10/15 公布企划中止）、粉丝问答；英日双语分号运营。", ""),
    ("nakazawatakumi", "中澤工", "4,783", "2026-10-25", "导演",
     "『Ever17』『Root Double』『終天教団』",
     "制作幕后解说连载（Ever17 的设计意图、没采用的设定）、行业观察。质量最高的导演号。", "优先"),
    ("rodorin", "ろど", "15,905", "2026-10-28", "导演",
     "ゆずソフト ディレクター（ムービー・背景）",
     "自称ゆずソフト 监督。但 20 条里只有 1 条原创，其余全是转推／点赞，几乎无情报价值。", "可缓"),
    ("digitarou", "でじたろう@ニトロプラス", "105,029", "2026-10-28", "代表",
     "Nitroplus 代表取締役（小坂崇氣）",
     "企划进展（刀剣乱舞、まどマギ新作、Dolls Nest）、刀剑文化与美术馆话题。原创比例低但均为官方口径。", "优先"),
    ("Famishin", "Famishin", "14,155", "2026-10-29", "代表",
     "ゆずソフト 代表（＝天宮リツ）",
     "自称「名ばかり代表」的音屋。SongFes 混音、会议与监修日常，日更，最像「公司内部视角」的号。", "优先"),
    ("vavasyatyou", "馬場隆博", "30,933", "2026-10-26", "代表",
     "ビジュアルアーツ／Key 創業者",
     "简介写「現在は特定投資家」。近期以电视剧／演员评论为主，业界内容少。", "可缓"),
]

STYLE = """
:root {
  --bg: #ffffff; --bg-subtle: #fafafa; --text: #1a1a1a; --text-2: #555;
  --muted: #767676; --border: #e5e5e5; --border-strong: #cfcfcf;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; padding: 48px 24px 96px; background: var(--bg); color: var(--text);
  font: 15px/1.7 -apple-system, "Segoe UI", "Noto Sans SC", "Hiragino Sans", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1140px; margin: 0 auto; }
h1 { margin: 0 0 8px; font-size: 26px; font-weight: 600; letter-spacing: -0.01em; }
h2 { margin: 52px 0 12px; padding-bottom: 8px; font-size: 19px; font-weight: 600;
  border-bottom: 1px solid var(--border); letter-spacing: -0.01em; }
h3 { margin: 26px 0 8px; font-size: 15px; font-weight: 600; }
p { margin: 0 0 12px; }
.sub { margin: 0 0 6px; color: var(--text-2); }
.meta { margin: 0 0 26px; color: var(--muted); font-size: 13px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9em;
  background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; }
.stats { display: flex; flex-wrap: wrap; gap: 32px; margin: 0 0 8px; padding: 16px 0;
  border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
.stat b { display: block; font-size: 23px; font-weight: 600; font-variant-numeric: tabular-nums; }
.stat span { color: var(--muted); font-size: 12px; }
.stat.is-pending b { color: var(--text-2); }
nav.toc { margin: 22px 0 0; font-size: 13px; color: var(--muted); }
nav.toc a { color: var(--text-2); text-decoration: none; border-bottom: 1px solid var(--border-strong);
  margin-right: 14px; white-space: nowrap; }
nav.toc a:hover { color: var(--text); border-bottom-color: var(--text); }
.filter { margin: 22px 0 0; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.filter input { font: inherit; font-size: 13px; padding: 6px 10px; width: 280px;
  border: 1px solid var(--border-strong); border-radius: 6px; background: var(--bg); color: var(--text); }
.filter input:focus { outline: none; border-color: var(--text); }
.filter span { color: var(--muted); font-size: 12.5px; font-variant-numeric: tabular-nums; }
.scroll { overflow: auto; max-height: 72vh; margin: 16px 0 0;
  border: 1px solid var(--border); border-radius: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { padding: 7px 10px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--border); }
th { font-weight: 500; color: var(--muted); font-size: 12px; white-space: nowrap;
  position: sticky; top: 0; background: var(--bg); border-bottom-color: var(--border-strong); z-index: 1; }
tbody tr:nth-child(even) { background: #fcfcfc; }
tbody tr:hover { background: var(--bg-subtle); }
td.rank { color: var(--muted); font-variant-numeric: tabular-nums; width: 42px; }
td.num { text-align: right; color: var(--text-2); font-variant-numeric: tabular-nums; white-space: nowrap; }
td.name { font-weight: 500; white-space: nowrap; }
td.handle { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; white-space: nowrap; }
td.handle a { color: var(--text-2); text-decoration: none; border-bottom: 1px solid var(--border-strong); }
td.handle a:hover { color: var(--text); border-bottom-color: var(--text); }
td.note { color: var(--muted); font-size: 12.5px; min-width: 16em; }
td.tags { white-space: nowrap; }
.tag { display: inline-block; margin: 0 3px 2px 0; padding: 1px 6px; font-size: 11px;
  color: var(--text-2); border: 1px solid var(--border-strong); border-radius: 6px; white-space: nowrap; }
.tag--live { color: var(--text); border-color: var(--text); font-weight: 500; }
.tag--pending { color: var(--muted); border-style: dashed; }
.tag--prio { color: var(--text); border-color: var(--text); }
.tag--hold { color: var(--muted); border-style: dotted; }
.tag--info { color: var(--text); border-color: var(--text); }
table.kv { max-width: 100%; font-size: 13.5px; }
table.kv th, table.kv td { white-space: normal; }
table.kv td { vertical-align: top; }
.note-box { background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 6px;
  padding: 14px 18px; margin: 18px 0; }
.note-box strong { font-weight: 600; }
.legend { margin: 12px 0 0; color: var(--muted); font-size: 12.5px; }
footer { margin-top: 60px; padding-top: 20px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 12.5px; }
"""


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def tag_chips(tags, extra=""):
    out = "".join('<span class="tag">%s</span>' % esc(t) for t in tags)
    return out + extra


def state_chip(active: bool) -> str:
    if active:
        return '<span class="tag tag--live">在用</span>'
    return '<span class="tag tag--pending">待选</span>'


def prio_chip(prio: str) -> str:
    if prio == "优先":
        return '<span class="tag tag--prio">优先</span>'
    if prio == "可缓":
        return '<span class="tag tag--hold">可缓</span>'
    return ""


def parse_counts(note: str):
    m = re.search(r"近三年\s*(\d+)\s*部\s*/\s*累计\s*(\d+)\s*部", note or "")
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def roster_rows(accounts, start=1):
    rows = []
    for index, a in enumerate(accounts, start=start):
        extra = state_chip(bool(a.get("active", True)))
        rows.append(
            '<tr data-s="%s"><td class="rank">%d</td><td class="name">%s</td>'
            '<td class="handle"><a href="https://x.com/%s" rel="noopener">@%s</a></td>'
            '<td class="tags">%s</td><td>%s</td><td class="note">%s</td></tr>'
            % (
                esc(("%s %s %s %s" % (a.get("name", ""), a["handle"],
                                       " ".join(a.get("tags") or []),
                                       ROLE_LABEL.get(a.get("role", ""), a.get("role", "")))).lower()),
                index,
                esc(a.get("name", "")),
                esc(a["handle"]),
                esc(a["handle"]),
                tag_chips(a.get("tags") or [], extra),
                esc(ROLE_LABEL.get(a.get("role", ""), a.get("role", ""))),
                esc(a.get("note", "")),
            )
        )
    return rows


def circle_rows(accounts):
    rows = []
    for index, a in enumerate(accounts, start=1):
        recent, total = parse_counts(a.get("note", ""))
        rows.append(
            '<tr data-s="%s"><td class="rank">%d</td><td class="name">%s</td>'
            '<td class="handle"><a href="https://x.com/%s" rel="noopener">@%s</a></td>'
            '<td class="tags">%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
            % (
                esc(("%s %s %s" % (a.get("name", ""), a["handle"],
                                    " ".join(a.get("tags") or []))).lower()),
                index,
                esc(a.get("name", "")),
                esc(a["handle"]),
                esc(a["handle"]),
                tag_chips(a.get("tags") or [], state_chip(bool(a.get("active", True)))),
                "—" if recent is None else recent,
                "—" if total is None else total,
            )
        )
    return rows


def candidate_rows(items, with_fans=True, with_affil=False):
    rows = []
    for index, item in enumerate(items, start=1):
        if with_affil:
            handle, name, fans, last, kind, affil, note, prio = item
            tags = ["游戏制造", kind]
            mid = '<td class="note">%s</td>' % esc(affil)
        else:
            handle, name, fans, last, tags, note, prio = item
            mid = ""
        extra = prio_chip(prio) + '<span class="tag tag--pending">待选</span>'
        rows.append(
            '<tr data-s="%s"><td class="rank">%d</td><td class="name">%s</td>'
            '<td class="handle"><a href="https://x.com/%s" rel="noopener">@%s</a></td>'
            '<td class="num">%s</td><td class="num">%s</td>%s'
            '<td class="tags">%s</td><td class="note">%s</td></tr>'
            % (
                esc(("%s %s %s %s" % (name, handle, " ".join(tags), note)).lower()),
                index,
                esc(name),
                esc(handle),
                esc(handle),
                esc(fans),
                esc(last),
                mid,
                tag_chips(tags, extra),
                esc(note),
            )
        )
    return rows


def build(out_path: Path) -> None:
    data = json.loads(io.open(ROSTERS["voice"], encoding="utf-8").read())
    accounts = list(data["accounts"])
    # 2026-10-29 起名单拆成两份，总表要把 Galgame 版并进来（顺序：声优 → 社团 → 厂商 → 信息号）
    accounts += json.loads(io.open(ROSTERS["galgame"], encoding="utf-8").read())["accounts"]

    seiyuu = [a for a in accounts if a.get("category") == "seiyuu"]
    makers = [a for a in accounts if a.get("category") == "manufacturer"]
    circles = [a for a in accounts if a.get("category") == "circle"]
    others = [a for a in accounts if a.get("category") not in {"seiyuu", "manufacturer", "circle"}]

    live = [a for a in accounts if a.get("active", True)]
    dormant = [a for a in accounts if not a.get("active", True)]
    people = len({a["name"] for a in seiyuu})
    circle_role_live = [a for a in seiyuu if a.get("role") == "circle"]

    # 2026-10-29：三个信息号已入册并启用，其余候选仍是「未入册」
    info_live = [a for a in accounts if a.get("category") == "info"]
    enabled = {a["handle"].lower() for a in info_live}
    info_personal = [x for x in INFO_PERSONAL if x[0].lower() not in enabled]
    info_platform = [x for x in INFO_PLATFORM if x[0].lower() not in enabled]
    n_candidates = len(info_personal) + len(info_platform) + len(VENDOR_PEOPLE)

    prio = sum(1 for x in info_personal + info_platform + VENDOR_PEOPLE if x[-1] == "优先")

    tag_counts = collections.Counter()
    for a in accounts:
        for t in a.get("tags") or []:
            tag_counts[t] += 1
    tag_line = "、".join("<code>%s</code> %d" % (esc(t), n) for t, n in tag_counts.most_common())

    rows_seiyuu = roster_rows(seiyuu)
    rows_makers = roster_rows(makers)
    rows_circles = circle_rows(circles)
    rows_info_live = roster_rows(info_live)
    rows_vendor = candidate_rows(VENDOR_PEOPLE, with_affil=True)

    today = date.today().isoformat()

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>日报名单：两版在册 {len(accounts)} · 全部在用 · 未入册候选 {n_candidates}</title>
<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
  <h1>日报名单：两版在册 {len(accounts)} · 全部在用 · 未入册候选 {n_candidates}</h1>
  <p class="sub">2026-10-29 起名单拆成两份、一天出两份日报：<strong>声优版</strong>（声优 + 音声社团，期号 <code>YYMMDD</code>）与 <strong>Galgame 版</strong>（游戏制造商 + 信息号，期号 <code>YYMMDD-g</code>）。下面四个大类逐条列出，每条带名单里的原始 <code>tags</code>。</p>
  <p class="meta">生成日期 {today} ｜ 数据源 <code>src/config/daily-roster.json</code>（{len(seiyuu) + len(circles)} 条）+ <code>daily-roster-galgame.json</code>（{len(makers) + len(info_live)} 条），schema v{data.get("schema_version")} ｜ 候选来自 <code>README/reports/galgame-accounts-2026-10.html</code> ｜ 重跑 <code>python scripts/build_roster_overview.py</code></p>

  <div class="stats">
    <div class="stat"><b>{len(accounts)}</b><span>两版在册</span></div>
    <div class="stat"><b>{len(seiyuu) + len(circles)}</b><span>声优版 · 声优 {len(seiyuu)} + 社团 {len(circles)}</span></div>
    <div class="stat"><b>{len(makers) + len(info_live)}</b><span>Galgame 版 · 厂商 {len(makers)} + 信息号 {len(info_live)}</span></div>
    <div class="stat"><b>{len(live)}</b><span>全部在用（进抓取）</span></div>
    <div class="stat is-pending"><b>{n_candidates}</b><span>已核实未入册</span></div>
    <div class="stat"><b>{prio}</b><span>候选里标「优先」</span></div>
  </div>

  <nav class="toc">
    <a href="#scope">口径</a><a href="#seiyuu">声优 {len(seiyuu)}</a><a href="#circle">音声社团 {len(circles)}</a><a href="#maker">游戏制造商 {len(makers)}</a><a href="#info">信息号 {len(info_live)}</a><a href="#vendor">厂商侧个人号 {len(VENDOR_PEOPLE)}</a><a href="#gaps">还差什么</a>
  </nav>

  <div class="filter">
    <input id="q" type="search" placeholder="筛选 handle / 名称 / 标签（全表生效）" autocomplete="off">
    <span id="q-count"></span>
  </div>

  <h2 id="scope">0 口径：四个「类」怎么落到两份名单的字段上</h2>
  <p>名单里 <code>category</code> 有四个在用值，正好对应你说的四大类；<code>other</code> 在两份里都空置。但<strong>「进哪一版日报」不看 category，看它写在哪份文件里</strong>——<code>daily-roster.json</code> 出 <code>YYMMDD</code>，<code>daily-roster-galgame.json</code> 出 <code>YYMMDD-g</code>。category 只决定条目落在哪个栏目、以及页面上的筛选按钮怎么分组。</p>
  <div class="scroll" style="max-height:none">
    <table class="kv">
      <thead><tr><th>你说的类</th><th>名单里怎么认</th><th>数量</th><th>进哪一版</th><th>说明</th></tr></thead>
      <tbody>
        <tr><td class="name">声优</td><td><code>category: seiyuu</code></td><td class="num">{len(seiyuu)}</td><td>声优版</td><td>{people} 人 ／ {len(seiyuu)} 条：主号 {sum(1 for a in seiyuu if a.get("role")=="main")}、小号 {sum(1 for a in seiyuu if a.get("role")=="sub")}、告知号 {sum(1 for a in seiyuu if a.get("role")=="announce")}、社团号 {len(circle_role_live)}、其它 {sum(1 for a in seiyuu if a.get("role")=="other")}。同一人多号时 <code>role</code> 区分。</td></tr>
        <tr><td class="name">同人音声社团</td><td><code>category: circle</code></td><td class="num">{len(circles)}</td><td>声优版</td><td>2026-10-25 从 swsem 的 1,450 家里筛出（近三年 &gt; 5 部）344 家，其中 116 家拿到 X 账号，109 家进名单。<strong>2026-10-29 起全部 <code>active: true</code></strong>，和声优同版出。</td></tr>
        <tr><td class="name">游戏制造商</td><td><code>category: manufacturer</code></td><td class="num">{len(makers)}</td><td>Galgame 版</td><td>{sum(1 for a in makers if a.get("role")=="brand")} 个厂商官号（<code>role: brand</code>）+ 1 个非厂商（Moepedia，情报站，<code>role: other</code>）。同社多品牌写在 <code>note</code> 里，一个 handle 一条。</td></tr>
        <tr><td class="name">游戏信息账号</td><td><code>category: info</code></td><td class="num">{len(info_live)}</td><td>Galgame 版</td><td>2026-10-29 新建这个 category，先启用三个个人向信息号（{"、".join("<code>@" + a["handle"] + "</code>" for a in info_live)}）。另有 {len(info_personal) + len(info_platform)} 个候选还在报告里，见第 4 节。</td></tr>
      </tbody>
    </table>
  </div>

  <div class="note-box">
    <p><strong>「在用」只看一个字段。</strong><code>scripts/sync_xreader_accounts.py</code> 只判断 <code>active != false</code>，把 handle 按名单顺序写成 X-Reader 的 <code>accounts.yaml</code> / <code>accounts.galgame.yaml</code>；<code>category</code> 不参与抓不抓，它只决定条目落在日报页哪个栏目。现在两版合计 <strong>{len(accounts)} 个账号全部 <code>active: true</code></strong>，待选 0——剩下 {n_candidates} 个是「核实过但还没写进 JSON」的候选，不在这两份名单里。</p>
    <p><strong>标签是名单里的原值，不是我加的。</strong>两版合并后只出现 {len(tag_counts)} 种：{tag_line}。候选那 {n_candidates} 条还没进 JSON，标签是我按来源报告补的临时标识（<code>游戏情报</code>／<code>厂商侧</code> 等），入册时要换成正式标签。</p>
    <p><strong>抓取已经拆成两个 workflow。</strong>声优版 237 个账号跑 <code>update.yml</code>（超时线放宽到 30 分钟），Galgame 版 177 个跑 <code>update-galgame.yml</code>（<code>data-galgame</code> 独立目录）。两版互不阻塞，也避免同时 <code>git add data</code> 打架。</p>
  </div>

  <h2 id="seiyuu">1 声优：{len(seiyuu)} 条（{people} 人）· 声优版 · 全部在用</h2>
  <p>按名单顺序，即日报里的显示顺序。同一个人的小号／告知号／社团号紧跟在主号后面，靠 <code>role</code> 认。</p>
  <div class="scroll">
    <table>
      <thead><tr><th>#</th><th>名称</th><th>X 账号</th><th>标签</th><th>身份</th><th>备注</th></tr></thead>
      <tbody>
        {"".join(rows_seiyuu)}
      </tbody>
    </table>
  </div>
  <p class="legend">声优里有 {len(circle_role_live)} 个条目 <code>role: circle</code>——是本人名下的同人社团号（{"、".join("@" + a["handle"] for a in circle_role_live)}，其中多数为「推定自有」：同一声优在该社多部作品里是唯一 cast）。它们归在声优类，所以算进这 {len(seiyuu)} 条，不算进下一节的 {len(circles)} 个社团。</p>

  <h2 id="circle">2 同人音声社团：{len(circles)} 条 · 声优版 · 全部在用</h2>
  <p>这 {len(circles)} 个 2026-10-29 起从「在册未启用」转成 <code>active: true</code>，跟着声优版一起抓、一起出。备注两列是 DLsite 侧的产量：近三年部数（2023-10 之后）和累计部数，用来看这个社更不更新得动。</p>
  <div class="scroll">
    <table>
      <thead><tr><th>#</th><th>名称</th><th>X 账号</th><th>标签</th><th class="num">近三年</th><th class="num">累计</th></tr></thead>
      <tbody>
        {"".join(rows_circles)}
      </tbody>
    </table>
  </div>
  <p class="legend">来源：<code>dlsite-circle-roster.html</code>（2026-10-25）。1,450 家里近三年 &gt; 5 部的有 344 家，其中 116 家拿到 X 账号，进名单 {len(circles)} 家（其余 7 家是搜到候选但没采信，不算待选）。启用代价：声优版从 128 个涨到 {len(seiyuu) + len(circles)} 个，所以 <code>update.yml</code> 超时线同步从 20 分钟放宽到 30 分钟。</p>

  <h2 id="maker">3 游戏制造商：{len(makers)} 条 · Galgame 版 · 全部在用</h2>
  <p>一个 handle 一条；同社多品牌写进备注。备注里的「五年 N 部」是 2021-10 ～ 2026-10 在 moepedia 登场的作品数，用来判断这个号值不值得跟。</p>
  <div class="scroll">
    <table>
      <thead><tr><th>#</th><th>名称</th><th>X 账号</th><th>标签</th><th>身份</th><th>备注</th></tr></thead>
      <tbody>
        {"".join(rows_makers)}
      </tbody>
    </table>
  </div>
  <p class="legend">第 1 条 <code>@Moepedia_net</code> 不是厂商，是作品情报站（tags：资料站／作品情报），因为月度新作日历靠它才挂在 manufacturer 下。它广告味重，走名单里的 <code>filter</code> 段降噪：抽奖、店铺特典、周年回顾、发售日回顾全筛掉，每期最多 5 条。</p>

  <h2 id="info">4 游戏信息账号：在用 {len(info_live)} · Galgame 版</h2>
  <p>这一类 2026-10-29 才有自己的 <code>category: info</code>，只启用三个个人向信息号；其余候选还停在报告里，没进 JSON。</p>

  <h3>4.1 在用（{len(info_live)}）</h3>
  <div class="scroll" style="max-height:none">
    <table>
      <thead><tr><th>#</th><th>名称</th><th>X 账号</th><th>标签</th><th>身份</th><th>备注</th></tr></thead>
      <tbody>
        {"".join(rows_info_live)}
      </tbody>
    </table>
  </div>
  <p class="legend">三个都在 <code>daily-roster-galgame.json</code> 里挂了 <code>filter</code>：<code>max_items: 5</code> + <code>prefer_if</code>（新作／発売／体験版／予約…）。信息号发帖频次高，不限量会把厂商官号挤掉。Moepedia 仍挂 manufacturer，不重复计入这里。</p>

  <h3>4.2 待选·个人向信息号（{len(info_personal)}）</h3>
  <p>定位是「有人在替读者做筛选」：原创感想 + 新作／旧作情报 + 回顾，会和业界、玩家来回互动。不是声优，不是厂商官号。</p>
  <div class="scroll">
    <table>
      <thead><tr><th>#</th><th>名称</th><th>X 账号</th><th class="num">粉丝</th><th class="num">最近发帖</th><th>标签</th><th>发什么</th></tr></thead>
      <tbody>
        {"".join(candidate_rows(info_personal))}
      </tbody>
    </table>
  </div>

  <h3>4.3 待选·平台／媒体官方号（{len(info_platform)}）</h3>
  <p>量和噪音都更大。真正每天值得抓的是 <code>@getchucom</code>（发售日历）和 <code>@bugbug_info</code>（新作介绍），其余按「补哪个栏目」再决定。</p>
  <div class="scroll">
    <table>
      <thead><tr><th>#</th><th>名称</th><th>X 账号</th><th class="num">粉丝</th><th class="num">最近发帖</th><th>标签</th><th>发什么</th></tr></thead>
      <tbody>
        {"".join(candidate_rows(info_platform))}
      </tbody>
    </table>
  </div>

  <h2 id="vendor">5 待选·厂商侧个人号：{len(VENDOR_PEOPLE)}</h2>
  <p>这一栏的人是「被报道的对象」，不是报道者。抓进来是为了在日报里出现「某人的新作动向」时能引到本人发言，而不是每天产出条目——入册时每条要挂 <code>max_items: 1</code>，否则一天五条日常会把厂商栏目挤掉。类别上归在「游戏制造商」这一大类的侧翼，名单里建议新增 <code>scenario</code> / <code>director</code> / <code>owner</code> 三个 role。</p>
  <div class="scroll">
    <table>
      <thead><tr><th>#</th><th>名称</th><th>X 账号</th><th class="num">粉丝</th><th class="num">最近原创</th><th>所属／代表作</th><th>标签</th><th>发什么</th></tr></thead>
      <tbody>
        {"".join(rows_vendor)}
      </tbody>
    </table>
  </div>
  <p class="legend">剧作者 8 · 导演 3 · 代表 3。导演这一栏只有 3 个不是漏查——galgame 导演普遍不开个人号（下條水月、三舛啓、藤原将、高橋龍也、吉川浩司、飯田和彦都没找到可用账号）。原表里两个悬而未决的已处理：<code>@youtan0309</code> 已在 10-29 作为信息号入册启用，<code>@uitachibana3</code>（5,444 粉，主号指向 <code>@uitachibana4</code>）仍未采信、也没进这两份名单。</p>

  <h2 id="gaps">6 还差什么（要不要动，你拍板）</h2>
  <div class="note-box">
    <p><strong>一、厂商侧个人号 14 条还停在报告里。</strong>剧作者 / 导演 / 代表这批人不进名单，日报里就引不到「某人说」的原话。你说过之后再补，所以现在只留表；补的时候除了加 role，还要给每条挂 <code>max_items: 1</code>。</p>
    <p><strong>二、信息号候选还有 {len(info_personal) + len(info_platform)} 条。</strong>其中 <code>@getchucom</code>（发售日历）与 <code>@bugbug_info</code>（新作介绍）标了「优先」，但都量大、要单独配 filter。加进来会让 Galgame 版从 {len(makers) + len(info_live)} 涨到 {len(makers) + len(info_live) + 2}，仍在 <code>update-galgame.yml</code> 的 20 分钟余量内。</p>
    <p><strong>三、<code>other</code> 分类两份都空置。</strong>两份 <code>categories</code> 都登记了 <code>other</code>（未归类），实际 0 条。留着是给「以后说不清归哪类」的号兜底，不用急着删。</p>
    <p><strong>四、名单顶层的 <code>note</code> 要跟着改。</strong>两份 JSON 的 <code>note</code> 已按新口径重写（声优版写「社团全部 active」、Galgame 版写「信息号先启用三个」）。以后改名单结构，记得同步这句，否则下次看名单的人会被旧说明误导。</p>
  </div>

  <footer>
    <p>一次性产物，放在 <code>README/reports/</code>，不参与构建、不被站点链接。名单正本是 <code>src/config/daily-roster.json</code> 与 <code>src/config/daily-roster-galgame.json</code>；本页由 <code>scripts/build_roster_overview.py</code> 生成，改了名单重跑即可。</p>
  </footer>
</div>
<script>
(function () {{
  var q = document.getElementById('q');
  var out = document.getElementById('q-count');
  var rows = Array.prototype.slice.call(document.querySelectorAll('tbody tr'));
  var rowsWithData = rows.filter(function (r) {{ return r.hasAttribute('data-s'); }});
  function run() {{
    var v = (q.value || '').trim().toLowerCase();
    var hit = 0;
    rowsWithData.forEach(function (r) {{
      var ok = !v || r.getAttribute('data-s').indexOf(v) !== -1;
      r.style.display = ok ? '' : 'none';
      if (ok) hit++;
    }});
    out.textContent = v ? (hit + ' / ' + rowsWithData.length + ' 条匹配') : (rowsWithData.length + ' 条');
  }}
  q.addEventListener('input', run);
  run();
}})();
</script>
</body>
</html>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(html_out)
    print("[roster] 两版在册 %d（声优版 %d / Galgame 版 %d，在用 %d、待选 %d）＋ 未入册候选 %d → %s"
          % (len(accounts), len(seiyuu) + len(circles), len(makers) + len(info_live),
             len(live), len(dormant), n_candidates, out_path.relative_to(ROOT)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导出日报名单的「在用 / 待选」总表")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    build(parser.parse_args().out)
