"""M3.3 合并：把校验过的回答写进正本 `report.json`。

三条约束：

* **只写回答里出现的字段**。`apply` 不重建整份报告——没答的分类、没提的人保持原样，
  否则「补一个人」会顺手把别人的摘要清空。
* **来源跟着文字走**。`sources` 原样留在报告里，页面不显示，但它是唯一能回溯的凭据。
* **定稿之后不许再合并**。要改先 `reopen`，历史在 `history/` 里。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .roster import Roster
from .schema import SchemaError, load_schema, validate


class ApplyError(RuntimeError):
    pass


def new_report(issue_id: str, generate: dict) -> dict:
    """从 M2 的 `generate.json` 起一份空正本。

    正常流程里这份文件已经由 `daily build` 写好了（`build_report`），这里只是兜底：
    直接跑 `apply` 而没跑 `build` 时，字段名必须和 `build_report` 完全一致，
    否则两条路径产出的正本会不一样，而站点只认一种。
    """
    issue = generate.get("issue") or {}
    counts = generate.get("counts") or {}
    people = []
    for category in generate.get("categories") or []:
        cid = str(category.get("id") or "")
        for handle in category.get("handles") or []:
            people.append(
                {
                    "handle": str(handle),
                    "category": cid,
                    "summary": "",
                    "via": [],
                    "sources": [],
                }
            )

    return {
        "schema_version": 1,
        "issue": {
            "id": issue_id,
            "published_at": issue.get("published_at") or "",
            "window": issue.get("window") or {},
            "status": "draft",
            "confirmed_at": None,
        },
        "counts": {
            "items": int(counts.get("items") or 0),
            "accounts": int(counts.get("accounts") or 0),
            "late": int(counts.get("late") or 0),
            "skipped_duplicate": int(counts.get("skipped_duplicate") or 0),
        },
        "description": "",
        "highlights": [],
        "insights": [],
        "interactions": [],
        "works": "",
        "categories": [
            {"id": str(c.get("id") or ""), "label": str(c.get("label") or c.get("id") or "")}
            for c in generate.get("categories") or []
        ],
        "accounts": [],
        "people": people,
        "provenance": {
            "generator": "daily",
            "prompt_version": 1,
            "cache_key": "",
            "generated_at": "",
        },
    }


def load_report(ws: Path, issue_id: str, generate: dict) -> dict:
    path = paths.report(ws)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return new_report(issue_id, generate)


def _merge_people(report: dict, people: list[dict], category: str, roster: Roster) -> None:
    index = {str(p.get("handle")): p for p in report["people"]}
    # 小号也指向同一个人那一行。模型看到的是「每个号一条材料」，很容易把某个人的
    # 小号当成另一个人来写；不在这里兜住，页面上就会出现同一个人两行。
    for row in report["people"]:
        for alt in row.get("via") or []:
            index.setdefault(str(alt), row)
    for person in people:
        handle = str(person.get("handle") or "").strip()
        if not handle:
            continue
        target = index.get(handle)
        if target is None:
            target = {"handle": handle, "category": category, "summary": "", "via": [], "sources": []}
            report["people"].append(target)
            index[handle] = target
        if "summary" in person:
            target["summary"] = person["summary"]
        if "sources" in person:
            target["sources"] = list(person["sources"])
        target.setdefault("category", category)
    # 名单顺序即显示顺序（roster.py 的约定），合并后按名单序重排
    report["people"].sort(key=lambda p: roster.index_of(str(p.get("handle") or "")))


def apply(
    issue_id: str,
    answers: list[dict],
    *,
    roster: Roster,
    generate: dict,
    out_dir: str | Path = "out",
    force: bool = False,
) -> dict:
    ws = paths.workspace(out_dir, issue_id)
    report = load_report(ws, issue_id, generate)

    if report["issue"].get("status") == "confirmed" and not force:
        raise ApplyError(
            "这一期已经定稿（status=confirmed），拒绝合并。要改先 `daily confirm --reopen`。"
        )

    for answer in answers:
        cid = str(answer.get("category") or "")
        if cid == "all":
            if "summary" in answer:
                report["description"] = answer["summary"]
            if "works" in answer:
                report["works"] = answer["works"]
            if "highlights" in answer:
                report["highlights"] = list(answer["highlights"])
            if "interactions" in answer:
                report["interactions"] = list(answer["interactions"])
            _merge_people(report, answer.get("people") or [], "all", roster)
            continue

        target = next((c for c in report["categories"] if c["id"] == cid), None)
        if target is None:
            target = {"id": cid, "label": cid}
            report["categories"].append(target)
        if "summary" in answer:
            target["summary"] = answer["summary"]
        if "highlights" in answer:
            target["highlights"] = list(answer["highlights"])
        if "interactions" in answer:
            target["interactions"] = list(answer["interactions"])
        _merge_people(report, answer.get("people") or [], cid, roster)

    report["provenance"] = {
        "generator": "daily",
        "prompt_version": 1,
        "cache_key": "answers:" + str(len(answers)),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    try:
        validate(report, load_schema("report"))
    except SchemaError as exc:
        raise ApplyError(f"合并后的正本不合法，未写入：{exc}") from None

    paths.report(ws).parent.mkdir(parents=True, exist_ok=True)
    paths.report(ws).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
