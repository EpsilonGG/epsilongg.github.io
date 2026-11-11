"""试验性 · media sidecar 回填（只写 `weekly/out/`，只读其它一切）。

## 为什么需要

2026-11-10 查明：X-Reader 的 `parsers/nitter_rss.py` 只认 `<enclosure>`，
而现役 Nitter 实例把附件放在 RSS CDATA `<description>` 的
`<img src="https://pbs.twimg.com/media/...">` 里；`clean_html()` 又把标签全
剥掉。加上 `config.galgame.yaml` 的 routes 是 `[rss, html]` 且 runner 第一条
route 出记录就返回，会解析附件的 HTML route 几乎不跑 —— 于是 40 天历史切片
里 `media[]` 几乎全空（全库 4359 条 rss 行 0 张图）。

修根因要改独立的 `EpsilonGG/X-Reader` 仓（方案 A，需授权）。这里做方案 C：
**不改原始切片、不改 X-Reader、不改日报管线**，只对「候选源推」查一次公开
API，把图片 URL 落成可复用 sidecar，交给 `image_preview.py` 合并读取。

## 边界

* sidecar 只补 `media` 元数据，**不新增、不改写任何一条源推**；
* 键仍用 `corpus.json:source_refs` 的 `x:<tweet_id>`，URL 逐字取自 source_refs；
* 已查过的键（含「确认无图」）默认不重复联网，`--refresh` 才重查；
* 失败也落盘并记原因，避免每次 build 反复打同一个坏 URL；
* 本模块联网只用于探针与量体积，产物是 JSON，不是图片库。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .config import OUT, WORK, load_rules, read_json, write_json
from .identity import Identity

_API_DEFAULT = "https://api.vxtwitter.com"
_CONTENT_LENGTH = re.compile(rb"content-length:\s*(\d+)", re.I)
_STATUS = re.compile(r"x\.com/([^/]+)/status/(\d+)", re.I)


def sidecar_path(rules: dict) -> Path:
    cfg = rules.get("image_preview", {}).get("media_backfill") or {}
    return OUT / str(cfg.get("sidecar") or "media-sidecar.json")


def load_sidecar(rules: dict) -> dict:
    path = sidecar_path(rules)
    if not path.is_file():
        return {"schema_version": 1, "source": "vxtwitter", "entries": {}}
    try:
        data = read_json(path)
    except Exception:
        return {"schema_version": 1, "source": "vxtwitter", "entries": {}}
    if not isinstance(data.get("entries"), dict):
        data["entries"] = {}
    return data


def save_sidecar(rules: dict, sidecar: dict) -> Path:
    path = sidecar_path(rules)
    sidecar["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(path, sidecar)
    return path


def candidate_keys(rules: dict, data: dict, corpus: dict, scope: str = "candidates") -> list[str]:
    """待回填的源推键。

    candidates = 第 1/2 档 + 作品情报 + 已检出作品的小条目所引用的源推
                 （也就是图片栏目唯一可能合格的池子，实测 137 条）；
    all        = 全部 source_refs（规则放宽到别的栏目时再跑）。
    """
    refs = corpus["source_refs"]
    if scope == "all":
        return sorted(k for k, v in refs.items()
                      if _STATUS.search(str(v.get("url") or "")))
    tiers = {int(t) for t in ((rules.get("image_preview") or {}).get("tiers") or [1, 2])}
    identity = Identity(rules)
    keys: set[str] = set()
    for section in data["sections"]:
        if section["column"] != WORK or identity.tier_for(section["label"]) not in tiers:
            continue
        for item in section["items"]:
            if item.get("group_label") in ("", "未标注作品") or not item.get("work_canonical"):
                continue
            for src in item["sources"]:
                k = str(src.get("key") or "")
                if k in refs and _STATUS.search(str(refs[k].get("url") or "")):
                    keys.add(k)
    return sorted(keys)


def _curl(args: list[str], timeout: int = 15) -> str:
    env = dict(os.environ)
    env.setdefault("https_proxy", "http://127.0.0.1:7897")
    env.setdefault("HTTPS_PROXY", "http://127.0.0.1:7897")
    out = subprocess.run(["curl", "-s", "--max-time", str(timeout), *args],
                         capture_output=True, env=env, timeout=timeout + 4)
    return out.stdout.decode("utf-8", "replace")


def probe_one(key: str, url: str, api: str) -> dict:
    """查一条推文的图片直链。只认 type=image，video / gif 留给以后决定。"""
    match = _STATUS.search(url)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not match:
        return {"images": [], "ok": False, "error": "非 x.com/status URL", "checked_at": now}
    endpoint = f"{api.rstrip('/')}/{match.group(1)}/status/{match.group(2)}"
    try:
        raw = _curl([endpoint])
        payload = json.loads(raw)
    except Exception as exc:
        return {"images": [], "ok": False, "error": f"probe failed: {str(exc)[:100]}",
                "checked_at": now}
    images: list[str] = []
    for media in payload.get("media_extended") or []:
        if not isinstance(media, dict):
            continue
        if str(media.get("type") or "").lower() != "image":
            continue
        u = str(media.get("url") or "")
        if u and u not in images:
            images.append(u)
    if not images:
        # 有些响应只给 mediaURLs，没有 media_extended；类型未知，按图片 URL 收。
        for u in payload.get("mediaURLs") or []:
            u = str(u or "")
            if "pbs.twimg.com/media/" in u and u not in images:
                images.append(u)
    return {"images": images, "ok": True, "has_media": bool(payload.get("hasMedia")),
            "checked_at": now}


def backfill(rules: dict, data: dict, corpus: dict, *, scope: str = "candidates",
             refresh: bool = False, known: set[str] | None = None,
             workers: int | None = None) -> tuple[dict, dict]:
    """查候选源推 → 落 sidecar。返回 (sidecar, 统计)。"""
    cfg = rules.get("image_preview", {}).get("media_backfill") or {}
    api = str(cfg.get("api") or _API_DEFAULT)
    workers = int(workers or cfg.get("workers") or 6)
    refs = corpus["source_refs"]
    keys = candidate_keys(rules, data, corpus, scope)
    known = known or set()
    sidecar = load_sidecar(rules)
    sidecar["schema_version"] = 1
    sidecar["scope"] = scope
    sidecar["api"] = api
    entries = sidecar["entries"]

    todo = [k for k in keys
            if k not in known
            and (refresh or k not in entries)]
    fetched = 0
    if todo:
        def work(k: str) -> tuple[str, dict]:
            return k, probe_one(k, str(refs[k]["url"]), api)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for k, result in pool.map(work, todo):
                entries[k] = result
                fetched += 1

    hits = {k: v for k, v in entries.items() if v.get("images")}
    stats = {
        "scope": scope,
        "candidate_keys": len(keys),
        "already_known_from_crawl": len(set(keys) & known),
        "probed_this_run": fetched,
        "sidecar_entries": len(entries),
        "sidecar_hits": len(hits),
        "sidecar_images": sum(len(v["images"]) for v in hits.values()),
        "probe_errors": sum(1 for v in entries.values() if not v.get("ok")),
        "refresh": bool(refresh),
    }
    save_sidecar(rules, sidecar)
    return sidecar, stats


def sidecar_images(sidecar: dict) -> dict[str, list[str]]:
    """sidecar → {key: [图片直链]}，坏记录不计。"""
    return {k: list(v.get("images") or [])
            for k, v in sidecar.get("entries", {}).items()
            if isinstance(v, dict) and v.get("images")}


def measure_one(url: str) -> tuple[int, str]:
    """HEAD 取 Content-Length；拿不到就 GET 到 /dev/null 数下载字节。不落盘。"""
    try:
        raw = _curl(["-I", "-L", url], timeout=15)
        matches = _CONTENT_LENGTH.findall(raw.encode("utf-8", "replace"))
        if matches:
            return int(matches[-1]), "head"
    except Exception:
        pass
    try:
        raw = _curl(["-o", os.devnull, "-w", "%{size_download}", url], timeout=25)
        value = int(str(raw).strip() or 0)
        if value:
            return value, "get"
    except Exception:
        pass
    return 0, "failed"


def measure_images(urls: list[str], workers: int = 8) -> dict:
    """逐张量原图字节，用于「一期要多大存储」的实测算，不下载入库。"""
    unique = sorted(set(urls))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        sizes = list(pool.map(measure_one, unique))
    ok = [n for n, _ in sizes if n > 0]
    sizes.sort(key=lambda x: x[0])
    return {
        "measured_urls": len(unique),
        "measured_ok": len(ok),
        "measured_failed": len(unique) - len(ok),
        "total_bytes": sum(ok),
        "min_bytes": min(ok) if ok else 0,
        "max_bytes": max(ok) if ok else 0,
        "median_bytes": ok[len(ok) // 2] if ok else 0,
        "mean_bytes": round(sum(ok) / len(ok)) if ok else 0,
        "method": "HEAD Content-Length，缺失时 GET 到 /dev/null 数字节；不落盘",
        "by_head": sum(1 for _, m in sizes if m == "head"),
        "by_get": sum(1 for _, m in sizes if m == "get"),
    }


def estimate_webp(local_files: list[Path]) -> dict:
    """用站点已有的 sharp 把样本图按 600 / 960 / 原宽转成 WebP，实测压缩比。"""
    script = Path(__file__).with_name("webp_probe.mjs")
    if not script.is_file() or not local_files:
        return {"available": False, "sample": 0, "note": "没有 sharp 样本可测"}
    node = "node"
    try:
        out = subprocess.run([node, str(script), *[str(p) for p in local_files]],
                             capture_output=True, timeout=180)
        rows = json.loads(out.stdout.decode("utf-8", "replace") or "[]")
    except Exception as exc:
        return {"available": False, "sample": 0, "note": f"sharp 探针失败：{str(exc)[:120]}"}
    rows = [r for r in rows if isinstance(r, dict) and not r.get("error")]
    if not rows:
        return {"available": False, "sample": 0, "note": "sharp 未产出有效结果"}
    original = sum(int(r["original"]) for r in rows)
    widths = ("600", "960", "original_width")
    totals = {w: sum(int(r["sizes"][w]) for r in rows) for w in widths}
    return {
        "available": True,
        "sample": len(rows),
        "quality": 80,
        "sample_original_bytes": original,
        "sample_webp_bytes": {w: totals[w] for w in widths},
        "ratios": {w: round(totals[w] / original, 4) if original else 0 for w in widths},
        "note": "600 / 960 宽按 withoutEnlargement 缩放，原宽不缩放；WebP quality=80",
    }
