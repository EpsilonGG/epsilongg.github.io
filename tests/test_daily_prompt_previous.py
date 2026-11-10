"""题面要带上「上两期已用过的头条与看点」，并要求一律降级。

为什么单独盯这一条：261107 / 261108 / 261109 连着三天同一个头条、同一批看点，
根因不是数据错，是题面里**没有「昨天已经领过」这件事**——模型每天看到的都是
「今天最大的一件事」，连载型事件（梗刷屏、赛事收官、销量倒计时）就天天夺冠。

三件事必须成立：

* 只取**同一版**的前两期，按时间倒序（声优版不吃 Galgame 版的头条）；
* 题面里真有那张表，也真有那条硬规则；
* 上一期改了头条 → 这一期的指纹跟着变，否则缓存会跳过重出题。

    python -m unittest tests.test_daily_prompt_previous -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily import prompt as prompt_mod  # noqa: E402
from daily.cache import input_hash  # noqa: E402

ISSUE = "261109"


def generate() -> dict:
    return {
        "categories": [
            {
                "id": "all",
                "label": "整期",
                "handles": ["alice"],
                "items": [
                    {
                        "key": "x:1",
                        "account": "alice",
                        "published_at": "2026-11-09T10:00:00+09:00",
                        "kind": "post",
                        "text": "新作が発売されます",
                    }
                ],
            }
        ]
    }


class PreviousIssuesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.daily = self.root / "data" / "daily"
        self.out = self.root / "out"
        self.daily.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, issue: str, description: str, highlights: list[str]) -> None:
        folder = self.daily / issue
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "description": description,
            "highlights": [{"text": text, "sources": ["x:1"]} for text in highlights],
        }
        (folder / "report.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    # -- 选期 ---------------------------------------------------------
    def test_takes_two_most_recent_of_the_same_kind(self) -> None:
        for issue in ("261105", "261106", "261107", "261108", "261108-g", "261109", "261110"):
            self.write(issue, f"{issue} 头条", [f"{issue} 看点"])

        blocks = prompt_mod._previous_issues(ISSUE, self.daily)
        self.assertEqual(["261108", "261107"], [block["id"] for block in blocks])
        self.assertEqual("261108 头条", blocks[0]["description"])
        self.assertEqual(["261108 看点"], blocks[0]["highlights"])

    def test_galgame_side_does_not_borrow_voice_headlines(self) -> None:
        for issue in ("261107", "261108", "261108-g", "261109-g"):
            self.write(issue, f"{issue} 头条", [])

        blocks = prompt_mod._previous_issues("261109-g", self.daily)
        self.assertEqual(["261108-g"], [block["id"] for block in blocks])

    def test_first_issue_has_no_previous(self) -> None:
        self.write("261105", "更早的一期", [])
        self.assertEqual([], prompt_mod._previous_issues("261101", self.daily))

    def test_missing_directory_is_not_an_error(self) -> None:
        self.assertEqual([], prompt_mod._previous_issues(ISSUE, self.root / "nope"))

    # -- 题面 ---------------------------------------------------------
    def test_prompt_carries_the_table_and_the_rule(self) -> None:
        self.write("261107", "梗刷屏第二天", ["梗刷屏那条"])
        self.write("261108", "梗刷屏第三天", ["梗刷屏那条", "赛事收官"])

        prompt = prompt_mod.build_flat(ISSUE, generate(), self.out, daily_dir=self.daily)
        text = prompt.md_path.read_text(encoding="utf-8")

        self.assertIn("上两期已用过的头条与看点", text)
        self.assertIn("梗刷屏第三天", text)
        self.assertIn("梗刷屏第二天", text)
        self.assertIn("赛事收官", text)
        self.assertIn("上两期用过的头条与看点一律降级", prompt_mod.RULES_FLAT)
        # 材料本身还在——降级不等于把条目删掉
        self.assertIn("新作が発売されます", text)

        payload = json.loads(prompt.json_path.read_text(encoding="utf-8"))
        self.assertEqual(["261108", "261107"], [b["id"] for b in payload["previous_issues"]])

    def test_no_previous_issue_means_no_table(self) -> None:
        prompt = prompt_mod.build_flat("261101", generate(), self.out, daily_dir=self.daily)
        text = prompt.md_path.read_text(encoding="utf-8")
        # 规则正文里也会提到这张表，所以只认小标题
        self.assertNotIn("## 上两期已用过的头条与看点", text)

    # -- 指纹 ---------------------------------------------------------
    def test_editing_yesterday_headline_changes_the_digest(self) -> None:
        self.write("261108", "旧头条", ["旧看点"])
        first = prompt_mod.build_flat(ISSUE, generate(), self.out, daily_dir=self.daily)

        self.write("261108", "改过的头条", ["旧看点"])
        second = prompt_mod.build_flat(ISSUE, generate(), self.out, daily_dir=self.daily)

        self.assertNotEqual(first.input_hash, second.input_hash, "上一期改了头条，题面指纹必须变")

    def test_digest_matches_items_when_there_is_no_previous(self) -> None:
        prompt = prompt_mod.build_flat("261101", generate(), self.out, daily_dir=self.daily)
        items = generate()["categories"][0]["items"]
        self.assertEqual(input_hash(items), prompt.input_hash)


if __name__ == "__main__":
    unittest.main()
