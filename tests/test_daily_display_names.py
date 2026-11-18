"""叙述里的账号必须是显示名，不能是 `bili_<uid>`。

261118-g 的两条互动把「被炒的炒饭 / 33祖传上色 / StuartRiki_鍵視」写成了
`bili_16302815` / `bili_138256` / `bili_39471072`：出题材料只带句柄，
名单里的 `name` 从来没进题面。这里盯住两道闸门：

* 题面里有账号显示名表，也有不许写句柄的硬规则；
* 判卷拦住叙述里的 `bili_<uid>`，但放行 `people[].handle`。

    python -m unittest tests.test_daily_display_names -v
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
from daily.issue import GALGAME  # noqa: E402
from daily.roster import Roster  # noqa: E402
from daily.validate import ValidationError, validate_answer  # noqa: E402

ISSUE = "261118-g"
ROSTER = {
    "schema_version": 5,
    "categories": [{"id": "bili_gal", "label": "B站Gal"}],
    "accounts": [
        {"handle": "bili_138256", "name": "33祖传上色", "category": "bili_gal"},
        {"handle": "bili_39471072", "name": "StuartRiki_鍵視", "category": "bili_gal"},
        {"handle": "bili_16302815", "name": "被炒的炒饭", "category": "bili_gal"},
    ],
}


def generate() -> dict:
    handles = [a["handle"] for a in ROSTER["accounts"]]
    return {
        "categories": [
            {
                "id": "bili_gal",
                "label": "B站Gal",
                "handles": handles,
                "items": [
                    {
                        "key": "bilibili:1",
                        "account": h,
                        "published_at": "2026-11-18T10:00:00+09:00",
                        "kind": "post",
                        "text": "材料正文",
                    }
                    for h in handles
                ],
            }
        ]
    }


def answer() -> dict:
    return {
        "category": "all",
        "summary": "今天有人发了免费素材",
        "works": [],
        "highlights": [
            {"text": "一件值得说的事", "sources": ["bilibili:1"]},
            {"text": "另一件值得说的事", "sources": ["bilibili:1"]},
        ],
        "interactions": [
            {"text": "被炒的炒饭转发了33祖传上色的素材", "sources": ["bilibili:1"]}
        ],
        "people": [{"handle": "bili_16302815", "summary": "发了动态", "sources": ["bilibili:1"]}],
    }


class DisplayNameTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.out = self.root / "out"
        (self.root / "roster.json").write_text(
            json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8"
        )
        self.roster = Roster.load(self.root / "roster.json", kind=GALGAME)

    def check(self, payload: dict) -> None:
        validate_answer(
            payload,
            roster=self.roster,
            known_keys={"bilibili:1"},
            handles=set(a["handle"] for a in ROSTER["accounts"]),
        )

    def test_flat_prompt_shows_names_and_bans_uids(self) -> None:
        prompt = prompt_mod.build_flat(
            ISSUE,
            generate(),
            self.out,
            roster=self.roster,
            daily_dir=self.root / "data" / "daily",
        )
        md = prompt.md_path.read_text(encoding="utf-8")
        self.assertIn("## 账号显示名", md)
        self.assertIn("`bili_138256` → 33祖传上色", md)
        self.assertIn("`bili_39471072` → StuartRiki_鍵視", md)
        self.assertIn("`bili_16302815` → 被炒的炒饭", md)
        self.assertIn("不许写 `bili_123456`", md)
        payload = json.loads(prompt.json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["account_names"]["bili_138256"], "33祖传上色")

    def test_good_answer_with_names_passes(self) -> None:
        self.check(answer())

    def test_uid_in_interaction_is_rejected(self) -> None:
        payload = answer()
        payload["interactions"][0]["text"] = "bili_16302815转发了bili_138256的素材"
        with self.assertRaises(ValidationError) as ctx:
            self.check(payload)
        self.assertIn("$.interactions[0]", str(ctx.exception))
        self.assertIn("账号显示名", str(ctx.exception))

    def test_uid_in_highlight_and_summary_is_rejected(self) -> None:
        payload = answer()
        payload["highlights"][0]["text"] = "bili_39471072 报道了 Key 的动态"
        with self.assertRaises(ValidationError):
            self.check(payload)
        payload = answer()
        payload["summary"] = "bili_138256 发布素材"
        with self.assertRaises(ValidationError):
            self.check(payload)

    def test_handle_field_is_allowed_to_be_uid(self) -> None:
        payload = answer()
        payload["people"][0]["handle"] = "bili_39471072"
        self.check(payload)


if __name__ == "__main__":
    unittest.main()
