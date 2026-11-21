"""周报条目末尾原文链接的回归（2026-11-21 裁决）。

* 单来源写 `[原文](url)`，多来源依次编号，URL 逐字取 `sources[].url`；
* 链接必须真的出现在 render.collect() 的成稿行尾，且不影响插图匹配；
* HTML 里这类链接要带 `weekly-source` 小号样式。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEEKLY_DIR = ROOT / "weekly"
ALIAS = "_weekly_root_source_links"
if ALIAS not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        ALIAS, WEEKLY_DIR / "__init__.py",
        submodule_search_locations=[str(WEEKLY_DIR)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = package
    spec.loader.exec_module(package)

render = importlib.import_module(ALIAS + ".render")
draft_export = importlib.import_module(ALIAS + ".draft_export")
config = importlib.import_module(ALIAS + ".config")

U1 = "https://x.com/yuzusoft/status/1"
U2 = "https://www.bilibili.com/opus/2"
GAME = "『LimeLightLemonadeJam（暂译）』"


class SourceLinkTextTests(unittest.TestCase):
    def test_single_source(self):
        item = {"sources": [{"url": U1}]}
        self.assertEqual(render.source_links(item), f" [原文]({U1})")

    def test_multiple_sources_are_numbered_and_deduped(self):
        item = {"sources": [{"url": U1}, {"url": U2}, {"url": U1}]}
        self.assertEqual(render.source_links(item),
                         f" [原文1]({U1}) [原文2]({U2})")

    def test_missing_url_adds_nothing(self):
        self.assertEqual(render.source_links({"sources": [{"url": ""}]}), "")


class DraftLineTests(unittest.TestCase):
    def test_collected_line_ends_with_source_link(self):
        data = {
            "title": "Galgame 周报", "stage": "测试", "lead": "导语",
            "sections": [{
                "key": "s:1", "label": "ゆずソフト", "column": config.WORK,
                "items": [{
                    "key": "i:1", "sentence": "柚子社新作确定多语版",
                    "group_key": "g:1", "group_label": GAME,
                    "display_column": config.WORK,
                    "subject_prefix": "", "prefix_md": "", "is_official": True,
                    "sources": [{"url": U1}, {"url": U2}],
                }],
            }],
            "bilibili_lines": [],
        }
        decisions = {"section_order": ["s:1"], "item_order": {"s:1": ["i:1"]},
                     "deleted_items": []}
        lines = render.collect(data, decisions)["brands"][config.WORK]["ゆずソフト"]["g:1"]["lines"]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0]["text"].endswith(f" [原文1]({U1}) [原文2]({U2})"))

    def test_image_match_strips_source_tail(self):
        body = f"柚子社新作确定多语版 [原文1]({U1}) [原文2]({U2})"
        self.assertEqual(draft_export._SOURCE_TAIL.sub("", body),
                         "柚子社新作确定多语版")


class HtmlStyleTests(unittest.TestCase):
    def test_source_link_gets_small_style_class(self):
        html = draft_export._inline(f"正文 [原文]({U1})")
        self.assertIn('class="weekly-source"', html)
        self.assertIn(f'href="{U1}"', html)

    def test_other_links_keep_normal_style(self):
        html = draft_export._inline(f"[@someone]({U1})")
        self.assertNotIn("weekly-source", html)


if __name__ == "__main__":
    unittest.main()
