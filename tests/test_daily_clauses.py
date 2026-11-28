"""分句级出处索引（`scripts/daily_clauses.py`）的回归测试。

这一层最容易出的错不是「链接解析不出来」，而是**偷偷改了日报**：往正本加字段、
放宽 60 字上限、让分句切法跟 Ci-en 版分叉。所以测试分成两组：

* 前半用临时目录里的假正本/假切片，覆盖精度口径、L0-b、指纹、落盘位置；
* 后半直接对仓库真数据做只读断言（无损切分、出处可解析、台账不含原文）。

本测试文件本身不在 `tests/test_daily_protection.py` 的 PROTECTED 清单里，
但被测模块**不许**写任何受保护路径——`test_paths_are_outside_protection` 盯着这一点。
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_clauses as dc  # noqa: E402
from daily.issue import kind_of  # noqa: E402
from daily.ja import _CLAUSE_SPLIT  # noqa: E402


def _report(issue: str = "261104", *, people: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "issue": {"id": issue, "status": "confirmed"},
        "counts": {"items": 4},
        "description": "今日看点",
        "highlights": [{"text": "看点一", "sources": ["x:1"]}],
        "works": ["作品一"],
        "interactions": [{"text": "互动一", "sources": ["x:2"]}],
        "people": people if people is not None else [
            {
                "handle": "alice",
                "category": "seiyuu",
                "summary": "确认出演新作，另为一周限定再贩。",
                "sources": ["x:1", "x:2"],
            },
            {
                "handle": "bob",
                "category": "seiyuu",
                "summary": "没有出处的旧行。",
                "sources": [],
            },
        ],
        "provenance": {"generator": "daily"},
    }


def _slice_line(key: str, *, text: str = "原文全文", author: str = "alice",
                retweeted_by: str | None = None) -> str:
    return json.dumps({
        "identity_key": key,
        "content": text,
        "publisher": author,
        "canonical_url": f"https://x.com/{author}/status/{key.split(':')[-1]}",
        "published_at": "2026-11-03T15:02:31+00:00",
        "metadata": {
            "account": author, "author_name": author,
            "is_retweet": bool(retweeted_by), "retweeted_by": retweeted_by,
            "is_reply": False, "is_quote": False, "quoted_tweet_id": None,
        },
    }, ensure_ascii=False)


def make_repo(tmp: Path, issues: tuple[str, ...] = ("261104",)) -> None:
    """搭一个最小仓库：正本 + 切片 + generate 底稿。"""
    daily = tmp / "data" / "daily"
    xreader = tmp / "data" / "xreader" / "voice"
    out = tmp / "out"
    for path in (daily, xreader, out):
        path.mkdir(parents=True, exist_ok=True)
    for issue in issues:
        d = daily / issue
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text(
            json.dumps(_report(issue), ensure_ascii=False), encoding="utf-8")
        (out / f"{issue}.generate.json").write_text(json.dumps({
            "issue": {"id": issue},
            "categories": [{
                "id": "seiyuu",
                "items": [
                    {"key": "x:1", "account": "alice", "text": "generate 里的原文",
                     "url": "https://x.com/alice/status/1",
                     "published_at": "2026-11-03T15:02:31+00:00"},
                    {"key": "x:3", "account": "carol", "text": "只在 generate 里的链接",
                     "url": "https://x.com/carol/status/3",
                     "published_at": "2026-11-03T16:00:00+00:00"},
                ],
            }],
        }, ensure_ascii=False), encoding="utf-8")
    (xreader / "2026-11-03.jsonl").write_text(
        _slice_line("x:1", text="切片里的完整原文", retweeted_by="amplifier") + "\n"
        + _slice_line("x:2") + "\n",
        encoding="utf-8",
    )


class ClauseSplitTests(unittest.TestCase):
    def test_charset_is_shared_with_cien_ts(self) -> None:
        """分句字符集只有一份：daily.ja 与 src/lib/cien.ts 不许分叉。"""
        ts = (ROOT / "src" / "lib" / "cien.ts").read_text(encoding="utf-8")
        match = re.search(r"split\(/\[(.*?)\]/", ts)
        self.assertIsNotNone(match, "cien.ts 里找不到 splitClauses 的标点集")
        ts_chars = set(match.group(1))
        py_chars = set(_CLAUSE_SPLIT.pattern.strip("[]"))
        self.assertEqual(ts_chars, py_chars)
        self.assertIn("、", py_chars)
        self.assertIn("？", py_chars)

    def test_split_is_lossless_and_keeps_punctuation(self) -> None:
        samples = [
            "确认出演新作，另为一周限定再贩。",
            "没有标点的一句话",
            "一句、两句。三句！",
            " a，b。 ",
            "   ",
            "",
            "末尾带空格，另一句。 ",
        ]
        for text in samples:
            with self.subTest(text=text):
                clauses = dc.split_clauses(text)
                self.assertEqual(text, "".join(clauses))
                if text.strip():
                    for clause in clauses:
                        self.assertTrue(clause.strip())
                elif text:
                    # 纯空白不成句，但为了无损仍作为唯一一段留在结果里
                    self.assertEqual([text], clauses)
                else:
                    self.assertEqual([], clauses)
        self.assertEqual(["一句、", "两句。", "三句！"], dc.split_clauses("一句、两句。三句！"))
        self.assertEqual([], dc.split_clauses(""))


class FingerprintTests(unittest.TestCase):
    def test_stable_and_only_sensitive_to_indexed_fields(self) -> None:
        report = _report()
        fp = dc.fingerprint(report)
        self.assertTrue(fp.startswith("sha256:"))
        self.assertEqual(fp, dc.fingerprint(json.loads(json.dumps(report))))
        report["counts"]["items"] = 999
        report["issue"]["confirmed_at"] = "2026-11-05T00:00:00Z"
        self.assertEqual(fp, dc.fingerprint(report), "元数据变动不该让索引过期")
        report["people"][0]["summary"] = "改了一句话。"
        self.assertNotEqual(fp, dc.fingerprint(report))

    def test_issue_keys_cover_all_sections_and_dedupe(self) -> None:
        report = _report()
        self.assertEqual(["x:1", "x:2"], dc.issue_keys(report))
        report["works"] = {"unexpected": "shape"}  # 不是数组也不该炸
        self.assertEqual(["x:1", "x:2"], dc.issue_keys(report))


class ResolverTests(unittest.TestCase):
    def test_xreader_is_authoritative_and_generate_is_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            resolver = dc.SourceResolver({"x:1", "x:2", "x:3"}, root=root)
            self.assertEqual(1, resolver.slice_files)
            self.assertEqual(1, resolver.generate_files)
            one = resolver.get("x:1")
            self.assertEqual("xreader", one["origin"])
            self.assertEqual("切片里的完整原文", one["text"], "不能退化成 generate 的短文本")
            self.assertTrue(one["is_retweet"])
            self.assertEqual("amplifier", one["retweeted_by"])
            three = resolver.get("x:3")
            self.assertEqual("generate", three["origin"])
            self.assertEqual("https://x.com/carol/status/3", three["url"])
            self.assertEqual("", resolver.get("x:404")["url"])
            self.assertEqual("none", resolver.get("x:404")["origin"])

    def test_only_needed_keys_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            resolver = dc.SourceResolver({"x:2"}, root=root)
            self.assertEqual({"x:2"}, set(resolver.records))


class BuildIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root)
        self.report = _report()
        self.resolver = dc.SourceResolver(dc.issue_keys(self.report), root=self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_row_precision_and_clause_ids(self) -> None:
        index = dc.build_index("261104", self.report, self.resolver, built_at="fixed")
        self.assertEqual("voice", index["kind"])
        self.assertEqual(dc.fingerprint(self.report), index["summary_fingerprint"])
        alice = index["people"][0]
        self.assertEqual(["x:1", "x:2"], alice["row_sources"])
        self.assertEqual(2, len(alice["clauses"]))
        for i, clause in enumerate(alice["clauses"]):
            self.assertEqual(f"261104/alice#{i + 1}", clause["clause_id"])
            self.assertEqual("row", clause["precision"])
            self.assertEqual(["x:1", "x:2"], clause["sources"])
            self.assertEqual(2, len(clause["source_urls"]))
            self.assertFalse(clause["exact_source"])
            self.assertEqual([], clause["span_facts"], "索引阶段不许猜独立事实")
        self.assertTrue(index["stats"]["lossless"])
        # 正本里只有 x:1 / x:2；x:3 只存在于 generate 底稿，不该混进 source_refs
        self.assertEqual(2, index["stats"]["resolved_keys"])
        self.assertEqual({"x:1", "x:2"}, set(index["source_refs"]))

    def test_no_source_row_is_unresolved(self) -> None:
        index = dc.build_index("261104", self.report, self.resolver)
        bob = index["people"][1]
        self.assertEqual([], bob["row_sources"])
        for clause in bob["clauses"]:
            self.assertEqual("unresolved", clause["precision"])
            self.assertEqual([], clause["sources"])
            self.assertEqual([], clause["source_urls"])

    def test_l0b_explicit_clauses_are_adopted(self) -> None:
        parts = dc.split_clauses(self.report["people"][0]["summary"])
        answer = {"alice": {"clauses": [
            {"text": parts[0], "sources": ["x:1"]},
            {"text": parts[1], "sources": ["x:2"]},
        ], "origin": "all.json"}}
        index = dc.build_index("261104", self.report, self.resolver, answer)
        clauses = index["people"][0]["clauses"]
        self.assertEqual(["clause", "clause"], [c["precision"] for c in clauses])
        self.assertEqual([["x:1"], ["x:2"]], [c["sources"] for c in clauses])
        self.assertTrue(all(c["exact_source"] for c in clauses))
        self.assertEqual(1, index["stats"]["explicit_rows"])
        self.assertEqual(0, index["stats"]["rejected_explicit_rows"])

    def test_l0b_is_rejected_when_text_or_sources_do_not_match(self) -> None:
        bad_text = {"alice": {"clauses": [
            {"text": "完全不同的分句。", "sources": ["x:1"]},
        ], "origin": "all.json"}}
        fabricated = {"alice": {"clauses": [
            {"text": dc.split_clauses(self.report["people"][0]["summary"])[0], "sources": ["x:999"]},
        ], "origin": "all.json"}}
        for answer in (bad_text, fabricated):
            with self.subTest(answer=answer):
                index = dc.build_index("261104", self.report, self.resolver, answer)
                self.assertEqual(1, index["stats"]["rejected_explicit_rows"])
                self.assertTrue(all(c["precision"] == "row"
                                    for c in index["people"][0]["clauses"]),
                                "不合格的显式分句必须整行退回 row，不许部分采用")

    def test_answer_fragment_lists_are_ignored(self) -> None:
        # 分片出稿会把顶层为 list 的 people 片段放进 answer/，它们不是答题对象。
        answer_dir = dc.paths_for(self.root)["out"] / "261104" / "answer"
        answer_dir.mkdir(parents=True, exist_ok=True)
        (answer_dir / "p1.json").write_text(
            json.dumps([{"handle": "alice", "summary": "片段", "sources": []}],
                       ensure_ascii=False), encoding="utf-8")
        parts = dc.split_clauses(self.report["people"][0]["summary"])
        (answer_dir / "all.json").write_text(json.dumps({
            "people": [{"handle": "alice", "clauses": [
                {"text": parts[0], "sources": ["x:1"]},
                {"text": parts[1], "sources": ["x:2"]},
            ]}],
        }, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(
            ["all.json"],
            [dc.load_answer_clauses("261104", root=self.root)["alice"]["origin"]])

    def test_kind_of_separates_the_two_editions(self) -> None:
        self.assertEqual("voice", kind_of("261104"))
        self.assertEqual("galgame", kind_of("261104-g"))
        other = _report("261104-g")
        index = dc.build_index("261104-g", other, self.resolver)
        self.assertEqual("galgame", index["kind"])


class SyncAndCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root, ("261104", "261104-g"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sync_is_lazy_and_check_catches_stale_fingerprint(self) -> None:
        issues = dc.list_issues(self.root)
        self.assertEqual(["261104", "261104-g"], issues)
        first = dc.sync(issues, root=self.root)
        self.assertEqual(2, len(first["written"]))
        second = dc.sync(issues, root=self.root)
        self.assertEqual([], second["written"])
        self.assertEqual(2, len(second["fresh"]), "指纹没变就不该重写")
        self.assertEqual([], dc.check(issues, root=self.root))

        path = self.root / "data" / "daily" / "261104" / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["people"][0]["summary"] = "正本被改过了。"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        problems = dc.check(issues, root=self.root)
        self.assertTrue(any("指纹过期" in p for p in problems), problems)

        dc.sync(issues, root=self.root)
        self.assertEqual([], dc.check(issues, root=self.root))

    def test_check_reports_missing_index(self) -> None:
        self.assertTrue(any("索引缺失" in p
                            for p in dc.check(dc.list_issues(self.root), root=self.root)))

    def test_index_never_writes_into_protected_paths(self) -> None:
        dc.sync(dc.list_issues(self.root), root=self.root)
        paths = dc.paths_for(self.root)
        self.assertEqual(self.root / "out" / "clauses", paths["clauses"])
        self.assertEqual(self.root / "data" / "period-sources", paths["period"])
        self.assertNotIn("daily", paths["clauses"].parts)
        self.assertNotEqual(paths["daily"], paths["period"])
        for path in paths["clauses"].glob("*.json"):
            self.assertIn("out", path.parts)


class ExportLinksTests(unittest.TestCase):
    def test_ledger_has_only_links_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root, ("261104", "261104-g"))
            stats = dc.export_links(root=root)
            self.assertEqual(0, stats["unresolved"])
            payload = json.loads(
                (root / "data" / "period-sources" / "backfill-links.json").read_text(encoding="utf-8"))
            self.assertEqual(1, payload["schema_version"])
            allowed = {"url", "author", "published_at", "is_retweet", "retweeted_by",
                       "quote_of", "used_in"}
            for key, link in payload["links"].items():
                self.assertLessEqual(set(link), allowed, f"{key} 带了不该有的字段")
                self.assertTrue(link["url"].startswith("https://x.com/"))
            raw = json.dumps(payload, ensure_ascii=False)
            for forbidden in ("切片里的完整原文", "generate 里的原文", "确认出演新作"):
                self.assertNotIn(forbidden, raw, "台账不许带推文原文或日报分句")


class RealDataTests(unittest.TestCase):
    """只读的仓库级断言：正本切分无损、链接可解析、台账落点不上页面。"""

    def test_all_real_reports_split_losslessly(self) -> None:
        issues = dc.list_issues(ROOT)
        self.assertGreaterEqual(len(issues), 18)
        for issue in issues:
            report = dc.load_report(issue, ROOT)
            for person in report.get("people") or []:
                summary = person.get("summary") or ""
                with self.subTest(issue=issue, handle=person.get("handle")):
                    self.assertEqual(summary, "".join(dc.split_clauses(summary)))

    def test_all_real_source_keys_resolve(self) -> None:
        issues = dc.list_issues(ROOT)
        slices = list((ROOT / "data" / "xreader").glob("*/*.jsonl")) \
            if (ROOT / "data" / "xreader").is_dir() else []
        if not slices:
            self.skipTest("没有版本化切片，跳过链接解析断言")
        mapping = dc.collect_keys(issues, ROOT)
        resolver = dc.SourceResolver(mapping.keys(), root=ROOT)
        unresolved = [key for key in mapping if not resolver.get(key)["url"]]
        self.assertEqual([], unresolved, "有出处解析不出原推链接")

    def test_period_sources_dir_is_not_an_astro_loader(self) -> None:
        config = (ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
        self.assertIn("base: './data/daily'", config)
        self.assertNotIn("period-sources", config, "台账目录绝不能被 Astro loader 读到")


if __name__ == "__main__":
    unittest.main()
