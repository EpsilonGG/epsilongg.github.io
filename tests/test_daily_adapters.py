"""M1.3 适配器契约测试：每个适配器都过同一套。

    python -m unittest discover -s tests -v
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

from daily.adapters.base import SourceAdapter  # noqa: E402
from daily.adapters.fixture import FixtureAdapter  # noqa: E402
from daily.adapters.xreader import XReaderAdapter  # noqa: E402
from daily.schema import load_schema, validate  # noqa: E402

RECORD = {
    "source_id": "x",
    "item_id": "2113264805360677299",
    "content": "今日は配信です",
    # 转发：publisher 是被转的原作者，metadata.account 才是时间线主人（转发者）。
    # 真实数据里两者不同，按 publisher 归属会把品牌号当成人写进日报。
    "publisher": "solfa_info",
    "canonical_url": "https://x.com/solfa_info/status/2113264805360677299",
    "published_at": "2026-10-22T13:42:46+00:00",
    "published_precision": "second",
    "fetched_at": "2026-10-24T17:07:15+00:00",
    "media": [],
    "metadata": {
        "account": "mimoriaino",
        "author_name": "solfa_info",
        "is_retweet": True,
        "retweeted_by": "mimoriaino",
        "is_reply": False,
        "is_quote": False,
        "stats": {"likes": 3, "retweets": 2},
    },
}


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")


class XReaderTest(unittest.TestCase):
    def test_reads_and_skips_non_meaningful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_jsonl(Path(tmp) / "x.jsonl", [RECORD, dict(RECORD, item_id="2", is_meaningful=False)])
            items = list(XReaderAdapter(tmp).iter_items())
        self.assertEqual([i.native_id for i in items], ["2113264805360677299"])

    def test_maps_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_jsonl(Path(tmp) / "x.jsonl", [RECORD])
            item = list(XReaderAdapter(tmp).iter_items())[0]
        self.assertEqual(item.key, "x:2113264805360677299")
        self.assertEqual(item.account, "mimoriaino")
        self.assertEqual(item.kind, "repost")
        self.assertEqual(item.engagement.score(), 5)
        self.assertEqual(item.amplifiers, ["mimoriaino"])
        self.assertEqual(item.repost_of, "solfa_info")
        self.assertEqual(item.date().isoformat(), "2026-10-22")

    def test_retweet_belongs_to_the_retweeter_not_the_author(self) -> None:
        """转发的归属是转发者。按 publisher 归属会让品牌号变成 people 里的一行。"""
        with tempfile.TemporaryDirectory() as tmp:
            write_jsonl(Path(tmp) / "x.jsonl", [RECORD])
            item = list(XReaderAdapter(tmp).iter_items())[0]
        self.assertNotEqual(item.account, "solfa_info")
        self.assertIn(item.account, item.amplifiers)

    def test_original_post_belongs_to_its_author(self) -> None:
        original = dict(RECORD)
        original["metadata"] = {
            "account": "solfa_info",
            "author_name": "solfa_info",
            "is_retweet": False,
            "retweeted_by": None,
            "is_reply": False,
            "is_quote": False,
            "stats": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            write_jsonl(Path(tmp) / "x.jsonl", [original])
            item = list(XReaderAdapter(tmp).iter_items())[0]
        self.assertEqual(item.account, "solfa_info")
        self.assertEqual(item.kind, "post")
        self.assertEqual(item.amplifiers, [])
        self.assertIsNone(item.repost_of)

    def test_fingerprint_is_stable_and_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            write_jsonl(path, [RECORD])
            first = XReaderAdapter(tmp).fingerprint()
            second = XReaderAdapter(tmp).fingerprint()
            self.assertEqual(first, second)
            write_jsonl(path, [RECORD, dict(RECORD, item_id="2")])
            self.assertNotEqual(first, XReaderAdapter(tmp).fingerprint())

    def test_missing_dir_is_empty(self) -> None:
        adapter = XReaderAdapter(Path(tempfile.gettempdir()) / "no-such-dir-daily")
        self.assertEqual(list(adapter.iter_items()), [])
        self.assertTrue(adapter.fingerprint().startswith("sha256:"))

    def test_unicode_line_separator_does_not_split_a_record(self) -> None:
        """U+2028 不是换行。

        `json.dumps(ensure_ascii=False)` 不转义 U+2028，`str.splitlines()` 却认它——
        用 splitlines 读会把这条合法记录劈成两半，两半都解析失败、都被静默跳过。
        真实数据里 x.jsonl 有 2 条记录共 12 个 U+2028（2026-10-26 修），
        旧读法把文件读成 2423 行、丢掉 2 条。
        """
        record = dict(RECORD, content="前\u2028后")
        with tempfile.TemporaryDirectory() as tmp:
            write_jsonl(Path(tmp) / "x.jsonl", [record])
            adapter = XReaderAdapter(tmp)
            items = list(adapter.iter_items())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].key, "x:2113264805360677299")
        self.assertEqual(adapter.malformed, [])

    def test_malformed_line_is_counted_not_silently_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            path.write_text(
                json.dumps(RECORD, ensure_ascii=False) + "\n{ 断了\n", encoding="utf-8"
            )
            adapter = XReaderAdapter(tmp)
            items = list(adapter.iter_items())
        self.assertEqual(len(items), 1)
        self.assertEqual(adapter.malformed, ["x.jsonl#2"])


class FixtureTest(unittest.TestCase):
    def test_reads_json_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.json"
            path.write_text(json.dumps([RECORD, dict(RECORD, item_id="2")], ensure_ascii=False), encoding="utf-8")
            items = list(FixtureAdapter(path, source="fixture").iter_items())
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].key, "fixture:2113264805360677299")
        self.assertEqual(items[1].source, "fixture")


class ContractTest(unittest.TestCase):
    def test_both_adapters_satisfy_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_jsonl(Path(tmp) / "x.jsonl", [RECORD])
            fixture = Path(tmp) / "fixture.json"
            fixture.write_text(json.dumps([RECORD], ensure_ascii=False), encoding="utf-8")
            adapters: list[SourceAdapter] = [XReaderAdapter(tmp), FixtureAdapter(fixture)]
            schema = load_schema("item")
            for adapter in adapters:
                self.assertTrue(adapter.name)
                self.assertTrue(adapter.fingerprint().startswith("sha256:"))
                items = list(adapter.iter_items())
                self.assertEqual(len(items), 1)
                validate(items[0].to_dict(), schema)

    def test_order_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_jsonl(Path(tmp) / "b.jsonl", [dict(RECORD, item_id="3")])
            write_jsonl(Path(tmp) / "a.jsonl", [dict(RECORD, item_id="1")])
            first = [i.native_id for i in XReaderAdapter(tmp).iter_items()]
            second = [i.native_id for i in XReaderAdapter(tmp).iter_items()]
        self.assertEqual(first, second)
        self.assertEqual(first, ["1", "3"])  # 按文件名排序，不按文件系统返回顺序


if __name__ == "__main__":
    unittest.main()
