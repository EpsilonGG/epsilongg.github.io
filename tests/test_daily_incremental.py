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
        export = build_export("26102322", classification, merged, self.roster, "2026-10-23T22:00:00+09:00")
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
        commit(state, first, "26102322", "2026-10-23T22:00:00+09:00")
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
        commit(state, classify(items, WINDOW, {}), "26102322", "2026-10-23T22:00:00+09:00")
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
                "--md-out", str(tmp_path / "26102322.md"), "--state", str(tmp_path / "state.json"),
            ])
            self.assertEqual(code, 0)
            self.assertTrue((tmp_path / "out" / "26102322.briefing.txt").exists())
            self.assertTrue((tmp_path / "out" / "26102322.generate.json").exists())
            self.assertTrue((tmp_path / "26102322.md").exists())
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
                "--md-out", str(tmp_path / "26102322.md"), "--state", str(tmp_path / "state.json"),
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
                "--md-out", str(tmp_path / "26102322.md"), "--backfill",
            ])
            self.assertEqual(code, 0)
            self.assertIn("迟到 0", out)
            self.assertIn("晚于窗口 0", out)
            self.assertFalse((tmp_path / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
