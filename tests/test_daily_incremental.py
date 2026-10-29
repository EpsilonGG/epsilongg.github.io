"""M2 增量链路测试：去重、五态判定、排序、名单、导出。

这些测试守的是「同一条内容算几件事」「哪些条目不进今天的日报」——
两类错误都不会报错，只会让日报悄悄多一条、少一条，或者把旧事写成新闻。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily import cli  # noqa: E402
from daily.adapters.xreader import XReaderAdapter  # noqa: E402
from daily.dedupe import identity, merge, normalize_url  # noqa: E402
from daily.export import build as build_export  # noqa: E402
from daily.export import interactions, low_value_reason  # noqa: E402
from daily.filter import parse_rule  # noqa: E402
from daily.incremental import classify, commit  # noqa: E402
from daily.model import Item  # noqa: E402
from daily.order import sort_accounts, sort_items  # noqa: E402
from daily.roster import Roster  # noqa: E402
from daily.state import State  # noqa: E402
from daily.window import IssueWindow  # noqa: E402

SAMPLE_DIR = SCRIPTS_DIR / "sample_items"
DAY = date(2026, 10, 23)
WINDOW = IssueWindow.for_day(DAY)


def make(
    native_id: str,
    account: str = "alice",
    published_at: str = "2026-10-23T03:00:00+00:00",
    *,
    text: str = "今日は配信です、よろしくお願いします",
    kind: str = "post",
    amplifiers: list[str] | None = None,
    url: str = "",
    source: str = "x",
) -> Item:
    return Item(
        key=f"{source}:{native_id}",
        source=source,
        native_id=native_id,
        account=account,
        published_at=published_at,
        text=text,
        kind=kind,
        amplifiers=list(amplifiers or []),
        url=url,
    )


class DedupeTest(unittest.TestCase):
    def test_same_native_id_collapses_to_one_item_with_two_amplifiers(self) -> None:
        """§1 问题②：同一条推被两个账号各转一次 → 1 条内容、2 个传播者。"""
        items = [
            make("2113601516565311503", "re_re_tsubame", kind="repost", amplifiers=["re_re_tsubame"]),
            make("2113601516565311503", "mirai_chiroru", kind="repost", amplifiers=["mirai_chiroru"]),
        ]
        merged = merge(items)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].amplifiers, ["mirai_chiroru", "re_re_tsubame"])

    def test_plain_post_gets_itself_in_amplifiers(self) -> None:
        merged = merge([make("1", "alice")])
        self.assertEqual(merged[0].amplifiers, ["alice"])

    def test_original_beats_repost(self) -> None:
        items = [
            make("1", "bob", kind="repost", amplifiers=["bob"]),
            make("1", "alice", kind="post"),
        ]
        merged = merge(items)
        self.assertEqual(merged[0].account, "alice")
        self.assertEqual(merged[0].amplifiers, ["alice", "bob"])

    def test_order_is_first_seen(self) -> None:
        items = [make("b"), make("a"), make("b")]
        self.assertEqual([i.native_id for i in merge(items)], ["b", "a"])

    def test_url_fallback_when_no_native_id(self) -> None:
        a = make("", url="https://x.com/alice/status/9")
        b = make("", url="http://www.x.com/alice/status/9/?s=1")
        self.assertEqual(identity(a), identity(b))
        self.assertEqual(len(merge([a, b])), 1)

    def test_normalize_url_strips_scheme_www_and_query(self) -> None:
        self.assertEqual(
            normalize_url("https://www.X.com/a/b/?utm=1#frag"), "x.com/a/b"
        )

    def test_text_fallback_when_nothing_else(self) -> None:
        a = make("", text="同じ本文です")
        b = make("", text="同じ本文です")
        self.assertEqual(len(merge([a, b])), 1)


class ClassifyTest(unittest.TestCase):
    def test_new_and_duplicate(self) -> None:
        item = make("1")
        first = classify([item], WINDOW, {})
        self.assertEqual(len(first.items), 1)
        seen = {"x:1": {"content_hash": item.content_hash}}
        second = classify([item], WINDOW, seen)
        self.assertEqual(len(second.items), 0)
        self.assertEqual(len(second.duplicate), 1)

    def test_updated_when_hash_changed(self) -> None:
        item = make("1", text="編集後の本文です、長めに書いておく")
        seen = {"x:1": {"content_hash": "sha256:deadbeef"}}
        result = classify([item], WINDOW, seen)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.updated), 1)

    def test_late_is_first_seen_before_window(self) -> None:
        """闸门第 2 条：10-01 的推、10-25 才第一次见到 → late，不进 items。"""
        old = make("1", published_at="2026-10-01T03:00:00+00:00")
        result = classify([old], IssueWindow.for_day(date(2026, 10, 25)), {})
        self.assertEqual(len(result.items), 0)
        self.assertEqual(len(result.late), 1)

    def test_old_content_already_seen_is_dropped_silently(self) -> None:
        """过去某期处理过的旧内容不算今天的重复项——否则数字会变成「全部历史」。"""
        old = make("1", published_at="2026-10-01T03:00:00+00:00")
        result = classify([old], WINDOW, {"x:1": {}})
        self.assertEqual((len(result.items), len(result.duplicate), len(result.late)), (0, 0, 0))

    def test_future_is_quarantined(self) -> None:
        ahead = make("1", published_at="2026-10-24T03:00:00+00:00")
        result = classify([ahead], WINDOW, {})
        self.assertEqual(len(result.future), 1)
        self.assertEqual(len(result.items), 0)

    def test_undated_is_ignored(self) -> None:
        result = classify([make("1", published_at="")], WINDOW, {})
        self.assertEqual((len(result.items), len(result.late), len(result.future)), (0, 0, 0))

    def test_buckets_partition_the_input(self) -> None:
        items = [
            make("new"),
            make("dup"),
            make("late", published_at="2026-10-01T03:00:00+00:00"),
            make("future", published_at="2026-10-24T03:00:00+00:00"),
        ]
        seen = {"x:dup": {"content_hash": items[1].content_hash}}
        result = classify(items, WINDOW, seen)
        buckets = result.buckets()
        self.assertEqual(sum(len(v) for v in buckets.values()), len(items))


class OrderTest(unittest.TestCase):
    def test_items_sort_by_time_then_source_then_id(self) -> None:
        items = [
            make("2", published_at="2026-10-23T05:00:00+00:00"),
            make("1", published_at="2026-10-23T05:00:00+00:00"),
            make("9", published_at="2026-10-23T01:00:00+00:00"),
        ]
        self.assertEqual([i.native_id for i in sort_items(items)], ["9", "1", "2"])

    def test_accounts_follow_roster_order_not_counts(self) -> None:
        roster = Roster(
            categories=[{"id": "seiyuu", "label": "声优"}],
            accounts=[],  # 用真实文件的顺序，见下一个测试
        )
        from daily.model import Account

        roster.accounts = [Account("z"), Account("a"), Account("m")]
        self.assertEqual(sort_accounts(["m", "z", "a"], roster), ["z", "a", "m"])
        self.assertEqual(sort_accounts(["m", "a"], None), ["a", "m"])

    def test_unknown_accounts_go_last(self) -> None:
        from daily.model import Account

        roster = Roster(categories=[], accounts=[Account("a")])
        self.assertEqual(sort_accounts(["zzz", "a"], roster), ["a", "zzz"])


class RosterTest(unittest.TestCase):
    def test_loads_the_real_file(self) -> None:
        roster = Roster.load()
        self.assertTrue(roster.is_known("asuparama40"))
        self.assertIn("other", [c["id"] for c in roster.categories])

    def test_unknown_handle_falls_back_to_other_and_warns(self) -> None:
        roster = Roster.load()
        buf = io.StringIO()
        missing = roster.warn_unknown(["asuparama40", "nobody_here"], stream=buf)
        self.assertEqual(missing, ["nobody_here"])
        self.assertEqual(roster.category_of("nobody_here"), "other")
        self.assertIn("nobody_here", buf.getvalue())

    def test_no_warning_when_all_known(self) -> None:
        buf = io.StringIO()
        Roster.load().warn_unknown(["asuparama40"], stream=buf)
        self.assertEqual(buf.getvalue(), "")


class ExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.roster = Roster.load()

    def test_interactions_only_inside_roster(self) -> None:
        item = make("1", "asuparama40", kind="repost", amplifiers=["asuparama40", "nobody_here"])
        edges = interactions([item], self.roster)
        self.assertEqual(edges, [])  # nobody_here 不在名单内，不建边

    def test_amplify_edge_is_bidirectional(self) -> None:
        item = make("1", "asuparama40", amplifiers=["asuparama40", "mimoriaino"])
        edges = interactions([item], self.roster)
        self.assertEqual(len(edges), 2)
        self.assertEqual({(e["from"], e["to"]) for e in edges}, {
            ("asuparama40", "mimoriaino"),
            ("mimoriaino", "asuparama40"),
        })

    def test_mention_edge(self) -> None:
        item = make("1", "asuparama40", text="@mimoriaino さんと一緒に配信します")
        edges = interactions([item], self.roster)
        self.assertEqual(edges[0]["kind"], "mention")
        self.assertEqual((edges[0]["from"], edges[0]["to"]), ("asuparama40", "mimoriaino"))

    def test_low_value_rules(self) -> None:
        self.assertEqual(low_value_reason(make("1", text="https://x.com/a/status/1")), "只有链接或空正文")
        self.assertEqual(low_value_reason(make("1", text="はい")), "正文过短")
        self.assertEqual(low_value_reason(make("1", text="今日は配信です、よろしく")), "")

    def test_counts_report_merged_items(self) -> None:
        items = [
            make("1", "asuparama40", kind="repost", amplifiers=["asuparama40"]),
            make("1", "mimoriaino", kind="repost", amplifiers=["mimoriaino"]),
        ]
        merged = merge(items)
        classification = classify(items, WINDOW, {})
        export = build_export("261023", classification, merged, self.roster, "2026-10-23T22:00:00+09:00")
        self.assertEqual(export["counts"]["items"], 1)
        # 只有一个人「拥有」这条内容；另一个人记在 amplifiers / interactions 里
        self.assertEqual(export["counts"]["accounts"], 1)
        self.assertEqual(len(merged[0].amplifiers), 2)
        self.assertEqual(len(export["interactions"]), 2)
        self.assertEqual(export["categories"][0]["id"], "seiyuu")


@unittest.skipUnless(SAMPLE_DIR.is_dir(), "缺少 scripts/sample_items")
class SamplePipelineTest(unittest.TestCase):
    """闸门 1 / 3：连跑两次、同一条推只算一条。"""

    def test_second_run_skips_all_28(self) -> None:
        items = list(XReaderAdapter(SAMPLE_DIR).iter_items())
        state = State()
        first = classify(items, WINDOW, state.seen)
        self.assertEqual(len(first.items), 28)
        commit(state, first, "261023", "2026-10-23T22:00:00+09:00")
        second = classify(items, WINDOW, state.seen)
        self.assertEqual(len(second.items), 0)
        self.assertEqual(len(second.duplicate), 28)

    def test_known_duplicate_pair(self) -> None:
        items = list(XReaderAdapter(SAMPLE_DIR).iter_items())
        pair = [i for i in items if i.native_id == "2113601516565311503"]
        self.assertEqual(len(pair), 2)
        merged = merge(pair)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0].amplifiers), 2)

    def test_state_roundtrip_is_byte_stable(self) -> None:
        items = list(XReaderAdapter(SAMPLE_DIR).iter_items())
        state = State()
        commit(state, classify(items, WINDOW, {}), "261023", "2026-10-23T22:00:00+09:00")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state.save(path)
            first = path.read_bytes()
            State.load(path).save(path)
            self.assertEqual(first, path.read_bytes())


class CliTest(unittest.TestCase):
    """命令行一条龙：落盘、账本、拒绝覆盖。"""

    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    @unittest.skipUnless(SAMPLE_DIR.is_dir(), "缺少 scripts/sample_items")
    def test_build_writes_three_files_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            code, out, _ = self.run_cli([
                "build", "--items-dir", str(SAMPLE_DIR), "--date", "2026-10-23",
                "--at", "2026-10-23 22:00", "--out", str(tmp_path / "out"),
                "--report-out", str(tmp_path / "report" / "261023.json"), "--state", str(tmp_path / "state.json"),
            ])
            self.assertEqual(code, 0)
            self.assertTrue((tmp_path / "out" / "261023.briefing.txt").exists())
            self.assertTrue((tmp_path / "out" / "261023.generate.json").exists())
            self.assertTrue((tmp_path / "report" / "261023.json").exists())
            state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(len(state["issues"]), 1)
            self.assertIn("27 条", out)

    @unittest.skipUnless(SAMPLE_DIR.is_dir(), "缺少 scripts/sample_items")
    def test_refuses_to_overwrite_existing_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            argv = [
                "build", "--items-dir", str(SAMPLE_DIR), "--date", "2026-10-23",
                "--at", "2026-10-23 22:00", "--out", str(tmp_path / "out"),
                "--report-out", str(tmp_path / "report" / "261023.json"), "--state", str(tmp_path / "state.json"),
            ]
            self.assertEqual(self.run_cli(argv)[0], 0)
            code, _, err = self.run_cli(argv)
            self.assertEqual(code, 3)
            self.assertIn("拒绝覆盖", err)

    @unittest.skipUnless(SAMPLE_DIR.is_dir(), "缺少 scripts/sample_items")
    def test_backfill_ignores_state_and_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            code, out, _ = self.run_cli([
                "build", "--items-dir", str(SAMPLE_DIR), "--date", "2026-10-23",
                "--at", "2026-10-23 22:00", "--out", str(tmp_path / "out"),
                "--report-out", str(tmp_path / "report" / "261023.json"), "--backfill",
            ])
            self.assertEqual(code, 0)
            self.assertIn("迟到 0", out)
            self.assertIn("晚于窗口 0", out)
            self.assertFalse((tmp_path / "state.json").exists())

class InactiveAccountTest(unittest.TestCase):
    """名单里 active=false 的账号（现在的社团号）暂时不进日报。

    跳过的是**条目**，不是当成未知账号：它们在名单里，只是不消化。
    """

    def test_inactive_items_are_dropped_from_the_issue(self) -> None:
        from daily.model import Account

        roster = Roster(
            categories=[{"id": "seiyuu", "label": "声优"}],
            accounts=[Account("alice"), Account("some_circle", category="circle", active=False)],
        )
        items = [make("1", "alice"), make("2", "some_circle")]
        buf = io.StringIO()
        with redirect_stderr(buf):
            _, merged, accounts, _ = cli._pipeline(items, WINDOW, roster, {})
        self.assertEqual([i.account for i in merged], ["alice"])
        self.assertEqual(accounts, ["alice"])
        self.assertIn("some_circle", buf.getvalue())  # 静默跳过会让「人不见了」无从查起

    def test_circles_are_active_since_the_two_edition_split(self) -> None:
        """2026-10-29 起社团号进抓取：声优版 = 声优 + 音声社团，两类都 active。"""
        roster = Roster.load()
        circles = [a for a in roster.accounts if a.category == "circle"]
        self.assertTrue(circles, "社团号应该已经在名单里")
        self.assertTrue(all(a.active for a in circles), "社团号一律 active=true")
        self.assertEqual(roster.category_of(circles[0].handle), "circle")
        self.assertIn("circle", roster.category_ids)

    def test_manufacturers_are_active_and_form_their_own_column(self) -> None:
        """厂商号从 2026-10-27 起进抓取，2026-10-29 起归到 Galgame 版单独一栏。

        改的是「抓不抓」，不是「怎么显示」：Galgame 版日报页的栏目筛选按钮默认只看
        游戏制造商，点「信息号」才把它们加进列表——所以放它们进来不会把厂商那几句挤没。

        Moepedia 也在这一栏（对读者来说情报站和厂商是一回事，都发新作信息），
        但它广告味重，靠 `filter` 段降噪——见 test_daily_filter.py。
        """
        roster = Roster.load(kind="galgame")
        makers = [a for a in roster.accounts if a.category == "manufacturer"]
        self.assertTrue(makers, "制造商应该已经在名单里")
        self.assertTrue(all(a.active for a in makers), "厂商号一律 active=true")
        # 这一栏里只有一家不是品牌号：Moepedia 是作品情报站。
        self.assertEqual(
            {a.handle for a in makers if a.role != "brand"},
            {"Moepedia_net"},
            "manufacturer 段里出现了非品牌号：确认它确实是情报来源，再改这条断言",
        )
        # 带降噪规则的号：Moepedia + 2026-10-29 启用的五个信息号。
        self.assertEqual(
            set(roster.filters),
            {"moepedia_net", "seiya_saiga", "youtan0309", "aikouka23",
             "getchucom", "bugbug_info"},
        )
        self.assertTrue(all("游戏" in a.tags or "资料站" in a.tags for a in makers))
        self.assertTrue(any("Moe Award" in a.tags for a in makers), "拿过萌奖的应该有标签")
        self.assertIn("manufacturer", [c["id"] for c in roster.categories])

    def test_rosters_are_split_by_edition(self) -> None:
        """两份名单各管一版：声优版没有厂商，Galgame 版没有声优。"""
        voice = Roster.load()
        galgame = Roster.load(kind="galgame")
        self.assertNotIn("manufacturer", voice.category_ids)
        self.assertNotIn("info", voice.category_ids)
        self.assertNotIn("seiyuu", galgame.category_ids)
        self.assertNotIn("circle", galgame.category_ids)

        # 但查询层是合并的：拿声优版查一个厂商号，名字和栏目照样查得到——
        # 历史期号（261025–261028）是合并名单时代的产物，people 里有厂商。
        self.assertEqual(voice.category_of("silkysplus"), "manufacturer")
        self.assertTrue(voice.is_known("silkysplus"))
        self.assertEqual(galgame.category_of("yukanyan2525"), "seiyuu")

    def test_info_accounts_are_the_five_enabled_ones(self) -> None:
        """信息号 2026-10-29 启用五个：三个个人向 + 两个媒体号。

        媒体号（getchucom 发售日历 / bugbug_info 新作介绍）用 `keep_if` 白名单，
        只收指定内容；其余媒体号明确不加。厂商侧个人号还没入册。
        """
        roster = Roster.load(kind="galgame")
        info = [a.handle for a in roster.accounts if a.category == "info"]
        self.assertEqual(
            sorted(info),
            ["aikouka23", "bugbug_info", "getchucom", "seiya_saiga", "youtan0309"],
        )
        for handle in ("Famishin", "nakazawatakumi", "digitarou"):
            self.assertFalse(roster.is_known(handle), f"{handle} 是厂商侧个人号，暂时不入册")
        # 媒体号必须是白名单，不是黑名单——黑名单列不全「不要什么」。
        for handle in ("getchucom", "bugbug_info"):
            self.assertIn("keep_if", roster.filters[handle], f"{handle} 应该走 keep_if")
        for handle in ("seiya_saiga", "youtan0309", "aikouka23"):
            self.assertNotIn("keep_if", roster.filters[handle], "个人号不收窄到白名单")

    def test_every_roster_filter_compiles(self) -> None:
        """名单里的正则全部当场编译一遍。

        规则是数据，写错一个括号不会在 `Roster.load` 报错，要等那天真的抓到
        这个号的条目、走到 `apply_rules` 才炸——而那时已经在出稿路径上了。
        """
        for kind in ("voice", "galgame"):
            roster = Roster.load(kind=kind)
            for handle, raw in roster.filters.items():
                with self.subTest(kind=kind, handle=handle):
                    rule = parse_rule(handle, raw)
                    self.assertFalse(rule.empty, f"{handle} 的 filter 是空的，删掉它")

    def test_handles_are_unique(self) -> None:
        """一个 handle 只能有一条。

        社团号、厂商号、声优号会撞车（同一个号既是厂商的又是社团的），
        重复建条目会让「同一件事」在两个分类里各算一次。
        """
        roster = Roster.load()
        handles = [a.handle.lower() for a in roster.accounts]
        dupes = {h for h in handles if handles.count(h) > 1}
        self.assertEqual(dupes, set())


if __name__ == "__main__":
    unittest.main()
