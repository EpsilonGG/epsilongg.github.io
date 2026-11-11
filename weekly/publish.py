"""发布层：把本地工作台产物变成站点可发的正本 `data/weekly/<vol_XXX>/report.json`。

2026-11-11 用户裁决：周报正式上线，**不做人工看稿**。

分工（很重要，别把两层混起来）：

* `weekly/out/` 是**工作台**：有内部版式说明、导语里的「测试窗口」、筛选页、
  未定稿徽章、全部证据文件。这里的东西永远不进站点。
* `data/weekly/<期号>/report.json` 是**发布正本**：只带对外该有的东西
  （元信息 / 导语 / 栏目统计 / 干净的正文与 HTML 片段）。`src/lib/weekly.ts`
  只读这一层，绝不 read `weekly/out/`。

因此本模块是唯一一次「对外脱敏」：删掉工作台内部说明、按上线策略剔除
未启用的栏目、重写导语。期号用 `vol_XXX`（用户指定），与日报的 `YYMMDD-g`
完全无关；站点上「上一期 / 下一期」由已发布期号排序派生，不写进正本。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .config import OUT, ROOT, read_json, write_json
from .draft_export import _image_index, _insert_images, _stats, render_public_fragment

PUBLISH_DIR = ROOT / "data" / "weekly"
ISSUE_RE = re.compile(r"^vol_(\d{3,})$")
GENERATOR = "weekly/publish/1"

# 工作台内部语言：出现在线上就是事故，publish 与 check-site 双重拦。
INTERNAL_MARKERS = (
    "未定稿", "未发布", "未启用", "不上页面", "不 publish",
    "测试窗口", "本地工作台", "筛选页", "机器稿",
)


def _publish_rules(rules: dict) -> dict:
    cfg = dict(rules.get("publish") or {})
    cfg.setdefault("issue_prefix", "vol_")
    cfg.setdefault("issue_width", 3)
    cfg.setdefault("disabled_display_columns", ["业界动向"])
    cfg.setdefault("human_review_required", False)
    cfg.setdefault("selection_mode", "deterministic_default")
    return cfg


def public_markdown(draft: str, disabled_columns: list[str]) -> str:
    """从 `weekly.md` 剥出**对外正文**。

    删掉四类只属于工作台的行：页面标题（Astro 自己写）、`>` 版式说明块、
    `**导语**`（改由 report.json 的 `lead` 重写）、分隔线；再整节删掉
    上线策略里未启用的栏目（创刊阶段是「业界动向」）。
    """
    banned = set(disabled_columns)
    out: list[str] = []
    skipping = False
    for line in draft.splitlines():
        if line.startswith("## "):
            skipping = line[3:].strip() in banned
            if skipping:
                continue
        if skipping:
            continue
        if line.startswith("# ") or line.startswith("> ") or line.strip() == "---":
            continue
        if line.startswith("**导语**"):
            continue
        out.append(line)
    # 掐掉开头因删行留下的空行；结尾统一一个换行
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out).rstrip() + "\n"


def next_issue_id(cfg: dict) -> str:
    """扫已发布正本，取最大编号 +1。空目录从 001 开始。"""
    top = 0
    if PUBLISH_DIR.is_dir():
        for path in PUBLISH_DIR.glob("*/report.json"):
            m = ISSUE_RE.match(path.parent.name)
            if m:
                top = max(top, int(m.group(1)))
    prefix = str(cfg["issue_prefix"])
    return f"{prefix}{top + 1:0{int(cfg['issue_width'])}d}"


def previous_issue_id() -> str | None:
    if not PUBLISH_DIR.is_dir():
        return None
    ids = [p.parent.name for p in PUBLISH_DIR.glob("*/report.json")
           if ISSUE_RE.match(p.parent.name)]
    return max(ids) if ids else None


def latest_published() -> tuple[str, dict] | None:
    """最近一期（期号 + 正本）。没有就返回 None。"""
    iid = previous_issue_id()
    if not iid:
        return None
    path = PUBLISH_DIR / iid / "report.json"
    if not path.is_file():
        return None
    return iid, read_json(path)


def build_report(rules: dict, manifest: dict, corpus: dict, decisions: dict,
                 *, published_at: str, issue_id: str) -> dict:
    cfg = _publish_rules(rules)
    disabled = [str(c) for c in cfg["disabled_display_columns"]]
    draft = (OUT / "weekly.md").read_text(encoding="utf-8")

    body_md = public_markdown(draft, disabled)
    leak = [s for s in INTERNAL_MARKERS if s in body_md]
    if leak:
        raise RuntimeError("对外正文仍带工作台内部语言：" + " / ".join(leak))
    for column in disabled:
        if f"## {column}" in body_md:
            raise RuntimeError(f"对外正文仍输出未启用栏目「{column}」")
    if "## " not in body_md or "\n- " not in body_md:
        raise RuntimeError("对外正文没有栏目或条目，拒绝发布空稿")

    idx = _image_index()
    # 线上正本不能用工作台的相对路径（站点没有那份 images/ 目录），一律走 X 热链。
    with_images, n_images = _insert_images(body_md, idx, prefer_local=False)
    content_html = render_public_fragment(with_images)

    stats = _stats(body_md)
    order = [c for c in stats["order"] if c not in disabled]
    win = corpus["window"]
    issues = list(manifest.get("issues") or corpus.get("issues") or [])
    brands = stats["brands"]
    items = stats["items"]

    lead = (
        f"本期汇总 {win['start']} – {win['end']} 共 {len(issues)} 期 Galgame 日报，"
        f"筛出 {brands} 个品牌 / {items} 条动态，按「" + " / ".join(order) + "」整理。"
    )
    description = f"{win['start']} – {win['end']} · {items} 条 Galgame 动态"
    if len(description) > 70:
        description = description[:70]

    routing = rules.get("game_routing") or {}
    policy = {
        "new_work_label_source": str(routing.get("label_source") or "auto"),
        "new_work_signal_groups": sorted((routing.get("signals") or {}).keys()),
        "new_work_manual_overrides": len(routing.get("new_work_games") or []),
        "human_review": bool(cfg["human_review_required"]),
        "selection_mode": str(cfg["selection_mode"]),
        "decisions_human_confirmed": int(
            (decisions.get("policy") or {}).get("human_confirmed") or 0),
        "disabled_display_columns": disabled,
    }

    return {
        "schema_version": 1,
        "generator": GENERATOR,
        "issue": {
            "id": issue_id,
            "title": f"Galgame 周报 · {issue_id}",
            "published_at": published_at,
            "window": {"start": str(win["start"]), "end": str(win["end"])},
            "status": "published",
            "previous": previous_issue_id(),
        },
        "description": description,
        "lead": lead,
        "columns": [
            {"label": c,
             "brands": stats["columns"].get(c, {}).get("brands", 0),
             "items": stats["columns"].get(c, {}).get("items", 0)}
            for c in order
        ],
        "stats": {
            "source_issues": len(issues),
            "brands": brands,
            "items": items,
            "images": n_images,
            "raw_records": (manifest.get("stats") or {}).get("raw_records", 0),
        },
        "policy": policy,
        "source_issues": issues,
        "markdown": body_md,
        "content_html": content_html,
    }


def publish(rules: dict, *, published_at: str | None = None,
            issue_id: str | None = None, dry_run: bool = False,
            force: bool = False) -> dict:
    """出一份发布正本。默认自动续 `vol_XXX`。

    `force=False` 时会先比窗口：本期语料末端不晚于上期，说明这几天没有新日报
    （抓取断了 / 这周没数据），**不出一期空的或重复的**，返回 `skipped`。
    自动化按这个语义跑；要强制补一期用 `--force`。
    """
    manifest = read_json(OUT / "manifest.json")
    corpus = read_json(OUT / "corpus.json")
    decisions = read_json(OUT / "decisions.json")
    cfg = _publish_rules(rules)

    prev = latest_published()
    if prev and not force and issue_id is None:
        last_id, last_report = prev
        last_end = str(((last_report.get("issue") or {}).get("window") or {}).get("end") or "")
        this_end = str(corpus["window"]["end"])
        if this_end <= last_end:
            return {"issue_id": None, "path": None, "dry_run": dry_run,
                    "skipped": True,
                    "reason": f"窗口末端 {this_end} 不晚于上期 {last_id}（{last_end}），"
                              f"这几天没有新日报，不出重复的一期"}

    stamp = published_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    iid = issue_id or next_issue_id(cfg)
    if not ISSUE_RE.match(iid):
        raise RuntimeError(f"期号必须是 vol_XXX（三位以上数字）：{iid}")
    target = PUBLISH_DIR / iid / "report.json"
    if target.is_file():
        raise RuntimeError(f"{target} 已存在；一期只发一次，别覆盖已发布正本")

    report = build_report(rules, manifest, corpus, decisions,
                          published_at=stamp, issue_id=iid)
    if not dry_run:
        write_json(target, report)
    return {"issue_id": iid, "path": target, "dry_run": dry_run, "report": report}
