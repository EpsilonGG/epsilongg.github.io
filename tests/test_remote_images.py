"""远程图片体检脚本的单元测试。

只测纯函数（地址提取），不发起任何网络请求。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_remote_images as checker  # noqa: E402


class FindRemoteImagesTest(unittest.TestCase):
    def test_markdown_image(self) -> None:
        text = "正文\n\n![图注](https://example.com/a.jpg \"说明\")\n"
        self.assertEqual(
            checker.find_remote_images(text),
            [(3, "https://example.com/a.jpg", "md")],
        )

    def test_markdown_image_without_title(self) -> None:
        text = "![alt](https://example.com/b.png)\n"
        self.assertEqual(checker.find_remote_images(text), [(1, "https://example.com/b.png", "md")])

    def test_html_img(self) -> None:
        text = '<img src="https://example.com/c.webp" alt="x" width="600">\n'
        self.assertEqual(checker.find_remote_images(text), [(1, "https://example.com/c.webp", "html")])

    def test_local_image_is_ignored(self) -> None:
        text = "![图注](/images/blog/x/01.jpg)\n"
        self.assertEqual(checker.find_remote_images(text), [])

    def test_fenced_code_block_is_ignored(self) -> None:
        text = (
            "前言\n\n"
            "```md\n"
            "![示例](https://example.com/in-code.jpg)\n"
            "```\n\n"
            "![真图](https://example.com/real.jpg)\n"
        )
        self.assertEqual(
            checker.find_remote_images(text),
            [(7, "https://example.com/real.jpg", "md")],
        )

    def test_multiple_images_keep_line_numbers(self) -> None:
        text = (
            "![a](https://example.com/1.jpg)\n"
            "\n"
            "中间一段文字\n"
            "\n"
            '<figure><img src="https://example.com/2.jpg"></figure>\n'
        )
        self.assertEqual(
            checker.find_remote_images(text),
            [(1, "https://example.com/1.jpg", "md"), (5, "https://example.com/2.jpg", "html")],
        )


class HumanSizeTest(unittest.TestCase):
    def test_formats(self) -> None:
        self.assertEqual(checker.human_size(None), "—")
        self.assertEqual(checker.human_size(2048), "2 KB")
        self.assertEqual(checker.human_size(3 * 1024 * 1024), "3.0 MB")


def make_png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00" * 16
    )


def make_gif(width: int, height: int) -> bytes:
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00" * 24


def make_jpeg(width: int, height: int) -> bytes:
    # SOI + APP0（长度 16 的空段）+ SOF0
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"\x00" * 14
    sof0 = (
        b"\xff\xc0"
        + struct.pack(">H", 11)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8" + app0 + sof0 + b"\x00" * 8


def make_webp_vp8x(width: int, height: int) -> bytes:
    return (
        b"RIFF"
        + b"\x00\x00\x00\x00"
        + b"WEBP"
        + b"VP8X"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
        + b"\x00" * 8
    )


class ImageSizeTest(unittest.TestCase):
    def test_png(self) -> None:
        self.assertEqual(checker.image_size(make_png(670, 377)), (670, 377))

    def test_gif(self) -> None:
        self.assertEqual(checker.image_size(make_gif(120, 90)), (120, 90))

    def test_jpeg(self) -> None:
        self.assertEqual(checker.image_size(make_jpeg(1400, 788)), (1400, 788))

    def test_webp(self) -> None:
        self.assertEqual(checker.image_size(make_webp_vp8x(960, 540)), (960, 540))

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(checker.image_size(b"not an image at all, just text......"))
        self.assertIsNone(checker.image_size(b""))

    def test_write_dimensions(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "remote-images.json"
            count = checker.write_dimensions(
                [
                    ("https://example.com/a.jpg", make_jpeg(800, 600)),
                    ("https://example.com/b.png", make_png(300, 200)),
                    ("https://example.com/bad.jpg", b"garbage"),
                ],
                out,
            )
            self.assertEqual(count, 2)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["images"]["https://example.com/a.jpg"], {"w": 800, "h": 600, "bytes": len(make_jpeg(800, 600))})
            self.assertEqual(payload["images"]["https://example.com/b.png"]["w"], 300)
            self.assertNotIn("https://example.com/bad.jpg", payload["images"])


if __name__ == "__main__":
    unittest.main()
