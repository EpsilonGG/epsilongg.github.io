"""M4 发布门：`out/<期号>/report.json` → `data/daily/<期号>/report.json`。

这一道门的价值全在「什么时候拒绝」上，所以测试也围着拒绝写：
草稿不能上线、已发布的不许静默覆盖、期号对不上不许写。
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

from daily.apply import new_report  # noqa: E402
from daily.publish import PublishError, publish  # noqa: E402
from daily.schema import DESCRIPTION_MAX  # noqa: E402

GENERATE = {
    "issue": {"published_at": "2026-10-23T22:00:00+09:00"},
    "counts": {"items": 27, "accounts": 6},
    "categories": [{"id": "people", "label": "聊人", "handles": ["asuparama40"]}],
}


def make_report(status: str = "confirmed", issue_id: str = "261023") -> dict:
    report = new_report(issue_id, GENERATE)
    report["issue"]["status"] = status
    report["issue"]["confirmed_at"] = "2026-10-23T23:10:00+00:00" if status == "confirmed" else None
    report["description"] = "柚木つばめ汇总生誕祭活动详情"
    report["people"][0]["summary"] = "在做 Ci-en 的宣传"
    return report


class PublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.out = self.root / "out"
        self.dest = self.root / "data" / "daily"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, report: dict, issue_id: str = "261023") -> Path:
        path = self.out / issue_id / "report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def test_publishes_confirmed_report(self) -> None:
        self.write(make_report())
        result = publish("261023", out_dir=self.out, dest_root=self.dest)
        self.assertFalse(result.replaced)
        self.assertEqual(
            result.path, self.dest / "261023" / "report.json"
        )
        on_disk = json.loads(result.path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["issue"]["status"], "confirmed")

    def test_refuses_draft(self) -> None:
        self.write(make_report(status="draft"))
        with self.assertRaises(PublishError) as ctx:
            publish("261023", out_dir=self.out, dest_root=self.dest)
        self.assertIn("拒绝发布", str(ctx.exception))
        self.assertFalse((self.dest / "261023").exists())

    def test_refuses_overwrite_without_force(self) -> None:
        self.write(make_report())
        publish("261023", out_dir=self.out, dest_root=self.dest)
        with self.assertRaises(PublishError) as ctx:
            publish("261023", out_dir=self.out, dest_root=self.dest)
        self.assertIn("--force", str(ctx.exception))

    def test_force_overwrites(self) -> None:
        self.write(make_report())
        publish("261023", out_dir=self.out, dest_root=self.dest)
        updated = make_report()
        updated["description"] = "改过的副标题"
        self.write(updated)
        result = publish("261023", out_dir=self.out, dest_root=self.dest, force=True)
        self.assertTrue(result.replaced)
        on_disk = json.loads(result.path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["description"], "改过的副标题")

    def test_refuses_when_issue_id_disagrees(self) -> None:
        # 文件在 out/26109999/ 下，但正本里的期号是 261023——手滑复制目录的典型后果
        self.write(make_report(issue_id="261023"), issue_id="26109999")
        with self.assertRaises(PublishError) as ctx:
            publish("26109999", out_dir=self.out, dest_root=self.dest)
        self.assertIn("对不上", str(ctx.exception))

    def test_missing_report(self) -> None:
        with self.assertRaises(PublishError) as ctx:
            publish("261023", out_dir=self.out, dest_root=self.dest)
        self.assertIn("还没有正本", str(ctx.exception))

    def test_refuses_invalid_report(self) -> None:
        """字段写错不该等到 `npm run build` 才炸。"""
        broken = make_report()
        broken["description"] = "长" * (DESCRIPTION_MAX + 1)  # 超过 schema 的 maxLength
        self.write(broken)
        with self.assertRaises(PublishError) as ctx:
            publish("261023", out_dir=self.out, dest_root=self.dest)
        self.assertIn("不合法", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
