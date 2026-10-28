#!/usr/bin/env python3
"""生成「转发条目怎么落地」的方案对比页（一次性报告，不参与站点构建）。

用法：
    python build_rt_compare.py
产物：README/reports/daily-rt-handling.html

排版不靠手抄：直接内联 dist 里构建出来的 CSS，报告里的样张用站点真实类名
（.prose / .daily-block / .daily-roster），所以看到的就是线上日报页的样子。
"""
from __future__ import annotations

import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSS = next((ROOT / "dist" / "_astro").glob("BaseLayout.*.css")).read_text(encoding="utf-8")
OUT = ROOT / "README" / "reports" / "daily-rt-handling.html"

E = html.escape


def person(name: str, handle: str, summary: str) -> str:
    return (
        "<li>"
        f'<a class="daily-roster__name" href="https://x.com/{E(handle)}" target="_blank" rel="noopener noreferrer">{E(name)}</a>'
        '<span class="daily-roster__sep">：</span>'
        f"<span>{summary}</span>"
        "</li>"
    )


# ---------------------------------------------------------------- 方案 A 数据
A_ROWS = [
    person(
        "みたかりん", "mitakarin",
        "在 M3 帮 solfa 摊位，以「妹ぱらだいす！3」七瀬ざくろ的身份参与。"
        "<em>转发提到了</em>有听众因为她的歌声买下她参与的两部作品，也有人专门说「喜欢 みたかりん 的歌声」，"
        "另有 solfa 摊位设营完成的消息。",
    ),
    person(
        "柚木つばめ", "re_re_tsubame",
        "生日活动「FIRST FLIGHT」收官，公开歌单与幕后，周边在 BOOTH 开卖。"
        "<em>转发提到了</em>《AshArms》B-36B「ピースメイカー」新皮肤连发四条（CV 是她本人），"
        "以及有听众解释昨天直播落泪的原因。",
    ),
    person(
        "大山チロル", "chiroru_o_",
        "<em>当日没有原创发言。</em><em>转发提到了</em> 8 条互不相干的内容：为ストグラ活动做的服装、"
        "把自制 3D 角色做成 MMD 舞蹈、一个「把人做成天妇罗」的 VRChat 世界、"
        "一款 VRChat 自动拍摄工具上架、两张 ASMR 作品放上 BOOTH……",
    ),
    person(
        "御崎ひより", "hiyori_voice",
        "<em>转发提到了</em>三条「收到周边」的晒单——有人收到夏季周边后立刻装进卡套，"
        "有人晒了 2026 夏季周边。",
    ),
    person(
        "歩サラ", "potte1919",
        "新作预告收藏破 200，11 月中旬发售。<em>转发提到了</em>新作封面由 Mishiro_szk 执笔，"
        "以及有人说那部作品里的挠痒桥段是自己加的。",
    ),
    person(
        "浪実みお", "namimimiobot",
        "说明天 21 点会待在聊天室里。<em>转发提到了</em>卡牌游戏 YouTuber 的标题党吐槽、"
        "某位创作者只在拍片时化妆的讨论，以及一段别人的争论。",
    ),
]

# ---------------------------------------------------------------- 方案 B 数据
B_ROWS = [
    person("みたかりん", "mitakarin", "在 M3 帮 solfa 摊位，以「妹ぱらだいす！3」七瀬ざくろ的身份参与。"),
    person("柚木つばめ", "re_re_tsubame", "生日活动「FIRST FLIGHT」收官，公开歌单与幕后，周边在 BOOTH 开卖。"),
    person("歩サラ", "potte1919", "新作预告收藏破 200，11 月中旬发售。"),
    person("浪実みお", "namimimiobot", "说明天 21 点会待在聊天室里。"),
]

B_SIDE = [
    (
        "聊人",
        "转发里最多的是晒单与表白。有听众因为 みたかりん 的歌声买下她参与的两部作品，"
        "也有人专门发一条说「喜欢她的歌声」；一位画师接下 歩サラ 新作的封面，"
        "另一位则说那部作品里的挠痒桥段是自己加的。御崎ひより 的夏季周边陆续到货，三条晒单都拍了照。"
        "还有人把 柚木つばめ 生日 live 上没做成的造型在家补拍了一遍。",
    ),
    (
        "聊音声",
        "《AshArms》连发四条公开 B-36B「ピースメイカー」的新皮肤，CV 是 柚木つばめ。"
        "一部全年龄作品被推荐「低音很舒服，还能反过来宠回去」；有社团把新作定在 10 月 31 日，"
        "也有社团庆祝某作发售半年仍卖得像新作。天知遥 帮卖的「大罪魔女の晩餐会」在 BOOTH 开通贩，"
        "另有社团把两张 ASMR 作品放上了 BOOTH。",
    ),
    (
        "聊事情",
        "M3 本身占了多数：第一展示场 G-21a、第二展示场「う-39b」与二楼陆续报出设营完成，"
        "15:35 闭会，下一届时间一并公布。此外还有卡拉 OK 联合直播、withny 的排期预告、"
        "Ci-en 第 16 回秘密杂谈更新。日常一侧杂得多——有人带兔子玩偶去京都赛马场玩了一天，"
        "有人排了一周的收听清单，有人吐槽卡牌游戏 YouTuber 的标题党，"
        "也有人只是预报 10 月 28 日札幌可能下初雪。",
    ),
]

HIGHLIGHT = (
    "柚木つばめ 的生日活动「FIRST FLIGHT」办完，mini live 上首唱了新曲 Chun-pi Tune（作曲 manate），"
    "她把歌单和幕后一起发了出来；周边在 BOOTH 开卖，库存要等周二重新点过才准。"
    "同一天 AshArms 公开的新皮肤里，B-36B「ピースメイカー」的语音也是她配的。"
)
WORKS = (
    "今天发布与预告的密度很高。伊ヶ崎綾香 的新作因服务器故障没能按期上架，她专门为此道歉，"
    "同一天还公布了 11/30–12/13 在 JAM Akihabara 的合作咖啡。御子柴泉 出演、葉月ゆう 主创的"
    "《シネ連呼／唾吐き》开始贩售，御子柴泉 自己转了这条。歩サラ 预告了 potte 新作，与北見六花 共演…"
)
INTERACTIONS = [
    "涼花みなせ 中途加入 雲八はち 的生日直播串场；逢坂成美 也发文道贺。",
    "歩サラ 的 potte 新作预告发出后，小倉結衣 转发说「六花ちゃんとコラボ」，两人隔空对上了。",
]


def block(title: str, body: str, *, klass: str = "") -> str:
    cls = f"daily-block {klass}".strip()
    return f'<section class="{cls}"><h2>{E(title)}</h2>{body}</section>'


def screen(inner: str, *, label: str, note: str) -> str:
    return f"""
      <figure class="screen">
        <figcaption class="screen__bar"><span class="screen__dot"></span>{E(label)}
          <span class="screen__note">{E(note)}</span></figcaption>
        <div class="screen__body"><div class="prose">{inner}</div></div>
      </figure>"""


def common_sections() -> str:
    hl = "".join(f"<p>{E(HIGHLIGHT)}</p>")
    works = f"<p>{E(WORKS)}</p>"
    inter = "<ul>" + "".join(f"<li>{E(t)}</li>" for t in INTERACTIONS) + "</ul>"
    return (
        block("今日看点", hl)
        + block("作品动态", works)
        + block("互动", inter)
    )


variant_a = screen(
    common_sections()
    + block("详细", '<ul class="daily-roster">' + "".join(A_ROWS) + "</ul>"),
    label="方案 A · 只归名",
    note="详细栏 65 行（节选 6 人）",
)

variant_b = screen(
    common_sections()
    + block("详细", '<ul class="daily-roster">' + "".join(B_ROWS) + "</ul>")
    + block(
        "旁及",
        "".join(f"<h3>{E(t)}</h3><p>{E(p)}</p>" for t, p in B_SIDE),
    ),
    label="方案 B · 只开主题栏",
    note="详细栏 61 行（节选 4 人）+ 新增一栏三段",
)

TABLE_ROWS = [
    ("详细栏行数", "65 行", "61 行"),
    ("转发内容去哪了", "并进转发者那一行，句首写「转发提到了」", "集中到「旁及」一栏，按主题三段"),
    ("能不能看出是谁转的", "能，明确挂在转发者名下", "不能，只按主题合并"),
    ("原发账号（品牌号／社团号）", "不进 people，只作为句子里的宾语出现", "不进 people，名字隐去，写成「有社团」「有听众」"),
    ("重度转发者那一行长什么样", "变成杂项清单（大山チロル 8 条互不相干）", "不受影响，本人没有原创就不出现"),
    ("每期编辑成本", "30 人各改写一句，要逐条读转发原文", "通读一遍转发原文，写 3 段"),
    ("丢掉的信息", "几乎没有", "「谁转了谁的什么」这一层关系"),
]

rows = "".join(
    f"<tr><th>{E(a)}</th><td>{E(b)}</td><td>{E(c)}</td></tr>" for a, b, c in TABLE_ROWS
)

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>转发条目怎么落地 · 方案对比（261025 实测）</title>
<style>{CSS}</style>
<style>
  :root {{ color-scheme: light; }}
  body {{ background: #fafafa; color: #1a1a1a; margin: 0;
         font-family: "Inter","PingFang SC","Microsoft YaHei",system-ui,sans-serif; }}
  .wrap {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px 96px; }}
  .lede {{ border-bottom: 1px solid #e5e5e5; padding-bottom: 28px; margin-bottom: 36px; }}
  .lede h1 {{ font-size: 1.75rem; line-height: 1.35; margin: 0 0 12px; font-weight: 600; letter-spacing: -0.01em; }}
  .lede p {{ color: #555; line-height: 1.75; margin: 8px 0; font-size: 0.95rem; }}
  .kpis {{ display: flex; flex-wrap: wrap; gap: 28px; margin-top: 22px; }}
  .kpi b {{ display: block; font-size: 1.5rem; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .kpi span {{ display: block; font-size: 0.78rem; color: #767676; margin-top: 4px; letter-spacing: 0.02em; }}
  h2.sec {{ font-size: 1.05rem; font-weight: 600; margin: 48px 0 6px; }}
  p.sec-note {{ color: #767676; font-size: 0.85rem; line-height: 1.7; margin: 0 0 18px; }}
  .screen {{ margin: 0; border: 1px solid #e5e5e5; border-radius: 6px; background: #fff; overflow: hidden; }}
  .screen__bar {{ display: flex; align-items: center; gap: 8px; padding: 9px 14px;
                  border-bottom: 1px solid #e5e5e5; background: #f7f7f7;
                  font-size: 0.78rem; color: #555; letter-spacing: 0.02em; }}
  .screen__dot {{ width: 7px; height: 7px; border-radius: 50%; background: #cfcfcf; }}
  .screen__note {{ margin-left: auto; color: #767676; }}
  .screen__body {{ padding: 40px 24px 56px; }}
  .screen__body .prose {{ max-width: 38rem; margin: 0 auto; }}
  .screen__body .prose h2 {{ font-size: 1.05rem; }}
  .screen__body .prose h3 {{ font-size: 0.95rem; }}
  .screen__body .prose em {{ font-style: normal; color: #767676; }}
  table.cmp {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 8px;
               background: #fff; border: 1px solid #e5e5e5; border-radius: 6px; overflow: hidden; }}
  table.cmp th, table.cmp td {{ text-align: left; padding: 12px 14px; border-bottom: 1px solid #f0f0f0;
                                 vertical-align: top; line-height: 1.65; }}
  table.cmp tr:last-child th, table.cmp tr:last-child td {{ border-bottom: 0; }}
  table.cmp thead th {{ background: #f7f7f7; font-weight: 600; font-size: 0.82rem; color: #555; }}
  table.cmp tbody th {{ font-weight: 500; color: #555; width: 22%; }}
  .concl {{ margin-top: 40px; padding: 22px 24px; background: #fff; border: 1px solid #e5e5e5;
            border-radius: 6px; }}
  .concl h2 {{ font-size: 0.95rem; margin: 0 0 10px; }}
  .concl p {{ font-size: 0.9rem; line-height: 1.8; color: #333; margin: 8px 0; }}
  .concl strong {{ font-weight: 600; }}
</style>
</head>
<body>
<div class="wrap">
  <header class="lede">
    <h1>转发条目怎么落地：两个方案，同一份数据</h1>
    <p>样本是已发布的第一期 <code>261025</code>（2026-10-25，127 人）。名单外的 66 个 handle 全部是
       <b>名单内成员的转发</b>，转发者 100% 可读（<code>metadata.retweeted_by</code>），没有一条是「无法读取转发者」。
       所以这次要比的不是「读不读得到」，而是这批内容<b>放在哪一栏、以谁的名义说</b>。</p>
    <p>下面两块的排版不是示意图：内联的是线上构建出来的 CSS，样张用的是日报页真实类名，
       字号、行高、两端对齐、姓名链接的颜色都和 <code>/daily/261025/</code> 一致。</p>
    <div class="kpis">
      <div class="kpi"><b>81</b><span>名单外条目（全部为转发）</span></div>
      <div class="kpi"><b>66</b><span>因此多出来的 people 行</span></div>
      <div class="kpi"><b>30</b><span>实际转发的人数</span></div>
      <div class="kpi"><b>46%</b><span>详细栏文字其实不是本人的话</span></div>
    </div>
  </header>

  <h2 class="sec">方案 A · 只归名</h2>
  <p class="sec-note">把转发内容并到转发者名下，句首写「转发提到了」。信息最全，但重度转发者那一行会变成清单。</p>
  {variant_a}

  <h2 class="sec">方案 B · 只开主题栏</h2>
  <p class="sec-note">转发条目一律不进「详细」，集中到新开的一栏，按「聊人 / 聊音声 / 聊事情」三段概括，
     原发账号的名字隐去（写成「有听众」「一位画师」「有社团」）。</p>
  {variant_b}

  <h2 class="sec">逐项对比</h2>
  <table class="cmp">
    <thead><tr><th></th><th>方案 A · 只归名</th><th>方案 B · 只开主题栏</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>

  <div class="concl">
    <h2>看完这两块之后的判断</h2>
    <p><strong>数据是偏向 B 的。</strong>详细栏原有 2149 字，其中 997 字（46%）来自转发、不是本人说的话；
       把它们挂回转发者名下，等于让 30 个人的一句话里混进半句别人的内容。方案 A 在「大山チロル」这类
       重度转发者身上会直接失效——当天没有原创发言，整行变成 8 条互不相干的 VRChat 杂项。</p>
    <p><strong>但 A 保住了 B 丢掉的那层信息：</strong>谁转了谁的什么。如果以后要做「扩散度」「谁在帮谁推」，
       这层关系是原料，B 之后就查不回来了——除非它同时留在数据里（不进页面，但进 report.json）。</p>
    <p><strong>所以推荐 B，前提是 A 的那层关系不丢在数据层：</strong>转发条目在 <code>report.json</code> 里保留
       <code>retweeted_by</code> 与 <code>original_author</code>，页面上只呈现三段概括。这样哪天想改回 A，
       不用重新抓数据。</p>
  </div>
</div>
</body>
</html>
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT} ({len(HTML):,} bytes)")
