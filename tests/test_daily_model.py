"""M1 协议层的测试：模型、schema、状态、版本、可复现。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily import SCHEMA_VERSION  # noqa: E402
from daily.build import build_briefing, build_markdown  # noqa: E402
from daily.migrate import VersionError, check, migrate  # noqa: E402
from daily.model import Claim, Item, Issue, Report, content_hash, item_key  # noqa: E402
from daily.schema import SchemaError, load_schema, validate  # noqa: E402
from daily.state import State  # noqa: E402

RAW = {
    "source_id": "x",
    "item_id": "2113264805360677299",
    "content": "ジェラピケ味を占めすぎやろ！\nこんなん買うしか…💸",
    "publisher": "mimoriaino",
    "canonical_url": "https://x.com/mimoriaino/status/2113264805360677299",
    "published_at": "2026-10-22T13:42:46+00:00",
    "published_precision": "second",
    "fetched_at": "2026-10-24T17:07:15+00:00",
    "media": [],
    "metadata": {"account": "mimoriaino", "is_retweet": False, "is_reply": False, "is_quote": False, "stats": {}},
}


def make_report(description: str = "两位发了新作预告") -> Report:
    issue = Issue(
        id="26102322",
        published_at="2026-10-23T22:00:00+09:00",
        window_start="2026-10-23T00:00:00+09:00",
        window_end="2026-10-24T00:00:00+09:00",
    )
    return Report(
        issue=issue,
        description=description,
        highlights=[Claim("一句话", ["x:2113"])],
        people=[{"handle": "asuparama40", "category": "seiyuu", "summary": "…", "sources": []}],
        provenance={"generator": "test"},
    )


class ModelTest(unittest.TestCase):
    def test_item_key_is_source_colon_id(self) -> None:
        self.assertEqual(item_key("x", "123"), "x:123")

    def test_content_hash_ignores_whitespace(self) -> None:
        self.assertEqual(content_hash("a  b\nc"), content_hash(" a b c "))

    def test_item_key_order_is_fixed(self) -> None:
        item = Item.from_xreader(RAW, raw_ref="x.jsonl#1")
        self.assertEqual(
            list(item.to_dict().keys()),
            [
                "key", "source", "native_id", "account", "amplifiers", "published_at",
                "precision", "text", "url", "kind", "reply_to", "quote_of", "repost_of",
                "engagement", "media", "content_hash", "first_seen", "raw_ref",
            ],
        )

    def test_item_validates_against_schema(self) -> None:
        item = Item.from_xreader(RAW)
        validate(item.to_dict(), load_schema("item"))

    def test_engagement_does_not_leak_into_text(self) -> None:
        item = Item.from_xreader(RAW)
        self.assertEqual(item.engagement.score(), 0)
        self.assertNotIn("❤", item.text)

    def test_report_validates_against_schema(self) -> None:
        validate(make_report().to_dict(), load_schema("report"))

    def test_report_description_too_long(self) -> None:
        with self.assertRaises(SchemaError) as ctx:
            validate(make_report("字" * 51).to_dict(), load_schema("report"))
        self.assertEqual(ctx.exception.path, "$.description")


class SchemaTest(unittest.TestCase):
    def test_required_field_path(self) -> None:
        schema = {"type": "object", "required": ["sources"]}
        with self.assertRaises(SchemaError) as ctx:
            validate({}, schema, "$.highlights[0]")
        self.assertEqual(ctx.exception.path, "$.highlights[0].sources")

    def test_enum(self) -> None:
        schema = {"type": "string", "enum": ["draft", "confirmed"]}
        with self.assertRaises(SchemaError):
            validate("published", schema, "$.issue.status")

    def test_pattern(self) -> None:
        schema = {"type": "string", "pattern": "^[0-9]{8}$"}
        with self.assertRaises(SchemaError):
            validate("2610232", schema, "$.issue.id")

    def test_min_items(self) -> None:
        schema = load_schema("generation")
        payload = {
            "category": "seiyuu",
            "summary": "…",
            "highlights": [{"text": "一", "sources": ["x:1"]}] * 6,
            "interactions": [],
            "people": [],
        }
        with self.assertRaises(SchemaError) as ctx:
            validate(payload, schema)
        self.assertIn("最多 4 项", ctx.exception.message)

    def test_good_generation_passes(self) -> None:
        payload = {
            "category": "seiyuu",
            "summary": "…",
            "highlights": [{"text": "一", "sources": ["x:1"]}, {"text": "二", "sources": ["x:2"]}],
            "interactions": [],
            "people": [{"handle": "a", "summary": "…"}],
        }
        validate(payload, load_schema("generation"))


class StateTest(unittest.TestCase):
    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = State()
            state.record_issue("26102322", "2026-10-23T22:00:00+09:00", ["x:1", "x:2"])
            state.mark_seen("x:1", "2026-10-23T00:00:00+00:00", "sha256:abc")
            state.save(path)
            again = State.load(path)
            self.assertEqual(again.to_dict(), state.to_dict())
            self.assertEqual(again.to_dict()["schema_version"], SCHEMA_VERSION)

    def test_prune_drops_old_entries(self) -> None:
        state = State()
        old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        new = datetime.now(timezone.utc).isoformat()
        state.seen["x:old"] = {"first_seen": old, "last_seen": old}
        state.seen["x:new"] = {"first_seen": new, "last_seen": new}
        self.assertEqual(state.prune(days=90), 1)
        self.assertEqual(list(state.seen), ["x:new"])

    def test_rebuild_from_issues(self) -> None:
        state = State()
        state.record_issue("26102222", "2026-10-22T22:00:00+09:00", ["x:1"])
        state.record_issue("26102322", "2026-10-23T22:00:00+09:00", ["x:1", "x:2"])
        self.assertEqual(state.rebuild(), 2)
        self.assertEqual(state.seen["x:1"]["first_seen"], "2026-10-22T22:00:00+09:00")
        self.assertEqual(state.seen["x:1"]["last_seen"], "2026-10-23T22:00:00+09:00")

    def test_load_rejects_newer_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"schema_version": 99, "issues": [], "seen": {}}', encoding="utf-8")
            with self.assertRaises(VersionError):
                State.load(path)

    def test_issue_is_replaced_not_duplicated(self) -> None:
        state = State()
        state.record_issue("26102322", "2026-10-23T22:00:00+09:00", ["x:1"])
        state.record_issue("26102322", "2026-10-23T22:00:00+09:00", ["x:1", "x:2"])
        self.assertEqual(len(state.issues), 1)


class MigrateTest(unittest.TestCase):
    def test_accepts_current(self) -> None:
        self.assertEqual(check({"schema_version": SCHEMA_VERSION}), SCHEMA_VERSION)
        self.assertEqual(migrate({"schema_version": SCHEMA_VERSION})["schema_version"], SCHEMA_VERSION)

    def test_rejects_newer(self) -> None:
        with self.assertRaises(VersionError):
            check({"schema_version": SCHEMA_VERSION + 1})

    def test_rejects_missing(self) -> None:
        with self.assertRaises(VersionError):
            check({})


class ReproducibleTest(unittest.TestCase):
    def test_two_runs_are_identical(self) -> None:
        items = [Item.from_xreader(RAW), Item.from_xreader(dict(RAW, item_id="2", publisher="b"))]
        a = (build_briefing(items, date(2026, 10, 22)), build_markdown(items, "26102222"))
        b = (build_briefing(items, date(2026, 10, 22)), build_markdown(items, "26102222"))
        self.assertEqual(a, b)

    def test_engagement_sorted_without_mutating_input(self) -> None:
        low = Item.from_xreader(RAW)
        high = Item.from_xreader(dict(RAW, item_id="2", metadata=dict(RAW["metadata"], stats={"likes": 10})))
        items = [low, high]
        build_briefing(items, date(2026, 10, 22))
        self.assertEqual([i.key for i in items], [low.key, high.key])

    def test_briefing_keeps_every_tweet_by_default(self) -> None:
        """以前写死「每账号 5 条」，一天发 10 条只喂进去 5 条，写出来的日报是残的。"""
        items = [Item.from_xreader(dict(RAW, item_id=str(i))) for i in range(8)]
        text = build_briefing(items, date(2026, 10, 22))
        self.assertEqual(text.count("- [❤"), 8)

    def test_per_account_keeps_the_most_engaged(self) -> None:
        quiet = [Item.from_xreader(dict(RAW, item_id=str(i))) for i in range(4)]
        loud = Item.from_xreader(
            dict(RAW, item_id="hot", metadata=dict(RAW["metadata"], stats={"likes": 99}))
        )
        text = build_briefing(quiet + [loud], date(2026, 10, 22), per_account=2)
        self.assertEqual(text.count("- [❤"), 2)
        self.assertIn("❤99", text)


if __name__ == "__main__":
    unittest.main()
