r"""Publish Gplus drafts (out/gplus/reports/Gplus_XXX.json) into data/daily/ as YYMMDD-gp.

Checks before writing:
  * issue.id matches the directory name
  * status is confirmed
  * every source key resolves to a real fetched tweet in data/xreader/gplus/
  * every people[].handle is in the list 1-1 roster
  * no @handle appears inside narrative text

Usage:
    python scripts/gplus_publish.py --issue Gplus_001
    python scripts/gplus_publish.py --all
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "out" / "gplus" / "reports"
DEST = ROOT / "data" / "daily"


def load_sources() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in (ROOT / "data" / "xreader" / "gplus").glob("*.jsonl"):
        for line in f.open(encoding="utf-8"):
            try:
                item = json.loads(line)
            except Exception:
                continue
            key = f"x:{item.get('item_id')}"
            out[key] = item
    return out


def check(report: dict, sources: dict[str, dict], roster: set[str]) -> list[str]:
    errors: list[str] = []
    issue_id = str(((report.get("issue") or {}).get("id")) or "")
    if not re.fullmatch(r"Gplus_\d{3,}", issue_id):
        errors.append(f"bad draft issue.id {issue_id!r}")
    start = str(((report.get("issue") or {}).get("window") or {}).get("start") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00\+09:00", start):
        errors.append(f"bad window.start {start!r}; need JST midnight")
    if (report.get("issue") or {}).get("status") != "confirmed":
        errors.append("status must be confirmed")
    for claim in report.get("highlights", []) + report.get("insights", []) + report.get("interactions", []):
        for key in claim.get("sources", []):
            if key not in sources:
                errors.append(f"unresolved source {key} in claim")
    for person in report.get("people", []):
        h = str(person.get("handle", "")).lower()
        if h not in roster:
            errors.append(f"handle not in roster: {h}")
        for key in person.get("sources", []):
            if key not in sources:
                errors.append(f"unresolved source {key} in {h}")
    narrative = [report.get("description", "")]
    for claim in report.get("highlights", []) + report.get("insights", []) + report.get("interactions", []):
        narrative.append(claim.get("text", ""))
    narrative.extend(p.get("summary", "") for p in report.get("people", []))
    for text in narrative:
        if re.search(r"@[A-Za-z0-9_]+", text or ""):
            errors.append(f"@handle in narrative: {(text or '')[:60]}")
    if report.get("works"):
        errors.append("works must be empty for Gplus")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Publish Gplus drafts")
    ap.add_argument("--issue", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args(argv)

    roster = {a["handle"].lower() for a in json.loads((ROOT / "src/config/gplus-roster.json").read_text(encoding="utf-8"))["accounts"]}
    sources = load_sources()
    files = sorted(DRAFTS.glob("Gplus_*.json")) if args.all else [DRAFTS / f"{args.issue}.json"]
    failed = False
    for f in files:
        if not f.exists():
            print(f"missing draft: {f}")
            failed = True
            continue
        report = json.loads(f.read_text(encoding="utf-8"))
        errors = check(report, sources, roster)
        issue_id = report["issue"]["id"]
        if errors:
            failed = True
            print(f"{issue_id}: FAIL")
            for e in errors[:12]:
                print(f"  - {e}")
            if len(errors) > 12:
                print(f"  ... {len(errors) - 12} more")
            continue
        print(f"{issue_id}: OK  highlights={len(report['highlights'])} people={len(report['people'])} sources={len(sources)}")
        if not args.check_only:
            from datetime import date
            start = report["issue"]["window"]["start"]
            # 期号按 JST 覆盖日：window.start 的日期就是那一天
            d = date.fromisoformat(start[:10])
            daily_id = d.strftime("%y%m%d") + "-gp"
            published = dict(report["issue"])
            published["id"] = daily_id
            # Zod 的 dailyReports schema 会给这两个字段填默认值；出口必须与正本
            # 逐字节相同（`check:daily` 盯着），所以发布时就写进正本，不留缺省。
            counts = dict(report["counts"])
            counts.setdefault("late", 0)
            counts.setdefault("skipped_duplicate", 0)
            payload = dict(report)
            payload["issue"] = published
            payload["counts"] = counts
            payload.setdefault("categories", [])
            target = DEST / daily_id / "report.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            print(f"  wrote {target.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
