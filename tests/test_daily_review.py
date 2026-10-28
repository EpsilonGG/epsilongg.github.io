"""M3.8 判卷与定稿的回归测试。

四条必须成立的：

* 坏回答被拒（缺来源、孤儿来源、名单外 handle、超长、重复）
* 定稿之后 `apply` 被拒
* `reopen` 之后旧版本进了 `history/`
* 输入没变时缓存命中、不重写题面

    python -m unittest tests.test_daily_review -v
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

from daily import confirm as confirm_mod  # noqa: E402
from daily import paths as path_mod  # noqa: E402
from daily import prompt as prompt_mod  # noqa: E402
from daily.apply import ApplyError, apply  # noqa: E402
from daily.roster import Roster  # noqa: E402
from daily.validate import ValidationError, validate_answer  # noqa: E402

ISSUE = "261025"


def generate(extra_item: dict | None = None) -> dict:
    items = [
        {"key": "x:1", "account": "alice", "published_at": "2026-10-25T10:00:00+09:00",
         "kind": "post", "text": "新作が発売されます"},
        {"key": "x:2", "account": "bob", "published_at": "2026-10-25T11:00:00+09:00",
         "kind": "post", "text": "配信します"},
    ]
    if extra_item:
        items.append(extra_item)
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


def good_answer() -> dict:
    return {
        "category": "seiyuu",
        "summary": "两位都在报新作",
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


ROSTER = {
    "schema_version": 1,
    "categories": [{"id": "seiyuu", "label": "声优"}],
    "accounts": [
        {"handle": "alice", "name": "アリス", "category": "seiyuu"},
        {"handle": "bob", "name": "ボブ", "category": "seiyuu"},
    ],
}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "out"
        self.out.mkdir()
        (self.root / "roster.json").write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")
        self.roster = Roster.load(self.root / "roster.json")

    def check(self, answer: dict, *, keys=None, handles=None) -> None:
        validate_answer(
            answer,
            roster=self.roster,
            known_keys=keys or {"x:1", "x:2"},
            handles=handles or {"alice", "bob"},
            category="seiyuu",
        )

    def apply(self, answer: dict, *, force: bool = False) -> dict:
        return apply(ISSUE, [answer], roster=self.roster, generate=generate(), out_dir=self.out, force=force)


class ValidationTest(Base):
    def test_good_answer_passes(self) -> None:
        self.check(good_answer())

    def test_claim_without_sources_is_rejected(self) -> None:
        answer = good_answer()
        answer["highlights"][0]["sources"] = []
        with self.assertRaises(ValidationError) as ctx:
            self.check(answer)
        self.assertIn("$.highlights[0].sources", str(ctx.exception))

    def test_orphan_source_is_rejected(self) -> None:
        answer = good_answer()
        answer["people"][0]["sources"] = ["x:999"]
        with self.assertRaises(ValidationError) as ctx:
            self.check(answer)
        self.assertIn("来源不存在", str(ctx.exception))
        self.assertIn("$.people[0].sources[0]", str(ctx.exception))

    def test_handle_outside_roster_is_rejected(self) -> None:
        answer = good_answer()
        answer["people"][0]["handle"] = "carol"
        with self.assertRaises(ValidationError) as ctx:
            self.check(answer)
        self.assertIn("不在名单里", str(ctx.exception))

    def test_handle_from_another_category_is_rejected(self) -> None:
        answer = good_answer()
        answer["people"][0]["handle"] = "bob"
        with self.assertRaises(ValidationError) as ctx:
            self.check(answer, handles={"alice"})
        self.assertIn("不在本题的 handles 里", str(ctx.exception))

    def test_summary_over_limit_is_rejected(self) -> None:
        answer = good_answer()
        answer["summary"] = "あ" * 61
        with self.assertRaises(ValidationError) as ctx:
            self.check(answer)
        self.assertIn("$.summary", str(ctx.exception))

    def test_duplicate_handle_is_rejected(self) -> None:
        answer = good_answer()
        answer["people"][1]["handle"] = "alice"
        with self.assertRaises(ValidationError) as ctx:
            self.check(answer)
        self.assertIn("重复出现", str(ctx.exception))


class ConfirmTest(Base):
    def test_apply_writes_report(self) -> None:
        report = self.apply(good_answer())
        self.assertEqual(report["issue"]["status"], "draft")
        self.assertEqual(report["description"], "")
        self.assertEqual(report["categories"][0]["summary"], "两位都在报新作")
        alice = next(p for p in report["people"] if p["handle"] == "alice")
        self.assertEqual(alice["summary"], "宣布新作发售")
        self.assertEqual(alice["sources"], ["x:1"])

    def test_apply_does_not_wipe_untouched_fields(self) -> None:
        self.apply(good_answer())
        partial = {
            "category": "seiyuu",
            "summary": "两位都在报新作",
            "highlights": [],
            "interactions": [],
            "people": [{"handle": "bob", "summary": "改了 bob", "sources": ["x:2"]}],
        }
        report = self.apply(partial)
        alice = next(p for p in report["people"] if p["handle"] == "alice")
        self.assertEqual(alice["summary"], "宣布新作发售")  # 没提 alice，就不该动她

    def test_apply_is_refused_after_confirm(self) -> None:
        self.apply(good_answer())
        confirm_mod.confirm(ISSUE, self.out)
        with self.assertRaises(ApplyError) as ctx:
            self.apply(good_answer())
        self.assertIn("已经定稿", str(ctx.exception))

    def test_reopen_moves_old_version_to_history(self) -> None:
        self.apply(good_answer())
        confirm_mod.confirm(ISSUE, self.out)
        confirm_mod.reopen(ISSUE, self.out)

        history = sorted(path_mod.history(path_mod.workspace(self.out, ISSUE)).glob("*.json"))
        self.assertTrue(history, "history/ 里应该有旧版本")
        saved = json.loads(history[0].read_text(encoding="utf-8"))
        self.assertEqual(saved["issue"]["status"], "confirmed")

        report = json.loads(path_mod.report(path_mod.workspace(self.out, ISSUE)).read_text(encoding="utf-8"))
        self.assertEqual(report["issue"]["status"], "draft")
        self.assertIsNone(report["issue"]["confirmed_at"])

        # reopen 之后能重新合并
        report = self.apply(good_answer())
        self.assertEqual(report["issue"]["status"], "draft")

    def test_confirm_twice_is_refused(self) -> None:
        self.apply(good_answer())
        confirm_mod.confirm(ISSUE, self.out)
        with self.assertRaises(confirm_mod.ConfirmError):
            confirm_mod.confirm(ISSUE, self.out)

    def test_reopen_before_confirm_is_refused(self) -> None:
        self.apply(good_answer())
        with self.assertRaises(confirm_mod.ConfirmError):
            confirm_mod.reopen(ISSUE, self.out)


class CacheTest(Base):
    def test_second_build_is_cached(self) -> None:
        first = prompt_mod.build(ISSUE, generate(), self.out)[0]
        self.assertFalse(first.cached)
        before = first.md_path.stat().st_mtime_ns

        second = prompt_mod.build(ISSUE, generate(), self.out)[0]
        self.assertTrue(second.cached)
        self.assertEqual(second.md_path.stat().st_mtime_ns, before)

    def test_changed_input_marks_stale_without_touching_report(self) -> None:
        self.apply(good_answer())
        report_path = path_mod.report(path_mod.workspace(self.out, ISSUE))
        before = report_path.read_bytes()

        prompt_mod.build(ISSUE, generate(), self.out)
        changed = generate(
            {"key": "x:3", "account": "alice", "published_at": "2026-10-25T12:00:00+09:00",
             "kind": "post", "text": "追加の告知"}
        )
        rebuilt = prompt_mod.build(ISSUE, changed, self.out)[0]

        self.assertFalse(rebuilt.cached)
        self.assertEqual(report_path.read_bytes(), before, "材料变了也不许自动覆盖正本")

    def test_prompt_lists_items_and_handles(self) -> None:
        prompt = prompt_mod.build(ISSUE, generate(), self.out)[0]
        text = prompt.md_path.read_text(encoding="utf-8")
        self.assertIn("x:1", text)
        self.assertIn("`alice`", text)
        payload = json.loads(prompt.json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["input_hash"], prompt.input_hash)
        self.assertEqual(len(payload["items"]), 2)


if __name__ == "__main__":
    unittest.main()
