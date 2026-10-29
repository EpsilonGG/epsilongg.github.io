"""M5 Ci-en 版：`daily ja` 的判卷与落盘。

这一层最容易出的错不是「翻错了」，而是**范围错了**：把制造商的条目带进 Ci-en 版、
`highlight_indexes` 和 `highlights` 条数对不上、正文里混进 `**` 让 Ci-en 当场变形。
所以测试全围着「什么时候拒绝」写。
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

from daily import ja  # noqa: E402
from daily.apply import new_report  # noqa: E402
from daily import paths  # noqa: E402
from daily.publish import publish  # noqa: E402
from daily.roster import Roster  # noqa: E402

ROSTER = {
    "schema_version": 1,
    "categories": [
        {"id": "seiyuu", "label": "声优"},
        {"id": "manufacturer", "label": "制造商"},
        {"id": "other", "label": "未归类"},
    ],
    "accounts": [
        {"handle": "re_re_tsubame", "name": "柚木つばめ", "category": "seiyuu", "role": "main"},
        {"handle": "asuparama40", "name": "御子柴泉", "category": "seiyuu", "role": "main"},
        {"handle": "chaos_R_public", "name": "CHAOS-R", "category": "manufacturer", "role": "brand"},
    ],
}

REPORT = {
    "issue": {"id": "261028", "status": "confirmed"},
    "description": "柚木つばめ关注数破 5.7 万，CHAOS-R 新作完工待发",
    "highlights": [
        {"text": "柚木つばめ关注数破 5.7 万。"},
        {"text": "御子柴泉聊录音档期。"},
        {"text": "CHAOS-R 新作完工。"},
    ],
    "works": ["发售方面……", "另一部作品同日开卖。"],
    "interactions": [{"text": "两人互相转发。"}],
    "people": [
        {"handle": "re_re_tsubame", "summary": "生誕祭周边开卖。"},
        {"handle": "chaos_R_public", "summary": "新作完工。"},
        {"handle": "asuparama40", "summary": "聊录音档期。"},
    ],
}

ANSWER = {
    "schema_version": 1,
    "hook": "柚木つばめ5.7万突破",
    "description": "柚木つばめが5.7万フォロワーを突破した一日。",
    "description_zh": "柚木つばめ粉丝破5.7万",
    "highlights": ["柚木つばめのフォロワーが5.7万を突破。", "御子柴泉が収録枠の話。"],
    "highlight_indexes": [0, 1],
    "works": ["販売面では……"],
    "interactions": ["二人が互いにリポスト。"],
    "people": [
        {"handle": "re_re_tsubame", "summary": "生誕祭グッズがBOOTHで販売開始。"},
        {"handle": "asuparama40", "summary": "収録枠の話をした。"},
    ],
}


class JaTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        roster_path = self.root / "roster.json"
        roster_path.write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")
        self.roster = Roster.load(roster_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def answer(self, **overrides) -> dict:
        payload = json.loads(json.dumps(ANSWER, ensure_ascii=False))
        payload.update(overrides)
        return payload

    # -- 判卷 ----------------------------------------------------------
    def test_accepts_a_clean_answer(self) -> None:
        ja.validate(ANSWER, REPORT, self.roster)

    def test_rejects_manufacturer(self) -> None:
        """Ci-en 只收声优：把厂商的人带进来必须当场拒绝。"""
        people = ANSWER["people"] + [
            {"handle": "chaos_R_public", "summary": "新作が完成。"}
        ]
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(self.answer(people=people), REPORT, self.roster)
        self.assertIn("不是声优", str(ctx.exception))

    def test_rejects_handle_not_in_report(self) -> None:
        people = [{"handle": "someone_else", "summary": "知らない人。"}]
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(self.answer(people=people), REPORT, self.roster)
        self.assertIn("不在这一期的正本里", str(ctx.exception))

    def test_rejects_count_mismatch(self) -> None:
        """highlight_indexes 选了 2 条、highlights 只给 1 条，读者会看到少一条的日文版。"""
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(self.answer(highlights=["一条だけ"]), REPORT, self.roster)
        self.assertIn("条数对不上", str(ctx.exception))

    def test_rejects_out_of_range_index(self) -> None:
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(
                self.answer(highlight_indexes=[0, 9], highlights=["a", "b"]), REPORT, self.roster
            )
        self.assertIn("越界", str(ctx.exception))

    def test_rejects_markdown_in_body(self) -> None:
        """`**` 会被原样打进 Ci-en，渲染器才是加粗的人。"""
        people = [{"handle": "re_re_tsubame", "summary": "**生誕祭**グッズ。"}]
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(self.answer(people=people), REPORT, self.roster)
        self.assertIn("**", str(ctx.exception))

    def test_rejects_long_hook(self) -> None:
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(self.answer(hook="あ" * (ja.HOOK_MAX + 1)), REPORT, self.roster)
        self.assertIn("hook 超长", str(ctx.exception))

    def test_rejects_people_out_of_order(self) -> None:
        """顺序要跟中文正本走，否则中日两版的人名对不上。"""
        people = list(reversed(ANSWER["people"]))
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(self.answer(people=people), REPORT, self.roster)
        self.assertIn("顺序", str(ctx.exception))

    def test_rejects_title_clause_mismatch(self) -> None:
        """中日副标题一句对一句：片方 1 句、片方 2 句就是两篇不同的稿子。"""
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(
                self.answer(description="柚木つばめが5.7万を突破。御子柴泉も収録枠を話した。"),
                REPORT,
                self.roster,
            )
        self.assertIn("分句数不一致", str(ctx.exception))

    def test_accepts_parallel_titles(self) -> None:
        """2 句对 2 句，句序也一样，就通过。"""
        ja.validate(
            self.answer(
                hook="柚木つばめ5.7万突破、御子柴泉も収録枠",
                description="柚木つばめが5.7万を突破。御子柴泉も収録枠を話した。",
                description_zh="柚木つばめ破5.7万，御子柴泉也聊录音档期",
            ),
            REPORT,
            self.roster,
        )

    def test_rejects_too_many_clauses(self) -> None:
        """副标题不是段落：超过三句就该写进 highlights。"""
        four = "一。二。三。四。"
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(
                self.answer(hook=four, description=four, description_zh="一，二，三，四"),
                REPORT,
                self.roster,
            )
        self.assertIn("分句太多", str(ctx.exception))

    def test_rejects_contact_email_in_answer(self) -> None:
        """末尾的联系邮箱由渲染器加；答案里写了就会在 Ci-en 上出现两遍。"""
        contact = ja._contact()
        self.assertTrue(contact, "profile.json 里应该有 email")
        people = [{"handle": "re_re_tsubame", "summary": f"ご連絡は {contact} まで。"}]
        with self.assertRaises(ja.JaError) as ctx:
            ja.validate(self.answer(people=people), REPORT, self.roster)
        self.assertIn("联系邮箱", str(ctx.exception))

    # -- 出题与落盘 ----------------------------------------------------
    def test_task_marks_manufacturer_as_skipped(self) -> None:
        task = ja.build_task("261028", REPORT, self.roster)
        self.assertIn("跳过（制造商）", task)
        self.assertIn("2026-10-28", task)
        self.assertIn("`re_re_tsubame`（柚木つばめ）｜声优", task)

    def test_task_states_the_title_and_contact_rules(self) -> None:
        """两条新规矩要写进题面，否则只有判卷知道、写的人不知道。"""
        task = ja.build_task("261028", REPORT, self.roster)
        self.assertIn("分句数必须一样", task)
        self.assertIn("联系邮箱不要写", task)

    def test_apply_writes_workspace_file(self) -> None:
        answer_path = self.root / "a.json"
        answer_path.write_text(json.dumps(ANSWER, ensure_ascii=False), encoding="utf-8")
        target = ja.apply("261028", answer_path, REPORT, self.roster, self.root)
        self.assertEqual(target, paths.ja_report(paths.workspace(self.root, "261028")))
        saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(saved["hook"], ANSWER["hook"])
        self.assertEqual(saved["works"], ["販売面では……"])
        self.assertEqual([p["handle"] for p in saved["people"]], ["re_re_tsubame", "asuparama40"])

    def test_apply_refuses_to_overwrite(self) -> None:
        answer_path = self.root / "a.json"
        answer_path.write_text(json.dumps(ANSWER, ensure_ascii=False), encoding="utf-8")
        ja.apply("261028", answer_path, REPORT, self.roster, self.root)
        with self.assertRaises(ja.JaError):
            ja.apply("261028", answer_path, REPORT, self.roster, self.root)

    def test_publish_carries_the_ja_file(self) -> None:
        """只发正本不发日文版，等于当天悄悄少一个出口。"""
        ws = paths.workspace(self.root / "out", "261028")
        ws.mkdir(parents=True)
        # 正本要走 publish 的 schema 校验，所以用 new_report 起一份合规的
        report = new_report(
            "261028",
            {
                "issue": {"published_at": "2026-10-29T00:41:00+09:00"},
                "counts": {"items": 12, "accounts": 3},
                "categories": [
                    {
                        "id": "people",
                        "label": "聊人",
                        "handles": ["re_re_tsubame", "chaos_R_public", "asuparama40"],
                    }
                ],
            },
        )
        report["issue"]["status"] = "confirmed"
        report["issue"]["confirmed_at"] = "2026-10-28T15:44:17+00:00"
        report["description"] = REPORT["description"]
        for person, src in zip(report["people"], REPORT["people"]):
            person["summary"] = src["summary"]
        paths.report(ws).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        paths.ja_report(ws).write_text(
            json.dumps(ANSWER, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        dest = self.root / "data"
        result = publish("261028", out_dir=self.root / "out", dest_root=dest)
        self.assertIsNotNone(result.ja_path)
        self.assertTrue((dest / "261028" / "report.ja.json").exists())


if __name__ == "__main__":
    unittest.main()
