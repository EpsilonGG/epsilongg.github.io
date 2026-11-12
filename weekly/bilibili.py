"""B 站动态：周报的第二个数据源（只读展示层旁路）。

`data/bilibili/galgame/<JST 日>.jsonl` 是 B 站动态的正本，由
`scripts/bilibili_daily.py fetch` 落盘，键形如 `bilibili:<动态 id>`。
日报侧已经在「详细」里给 Galgame 版开了第三个栏目按钮；周报这一层
（2026-11-12 用户裁决）再开第四个展示栏「B站动态」。

为什么**不**把 B 站条目塞进 `weekly/corpus.py` 的 X 侧语料：

* 那套四类筛选 / 原推内容组去重 / 三值归栏有整套守恒断言与历史回测基线，
  混入一个没有 X handle、没有 M1 分句索引的数据源会把证据链全部漂掉；
* 用户明确要求「作品情报」「业界动向」两栏保持不变。

所以 B 站条目只在**展示层**单独成行：按当期日报覆盖的 JST 日逐日读正本，
每条压成单行，剥掉裸 URL（周报正文只允许 Markdown 链接）、归一书名号，
句首挂一条 `[发布者](B站原文)`；再按 `game_routing.new_work_labels()`
的**同一份**规则做游戏级「新作」过滤——命中的游戏整组进第一栏「新作」，
其余留在第四栏「B站动态」。

本模块不写 `data/daily/<期号>/report.json`，也不碰任何受保护的日报文件。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import brackets
from .config import BILIBILI, BILI_VIEW, NEW, WORK
from .corpus import day_of, norm_title
from .game_routing import NO_GAME, new_work_labels

# URL 只吃 URL 合法的 ASCII 字符，遇到中文标点 / 空白就停，不会把后面的正文吞掉。
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.I)
# 作品小标题只认『』：《》在周报里是乐曲 / 书籍，「」是角色或引语。
WORK_RE = re.compile(r"『([^』]{1,60})』")


def _display_title(title: str) -> str:
    """与 pipeline._display_title 同口径：拆散成对半角 `~`，避免渲染成 <del>。"""
    if "~" not in str(title or ""):
        return str(title or "")
    return " ".join(str(title).replace("~", " ~ ").split())


def clean_text(text: str, titles: set[str], bracket_cfg: dict) -> str:
    """一条 B 站动态 → 可直接进 `- ` 小条目的单行正文。

    三件事换行压平、剥裸 URL、书名号归一（归一函数幂等，check 会复核）。
    """
    parts: list[str] = []
    for raw in str(text or "").splitlines():
        line = URL_RE.sub("", raw.strip()).strip()
        line = re.sub(r"\s+", " ", line)
        if line:
            parts.append(line)
    joined = re.sub(r"\s+", " ", " ".join(parts)).strip()
    fixed, _ = brackets.normalize(joined, titles, bracket_cfg)
    return fixed.strip()


def source_files(issues: list[str]) -> list[tuple[str, Path]]:
    """当期 Galgame 日报覆盖的 JST 日 → 对应的 B 站正本文件（缺文件就跳过）。"""
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for issue in issues or []:
        day = day_of(issue)
        if day in seen:
            continue
        seen.add(day)
        path = BILIBILI / f"{day}.jsonl"
        if path.is_file():
            out.append((day, path))
    return out


def attach(corpus: dict, rules: dict) -> dict:
    """把 B 站正本以 `bilibili` / `bilibili_refs` 两个键挂到语料字典上。

    `bilibili_refs` 是给 `weekly check` 的外链白名单用的，`source_refs` 一个键都
    不加——X 侧源索引保持逐字不变。返回的是新字典，不改调用方手里的那份。
    """
    cfg = rules.get("bilibili") or {}
    rows: list[dict] = []
    refs: dict[str, dict] = {}
    if cfg.get("enabled", True):
        seen: set[str] = set()
        for day, path in source_files(corpus.get("issues") or []):
            for raw in path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                try:
                    rec = read_json_line(raw)
                except ValueError:
                    continue
                key = str(rec.get("identity_key") or "")
                url = str(rec.get("canonical_url") or "")
                content = str(rec.get("content") or "").strip()
                if not key.startswith("bilibili:") or not url or not content or key in seen:
                    continue
                seen.add(key)
                meta = rec.get("metadata") or {}
                publisher = str(rec.get("publisher") or "").strip() or "B站账号"
                handle = str(meta.get("account") or "")
                rows.append({
                    "key": key, "day": day, "url": url, "content": content,
                    "publisher": publisher, "handle": handle,
                    "published_at": str(rec.get("published_at") or ""),
                    "source_file": f"data/bilibili/galgame/{day}.jsonl",
                })
                refs[key] = {
                    "url": url, "text": content, "author": publisher,
                    "handle": handle, "published_at": str(rec.get("published_at") or ""),
                    "origin": "bilibili", "source_file": f"data/bilibili/galgame/{day}.jsonl",
                }
    rows.sort(key=lambda r: (r["day"], r["published_at"], r["key"]))
    payload = dict(corpus)
    payload["bilibili"] = rows
    payload["bilibili_refs"] = refs
    payload["stats"] = {**dict(corpus.get("stats") or {}), "bilibili_rows": len(rows)}
    return payload


def read_json_line(raw: str) -> dict:
    """单独抽出来方便测试造样本；坏行由调用方跳过，不让一条脏数据毁掉整期。"""
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def build_lines(corpus: dict, rules: dict) -> list[dict]:
    """B 站动态 → 出稿 / 筛选页共用的展示行（Python 与内联 JS 读同一份）。

    每行已经带好 `column / brand / gkey / glabel / text`，两端都不再计算，
    所以 JS-Python parity 不会因为多一栏而出现两套口径。
    """
    cfg = rules.get("bilibili") or {}
    if not cfg.get("enabled", True) or not BILI_VIEW:
        return []
    titles = set(corpus.get("titles") or [])
    bracket_cfg = rules.get("brackets") or {}
    prefix = str(cfg.get("brand_prefix") or "B站 · ")
    no_game = str(cfg.get("no_game_label") or "动态")

    rows: list[dict] = []
    for rec in corpus.get("bilibili") or []:
        text = clean_text(rec["content"], titles, bracket_cfg)
        if not text:
            continue
        match = WORK_RE.search(text)
        title = norm_title(match.group(1)) if match else ""
        glabel = f"『{_display_title(title)}』" if title else no_game
        # 路由用「未标注作品」这个名字，让 new_work_labels() 的 never 列表直接生效。
        route_game = glabel if title else NO_GAME
        brand = prefix + str(rec["publisher"])
        rows.append({
            "key": rec["key"], "day": rec["day"], "url": rec["url"],
            "publisher": rec["publisher"], "brand": brand,
            "gkey": "b:" + hashlib.md5(
                (brand + "|" + glabel).encode("utf-8")).hexdigest()[:12],
            "glabel": glabel, "group_label": route_game,
            "sentence": text,
            "text": "- [" + str(rec["publisher"]) + "](" + rec["url"] + ")：" + text,
        })

    # 游戏级「新作」过滤：与 X 侧出稿分流读同一个函数、同一份 rules.json 配置。
    pseudo = [{
        "column": WORK,
        "items": [{"group_label": r["group_label"], "sentence": r["sentence"]}
                  for r in rows],
    }]
    labels = new_work_labels(pseudo, rules.get("game_routing") or {}) if rows else set()
    lines: list[dict] = []
    for row in rows:
        is_new = row["group_label"] != NO_GAME and row["group_label"] in labels
        lines.append({
            "key": row["key"], "column": NEW if is_new else BILI_VIEW,
            "brand": row["brand"], "gkey": row["gkey"], "glabel": row["glabel"],
            "text": row["text"], "official": False, "new_work": is_new,
            "day": row["day"], "url": row["url"], "publisher": row["publisher"],
            "group_label": row["group_label"],
        })
    return lines


def material_lines(corpus: dict) -> list[str]:
    """选材库里的 B 站正本清单（只暴露，不参与 X 侧去重 / 归栏）。"""
    lines = ["", "## 十、B 站动态正本（只读，第二数据源）", ""]
    rows = corpus.get("bilibili") or []
    lines.append(f"- 当期覆盖日命中 {len(rows)} 条动态；"
                 "键 `bilibili:<动态 id>` 与 X 侧源索引分开放，互不合并。")
    for rec in rows:
        lines.append(
            f"- `{rec['key']}` → {rec['url']}（{rec['publisher']} · "
            f"`{rec['handle']}` · {rec['published_at'] or '时间未知'} · "
            f"{rec['source_file']}）")
    if not rows:
        lines.append("- （本期窗口内没有 B 站动态正本）")
    return lines
