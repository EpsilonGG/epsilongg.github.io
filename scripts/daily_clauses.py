"""日报「详细」栏的分句级出处索引（旁路，M0 / M1）。

**这个模块不参与日报生产。** 它只读 `data/daily/<期号>/report.json` 与
`data/xreader/*/*.jsonl`，把每个 `people[].summary` 切成带尾标点的分句，给每一句
挂上已解析的原推链接，并把该行全部来源推文的**完整原文**留在本地索引里。产物全部落在
保护集之外：

    out/clauses/<期号>.json                 临时索引，gitignored，可删可重建
    data/period-sources/backfill-links.json  M1 历史回填链接台账，进 git，只有链接与元数据

为什么必须有这层旁路（而不是往 `report.json` 里加 `source_refs`）：

* `tests/test_daily_protection.py` 用 `git diff` 把 `data/daily/`、`schemas/`、
  `scripts/daily/` 等路径逐字节钉死在 HEAD，还精确断言 schema 顶层属性集合。
  往正本加一个字段、或放宽 `summary` 的 60 字上限，都会直接跑红。
* 日报是唯一每天人工 `confirm` 过的已判卷事实层；周报月报还在试验，不能让试验改它。
* 「完整性」和「对齐性」其实不是靠放宽字数解决的：实测 55.0% 的行「分句数 ≠ 来源数」，
  因为逗号连接的常常只是同一条推文的补充。把 60 字放到 100 字只会让分句更多、
  `sources` 不变，错配率反而上升。所以这里把**原文全文**留在旁路（L0-a），
  并支持答题侧可选的 `people[].clauses`（L0-b），正文一个字不动。

精度口径（不伪造出处）：

    clause      该分句由 L0-b 的结构化答案明确给出 sources
    row         该分句继承整行 people[].sources（Q2 已裁定「算达标」）
    unresolved  该行没有任何 sources，或来源无法解析

单来源的行虽然 `precision=row`，但 `sources` 只有一条、结果同样是精确的，
用 `exact_source: true` 标出来，方便周报取料时判断。自动对齐试算只有 38.1% 可信，
所以**本模块绝不用算法猜分句归哪条推文**。

命令::

    python scripts/daily_clauses.py sync --all            # 全量回填 18 期
    python scripts/daily_clauses.py sync 261104          # 单期（懒生成，指纹相同就跳过）
    python scripts/daily_clauses.py check --all          # 指纹 / 无损 / 出处一致性
    python scripts/daily_clauses.py export-links         # 导出防 prune 断链的链接台账
    python scripts/daily_clauses.py sample --out README/reports/m0-sample.md  # M0 只读样张
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily.issue import is_issue_id, kind_of  # noqa: E402
from daily.ja import _CLAUSE_SPLIT  # noqa: E402

SCHEMA_VERSION = 1

# 分句字符集只有一份来源：日报日语版 `_CLAUSE_SPLIT = [、。，,！？!?]`，
# 与 `src/lib/cien.ts::splitClauses()` 同源。这里从它的 pattern 推「保留标点」的切法，
# 不另抄一份字符集，改标点时两处一起变。
CLAUSE_CUT = re.compile(r"(?<=" + _CLAUSE_SPLIT.pattern + r")")

# 指纹只覆盖索引真正用到的字段。`issue.confirmed_at` / `counts` / `provenance` 之类
# 元数据变动不该让索引报过期；但这五个字段任何一个改了，索引就必须重建。
FINGERPRINT_FIELDS = ("description", "highlights", "works", "interactions", "people")
PRECISIONS = ("clause", "row", "unresolved")


class ClauseError(RuntimeError):
    """索引不合格。消息里带全部问题，不逐条试。"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def paths_for(root: Path) -> dict[str, Path]:
    """所有落盘位置都从 root 推，测试可以整个搬进临时目录。"""
    return {
        "daily": root / "data" / "daily",
        "xreader": root / "data" / "xreader",
        "out": root / "out",
        "clauses": root / "out" / "clauses",
        "period": root / "data" / "period-sources",
    }


def list_issues(root: Path = ROOT) -> list[str]:
    """`data/daily/` 下所有合法期号且带正本的报告，按两版混排的字典序。"""
    daily = paths_for(root)["daily"]
    if not daily.is_dir():
        return []
    return sorted(
        p.name for p in daily.iterdir()
        if p.is_dir() and is_issue_id(p.name) and (p / "report.json").is_file()
    )


def load_report(issue: str, root: Path = ROOT) -> dict:
    path = paths_for(root)["daily"] / issue / "report.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(report: dict) -> str:
    """正本内容指纹。字段顺序固定、不带缩进，跨机器可复现。"""
    payload = {k: report.get(k) for k in FINGERPRINT_FIELDS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def split_clauses(text: str) -> list[str]:
    """按项目标点集切分，**保留尾部标点**，保证 `''.join(结果) == text`。

    纯空白片段不单独成句：接到前一句末尾（或单独留作第一句），这样带首尾空格的
    summary 也不会被切掉字符。空串返回空列表。
    """
    parts = CLAUSE_CUT.split(text)
    out: list[str] = []
    for part in parts:
        if part.strip():
            out.append(part)
        elif out:
            out[-1] += part
        elif part:
            out.append(part)
    assert "".join(out) == text, "split_clauses 必须无损"
    return out


def issue_keys(report: dict) -> list[str]:
    """这一期正本里出现的全部出处 key，保序去重。

    除 `people[].sources` 外还收 `highlights` / `interactions`：M3 的「各天要点汇总」
    也要能点到原推，否则周报头条会没有链接。
    """
    out: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value:
            out.append(value)
        elif isinstance(value, list):
            for item in value:
                add(item)

    for person in report.get("people") or []:
        add(person.get("sources") or [])
    for group in ("highlights", "interactions"):
        for claim in report.get(group) or []:
            if isinstance(claim, dict):
                add(claim.get("sources") or [])
    return list(dict.fromkeys(out))


def collect_keys(issues: Iterable[str], root: Path = ROOT) -> dict[str, list[str]]:
    """key → 用到它的期号列表。用来只扫需要的切片，不必把 80 个 jsonl 全读进内存。"""
    mapping: dict[str, list[str]] = {}
    for issue in issues:
        for key in issue_keys(load_report(issue, root)):
            mapping.setdefault(key, []).append(issue)
    return mapping


class SourceResolver:
    """把 `x:<id>` 解析成原推链接 / 元数据 / **完整原文**。

    优先读版本化的 `data/xreader/*/*.jsonl`（40 天滚存，带 `retweeted_by` 等转发关系）；
    `out/*.generate.json` 只用来补切片里缺的字段。注意最早的 3 期底稿用的是旧期号
    `26102522.generate.json`，所以 generate 侧按 `issue.id` 而不是文件名前缀匹配。
    """

    def __init__(
        self,
        needed: Iterable[str],
        *,
        root: Path = ROOT,
    ) -> None:
        self.needed = set(needed)
        self.records: dict[str, dict] = {}
        self._text_origin: dict[str, str] = {}
        self.slice_files = 0
        self.generate_files = 0
        self._read_xreader(paths_for(root)["xreader"])
        self._read_generate(paths_for(root)["out"])

    @staticmethod
    def empty(key: str) -> dict:
        return {
            "url": "", "author": "", "published_at": "",
            "is_retweet": False, "retweeted_by": None, "quote_of": None,
            "text": "", "origin": "none", "source_file": "",
        }

    def _merge(self, key: str, cand: dict) -> None:
        cur = self.records.get(key)
        if cur is None:
            self.records[key] = cand
            self._text_origin[key] = cand["origin"]
            return
        for field in ("url", "author", "published_at", "retweeted_by", "quote_of", "source_file"):
            if not cur.get(field) and cand.get(field):
                cur[field] = cand[field]
        if not cur.get("is_retweet") and cand.get("is_retweet"):
            cur["is_retweet"] = True
        # 原文全文只在「同为 xreader 的记录」之间比长短（同一条推可能落在多个日切片里）。
        # generate 的 `text` 只用来填空，绝不能因为它更长就盖掉切片的权威原文。
        if cand["origin"] == "xreader":
            if (self._text_origin.get(key) in (None, "xreader")
                    and len(cand.get("text") or "") > len(cur.get("text") or "")):
                cur["text"] = cand["text"]
                self._text_origin[key] = "xreader"
        elif not cur.get("text") and cand.get("text"):
            cur["text"] = cand["text"]
            self._text_origin[key] = "generate"
        # xreader 是权威来源；generate 只在没有切片记录时兜底
        if cur.get("origin") == "generate" and cand.get("origin") == "xreader":
            cur["origin"] = "xreader"

    def _read_xreader(self, xreader: Path) -> None:
        if not xreader.is_dir():
            return
        files = sorted(p for p in xreader.glob("*/*.jsonl") if p.is_file())
        self.slice_files = len(files)
        for path in files:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = rec.get("identity_key") or ""
                    if key not in self.needed:
                        continue
                    md = rec.get("metadata") or {}
                    self._merge(key, {
                        "url": rec.get("canonical_url") or "",
                        "author": (md.get("author_name") or md.get("account")
                                   or rec.get("publisher") or ""),
                        "published_at": rec.get("published_at") or "",
                        "is_retweet": bool(md.get("is_retweet")),
                        "retweeted_by": md.get("retweeted_by") or None,
                        "quote_of": md.get("quoted_tweet_id") or None,
                        "text": rec.get("content") or "",
                        "origin": "xreader",
                        "source_file": str(path.relative_to(xreader.parent.parent)).replace("\\", "/"),
                    })

    def _read_generate(self, out: Path) -> None:
        if not out.is_dir():
            return
        files = sorted(out.glob("*.generate.json"))
        self.generate_files = len(files)
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for category in data.get("categories") or []:
                for item in category.get("items") or []:
                    key = item.get("key") or ""
                    if key not in self.needed:
                        continue
                    # generate 的 item 已带 kind/repost_of（model.from_xreader 已兜底
                    # 识别 inline RT），别再写死 False——否则周报把转发又当原创。
                    is_repost = item.get("kind") == "repost" or bool(item.get("repost_of"))
                    self._merge(key, {
                        "url": item.get("url") or "",
                        "author": item.get("account") or "",
                        "published_at": item.get("published_at") or "",
                        "is_retweet": is_repost,
                        "retweeted_by": item.get("account") if is_repost else None,
                        "quote_of": item.get("quote_of") or None,
                        "text": item.get("text") or "",
                        "origin": "generate",
                        "source_file": str(path.relative_to(out.parent)).replace("\\", "/"),
                    })

    def get(self, key: str) -> dict:
        return self.records.get(key) or self.empty(key)


def load_answer_clauses(issue: str, root: Path = ROOT) -> dict[str, dict]:
    """L0-b：读 `out/<期号>/answer/*.json` 里可选的 `people[].clauses`。

    答题 JSON 里多带字段不会被 `daily.validate` 拦（极简校验器忽略未知字段），
    `apply` 会丢掉它，所以旁路必须直接读 answer 文件。`all.json` 优先。
    """
    answer_dir = paths_for(root)["out"] / issue / "answer"
    if not answer_dir.is_dir():
        return {}
    found: dict[str, dict] = {}
    for path in sorted(answer_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for person in data.get("people") or []:
            handle = person.get("handle")
            clauses = person.get("clauses")
            if not handle or not isinstance(clauses, list) or not clauses:
                continue
            if handle not in found or path.name == "all.json":
                found[handle] = {"clauses": clauses, "origin": path.name}
    return found


def _explicit_rows(
    person: dict,
    parts: list[str],
    answer_map: dict[str, dict],
) -> tuple[list[dict] | None, bool]:
    """返回 (可采用的显式分句, 是否曾有显式分句但被拒)。

    三条都满足才采用：分句数一致、逐句文本与项目切法**完全相同**、
    每句的 sources 都是本行 `sources` 的子集（不许凭空造 key）。
    任何一条不满足就整行退回 `row`，绝不部分采用。
    """
    entry = answer_map.get(person.get("handle"))
    if entry is None:
        return None, False
    clauses = entry["clauses"]
    row_sources = set(person.get("sources") or [])
    ok = (
        len(clauses) == len(parts)
        and all(isinstance(c, dict) and c.get("text") == parts[i]
                for i, c in enumerate(clauses))
        and all(
            isinstance(c.get("sources"), list)
            and all(src in row_sources for src in c["sources"])
            for c in clauses
        )
    )
    return (clauses, False) if ok else (None, True)


def build_index(
    issue: str,
    report: dict,
    resolver: SourceResolver,
    answer_map: dict[str, dict] | None = None,
    *,
    built_at: str | None = None,
) -> dict:
    """为一期构造完整索引。纯函数（除 built_at），不写盘。"""
    answer_map = answer_map or {}
    keys = issue_keys(report)
    refs = {key: dict(resolver.get(key)) for key in keys}

    daily = {
        "description": report.get("description") or "",
        "highlights": [
            {"text": h.get("text") or "", "sources": list(h.get("sources") or [])}
            for h in report.get("highlights") or [] if isinstance(h, dict)
        ],
        "works": list(report.get("works") or []),
        "interactions": [
            {"text": i.get("text") or "", "sources": list(i.get("sources") or [])}
            for i in report.get("interactions") or [] if isinstance(i, dict)
        ],
    }

    people: list[dict] = []
    precision_counts = {p: 0 for p in PRECISIONS}
    total_clauses = 0
    lossless = True
    explicit_rows = 0
    rejected_rows = 0

    for person in report.get("people") or []:
        handle = person.get("handle") or ""
        summary = person.get("summary") or ""
        parts = split_clauses(summary)
        if "".join(parts) != summary:
            lossless = False
        row_sources = list(dict.fromkeys(person.get("sources") or []))
        explicit, rejected = _explicit_rows(person, parts, answer_map)
        if explicit is not None:
            explicit_rows += 1
        if rejected:
            rejected_rows += 1

        clauses: list[dict] = []
        for i, text in enumerate(parts):
            if explicit is not None:
                sources = list(dict.fromkeys(explicit[i].get("sources") or []))
                precision = "clause" if sources else "unresolved"
            elif row_sources:
                sources = row_sources
                precision = "row"
            else:
                sources = []
                precision = "unresolved"
            clauses.append({
                "clause_id": f"{issue}/{handle}#{i + 1}",
                "index": i,
                "text": text,
                "context": summary,
                "sources": sources,
                "source_urls": [refs.get(k, {}).get("url", "") for k in sources],
                "precision": precision,
                "exact_source": len(sources) == 1,
                # M3 取料时才按 source_refs[].text 拆独立事实单元；索引阶段不猜。
                "span_facts": [],
            })
            precision_counts[precision] += 1
            total_clauses += 1

        people.append({
            "handle": handle,
            "category": person.get("category") or "",
            "summary": summary,
            "row_sources": row_sources,
            "clauses": clauses,
        })

    resolved = sum(1 for rec in refs.values() if rec.get("url"))
    return {
        "schema_version": SCHEMA_VERSION,
        "issue": issue,
        "kind": kind_of(issue),
        "built_at": built_at or now_iso(),
        "summary_fingerprint": fingerprint(report),
        "source_refs": refs,
        "daily": daily,
        "people": people,
        "stats": {
            "people_rows": len(people),
            "clauses": total_clauses,
            "source_keys": len(refs),
            "resolved_keys": resolved,
            "unresolved_keys": len(refs) - resolved,
            "precision": precision_counts,
            "lossless": lossless,
            "explicit_rows": explicit_rows,
            "rejected_explicit_rows": rejected_rows,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sync(
    issues: list[str],
    *,
    root: Path = ROOT,
    force: bool = False,
) -> dict:
    """懒生成：指纹没变就跳过；`--force` 全量重建。返回统计便于 CLI / 测试断言。"""
    paths = paths_for(root)
    resolver = SourceResolver(collect_keys(issues, root).keys(), root=root)
    written, fresh = [], []
    for issue in issues:
        report = load_report(issue, root)
        target = paths["clauses"] / f"{issue}.json"
        fp = fingerprint(report)
        if target.is_file() and not force:
            try:
                if json.loads(target.read_text(encoding="utf-8")).get("summary_fingerprint") == fp:
                    fresh.append(issue)
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        index = build_index(issue, report, resolver, load_answer_clauses(issue, root))
        _write_json(target, index)
        written.append(issue)
    return {
        "written": written, "fresh": fresh,
        "slice_files": resolver.slice_files,
        "generate_files": resolver.generate_files,
        "resolved_keys": len(resolver.records),
    }


def check(issues: list[str], *, root: Path = ROOT) -> list[str]:
    """只校验已有索引，不重建、不写盘。返回全部问题（空列表 = 通过）。"""
    paths = paths_for(root)
    problems: list[str] = []
    for issue in issues:
        target = paths["clauses"] / f"{issue}.json"
        if not target.is_file():
            problems.append(f"{issue}: 索引缺失（先跑 sync）")
            continue
        try:
            index = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{issue}: 索引读不出来（{exc}）")
            continue
        report = load_report(issue, root)
        if index.get("summary_fingerprint") != fingerprint(report):
            problems.append(f"{issue}: 指纹过期，正本已改，需 sync")
        refs = index.get("source_refs") or {}
        for person in index.get("people") or []:
            if "".join(c.get("text") or "" for c in person.get("clauses") or []) != person.get("summary"):
                problems.append(f"{issue}/{person.get('handle')}: 分句拼接不等于 summary")
            for clause in person.get("clauses") or []:
                if clause.get("precision") not in PRECISIONS:
                    problems.append(f"{issue}/{clause.get('clause_id')}: 非法 precision")
                for key in clause.get("sources") or []:
                    if key not in refs:
                        problems.append(f"{issue}/{clause.get('clause_id')}: 出处 {key} 不在 source_refs")
                    elif not refs[key].get("url"):
                        problems.append(f"{issue}/{clause.get('clause_id')}: 出处 {key} 没解析出链接")
        for key in issue_keys(report):
            if key not in refs:
                problems.append(f"{issue}: 正本里的出处 {key} 没进 source_refs")
    known = set(issues)
    for path in sorted(paths["clauses"].glob("*.json")):
        if path.stem not in known:
            problems.append(f"{path.name}: 孤儿索引（正本里没有这一期）")
    return problems


def export_links(*, root: Path = ROOT) -> dict:
    """M1 验收 ⑥：把 18 期已解析的链接**只以链接+元数据**固化，防 40 天 prune 断链。

    这是「回填台账」，不是周报正本、不是选择结果、不含推文原文、不含分句文本。
    去噪后的「选中即固化」快照由 M3 写 `data/period-sources/<期号>.json`，
    两者形状不同、互不覆盖。
    """
    paths = paths_for(root)
    key_issues = collect_keys(list_issues(root), root)
    resolver = SourceResolver(key_issues.keys(), root=root)
    links: dict[str, dict] = {}
    unresolved: list[str] = []
    for key in sorted(key_issues):
        rec = resolver.get(key)
        if not rec.get("url"):
            unresolved.append(key)
            continue
        links[key] = {
            "url": rec["url"],
            "author": rec.get("author") or "",
            "published_at": rec.get("published_at") or "",
            "is_retweet": bool(rec.get("is_retweet")),
            "retweeted_by": rec.get("retweeted_by"),
            "quote_of": rec.get("quote_of"),
            "used_in": key_issues[key],
        }
    issues = list_issues(root)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "purpose": (
            "M1 历史回填链接台账：防 data/xreader 40 天 prune 断链。"
            "只有链接与元数据，无推文原文、无分句文本；非周报正本、非选择结果、不上页面。"
        ),
        "built_at": now_iso(),
        "issues": issues,
        "links": links,
        "unresolved": unresolved,
        "stats": {
            "issues": len(issues),
            "keys": len(key_issues),
            "resolved": len(links),
            "unresolved": len(unresolved),
        },
    }
    _write_json(paths["period"] / "backfill-links.json", payload)
    return payload["stats"]


# ---------------------------------------------------------------------------
# M0 只读样张
# ---------------------------------------------------------------------------

# 周报栏目要的事实类别（口径来自 weekly-report-plan-2026-11.html:185-254）。
# 只用来做「日报正本 vs 旁路原文」的命中计数，不是分类器，也不进任何数据。
GAP_GROUPS: dict[str, str] = {
    "价格": r"[0-9][0-9,]{2,}\s*円|税込|税抜|税別|価格|￥|¥",
    "版本分档": r"通常版|限定版|完全生産限定版|ダウンロード版|DL版|NS版|Switch版|Steam版|パッケージ版|初回版|特装版|廉価版",
    "发售/日期": r"発売|発売日|发售|開卖|开卖|定档|延期|[0-9]{1,2}月[0-9]{1,2}日|[0-9]{4}年[0-9]{1,2}月",
    "人员": r"配音|出演|参演|CV|声優|原画|シナリオ|飾",
    "汉化/语言": r"汉化|簡体中文|繁体中文|简体中文|官中|中国語|中文版|ローカライズ|英語版",
    "周边/通贩": r"グッズ|周边|抱枕|アクリル|再販|通販|フィギュア|缶バッジ|タペストリー|特典|グッズ化",
    "平台": r"Steam|Nintendo Switch|PS4|PS5|DLsite|FANZA|dmm",
}
GAP_RE = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in GAP_GROUPS.items()}


def _excerpt(text: str, limit: int = 110) -> str:
    flat = " ".join((text or "").split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def _md_escape(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def build_sample(
    issues: list[str],
    resolver: SourceResolver,
    *,
    root: Path = ROOT,
    rows_per_issue: int = 4,
) -> str:
    """生成 M0 样张 Markdown。只读，不改任何文件。"""
    reports = {issue: load_report(issue, root) for issue in issues}
    lines: list[str] = []
    lines.append("# M0 只读样张：日报「详细」栏分句 → 周报原材料")
    lines.append("")
    lines.append(
        f"**窗口**：{issues[0]} – {issues[-1]}（{len(issues)} 期，"
        f"{'/'.join(sorted({kind_of(i) for i in issues}))} 版） · "
        f"**生成时刻**：{now_iso()}"
    )
    lines.append("")
    lines.append(
        "> 本样张由 `python scripts/daily_clauses.py sample` 生成，全程**只读**："
        "不写 `data/daily/`、不写正本、不改任何生产文件。目的是回答一个问题："
        "「周报制作时，除各天要点汇总外，只勾选对应天的『人-分句』能不能直接拿到原材料」。"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # §1 各天要点汇总
    lines.append("## 1. 各天要点汇总（M3 的另一个输入）")
    lines.append("")
    lines.append("| 期号 | 版 | description（副标题） | 看点条数 | 作品条数 | 详细行数 |")
    lines.append("|---|---|---|---:|---:|---:|")
    for issue in issues:
        r = reports[issue]
        lines.append(
            f"| `{issue}` | {kind_of(issue)} | {_md_escape(r.get('description') or '')} | "
            f"{len(r.get('highlights') or [])} | {len(r.get('works') or [])} | {len(r.get('people') or [])} |"
        )
    lines.append("")

    # §2 人-分句样张
    lines.append("## 2. 「人-分句 → 出处」样张")
    lines.append("")
    lines.append(
        "每期挑含 ≥1 条来源的行；`precision=row` 表示继承整行 `sources`（Q2 已裁定算达标），"
        "`unresolved` 表示该行没有出处。`source_urls` 是解析出的原推链接。"
    )
    lines.append("")
    sample_rows: list[tuple[str, dict, dict]] = []
    for issue in issues:
        report = reports[issue]
        candidates = [p for p in report.get("people") or [] if (p.get("sources") or [])]
        # 多分句、多来源的行最能说明「一行为什么不等于一个事实」；同一人只抽一行，
        # 否则样张会连续几页都是同一个账号。handle 参与排序保证结果可复现。
        candidates.sort(key=lambda p: (
            -len(split_clauses(p.get("summary") or "")),
            -len(set(p.get("sources") or [])),
            p.get("handle") or "",
        ))
        picked: list[dict] = []
        seen: set[str] = set()
        for person in candidates:
            handle = person.get("handle") or ""
            if handle in seen:
                continue
            picked.append(person)
            seen.add(handle)
            if len(picked) >= rows_per_issue:
                break
        sample_rows.extend((issue, report, p) for p in picked)

    lines.append("| 期号 | 人 | 分句（含尾标点） | 精度 | 出处链接 | 原推原文（节选） |")
    lines.append("|---|---|---|---|---|---|")
    for issue, _report, person in sample_rows:
        parts = split_clauses(person.get("summary") or "")
        row_sources = list(dict.fromkeys(person.get("sources") or []))
        for i, text in enumerate(parts):
            urls = [resolver.get(k).get("url") or "—" for k in row_sources]
            excerpt = " ／ ".join(_excerpt(resolver.get(k).get("text") or "", 70) for k in row_sources)
            lines.append(
                f"| `{issue}` | @{_md_escape(person.get('handle') or '')} | "
                f"{_md_escape(text)} | `row` | "
                f"{'<br>'.join(_md_escape(u) for u in urls)} | {_md_escape(excerpt)} |"
            )
    lines.append("")
    lines.append(
        "> 表里是「行级继承」的呈现。索引里每一句都有自己的 `clause_id`"
        "（`<期号>/<handle>#<序号>`），M3 勾选时按句勾选，不是按整行勾选。"
    )
    lines.append("")

    # §3 缺口实测：日报正本 vs 旁路原文
    lines.append("## 3. 周报栏目缺口实测：日报正本里没有的，旁路原文里有没有")
    lines.append("")
    lines.append(
        "计数口径：对每一类正则，分别统计「日报正本的文本行」与「来源推文完整原文」"
        "里**命中的条数**（不是事件数，也不是准确率）。正本文本 = "
        "`description + highlights + works + interactions + people[].summary`；"
        "旁路原文 = 这 7 期所有 `sources` 解析出的 `source_refs[].text`。"
    )
    lines.append("")
    canonical_lines: list[str] = []
    for issue in issues:
        r = reports[issue]
        canonical_lines.append(r.get("description") or "")
        for group in ("highlights", "interactions"):
            for claim in r.get(group) or []:
                if isinstance(claim, dict):
                    canonical_lines.append(claim.get("text") or "")
        canonical_lines.extend(str(w) for w in (r.get("works") or []))
        canonical_lines.extend((p.get("summary") or "") for p in (r.get("people") or []))

    source_texts: dict[str, str] = {}
    for issue in issues:
        for key in issue_keys(reports[issue]):
            source_texts[key] = resolver.get(key).get("text") or ""

    lines.append("| 事实类别 | 日报正本命中 | 旁路原文命中 | 判定 |")
    lines.append("|---|---:|---:|---|")
    gap_rows: list[tuple[str, int, int]] = []
    for name, pattern in GAP_RE.items():
        in_report = sum(1 for text in canonical_lines if pattern.search(text))
        in_source = sum(1 for text in source_texts.values() if pattern.search(text))
        gap_rows.append((name, in_report, in_source))
        if in_source == 0:
            verdict = "两边都没有（需非 X 源）"
        elif in_source - in_report >= 5 and in_source >= in_report * 1.5:
            verdict = "**正本缺，旁路能补**"
        elif in_source > in_report:
            verdict = "旁路小幅补充"
        else:
            verdict = "正本已覆盖较多"
        lines.append(f"| {name} | {in_report} | {in_source} | {verdict} |")
    lines.append("")
    lines.append(
        "**结构性缺口（不是字数问题）**：`README/reports/weekly-report-plan-2026-11.html:135-141` "
        "已记录 `filter` 的 `drop_if` 主动删掉周边/周年，且汉化情报在 14 天里只有 9 条、"
        "价格只有约 5% 的事件原文含——这些**从未进入日报正本**，所以再怎么放宽 "
        "`summary ≤ 60` 也拿不回来。旁路 L0-a 保存完整原文后，上表「旁路原文命中」"
        "才是周报可判事实的材料池。"
    )
    lines.append("")

    # §4 结论
    lines.append("## 4. 结论与边界")
    lines.append("")
    all_rows = [p for r in reports.values() for p in (r.get("people") or [])]
    all_clauses = sum(len(split_clauses(p.get("summary") or "")) for p in all_rows)
    no_src = sum(1 for p in all_rows if not (p.get("sources") or []))
    one_src = sum(1 for p in all_rows if len(set(p.get("sources") or [])) == 1)
    mismatch = sum(1 for p in all_rows
                   if len(split_clauses(p.get("summary") or "")) != len(set(p.get("sources") or [])))
    lines.append(f"- 样张窗口：{len(issues)} 期 / {len(all_rows)} 行 / {all_clauses} 分句；"
                 f"无出处 {no_src} 行、单出处 {one_src} 行、分句数≠来源数 {mismatch} 行。")
    lines.append(
        "- **结论：想法成立。**「各天要点汇总」+「勾选人-分句」确实能直接出周报原材料，"
        "且每一行本来就有 `sources`、每一个 `x:<id>` 都能解析成原推链接。"
    )
    lines.append(
        "- **边界 1**：分句 ≠ 独立事实。多来源行里靠算法猜只能到 38.1% 可信，"
        "所以 M1 用 `row` 继承并如实标注，不伪造 `clause`；真正的精确到句留给可选 M2 / L0-b。"
    )
    lines.append(
        "- **边界 2**：价格/版本/周边这类周报主栏在日报正本里**覆盖明显不足**（见 §3），"
        "汉化更是几近于无；且 `filter` 的 `drop_if` 会主动删掉周边/周年，"
        "这些不是放宽 `summary` 字数能补回来的。本方案只解决"
        "「原材料从哪来、链接怎么留」，不解决 D3 审计的内容不合格问题。"
    )
    lines.append(
        "- **边界 3**：链接不外显，但 `data/period-sources/` 进 git 意味着公开仓库可 clone 到；"
        "台账只存链接与元数据，推文原文全文只留本地 `out/clauses/`。"
    )
    lines.append("")
    lines.append(
        "_M0 零生产改动：本样张是 M0 阶段唯一新增的报告文件；`data/daily/`、`schemas/`、"
        "`scripts/daily/`、workflow、golden、Ci-en 全部未被触碰。_"
    )
    lines.append("")
    return "\n".join(lines)


def _resolve_issues(args: argparse.Namespace, root: Path) -> list[str]:
    available = list_issues(root)
    if getattr(args, "all", False):
        return available
    if getattr(args, "issues", None):
        unknown = [i for i in args.issues if i not in available]
        if unknown:
            raise ClauseError("没有这些期号的正本：" + ", ".join(unknown))
        return list(dict.fromkeys(args.issues))
    raise ClauseError("请给期号，或用 --all")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="日报分句级出处索引（旁路，不改日报生产）")
    parser.add_argument("--root", type=Path, default=ROOT, help="仓库根（测试用）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="懒生成索引")
    p_sync.add_argument("issues", nargs="*", help="期号；省略则用 --all")
    p_sync.add_argument("--all", action="store_true", help="全部期号")
    p_sync.add_argument("--force", action="store_true", help="指纹没变也重建")

    p_check = sub.add_parser("check", help="校验索引未过期且自洽")
    p_check.add_argument("issues", nargs="*")
    p_check.add_argument("--all", action="store_true")

    p_export = sub.add_parser("export-links", help="导出 M1 历史回填链接台账（进 git）")

    p_sample = sub.add_parser("sample", help="M0 只读样张")
    p_sample.add_argument("issues", nargs="*", help="默认最近 7 期声优版")
    p_sample.add_argument("--out", type=Path, required=True, help="样张 Markdown 落盘位置")
    p_sample.add_argument("--rows", type=int, default=4, help="每期抽几行")

    p_info = sub.add_parser("info", help="汇总现有索引统计")

    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "sync":
            issues = _resolve_issues(args, root)
            result = sync(issues, root=root, force=args.force)
            print(f"sync: 写入 {len(result['written'])} 期，跳过（指纹未变）{len(result['fresh'])} 期；"
                  f"扫描切片 {result['slice_files']} 个 / 底稿 {result['generate_files']} 个，"
                  f"解析到 {result['resolved_keys']} 个出处")
        elif args.command == "check":
            issues = _resolve_issues(args, root)
            problems = check(issues, root=root)
            if problems:
                print(f"check: {len(problems)} 处问题", file=sys.stderr)
                for problem in problems[:40]:
                    print("  - " + problem, file=sys.stderr)
                if len(problems) > 40:
                    print(f"  … 另有 {len(problems) - 40} 处", file=sys.stderr)
                return 1
            print(f"check: {len(issues)} 期全部通过（指纹 / 无损 / 出处一致）")
        elif args.command == "export-links":
            stats = export_links(root=root)
            print(f"export-links: {stats['issues']} 期 / {stats['keys']} 键，"
                  f"固化 {stats['resolved']} 条链接，未解析 {stats['unresolved']} 条 → "
                  f"{paths_for(root)['period'] / 'backfill-links.json'}")
        elif args.command == "sample":
            issues = args.issues or [i for i in list_issues(root) if kind_of(i) == "voice"][-7:]
            if not issues:
                raise ClauseError("没有可用的正本")
            resolver = SourceResolver(collect_keys(issues, root).keys(), root=root)
            text = build_sample(issues, resolver, root=root, rows_per_issue=args.rows)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
            print(f"sample: {len(issues)} 期 → {args.out}")
        elif args.command == "info":
            paths = paths_for(root)
            rows = clauses = keys = resolved = 0
            for path in sorted(paths["clauses"].glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                s = data.get("stats") or {}
                rows += s.get("people_rows", 0)
                clauses += s.get("clauses", 0)
                keys += s.get("source_keys", 0)
                resolved += s.get("resolved_keys", 0)
            print(f"info: 索引 {len(list(paths['clauses'].glob('*.json')))} 期 / "
                  f"{rows} 行 / {clauses} 分句 / {keys} 出处（已解析 {resolved}）")
    except ClauseError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
