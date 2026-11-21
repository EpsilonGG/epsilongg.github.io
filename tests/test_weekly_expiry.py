"""过期贩售判据的回归（2026-11-21 裁决，2026-11-22 提到周报级）。

用户原话：「贩卖消息在周报开始形成若已过期（即贩卖结束）则删去那条贩卖信息」。
原先只做在 B 站行上，X 侧照样留着「后日通贩 11/16 截止」这类已经失效的消息。
这里钉住五条边界：
* 写明结束日且已过 → 删；
* 结束日在未来 / 没有结束日 → 留（无法证明已结束就不猜）；
* 结果通报（完成抽奖、已通知中奖）→ 留；
* 另一句有未来发售 → 留并写明理由；
* 同一句里的「某作特典截止提醒」不算未来发售豁免。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from datetime import date
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

expiry = importlib.import_module(ALIAS + ".expiry")
config = importlib.import_module(ALIAS + ".config")

RULES = config.load_rules()
CFG = RULES["expiry"]
TODAY = date(2026, 11, 22)


def _hit(text: str, anchor: date | None = None) -> dict | None:
    return expiry.find_expired(text, TODAY, anchor or TODAY, CFG)


class ExpiredSaleTests(unittest.TestCase):
    def test_rules_block_is_wired(self):
        self.assertTrue(CFG["enabled"])
        self.assertTrue(CFG["keep_if_result_report"])
        self.assertTrue(CFG["keep_if_future_release"])
        self.assertIn("成形日", CFG["basis"])

    def test_expired_with_explicit_end_is_dropped(self):
        cases = (
            ("提醒『as:9-nine-ARTEISIA Café』后日通贩 11/16 23:59 截止。", date(2026, 11, 16)),
            ("公开『Karanoshojo Complete Box』黑胶封套草图，预约到 11/16 截止。", date(2026, 11, 15)),
            ("旗下CS版作品下载版促销最高七折，活动持续至11月20日。", date(2026, 11, 17)),
            ("促销 11月1日まで，限定特卖", date(2026, 11, 1)),
            ("限定通贩到 15 日 24 时", date(2026, 11, 15)),
        )
        for text, anchor in cases:
            with self.subTest(text=text):
                hit = _hit(text, anchor)
                self.assertIsNotNone(hit)
                self.assertTrue(hit["drop"], hit)

    def test_future_or_missing_end_is_kept(self):
        cases = (
            "促销 11月30日まで，限定特卖",
            "任天堂 eShop 十一月促销开跑，旗下作品最多七折，到 25 日。",
            "『君色パトラIF』BOOTH 版受注到29日",
            "白舟黑五特卖来袭！12/2日为止！",
            "『近月少女的礼仪2』国际中文版现正于 Steam 促销热卖中！仅需52元即可入手！",
            "感谢粉丝购入BOOTH通贩挂画与徽章",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertIsNone(_hit(text, date(2026, 11, 20)))

    def test_result_report_is_kept(self):
        text = "为11月9日截止的两项赠品活动完成抽奖，已通过私信与邮件通知中奖者。"
        self.assertIsNone(_hit(text, date(2026, 11, 17)))

    def test_campaign_deadline_and_relative_deadline(self):
        # 应援活动也算贩售（购买向的 campaign）；「今晚二十四点」按发推当天算截止。
        for text, anchor in (
            ("『女装百合嵐』盒装版应援活动到 15 日 24 时，还晒了历代伪娘角色", date(2026, 11, 15)),
            ("『女装百合嵐』包装版应援活动到今晚二十四点，另晒出历代女装角色图。", date(2026, 11, 15)),
        ):
            with self.subTest(text=text):
                hit = _hit(text, anchor)
                self.assertIsNotNone(hit)
                self.assertTrue(hit["drop"], hit)

    def test_relative_deadline_tomorrow_is_still_valid(self):
        self.assertIsNone(_hit("受注到明日二十四点", date(2026, 11, 21)))

    def test_future_release_in_another_sentence_keeps_the_item(self):
        hit = _hit("预约到11/16截止。另公布新作将于12月25日发售。", date(2026, 11, 15))
        self.assertIsNotNone(hit)
        self.assertFalse(hit["drop"])
        self.assertIn("未来发售", hit["why"])

    def test_same_sentence_release_reference_does_not_exempt(self):
        # 「11/27 发售作的特典提醒」——未来发售只是定语，这条仍然是过期特典。
        text = "转发了 11/27 发售作的原画特典截止提醒，数量将在 11/16 定下。"
        self.assertIsNone(_hit(text, date(2026, 11, 15)))

    def test_month_rolls_over_when_only_day_is_written(self):
        # 12/28 发推说「到 5 日」，指的是明年 1 月 5 日，不是 12 月 5 日。
        hit = _hit("通贩到 5 日截止", date(2026, 12, 28))
        self.assertTrue(hit is None or not hit["drop"])

    def test_year_rolls_over(self):
        # 12 月发推写「1月10日まで」，指的是明年 1 月 10 日（相对今天已过 → 删）。
        hit = _hit("特卖 1月10日まで", date(2025, 12, 20))
        self.assertIsNotNone(hit)
        self.assertEqual(hit["end"], "2026-01-10")
        self.assertTrue(hit["drop"])

    def test_disabled_returns_nothing(self):
        self.assertIsNone(expiry.find_expired(
            "促销 11月1日まで", TODAY, TODAY, {"enabled": False}))


if __name__ == "__main__":
    unittest.main()
