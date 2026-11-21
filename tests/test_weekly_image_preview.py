"""图片栏目只允许 X 原推配图的回归（2026-11-21 裁决）。

B站动态认亲成功后会并进 X 侧品牌-游戏子集参与归栏，但它没有 `/photo/1`
入口。若把它当普通图片源，会拼出 `.../opus/<id>/photo/1` 这种坏链。这里钉住：
文本归栏照旧，配图只收 `x:<id>` / `x.com/status`。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEEKLY_DIR = ROOT / "weekly"
ALIAS = "_weekly_root_image_preview"
if ALIAS not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        ALIAS, WEEKLY_DIR / "__init__.py",
        submodule_search_locations=[str(WEEKLY_DIR)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = package
    spec.loader.exec_module(package)

image_preview = importlib.import_module(ALIAS + ".image_preview")
config = importlib.import_module(ALIAS + ".config")
RULES = config.load_rules()

X_URL = "https://x.com/yuzusoft/status/1"
BILI_URL = "https://www.bilibili.com/opus/2"
GAME = "『LimeLightLemonadeJam（暂译）』"


def _fixture() -> tuple[dict, dict]:
    media = {
        "x:1": ["https://pbs.twimg.com/media/x1.jpg"],
        "bilibili:2": ["http://i0.hdslb.com/bfs/new_dyn/b.jpg"],
    }
    refs = {
        "x:1": {"url": X_URL, "author": "yuzusoft"},
        "bilibili:2": {"url": BILI_URL, "author": "bili_373471"},
    }
    data = {
        "sections": [{
            "key": "s:1", "label": "ゆずソフト", "column": config.WORK,
            "items": [{
                "key": "i:1",
                "group_label": GAME,
                "work_canonical": GAME.strip("『』"),
                "sentence": "柚子社新作确定多语版",
                "sources": [
                    {"key": "x:1", "url": X_URL},
                    {"key": "bilibili:2", "url": BILI_URL},
                ],
            }],
        }]
    }
    return {"source_refs": refs}, data


class XOnlyImageScopeTests(unittest.TestCase):
    def test_helper_recognizes_only_x_sources(self):
        self.assertTrue(image_preview.is_x_source("x:1", {"url": ""}))
        self.assertTrue(image_preview.is_x_source("x:9", {"url": X_URL}))
        self.assertFalse(image_preview.is_x_source("bilibili:2", {"url": BILI_URL}))

    def test_bilibili_image_is_diagnosed_but_never_eligible(self):
        corpus, data = _fixture()
        media = {
            "x:1": ["https://pbs.twimg.com/media/x1.jpg"],
            "bilibili:2": ["http://i0.hdslb.com/bfs/new_dyn/b.jpg"],
        }
        media_stats = {"files": 1, "lines": 2, "bad_lines": 0,
                       "image_tweets": 2, "images": 2, "video_only_tweets": 0}
        with mock.patch.object(image_preview, "load_media",
                               return_value=({k: list(v) for k, v in media.items()},
                                             dict(media_stats))), \
             mock.patch.object(image_preview.media_backfill, "load_sidecar",
                               return_value={"entries": {}}), \
             mock.patch.object(image_preview, "read_json",
                               return_value={"deleted_items": []}):
            payload, _ = image_preview.build_preview(RULES, data, corpus)

        eligible_keys = [e["tweet_key"] for e in payload["eligible"]]
        self.assertEqual(eligible_keys, ["x:1"])
        self.assertEqual(payload["rule"]["source_scope"], "x")
        self.assertEqual(payload["stats"]["non_x_image_tweets_skipped"], 1)
        self.assertEqual(payload["stats"]["non_x_images_skipped"], 1)

        diagnostics = {row["key"]: row for row in payload["diagnostics"]}
        bili = diagnostics["bilibili:2"]
        self.assertIn("非 X 原推", bili["reason"])
        self.assertEqual(bili["images"], 0)
        self.assertEqual(bili["raw_images"], 1)
        self.assertNotIn("i0.hdslb.com",
                         " ".join(str(e["images"]) for e in payload["eligible"]))


if __name__ == "__main__":
    unittest.main()
