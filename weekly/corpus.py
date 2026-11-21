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


def _report_has_sources(report: dict) -> bool:
    """正本 people / highlights / interactions 里是否出现任一出处 key。

    与 `scripts/daily_clauses.py:issue_keys()` 的收集口径一致（只读）：sources
    可能是字符串或字符串列表。C1 护栏据此区分「正常零图周」与「索引缓存断了」。
    """
    def has(value) -> bool:
        if isinstance(value, str):
            return bool(value)
        if isinstance(value, list):
            return any(has(item) for item in value)
        return False

    for person in report.get("people") or []:
        if has(person.get("sources")):
            return True
    for group in ("highlights", "interactions"):
        for claim in report.get(group) or []:
            if isinstance(claim, dict) and has(claim.get("sources")):
                return True
    return False


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
    broken: list[str] = []  # 缺索引、但正本明摆着有 sources 的期号（C1 护栏）

    for issue in issues:
        day = day_of(issue)
        report = read_json(DAILY / issue / "report.json")
        has_sources = _report_has_sources(report)
        idx_path = CLAUSES / f"{issue}.json"
        index = read_json(idx_path) if idx_path.is_file() else None
        (indexed if index else prose_only).append(issue)
        if not index and has_sources:
            broken.append(issue)

        if index:
            # 原推事实层（2026-11-21）：中文概括只作表述，作品名/信号以本推正文为准。
            # 延迟导入避免 corpus ↔ source_grounding 的模块环。
            from .source_grounding import primary_text, title_values
            for key, rec in (index.get("source_refs") or {}).items():
                # 同一 key 多期出现时留原文更全的一条（与 weekly_material 同口径）。
                if key not in refs or len(rec.get("text") or "") > len(refs[key].get("text") or ""):
                    enriched = dict(rec)
                    enriched["origin_text"] = primary_text(rec)
                    enriched["origin_titles"] = title_values(enriched["origin_text"])
                    refs[key] = enriched
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

    # C1 护栏（2026-11-21）：某期缺索引、但正本明摆着有 sources 时，只可能是
    # 本地 out/clauses/ 缓存断了（它 gitignored，日报自动化与 CI 都不生成）。
    # build 必须早失败，不能产出一份「缺源索引」的稿子拖到 check 才以
    # 「没有首图」的假象暴露。零图是合法的选材结果，缺源索引不是。
    if broken:
        raise RuntimeError(
            f"窗口内 {len(broken)} 期日报没有 M1 分句索引（out/clauses/）："
            + "、".join(broken) + "；但正本里存在 sources。"
            "请先运行 python scripts/daily_clauses.py sync --all"
        )

    titles_cn: set[str] = set()
    for row in daily_rows:
        titles_cn.update(norm_title(m.group(1)) for m in TITLE_RE.finditer(row["text"])
                         if len(norm_title(m.group(1))) >= 2)
    for cand in candidates:
        titles_cn.update(norm_title(m.group(1)) for m in TITLE_RE.finditer(cand["context"])
                         if len(norm_title(m.group(1))) >= 2)
    # 原推里写了、但中文概括漏掉的作品名也必须进词表，否则「认亲」这一步
    # 根本没机会命中它。原推题名先过 title_values 的最小去噪（见该模块）。
    titles_original: set[str] = {t for rec in refs.values() for t in (rec.get("origin_titles") or [])}
    titles = titles_cn | titles_original

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
        "original_titles": sorted(titles_original),
        "chinese_titles": sorted(titles_cn),
        "generator_note": "作品名与信号以 source_refs[].origin_text（原推本推正文）为准；中文概括只作表述层，不新增 LLM 调用。",
        "stats": {
            "issues": len(issues),
            "source_keys": len(refs),
            "candidates": len(candidates),
            "daily_rows": len(daily_rows),
            "daily_rows_by_origin": dict(Counter(r["origin"] for r in daily_rows)),
            "titles": len(titles),
            "titles_from_original": len(titles_original - titles_cn),
            "titles_from_chinese_only": len(titles_cn - titles_original),
            "source_grounding": True,
            "unresolved_source_keys": sorted({k for r in daily_rows for k in r["sources"]
                                             if k not in refs}),
        },
    }
    return payload
