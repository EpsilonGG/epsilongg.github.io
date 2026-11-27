"""X 推文归属回归：转发/引用不能算成抓取账号本人的发言。

2026-11-27 Gplus 日报把浅生詠（asou_ei）三条来源都当成她本人发的，实际全是
mzn773 / sayuki_acp / tkwsnb 的推文被她转发。根因在 Nitter RSS 解析：title
里的 `RT @author (by @viewer)` 被丢掉，publisher 直接写成被抓的账号。

    python -m unittest tests.test_gplus_attribution -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gplus_digest  # noqa: E402
import gplus_fetch  # noqa: E402
import gplus_publish  # noqa: E402
from daily import prompt as daily_prompt  # noqa: E402

DATE = "2026-11-27"
PUBDATE = "Fri, 27 Nov 2026 05:00:00 GMT"


def rss_bytes(rows: list[tuple[str, str, str]]) -> bytes:
    items = "".join(
        f"<item><title>{escape(title)}</title><link>{link}</link>"
        f"<description>{escape(desc)}</description><pubDate>{PUBDATE}</pubDate></item>"
        for title, link, desc in rows
    )
    return ("<rss><channel>" + items + "</channel></rss>").encode("utf-8")


class GplusFetchAttributionTest(unittest.TestCase):
    def test_retweet_author_and_retweeter_are_separated(self) -> None:
        raw = rss_bytes([
            (
                "RT @sayuki_acp (by @asou_ei): 終のステラ、見る度にセールしてる気がする笑",
                "https://nitter.cf/sayuki_acp/status/2126223564793958426",
                "<p>終のステラ、見る度にセールしてる気がする笑</p>",
            )
        ])
        item = gplus_fetch.parse_rss(raw, "asou_ei")[0]
        self.assertEqual(item["publisher"], "sayuki_acp")
        self.assertEqual(item["metadata"]["account"], "asou_ei")
        self.assertEqual(item["metadata"]["retweeted_by"], "asou_ei")
        self.assertTrue(item["metadata"]["is_retweet"])
        self.assertEqual(item["canonical_url"], "https://x.com/sayuki_acp/status/2126223564793958426")
        self.assertIn("終のステラ", item["content"])

    def test_quote_body_is_split_out_and_attributed(self) -> None:
        desc = (
            "<p>ミャウワウ役で出演します</p><hr/><blockquote>"
            "<b>Liar-soft＆raiL-soft (@liar_railsoft)</b>"
            "<p>新作ティザーサイトを公開しました</p>"
            '<footer>— <cite><a href="https://nitter.cf/liar_railsoft/status/2126239611508990136">'
            "https://nitter.cf/liar_railsoft/status/2126239611508990136</a></cite></footer>"
            "</blockquote>"
        )
        raw = rss_bytes([(
            "RT @mzn773 (by @asou_ei): ミャウワウ役で出演します",
            "https://nitter.cf/mzn773/status/2126325643659079835", desc,
        )])
        item = gplus_fetch.parse_rss(raw, "asou_ei")[0]
        self.assertEqual(item["publisher"], "mzn773")
        meta = item["metadata"]
        self.assertTrue(meta["is_retweet"])  # asou_ei 转了 mzn773 的引用推
        self.assertTrue(meta["is_quote"])
        self.assertEqual(meta["quoted_author"], "liar_railsoft")
        self.assertEqual(meta["quoted_tweet_id"], "2126239611508990136")
        self.assertIn("ティザーサイト", meta["quoted_text"] or "")
        self.assertIn("ミャウワウ役", item["content"])
        self.assertNotIn("ティザーサイト", item["content"])

    def test_original_still_belongs_to_scraped_account(self) -> None:
        raw = rss_bytes([("Pinned: 自主制作ゲームを公開しました", "https://nitter.cf/asou_ei/status/111", "<p>自主制作ゲーム</p>")])
        item = gplus_fetch.parse_rss(raw, "asou_ei")[0]
        self.assertEqual(item["publisher"], "asou_ei")
        self.assertEqual(item["metadata"]["account"], "asou_ei")
        self.assertFalse(item["metadata"]["is_retweet"])
        self.assertFalse(item["metadata"]["is_quote"])
        self.assertTrue(item["metadata"]["is_pinned"])
        self.assertEqual(item["content"], "自主制作ゲーム")


class GplusDigestAttributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.slices = root / "slices"
        self.slices.mkdir()
        self.dest = root / "digest"
        roster = root / "roster.json"
        roster.write_text(json.dumps({"accounts": [{"handle": "asou_ei", "name": "浅生 詠", "group": "creator"}]}), encoding="utf-8")
        rows = [
            {
                "item_id": "1", "publisher": "asou_ei", "content": "本人のオリジナル",
                "published_at": "2026-11-27T05:00:00+00:00",
                "metadata": {"account": "asou_ei", "is_retweet": False, "is_quote": False},
            },
            {
                "item_id": "2", "publisher": "sayuki_acp", "content": "終のステラ700円",
                "published_at": "2026-11-27T05:00:00+00:00",
                "metadata": {"account": "asou_ei", "is_retweet": True, "retweeted_by": "asou_ei"},
            },
            {
                "item_id": "3", "publisher": "asou_ei", "content": "私のコメント",
                "published_at": "2026-11-27T05:00:00+00:00",
                "metadata": {
                    "account": "asou_ei", "is_retweet": False, "is_quote": True,
                    "quoted_author": "liar_railsoft", "quoted_text": "ティザー公開",
                },
            },
        ]
        (self.slices / f"{DATE}.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
        )
        self._old = (gplus_digest.SLICES, gplus_digest.ROSTER)
        gplus_digest.SLICES, gplus_digest.ROSTER = self.slices, roster
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        gplus_digest.SLICES, gplus_digest.ROSTER = self._old

    def build(self) -> str:
        self.assertEqual(gplus_digest.main(["--date", DATE, "--dest", str(self.dest)]), 0)
        return (self.dest / f"{DATE}.md").read_text(encoding="utf-8")

    def test_accounts_excludes_retweet_and_marks_quote_inline(self) -> None:
        text = self.build()
        self.assertIn("items=3 accounts=2 originals=2", text)
        accounts = text.split("\n## Accounts (originals", 1)[1]
        self.assertIn("[1] 本人のオリジナル", accounts)
        self.assertIn("引用了 @liar_railsoft", accounts)
        self.assertNotIn("終のステラ700円", accounts)
        self.assertNotIn("@sayuki_acp |", accounts)

    def test_reposts_and_quotes_name_the_real_author(self) -> None:
        text = self.build()
        self.assertIn("### @asou_ei x1", text)
        self.assertIn("- [2] -> @sayuki_acp: 終のステラ700円", text)
        self.assertIn("## Quotes (quoter -> [id] @quoted_author: quoted body)", text)
        self.assertIn("@liar_railsoft: ティザー公開", text)


class DailyPromptAttributionTest(unittest.TestCase):
    def test_flattened_quote_is_marked_in_prompt(self) -> None:
        text = daily_prompt._item_lines([
            {
                "key": "x:1", "account": "viewer", "published_at": "2026-11-27T10:00:00+09:00",
                "kind": "post",
                "text": "自分异常的感想\n\n他人の発表\n\n— https://nitter.cf/original_author/status/999",
            }
        ])
        self.assertIn("引用了 @original_author", text.splitlines()[0])
        self.assertIn("自分异常的感想", text)

    def test_own_quote_is_not_flagged(self) -> None:
        text = daily_prompt._item_lines([{
            "key": "x:2", "account": "viewer", "published_at": "2026-11-27T10:00:00+09:00",
            "kind": "post", "text": "— https://nitter.cf/viewer/status/999",
        }])
        self.assertNotIn("引用了", text.splitlines()[0])


class GplusPublishAttributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = {
            "x:1": {
                "item_id": "1", "publisher": "sayuki_acp",
                "metadata": {"account": "asou_ei", "is_retweet": True},
            },
            "x:2": {
                "item_id": "2", "publisher": "asou_ei",
                "metadata": {"account": "asou_ei", "is_retweet": False},
            },
        }
        self.report = {
            "issue": {
                "id": "Gplus_999",
                "window": {"start": f"{DATE}T00:00:00+09:00"},
                "status": "confirmed",
            },
            "highlights": [], "insights": [], "interactions": [],
            "people": [{"handle": "asou_ei", "summary": "浅生詠の話", "sources": ["x:1"]}],
            "works": [],
        }

    def test_person_with_only_retweeted_sources_is_rejected(self) -> None:
        errors = gplus_publish.check(self.report, self.sources, {"asou_ei", "sayuki_acp"})
        self.assertTrue(any("no source authored by this handle" in err for err in errors), errors)

    def test_person_with_own_source_passes_attribution_check(self) -> None:
        self.report["people"][0]["sources"] = ["x:2"]
        errors = gplus_publish.check(self.report, self.sources, {"asou_ei", "sayuki_acp"})
        self.assertFalse([err for err in errors if "authored by this handle" in err], errors)

    def test_repost_source_requires_attribution_wording(self) -> None:
        self.report["people"] = []
        self.report["interactions"] = [{"text": "終のステラが700円", "sources": ["x:1"]}]
        errors = gplus_publish.check(self.report, self.sources, {"asou_ei", "sayuki_acp"})
        self.assertTrue(any("repost source needs 转发/引用" in err for err in errors), errors)
        self.report["interactions"][0]["text"] = "浅生詠转发了佐雪隼的消息：終のステラが700円"
        errors = gplus_publish.check(self.report, self.sources, {"asou_ei", "sayuki_acp"})
        self.assertFalse([err for err in errors if "repost source needs" in err], errors)


if __name__ == "__main__":
    unittest.main()
