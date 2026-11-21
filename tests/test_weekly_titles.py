"""作品名别名表的回归（2026-11-21 用户裁决前自查发现）。

背景：同一个作品被拆成多个小标题时，条目会分散到不同栏目。
vol_002 里『ライムライト・レモネードジャム』（X 原推）、
『LimeLight Lemonade Jam（暂译）』（DLsite B 站）与
『LimelightLemonadeJam』（柚子社official B 站）三条同指一作，
后者因此留在「作品情报」而前两者在「新作」。

两条口径不能悄悄坏掉：
* `canonical_aliases` 登记的目标名优先作为显示名（不按标题长度猜）；
* 已登记的别名必须真的并到同一个 canonical。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEEKLY_DIR = ROOT / "weekly"
ALIAS = "_weekly_root_pipeline"
if ALIAS not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        ALIAS, WEEKLY_DIR / "__init__.py",
        submodule_search_locations=[str(WEEKLY_DIR)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = package
    spec.loader.exec_module(package)

titles_mod = importlib.import_module(ALIAS + ".titles")
config = importlib.import_module(ALIAS + ".config")
RULES = config.load_rules()


def _normalizer(*names: str):
    return titles_mod.TitleNormalizer(list(names), RULES)


class AliasMergeTests(unittest.TestCase):
    def test_latin_and_japanese_titles_of_same_work_merge(self):
        n = _normalizer(
            "LimeLight Lemonade Jam（暂译）",
            "ライムライト・レモネードジャム",
            "Limelight Lemonade Jam",
        )
        for name in ("LimeLight Lemonade Jam（暂译）",
                     "ライムライト・レモネードジャム",
                     "Limelight Lemonade Jam"):
            self.assertEqual(n.canonical(name), "ライムライト・レモネードジャム", name)

    def test_alias_target_wins_display_even_when_shorter(self):
        """旧逻辑按长度选根，拉丁长名会顶掉日文官方名；登记值必须优先。"""
        n = _normalizer(
            "LimeLight Lemonade Jam（暂译）",
            "ライムライト・レモネードジャム",
        )
        self.assertEqual(n.canonical("ライムライト・レモネードジャム"),
                         "ライムライト・レモネードジャム")

    def test_variant_character_alias(self):
        n = _normalizer("虚妄爱丽丝-歧梦重缘-", "虚妄爱丽丝 -岐梦重缘-")
        self.assertEqual(n.canonical("虚妄爱丽丝-歧梦重缘-"),
                         n.canonical("虚妄爱丽丝 -岐梦重缘-"))

    def test_prefix_rule_still_merges_subtitles(self):
        """人工别名不能影响原有的波浪号/副标题合并（② 号规则）。"""
        n = _normalizer("ハピメア", "ハピメア～副題～")
        self.assertEqual(n.canonical("ハピメア～副題～"), n.canonical("ハピメア"))

    def test_distinct_works_are_not_merged(self):
        n = _normalizer("近月少女的礼仪", "近月少女的礼仪2")
        self.assertNotEqual(n.canonical("近月少女的礼仪"),
                            n.canonical("近月少女的礼仪2"))

    def test_alias_table_is_documented(self):
        """新增别名必须同步 alias_note，否则下一个人不知道依据。"""
        cfg = RULES["title_merge"]
        note = cfg.get("alias_note") or ""
        self.assertIn("ライムライト", note)
        self.assertIn("虚妄爱丽丝", note)


if __name__ == "__main__":
    unittest.main()
