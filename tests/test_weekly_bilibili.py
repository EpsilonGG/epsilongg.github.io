"""周报第四展示栏「B站动态」的回归（2026-11-12 用户裁决）。

守住四条不能悄悄坏掉的口径：

* 第四栏是**展示层**新增的一个值，归栏三值不动，前三栏顺序不动；
* B 站正本走只读旁路：`source_refs` / `candidates` / `daily_rows` 一个键都不加，
  所以作品情报、业界动向与历史回测逐字不变；
* B 站行参与 `game_routing.new_work_labels()` 的**同一份**游戏级「新作」过滤：
  命中的游戏整组上提第一栏，其余留第四栏；没有作品名的绝不掉进「未标注作品」
  默认排除池；
* 每条正文只留一条 `[发布者](B站原文)` 链接，裸 URL 全部剥掉。
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
WEEKLY_DIR = ROOT / "weekly"
# 与 test_weekly_game_routing.py 同样按文件路径挂别名：`unittest discover -s tests`
# 会把 scripts/ 插到 sys.path 前面，直接 `import weekly` 会拿到 scripts/weekly/ 旧包。
ALIAS = "_weekly_root_pipeline"
if ALIAS not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        ALIAS, WEEKLY_DIR / "__init__.py",
        submodule_search_locations=[str(WEEKLY_DIR)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = package
    spec.loader.exec_module(package)

bili = importlib.import_module(ALIAS + ".bilibili")
config = importlib.import_module(ALIAS + ".config")
render = importlib.import_module(ALIAS + ".render")
editor = importlib.import_module(ALIAS + ".editor")
highlight = importlib.import_module(ALIAS + ".highlight")
gr = importlib.import_module(ALIAS + ".game_routing")
RULES = config.load_rules()

PUBLISHER = "HOOKSOFT公式"
URL = "https://www.bilibili.com/opus/1265219746759966722"


def _record(key: str, content: str, url: str = URL,
            publisher: str = PUBLISHER) -> str:
    return json.dumps({
        "identity_key": key,
        "source_id": "bilibili",
        "item_id": key.split(":", 1)[-1],
        "content": content,
        "publisher": publisher,
        "canonical_url": url,
        "published_at": "2026-11-10T05:45:15+00:00",
        "metadata": {"account": "bili_3632310624717268",
                     "uid": "3632310624717268", "tag": "B站Gal"},
    }, ensure_ascii=False)


def _corpus(rows: list[dict]) -> dict:
    """build_lines() 能吃的最小语料形状（attach() 的输出）。"""
    return {"issues": ["261110-g"], "bilibili": rows, "titles": [],
            "source_refs": {}, "candidates": [], "daily_rows": []}


def _row(key: str, content: str, url: str = URL) -> dict:
    return {"key": key, "day": "2026-11-10", "url": url, "content": content,
            "publisher": PUBLISHER, "handle": "bili_3632310624717268",
            "published_at": "2026-11-10T05:45:15+00:00",
            "source_file": "data/bilibili/galgame/2026-11-10.jsonl"}


class ColumnConfigTests(unittest.TestCase):
    def test_four_display_columns_with_bilibili_last(self):
        self.assertEqual(tuple(config.DISPLAY_COLUMNS),
                         ("新作", "作品情报", "业界动向", "B站动态"))
        self.assertEqual(config.BILI_VIEW, "B站动态")
        self.assertEqual((config.NEW, config.WORK_VIEW, config.INDUSTRY_VIEW),
                         ("新作", "作品情报", "业界动向"))

    def test_evidence_columns_are_untouched(self):
        self.assertEqual(tuple(config.COLUMNS),
                         ("作品情报", "品牌动向", "业界动向"))

    def test_rules_carry_the_second_source_config(self):
        cfg = RULES["bilibili"]
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["source_dir"], "data/bilibili/galgame")
        self.assertEqual(cfg["no_game_label"], "动态")
        self.assertNotEqual(cfg["no_game_label"], gr.NO_GAME)
        self.assertEqual(config.BILIBILI, ROOT / "data" / "bilibili" / "galgame")


class CleanTextTests(unittest.TestCase):
    def test_bare_urls_newlines_and_spaces_are_removed(self):
        text = "第一行 https://t.co/abc?x=1\n第二行  https://www.bilibili.com/opus/1  继续"
        out = bili.clean_text(text, set(), RULES["brackets"])
        self.assertNotIn("http://", out)
        self.assertNotIn("https://", out)
        self.assertNotIn("\n", out)
        self.assertIn("第一行", out)
        self.assertIn("继续", out)
        self.assertNotIn("  ", out)

    def test_bracket_normalization_is_idempotent(self):
        text = "《一夜之后》与『Sugar*Style』的「角色」介绍"
        once = bili.clean_text(text, {"一夜之后"}, RULES["brackets"])
        twice = bili.clean_text(once, {"一夜之后"}, RULES["brackets"])
        self.assertEqual(once, twice)
        self.assertIn("『一夜之后』", once)

    def test_read_json_line_only_accepts_objects(self):
        self.assertEqual(bili.read_json_line("[1, 2]"), {})
        self.assertEqual(bili.read_json_line("42"), {})
        with self.assertRaises(json.JSONDecodeError):
            bili.read_json_line("{not json")


class AttachIsolationTests(unittest.TestCase):
    def _attached(self, lines: list[str]):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "2026-11-10.jsonl").write_text(
                "\n".join(lines) + "\n", encoding="utf-8")
            # 261110-g 的覆盖日就是 2026-11-10，缺文件的日子直接跳过。
            with mock.patch.object(bili, "BILIBILI", folder):
                return bili.attach({
                    "issues": ["261110-g", "261109-g"],
                    "source_refs": {"x:1": {"url": "https://x.com/a/status/1"}},
                    "candidates": [{"key": "x:1"}],
                    "daily_rows": [{"key": "x:1"}],
                    "stats": {"items": 1},
                }, RULES)

    def test_source_index_and_x_side_rows_are_byte_identical(self):
        payload = self._attached([_record("bilibili:1", "『X』发售日期公布")])
        self.assertIsNotNone(payload)
        self.assertEqual(set(payload["source_refs"]), {"x:1"})
        self.assertEqual(payload["candidates"], [{"key": "x:1"}])
        self.assertEqual(payload["daily_rows"], [{"key": "x:1"}])
        self.assertEqual(payload["stats"]["items"], 1)
        self.assertEqual(payload["stats"]["bilibili_rows"], 1)
        self.assertEqual(payload["bilibili"][0]["source_file"],
                         "data/bilibili/galgame/2026-11-10.jsonl")
        self.assertEqual(payload["bilibili_refs"]["bilibili:1"]["origin"], "bilibili")

    def test_bad_lines_duplicates_and_foreign_keys_are_dropped(self):
        payload = self._attached([
            "", "{oops", "[1, 2]", "{}",
            _record("bilibili:1", "第一条"),
            _record("bilibili:1", "重复的同一条"),
            _record("x:1", "这不是 B 站动态"),
            _record("bilibili:2", "第二条", url=""),
        ])
        self.assertEqual([r["key"] for r in payload["bilibili"]], ["bilibili:1"])
        self.assertEqual(payload["bilibili"][0]["content"], "第一条")
        self.assertEqual(set(payload["bilibili_refs"]), {"bilibili:1"})

    def test_disabled_config_returns_no_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "2026-11-10.jsonl").write_text(
                _record("bilibili:1", "一条") + "\n", encoding="utf-8")
            with mock.patch.object(bili, "BILIBILI", folder):
                payload = bili.attach(
                    {"issues": ["261110-g"], "stats": {}},
                    dict(RULES, bilibili={**RULES["bilibili"], "enabled": False}))
        self.assertEqual(payload["bilibili"], [])
        self.assertEqual(payload["bilibili_refs"], {})
        self.assertEqual(payload["stats"]["bilibili_rows"], 0)

    def test_source_files_dedupes_the_same_covered_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "2026-11-10.jsonl").write_text("", encoding="utf-8")
            with mock.patch.object(bili, "BILIBILI", folder):
                files = bili.source_files(["261110-g", "261110-g2", "261109-g"])
        self.assertEqual([day for day, _ in files], ["2026-11-10"])


class GameLevelRoutingTests(unittest.TestCase):
    def _lines(self, *texts: str) -> list[dict]:
        return bili.build_lines(_corpus([
            _row(f"bilibili:{i}", text) for i, text in enumerate(texts)
        ]), RULES)

    def test_new_work_signal_lifts_the_whole_game(self):
        lines = self._lines(
            "『X』发售日期公布，12 月 25 日发售",
            "『X』公布了一段角色介绍",
            "『Y』Switch 版促销最后一天",
        )
        by_key = {x["key"]: x for x in lines}
        self.assertEqual(by_key["bilibili:0"]["column"], config.NEW)
        self.assertEqual(by_key["bilibili:1"]["column"], config.NEW)  # 整组上提
        self.assertEqual(by_key["bilibili:2"]["column"], config.BILI_VIEW)
        self.assertEqual(by_key["bilibili:0"]["glabel"], "『X』")

    def test_cg_alone_is_not_a_new_work_but_cg_with_news_is(self):
        lines = bili.build_lines(_corpus([
            _row("bilibili:0", "『Z』公开新CG"),
            _row("bilibili:1", "『W』公开新CG"),
            _row("bilibili:2", "『W』角色介绍公开"),
        ]), RULES)
        by_key = {x["key"]: x for x in lines}
        self.assertEqual(by_key["bilibili:0"]["column"], config.BILI_VIEW)
        self.assertEqual(by_key["bilibili:1"]["column"], config.NEW)
        self.assertEqual(by_key["bilibili:2"]["column"], config.NEW)

    def test_no_game_rows_never_become_new_work_and_keep_a_safe_label(self):
        lines = bili.build_lines(_corpus([
            _row("bilibili:0", "【通知】秋叶原活动照常举行 " + URL),
        ]), RULES)
        self.assertEqual(len(lines), 1)
        row = lines[0]
        self.assertEqual(row["column"], config.BILI_VIEW)
        self.assertEqual(row["glabel"], RULES["bilibili"]["no_game_label"])
        self.assertNotEqual(row["glabel"], gr.NO_GAME)
        self.assertEqual(row["group_label"], gr.NO_GAME)

    def test_every_row_has_one_publisher_link_and_no_bare_url(self):
        lines = bili.build_lines(_corpus([
            _row("bilibili:0", "『X』发售日期公布 " + URL + " 详情"),
            _row("bilibili:1", "普通通知 https://t.co/abc 结束"),
        ]), RULES)
        for row in lines:
            with self.subTest(key=row["key"]):
                self.assertIn(row["column"], (config.NEW, config.BILI_VIEW))
                self.assertTrue(row["text"].startswith("- [" + PUBLISHER + "](" + URL + ")："))
                self.assertEqual(row["text"].count("http"), 1)
                self.assertTrue(row["brand"].startswith("B站 · "))
                self.assertFalse(row["official"])

    def test_disabled_or_three_column_layout_returns_no_rows(self):
        corpus = _corpus([_row("bilibili:0", "『X』发售日期公布")])
        self.assertEqual(bili.build_lines(corpus, dict(
            RULES, bilibili={**RULES["bilibili"], "enabled": False})), [])
        with mock.patch.object(bili, "BILI_VIEW", ""):
            self.assertEqual(bili.build_lines(corpus, RULES), [])


class RenderAndEditorTests(unittest.TestCase):
    def _data(self, lines: list[dict]) -> dict:
        return {"title": "Galgame 周报", "stage": "测试", "lead": "导语",
                "sections": [], "bilibili_lines": lines, "format": {}}

    def test_render_writes_only_the_columns_that_have_rows(self):
        lines = bili.build_lines(_corpus([
            _row("bilibili:0", "『X』发售日期公布"),
            _row("bilibili:1", "普通通知"),
        ]), RULES)
        md = render.render_markdown(self._data(lines), {})
        self.assertIn("## 新作", md)
        self.assertIn("## B站动态", md)
        self.assertIn("### B站 · " + PUBLISHER, md)
        self.assertIn("#### 动态", md)
        self.assertNotIn("## 作品情报", md)
        self.assertNotIn("## 业界动向", md)
        self.assertTrue(md.index("## 新作") < md.index("## B站动态"))

    def test_deleting_a_bilibili_row_removes_its_column(self):
        lines = bili.build_lines(_corpus([
            _row("bilibili:0", "『X』发售日期公布"),
        ]), RULES)
        md = render.render_markdown(
            self._data(lines), {"deleted_items": ["bilibili:0"]})
        self.assertNotIn("## 新作", md)
        self.assertNotIn(URL, md)

    def test_filter_page_js_reads_the_same_bilibili_lines(self):
        self.assertIn("DATA.bilibili_lines", editor._JS)

    def test_material_lists_the_second_source_without_merging_it(self):
        corpus = _corpus([_row("bilibili:0", "一条")])
        text = "\n".join(bili.material_lines(corpus))
        self.assertIn("## 十、B 站动态正本", text)
        self.assertIn("bilibili:0", text)
        self.assertIn(URL, text)
        self.assertIn("互不合并", text)
        self.assertIn("本期窗口内没有 B 站动态正本",
                      "\n".join(bili.material_lines(_corpus([]))))


class HighlightTests(unittest.TestCase):
    """B 站组进了「新作」，但不能把 X 侧头条挤出 ≤70 字的亮点句。"""

    @staticmethod
    def _md() -> str:
        lines = ["## 新作", "", "### B站 · " + PUBLISHER, "", "#### 『一夜之后』", ""]
        lines += [f"- [{PUBLISHER}]({URL})：促销消息 {i}" for i in range(5)]
        lines += ["", "### AMUSE CRAFT", "", "#### 『X』", "",
                  "- 『X』明天包装版发售，秋叶原办免费配布会", "",
                  "## B站动态", "", "### B站 · " + PUBLISHER, "", "#### 动态", "",
                  f"- [{PUBLISHER}]({URL})：普通通知", ""]
        return "\n".join(lines)

    def test_bilibili_groups_are_not_used_as_highlight_subjects(self):
        md = self._md()
        text = highlight.build(md, {"brands": 2, "items": 7}, ["新作", "B站动态"])
        self.assertNotIn("B站 · ", text)
        self.assertIn("AMUSE CRAFT", text)
        self.assertLessEqual(len(text), highlight.LIMIT)

    def test_bilibili_rows_still_count_toward_the_column_total(self):
        text = highlight.build(self._md(), {"brands": 2, "items": 7},
                               ["新作", "B站动态"])
        self.assertIn("新作 6 条", text)

    def test_brand_prefix_comes_from_rules_not_a_second_hardcoded_copy(self):
        self.assertEqual(highlight.bili_brand_prefix(),
                         RULES["bilibili"]["brand_prefix"])

    def test_toc_includes_the_fourth_column(self):
        toc = highlight.build_toc(self._md())
        self.assertEqual([x["label"] for x in toc], ["新作", "B站动态"])
        self.assertEqual([x["id"] for x in toc], ["section-1", "section-2"])


if __name__ == "__main__":
    unittest.main()
