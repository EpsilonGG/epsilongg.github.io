"""日报期号规则的单元测试。

期号（`YYMMDDHH`，JST）是日报存档的主键，格式一旦漂移，旧档就找不回来了，
所以这里把它钉死。只测纯函数，不读写任何数据目录。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_digest as digest  # noqa: E402


class IssueIdTest(unittest.TestCase):
    def test_jst_evening(self) -> None:
        """用户给的例子：26 年 10 月 31 日 22 点 → 26103122。"""
        moment = datetime(2026, 10, 31, 22, 0, tzinfo=digest.JST)
        self.assertEqual(digest.issue_id_for(moment), "26103122")

    def test_utc_is_converted_to_jst(self) -> None:
        """UTC 13:00 就是 JST 22:00，期号按 JST 写。"""
        moment = datetime(2026, 10, 31, 13, 0, tzinfo=timezone.utc)
        self.assertEqual(digest.issue_id_for(moment), "26103122")

    def test_hour_is_not_truncated(self) -> None:
        """同一天的不同小时必须是不同期号——这是存档不互相覆盖的前提。"""
        a = digest.issue_id_for(datetime(2026, 10, 31, 9, 5, tzinfo=digest.JST))
        b = digest.issue_id_for(datetime(2026, 10, 31, 22, 40, tzinfo=digest.JST))
        self.assertEqual((a, b), ("26103109", "26103122"))
        self.assertNotEqual(a, b)

    def test_midnight_boundary(self) -> None:
        self.assertEqual(
            digest.issue_id_for(datetime(2027, 1, 1, 0, 0, tzinfo=digest.JST)),
            "27010100",
        )

    def test_parse_at_accepts_common_forms(self) -> None:
        for text in ("2026-10-31 22:00", "2026-10-31T22:00", "2026-10-31 22"):
            self.assertEqual(digest.issue_id_for(digest._parse_at(text)), "26103122")

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
        report = digest.build_report(self.RECORDS, "26103122")
        self.assertNotIn("title", report)
        self.assertNotIn("pubDate", report)
        # 期号之外不要再存一份时间
        self.assertEqual(report["issue"]["id"], "26103122")

    def test_keeps_three_sections(self) -> None:
        report = digest.build_report(self.RECORDS, "26103122")
        for key in ("highlights", "interactions", "people"):
            self.assertIn(key, report)

    def test_skeleton_is_a_draft(self) -> None:
        """骨架必须是 draft：`publish` 靠 status 挡住「没定稿就上线」。"""
        report = digest.build_report(self.RECORDS, "26103122")
        self.assertEqual(report["issue"]["status"], "draft")
        self.assertIsNone(report["issue"]["confirmed_at"])

    def test_mentions_issue_id(self) -> None:
        report = digest.build_report(self.RECORDS, "26103122")
        self.assertIn("26103122", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
