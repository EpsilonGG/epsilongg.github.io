"""Gplus 信息号回复抓取与切片合并。

RSS 出口没有 is_reply 字段（gplus_fetch.py 里硬编码 False），所以回复必须走
Nitter profile HTML。这里钉死三件事：只收带 replying-to 的条目、12 小时制日期
不能读错（11:35 PM 不是 11:35）、重切不能冲掉已有历史条目。
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

import gplus_replies  # noqa: E402
import gplus_slice  # noqa: E402


def _tweet(item_id: str, author: str, body: str, *, reply_to: str = "") -> str:
    reply = (
        f'<div class="replying-to">Replying to <a href="/{reply_to}">@{reply_to}</a></div>'
        if reply_to else ""
    )
    return f"""<div class="timeline-item author-{author}" data-username="{author}">
  <a class="tweet-link" href="/{author}/status/{item_id}#m"></a>
  <div class="tweet-body">
    {reply}
    <div class="tweet-header"><a href="/{author}" class="username">@{author}</a>
      <span class="tweet-date"><a href="/{author}/status/{item_id}#m"
        title="Nov 19, 2026 · 11:35 PM UTC">Nov 19</a></span></div>
    <div class="tweet-content media-body" dir="auto">{body}</div>
  </div>
</div>"""


PROFILE = (
    '<div class="timeline">'
    + _tweet("111", "famitsu", 'New <a href="https://example.com">link</a> &amp; text')
    + _tweet("222", "famitsu", "今日はおつかれさまでした", reply_to="someone")
    + _tweet("333", "someone_else", "別アカの返信", reply_to="famitsu")
    + "</div>"
)


class ParseDateTest(unittest.TestCase):
    def test_pm_is_not_read_as_am(self) -> None:
        self.assertEqual(
            gplus_replies.parse_nitter_date("Nov 19, 2026 · 11:35 PM UTC"),
            "2026-11-19T23:35:00+00:00",
        )

    def test_jst_offset_and_relative_date(self) -> None:
        self.assertEqual(
            gplus_replies.parse_nitter_date("Nov 19, 2026 · 9:00 AM JST"),
            "2026-11-19T09:00:00+09:00",
        )
        self.assertIsNone(gplus_replies.parse_nitter_date("3h"))


class ParseProfileTest(unittest.TestCase):
    def test_only_own_reply_items_survive(self) -> None:
        items = gplus_replies.parse_profile(PROFILE, "famitsu")
        self.assertEqual([i["item_id"] for i in items], ["222"])
        item = items[0]
        self.assertTrue(item["metadata"]["is_reply"])
        self.assertEqual(item["metadata"]["reply_to"], "someone")
        self.assertEqual(item["metadata"]["provider"], "nitter-html")
        self.assertEqual(item["published_at"], "2026-11-19T23:35:00+00:00")
        self.assertEqual(item["canonical_url"], "https://x.com/famitsu/status/222")

    def test_reply_to_falls_back_to_href(self) -> None:
        html = _tweet("444", "DLsite", "hello", reply_to="someone").replace(
            '<a href="/someone">@someone</a>', '<a href="/someone">someone</a>'
        )
        items = gplus_replies.parse_profile(f"<div class=\"timeline\">{html}</div>", "DLsite")
        self.assertEqual(items[0]["metadata"]["reply_to"], "someone")

    def test_status_page_parent_mode(self) -> None:
        """Status pages have no replying-to marker; every non-focal item is a reply."""
        html = (
            '<div class="timeline">'
            + _tweet("100", "famitsu", "focal tweet")
            + _tweet("101", "creator_x", "面白いです")
            + "</div>"
        )
        items = gplus_replies.parse_profile(html, parent={"id": "100", "handle": "famitsu"})
        self.assertEqual([i["item_id"] for i in items], ["101"])
        self.assertEqual(items[0]["metadata"]["reply_to"], "famitsu")
        self.assertEqual(items[0]["metadata"]["parent_tweet_id"], "100")
        self.assertEqual(items[0]["metadata"]["route"], "status-html")

    def test_scope_replies_drops_other_peoples_comments(self) -> None:
        """Only replies authored by a scope account survive; comments do not."""
        html = (
            '<div class="timeline">'
            + _tweet("100", "youtan0309", "focal tweet")
            + _tweet("101", "youtan0309", "自分への返信")
            + _tweet("102", "cloud668", "別のスコープアカウント")
            + _tweet("103", "random_player", "ただのコメント")
            + "</div>"
        )
        items = gplus_replies.scope_replies(
            gplus_replies.parse_profile(html, parent={"id": "100", "handle": "youtan0309"}),
            {"youtan0309", "cloud668"},
        )
        self.assertEqual([i["item_id"] for i in items], ["101", "102"])

    def test_thread_targets_use_newest_own_tweets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "famitsu.json").write_text(json.dumps({"status": "ok", "items": [
                {"item_id": "1", "publisher": "famitsu", "published_at": "2026-11-22T01:00:00+00:00",
                 "metadata": {"is_retweet": False}},
                {"item_id": "2", "publisher": "famitsu", "published_at": "2026-11-21T01:00:00+00:00",
                 "metadata": {"is_retweet": False}},
                {"item_id": "3", "publisher": "famitsu", "published_at": "2026-11-23T01:00:00+00:00",
                 "metadata": {"is_retweet": True}},
                {"item_id": "4", "publisher": "elsewhere", "published_at": "2026-11-23T01:00:00+00:00",
                 "metadata": {"is_retweet": False}},
            ]}), encoding="utf-8")
            targets = gplus_replies.thread_targets(raw, ["famitsu"], 1)
            self.assertEqual([t["id"] for t in targets], ["1"])

    def test_reply_scope_roster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            roster = Path(tmp) / "roster.json"
            roster.write_text(
                json.dumps({"accounts": [
                    {"handle": "youtan0309", "group": "info", "reply_scope": True},
                    {"handle": "someone", "group": "creator"},
                    {"handle": "famitsu", "group": "info"},
                    {"handle": "cloud668", "group": "info", "reply_scope": True},
                    {"handle": "DLsite", "group": "info", "reply_scope": False},
                ]}),
                encoding="utf-8",
            )
            self.assertEqual(gplus_replies.reply_scope_handles(roster),
                             ["youtan0309", "cloud668"])

    def test_prune_cache_drops_out_of_scope_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "youtan0309.json").write_text(
                json.dumps({"handle": "youtan0309", "status": "ok", "items": []}),
                encoding="utf-8",
            )
            (out / "famitsu.json").write_text(
                json.dumps({"handle": "famitsu", "status": "ok", "items": []}),
                encoding="utf-8",
            )
            removed = gplus_replies.prune_cache([out], {"youtan0309"})
            self.assertEqual(removed, 1)
            self.assertEqual(sorted(p.name for p in out.glob("*.json")), ["youtan0309.json"])

    def test_cached_thread_is_refiltered_on_scope_narrowing(self) -> None:
        """A cached status payload is rewritten when the scope shrinks."""
        def item(iid: str, author: str) -> dict:
            return {"item_id": iid, "publisher": author,
                    "metadata": {"route": "status-html", "is_reply": True}}

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            parent = {"id": "100", "handle": "youtan0309"}
            payload = {"parent": parent, "status": "ok",
                       "items": [item("101", "youtan0309"),
                                 item("102", "random_player")]}
            (out / "100.json").write_text(json.dumps(payload, ensure_ascii=False),
                                          encoding="utf-8")
            result = gplus_replies.fetch_thread(parent, None, out, {"youtan0309"})
            self.assertEqual(result["status"], "cached")
            self.assertEqual(result["items"], 1)
            stored = json.loads((out / "100.json").read_text(encoding="utf-8"))
            self.assertEqual([i["item_id"] for i in stored["items"]], ["101"])


class SliceMergeTest(unittest.TestCase):
    def test_existing_history_is_preserved_and_reply_replaces_rss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            replies = Path(tmp) / "replies"
            dest = Path(tmp) / "dest"
            raw.mkdir(); replies.mkdir(); dest.mkdir()

            old_line = json.dumps({"item_id": "999", "content": "old"}, ensure_ascii=False)
            rss_line = json.dumps(
                {"item_id": "222", "content": "rss", "metadata": {"is_reply": False}},
                ensure_ascii=False,
            )
            (dest / "2026-11-19.jsonl").write_text(old_line + "\n" + rss_line + "\n", encoding="utf-8")
            (raw / "famitsu.json").write_text(
                json.dumps({"status": "ok", "items": [{
                    "item_id": "111", "published_at": "2026-11-19T01:00:00+00:00",
                    "content": "new rss",
                }]}),
                encoding="utf-8",
            )
            (replies / "famitsu.json").write_text(
                json.dumps({"status": "ok", "items": [{
                    "item_id": "222", "published_at": "2026-11-19T14:35:00+00:00",
                    "content": "reply body",
                    "metadata": {"is_reply": True, "reply_to": "someone"},
                }]}),
                encoding="utf-8",
            )

            by_day = gplus_slice.load_items(raw)
            got = gplus_slice.load_items(replies)
            for day, items in got.items():
                by_day[day].update(items)
            count = gplus_slice.write_day(dest / "2026-11-19.jsonl", by_day["2026-11-19"])

            lines = (dest / "2026-11-19.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(count, 3)  # old + new rss + reply (no duplicate 222)
            items = {json.loads(line)["item_id"]: json.loads(line) for line in lines}
            self.assertEqual(set(items), {"999", "111", "222"})
            self.assertEqual(items["999"]["content"], "old")  # existing line preserved
            self.assertEqual(items["111"]["content"], "new rss")
            self.assertTrue(items["222"]["metadata"]["is_reply"])
            self.assertEqual(items["222"]["content"], "reply body")

    def test_status_html_reply_never_overwrites_rss_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-11-22.jsonl"
            original = {"item_id": "555", "content": "rss with seconds",
                        "published_at": "2026-11-22T05:00:19+00:00"}
            path.write_text(json.dumps(original, ensure_ascii=False) + "\n", encoding="utf-8")
            gplus_slice.write_day(path, {
                "555": {"item_id": "555", "content": "status minute precision",
                        "published_at": "2026-11-22T05:00:00+00:00",
                        "metadata": {"route": "status-html", "is_reply": True}},
                "556": {"item_id": "556", "content": "new reply",
                        "metadata": {"route": "status-html", "is_reply": True}},
            })
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0]), original)
            self.assertEqual(json.loads(lines[1])["item_id"], "556")


if __name__ == "__main__":
    unittest.main()
