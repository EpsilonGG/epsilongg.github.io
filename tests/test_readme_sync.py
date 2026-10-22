"""README 同步脚本的单元测试。

运行方式（在项目根目录）：

    python -m unittest discover -s tests -v

测试只使用标准库，并且全部在临时目录中操作文件，不会修改真实 README。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_profile_readme as sync  # noqa: E402

SITE = {"name": "示例站点", "url": "https://example.github.io"}
PROFILE = {
    "name": "张三",
    "tagline": "独立研究者",
    "intro": ["第一段简介。", "第二段简介。"],
}
NAVIGATION = [
    {"label": "首页", "href": "/", "description": "个人简介与站点入口"},
    {"label": "名片", "href": "/links/", "description": "主要身份信息与联系入口"},
]
POSTS = [
    sync.PostSummary("文章 A", "post-a", date(2026, 3, 1)),
    sync.PostSummary("文章 B", "post-b", date(2025, 12, 31)),
]

README_TEMPLATE = """# 手写标题

这是 Marker 之外的手写内容，同步时不能被修改。

<!-- PROFILE:START -->
旧的简介内容
<!-- PROFILE:END -->

中间的手写说明，也要保留。

<!-- NAV:START -->
- 旧的导航
<!-- NAV:END -->

<!-- POSTS:START -->
- 旧的文章
<!-- POSTS:END -->

最后一段手写内容。
"""


def build_blocks(posts=POSTS, max_posts=sync.DEFAULT_MAX_POSTS):
    return sync.build_blocks(SITE, PROFILE, NAVIGATION, posts, max_posts)


class ApplyBlocksTests(unittest.TestCase):
    def test_all_three_blocks_are_replaced(self):
        result = sync.apply_blocks(README_TEMPLATE, build_blocks())

        self.assertIn("**张三** · 独立研究者", result)
        self.assertIn("第一段简介。", result)
        self.assertIn("[名片](https://example.github.io/links/)", result)
        self.assertIn("[文章 A](https://example.github.io/blog/post-a/)", result)
        self.assertNotIn("旧的简介内容", result)
        self.assertNotIn("旧的导航", result)
        self.assertNotIn("旧的文章", result)

    def test_content_outside_markers_is_preserved(self):
        result = sync.apply_blocks(README_TEMPLATE, build_blocks())

        self.assertTrue(result.startswith("# 手写标题\n\n这是 Marker 之外的手写内容，同步时不能被修改。\n"))
        self.assertIn("\n\n中间的手写说明，也要保留。\n", result)
        self.assertTrue(result.endswith("\n\n最后一段手写内容。\n"))

    def test_apply_is_idempotent(self):
        once = sync.apply_blocks(README_TEMPLATE, build_blocks())
        twice = sync.apply_blocks(once, build_blocks())

        self.assertEqual(once, twice)

    def test_missing_start_marker_raises(self):
        broken = README_TEMPLATE.replace("<!-- NAV:START -->\n", "")

        with self.assertRaises(sync.SyncError) as context:
            sync.apply_blocks(broken, build_blocks())

        self.assertEqual(context.exception.exit_code, sync.EXIT_STRUCTURE)
        self.assertIn("NAV:START", str(context.exception))

    def test_missing_end_marker_raises(self):
        broken = README_TEMPLATE.replace("<!-- POSTS:END -->\n", "")

        with self.assertRaises(sync.SyncError) as context:
            sync.apply_blocks(broken, build_blocks())

        self.assertIn("POSTS:END", str(context.exception))

    def test_duplicate_marker_raises(self):
        broken = README_TEMPLATE.replace(
            "<!-- POSTS:END -->",
            "<!-- POSTS:END -->\n<!-- POSTS:START -->\n重复区域\n<!-- POSTS:END -->",
        )

        with self.assertRaises(sync.SyncError) as context:
            sync.apply_blocks(broken, build_blocks())

        self.assertIn("必须唯一", str(context.exception))

    def test_wrong_order_raises(self):
        nav_block = (
            "<!-- NAV:START -->\n- 旧的导航\n<!-- NAV:END -->"
        )
        posts_block = (
            "<!-- POSTS:START -->\n- 旧的文章\n<!-- POSTS:END -->"
        )
        broken = README_TEMPLATE.replace(nav_block, "@@NAV@@").replace(
            posts_block, nav_block
        ).replace("@@NAV@@", posts_block)

        with self.assertRaises(sync.SyncError) as context:
            sync.apply_blocks(broken, build_blocks())

        self.assertIn("顺序错误", str(context.exception))

    def test_nested_marker_raises(self):
        broken = README_TEMPLATE.replace(
            "旧的简介内容",
            "旧的简介内容\n<!-- NAV:START -->\n嵌套\n<!-- NAV:END -->",
        ).replace("<!-- NAV:START -->\n- 旧的导航\n<!-- NAV:END -->\n", "")

        with self.assertRaises(sync.SyncError):
            sync.apply_blocks(broken, build_blocks())

    def test_empty_posts_is_handled(self):
        result = sync.apply_blocks(README_TEMPLATE, build_blocks(posts=[]))

        self.assertIn("文章归档正在整理中。", result)
        self.assertNotIn("旧的简介内容", result)

    def test_posts_are_sorted_and_limited(self):
        result = sync.apply_blocks(README_TEMPLATE, build_blocks(max_posts=1))

        self.assertIn("文章 A", result)
        self.assertNotIn("文章 B", result)


class RenderTests(unittest.TestCase):
    def test_posts_sorted_by_date_desc(self):
        unsorted = [POSTS[1], POSTS[0]]
        rendered = sync.render_posts_block(SITE, sorted(
            unsorted, key=lambda item: -item.published.toordinal()
        ))

        self.assertLess(rendered.index("文章 A"), rendered.index("文章 B"))

    def test_navigation_uses_absolute_urls(self):
        rendered = sync.render_navigation_block(SITE, NAVIGATION)

        self.assertIn("[首页](https://example.github.io/)", rendered)
        self.assertIn("[名片](https://example.github.io/links/)", rendered)

    def test_unicode_and_blank_lines_are_kept(self):
        text = (
            "开头\n\n<!-- PROFILE:START -->\n旧\n<!-- PROFILE:END -->\n\n"
            "<!-- NAV:START -->\n旧\n<!-- NAV:END -->\n\n"
            "<!-- POSTS:START -->\n旧\n<!-- POSTS:END -->\n\n结尾 — 保留空行\n"
        )
        result = sync.apply_blocks(text, build_blocks())

        self.assertIn("开头\n\n", result)
        self.assertTrue(result.endswith("\n\n结尾 — 保留空行\n"))
        self.assertIn("第一段简介。", result)


class SyncFileTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.readme_path = Path(self._temp_dir.name) / "README.md"

    def _write(self, text: str) -> None:
        with self.readme_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _read(self) -> str:
        with self.readme_path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()

    def test_sync_writes_file(self):
        self._write(README_TEMPLATE)

        code = sync.sync_file(self.readme_path, build_blocks())

        self.assertEqual(code, sync.EXIT_OK)
        self.assertIn("**张三**", self._read())

    def test_check_does_not_write_when_up_to_date(self):
        self._write(sync.apply_blocks(README_TEMPLATE, build_blocks()))
        before = self._read()

        code = sync.sync_file(self.readme_path, build_blocks(), check=True)

        self.assertEqual(code, sync.EXIT_OK)
        self.assertEqual(self._read(), before)

    def test_check_does_not_write_when_outdated(self):
        self._write(README_TEMPLATE)
        before = self._read()

        code = sync.sync_file(self.readme_path, build_blocks(), check=True)

        self.assertEqual(code, sync.EXIT_DIFF)
        self.assertEqual(self._read(), before)

    def test_sync_is_idempotent_on_disk(self):
        self._write(README_TEMPLATE)
        sync.sync_file(self.readme_path, build_blocks())
        first = self._read()

        sync.sync_file(self.readme_path, build_blocks())

        self.assertEqual(self._read(), first)

    def test_missing_file_returns_input_error(self):
        with self.assertRaises(sync.SyncError) as context:
            sync.sync_file(self.readme_path, build_blocks())

        self.assertEqual(context.exception.exit_code, sync.EXIT_INPUT)


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.readme_path = Path(self._temp_dir.name) / "README.md"
        self.readme_path.write_text(README_TEMPLATE, encoding="utf-8")

    def test_check_mode_exit_code(self):
        code = sync.main(["--readme", str(self.readme_path), "--check"])

        self.assertEqual(code, sync.EXIT_DIFF)

    def test_structure_error_exit_code(self):
        self.readme_path.write_text("# 没有 Marker 的 README\n", encoding="utf-8")

        code = sync.main(["--readme", str(self.readme_path)])

        self.assertEqual(code, sync.EXIT_STRUCTURE)


class FrontmatterTests(unittest.TestCase):
    def test_parse_title_date_and_list(self):
        text = (
            "---\n"
            "title: 示例文章\n"
            "pubDate: 2026-01-01\n"
            "tags:\n"
            "  - 示例\n"
            "  - 测试\n"
            "draft: true\n"
            "---\n\n正文\n"
        )

        meta = sync.parse_frontmatter(text, "example.md")

        self.assertEqual(meta["title"], "示例文章")
        self.assertEqual(meta["tags"], ["示例", "测试"])
        self.assertEqual(meta["draft"], "true")

    def test_invalid_date_raises(self):
        text = "---\ntitle: 坏日期\npubDate: 不是日期\n---\n\n正文\n"

        with self.assertRaises(sync.SyncError):
            sync._parse_date(sync.parse_frontmatter(text)["pubDate"], "bad.md")


if __name__ == "__main__":
    unittest.main()
