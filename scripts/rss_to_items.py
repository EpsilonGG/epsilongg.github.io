#!/usr/bin/env python3
"""把 X-rss-main 的真实 RSS feeds 转成 NormalizedItem JSONL（供 daily_digest.py 用）。

数据来源是 X-rss-main 实际抓取的 output/feeds_processed/<account>.xml，
因此推文正文、原文链接、时间都是真实的。注意：该 RSS 源不含媒体 URL 与
互动数（likes/retweets），所以这两项在转换结果里为空——这是数据源限制，
不是 bug。

用法：
    python rss_to_items.py \
        --feeds-dir "<X-rss-main>/output/feeds_processed" \
        --accounts mimoriaino mimo_chorion ... \
        --out scripts/sample_items/x.jsonl [--date YYYY-MM-DD] [--stats]
"""
from __future__ import annotations

import argparse
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET


def _clean_description(desc_html: str) -> str:
    """RSS description 是「XML 转义后的 HTML」。ElementTree 已解一层 XML，
    这里再把 HTML 标签/实体清成纯文本。"""
    if not desc_html:
        return ""
    # <br/> / <br> / </p> / <p> -> 换行
    s = re.sub(r"<br\s*/?>", "\n", desc_html, flags=re.I)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<p\s*>", "", s, flags=re.I)
    # 去掉其余 HTML 标签
    s = re.sub(r"<[^>]+>", "", s)
    # 去掉 nitter 自带的尾部归属行：— http://nitter.../...#m
    s = re.sub(r"\n?—\s*https?://\S+", "", s)
    # 解 HTML 实体
    s = html.unescape(s)
    # 收尾清理（逐行）：去空行、nitter 域名残留行、裸 URL 行、nitter 的媒体占位行
    cleaned = []
    for ln in s.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if "nitter." in ln:
            continue
        if re.match(r"^—?\s*https?://\S+$", ln):
            continue
        if ln.lower() in ("video", "video/video"):
            continue
        cleaned.append(ln)
    # nitter 给带链接的推文附加「Link」卡片标记，其后是卡片标题/描述/域名，
    # 属于预览噪音；截断到第一个独立 "Link" 行，保留作者自己的文字与话题标签。
    for idx, ln in enumerate(cleaned):
        if ln == "Link" and idx < len(cleaned) - 1:
            cleaned = cleaned[:idx]
            break
    return "\n".join(cleaned).strip()


def _status_id(url: str) -> str:
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else url.rsplit("/", 1)[-1]


def _title_text(title: str, account: str) -> tuple[str, bool, str | None]:
    """返回 (正文, 是否转发, 原作者)。nitter 标题形如 '@acc: ...' 或 '@RT by @acc: ...'。"""
    is_rt = False
    orig_author = None
    t = title.strip()
    m = re.match(r"@RT by @([^:]+):\s*(.*)", t)
    if m:
        is_rt = True
        # '@RT by @acc' 里 acc 是被跟踪账号本身；原作者从正文尾部另取（此处留空）
        return m.group(2).strip(), True, orig_author
    m = re.match(r"@([^:]+):\s*(.*)", t)
    if m:
        return m.group(2).strip(), False, orig_author
    return t, False, orig_author


def convert(feeds_dir: Path, accounts: list[str], out: Path,
            only_date: str | None = None) -> list[dict]:
    items: list[dict] = []
    for acc in accounts:
        fp = feeds_dir / f"{acc}.xml"
        if not fp.exists():
            print(f"  ! missing feed: {fp.name}")
            continue
        root = ET.parse(fp).getroot()
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            desc = it.findtext("description") or ""
            try:
                dt = parsedate_to_datetime(pub).astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
            if only_date and dt.date().isoformat() != only_date:
                continue
            body_title, is_rt, _ = _title_text(title, acc)
            content = _clean_description(desc) or body_title
            item_id = _status_id(link)
            items.append({
                "source_id": "x",
                "item_id": item_id,
                "title": None,
                "content": content,
                "publisher": acc,
                "canonical_url": link,
                "published_at": dt.isoformat(),
                "published_at_raw": pub,
                "published_precision": "second",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "media": [],
                "metadata": {
                    "account": acc,
                    "author_name": acc,
                    "is_retweet": is_rt,
                    "retweeted_by": acc if is_rt else None,
                    "is_reply": False,
                    "reply_to": None,
                    "is_quote": False,
                    "quoted_tweet_id": None,
                    "quoted_author": None,
                    "quoted_text": None,
                    "is_pinned": False,
                    "stats": {},
                    "provider": "rss",
                    "route": "xml",
                },
            })
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json_dumps(it) + "\n")
    return items


def json_dumps(o) -> str:
    import json
    return json.dumps(o, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds-dir", required=True)
    ap.add_argument("--accounts", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", help="只保留该日(UTC)的推文")
    args = ap.parse_args()

    items = convert(Path(args.feeds_dir), args.accounts, Path(args.out), args.date)
    print(f"Wrote {len(items)} items -> {args.out}")
    # 分布统计
    by_day: dict[str, int] = {}
    by_acc: dict[str, int] = {}
    for it in items:
        d = it["published_at"][:10]
        by_day[d] = by_day.get(d, 0) + 1
        by_acc[it["publisher"]] = by_acc.get(it["publisher"], 0) + 1
    print("per-day:", dict(sorted(by_day.items())))
    print("per-account:", dict(sorted(by_acc.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
