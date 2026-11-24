"""Gplus digest 的格式契约。

这份 digest 是 Gplus 出稿时唯一的题面：格式一变，写稿那一步就找不到
`[id]`、对不上「谁转了谁」，所以这里把四段（计数、RT 集群、关键词、按账号分组）
的形状钉住，同时钉住「缺切片＝退出码 2」。

    python -m unittest tests.test_gplus_digest -v
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

import gplus_digest  # noqa: E402

DAY = "2026-11-19"

ROSTER = {
    "accounts": [
        {"handle": "kionachi", "name": "木緒なち", "group": "creator", "brand": "—"},
        {"handle": "smee_official", "name": "SMEE／スミー", "group": "brand", "brand": "SMEE"},
        {"handle": "Elen_Mass", "name": "Elen", "group": "creator", "brand": "—"},
    ]
}


def item(item_id: str, publisher: str, content: str, *, rt: bool = False, at: str = "2026-11-19T05:00:00+00:00"):
    return {
        "identity_key": f"x:{item_id}",
        "source_id": "x",
        "item_id": item_id,
        "publisher": publisher,
        "canonical_url": f"https://x.com/{publisher}/status/{item_id}",
        "published_at": at,
        "content": content,
        "metadata": {"is_retweet": rt, "is_quote": False, "is_reply": False, "provider": "nitter-rss"},
    }


class GplusDigestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.slices = root / "slices"
        self.slices.mkdir()
        self.dest = root / "digest"
        roster = root / "roster.json"
        roster.write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")

        rows = [
            item("111", "kionachi", "『新作』の発売が決定しました"),
            item("222", "kionachi", "今日は野球の話"),  # 第二条同账号：n=2
            item("333", "smee_official", "予約受付スタート" + "あ" * 400),
            item("444", "Elen_Mass", "RT @kionachi: 『新作』の発売が決定しました", rt=True),
        ]
        (self.slices / f"{DAY}.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
        )

        self._old = (gplus_digest.SLICES, gplus_digest.ROSTER)
        gplus_digest.SLICES = self.slices
        gplus_digest.ROSTER = roster
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        gplus_digest.SLICES, gplus_digest.ROSTER = self._old

    def build(self) -> str:
        code = gplus_digest.main(["--date", DAY, "--dest", str(self.dest)])
        self.assertEqual(code, 0)
        return (self.dest / f"{DAY}.md").read_text(encoding="utf-8")

    def test_counts_and_sections(self) -> None:
        text = self.build()
        self.assertTrue(text.startswith(f"# Gplus digest {DAY}\n"))
        # 4 条 / 3 个账号 / 3 条原创（转推不算原创）
        self.assertIn("items=4 accounts=3 originals=3", text)
        for heading in (
            "## RT clusters (target -> retweeters)",
            "## Keyword topics",
            "## Accounts (originals only, group | name | handle | brand)",
        ):
            self.assertIn(heading, text)

    def test_rt_cluster_lists_retweeter(self) -> None:
        text = self.build()
        self.assertIn("- @kionachi (木緒なち) x1: elen_mass", text)

    def test_reposts_section_names_original_author(self) -> None:
        text = self.build()
        self.assertIn("## Reposts (retweeter -> [id] @original: body)", text)
        self.assertIn("- [444] -> @kionachi: RT @kionachi: 『新作』の発売が決定しました", text)

    def test_keywords_count_items_not_occurrences(self) -> None:
        text = self.build()
        # 「発売」出现在两条（一条原创、一条转推），按条目数算 2
        self.assertIn("発売:2", text)
        self.assertIn("予約:1", text)

    def test_accounts_sorted_by_size_and_body_truncated(self) -> None:
        text = self.build()
        self.assertIn("### creator | 木緒なち | @kionachi | — | n=2", text)
        self.assertIn(f"### brand | SMEE／スミー | @smee_official | SMEE | n=1", text)
        # 截断到 260 字，且不出现换行把列表拆断
        long_line = [line for line in text.splitlines() if line.startswith("- [333]")][0]
        self.assertLessEqual(len(long_line) - len("- [333] "), 260)

    def test_missing_slice_exits_2(self) -> None:
        self.assertEqual(gplus_digest.main(["--date", "2020-01-01", "--dest", str(self.dest)]), 2)


if __name__ == "__main__":
    unittest.main()
