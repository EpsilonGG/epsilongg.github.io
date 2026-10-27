#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把名单里的 manufacturer 段导成一张可以审阅的表。

名单的正本是 `src/config/daily-roster.json`，这张表只是它的只读视图——
改名单请改 JSON，改完重跑这个脚本。

用法：
    python scripts/build_manufacturer_roster.py
    python scripts/build_manufacturer_roster.py --out README/reports/xxx.html
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "src" / "config" / "daily-roster.json"
DEFAULT_OUT = ROOT / "README" / "reports" / "manufacturer-roster.html"

# 只给「非厂商」这一类打标记：名单里混进了情报站/资料站时要一眼看得出来
NON_BRAND_ROLES = {"other"}

STYLE = """
:root {
  --bg: #ffffff; --bg-subtle: #f7f7f7; --text: #1a1a1a; --text-2: #555;
  --muted: #767676; --border: #e5e5e5; --border-strong: #cfcfcf;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 48px 24px 96px; background: var(--bg); color: var(--text);
  font: 15px/1.7 -apple-system, "Segoe UI", "Noto Sans SC", "Hiragino Sans", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { margin: 0 0 8px; font-size: 26px; font-weight: 600; letter-spacing: -0.01em; }
.sub { margin: 0 0 6px; color: var(--text-2); }
.meta { margin: 0 0 28px; color: var(--muted); font-size: 13px; }
.stats { display: flex; flex-wrap: wrap; gap: 28px; margin: 0 0 28px; padding: 16px 0;
  border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
.stat b { display: block; font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
.stat span { color: var(--muted); font-size: 12px; }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 9px 10px; text-align: left; vertical-align: top;
  border-bottom: 1px solid var(--border); }
th { font-weight: 500; color: var(--muted); font-size: 12px; white-space: nowrap;
  position: sticky; top: 0; background: var(--bg); border-bottom-color: var(--border-strong); }
td.rank { color: var(--muted); font-variant-numeric: tabular-nums; width: 44px; }
td.name { font-weight: 500; }
td.handle { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
td.handle a { color: var(--text-2); text-decoration: none; border-bottom: 1px solid var(--border-strong); }
td.handle a:hover { color: var(--text); border-bottom-color: var(--text); }
td.note { color: var(--muted); font-size: 13px; }
.tag { display: inline-block; margin: 0 4px 2px 0; padding: 1px 6px; font-size: 11px;
  color: var(--text-2); border: 1px solid var(--border-strong); border-radius: 6px; white-space: nowrap; }
.tag--new { color: var(--text); border-color: var(--text); font-weight: 500; }
.tag--idle { color: var(--muted); border-style: dashed; }
tr.is-new { background: var(--bg-subtle); }
.legend { margin: 20px 0 0; color: var(--muted); font-size: 13px; }
.legend code { font-size: 12px; }
"""


def esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build(out_path: Path) -> None:
    data = json.loads(io.open(ROSTER, encoding="utf-8").read())
    accounts = [a for a in data["accounts"] if a.get("category") == "manufacturer"]
    labels = {c["id"]: c["label"] for c in data.get("categories", [])}

    brands = [a for a in accounts if a.get("role") not in NON_BRAND_ROLES]
    others = [a for a in accounts if a.get("role") in NON_BRAND_ROLES]
    active = [a for a in accounts if a.get("active", True)]

    rows = []
    for index, account in enumerate(accounts, start=1):
        is_other = account.get("role") in NON_BRAND_ROLES
        tags = "".join(
            '<span class="tag%s">%s</span>' % (" tag--new" if is_other else "", esc(t))
            for t in account.get("tags") or []
        )
        if not account.get("active", True):
            tags += '<span class="tag tag--idle">暂停</span>'
        rows.append(
            '<tr%s><td class="rank">%d</td><td class="name">%s</td>'
            '<td class="handle"><a href="https://x.com/%s" rel="noopener">@%s</a></td>'
            '<td>%s</td><td class="note">%s</td></tr>'
            % (
                ' class="is-new"' if is_other else "",
                index,
                esc(account.get("name", "")),
                esc(account["handle"]),
                esc(account["handle"]),
                tags,
                esc(account.get("note", "")),
            )
        )

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>美少女游戏厂商名单（manufacturer）· %(total)d 条</title>
<style>%(style)s</style>
</head>
<body>
<div class="wrap">
  <h1>美少女游戏厂商名单（manufacturer）</h1>
  <p class="sub">这是 <code>src/config/daily-roster.json</code> 里 <code>category: manufacturer</code> 的只读视图，顺序即日报里的显示顺序。</p>
  <p class="meta">生成日期 %(date)s · 改名单请改 JSON，再重跑 <code>python scripts/build_manufacturer_roster.py</code></p>

  <div class="stats">
    <div class="stat"><b>%(total)d</b><span>条目</span></div>
    <div class="stat"><b>%(brands)d</b><span>厂商</span></div>
    <div class="stat"><b>%(others)d</b><span>非厂商（情报站等）</span></div>
    <div class="stat"><b>%(active)d</b><span>active（进抓取）</span></div>
  </div>

  <div class="scroll">
    <table>
      <thead><tr><th>#</th><th>名称</th><th>X 账号</th><th>标签</th><th>备注</th></tr></thead>
      <tbody>
        %(rows)s
      </tbody>
    </table>
  </div>

  <p class="legend">
    <span class="tag tag--new">资料站</span> 标出的行不是厂商，是情报来源（例如 Moepedia），放进名单是为了在第二份日报里当「新作情报」的入口；
    <span class="tag tag--idle">暂停</span> 对应 <code>active: false</code>——名单里登记着，但抓取和日报都会跳过，改这一位就能启用。
    备注里的「五年 N 部」是 2021-10 ～ 2026-10 在 moepedia 登场的作品数，用来判断这个号值不值得跟。
  </p>
</div>
</body>
</html>
""" % {
        "total": len(accounts),
        "brands": len(brands),
        "others": len(others),
        "active": len(active),
        "rows": "\n        ".join(rows),
        "style": STYLE,
        "date": "2026-10-27",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(html)
    print("[roster] %d 条（厂商 %d / 非厂商 %d / active %d）→ %s"
          % (len(accounts), len(brands), len(others), len(active), out_path.relative_to(ROOT)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导出 manufacturer 名单的审阅视图")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    build(parser.parse_args().out)
