"""日报期号规则的单元测试。

期号（`YYMMDD`，JST）是日报存档的主键，格式一旦漂移，旧档就找不回来了，
所以这里把它钉死。只测纯函数，不读写任何数据目录。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_digest as digest  # noqa: E402


class IssueIdTest(unittest.TestCase):
    """一天两期：声优版 `YYMMDD`、Galgame 版 `YYMMDD-g`——期号里没有小时。"""

    def test_one_issue_per_day(self) -> None:
        self.assertEqual(digest.issue_id_for(date_cls(2026, 10, 31)), "261031")

    def test_second_issue_same_day_gets_suffix(self) -> None:
        day = date_cls(2026, 10, 31)
        self.assertEqual(digest.issue_id_for(day, 2), "261031-2")
        self.assertEqual(digest.issue_id_for(day, 10), "261031-10")

    def test_galgame_edition_gets_g_suffix(self) -> None:
        day = date_cls(2026, 10, 31)
        self.assertEqual(digest.issue_id_for(day, 1, "galgame"), "261031-g")
        self.assertEqual(digest.issue_id_for(day, 2, "galgame"), "261031-g2")

    def test_seq_starts_at_one(self) -> None:
        with self.assertRaises(ValueError):
            digest.issue_id_for(date_cls(2026, 10, 31), 0)

    def test_unknown_kind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            digest.issue_id_for(date_cls(2026, 10, 31), 1, "blog")

    def test_parse_round_trip(self) -> None:
        day = date_cls(2026, 10, 31)
        self.assertEqual(digest.parse_issue_id("261031"), (day, "voice", 1))
        self.assertEqual(digest.parse_issue_id("261031-2"), (day, "voice", 2))
        self.assertEqual(digest.parse_issue_id("261031-g"), (day, "galgame", 1))
        self.assertEqual(digest.parse_issue_id("261031-g2"), (day, "galgame", 2))

    def test_day_and_seq_helpers(self) -> None:
        self.assertEqual(digest.day_of("261031-2"), date_cls(2026, 10, 31))
        self.assertEqual(digest.seq_of("261031-2"), 2)
        self.assertEqual(digest.seq_of("261031"), 1)
        self.assertEqual(digest.seq_of("261031-g"), 1)
        self.assertEqual(digest.seq_of("261031-g2"), 2)

    def test_old_id_is_voice(self) -> None:
        """10-29 之前的期号都没有后缀，一律读成声优版——旧档不用迁移。"""
        self.assertEqual(digest.kind_of("261025"), "voice")
        self.assertEqual(digest.kind_of("261031-g"), "galgame")

    def test_old_hourly_id_is_rejected(self) -> None:
        """旧的八位期号不再合法：它把名义 22:00 当成了内容覆盖的时刻。"""
        with self.assertRaises(ValueError):
            digest.parse_issue_id("26103122")
        self.assertFalse(digest.is_issue_id("26103122"))

    def test_suffix_one_is_rejected(self) -> None:
        """第 1 期不写后缀，`261031-1` / `261031-g1` 是写错了而不是等价写法。"""
        with self.assertRaises(ValueError):
            digest.parse_issue_id("261031-1")
        with self.assertRaises(ValueError):
            digest.parse_issue_id("261031-g1")

    def test_impossible_day_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            digest.parse_issue_id("260230")

    def test_is_issue_id(self) -> None:
        self.assertTrue(digest.is_issue_id("261031"))
        self.assertTrue(digest.is_issue_id("261031-3"))
        self.assertTrue(digest.is_issue_id("261031-g"))
        self.assertTrue(digest.is_issue_id("261031-g3"))
        self.assertFalse(digest.is_issue_id("26103"))
        self.assertFalse(digest.is_issue_id("261031-"))
        self.assertFalse(digest.is_issue_id("261031x"))
        self.assertFalse(digest.is_issue_id(""))

    def test_parse_at_accepts_common_forms(self) -> None:
        """`--at` 只写 `issue.published_at`，不再决定期号。"""
        for text in ("2026-10-31 22:00", "2026-10-31T22:00", "2026-10-31 22"):
            self.assertEqual(digest._parse_at(text).date(), date_cls(2026, 10, 31))

    def test_parse_at_is_jst(self) -> None:
        self.assertEqual(digest._parse_at("2026-10-31 22:00").utcoffset(), digest.JST.utcoffset(None))

    def test_parse_at_rejects_garbage(self) -> None:
        with self.assertRaises(SystemExit):
            digest._parse_at("31/10/2026")


class SkeletonTest(unittest.TestCase):
    """骨架里不该再出现时间字段——时间只有期号一个来源。"""

    RECORDS = [
        {
            "publisher": "someone",
            "content": "hello",
            "published_at": "2026-10-31T12:00:00Z",
            "metadata": {"stats": {"likes": 3, "retweets": 1}},
        }
    ]

    def test_no_title_or_pubdate(self) -> None:
        report = digest.build_report(self.RECORDS, "261031")
        self.assertNotIn("title", report)
        self.assertNotIn("pubDate", report)
        # 期号之外不要再存一份时间
        self.assertEqual(report["issue"]["id"], "261031")

    def test_keeps_three_sections(self) -> None:
        report = digest.build_report(self.RECORDS, "261031")
        for key in ("highlights", "interactions", "people"):
            self.assertIn(key, report)

    def test_skeleton_is_a_draft(self) -> None:
        """骨架必须是 draft：`publish` 靠 status 挡住「没定稿就上线」。"""
        report = digest.build_report(self.RECORDS, "261031")
        self.assertEqual(report["issue"]["status"], "draft")
        self.assertIsNone(report["issue"]["confirmed_at"])

    def test_mentions_issue_id(self) -> None:
        report = digest.build_report(self.RECORDS, "261031")
        self.assertIn("261031", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
