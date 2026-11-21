"""原推事实层的回归（2026-11-21 用户裁决）。

守住三条口径：
* 作品名 / 新作信号先看**本推正文**（`origin_text`），中文概括只作表述层；
* 只取本推，不把引用推文、RT 前缀、裸 URL 当成这条账号发布的事实；
* 零 LLM / 零联网：这些都是纯字符串函数，跑一次 build 不再叫模型。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEEKLY_DIR = ROOT / "weekly"
ALIAS = "_weekly_root_source_grounding"
if ALIAS not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        ALIAS, WEEKLY_DIR / "__init__.py",
        submodule_search_locations=[str(WEEKLY_DIR)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = package
    spec.loader.exec_module(package)

sg = importlib.import_module(ALIAS + ".source_grounding")
pipeline = importlib.import_module(ALIAS + ".pipeline")
config = importlib.import_module(ALIAS + ".config")
RULES = config.load_rules()

YUZU_ORIGINAL = (
    "【お知らせ】ゆずソフト最新作『ライムライト・レモネードジャム』の"
    "海外版の発売が決定しました！英語・中国語・韓国語版を展開予定です。"
    "\n\nDLsite (@DLsite_English)\n🎸 Yuzusoft is BACK! "
    "https://nitter.cf/DLsite_English/status/2"
)


def _corpus(original: str, chinese: str, titles: list[str],
            *, chinese_titles: list[str] | None = None) -> dict:
    titles = [sg.norm_title(t) for t in titles]
    chinese_titles = ([sg.norm_title(t) for t in chinese_titles]
                      if chinese_titles is not None else list(titles))
    return {
        "schema_version": 1,
        "window": {"start": "2026-11-20", "end": "2026-11-20"},
        "issues": ["261120-g"],
        "indexed_issues": ["261120-g"], "prose_only_issues": [],
        "source_refs": {
            "x:1": {
                "url": "https://x.com/yuzusoft/status/1",
                "author": "yuzusoft", "published_at": "2026-11-20T05:03:26+00:00",
                "text": original, "origin": "xreader",
                "origin_text": sg.primary_text({"text": original}),
                "origin_titles": sg.title_values(sg.primary_text({"text": original})),
            }
        },
        "candidates": [{
            "clause_id": "261120-g/yuzusoft#1", "issue": "261120-g",
            "day": "2026-11-20", "handle": "yuzusoft", "group": "@yuzusoft",
            "group_fallback": True, "text": chinese, "context": chinese,
            "sources": ["x:1"], "precision": "row", "dedupe_key": "x:1",
        }],
        "daily_rows": [], "titles": titles, "original_titles": titles,
        "chinese_titles": chinese_titles, "stats": {},
    }


class PrimaryTextTests(unittest.TestCase):
    def test_quoted_tweet_and_urls_are_not_the_authors_facts(self):
        text = sg.primary_text({"text": YUZU_ORIGINAL})
        self.assertIn("海外版の発売が決定", text)
        self.assertNotIn("Yuzusoft is BACK", text)
        self.assertNotIn("http", text)

    def test_rt_prefix_is_stripped(self):
        self.assertEqual(
            sg.primary_text({"text": "RT @Moepedia_net: 『X』発売 https://t.co/a"}),
            "『X』発売",
        )

    def test_generic_bracketed_noise_is_not_a_work_title(self):
        values = sg.title_values("『本物のゲーム』と『通常版』『11/24(火)13時』『ストーリー』")
        self.assertEqual(values, ["本物のゲーム"])


class SourceFirstRoutingTests(unittest.TestCase):
    def test_missing_title_in_chinese_is_recovered_from_original(self):
        data = _corpus(YUZU_ORIGINAL, "海外版确认，支持四种语言",
                       ["ライムライト・レモネードジャム"])
        result = pipeline.run(data, RULES)
        rec = result["records"][0]
        self.assertEqual(rec["work"], "ライムライト・レモネードジャム")
        self.assertEqual(rec["work_basis"], "source+verbatim")
        item = result["sections"][0]["items"][0]
        self.assertEqual(item["display_column"], config.NEW)

    def test_truncated_title_is_completed_from_original(self):
        original = "電子書籍『放課後シンデレラ 長南陽佳は幼馴染。』が11月27日に発売されます"
        data = _corpus(original, "电子书『放課後シンデレラ』11/27 推出",
                       ["放課後シンデレラ 長南陽佳は幼馴染。", "放課後シンデレラ"],
                       chinese_titles=["放課後シンデレラ"])
        rec = pipeline.run(data, RULES)["records"][0]
        self.assertEqual(rec["work"], "放課後シンデレラ長南陽佳は幼馴染。")
        self.assertEqual(rec["work_basis"], "source+verbatim")

    def test_unrelated_song_title_in_original_does_not_hijack_the_game(self):
        original = "『ハピメア FD』主題歌『幻想楼閣』配信開始"
        data = _corpus(original, "『ハピメア FD』主题曲开始配信",
                       ["ハピメア FD", "幻想楼閣"], chinese_titles=["ハピメア FD"])
        rec = pipeline.run(data, RULES)["records"][0]
        self.assertEqual(rec["work"], "ハピメアFD")
        # 中文题名在原推里也确实出现，所以不算冲突；只是不能让同推的主题歌顶掉它。
        self.assertFalse(rec["source_conflict"])

    def test_source_text_is_carried_into_evidence(self):
        data = _corpus(YUZU_ORIGINAL, "海外版确认", ["ライムライト・レモネードジャム"])
        result = pipeline.run(data, RULES)
        self.assertIn("発売が決定", result["records"][0]["source_text"])
        self.assertIn("source_text", result["sections"][0]["items"][0])


if __name__ == "__main__":
    unittest.main()
