"""周报「新作」投放判定与「作品情报」品牌排序的回归（2026-11-12 用户裁决）。

三条不能悄悄坏掉的口径：
* 发售日期确定 / 公布 是新的投放条件（含不带裸「发售日」的说法）；
* 公开新CG **只在当期该游戏还有其它消息时**才算，单独一条 CG 不提栏；
* 「作品情报」栏的品牌顺序与「新作」栏共用同一份 rank，品牌动向派生的大单元
  不再被整段压到栏尾（梯队 1 品牌不能排在梯队 3 之后）。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEEKLY_DIR = ROOT / "weekly"
# 仓库里有两个 weekly 包：根目录的正式版管线，和 scripts/weekly/（旧版）。
# `unittest discover -s tests` 会把 scripts/ 插到 sys.path 前面，直接 `import weekly`
# 会拿到旧包，所以按文件路径把根包挂到独立别名下再取子模块。
ALIAS = "_weekly_root_pipeline"
if ALIAS not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        ALIAS, WEEKLY_DIR / "__init__.py",
        submodule_search_locations=[str(WEEKLY_DIR)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = package
    spec.loader.exec_module(package)

gr = importlib.import_module(ALIAS + ".game_routing")
config = importlib.import_module(ALIAS + ".config")
pipeline = importlib.import_module(ALIAS + ".pipeline")
INDUSTRY, MOVEMENT, WORK = config.INDUSTRY, config.MOVEMENT, config.WORK
section_sort_key = pipeline.section_sort_key
CFG = config.load_rules()["game_routing"]


def _sections(*rows: tuple[str, str], column: str = WORK) -> list[dict]:
    """[(游戏组, 正文)] → new_work_labels() 能吃的最小 sections 形状。"""
    return [{
        "column": column,
        "items": [{"group_label": game, "sentence": text} for game, text in rows],
    }]


class NewWorkSignalTests(unittest.TestCase):
    def test_rules_carry_the_two_new_conditions(self):
        self.assertIn("发售日期公布", CFG["signals"])
        self.assertIn("新CG公开", CFG["signals"])
        self.assertEqual(CFG["conditional_signals"], ["新CG公开"])

    def test_release_date_announcement_labels_game(self):
        cases = (
            "『X』発売日が決定しました",
            "『X』发售日期公布为 12 月 25 日",
            "『X』リリース日決定",  # 定档信号不含「发售日」，靠新信号补上
            "『X』发售日决定，同时开放预约",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    gr.new_work_labels(_sections(("『X』", text)), CFG),
                    {"『X』"},
                )

    def test_release_date_retrospective_is_still_dropped(self):
        labels = gr.new_work_labels(
            _sections(("『X』", "回顾 23 年前发售日决定，顺带聊了旧作")), CFG)
        self.assertEqual(labels, set())

    def test_cg_alone_does_not_label_game(self):
        for text in ("『X』公开新CG", "『X』新規CG公開", "『X』CG解禁"):
            with self.subTest(text=text):
                self.assertEqual(
                    gr.new_work_labels(_sections(("『X』", text)), CFG), set())

    def test_cg_with_other_news_labels_game(self):
        labels = gr.new_work_labels(_sections(
            ("『X』", "『X』公开新CG"),
            ("『X』", "『X』公布了一段角色介绍"),
        ), CFG)
        self.assertEqual(labels, {"『X』"})

    def test_two_cg_only_rows_still_do_not_label_game(self):
        labels = gr.new_work_labels(_sections(
            ("『X』", "『X』公开新CG"),
            ("『X』", "『X』新規CG公開"),
        ), CFG)
        self.assertEqual(labels, set())

    def test_other_game_does_not_open_the_gate(self):
        labels = gr.new_work_labels(_sections(
            ("『X』", "『X』公开新CG"),
            ("『Y』", "『Y』角色介绍公开"),
        ), CFG)
        self.assertEqual(labels, set())

    def test_conditional_gate_does_not_affect_other_signals(self):
        labels = gr.new_work_labels(
            _sections(("『X』", "『X』体验版公开")), CFG)
        self.assertEqual(labels, {"『X』"})

    def test_preview_signals_match_the_draft_verdict(self):
        rows = _sections(
            ("『X』", "『X』公开新CG"),
            ("『X』", "『X』角色介绍公开"),
        )[0]["items"]
        self.assertIn("新CG公开", gr.game_signals(rows, CFG))
        self.assertIn("『X』", gr.new_work_labels([{"column": WORK, "items": rows}], CFG))
        only_cg = _sections(("『X』", "『X』公开新CG"))[0]["items"]
        self.assertEqual(gr.game_signals(only_cg, CFG), [])

    def test_manual_source_ignores_auto_signals(self):
        cfg = dict(CFG, label_source="manual")
        self.assertEqual(gr.new_work_labels(
            _sections(("『X』", "『X』発売日が決定しました")), cfg), set())


class SectionOrderTests(unittest.TestCase):
    @staticmethod
    def _sec(column: str, label: str, rank: tuple) -> dict:
        return {"column": column, "label": label, "rank": rank}

    def test_work_view_uses_the_same_rank_as_new_column(self):
        sections = [
            self._sec(WORK, "Zzz", (3, 0, -1, "Zzz")),
            self._sec(MOVEMENT, "ぱれっと", (1, 8, -2, "ぱれっと")),
            self._sec(WORK, "Key", (1, 1, -2, "Key")),
            self._sec(MOVEMENT, "ALICESOFT", (2, 16, -2, "ALICESOFT")),
            self._sec(INDUSTRY, "业界号", (0, 0, -9, "业界号")),
        ]
        ordered = [s["label"] for s in sorted(sections, key=section_sort_key)]
        self.assertEqual(ordered, ["Key", "ぱれっと", "ALICESOFT", "Zzz", "业界号"])

    def test_relative_order_of_work_sections_is_unchanged(self):
        work = [
            self._sec(WORK, "Zzz", (3, 0, -1, "Zzz")),
            self._sec(WORK, "Key", (1, 1, -2, "Key")),
            self._sec(WORK, "HOOKSOFT", (2, 0, -3, "HOOKSOFT")),
        ]
        old = [s["label"] for s in sorted(
            work, key=lambda s: ({"作品情报": 0, "品牌动向": 1, "业界动向": 2}[s["column"]],
                                 s["rank"], s["label"]))]
        new = [s["label"] for s in sorted(work, key=section_sort_key)]
        self.assertEqual(new, old)

    def test_industry_always_sinks_to_the_bottom(self):
        sections = [
            self._sec(INDUSTRY, "业界号", (0, 0, -99, "业界号")),
            self._sec(WORK, "Key", (1, 1, -1, "Key")),
        ]
        self.assertEqual([s["label"] for s in sorted(sections, key=section_sort_key)],
                         ["Key", "业界号"])


if __name__ == "__main__":
    unittest.main()
