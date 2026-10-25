"""M2.1 时间窗测试：JST 自然日切分。

这个文件钉住的是「一天从几点开始」——写错了不会报错，只会让日报悄悄少几条、
多几条，而且看起来完全正常。所以边界、半开区间、精度不足三种情况各写一遍。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily.adapters.xreader import XReaderAdapter  # noqa: E402
from daily.issue import JST  # noqa: E402
from daily.model import Item  # noqa: E402
from daily.window import IssueWindow  # noqa: E402

SAMPLE_DIR = SCRIPTS_DIR / "sample_items"


def make_item(native_id: str, published_at: str, *, account: str = "someone", precision: str = "second") -> Item:
    return Item(
        key=f"x:{native_id}",
        source="x",
        native_id=native_id,
        account=account,
        published_at=published_at,
        precision=precision,
    )


class BoundaryTest(unittest.TestCase):
    def test_window_is_jst_natural_day(self) -> None:
        w = IssueWindow.for_day(date(2026, 10, 23))
        self.assertEqual(w.start, datetime(2026, 10, 23, 0, 0, tzinfo=JST))
        self.assertEqual(w.end, datetime(2026, 10, 24, 0, 0, tzinfo=JST))
        # 换算成 UTC 就是前一天 15:00 到当天 15:00
        self.assertEqual(w.start.astimezone(timezone.utc), datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(w.end.astimezone(timezone.utc), datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc))

    def test_half_open_interval(self) -> None:
        """跨零点的推只属于一天：00:00 算当天，次日 00:00 不算。"""
        w = IssueWindow.for_day(date(2026, 10, 23))
        self.assertTrue(w.contains(datetime(2026, 10, 23, 0, 0, tzinfo=JST)))
        self.assertFalse(w.contains(datetime(2026, 10, 24, 0, 0, tzinfo=JST)))
        self.assertTrue(w.contains(datetime(2026, 10, 23, 23, 59, 59, tzinfo=JST)))

    def test_containing_uses_jst_not_stamp_timezone(self) -> None:
        """UTC 10-22 15:10 = JST 10-23 00:10，落在 10-23 窗口。"""
        moment = datetime(2026, 10, 22, 15, 10, tzinfo=timezone.utc)
        self.assertEqual(IssueWindow.containing(moment).day, date(2026, 10, 23))

    def test_naive_timestamp_is_read_as_jst(self) -> None:
        w = IssueWindow.for_day(date(2026, 10, 23))
        self.assertTrue(w.contains(datetime(2026, 10, 23, 0, 30)))

    def test_rejects_datetime_as_day(self) -> None:
        with self.assertRaises(TypeError):
            IssueWindow(day=datetime(2026, 10, 23, 0, 0))  # type: ignore[arg-type]

    def test_label_names_the_zone(self) -> None:
        self.assertEqual(IssueWindow.for_day(date(2026, 10, 23)).label, "2026-10-23（JST）")


class SelectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.window = IssueWindow.for_day(date(2026, 10, 23))

    def test_early_morning_counts_as_the_same_day(self) -> None:
        """凌晨 07:07 JST 发的推属于 10-23，不是 10-22。"""
        item = make_item("1", "2026-10-22T22:07:25+00:00")
        self.assertEqual([i.native_id for i in self.window.select([item])], ["1"])

    def test_next_day_early_morning_does_not_leak_in(self) -> None:
        item = make_item("2", "2026-10-23T20:09:04+00:00")  # JST 10-24 05:09
        selection = self.window.select([item])
        self.assertEqual(len(selection), 0)
        self.assertEqual(selection.unsure, ())
        self.assertEqual(selection.undated, ())

    def test_keeps_input_order(self) -> None:
        items = [
            make_item("b", "2026-10-23T05:00:00+00:00"),
            make_item("a", "2026-10-23T01:00:00+00:00"),
        ]
        self.assertEqual([i.native_id for i in self.window.select(items)], ["b", "a"])

    def test_day_precision_is_flagged_not_dropped(self) -> None:
        """只知道哪一天的条目无法判定窗口，单独放 unsure，不混进 items。"""
        exact = make_item("exact", "2026-10-23T03:00:00+00:00")
        same_day = make_item("d0", "2026-10-23T00:00:00+00:00", precision="day")
        prev_day = make_item("d-1", "2026-10-22T00:00:00+00:00", precision="day")
        next_day = make_item("d+1", "2026-10-24T00:00:00+00:00", precision="day")
        selection = self.window.select([exact, same_day, prev_day, next_day])
        self.assertEqual([i.native_id for i in selection.items], ["exact"])
        self.assertEqual([i.native_id for i in selection.unsure], ["d0", "d-1"])
        self.assertEqual([i.native_id for i in selection.all_items], ["exact", "d0", "d-1"])

    def test_undated_items_are_separate(self) -> None:
        selection = self.window.select([make_item("x", "")])
        self.assertEqual(selection.undated[0].native_id, "x")
        self.assertEqual(selection.all_items, ())

    def test_buckets_partition_the_input(self) -> None:
        items = [
            make_item("a", "2026-10-23T03:00:00+00:00"),
            make_item("b", "2026-10-25T03:00:00+00:00"),
            make_item("c", "2026-10-23T00:00:00+00:00", precision="day"),
            make_item("d", "not-a-timestamp"),
        ]
        selection = self.window.select(items)
        self.assertEqual(
            sorted(i.native_id for i in selection.items + selection.unsure + selection.undated),
            ["a", "c", "d"],
        )
        self.assertEqual(len(selection.items) + len(selection.unsure) + len(selection.undated), 3)

    def test_iterates_the_definite_items_only(self) -> None:
        selection = self.window.select([make_item("a", "2026-10-23T03:00:00+00:00")])
        self.assertEqual([i.native_id for i in selection], ["a"])


class ItemDateTest(unittest.TestCase):
    def test_date_is_jst(self) -> None:
        """UTC 10-22 22:07 → JST 10-23 07:07，date() 必须给 10-23。"""
        item = make_item("1", "2026-10-22T22:07:25+00:00")
        self.assertEqual(item.date(), date(2026, 10, 23))

    def test_missing_timestamp_has_no_date(self) -> None:
        self.assertIsNone(make_item("1", "").date())


@unittest.skipUnless(SAMPLE_DIR.is_dir(), "缺少 scripts/sample_items")
class SampleAcceptanceTest(unittest.TestCase):
    """M2 出口闸门的第 4 条：10-23 窗口 26 → 28，账号集合不变。"""

    def setUp(self) -> None:
        self.items = list(XReaderAdapter(SAMPLE_DIR).iter_items())
        self.window = IssueWindow.for_day(date(2026, 10, 23))

    def test_window_grew_from_26_to_28(self) -> None:
        selection = self.window.select(self.items)
        self.assertEqual(len(selection), 28)
        self.assertEqual(selection.unsure, ())
        self.assertEqual(selection.undated, ())

    def test_account_set_unchanged(self) -> None:
        """旧口径（UTC 分天）与新口径（JST 分天）覆盖同一批人，只是条目数变了。"""
        utc_day = [it for it in self.items if it.published_dt().date() == date(2026, 10, 23)]
        jst_day = list(self.window.select(self.items))
        self.assertEqual(len(utc_day), 26)
        self.assertEqual({i.account for i in utc_day}, {i.account for i in jst_day})

    def test_swapped_items_are_the_expected_eight(self) -> None:
        utc_ids = {it.native_id for it in self.items if it.published_dt().date() == date(2026, 10, 23)}
        jst_ids = {it.native_id for it in self.window.select(self.items)}
        self.assertEqual(len(jst_ids - utc_ids), 5)
        self.assertEqual(len(utc_ids - jst_ids), 3)


if __name__ == "__main__":
    unittest.main()
