"""正式版导出：把 draft.md 出成 `weekly.md`（正文）与 `weekly.html`（带图）。

2026-11-10 用户裁决：以带图试稿的版式作为正式版版式。

* 只读 `out/draft.md` / `out/image-preview-data.json`；
* 只写 `out/weekly.md` 与 `out/weekly.html`；
* 不改 draft.md / draft-selected.md / filter.html / decisions.json / records.json。

分流已经在 `render` 里做完（新作第一栏、品牌动向并入作品情报），所以这里
不再解析、不再搬动栏目，只做两件事：原样落一份正文，以及给每条插一张首图后出 HTML。
"""
from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from pathlib import Path

from .config import OUT, read_json, write_text

# ---------- Markdown 解析 ----------

def _stats(text: str) -> dict:
    """按 `## 栏目` 数品牌与条目，用于页头徽章与命令行输出。"""
    from .config import DISPLAY_COLUMNS

    out = {"columns": {}}
    cur = ""
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out["columns"][cur] = {"brands": 0, "items": 0}
        elif cur and line.startswith("### "):
            out["columns"][cur]["brands"] += 1
        elif cur and line.startswith("- ") and not line.startswith("- （"):
            out["columns"][cur]["items"] += 1
    out["brands"] = sum(v["brands"] for v in out["columns"].values())
    out["items"] = sum(v["items"] for v in out["columns"].values())
    out["order"] = [c for c in DISPLAY_COLUMNS if c in out["columns"]]
    return out


# ---------- 图片 ----------

def _image_index() -> dict[str, list[dict]]:
    path = OUT / "image-preview-data.json"
    if not path.is_file():
        return {}
    data = read_json(path)
    idx: dict[str, list[dict]] = defaultdict(list)
    for row in data.get("eligible") or []:
        idx[str(row.get("game") or "")].append(row)
    return idx


def _insert_images(text: str, idx: dict[str, list[dict]],
                   *, prefer_local: bool = True) -> tuple[str, int]:
    """给每个游戏组的小条目补一张首图。

    `prefer_local=True` 给本地工作台（`weekly.html` 旁边就有 `images/`，用相对路径）；
    `prefer_local=False` 给线上正本：站点上没有那份 `images/` 目录，必须用
    `pbs.twimg.com` 的热链，碎图由 `<img onerror>` 退化成纯文字。
    """
    out: list[str] = []
    game = ""
    used: set[str] = set()
    n = 0
    for line in text.splitlines():
        if line.startswith("#### "):
            game = line[5:].strip()
            out.append(line)
            continue
        if line.startswith("- ") and game:
            body = line[2:]
            best = None
            for row in idx.get(game, []):
                sentence = str(row.get("sentence") or "")
                if not sentence or row["item_key"] in used:
                    continue
                if body.endswith(sentence):
                    if best is None or len(sentence) > len(str(best.get("sentence") or "")):
                        best = row
            out.append(line)
            if best is not None:
                used.add(best["item_key"])
                if prefer_local:
                    src = ((best.get("local_images") or [None])[0]
                           or (best.get("images") or [""])[0])
                else:
                    src = ((best.get("images") or [""])[0]
                           or (best.get("local_images") or [""])[0])
                link = (best.get("photo_links") or [""])[0]
                if src:
                    out.append(f"  [![首图]({src})]({link})")
                    n += 1
            continue
        out.append(line)
    return "\n".join(out).rstrip() + "\n", n


# ---------- HTML ----------

_CSS = """
:root{--bg:#fafafa;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e3e5e9;--blue:#1d4ed8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.85 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC","Microsoft YaHei",sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:28px 22px 80px}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:19px;margin:34px 0 12px;padding:6px 0 6px 10px;border-left:4px solid #111827;background:#f2f3f5;border-radius:0 6px 6px 0}
h3{font-size:15px;margin:22px 0 8px}
h4{font-size:14px;margin:14px 0 6px;color:#374151}
ul{margin:6px 0 10px;padding-left:22px}
li{margin:3px 0}
li img{display:block;max-width:100%;width:360px;border:1px solid var(--line);border-radius:6px;margin:6px 0 2px;background:#fff}
a{color:var(--blue);text-decoration:none}a:hover{color:#1e3a8a}
code{font:12px/1.7 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#f2f3f5;border-radius:4px;padding:1px 4px}
blockquote{margin:18px 0 0;padding:10px 14px;border-left:3px solid #9ca3af;background:#f6f7f9;border-radius:0 6px 6px 0;color:#374151;font-size:12px}
blockquote p{margin:2px 0}
hr{border:0;border-top:1px solid var(--line);margin:24px 0}
.note{border:1px solid var(--line);background:#fff;border-radius:6px;padding:10px 14px;font-size:13px;color:#374151;margin:10px 0 0}
.note b{color:var(--ink)}
.badge{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;color:var(--muted);margin:8px 6px 0 0}
.badge.warn{border-color:#9ca3af;color:#374151;background:#f6f7f9}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:30px}
"""

_INLINE = re.compile(
    r"\[!\[([^\]]*)\]\(([^)\s]+)\)\]\(([^)\s]+)\)"   # 可点击图片 [![alt](img)](link)
    r"|!\[([^\]]*)\]\(([^)\s]+)\)"                    # 图片
    r"|\[([^\]]+)\]\(([^)\s]+)\)"                     # 链接
    r"|\*\*([^*]+)\*\*"                               # 加粗
)


# 2026-11-11 上线裁决：首图是 X 的热链，随时可能 403 / 被删。
# 碎图必须退化成**纯文字**，而不是一个空洞的方框；图片外面那层 <a> 还指向
# 原推 /photo/1，所以退化后仍然点得回出处。属性里只用单引号，避免撑破 HTML 属性。
_IMG_ONERROR = (
    "this.onerror=null;var f=document.createElement('span');"
    "f.className='weekly-img-fallback';"
    "f.textContent='\uff3b\u56fe\u7247\u6682\u4e0d\u53ef\u7528\uff3d';"
    "this.replaceWith(f)"
)


def _img_tag(src: str, alt: str) -> str:
    return (f'<img src="{src}" alt="{alt}" loading="lazy" '
            f'onerror="{_IMG_ONERROR}">')


def _inline(text: str) -> str:
    def repl(m: re.Match) -> str:
        if m.group(1) is not None:
            src = html.escape(m.group(2), quote=True)
            link = html.escape(m.group(3), quote=True)
            alt = html.escape(m.group(1))
            return (f'<a href="{link}" target="_blank" rel="noopener">'
                    + _img_tag(src, alt) + '</a>')
        if m.group(4) is not None:
            return _img_tag(html.escape(m.group(5), quote=True),
                            html.escape(m.group(4)))
        if m.group(6) is not None:
            return (f'<a href="{html.escape(m.group(7), quote=True)}" '
                    f'target="_blank" rel="noopener">{m.group(6)}</a>')
        return f"<strong>{m.group(8)}</strong>"
    return _INLINE.sub(repl, text)


def _body_lines(md: str, *, anchors: bool = False) -> list[str]:
    """Markdown 正文 → HTML 片段。工作台与线上正本共用这一份渲染器。

    `anchors=True` 只给线上正本用：给每个 `##` 栏目补一个 `section-N` 的 id，
    站点页头那个「只收大标题」的目录才能跳转。工作台不需要（它有自己的筛选页），
    所以默认关掉，产物保持原样。
    """
    out: list[str] = []
    in_ul = False
    in_bq = False
    sections = 0

    def close() -> None:
        nonlocal in_ul, in_bq
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_bq:
            out.append("</blockquote>")
            in_bq = False

    for line in md.splitlines():
        s = line.strip()
        if not s:
            continue
        if s == "---":
            close()
            out.append("<hr>")
            continue
        if line.startswith("  [![") or (line.startswith("  ") and s.startswith("[![")):
            # 条目内的图片：塞进上一个 li
            if out and out[-1].endswith("</li>"):
                out[-1] = out[-1][:-5] + _inline(s) + "</li>"
            else:
                out.append(_inline(s))
            continue
        if s.startswith("# "):
            close()
            out.append(f"<h1>{_inline(s[2:])}</h1>")
            continue
        if s.startswith("## "):
            close()
            sections += 1
            anchor = f' id="section-{sections}"' if anchors else ""
            out.append(f"<h2{anchor}>{_inline(s[3:])}</h2>")
            continue
        if s.startswith("### "):
            close()
            out.append(f"<h3>{_inline(s[4:])}</h3>")
            continue
        if s.startswith("#### "):
            close()
            out.append(f"<h4>{_inline(s[5:])}</h4>")
            continue
        if s.startswith("> "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_bq:
                out.append("<blockquote>")
                in_bq = True
            out.append(f"<p>{_inline(s[2:])}</p>")
            continue
        if s.startswith("- "):
            if in_bq:
                out.append("</blockquote>")
                in_bq = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(s[2:])}</li>")
            continue
        close()
        out.append(f"<p>{_inline(s)}</p>")
    close()
    return out


def _to_html(md: str, title: str, subtitle: str, badges: list[str], note: str) -> str:
    """本地工作台用的独立 HTML：带内部版式说明 / 徽章 / 未定稿声明。"""
    badge_html = "".join(
        f'<span class="badge{" warn" if warn else ""}">{html.escape(t)}</span>'
        for t, warn in badges)
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>'
        f'<div class="wrap"><header><h1>{html.escape(title)}</h1>'
        f'<div class="badge" style="border:0;padding:0;color:#6b7280">{html.escape(subtitle)}</div>'
        f'{badge_html}</header><div class="note">{note}</div>'
        + "".join(_body_lines(md)) +
        '<footer>本地工作台版式 · 正式发布版见 /weekly/ · 由 weekly 管线生成</footer>'
        '</div></body></html>'
    )


def render_public_fragment(md: str) -> str:
    """站点正本用的**纯正文片段**：没有 doctype / head / 徽章 / 未定稿声明。

    页面标题、导语、元信息都由 Astro 页面按 `report.json` 渲染；这里只负责
    「栏目 → 品牌 → 游戏 → 条目」这一层，避免把工作台的内部说明带上线上。
    `##` 栏目带 `section-N` 锚点，与 `report.json:toc` 一一对应。
    """
    return ('<div class="weekly-body">'
            + "".join(_body_lines(md, anchors=True)) + '</div>')


# ---------- 入口 ----------

def build(rules: dict | None = None) -> dict:
    """出正式版两件产物：`weekly.md`（正文）与 `weekly.html`（带图）。"""
    from .config import DISPLAY_COLUMNS, GENERATOR, load_rules

    rules = rules or load_rules()
    draft = (OUT / "draft.md").read_text(encoding="utf-8")
    stats = _stats(draft)

    write_text(OUT / "weekly.md", draft)

    idx = _image_index()
    with_images, n_images = _insert_images(draft, idx)

    present = stats["order"] or list(DISPLAY_COLUMNS)
    dropped = [c for c in DISPLAY_COLUMNS if c not in present]
    note = (
        "<b>正式版版式</b>：栏目＝" + " → ".join(present) + "。"
        "品牌动向并入作品情报，品牌级条目落在该品牌下的「品牌动向」小标题里；"
        "带新作标签的游戏整组提到第一栏，组内条目不分到两栏。"
        "第四栏「B站动态」只读 B 站正本，按同一份游戏级规则命中的组上提到「新作」，其余留在本栏。"
        + (("本期 <b>" + " / ".join(dropped) + "</b> 一条都没剩，整节不显示。")
           if dropped else "")
        + "品牌中标题挂官号主页链接，点品牌名可到该官号；没有官号条目的品牌保持纯文本。"
        "官号条目只写正文、不写账号名或品牌名；非官号保留「主语：」，"
        "名单外账号主语用 <code>@handle</code> 并挂原推链接（可点，不加下划线）；"
        "品牌号转发的条目署被转发账号的真实名称并挂原推链接。"
        f"<br>本版<b>含图片</b>：每个源推只取第一张，共 {n_images} 张；"
        "点击图片可到原推 <code>/photo/1</code>。"
    )
    badges = [("正式版版式", False), ("本地工作台稿", True)]
    badges += [(c + " " + str(stats["columns"].get(c, {}).get("items", 0)) + " 条", False)
               for c in present]
    badges.append((f"带图 {n_images} 张", False))

    write_text(OUT / "weekly.html",
               _to_html(with_images, "Galgame 周报",
                        GENERATOR + " / " + " → ".join(present), badges, note))

    return {"stats": {**stats, "images": n_images},
            "outputs": ["weekly.md", "weekly.html"]}
