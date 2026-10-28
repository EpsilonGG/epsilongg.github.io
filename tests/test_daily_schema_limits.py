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


if __name__ == "__main__":
    unittest.main()
