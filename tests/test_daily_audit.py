"""M3.9 事后判卷 + 整期题（flat）的回归测试。

这一组钉住的是「最常用的那条路也得判卷」：

* 自动化直接改 `report.json`，绕过了 `apply` 的判卷——`audit` 要能查出来
* 整期题（`category=all`）的 `summary` 会当副标题、`works` 是作品动态，两者都要落进正本
* `confirm` 在判卷不通过时不许定稿

    python -m unittest tests.test_daily_audit -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily import cli  # noqa: E402
from daily import paths as path_mod  # noqa: E402
from daily import prompt as prompt_mod  # noqa: E402
from daily.apply import apply  # noqa: E402
from daily.audit import ERROR, WARN, audit_report, has_errors  # noqa: E402
from daily.roster import Roster  # noqa: E402
from daily.schema import DESCRIPTION_MAX  # noqa: E402

ISSUE = "26102522"

ROSTER = {
    "schema_version": 1,
    "categories": [{"id": "seiyuu", "label": "声优"}],
    "accounts": [
        {"handle": "alice", "name": "アリス", "category": "seiyuu"},
        {"handle": "bob", "name": "ボブ", "category": "seiyuu"},
        {"handle": "carol", "name": "キャロル", "category": "seiyuu"},
    ],
}


def generate() -> dict:
    items = [
        {"key": "x:1", "account": "alice", "published_at": "2026-10-25T10:00:00+09:00",
         "kind": "post", "text": "新作が発売されます"},
        {"key": "x:2", "account": "bob", "published_at": "2026-10-25T11:00:00+09:00",
         "kind": "post", "text": "配信します"},
    ]
    return {
        "schema_version": 1,
        "issue": {
            "id": ISSUE,
            "published_at": "2026-10-25T22:00:00+09:00",
            "window": {"start": "2026-10-25T00:00:00+09:00", "end": "2026-10-26T00:00:00+09:00"},
        },
        "counts": {"items": len(items), "accounts": 2, "late": 0, "skipped_duplicate": 0},
        "categories": [
            {"id": "seiyuu", "label": "声优", "handles": ["alice", "bob"], "items": items}
        ],
        "interactions": [],
        "low_value": [],
        "late": [],
        "future": [],
        "unknown": [],
    }


def flat_answer() -> dict:
    return {
        "category": "all",
        "summary": "两人都在报新作",
        "works": "alice 的新作今天上架，bob 的配信排在明晚。",
        "highlights": [
            {"text": "alice 宣布新作发售", "sources": ["x:1"]},
            {"text": "bob 预告直播", "sources": ["x:2"]},
        ],
        "interactions": [],
        "people": [
            {"handle": "alice", "summary": "宣布新作发售", "sources": ["x:1"]},
            {"handle": "bob", "summary": "预告直播", "sources": ["x:2"]},
        ],
    }


def report_with(**overrides) -> dict:
    report = {
        "schema_version": 1,
        "issue": {"id": ISSUE, "published_at": "", "status": "draft", "confirmed_at": None},
        "counts": {"items": 2, "accounts": 2, "late": 0, "skipped_duplicate": 0},
        "description": "两人都在报新作",
        "highlights": [{"text": "alice 宣布新作发售", "sources": ["x:1"]}],
        "insights": [],
        "interactions": [],
        "works": "一段作品动态",
        "categories": [],
        "accounts": ["alice", "bob"],
        "people": [
            {"handle": "alice", "category": "", "summary": "宣布新作", "via": [], "sources": ["x:1"]},
            {"handle": "bob", "category": "", "summary": "预告直播", "via": [], "sources": ["x:2"]},
        ],
        "provenance": {"generator": "daily", "prompt_version": 1, "cache_key": "", "generated_at": ""},
    }
    report.update(overrides)
    return report


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "out"
        self.out.mkdir()
        self.roster_path = self.root / "roster.json"
        self.roster_path.write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")
        self.roster = Roster.load(self.roster_path)

    def audit(self, report: dict, *, strict: bool = True, accounts=None) -> list:
        return audit_report(
            report,
            roster=self.roster,
            known_keys={"x:1", "x:2"},
            accounts={"alice", "bob"} if accounts is None else accounts,
            strict=strict,
        )


class AuditTest(Base):
    def test_clean_report_passes(self) -> None:
        self.assertEqual(self.audit(report_with()), [])

    def test_missing_sources_is_an_error_under_strict(self) -> None:
        report = report_with(highlights=[{"text": "没出处", "sources": []}])
        findings = self.audit(report)
        self.assertTrue(has_errors(findings))
        self.assertEqual(findings[0].path, "$.highlights[0].sources")

    def test_missing_sources_is_only_a_warning_under_lenient(self) -> None:
        report = report_with(highlights=[{"text": "没出处", "sources": []}])
        findings = self.audit(report, strict=False)
        self.assertFalse(has_errors(findings))
        self.assertEqual({f.level for f in findings}, {WARN})

    def test_orphan_source_key_is_an_error_even_under_lenient(self) -> None:
        report = report_with(highlights=[{"text": "编的", "sources": ["x:999"]}])
        findings = self.audit(report, strict=False)
        self.assertTrue(has_errors(findings))
        self.assertIn("来源不存在", str(findings[0]))

    def test_handle_outside_roster_is_an_error(self) -> None:
        report = report_with(people=[{"handle": "zoe", "summary": "编的", "sources": ["x:1"]}])
        findings = self.audit(report)
        self.assertTrue(any(f.level == ERROR and "不在名单里" in f.message for f in findings))

    def test_roster_handle_without_items_only_warns(self) -> None:
        """名单里有、当天没条目：可能是重复判定，也可能是从提及里补的，都不算错。"""
        report = report_with(
            people=[{"handle": "carol", "summary": "只出现在提及里", "sources": ["x:1"]}]
        )
        findings = self.audit(report)
        self.assertFalse(has_errors(findings))
        self.assertTrue(any("本期没有 carol 的条目" in f.message for f in findings))

    def test_duplicate_handle_is_an_error(self) -> None:
        report = report_with(
            people=[
                {"handle": "alice", "summary": "a", "sources": ["x:1"]},
                {"handle": "alice", "summary": "b", "sources": ["x:2"]},
            ]
        )
        findings = self.audit(report)
        self.assertTrue(any("重复出现" in f.message for f in findings))

    def test_long_description_is_an_error(self) -> None:
        report = report_with(description="あ" * (DESCRIPTION_MAX + 1))
        findings = self.audit(report)
        self.assertTrue(any("$.description" == f.path for f in findings))

    def test_claim_inside_category_view_is_checked_too(self) -> None:
        report = report_with(
            categories=[{"id": "seiyuu", "label": "声优", "highlights": [{"text": "x", "sources": []}]}]
        )
        findings = self.audit(report)
        self.assertTrue(any("$.categories[seiyuu].highlights[0]" in f.path for f in findings))


class FlatPromptTest(Base):
    def test_prompt_carries_every_item_and_handle(self) -> None:
        prompt = prompt_mod.build_flat(ISSUE, generate(), self.out)
        text = prompt.md_path.read_text(encoding="utf-8")
        self.assertIn("[x:1]", text)
        self.assertIn("[x:2]", text)
        self.assertIn("`alice`", text)
        self.assertIn("`bob`", text)
        self.assertIn('"works"', text)
        self.assertEqual(prompt.category, "all")
        self.assertEqual(prompt.items, 2)

    def test_second_call_hits_the_cache(self) -> None:
        prompt_mod.build_flat(ISSUE, generate(), self.out)
        again = prompt_mod.build_flat(ISSUE, generate(), self.out)
        self.assertTrue(again.cached)

    def test_flat_answer_lands_in_the_report(self) -> None:
        report = apply(
            ISSUE, [flat_answer()], roster=self.roster, generate=generate(), out_dir=self.out
        )
        self.assertEqual(report["description"], "两人都在报新作")
        self.assertEqual(report["works"], "alice 的新作今天上架，bob 的配信排在明晚。")
        self.assertEqual(len(report["highlights"]), 2)
        self.assertEqual([p["handle"] for p in report["people"]], ["alice", "bob"])

    def test_alt_handle_merges_into_the_main_row(self) -> None:
        """模型把小号当成另一个人来写时，不能真多出一行。"""
        ws = path_mod.ensure(path_mod.workspace(self.out, ISSUE))
        seeded = report_with(
            people=[
                {"handle": "alice", "category": "", "summary": "", "via": ["alice_sub"],
                 "sources": []}
            ]
        )
        path_mod.report(ws).write_text(json.dumps(seeded, ensure_ascii=False), encoding="utf-8")
        answer = {
            "category": "all",
            "summary": "一句话",
            "works": "",
            "highlights": [],
            "interactions": [],
            "people": [{"handle": "alice_sub", "summary": "小号补了一句", "sources": ["x:2"]}],
        }
        merged = apply(ISSUE, [answer], roster=self.roster, generate=generate(), out_dir=self.out)
        self.assertEqual([p["handle"] for p in merged["people"]], ["alice"])
        self.assertEqual(merged["people"][0]["summary"], "小号补了一句")


class ConfirmGateTest(Base):
    def _write_workspace(self, report: dict) -> None:
        ws = path_mod.ensure(path_mod.workspace(self.out, ISSUE))
        path_mod.report(ws).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        (self.out / f"{ISSUE}.generate.json").write_text(
            json.dumps(generate(), ensure_ascii=False), encoding="utf-8"
        )

    def _confirm(self, *extra: str) -> int:
        return cli.main(
            [
                "confirm",
                "--issue", ISSUE,
                "--out", str(self.out),
                "--roster", str(self.roster_path),
                *extra,
            ]
        )

    def test_confirm_is_refused_when_sources_are_missing(self) -> None:
        self._write_workspace(report_with(highlights=[{"text": "没出处", "sources": []}]))
        self.assertEqual(self._confirm(), 1)
        saved = json.loads(
            path_mod.report(path_mod.workspace(self.out, ISSUE)).read_text(encoding="utf-8")
        )
        self.assertEqual(saved["issue"]["status"], "draft")

    def test_confirm_passes_after_the_sources_are_filled(self) -> None:
        self._write_workspace(report_with())
        self.assertEqual(self._confirm(), 0)
        saved = json.loads(
            path_mod.report(path_mod.workspace(self.out, ISSUE)).read_text(encoding="utf-8")
        )
        self.assertEqual(saved["issue"]["status"], "confirmed")

    def test_no_audit_lets_a_source_less_report_through(self) -> None:
        self._write_workspace(report_with(highlights=[{"text": "没出处", "sources": []}]))
        self.assertEqual(self._confirm("--no-audit"), 0)

    def test_migrated_report_is_not_required_to_carry_sources(self) -> None:
        report = report_with(provenance={"generator": "daily.migrate", "prompt_version": 1,
                                         "cache_key": "", "generated_at": ""})
        self._write_workspace(report)
        self.assertEqual(self._confirm(), 0)


if __name__ == "__main__":
    unittest.main()
