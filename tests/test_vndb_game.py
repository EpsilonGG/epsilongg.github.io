"""`scripts/vndb_game.py` 的纯函数测试（不联网）。

这些用例守的是几个「看起来对、写出来错」的坑，每个都真踩过：

* 体验版不能当首发 —— VNDB 上《樱之诗》的第一次发售是 2008 年的体验版，
  照它写脚注会变成「2008 年发售、全年龄」，实际是 2015-10-23、18 禁；
* 全拉丁标题保持原名 —— 《ATRI -My Dear Moments-》有官方中文名「亚托莉」，
  但站内一直用原名，不能因为查到了中文名就替换；
* 日期只到年或月时要少写几段 —— VNDB 的 `released` 可能是 `2017` 或 `2017-12`；
* 厂牌带括号时不再空一格 —— 「Azurite（发行：DiGination）于 …」不是「） 于」。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import vndb_game as vg  # noqa: E402


def make_vn(**over) -> dict:
    vn = {
        "id": "v562",
        "title": "Sakura no Uta",
        "alttitle": "サクラノ詩－櫻の森の上を舞う－",
        "titles": [
            {"lang": "ja", "title": "サクラノ詩－櫻の森の上を舞う－"},
            {"lang": "zh-Hans", "title": "樱之诗 −于樱之森上飞舞−"},
        ],
        "released": "2015-10-23",
        "developers": [{"id": "p259", "name": "Makura", "original": "枕"}],
        "platforms": ["win"],
    }
    vn.update(over)
    return vn


def make_release(**over) -> dict:
    rel = {
        "id": "r10022",
        "released": "2015-10-23",
        "platforms": ["win"],
        "minage": 18,
        "has_ero": True,
        "official": True,
        "patch": False,
        "freeware": False,
        "vns": [{"id": "v562", "rtype": "complete"}],
        "producers": [{"name": "Makura", "original": "枕", "developer": True, "publisher": False}],
    }
    rel.update(over)
    return rel


class NormTest(unittest.TestCase):
    def test_全半角与波浪线不影响匹配(self):
        self.assertEqual(vg.norm("FORTUNE×WORLD～僕らが"), vg.norm("fortune×world~僕らが"))

    def test_空格和标点被忽略(self):
        self.assertEqual(vg.norm("金色ラブリッチェ"), vg.norm("金色ラブリッチェ "))


class ReleasePickTest(unittest.TestCase):
    def test_体验版不算首发(self):
        trial = make_release(
            id="r1160", released="2008-09-26", minage=0, has_ero=False,
            vns=[{"id": "v562", "rtype": "trial"}],
        )
        chosen = vg.pick_release(make_vn(), [trial, make_release()])
        self.assertEqual(chosen["id"], "r10022")

    def test_非官方版与补丁不算(self):
        port = make_release(id="r82144", official=False)
        patch = make_release(id="r99999", patch=True)
        chosen = vg.pick_release(make_vn(), [port, patch, make_release()])
        self.assertEqual(chosen["id"], "r10022")

    def test_同一天优先PC版(self):
        console = make_release(id="r67702", platforms=["ps4"], has_ero=False, minage=17)
        chosen = vg.pick_release(make_vn(), [console, make_release()])
        self.assertEqual(chosen["id"], "r10022")

    def test_没有正式版时返回None(self):
        trial = make_release(vns=[{"id": "v562", "rtype": "trial"}])
        self.assertIsNone(vg.pick_release(make_vn(), [trial]))


class DateTest(unittest.TestCase):
    def test_完整日期(self):
        self.assertEqual(vg.fmt_date("2017-12-22"), "2017 年 12 月 22 日")

    def test_只有年月(self):
        self.assertEqual(vg.fmt_date("2017-12"), "2017 年 12 月")

    def test_只有年(self):
        self.assertEqual(vg.fmt_date("2017"), "2017 年")

    def test_未定(self):
        self.assertEqual(vg.fmt_date("TBA"), "未定")
        self.assertEqual(vg.fmt_date(None), "未定")


class FootnoteTest(unittest.TestCase):
    def test_中文名优先(self):
        rec = vg.build_record(make_vn(), [make_release()])
        self.assertEqual(
            vg.footnote(rec),
            "《樱之诗 −于樱之森上飞舞−》。枕 于 2015 年 10 月 23 日发售的 18 禁 PC 游戏。",
        )

    def test_全拉丁标题保持原名(self):
        vn = make_vn(
            id="v27448",
            title="ATRI -My Dear Moments-",
            alttitle="ATRI -My Dear Moments-",
            titles=[{"lang": "zh-Hans", "title": "亚托莉 -我挚爱的时光-"}],
            released="2020-06-18",
            developers=[{"name": "Makura", "original": "枕"}, {"name": "Frontwing", "original": None}],
        )
        rel = make_release(
            released="2020-06-18", minage=0, has_ero=False,
            vns=[{"id": "v27448", "rtype": "complete"}],
        )
        rec = vg.build_record(vn, [rel])
        self.assertTrue(vg.footnote(rec).startswith("《ATRI -My Dear Moments-》"))
        self.assertNotIn("18 禁", vg.footnote(rec))

    def test_发行方不同才列出(self):
        rel = make_release(
            producers=[
                {"name": "Azurite", "original": None, "developer": True, "publisher": False},
                {"name": "DiGination", "original": None, "developer": False, "publisher": True},
            ]
        )
        vn = make_vn(developers=[{"name": "Azurite", "original": None}])
        rec = vg.build_record(vn, [rel])
        self.assertEqual(rec["publishers"], ["DiGination"])
        self.assertIn("Azurite（发行：DiGination）于", vg.footnote(rec))

    def test_开发方自己发行时不重复(self):
        rec = vg.build_record(make_vn(), [make_release()])
        self.assertEqual(rec["publishers"], [])


class AliasTest(unittest.TestCase):
    def test_别名不收罗马字转写(self):
        vn = make_vn(
            titles=[
                {"lang": "ja", "title": "金色ラブリッチェ", "latin": "Kin'iro Loveriche"},
                {"lang": "zh-Hans", "title": "金辉恋曲四重奏", "latin": "Jin Hui Lianqu Sichongzou"},
            ]
        )
        aliases = vg.display_aliases(vn)
        self.assertIn("金辉恋曲四重奏", aliases)
        self.assertNotIn("Kin'iro Loveriche", aliases)


if __name__ == "__main__":
    unittest.main()
