"""远程图片体检脚本的单元测试。

只测纯函数（地址提取），不发起任何网络请求。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
