"""周报纯文字版的契约测试（2026-11-22）。

`weekly/out/weekly.md` 是给论坛贴的纯文字版：GFM Markdown、不插图、
不带工作台内部说明，各级标题文字按论坛规则加粗；`report.json.markdown`
是同一份规则剥出来的**不加粗**正本，这次不再重发。
"""
from __future__ import annotations

import importlib
import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEEKLY_DIR = ROOT / "weekly"
# 与其他 weekly 测试同样挂别名：`unittest discover -s tests` 会把 scripts/ 放到
# sys.path 前面，直接 `import weekly` 会拿到 scripts/weekly/ 的旧脚手架。
ALIAS = "_weekly_plain_root"
if ALIAS not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        ALIAS, WEEKLY_DIR / "__init__.py",
        submodule_search_locations=[str(WEEKLY_DIR)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = package
    spec.loader.exec_module(package)

draft_export = importlib.import_module(f"{ALIAS}.draft_export")
weekly_publish = importlib.import_module(f"{ALIAS}.publish")
public_markdown = draft_export.public_markdown
forum_markdown = draft_export.forum_markdown
published_markdown = weekly_publish.public_markdown

DRAFT = """# Galgame 周报

> 正式版 · 本地工作台输出；未定稿。
> 栏目 → 品牌 → 游戏 → 条目。

**导语**：这里只是工作台统计，不对外。

---

## 新作

### [ゆずソフト](https://x.com/yuzusoft)

#### 『ライムライト・レモネードジャム』

- 海外版发售决定 [原文1](https://x.com/yuzusoft/status/1) [原文2](https://x.com/yuzusoft/status/2)

## 业界动向

### [某号](https://x.com/someone)

- 不启用栏目里的一句话 [原文](https://x.com/someone/status/3)

## 作品情报

- 另一条 [原文](https://www.bilibili.com/opus/4)
"""

DISABLED = ["业界动向"]


class WeeklyPlainMarkdownTest(unittest.TestCase):
    def test_only_canonical_body_survives(self) -> None:
        out = public_markdown(DRAFT, DISABLED)
        self.assertFalse(out.startswith("# "))
        self.assertNotIn("> 正式版", out)
        self.assertNotIn("**导语**", out)
        self.assertNotIn("---", out)
        self.assertNotIn("## 业界动向", out)
        self.assertNotIn("不启用栏目里的一句话", out)
        self.assertTrue(out.startswith("## 新作\n"))
        self.assertIn("## 作品情报", out)

    def test_source_links_are_verbatim_and_absolute(self) -> None:
        out = public_markdown(DRAFT, DISABLED)
        for link in ("[原文1](https://x.com/yuzusoft/status/1)",
                     "[原文2](https://x.com/yuzusoft/status/2)",
                     "[原文](https://www.bilibili.com/opus/4)"):
            self.assertIn(link, out)

    def test_no_images_and_single_trailing_newline(self) -> None:
        out = public_markdown(DRAFT, DISABLED)
        self.assertNotIn("![", out)
        self.assertNotIn("<img", out)
        self.assertTrue(out.endswith("\n"))
        self.assertFalse(out.endswith("\n\n"))

    def test_forum_export_bolds_every_heading_level(self) -> None:
        out = forum_markdown(public_markdown(DRAFT, DISABLED))
        self.assertIn("## **新作**\n", out)
        self.assertIn("### **[ゆずソフト](https://x.com/yuzusoft)**\n", out)
        self.assertIn("#### **『ライムライト・レモネードジャム』**\n", out)
        self.assertIn("## **作品情报**\n", out)
        headings = [ln for ln in out.splitlines() if re.match(r"^#{1,6} ", ln)]
        self.assertEqual(len(headings), 4)
        for line in headings:
            self.assertRegex(line, r"^#{1,6} \*\*.+\*\*$", line)
        self.assertNotIn("![", out)

    def test_forum_bold_is_reversible_and_does_not_touch_canonical(self) -> None:
        clean = public_markdown(DRAFT, DISABLED)
        bolded = forum_markdown(clean)
        self.assertEqual(public_markdown(bolded, DISABLED), clean)
        self.assertEqual(forum_markdown(bolded), bolded, '重复加粗不该叠加星号')
        self.assertIs(published_markdown, public_markdown)

    def test_publish_uses_the_same_rule_and_is_idempotent(self) -> None:
        once = public_markdown(DRAFT, DISABLED)
        self.assertEqual(once, public_markdown(once, DISABLED))


if __name__ == "__main__":
    unittest.main()
