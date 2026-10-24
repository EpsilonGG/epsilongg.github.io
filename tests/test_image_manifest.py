"""图片清单与文章内容的对账测试。

`src/data/image-manifest.json` 由 `scripts/optimize_images.mjs` 生成，
构建前会自动刷新。这个测试守两件事：

1. 文章里引用到的每一张站内图片，清单里都有对应条目（否则那张图没有
   WebP 变体、也没有 width/height，属于悄悄退化）；
2. 清单里每个变体文件都真实存在于 `public/` 下（否则页面会引用一个 404）。

跑之前要先跑一次 `npm run images`（`npm run build` 里已经包含）。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOG_DIR = ROOT / "src" / "content" / "blog"
MANIFEST = ROOT / "src" / "data" / "image-manifest.json"

# Markdown 图片：![alt](src "title")
MD_IMAGE = re.compile(r"!\[[^\]]*\]\((/images/[^)\s]+)")
# 手写 <img src="/images/...">
HTML_IMAGE = re.compile(r"<img[^>]*src=\"(/images/[^\"]+)\"")


def referenced_images() -> set[str]:
    found: set[str] = set()
    for path in BLOG_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        found.update(MD_IMAGE.findall(text))
        found.update(HTML_IMAGE.findall(text))
    return found


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


class ManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MANIFEST.exists():
            raise unittest.SkipTest("还没有生成 image-manifest.json，先跑 npm run images")
        cls.manifest = load_manifest()

    def test_manifest_shape(self) -> None:
        self.assertIn("images", self.manifest)
        self.assertGreater(len(self.manifest["images"]), 0)

    def test_article_images_are_in_manifest(self) -> None:
        images = self.manifest["images"]
        missing = sorted(src for src in referenced_images() if src not in images)
        self.assertEqual(
            missing,
            [],
            "以下图片在文章里被引用，但清单里没有（跑一次 npm run images）",
        )

    def test_every_entry_has_size_and_variants(self) -> None:
        for src, entry in self.manifest["images"].items():
            with self.subTest(src=src):
                self.assertIsInstance(entry.get("w"), int)
                self.assertIsInstance(entry.get("h"), int)
                self.assertGreater(entry["w"], 0)
                self.assertGreater(entry["h"], 0)
                self.assertTrue(entry.get("variants"), "至少要有一个 WebP 变体")

    def test_variant_files_exist(self) -> None:
        for src, entry in self.manifest["images"].items():
            for variant in entry["variants"]:
                with self.subTest(src=src, width=variant["w"]):
                    path = ROOT / "public" / variant["src"].lstrip("/")
                    self.assertTrue(path.is_file(), f"变体文件不存在：{variant['src']}")

    def test_variant_widths_match_original(self) -> None:
        for src, entry in self.manifest["images"].items():
            widths = [v["w"] for v in entry["variants"]]
            with self.subTest(src=src):
                self.assertEqual(widths, sorted(widths), "变体宽度应从小到大")
                self.assertEqual(widths[-1], entry["w"], "最大变体应等于原图宽度（不放大）")
                self.assertEqual(len(widths), len(set(widths)), "宽度不应重复")


if __name__ == "__main__":
    unittest.main()
