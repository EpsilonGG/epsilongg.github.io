"""语料层：把既有 Galgame 日报全集组装成一份只读数据库。

输入（全部只读）：
* `data/daily/*-g*/report.json` —— 已发布日报正本（11 期）
* `out/clauses/<issue>.json`     —— M1 分句索引（10 期；261108-g 无索引）

输出：`weekly/out/corpus.json`。不写 `data/`、不写 `out/clauses/`、不 publish。
分句索引缺失的期号仍收正本散文，但明确标 `prose_only`，不伪造出处。
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import CLAUSES, DAILY, read_json

ISSUE_RE = re.compile(r"^(\d{6})-g(\d*)$")
TITLE_RE = re.compile(r"[『《]([^』》]{1,60})[』》]")


def day_of(issue: str) -> str:
    m = ISSUE_RE.match(issue)
    if not m:
        raise ValueError(f"不是 Galgame 期号：{issue}")
    raw = m.group(1)
    return f"20{raw[:2]}-{raw[2:4]}-{raw[4:6]}"


def norm_title(text: str) -> str:
    return "".join(str(text or "").split()).strip("『』《》「」 　")


def _as_rows(items, origin: str, issue: str, day: str) -> list[dict]:
    rows = []
    for item in items or []:
        if isinstance(item, str):
            text, sources = item, []
        else:
            text = str(item.get("text") or "")
            sources = list(item.get("sources") or [])
        if text.strip():
            rows.append({"origin": origin, "issue": issue, "day": day,
                         "text": text, "sources": sources})
    return rows


def build(since: str | None = None, until: str | None = None,
          last_days: int | None = None) -> dict:
    """组装语料。默认仍是「全集」（本地回测用），上线时按窗口取近 N 期。

    `last_days=N` 以 **JST 昨天**为窗口末端、往前 N 个自然日：日报按 JST
    覆盖日出稿，今天那一期要到 JST 24:00 才闭合，所以周六中午能拿到的
    最后一期是「昨天」。不给窗口参数时行为与创刊前完全一致，回归不会漂。
    """
    issues = sorted(p.name for p in DAILY.iterdir()
                    if p.is_dir() and ISSUE_RE.match(p.name))
    if last_days is not None:
        if last_days < 1:
            raise ValueError("last_days 至少为 1")
        jst = timezone(timedelta(hours=9))
        end = datetime.now(jst).date() - timedelta(days=1)
        start = end - timedelta(days=last_days - 1)
        since, until = start.isoformat(), end.isoformat()
    if since:
        issues = [i for i in issues if day_of(i) >= since]
    if until:
        issues = [i for i in issues if day_of(i) <= until]
    if not issues:
        raise RuntimeError(
            "data/daily 里没有落在窗口内的 Galgame 日报正本"
            + (f"（{since} – {until}）" if since or until else ""))

    refs: dict[str, dict] = {}
    summaries: list[dict] = []
    candidates: list[dict] = []
    daily_rows: list[dict] = []
    indexed: list[str] = []
    prose_only: list[str] = []

    for issue in issues:
        day = day_of(issue)
        report = read_json(DAILY / issue / "report.json")
        idx_path = CLAUSES / f"{issue}.json"
        index = read_json(idx_path) if idx_path.is_file() else None
        (indexed if index else prose_only).append(issue)

        if index:
            for key, rec in (index.get("source_refs") or {}).items():
                # 同一 key 多期出现时留原文更全的一条（与 weekly_material 同口径）。
                if key not in refs or len(rec.get("text") or "") > len(refs[key].get("text") or ""):
                    refs[key] = dict(rec)
            for person in index.get("people") or []:
                handle = str(person.get("handle") or "")
                summary = str(person.get("summary") or "")
                match = TITLE_RE.search(summary)
                group = ("『" + match.group(1) + "』") if match else ("@" + handle)
                for clause in person.get("clauses") or []:
                    sources = list(clause.get("sources") or [])
                    candidates.append({
                        "clause_id": clause.get("clause_id") or "",
                        "issue": issue, "day": day,
                        "handle": handle, "group": group,
                        "group_fallback": not bool(match),
                        "text": clause.get("text") or "",
                        "context": clause.get("context") or "",
                        "sources": sources,
                        "precision": clause.get("precision") or "row",
                        "dedupe_key": "|".join(sorted(sources)) if sources
                                      else "solo:" + str(clause.get("clause_id") or ""),
                    })

        daily = (index or {}).get("daily") or {}
        works = daily.get("works") or report.get("works") or []
        highlights = daily.get("highlights") or report.get("highlights") or []
        interactions = daily.get("interactions") or report.get("interactions") or []
        wrows = _as_rows(works, "work", issue, day)
        hrows = _as_rows(highlights, "highlight", issue, day)
        irows = _as_rows(interactions, "interaction", issue, day)
        daily_rows.extend(wrows + hrows + irows)
        summaries.append({
            "issue": issue, "day": day,
            "description": (daily.get("description") or report.get("description") or ""),
            "works": [r["text"] for r in wrows],
            "highlights": [{"text": r["text"], "sources": r["sources"]} for r in hrows],
            "interactions": [{"text": r["text"], "sources": r["sources"]} for r in irows],
            "issue_meta": {"published_at": ((report.get("issue") or {}).get("published_at") or "")},
            "has_index": bool(index),
        })

    titles: set[str] = set()
    for row in daily_rows:
        titles.update(norm_title(m.group(1)) for m in TITLE_RE.finditer(row["text"])
                      if len(norm_title(m.group(1))) >= 2)
    for cand in candidates:
        titles.update(norm_title(m.group(1)) for m in TITLE_RE.finditer(cand["context"])
                      if len(norm_title(m.group(1))) >= 2)

    payload = {
        "schema_version": 1,
        "generator": "weekly/corpus/1",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "galgame",
        "window": {"start": day_of(issues[0]), "end": day_of(issues[-1])},
        "issues": issues,
        "indexed_issues": indexed,
        "prose_only_issues": prose_only,
        "source_refs": refs,
        "summaries": summaries,
        "candidates": candidates,
        "daily_rows": daily_rows,
        "titles": sorted(titles),
        "stats": {
            "issues": len(issues),
            "source_keys": len(refs),
            "candidates": len(candidates),
            "daily_rows": len(daily_rows),
            "daily_rows_by_origin": dict(Counter(r["origin"] for r in daily_rows)),
            "titles": len(titles),
            "unresolved_source_keys": sorted({k for r in daily_rows for k in r["sources"]
                                             if k not in refs}),
        },
    }
    return payload
