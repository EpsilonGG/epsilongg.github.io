"""试验性功能：图片栏目独立预览（不进初稿、不进筛选页）。

2026-11-10 用户要求：第一 / 第二档账号的游戏条目，若原推带图片，
增设一个「图片栏目」；先单独出一份 HTML 让人工判断要不要保留。

数据链路（全部只读）：
* `data/xreader/galgame/*.jsonl` —— 原始 `media` 图片信号
  （`out/clauses/*` 与 `corpus.json:source_refs` 都不带图片元数据）。
  `identity_key` 形如 `x:<tweet_id>`，与 `source_refs` 的键逐字对应。
* `weekly/out/media-sidecar.json` —— 2026-11-10 方案 C 回填：
  nitter RSS 解析器丢了 CDATA 里的 `<img>`，历史切片 `media[]` 几乎全空；
  sidecar 只补这些图片 URL（见 `media_backfill.py`），不新增源推。
* `weekly/out/filter-data.json` —— 三栏 / 品牌 / 游戏小标题 / 小条目
* `weekly/out/corpus.json`     —— 原推 URL（不拼造）
* `weekly/brand_rules.json` 的 `tiers` —— 第一 / 第二档判定

2026-11-10 补充裁决：**有图片的推文不论几张只取第一张**。原始 JSONL /
sidecar 里的全部 URL 照旧保留（不回写、不重新联网），这里只在生成预览时把
使用数组裁到 `[0:1]`，所以图片入口恒为原推 URL + `/photo/1`，不再出现
`/photo/2` 及以上。

缩略图用 `pbs.twimg.com` 直链，按 `cache_limit` best-effort 缓存几张样图到
`out/images/`（其余走外链 + 占位块；不进 `public/`、不写图片清单）。

产物：`weekly/out/image-preview.html` + `weekly/out/image-preview-data.json`
本模块不写 `draft.md` / `draft-selected.md` / `filter.html`，也不改动任何决策文件。
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.request
from pathlib import Path

from . import media_backfill
from .config import (OUT, WORK, load_rules, read_json, write_json, write_text)
from .identity import Identity

XREADER = Path(__file__).resolve().parent.parent / "data" / "xreader" / "galgame"
PHOTO_TAIL = re.compile(r"\d+$")


def load_media() -> tuple[dict[str, list[str]], dict]:
    """读原始 JSONL 的 media 字段；坏行跳过并计数（实测有 2 行未闭合字符串）。"""
    by_key: dict[str, list[str]] = {}
    stats = {"files": 0, "lines": 0, "bad_lines": 0, "image_tweets": 0,
             "images": 0, "video_only_tweets": 0}
    for path in sorted(XREADER.glob("*.jsonl")):
        stats["files"] += 1
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            stats["lines"] += 1
            try:
                row = json.loads(line)
            except Exception:
                stats["bad_lines"] += 1
                continue
            key = str(row.get("identity_key") or "").strip()
            images: list[str] = []
            has_video = False
            for media in row.get("media") or []:
                if isinstance(media, str):
                    if media.startswith("http"):
                        images.append(media)
                    continue
                if not isinstance(media, dict):
                    continue
                kind = str(media.get("type") or "").lower()
                url = str(media.get("url") or "")
                if kind == "image" and url:
                    images.append(url)
                elif kind == "video":
                    has_video = True
            if images:
                by_key[key] = images
                stats["image_tweets"] += 1
                stats["images"] += len(images)
            elif has_video:
                stats["video_only_tweets"] += 1
    return by_key, stats


def _photo_link(tweet_url: str, suffix: str, index: int) -> str:
    """第一张用配置里的 `/photo/1`；`first_image_only` 下 index 恒为 0。

    保留 index 形参是为了关掉开关后不必改调用点（多图依次 `/photo/2`…）。
    """
    if index == 0:
        return tweet_url.rstrip("/") + suffix
    tail = PHOTO_TAIL.sub(str(index + 1), suffix)
    return tweet_url.rstrip("/") + tail


def build_preview(rules: dict, data: dict, corpus: dict) -> tuple[dict, dict]:
    """挑出「第一/第二档 + 有作品名 + 原推带图」的小条目，并保留全库诊断。"""
    cfg = rules.get("image_preview") or {}
    tiers = {int(t) for t in (cfg.get("tiers") or [1, 2])}
    suffix = str(cfg.get("photo_suffix") or "/photo/1")
    media, media_stats = load_media()
    refs = corpus["source_refs"]
    identity = Identity(rules)
    decisions = read_json(OUT / "decisions.json")
    deleted = set(decisions.get("deleted_items") or [])

    # 原始抓取的 media 优先；sidecar 只补「抓取时丢掉的图片 URL」，
    # 且只接受 source_refs 里真实存在的键，绝不凭空造源推。
    provenance = {k: "crawl" for k in media}
    bf_cfg = cfg.get("media_backfill") or {}
    if bf_cfg.get("enabled", True):
        extra = media_backfill.sidecar_images(media_backfill.load_sidecar(rules))
        for key, images in extra.items():
            if key in refs and key not in media and images:
                media[key] = images
                provenance[key] = "backfill"
    media_stats["crawl_image_tweets"] = media_stats["image_tweets"]
    media_stats["crawl_images"] = media_stats["images"]
    media_stats["image_tweets"] = len(media)
    media_stats["images"] = sum(len(v) for v in media.values())
    media_stats["backfill_tweets"] = sum(1 for v in provenance.values() if v == "backfill")
    media_stats["backfill_images"] = sum(len(media[k]) for k, v in provenance.items()
                                         if v == "backfill")

    # 2026-11-10：不论图片多少只取第一张。诊断表要能看出「原有几张 / 用了几张」，
    # 所以先记 raw_by_key 再裁；sidecar 与原始切片完全不动。
    first_only = bool(cfg.get("first_image_only", True))
    raw_by_key = {k: len(v) for k, v in media.items()}
    before_images = sum(raw_by_key.values())
    if first_only:
        media = {k: v[:1] for k, v in media.items() if v}
    media_stats["raw_images"] = before_images
    media_stats["used_images"] = sum(len(v) for v in media.values())
    media_stats["dropped_extra_images"] = before_images - media_stats["used_images"]
    media_stats["images"] = media_stats["used_images"]

    eligible: list[dict] = []
    diagnostics: list[dict] = []
    in_corpus = set(media) & set(refs)
    for key, images in sorted(media.items()):
        ref = refs.get(key) or {}
        diagnostics.append({
            "key": key,
            "url": str(ref.get("url") or ""),
            "author": str(ref.get("author") or ""),
            "images": len(images),
            "raw_images": raw_by_key.get(key, len(images)),
            "media_source": provenance.get(key, "crawl"),
            "in_source_index": key in refs,
            "used_by_draft": False,
            "reason": "未进日报源索引" if key not in refs else "",
        })
    used_keys: set[str] = set()

    for section in data["sections"]:
        brand = section["label"]
        tier = identity.tier_for(brand)
        for item in section["items"]:
            is_game = (section["column"] == WORK
                       and item.get("group_label") not in ("", "未标注作品")
                       and bool(item.get("work_canonical")))
            for src in item["sources"]:
                key = str(src.get("key") or "")
                images = media.get(key) or []
                if not images:
                    continue
                used_keys.add(key)
                if key not in in_corpus:
                    continue
                tweet_url = str(src.get("url") or "") or str((refs.get(key) or {}).get("url") or "")
                reasons = []
                if not is_game:
                    reasons.append("非游戏条目（或无作品名）")
                if tier not in tiers:
                    reasons.append(f"第 {tier} 档（只放 {sorted(tiers)} 档）")
                photo_links = [_photo_link(tweet_url, suffix, i)
                               for i in range(len(images))] if tweet_url else []
                entry = {
                    "item_key": item["key"], "section_key": section["key"],
                    "column": section["column"], "brand": brand, "tier": tier,
                    "game": item.get("group_label") or "",
                    "sentence": str(item.get("sentence") or ""),
                    "in_default_draft": item["key"] not in deleted,
                    "tweet_key": key, "tweet_url": tweet_url,
                    "images": images, "photo_links": photo_links,
                    "raw_images": raw_by_key.get(key, len(images)),
                    "media_source": provenance.get(key, "crawl"),
                    "qualified": not reasons, "skip_reasons": reasons,
                }
                if not reasons:
                    eligible.append(entry)
                diagnostics.append({
                    "key": key, "url": tweet_url, "author": "",
                    "images": len(images),
                    "raw_images": raw_by_key.get(key, len(images)),
                    "in_source_index": True,
                    "media_source": provenance.get(key, "crawl"),
                    "used_by_draft": True,
                    "reason": "；".join(reasons) if reasons else "合格",
                    "brand": brand, "game": item.get("group_label") or "",
                })

    # 上面 diagnostics 里有重复（全库扫描 + 逐条扫描）；合并成一条一推文。
    merged: dict[str, dict] = {}
    for row in diagnostics:
        prev = merged.get(row["key"])
        if prev is None or (row["used_by_draft"] and not prev["used_by_draft"]):
            merged[row["key"]] = row
    diagnostics = sorted(merged.values(), key=lambda r: (not r["used_by_draft"], r["key"]))

    game_items_t12 = sum(
        1 for s in data["sections"]
        if s["column"] == WORK and identity.tier_for(s["label"]) in tiers
        for i in s["items"]
        if i.get("group_label") not in ("", "未标注作品") and i.get("work_canonical")
    )
    payload = {
        "schema_version": 2,
        "generator": "weekly/image-preview/2",
        "experimental": True,
        "integrated_into_draft": False,
        "integrated_into_filter": False,
        "rule": {
            "columns": [WORK], "tiers": sorted(tiers),
            "requires_game_title": True, "requires_image": True,
            "photo_suffix": suffix,
            "first_image_only": first_only,
            "image_signal": "原始 JSONL media[type=image].url ∪ out/media-sidecar.json（方案 C 回填）",
            "photo_link": ("每个源推只取第一张 → 原推 URL + /photo/1；sidecar 原始 URL 全保留"
                           if first_only else "原推 URL + /photo/N（N 从 1 起，按图片顺序）"),
            "backfill_enabled": bool(bf_cfg.get("enabled", True)),
        },
        "stats": {
            **media_stats,
            "source_refs": len(refs),
            "image_tweets_in_source_index": len(in_corpus),
            "game_items_tier_1_2": game_items_t12,
            "qualified_items": len(eligible),
            "qualified_images": sum(len(e["images"]) for e in eligible),
            "qualified_raw_images": sum(e.get("raw_images", len(e["images"]))
                                        for e in eligible),
            "qualified_from_crawl": sum(1 for e in eligible if e["media_source"] == "crawl"),
            "qualified_from_backfill": sum(1 for e in eligible if e["media_source"] == "backfill"),
        },
        "eligible": eligible,
        "diagnostics": diagnostics,
    }
    return payload, {"tiers": sorted(tiers), "suffix": suffix}


def cache_images(payload: dict, limit: int | None = None) -> int:
    """把前 `limit` 个合格条目的图片另存到 out/images/，让预览离线也能看。

    方案 C 回填后合格条目可能近百条，一次全缓存会把生成目录撑到几十 MB；
    预览只需要几张样图确认观感，其余走外链 + 占位块。`limit=0/None` 表示不限。
    纯 best-effort：网络不通就跳过；已存在的文件直接复用；只落在生成目录，
    不进 public/、不进 git 图片清单、不 publish。
    """
    folder = OUT / "images"
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or ""
    handlers = ([urllib.request.ProxyHandler({"http": proxy, "https": proxy})]
                if proxy else [])
    opener = urllib.request.build_opener(*handlers)
    count = 0
    for position, entry in enumerate(payload["eligible"]):
        local: list[str] = []
        if limit and position >= limit:
            entry["local_images"] = local
            continue
        for index, url in enumerate(entry["images"], start=1):
            suffix = ".jpg"
            match = re.search(r"\.(jpg|jpeg|png|webp)(?:\?|$)", url, re.I)
            if match:
                suffix = "." + match.group(1).lower()
            stem = re.sub(r"[^A-Za-z0-9_.-]", "_", entry["tweet_key"])
            name = f"{stem}-{index}{suffix}"
            target = folder / name
            if not target.is_file():
                try:
                    with opener.open(urllib.request.Request(
                            url, headers={"User-Agent": "Mozilla/5.0"}), timeout=12) as resp:
                        data = resp.read()
                    if not data:
                        continue
                    folder.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                except Exception:
                    continue
            if target.is_file():
                local.append("images/" + name)
                count += 1
        entry["local_images"] = local
    payload["stats"]["cached_images"] = count
    return count


def measure_storage(payload: dict, rules: dict) -> dict:
    """实测一期体积：sidecar 字节 + 每张原图 Content-Length + WebP 样本压缩比。

    量体积不落盘（HEAD 优先、GET 到 /dev/null 兜底），所以「一期要多大存储」
    是测出来的，不是拍脑袋按平均值估的。
    """
    cfg = (rules.get("image_preview") or {}).get("media_backfill") or {}
    urls = [u for e in payload["eligible"] for u in e["images"]]
    measured = media_backfill.measure_images(urls) if urls else {
        "measured_urls": 0, "measured_ok": 0, "measured_failed": 0,
        "total_bytes": 0, "min_bytes": 0, "max_bytes": 0,
        "median_bytes": 0, "mean_bytes": 0, "method": "无合格图片",
        "by_head": 0, "by_get": 0,
    }
    sidecar_path = media_backfill.sidecar_path(rules)
    sidecar_bytes = sidecar_path.stat().st_size if sidecar_path.is_file() else 0
    # 只数本次预览真正引用的本地样图（目录里可能还留着上一版的旧缓存）。
    referenced: list[Path] = []
    for entry in payload["eligible"]:
        for rel in entry.get("local_images") or []:
            path = OUT / rel
            if path.is_file() and path not in referenced:
                referenced.append(path)
    cached_bytes = sum(p.stat().st_size for p in referenced)
    sample_n = int(cfg.get("webp_sample") or 10)
    webp = media_backfill.estimate_webp(referenced[:sample_n])

    total = measured["total_bytes"]
    ratios = webp.get("ratios") or {}
    strategies = [
        {"name": "只存 sidecar（图片全走外链）", "bytes": sidecar_bytes,
         "note": "零图片存储；依赖 pbs.twimg.com 长期有效"},
        {"name": "本次预览实际落盘（样图缓存 + sidecar）", "bytes": sidecar_bytes + cached_bytes,
         "note": f"仅缓存 {payload['stats'].get('cached_images', 0)} 张样图"},
        {"name": "整期缓存全部原图", "bytes": sidecar_bytes + total,
         "note": f"{measured['measured_urls']} 张，实测 Content-Length 合计"},
    ]
    for key, label in (("600", "站点规范 600 宽 WebP"),
                       ("960", "站点规范 960 宽 WebP"),
                       ("original_width", "站点规范 原宽 WebP")):
        ratio = ratios.get(key)
        strategies.append({
            "name": label,
            "bytes": sidecar_bytes + round(total * ratio) if ratio else 0,
            "note": (f"按 {webp['sample']} 张样本实测压缩比 {ratio:.2f} 外推"
                     if ratio else "缺样本，未估算"),
        })
    # 这版测试稿是「Galgame 已有数据全集」，窗口比正常周报宽；
    # 给一个按 7 天线性折算的口径，避免把 12 期的体积当成一周。
    corpus_data = read_json(OUT / "corpus.json")
    issues = len(corpus_data.get("issues") or []) or 7
    factor = 7.0 / issues
    return {
        "measured_images": measured,
        "sidecar_bytes": sidecar_bytes,
        "window_issues": issues,
        "weekly_factor": round(factor, 4),
        "weekly_7day": {s["name"]: round(s["bytes"] * factor) for s in strategies},
        "sidecar_path": str(sidecar_path.relative_to(sidecar_path.parents[1])),
        "cached_sample_bytes": cached_bytes,
        "cached_sample_files": len(referenced),
        "webp": webp,
        "strategies": strategies,
        "per_52_issues": {
            s["name"]: round(s["bytes"] * 52 / 1024 / 1024, 1)
            for s in strategies
        },
        "note": ("一期＝本次 12 期日报合集的一版测试周报；52 期≈一年。"
                 + ("已按「每推只取第一张」裁过，" if payload["rule"].get("first_image_only") else "")
                 + "体积均为实测或按实测压缩比外推，不是估值表。"),
    }


_CSS = """
:root{--bg:#fafafa;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e3e5e9;--accent:#111827}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 80px}
header{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:20px}
h1{font-size:24px;margin:0 0 6px}
h2{font-size:17px;margin:28px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.sub{color:var(--muted);font-size:12px}
.badge{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;color:var(--muted);margin:8px 6px 0 0}
.badge.warn{border-color:#9ca3af;color:#374151;background:#f6f7f9}
.note{border-left:3px solid #9ca3af;padding:8px 12px;background:#f6f7f9;border-radius:0 6px 6px 0;font-size:13px;color:#374151;margin:12px 0}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.stat{border:1px solid var(--line);border-radius:6px;background:#fff;padding:8px 12px;min-width:132px}
.stat b{display:block;font-size:20px;line-height:1.3}
.stat span{font-size:11px;color:var(--muted)}
.card{border:1px solid var(--line);border-radius:6px;background:#fff;margin:12px 0;overflow:hidden}
.card-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:9px 12px;border-bottom:1px solid var(--line);background:#fcfcfd}
.card-head b{font-size:14px}
.tag{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:1px 6px;background:#fff}
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:0}
.cmp>div{padding:12px}
.cmp>div+div{border-left:1px solid var(--line);background:#fcfcfd}
.cmp h3{font-size:12px;color:var(--muted);font-weight:600;margin:0 0 8px}
.md{font:12px/1.75 ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-word;background:#f6f7f9;border:1px solid var(--line);border-radius:6px;padding:10px;margin:0}
.imgs{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.imgs a{display:block;border:1px solid var(--line);border-radius:6px;overflow:hidden;width:150px;text-align:center;background:#fff}
.imgs img{display:block;width:150px;height:110px;object-fit:cover;background:#f1f2f4}
.imgs .img-fallback{display:flex;width:150px;height:110px;align-items:center;justify-content:center;background:#f1f2f4;color:var(--muted);font-size:11px;text-align:center;padding:8px}
.imgs span{display:block;font-size:10px;color:var(--muted);padding:3px 4px;word-break:break-all}
.src{font-size:11px;color:var(--muted);word-break:break-all;margin-top:10px}
.src a{color:#1d4ed8;text-decoration:none}
.src a:hover{text-decoration:underline}
table{width:100%;border-collapse:collapse;font-size:12px;background:#fff}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;word-break:break-all}
th{background:#f6f7f9;font-weight:600}
tr.skip td{color:var(--muted)}
code{background:#f1f2f4;border-radius:4px;padding:1px 5px;font-size:12px}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:26px}
@media(max-width:760px){.cmp{grid-template-columns:1fr}.cmp>div+div{border-left:0;border-top:1px solid var(--line)}}
"""


def render_html(payload: dict, path: Path) -> str:
    s = payload["stats"]
    rule = payload["rule"]
    esc = html.escape
    badge_specs = [
        ("试验性 · 未决定是否保留", True),
        ("单独 HTML 预览", False),
        ("不进 draft.md", False),
        ("不进 filter.html", False),
        ("不写数据库 / 不入 git 图片", False),
        ("方案 C · sidecar 回填", True),
        (f"只放第 {' / '.join(map(str, rule['tiers']))} 档游戏条目", False),
    ]
    if rule.get("first_image_only"):
        badge_specs.append(("每推只取第一张 · 节约存储", False))
    badges = "".join(f'<span class="badge{" warn" if warn else ""}">{esc(t)}</span>'
                     for t, warn in badge_specs)
    stats = "".join(
        f'<div class="stat"><b>{value}</b><span>{esc(label)}</span></div>'
        for value, label in (
            (s["lines"], "扫描原始推文行"),
            (s["crawl_image_tweets"], "原始切片带图推文"),
            (s.get("backfill_tweets", 0), "★ sidecar 补回推文"),
            (s["image_tweets"], "合并后带图推文"),
            (s.get("backfill_images", 0), "★ sidecar 补回图片"),
            (s["game_items_tier_1_2"], "第 1/2 档游戏条目"),
            (s["qualified_items"], "★ 合格条目（会加图片栏）"),
            (s["qualified_images"], "★ 实际使用图片"),
            (s.get("qualified_raw_images", s["qualified_images"]), "合格条目原有图片"),
            (s.get("qualified_raw_images", s["qualified_images"]) - s["qualified_images"],
             "★ 合格条目省下的图"),
            (s.get("dropped_extra_images", 0), "全库裁掉的多余图"),
            (s.get("qualified_from_backfill", 0), "其中来自回填"),
            (s.get("cached_images", 0), "已缓存样图"),
        )
    )

    first_only = bool(rule.get("first_image_only"))
    cards = []
    for e in payload["eligible"]:
        current = "- " + e["sentence"]
        proposed = current
        cached = e.get("local_images") or []
        thumbs_list = []
        for i, (url, link) in enumerate(zip(e["images"], e["photo_links"])):
            shown = esc(cached[i] if i < len(cached) else url)
            # 属性用单引号包，JS 字符串用双引号；HTML 实体解码后仍是合法 JS 字面量。
            remote = html.escape(json.dumps(url), quote=True)
            caption = "photo/1 ↗ · 仅首张" if first_only else f"photo/{i + 1} ↗"
            thumbs_list.append(
                f'<a href="{esc(link)}" target="_blank" rel="noopener" title="打开原推图片">'
                f'<img src="{shown}" alt="原推图片 {i + 1}" loading="lazy" '
                f"onerror='imgFail(this,{remote})'>"
                f'<span>{caption}</span></a>'
            )
        thumbs = "".join(thumbs_list)
        md_links = " ".join(
            (f"[首图]({link})" if first_only else f"[图片{i + 1}]({link})")
            for i, link in enumerate(e["photo_links"])
        )
        direct = " ｜ ".join(e["images"])
        cards.append(
            '<div class="card"><div class="card-head">'
            f'<b>{esc(e["brand"])}</b><span class="tag">第 {e["tier"]} 档</span>'
            f'<span class="tag">{esc(e["column"])}</span>'
            f'<b>{esc(e["game"])}</b>'
            f'<span class="tag">{"在默认初稿里" if e["in_default_draft"] else "默认不入初稿"}</span>'
            f'<span class="tag">{"原始抓取" if e.get("media_source") == "crawl" else "sidecar 回填"}</span>'
            '</div><div class="cmp">'
            f'<div><h3>现在（无图片栏目）</h3><pre class="md">{esc(current)}</pre></div>'
            f'<div><h3>试验（增设图片栏目）</h3><pre class="md">{esc(proposed)}</pre>'
            f'<div class="imgs">{thumbs}</div>'
            f'<div class="src">图片栏目 Markdown 草案：<code>{esc(md_links)}</code></div>'
            '</div></div>'
            f'<div class="src" style="padding:0 12px 12px">原推：'
            f'<a href="{esc(e["tweet_url"])}" target="_blank" rel="noopener">{esc(e["tweet_url"])}</a>'
            f' ｜ 图片入口：{esc(e["photo_links"][0] if e["photo_links"] else "（无 URL）")}'
            f'<br>图片直链：{esc(direct)}'
            f'<br>出处键 <code>{esc(e["tweet_key"])}</code> · 小条目 <code>{esc(e["item_key"])}</code>'
            '</div></div>'
        )
    if not cards:
        cards.append('<div class="note">本窗口没有符合条件的条目。</div>')

    rows = []
    for d in payload["diagnostics"]:
        cls = "" if d["used_by_draft"] and d["reason"] == "合格" else ' class="skip"'
        url = d["url"] or "（无 URL）"
        rows.append(
            f'<tr{cls}><td><code>{esc(d["key"])}</code></td>'
            f'<td>{esc(d["author"] or "—")}</td>'
            f'<td>{d["images"]} / {d.get("raw_images", d["images"])}</td>'
            f'<td>{"抓取" if d.get("media_source") == "crawl" else "回填"}</td>'
            f'<td>{"是" if d["in_source_index"] else "否"}</td>'
            f'<td>{"是" if d["used_by_draft"] else "否"}</td>'
            f'<td>{esc(d.get("brand") or "—")} / {esc(d.get("game") or "—")}</td>'
            f'<td>{esc(d["reason"] or "—")}</td>'
            f'<td><a href="{esc(url)}" target="_blank" rel="noopener">{esc(url)}</a></td></tr>'
        )

    def _size(n: float) -> str:
        n = float(n or 0)
        if n >= 1024 ** 3:
            return f"{n / 1024 ** 3:.2f} GB"
        if n >= 1024 ** 2:
            return f"{n / 1024 ** 2:.2f} MB"
        if n >= 1024:
            return f"{n / 1024:.1f} KB"
        return f"{int(n)} B"

    storage = payload.get("storage") or {}
    storage_html = ""
    if storage:
        mi = storage["measured_images"]
        wr = (storage.get("webp") or {}).get("ratios") or {}
        st_rows = "".join(
            f'<tr><td>{esc(st["name"])}</td><td><b>{esc(_size(st["bytes"]))}</b></td>'
            f'<td>{esc(_size(st["bytes"] * 52))}</td>'
            f'<td>{esc(st["note"])}</td></tr>'
            for st in storage["strategies"]
        )
        storage_html = (
            '<h2>三、一期需要多大存储空间（实测）</h2>'
            '<div class="note">原图体积逐张用 <code>HEAD Content-Length</code> 量，'
            '拿不到就 GET 到 <code>/dev/null</code> 数下载字节，<b>不落盘</b>；'
            'WebP 档用站点已有 sharp 把样本图真转一遍再按实测压缩比外推。'
            '「一期」＝这版测试周报（12 期日报合集）；52 期≈一年。</div>'
            '<div class="stats">'
            f'<div class="stat"><b>{mi["measured_urls"]}</b><span>量测图片 URL</span></div>'
            f'<div class="stat"><b>{mi["measured_ok"]}</b><span>成功量到字节</span></div>'
            f'<div class="stat"><b>{esc(_size(mi["median_bytes"]))}</b><span>单张中位数</span></div>'
            f'<div class="stat"><b>{esc(_size(mi["max_bytes"]))}</b><span>最大单张</span></div>'
            f'<div class="stat"><b>{esc(_size(storage["sidecar_bytes"]))}</b><span>sidecar JSON</span></div>'
            f'<div class="stat"><b>{(storage.get("webp") or {}).get("sample", 0)}</b><span>WebP 实测样本</span></div>'
            '</div>'
            '<table><thead><tr><th>方案</th><th>一期</th><th>52 期</th><th>口径</th>'
            f'</tr></thead><tbody>{st_rows}</tbody></table>'
            '<div class="note">WebP 实测压缩比：'
            + " ／ ".join(f"{k} 宽 {v:.2f}×" for k, v in wr.items() if v) +
            '。sidecar 目前只覆盖候选源推；改 <code>scope: all</code> 会同时把 JSON 与流量放大。'
            f'<br><b>注意口径</b>：此测试稿是 {storage["window_issues"]} 期日报全集，'
            f'不是正常的 7 天一期；按 7/{storage["window_issues"]} 线性折算后，'
            + " ／ ".join(
                f'{esc(label)} <b>{esc(_size(storage["weekly_7day"].get(name, 0)))}</b>'
                for name, label in (
                    ("整期缓存全部原图", "原图"),
                    ("站点规范 600 宽 WebP", "600w WebP"),
                    ("站点规范 960 宽 WebP", "960w WebP"),
                )) +
            '／期。上表数字按测试稿原样计，未折算。'
            f' {esc(storage["note"])}</div>'
        )

    doc = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>图片栏目 · 试验性预览</title><style>{_CSS}</style></head>'
        '<body><div class="wrap"><header><h1>图片栏目 · 试验性预览</h1>'
        '<div class="sub">weekly / image-preview · 独立文档，仅供判断要不要保留</div>'
        f'{badges}</header>'
        '<div class="note"><b>规则</b>：只给「' + esc(WORK) + '」里第 '
        + ' / '.join(map(str, rule["tiers"])) + ' 档品牌、且挂了游戏小标题、且原推带图片的条目增设图片栏目。'
        '图片信号 = <code>data/xreader/galgame/*.jsonl</code> 的 '
        '<code>media[type=image].url</code> ∪ <code>out/media-sidecar.json</code>。'
        '<b>为什么需要回填</b>：X-Reader 的 nitter RSS 解析器只认 '
        '<code>&lt;enclosure&gt;</code>，现役实例却把附件放在 CDATA 的 '
        '<code>&lt;img&gt;</code> 里，历史切片 <code>media[]</code> 几乎全空；'
        '方案 C 只补图片 URL，不改原始切片、不改 X-Reader、不改日报管线。'
        '原推 URL 逐字取自 <code>corpus.json:source_refs</code>，图片入口为该 URL '
        f'+ <code>{esc(rule["photo_suffix"])}</code>。'
        + ('<b>本版规则：每个源推不论几张图只取第一张</b>，'
           '<code>/photo/N</code>（N ≥ 2）不再产出；sidecar 与原始 JSONL 仍保留全部图片 URL，'
           '所以以后改主意只要把 <code>first_image_only</code> 关掉即可，不用重新联网。'
           if first_only else '多图依次递增编号。') +
        '合格条目多，只把前几张样图缓存到 <code>weekly/out/images/</code>'
        '（仅生成目录、不进 <code>public/</code>），其余走外链 + 占位块，'
        '但图片入口链接始终可点。'
        '本页 <b>不改动</b> <code>draft.md</code>、<code>draft-selected.md</code>、'
        '<code>filter.html</code> 与任何决策文件。</div>'
        f'<div class="stats">{stats}</div>'
        '<h2>一、合格条目的「现在 / 试验」对照</h2>'
        + "".join(cards) +
        '<h2>二、带图推文诊断（为什么没进图片栏目）</h2>'
        '<div class="note">「抓取」＝原始 JSONL 里本来就有 <code>media[]</code>；'
        '「回填」＝方案 C sidecar 补回的 URL。「进了日报源索引」＝这条原推被 M1 '
        '分句索引引用过；「被初稿条目引用」＝它在 <code>filter-data.json</code> '
        '的某个小条目源索引里。回填只覆盖候选源推，所以表里仍会有大量「不在源索引」'
        '的抓取行，那是抓取池与成稿之间的正常落差。</div>'
        '<table><thead><tr><th>出处键</th><th>账号</th><th>图片数（用 / 原）</th><th>图片来源</th>'
        '<th>进源索引</th><th>被条目引用</th><th>品牌 / 作品</th><th>判定</th>'
        '<th>原推 URL</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        + storage_html +
        '<footer>试验产物 · 方案 C（只回填，不改抓取器）· 决定是否保留后再谈接入初稿与筛选页</footer>'
        '</div>'
        '<script>function imgFail(img, remote){'
        'img.onerror=null;'
        'if(remote && img.getAttribute("src").indexOf(remote)<0){img.src=remote;return;}'
        'var box=document.createElement("div");box.className="img-fallback";'
        'box.textContent="图片需联网 · 点开看原推";'
        'if(img.parentNode) img.parentNode.replaceChild(box,img);'
        '}</script>'
        '</body></html>'
    )
    write_text(Path(path), doc)
    return doc


def build(rules: dict | None = None) -> dict:
    """build 不联网：sidecar 已存在就复用；要刷新先跑 `backfill-media`。"""
    rules = rules or load_rules()
    data = read_json(OUT / "filter-data.json")
    corpus = read_json(OUT / "corpus.json")
    cfg = (rules.get("image_preview") or {}).get("media_backfill") or {}
    payload, _ = build_preview(rules, data, corpus)
    cache_images(payload, limit=int(cfg.get("cache_limit") or 0) or None)
    if cfg.get("measure_storage", True):
        payload["storage"] = measure_storage(payload, rules)
    write_json(OUT / "image-preview-data.json", payload)
    render_html(payload, OUT / "image-preview.html")
    return payload
