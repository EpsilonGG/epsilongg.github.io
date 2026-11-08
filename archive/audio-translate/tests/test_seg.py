"""断句规则的单元测试。在 tools/audio-translate 目录下运行：python -m unittest -v"""

import unittest

from seg import Seg, build, normalize, resolve_overlaps, split_long


class TestNormalize(unittest.TestCase):
    def test_ellipsis_variants(self):
        self.assertEqual(normalize("あ……"), "あ…")
        self.assertEqual(normalize("wait..."), "wait…")
        self.assertEqual(normalize("はい。。。"), "はい…")
        self.assertEqual(normalize("【…】"), "…")

    def test_spaces(self):
        self.assertEqual(normalize("  你好   世界  "), "你好 世界")


class TestSplitLong(unittest.TestCase):
    def test_short_untouched(self):
        s = Seg(0, 5, "短い")
        self.assertEqual(len(split_long(s)), 1)

    def test_split_at_strong_punct(self):
        text = "これは最初の文です。これは二番目の文です。"
        s = Seg(0, 20, text)
        out = split_long(s)
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0].text.endswith("。"))
        self.assertEqual(out[0].text + out[1].text, text)
        for p in out:
            self.assertLessEqual(p.dur, 12.0)
            self.assertGreaterEqual(p.dur, 1.0)

    def test_no_punct_repeats_whole_text(self):
        text = "あ" * 40
        s = Seg(0, 30, text)
        out = split_long(s)
        self.assertEqual(len(out), 3)
        for p in out:
            self.assertEqual(p.text, text)
            self.assertLessEqual(p.dur, 12.0)

    def test_weak_punct_too_short_falls_back_to_repeat(self):
        # 逗号两侧都太短，拆了读不通 → 整句重复
        text = "はい、そう"
        s = Seg(0, 25, text)
        out = split_long(s)
        self.assertEqual(len(out), 3)
        self.assertTrue(all(p.text == text for p in out))


class TestOverlap(unittest.TestCase):
    def test_duplicate_mode_splits_into_three(self):
        a = Seg(0, 5, "Aのセリフ")
        b = Seg(3, 8, "Bのセリフ")
        out = resolve_overlaps([a, b], mode="duplicate")
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0].text, "Aのセリフ")
        self.assertEqual(out[1].text, "Aのセリフ\nBのセリフ")
        self.assertEqual(out[2].text, "Bのセリフ")
        # 时间必须相连且不重叠
        for x, y in zip(out, out[1:]):
            self.assertAlmostEqual(x.end, y.start, places=3)

    def test_merge_mode(self):
        out = resolve_overlaps([Seg(0, 5, "A"), Seg(3, 8, "B")], mode="merge")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].text, "A\nB")
        self.assertEqual((out[0].start, out[0].end), (0, 8))

    def test_small_overlap_kept_consecutive(self):
        out = resolve_overlaps([Seg(0, 5, "A"), Seg(4.6, 8, "B")], mode="duplicate")
        for x, y in zip(out, out[1:]):
            self.assertLessEqual(x.end, y.start + 1e-6)

    def test_containment_splits_into_three(self):
        # B 整个落在 A 里面：A / A+B / A
        out = resolve_overlaps([Seg(0, 10, "A"), Seg(2, 4, "B")], mode="duplicate")
        self.assertEqual(len(out), 3)
        self.assertEqual([x.text for x in out], ["A", "A\nB", "A"])
        for x, y in zip(out, out[1:]):
            self.assertAlmostEqual(x.end, y.start, places=3)


class TestBuild(unittest.TestCase):
    def test_no_overlap_no_gap_violation(self):
        segs = [Seg(0, 3, "一。"), Seg(3.2, 6, "二。"), Seg(7, 9, "三。")]
        cues = build(segs)
        self.assertEqual(len(cues), 3)
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a.end, b.start + 1e-6)
        for c in cues:
            self.assertGreaterEqual(c.dur, 1.0 - 1e-6)
            self.assertLessEqual(c.dur, 12.0 + 1e-6)

    def test_lead_and_tail(self):
        cues = build([Seg(5.0, 8.0, "テスト。")])
        self.assertAlmostEqual(cues[0].start, 4.7, places=3)
        self.assertAlmostEqual(cues[0].end, 8.5, places=3)

    def test_never_starts_negative(self):
        cues = build([Seg(0.1, 3.0, "テスト。")])
        self.assertGreaterEqual(cues[0].start, 0.0)

    def test_min_duration_respected(self):
        cues = build([Seg(1.0, 1.2, "短。"), Seg(5.0, 8.0, "次。")])
        self.assertGreaterEqual(cues[0].dur, 1.0 - 1e-6)


if __name__ == "__main__":
    unittest.main()
