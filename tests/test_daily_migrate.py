"""M4.1 迁移：Markdown frontmatter → `report.json`。

迁移是一次性的，但它定下的**字段映射**是长期的：以后如果有人要重新迁一遍
（比如老期号在别的地方还有副本），必须得到同一份 JSON。所以这里测两件事：
映射对不对、同一份输入跑两次是不是逐字节一样。

需要 PyYAML；没有就整组跳过，不让环境问题变成红色的测试。
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

from daily.migrate import (  # noqa: E402
    MigrateError,
    migrate,
    report_from_meta,
    split_frontmatter,
)

try:  # pragma: no cover - 只是探测环境
    import yaml  # noqa: F401

    HAS_YAML = True
except ModuleNotFoundError:  # pragma: no cover
    HAS_YAML = False

MD = """---
description: "柚木つばめ汇总生誕祭活动详情"
source: ai
accounts:
  - re_re_tsubame
  - mirai_chiroru
highlights:
  - "第一段看点"
  - "第二段看点"
works: "一段作品动态"
interactions:
  - "两人发了同一段说明"
people:
  - handle: re_re_tsubame
    summary: "汇总生日活动详情"
    via:
      - tsubame_sub
  - handle: mirai_chiroru
    summary: "帮忙扩散"
---

<!-- 正文是空的，站点只读 frontmatter -->
"""


class FrontmatterTest(unittest.TestCase):
    def test_split(self) -> None:
        body = split_frontmatter(MD)
        self.assertTrue(body.startswith("description:"))
        self.assertNotIn("<!--", body)

    def test_missing_frontmatter(self) -> None:
        with self.assertRaises(MigrateError):
            split_frontmatter("# 只有正文\n")

    def test_unclosed_frontmatter(self) -> None:
        with self.assertRaises(MigrateError):
            split_frontmatter("---\ndescription: x\n")


@unittest.skipUnless(HAS_YAML, "需要 PyYAML")
class ReportFromMetaTest(unittest.TestCase):
    def meta(self) -> dict:
        return yaml.safe_load(split_frontmatter(MD))

    def test_issue_fields_come_from_the_id(self) -> None:
        report = report_from_meta(self.meta(), "26102322")
        self.assertEqual(report["issue"]["id"], "26102322")
        self.assertEqual(report["issue"]["published_at"], "2026-10-23T22:00:00+09:00")
        # 迁移的都是已经上线的期，状态照实写，否则 `publish` 会拒绝它们
        self.assertEqual(report["issue"]["status"], "confirmed")
        self.assertEqual(report["issue"]["window"]["start"], "2026-10-23T00:00:00+09:00")
        self.assertEqual(report["issue"]["window"]["end"], "2026-10-24T00:00:00+09:00")

    def test_claims_wrap_plain_strings(self) -> None:
        report = report_from_meta(self.meta(), "26102322")
        self.assertEqual(
            report["highlights"],
            [{"text": "第一段看点", "sources": []}, {"text": "第二段看点", "sources": []}],
        )
        self.assertEqual(report["interactions"][0]["text"], "两人发了同一段说明")
        self.assertEqual(report["works"], "一段作品动态")

    def test_people_keep_via_and_order(self) -> None:
        report = report_from_meta(self.meta(), "26102322")
        self.assertEqual([p["handle"] for p in report["people"]], ["re_re_tsubame", "mirai_chiroru"])
        self.assertEqual(report["people"][0]["via"], ["tsubame_sub"])
        self.assertEqual(report["people"][1]["via"], [])

    def test_accounts_survive(self) -> None:
        """`accounts` 是正文里 @提及 的链接白名单，丢了就少一半链接。"""
        report = report_from_meta(self.meta(), "26102322")
        self.assertEqual(report["accounts"], ["re_re_tsubame", "mirai_chiroru"])
        self.assertEqual(report["counts"]["accounts"], 2)

    def test_source_field_is_dropped(self) -> None:
        report = report_from_meta(self.meta(), "26102322")
        self.assertNotIn("source", report)

    def test_deterministic(self) -> None:
        """`--check` 靠这一条：连 generated_at 都不能是 now()。"""
        first = report_from_meta(self.meta(), "26102322")
        second = report_from_meta(self.meta(), "26102322")
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=False),
            json.dumps(second, ensure_ascii=False, sort_keys=False),
        )

    def test_bad_issue_id(self) -> None:
        for bad in ("2610232", "2610232x", "26103231"):
            with self.assertRaises(MigrateError):
                report_from_meta(self.meta(), bad)


@unittest.skipUnless(HAS_YAML, "需要 PyYAML")
class MigrateFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "content"
        self.dest = self.root / "data"
        self.src.mkdir()
        (self.src / "26102322.md").write_text(MD, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_check_is_read_only(self) -> None:
        results = migrate(self.src, self.dest, write=False)
        self.assertEqual([r.action for r in results], ["created"])
        self.assertFalse((self.dest / "26102322" / "report.json").exists())

    def test_write_then_check_is_identical(self) -> None:
        migrate(self.src, self.dest, write=True)
        self.assertTrue((self.dest / "26102322" / "report.json").exists())
        again = migrate(self.src, self.dest, write=False)
        self.assertEqual([r.action for r in again], ["identical"])

    def test_write_reports_drift(self) -> None:
        migrate(self.src, self.dest, write=True)
        (self.src / "26102322.md").write_text(MD.replace("第一段看点", "改过的看点"), encoding="utf-8")
        self.assertEqual([r.action for r in migrate(self.src, self.dest, write=False)], ["updated"])
        self.assertEqual([r.action for r in migrate(self.src, self.dest, write=True)], ["updated"])
        on_disk = json.loads((self.dest / "26102322" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["highlights"][0]["text"], "改过的看点")

    def test_unknown_id_is_an_error(self) -> None:
        with self.assertRaises(MigrateError):
            migrate(self.src, self.dest, ids=["26109999"], write=False)


if __name__ == "__main__":
    unittest.main()
