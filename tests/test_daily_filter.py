"""账号级降噪（`daily/filter.py`）测试。

这些规则守的是「情报站不该把抽奖和周年回顾刷进日报」——
规则写错不会报错，只会让某一栏悄悄变空或者变吵，所以每条规则各有一个用例。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily import cli  # noqa: E402
from daily.filter import apply_rules, drop_reason, parse_rule  # noqa: E402
from daily.model import Account, Item  # noqa: E402
from daily.roster import Roster  # noqa: E402
from daily.window import IssueWindow  # noqa: E402

WINDOW = IssueWindow.for_day(date(2026, 10, 27))


def make(native_id: str, account: str, text: str = "", kind: str = "post", at: str = "") -> Item:
    return Item(
        key=f"x:{native_id}",
        source="x",
        native_id=native_id,
        account=account,
        published_at=at or f"2026-10-27T0{native_id[-1]}:00:00+00:00",
        text=text or f"正文 {native_id}",
        kind=kind,
    )


class DropKindTest(unittest.TestCase):
    def test_repost_is_dropped_and_post_is_kept(self) -> None:
        rule = {"Moepedia_net": {"drop_kinds": ["repost"]}}
        items = [
            make("1", "Moepedia_net", kind="post"),
            make("2", "Moepedia_net", kind="repost"),
        ]
        kept, dropped = apply_rules(items, rule)
        self.assertEqual([i.native_id for i in kept], ["1"])
        self.assertEqual([d["key"] for d in dropped], ["x:2"])
        self.assertEqual(dropped[0]["reason"], "repost")

    def test_other_accounts_are_untouched(self) -> None:
        rule = {"Moepedia_net": {"drop_kinds": ["repost"]}}
        items = [make("1", "someone_else", kind="repost")]
        kept, dropped = apply_rules(items, rule)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])


class DropPatternTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = parse_rule(
            "Moepedia_net",
            {"drop_if": ["プレゼント", "^moepedia\\.net/"]},
        )

    def test_pattern_hit_drops(self) -> None:
        item = make("1", "Moepedia_net", "直筆サイン色紙を1名にプレゼント！")
        self.assertIn("プレゼント", drop_reason(item, self.rule))

    def test_anchor_matches_link_card(self) -> None:
        item = make("1", "Moepedia_net", "moepedia.net/game/793/\n\nLink\n\n各月発売ゲームタイトル一覧")
        self.assertTrue(drop_reason(item, self.rule))

    def test_url_is_stripped_before_matching(self) -> None:
        """链接里的词不算证据：`https://example.com/sale` 不该让这条被丢。"""
        item = make("1", "Moepedia_net", "新作を発表しました https://example.com/sale")
        self.assertEqual(drop_reason(item, self.rule), "")

    def test_case_insensitive(self) -> None:
        rule = parse_rule("x", {"drop_if": ["PR"]})
        self.assertTrue(drop_reason(make("1", "x", "これは pr です"), rule))

    def test_invalid_regex_fails_loudly(self) -> None:
        with self.assertRaises(ValueError):
            parse_rule("x", {"drop_if": ["(未闭合"]})


class KeepPatternTest(unittest.TestCase):
    """白名单：媒体号只收某一类内容（`@getchucom` 只要发售日历）。"""

    def setUp(self) -> None:
        self.rule = parse_rule(
            "getchucom",
            {"keep_if": ["予約", "発売", "体験版", "周年"]},
        )

    def test_hit_is_kept(self) -> None:
        for text in (
            "【予約開始】『○○』9月28日発売決定！",
            "【本日発売】『△△』発売中",
            "『□□』体験版を公開しました",
            "『××』20周年記念特設サイト公開",
        ):
            with self.subTest(text=text):
                self.assertEqual(drop_reason(make("1", "getchucom", text), self.rule), "")

    def test_miss_is_dropped(self) -> None:
        item = make("1", "getchucom", "秋葉原店舗の営業時間変更のお知らせ")
        self.assertIn("keep_if", drop_reason(item, self.rule))

    def test_keep_if_alone_is_not_an_empty_rule(self) -> None:
        """只有白名单也是规则——否则 `apply_rules` 会把它当没配置整条跳过。"""
        self.assertFalse(self.rule.empty)
        kept, dropped = apply_rules(
            [make("1", "getchucom", "本日発売"), make("2", "getchucom", "雑談")],
            {"getchucom": {"keep_if": ["発売"]}},
        )
        self.assertEqual([i.native_id for i in kept], ["1"])
        self.assertEqual(len(dropped), 1)

    def test_drop_if_wins_over_keep_if(self) -> None:
        """「新作发售，转发抽奖」两个都命中 → 丢。抽奖部分是唯一会过期的东西。"""
        rule = parse_rule(
            "getchucom",
            {"drop_if": ["プレゼント"], "keep_if": ["発売"]},
        )
        item = make("1", "getchucom", "本日発売！プレゼントキャンペーンも実施")
        self.assertIn("プレゼント", drop_reason(item, rule))

    def test_url_does_not_satisfy_keep_if(self) -> None:
        """链接里带 `release` 不算命中白名单，否则白名单会被 URL 骗过去。"""
        rule = parse_rule("x", {"keep_if": ["発売"]})
        item = make("1", "x", "新しいお知らせです https://example.com/housoku")
        self.assertTrue(drop_reason(item, rule))

    def test_repost_kind_beats_keep_if(self) -> None:
        rule = parse_rule("x", {"drop_kinds": ["repost"], "keep_if": ["発売"]})
        item = make("1", "x", "本日発売", kind="repost")
        self.assertEqual(drop_reason(item, rule), "repost")

    def test_invalid_keep_regex_fails_loudly(self) -> None:
        with self.assertRaises(ValueError):
            parse_rule("x", {"keep_if": ["(未闭合"]})


class PreferAndCapTest(unittest.TestCase):
    def test_prefer_wins_over_newer(self) -> None:
        """封顶时优先留公告，而不是留最新的那条抽奖。"""
        rule = {
            "Moepedia_net": {
                "prefer_if": ["発売"],
                "max_items": 2,
            }
        }
        items = [
            make("1", "Moepedia_net", "11月27日発売！", at="2026-10-27T01:00:00+00:00"),
            make("2", "Moepedia_net", "11月28日発売！", at="2026-10-27T02:00:00+00:00"),
            make("3", "Moepedia_net", "イベント開催中", at="2026-10-27T09:00:00+00:00"),
            make("4", "Moepedia_net", "グッズあります", at="2026-10-27T10:00:00+00:00"),
        ]
        kept, dropped = apply_rules(items, rule)
        self.assertEqual([i.native_id for i in kept], ["1", "2"])
        self.assertEqual({d["reason"] for d in dropped}, {"超过 2 条上限"})

    def test_prefer_is_not_a_requirement(self) -> None:
        """没命中保留词的真公告不该消失——只写作品名和链接的那种。"""
        rule = {"Moepedia_net": {"prefer_if": ["発売"], "max_items": 5}}
        items = [make("1", "Moepedia_net", "『さくらぶトライアングル』ADV")]
        kept, dropped = apply_rules(items, rule)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])

    def test_cap_keeps_newest_within_same_rank(self) -> None:
        rule = {"Moepedia_net": {"max_items": 1}}
        items = [
            make("1", "Moepedia_net", "旧", at="2026-10-27T01:00:00+00:00"),
            make("2", "Moepedia_net", "新", at="2026-10-27T05:00:00+00:00"),
        ]
        kept, _ = apply_rules(items, rule)
        self.assertEqual([i.native_id for i in kept], ["2"])

    def test_no_rule_is_a_no_op(self) -> None:
        items = [make("1", "alice"), make("2", "bob")]
        kept, dropped = apply_rules(items, None)
        self.assertEqual(kept, items)
        self.assertEqual(dropped, [])


class PipelineIntegrationTest(unittest.TestCase):
    def test_dropped_account_leaves_no_empty_person(self) -> None:
        """条目全被筛掉的号不该出现在 people 表里。"""
        roster = Roster(
            categories=[{"id": "manufacturer", "label": "制造商"}],
            accounts=[
                Account("alice", category="manufacturer"),
                Account("Moepedia_net", category="manufacturer"),
            ],
            filters={"moepedia_net": {"drop_if": ["プレゼント"]}},
        )
        items = [
            make("1", "alice", "新作を発表"),
            make("2", "Moepedia_net", "プレゼント企画"),
        ]
        buf = io.StringIO()
        with redirect_stderr(buf):
            _, merged, accounts, dropped = cli._pipeline(items, WINDOW, roster, {})
        self.assertEqual([i.account for i in merged], ["alice"])
        self.assertEqual(accounts, ["alice"])
        self.assertEqual(len(dropped), 1)
        self.assertIn("Moepedia_net 1 条", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
