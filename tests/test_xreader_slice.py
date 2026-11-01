"""`xreader_slice.py`：把 X-Reader 的全量库切成按日片。

这一层决定「仓库里那份数据到底还对不对得上昨天」。三个点必须钉死：

1. **按 JST 分日**，不是 UTC——`2026-10-31T15:30Z` 是 JST 的 11-01 00:30，
   分错一天就会让 `daily_prepare` 在 10-31 那一期里少一条、11-01 那期多一条。
2. **去重**，nitter 的 RSS 窗口会重叠，同一轮抓取常把同一条落两次。
3. **只删窗口外的旧片**，窗口内一天都不能少——少一天就是「重出旧期时数据没了」。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_prepare  # noqa: E402
import xreader_slice  # noqa: E402


def _item(item_id: str, published_at: str, content: str = "テスト") -> str:
    """一行 NormalizedItem，字段顺序和 X-Reader 写出来的一致。"""
    return json.dumps(
        {
            "identity_key": f"x:{item_id}",
            "source_id": "x",
            "item_id": item_id,
            "title": None,
            "content": content,
            "publisher": "someone",
            "canonical_url": f"https://x.com/someone/status/{item_id}",
            "published_at": published_at,
        },
        ensure_ascii=False,
    )


class CollectTest(unittest.TestCase):
    def _store(self, root: Path, lines: list[str]) -> Path:
        items = root / "data" / "items"
        items.mkdir(parents=True)
        (items / "x.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return items

    def test_days_are_jst_not_utc(self) -> None:
        """`15:30Z` 已经是 JST 的次日 00:30——分日必须按 JST。"""
        with tempfile.TemporaryDirectory() as tmp:
            items = self._store(
                Path(tmp),
                [
                    _item("1", "2026-10-31T14:59:00+00:00"),  # JST 10-31 23:59
                    _item("2", "2026-10-31T15:30:00+00:00"),  # JST 11-01 00:30
                ],
            )
            days = xreader_slice.collect(items)
            self.assertEqual(sorted(days), [date(2026, 10, 31), date(2026, 11, 1)])
            self.assertEqual(len(days[date(2026, 10, 31)]), 1)
            self.assertEqual(len(days[date(2026, 11, 1)]), 1)

    def test_duplicate_identity_lands_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            items = self._store(
                Path(tmp),
                [
                    _item("42", "2026-10-31T01:00:00+00:00", "旧"),
                    _item("42", "2026-10-31T01:00:00+00:00", "新"),
                ],
            )
            days = xreader_slice.collect(items)
            bucket = days[date(2026, 10, 31)]
            self.assertEqual(len(bucket), 1)
            # 后写的覆盖先写的：同一 id 的两次抓取，后一次的内容才是当下正确的
            self.assertIn("新", next(iter(bucket.values()))[1])

    def test_broken_line_is_skipped_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            items = self._store(
                Path(tmp),
                [_item("7", "2026-10-31T01:00:00+00:00"), "{ 这不是 JSON"],
            )
            days = xreader_slice.collect(items)
            self.assertEqual(len(days[date(2026, 10, 31)]), 1)


class WriteDayTest(unittest.TestCase):
    def test_lines_are_sorted_and_end_with_lf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            bucket = {
                "x:2": ("2026-10-31T02:00:00+00:00", _item("2", "2026-10-31T02:00:00+00:00")),
                "x:1": ("2026-10-31T01:00:00+00:00", _item("1", "2026-10-31T01:00:00+00:00")),
            }
            count, size = xreader_slice.write_day(dest, date(2026, 10, 31), bucket, dry_run=False)
            payload = (dest / "2026-10-31.jsonl").read_bytes()
            self.assertEqual(count, 2)
            self.assertEqual(size, len(payload))
            self.assertTrue(payload.endswith(b"\n"))
            self.assertNotIn(b"\r", payload, "切片必须是 LF，否则每次 checkout 都是假改动")
            order = [json.loads(line)["item_id"] for line in payload.decode().splitlines()]
            self.assertEqual(order, ["1", "2"])

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            bucket = {"x:1": ("2026-10-31T01:00:00+00:00", _item("1", "2026-10-31T01:00:00+00:00"))}
            xreader_slice.write_day(dest, date(2026, 10, 31), bucket, dry_run=True)
            self.assertFalse((dest / "2026-10-31.jsonl").exists())


class RefreshTest(unittest.TestCase):
    def _store(self, root: Path, days: list[str]) -> Path:
        items = root / "xreader" / "data" / "items"
        items.mkdir(parents=True)
        lines = [_item(day.replace("-", ""), f"{day}T03:00:00+00:00") for day in days]
        (items / "x.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return root / "xreader"

    def test_window_is_the_last_n_days_ending_at_the_newest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = self._store(Path(tmp), ["2026-10-29", "2026-10-30", "2026-10-31"])
            dest = Path(tmp) / "slices"
            code = xreader_slice.refresh("voice", src, keep=2, dest=dest, quiet=True)
            self.assertEqual(code, 0)
            self.assertEqual(
                sorted(p.stem for p in (dest / "voice").glob("*.jsonl")),
                ["2026-10-30", "2026-10-31"],
            )

    def test_old_slices_outside_the_window_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = self._store(Path(tmp), ["2026-10-30", "2026-10-31"])
            dest = Path(tmp) / "slices"
            (dest / "voice").mkdir(parents=True)
            stale = dest / "voice" / "2026-10-01.jsonl"
            stale.write_text("", encoding="utf-8")
            xreader_slice.refresh("voice", src, keep=2, dest=dest, quiet=True)
            self.assertFalse(stale.exists(), "窗口外的旧片必须删掉，否则目录会无限长")

    def test_only_day_leaves_other_slices_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = self._store(Path(tmp), ["2026-10-30", "2026-10-31"])
            dest = Path(tmp) / "slices"
            xreader_slice.refresh("voice", src, keep=14, dest=dest, quiet=True)
            xreader_slice.refresh("voice", src, keep=14, dest=dest, only_day=date(2026, 10, 30), quiet=True)
            self.assertEqual(
                sorted(p.stem for p in (dest / "voice").glob("*.jsonl")),
                ["2026-10-30", "2026-10-31"],
            )

    def test_missing_store_is_code_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = xreader_slice.refresh("voice", Path(tmp), dest=Path(tmp) / "slices", quiet=True)
            self.assertEqual(code, 2)


class ItemsDirForTest(unittest.TestCase):
    """`daily_prepare` 挑数据源：全量库优先，不在就用仓库里的切片。"""

    def test_live_store_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "xreader" / "data" / "items"
            live.mkdir(parents=True)
            (live / "x.jsonl").write_text("", encoding="utf-8")
            self.assertEqual(daily_prepare.items_dir_for("voice", root / "xreader"), live)

    def test_falls_back_to_slices_when_checkout_is_gone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            slices = Path(tmp) / "xreader"
            (slices / "voice").mkdir(parents=True)
            (slices / "voice" / "2026-10-31.jsonl").write_text("", encoding="utf-8")
            with mock.patch.object(daily_prepare, "SLICES_ROOT", slices):
                self.assertEqual(
                    daily_prepare.items_dir_for("voice", Path(tmp) / "missing"),
                    slices / "voice",
                )

    def test_neither_source_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(daily_prepare, "SLICES_ROOT", Path(tmp) / "empty"):
                self.assertIsNone(daily_prepare.items_dir_for("galgame", Path(tmp) / "missing"))


if __name__ == "__main__":
    unittest.main()
