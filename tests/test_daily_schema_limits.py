"""副标题字数上限的「三处必须一起改」守卫。

`description` 的上限同时写在三个地方，任何一处漏改都会产生很别扭的现象：

* `schemas/report.schema.json` —— `publish` 用它校验，写超了拒绝发布；
* `src/content.config.ts` 的 Zod —— `npm run build` 用它校验，写超了构建失败；
* `scripts/daily/schema.py` 的 `DESCRIPTION_MAX` —— 判卷的报错文案用它。

前两处不一致时，一份正本能过 `publish` 却在构建时炸；第三处不一致时报错会
说「上限 50」而实际卡在 70，照着改反而改错。所以这里把它们钉在一起。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily.schema import DESCRIPTION_MAX, load_schema  # noqa: E402
from daily.issue import parse_issue_id  # noqa: E402


class DescriptionLimitTest(unittest.TestCase):
    def test_python_constant_matches_json_schema(self) -> None:
        schema = load_schema("report")
        declared = schema["properties"]["description"]["maxLength"]
        self.assertEqual(
            DESCRIPTION_MAX,
            declared,
            "scripts/daily/schema.py 的 DESCRIPTION_MAX 与 schemas/report.schema.json 不一致",
        )

    def test_python_constant_matches_zod(self) -> None:
        source = (ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
        found = re.search(r"description:\s*z\.string\(\)\.trim\(\)\.max\((\d+)", source)
        self.assertIsNotNone(found, "content.config.ts 里找不到 description 的 .max()")
        self.assertEqual(
            DESCRIPTION_MAX,
            int(found.group(1)),
            "scripts/daily/schema.py 的 DESCRIPTION_MAX 与 content.config.ts 的 .max() 不一致",
        )


class IssueIdPatternTest(unittest.TestCase):
    """期号正则也是三处：JSON Schema / Zod / `daily.issue`。

    拆成两版之后这里最容易漏——`apply` 和 `publish` 都用 `report.schema.json` 校验，
    正则里少一个 `g`，Galgame 版连 `apply` 都过不去，而构建那边（Zod）却是好的：
    错误会以「期号不匹配」的形式出现在流程中段，而不是在写代码时。
    """

    VALID = [
        "261029",
        "261029-2",
        "261029-9",
        "261029-10",
        "261029-99",
        "261029-g",
        "261029-g2",
        "261029-g12",
        "261029-g99",
    ]
    INVALID = [
        "261029-1",
        "261029-g1",
        "261029-0",
        "261029-100",
        "261029-g100",
        "261029-",
        "261029-2-g",
        "261029-x",
        "26102",
        "2610290",
        "20261029",
    ]

    def _zod_pattern(self) -> str:
        source = (ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
        for line in source.splitlines():
            if "^[0-9]{6}" in line or "^\\d{6}" in line:
                start, end = line.index("/"), line.rindex("/")
                return line[start + 1 : end].replace(r"\d", "[0-9]")
        self.fail("content.config.ts 里找不到期号正则")

    def test_schema_pattern_agrees_with_issue_module(self) -> None:
        pattern = load_schema("report")["properties"]["issue"]["properties"]["id"]["pattern"]
        for issue_id in self.VALID:
            self.assertIsNotNone(
                parse_issue_id(issue_id), f"{issue_id} 是合法期号，daily.issue 却拒了"
            )
            self.assertRegex(issue_id, pattern, f"{issue_id} 能过 daily.issue，过不了 schema")
        for issue_id in self.INVALID:
            with self.assertRaises(ValueError, msg=f"{issue_id} 不是合法期号"):
                parse_issue_id(issue_id)
            self.assertNotRegex(issue_id, pattern, f"{issue_id} 被 daily.issue 拒了，schema 却放行")

    def test_zod_pattern_agrees_with_issue_module(self) -> None:
        pattern = self._zod_pattern()
        for issue_id in self.VALID:
            self.assertRegex(issue_id, pattern, f"{issue_id} 过不了 Zod")
        for issue_id in self.INVALID:
            self.assertNotRegex(issue_id, pattern, f"{issue_id} 被 Zod 放行了")

    def test_schema_and_zod_are_the_same_string(self) -> None:
        """两处正则必须是同一串：接受集相同但写法不同，下次改一处就会分叉。"""
        pattern = load_schema("report")["properties"]["issue"]["properties"]["id"]["pattern"]
        self.assertEqual(pattern, self._zod_pattern())


if __name__ == "__main__":
    unittest.main()
