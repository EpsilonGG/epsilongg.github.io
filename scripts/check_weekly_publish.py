#!/usr/bin/env python
"""周报发布出口闸门（只读，CI 在 `npm run build` 之后跑）。

与日报的 `check_daily_site.py` 同构：页面改名/漏了出口，Astro 构建不会报错，
只有点进去的人看到 404；这一条把「有一份正本就必须有全套出口」补上。

2026-11-11 上线裁决带来的额外约束：

* 期号是 `vol_XXX`，不是日报的 `YYMMDD-g`，也不是旧脚手架的 `YYMMDD-w`；
* 站点代码**只允许读 `data/weekly/`**，不许引用 `weekly/out/`（工作台）；
* 首图是外站热链，每个 `<img>` 必须有 `onerror` 纯文字兜底；
* 创刊阶段「业界动向」整块不上线，正文/栏目里都不许出现；
* 工作台内部语言（未定稿 / 测试窗口 / 本地工作台…）不许漏到对外正文。

用法：

    python scripts/check_weekly_publish.py
    python scripts/check_weekly_publish.py --repo-root /path/to/repo --dist /path/to/dist
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISSUE_RE = re.compile(r"^vol_(\d{3,})$")
IMG_RE = re.compile(r"<img\b[^>]*>", re.I)

# 发布目录里除正本外一律不许有东西（证据 / 决策 / 快照都在 weekly/out/）。
ALLOWED_FILES = frozenset({"report.json"})
FORBIDDEN_PREFIXES = ("overview", "candidates", "decisions", "snapshot")
FORBIDDEN_EXACT = frozenset({"manifest.json", "filter-data.json", "records.json"})

INTERNAL_MARKERS = (
    "未定稿", "未发布", "未启用", "不上页面", "不 publish",
    "测试窗口", "本地工作台", "筛选页", "机器稿",
)
DISABLED_COLUMN = "业界动向"

SITE_FILES = (
    "src/pages/weekly/index.astro",
    "src/pages/weekly/[id].astro",
    "src/pages/weekly/[id].json.ts",
    "src/pages/weekly/rss.xml.ts",
    "src/lib/weekly.ts",
)


class Failure(Exception):
    pass


def _iso_ok(text: str) -> bool:
    try:
        datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False


def _day_ok(text: str) -> bool:
    try:
        date.fromisoformat(str(text))
        return True
    except (ValueError, TypeError):
        return False


def _check_report(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    iid = path.parent.name
    if not ISSUE_RE.match(iid):
        raise Failure(f"{rel}: 目录名不是合法期号 vol_XXX：{iid}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Failure(f"{rel}: 不是合法 JSON：{exc}") from exc

    issue = report.get("issue") or {}
    if issue.get("id") != iid:
        raise Failure(f"{rel}: issue.id {issue.get('id')!r} ≠ 目录名 {iid!r}")
    if issue.get("status") != "published":
        raise Failure(f"{rel}: 未发布的正本不得进 data/weekly/（status={issue.get('status')!r}）")
    if not _iso_ok(issue.get("published_at")):
        raise Failure(f"{rel}: issue.published_at 不是 ISO 时间")
    win = issue.get("window") or {}
    if not _day_ok(win.get("start")) or not _day_ok(win.get("end")):
        raise Failure(f"{rel}: issue.window 的 start/end 必须是 YYYY-MM-DD")
    if str(win["start"]) > str(win["end"]):
        raise Failure(f"{rel}: window.start 晚于 window.end")
    if len(str(report.get("description") or "")) > 70:
        raise Failure(f"{rel}: description 超过 70 字")

    for key in ("lead", "markdown", "content_html", "policy", "columns", "stats"):
        if not report.get(key):
            raise Failure(f"{rel}: 缺字段 {key}")

    for label, text in (("markdown", report["markdown"]),
                        ("content_html", report["content_html"])):
        hit = [s for s in INTERNAL_MARKERS if s in text]
        if hit:
            raise Failure(f"{rel}: {label} 漏出工作台内部语言：{' / '.join(hit)}")
        if DISABLED_COLUMN in text:
            raise Failure(f"{rel}: {label} 仍出现未上线栏目「{DISABLED_COLUMN}」")

    html = report["content_html"]
    for tag in ("<!doctype", "<html", "<head", "<body", "<footer", "<script"):
        if tag in html.lower():
            raise Failure(f"{rel}: content_html 是整页 HTML，不是可嵌入片段（含 {tag}）")
    imgs = IMG_RE.findall(html)
    if any("onerror=" not in tag for tag in imgs):
        raise Failure(f"{rel}: {len(imgs)} 张 <img> 中有缺少 onerror 碎图兜底的")
    # 站点上没有工作台那份 images/ 目录，相对路径必然 404；线上只能用绝对热链。
    for tag in imgs:
        m = re.search(r'src="([^"]*)"', tag)
        if m and not re.match(r"^https?://", m.group(1)):
            raise Failure(f"{rel}: <img> 用了非绝对地址 {m.group(1)!r}（线上会 404）")
    if "<h2>" not in html:
        raise Failure(f"{rel}: content_html 没有任何栏目（## 标题）")
    if any("业界动向" == str(c.get("label")) for c in report["columns"]):
        raise Failure(f"{rel}: columns 仍列出未上线栏目「{DISABLED_COLUMN}」")

    policy = report["policy"]
    if DISABLED_COLUMN not in (policy.get("disabled_display_columns") or []):
        raise Failure(f"{rel}: policy.disabled_display_columns 没登记「{DISABLED_COLUMN}」未上线")
    if not isinstance(policy.get("new_work_signal_groups"), list) or not policy["new_work_signal_groups"]:
        raise Failure(f"{rel}: policy 没记录新作标签的自动信号组")
    return iid


def _check_site_source(root: Path) -> None:
    missing = [rel for rel in SITE_FILES if not (root / rel).is_file()]
    if missing:
        raise Failure("周报页面/出口缺失：" + "、".join(missing))
    for rel in SITE_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        if "weekly/out" in text or "out/weekly" in text:
            raise Failure(f"{rel}: 站点代码引用了工作台 weekly/out/（只允许读 data/weekly/）")


def _check_outlets(root: Path, ids: list[str], dist: Path | None) -> list[str]:
    """dist 存在时校验 HTML / JSON / RSS 三个出口；本地没构建就跳过这一段。"""
    if dist is None or not dist.is_dir():
        return ["dist/ 不存在，跳过产物出口校验（CI 在 build 之后会验）"]
    lines: list[str] = []
    index = dist / "weekly" / "index.html"
    rss = dist / "weekly" / "rss.xml"
    if not index.is_file():
        raise Failure("缺 /weekly/ 归档页（dist/weekly/index.html）")
    if not rss.is_file():
        raise Failure("缺 /weekly/rss.xml")
    for iid in ids:
        page = dist / "weekly" / iid / "index.html"
        outlet = dist / "weekly" / f"{iid}.json"
        if not page.is_file():
            raise Failure(f"缺 /weekly/{iid}/ 详情页")
        if not outlet.is_file():
            raise Failure(f"缺 /weekly/{iid}.json 出口")
        try:
            payload = json.loads(outlet.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise Failure(f"/weekly/{iid}.json 不是合法 JSON：{exc}") from exc
        if (payload.get("issue") or {}).get("id") != iid:
            raise Failure(f"/weekly/{iid}.json 的 issue.id 与期号不一致")
        hit = [s for s in INTERNAL_MARKERS if s in page.read_text(encoding="utf-8")]
        if hit:
            raise Failure(f"/weekly/{iid}/ 漏出工作台内部语言：{' / '.join(hit)}")
        lines.append(f"{iid}: HTML / JSON 出口齐备")
    return lines


def check(repo_root: Path | None = None, dist: Path | None = None) -> list[str]:
    root = Path(repo_root) if repo_root is not None else ROOT
    data_dir = root / "data" / "weekly"
    if not data_dir.is_dir():
        raise Failure("data/weekly/ 不存在：周报已上线，必须有发布正本")

    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        lower = name.lower()
        if (name not in ALLOWED_FILES or lower.startswith(FORBIDDEN_PREFIXES)
                or lower in FORBIDDEN_EXACT):
            raise Failure(f"不在发布白名单：{path.relative_to(root).as_posix()}")

    reports = sorted(data_dir.glob("*/report.json"))
    if not reports:
        raise Failure("data/weekly/ 里没有 report.json")
    ids = [_check_report(p, root) for p in reports]
    if len(set(ids)) != len(ids):
        raise Failure("存在重复期号")
    _check_site_source(root)
    lines = [f"发布正本 {len(ids)} 期（" + "、".join(ids) + "）校验通过",
             "站点代码只读 data/weekly/，未引用工作台产物"]
    lines.extend(_check_outlets(root, ids, dist))
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="check_weekly_publish.py",
                                description="周报发布出口与内容闸门（只读）")
    p.add_argument("--repo-root", help="覆盖仓库根（测试用）")
    p.add_argument("--dist", help="覆盖 dist 目录；不给则用 <root>/dist，不存在就跳过产物校验")
    args = p.parse_args(argv)
    root = Path(args.repo_root) if args.repo_root else ROOT
    dist = Path(args.dist) if args.dist else root / "dist"
    try:
        lines = check(root, dist)
    except Failure as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    print("check_weekly_publish: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
