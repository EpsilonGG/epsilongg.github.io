"""中文日报的「语言闸门」回归（2026-11-05 261105 日文漂移事故）。

事故经过：题面是中文、材料（X 推文）几乎全是日文，模型顺着材料把
`summary` / `highlights` / `works` / `people[].summary` 整篇写成日文；
`apply` 照单全收，三层闸门都没看出来，最终发布到站点。三期受影响：
261030-g / 261105 / 261105-g。

修法分两半，这里都钉住：

* 题面补硬规则 + `PROMPT_VERSION` 递增（`scripts/daily/prompt.py` / `cache.py`）；
* `scripts/daily_lang.py` 的机械判卷接进 `daily.validate.validate_answer`，
  并由 `scripts/check_daily_site.py` 对已发布正本再扫一遍。

判定口径是**日语语法信号 ≥ 2 且中文独有标记 == 0**，不是「有没有假名」：
站内中文稿本来就大量保留日文人名与作品名，用假名数量会大面积误杀。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_lang  # noqa: E402
from daily.roster import Roster  # noqa: E402
from daily.validate import ValidationError, validate_answer  # noqa: E402

ROSTER = {
    "schema_version": 1,
    "categories": [{"id": "seiyuu", "label": "声优"}],
    "accounts": [
        {"handle": "alice", "name": "柚木つばめ", "category": "seiyuu", "role": "main"},
    ],
}

# 事故里的原句（261105 / 261105-g / 261030-g），用来保证判据不会「修着修着放宽」。
DRIFTED = [
    "涼貴涼が『夢幻桜楼閣』レトラ役で発売、柚木つばめの生誕曲と小倉結衣1400本突破も",
    "ゆずソフト『千恋＊万花』アニメ化が決定、CHAOS-R新作のDL版とSMEE体験版も始動",
    "エスクード『廃村少女［弐］外伝 ～千艶万匣～』がパッケージ版・DL 版同時に発売、出演声優や原画、CG 監修から祝辞が相次いだ",
    "げっちゅ屋が『Nightmare×BlackSmith』『Dominate』などの予約を一斉に開始",
    "大山チロルがVTuberチロルニア名義でメイドカフェのアンバサダーに",
]

# 干净的中文稿：日文专有名词照站内口径保留，但叙述是中文。
CLEAN = [
    "涼貴涼为『夢幻桜楼閣』蕾特拉配音并当日发售，柚木つばめ生诞曲与小倉結衣销量破 1400 本",
    "escude『廃村少女［弐］外伝 ～千艶万匣～』盒装版与 DL 版同日发售，出演声优、原画与 CG 监修接连发来贺词",
    "ゆずソフト『千恋＊万花』确定动画化，全球销量破 100 万本、2027 年播出，原班声优续投",
    "柚木つばめ公开生诞纪念曲「Chun pi Tune」MV，manate 作曲并自称「ちゅんぴー」中毒",
    "介绍『廃村少女［弐］外伝』与『D.C.5 to 4』发售，并回顾『聖騎士セルシア』发售日",
]


class DetectorTest(unittest.TestCase):
    def test_flags_real_drifted_sentences(self) -> None:
        for text in DRIFTED:
            with self.subTest(text=text[:24]):
                self.assertTrue(daily_lang.is_japanese(text))

    def test_clean_chinese_with_japanese_proper_nouns_passes(self) -> None:
        for text in CLEAN:
            with self.subTest(text=text[:24]):
                self.assertFalse(daily_lang.is_japanese(text))

    def test_quoted_japanese_titles_are_not_evidence(self) -> None:
        self.assertFalse(daily_lang.is_japanese("『イク家畜～男性拘束搾精工場～』发售中，大山チロル出演"))
        self.assertFalse(daily_lang.is_japanese("公开生诞纪念曲「ちゅんぴー」的新 MV"))

    def test_empty_and_non_strings_are_ignored(self) -> None:
        for value in ("", "   ", None, 42, [], {}):
            self.assertFalse(daily_lang.is_japanese(value))  # type: ignore[arg-type]

    def test_scores_are_capped_and_stable(self) -> None:
        jp, zh = daily_lang.scores(DRIFTED[0])
        self.assertGreaterEqual(jp, 2)
        self.assertEqual(0, zh)
        self.assertLessEqual(jp, daily_lang._SCORE_CAP)


class ScanTest(unittest.TestCase):
    def test_scan_answer_walks_both_shapes(self) -> None:
        answer = {
            "category": "all",
            "summary": DRIFTED[0],
            "highlights": [
                {"text": DRIFTED[1], "sources": ["x:1"]},
                {"text": "中文看点，不带日文叙述", "sources": ["x:1"]},
            ],
            "interactions": [{"text": "互动中文句", "sources": ["x:1"]}],
            "works": [DRIFTED[2], "作品今日发售"],
            "people": [
                {"handle": "alice", "summary": DRIFTED[3], "sources": ["x:1"]},
                {"handle": "alice2", "summary": "中文一句", "sources": ["x:1"]},
            ],
        }
        paths = [path for path, _ in daily_lang.scan_answer(answer)]
        self.assertEqual(
            ["$.summary", "$.highlights[0].text", "$.works[0]", "$.people[0].summary"],
            paths,
        )

    def test_scan_report_ignores_handles_sources_and_timestamps(self) -> None:
        report = {
            "description": "中文副标题",
            "highlights": [{"text": "中文看点", "sources": ["x:1"]}],
            "works": ["中文作品动态"],
            "interactions": [{"text": "中文互动", "sources": ["x:1"]}],
            "people": [
                {"handle": "x_read_jp", "summary": "中文一句", "via": ["jp_sub"],
                 "sources": ["x:1"], "published_at": "2026-11-05T00:00:00+09:00"}
            ],
            "provenance": {"window": {"start": "…", "end": "…"}},
        }
        self.assertEqual([], daily_lang.scan_report(report))


class GateIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        path = Path(self._tmp.name) / "roster.json"
        path.write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")
        self.roster = Roster.load(path)

    def answer(self, **overrides) -> dict:
        # highlights 下限 2 条（generation.schema.json），别让形状问题抢在语言闸门前报错。
        payload = {
            "category": "all",
            "summary": DRIFTED[0],
            "highlights": [
                {"text": DRIFTED[1], "sources": ["x:1"]},
                {"text": DRIFTED[4], "sources": ["x:1"]},
            ],
            "interactions": [],
            "works": [DRIFTED[2]],
            "people": [{"handle": "alice", "summary": DRIFTED[3], "sources": ["x:1"]}],
        }
        payload.update(overrides)
        return payload

    def test_validate_answer_rejects_japanese_drift(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_answer(self.answer(), roster=self.roster,
                            known_keys={"x:1"}, handles={"alice"}, category=None)
        message = str(ctx.exception)
        self.assertIn("整句写成了日文", message)
        self.assertGreaterEqual(message.count("整句写成了日文"), 4, "逐句指到字段路径")

    def test_validate_answer_accepts_chinese_with_japanese_names(self) -> None:
        validate_answer(
            self.answer(summary=CLEAN[0], works=[CLEAN[1]],
                        highlights=[{"text": CLEAN[2], "sources": ["x:1"]},
                                    {"text": CLEAN[4], "sources": ["x:1"]}],
                        people=[{"handle": "alice", "summary": CLEAN[3], "sources": ["x:1"]}]),
            roster=self.roster, known_keys={"x:1"}, handles={"alice"}, category=None,
        )

    def test_prompt_rules_and_cache_version_were_updated(self) -> None:
        from daily import prompt as prompt_mod  # noqa: E402
        from daily.cache import PROMPT_VERSION  # noqa: E402
        self.assertIn("所有叙述一律用简体中文", prompt_mod.RULES_FLAT)
        self.assertIn("叙述一律用简体中文", prompt_mod.RULES)
        self.assertGreaterEqual(PROMPT_VERSION, 3, "题面改了，缓存版本必须 +1")


class PublishedDataTest(unittest.TestCase):
    def test_all_published_reports_are_chinese(self) -> None:
        reports = sorted((ROOT / "data" / "daily").glob("*/report.json"))
        self.assertGreater(len(reports), 0)
        for path in reports:
            with self.subTest(issue=path.parent.name):
                bad = daily_lang.scan_report(json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual([], bad, f"{path.parent.name}: {bad[:2]}")

    def test_repaired_workspace_answers_are_chinese_when_present(self) -> None:
        """`out/` 是 gitignore 的本地副本；存在就不许还留着日文，否则重跑 apply 会盖回正本。"""
        for issue in ("261030-g", "261105", "261105-g"):
            path = ROOT / "out" / issue / "answer" / "all.json"
            if not path.exists():
                continue
            with self.subTest(issue=issue):
                bad = daily_lang.scan_answer(json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual([], bad, f"{issue}: {bad[:2]}")


if __name__ == "__main__":
    unittest.main()
