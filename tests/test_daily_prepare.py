"""`daily_prepare.py` 的两版参数：期号后缀、数据目录、窗口计数。

这一层没有模型，但它决定「今天到底有没有数据」，而且**两版必须各走一条库**：
声优版读 `data/items`、Galgame 版读 `data-galgame/items`。写错一个目录名，
结果是 Galgame 版拿声优的条目出一期看起来完全正常的日报——所以这里钉死。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_prepare  # noqa: E402
from daily.issue import issue_id_for, kind_of  # noqa: E402


class KindMappingTest(unittest.TestCase):
    def test_both_editions_are_known(self) -> None:
        self.assertEqual(set(daily_prepare.KINDS), {"voice", "galgame"})

    def test_suffix_matches_the_issue_module(self) -> None:
        """后缀由本脚本拼、由 `daily.issue` 解，两处必须一致。"""
        day = date(2026, 10, 29)
        for kind, (suffix, _data, _label) in daily_prepare.KINDS.items():
            issue_id = day.strftime("%y%m%d") + suffix
            self.assertEqual(issue_id, issue_id_for(day, 1, kind))
            self.assertEqual(kind_of(issue_id), kind)

    def test_each_edition_reads_its_own_store(self) -> None:
        dirs = {kind: data for kind, (_s, data, _l) in daily_prepare.KINDS.items()}
        self.assertEqual(dirs["voice"], "data")
        self.assertEqual(dirs["galgame"], "data-galgame")
        self.assertEqual(len(set(dirs.values())), 2, "两版不能共用一个库")


class CountItemsTest(unittest.TestCase):
    def _write(self, path: Path, moments: list[str], broken: bool = False) -> None:
        lines = [
            json.dumps({"item_id": f"i{i}", "published_at": at}, ensure_ascii=False)
            for i, at in enumerate(moments)
        ]
        if broken:
            lines.append("{ 这不是 JSON")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_window_is_the_jst_natural_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            items = Path(tmp)
            self._write(
                items / "x.jsonl",
                [
                    "2026-10-29T00:00:00+09:00",  # 窗口内（左闭）
                    "2026-10-29T23:59:59+09:00",  # 窗口内（右开之前）
                    "2026-10-28T23:59:59+09:00",  # 前一天
                    "2026-10-30T00:00:00+09:00",  # 次日
                ],
                broken=True,
            )
            inside, total = daily_prepare.count_items(items, date(2026, 10, 29))
            self.assertEqual(inside, 2)
            # 坏行也算「读过一条」：总数对不上时才查得出 JSONL 被写坏了
            self.assertEqual(total, 5)

    def test_empty_dir_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(daily_prepare.count_items(Path(tmp), date(2026, 10, 29)), (0, 0))


class CoverageTest(unittest.TestCase):
    """「条数够」不等于「这一天抓全了」。

    261031 有 291 条，却只覆盖到 18:30 —— 后面五个半小时一条都没有，
    因为最后一轮抓取还没落地。这组测试钉住「最后一条几点」这个判断。
    """

    def _write(self, path: Path, moments: list[str]) -> None:
        lines = [json.dumps({"item_id": f"i{i}", "published_at": at}) for i, at in enumerate(moments)]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_scan_day_returns_the_last_item_inside_the_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            items = Path(tmp)
            self._write(
                items / "x.jsonl",
                ["2026-10-29T09:00:00+09:00", "2026-10-29T18:30:09+09:00", "2026-10-29T12:00:00+09:00"],
            )
            inside, total, latest = daily_prepare.scan_day(items, date(2026, 10, 29))
            self.assertEqual((inside, total), (3, 3))
            self.assertIsNotNone(latest)
            self.assertEqual(latest.astimezone(daily_prepare.JST).strftime("%H:%M"), "18:30")

    def test_latest_ignores_the_next_day(self) -> None:
        """次日凌晨的条目不属于这一天，不能把「覆盖到几点」抬上去。"""
        with tempfile.TemporaryDirectory() as tmp:
            items = Path(tmp)
            self._write(
                items / "x.jsonl",
                ["2026-10-29T18:30:00+09:00", "2026-10-30T04:11:00+09:00"],
            )
            _, _, latest = daily_prepare.scan_day(items, date(2026, 10, 29))
            self.assertEqual(latest.astimezone(daily_prepare.JST).strftime("%H:%M"), "18:30")

    def test_partial_day_refuses_to_build(self) -> None:
        """最后一条停在 18:30 就返回 5，不去写一期残稿。"""
        with tempfile.TemporaryDirectory() as tmp:
            items = Path(tmp) / "data" / "items"
            items.mkdir(parents=True)
            self._write(items / "x.jsonl", ["2026-10-29T09:00:00+09:00", "2026-10-29T18:30:09+09:00"])
            code = daily_prepare.main(["--no-pull", "--xreader", tmp, "--date", "2026-10-29"])
            self.assertEqual(code, 5)


if __name__ == "__main__":
    unittest.main()
