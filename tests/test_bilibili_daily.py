"""B 站动态日抓（`scripts/bilibili_daily.py`）的回归。

这个功能是 2026-11-11 接进 Galgame 日报的第二数据源。几个容易悄悄坏掉的点：

* 正本配置 ↔ 站点名单必须同步（漏一边页面就显示裸 handle 或抓错源）；
* `source=bilibili` 的号绝不能进 X-Reader 的 `accounts.galgame.yaml`；
* 归一化结果必须能被 `daily/adapters/xreader.py` 原样吃掉（字段边界只有那一处）；
* 按 JST 自然日落盘、同 id 只存一次（重复跑不能把镜像越滚越大）；
* WBI 签名与设备参数在，别被「匿名裸请求 412」逼回旧接口。
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import bilibili_daily as bili  # noqa: E402
import sync_xreader_accounts as sync  # noqa: E402
from daily.roster import Roster  # noqa: E402

CONFIG_PATH = ROOT / "src" / "config" / "daily-bilibili-galgame.json"
ROSTER_PATH = ROOT / "src" / "config" / "daily-roster-galgame.json"
HANDLE = "bili_3632310624717268"
UID = "3632310624717268"


def _item(**overrides):
    """一条 `DYNAMIC_TYPE_DRAW` 的 opus 图文动态（实测形状）。"""
    item = {
        "id_str": "1268953220126867464",
        "type": "DYNAMIC_TYPE_DRAW",
        "basic": {"jump_url": "//www.bilibili.com/opus/1268953220126867464"},
        "modules": {
            "module_author": {"name": "HOOKSOFT公式", "pub_ts": 1762753560},
            "module_dynamic": {
                "desc": {"text": None},
                "major": {
                    "opus": {
                        "title": "体验版公开中",
                        "summary": {"text": "『一夜之后』体验版已公开"},
                        "pics": [{"url": "https://i0.hdslb.com/bfs/xxx.jpg"}],
                    }
                },
            },
            "module_stat": {
                "like": {"count": 42},
                "forward": {"count": 3},
                "comment": {"count": 7},
            },
        },
    }
    item.update(overrides)
    return item


def _account():
    return {"uid": UID, "name": "HOOKSOFT公式", "handle": HANDLE,
            "tags": ["B站Gal"], "active": True}


def _record(item=None, account=None):
    return bili.normalize(item or _item(), account or _account(),
                          "2026-11-11T00:00:00+00:00")


class ConfigAndRosterTests(unittest.TestCase):
    def test_check_config_is_clean(self):
        self.assertEqual(bili.check_config(bili.load_config(), ROSTER_PATH), [])

    def test_category_label_is_the_required_tag(self):
        cfg = bili.load_config()
        self.assertEqual(cfg["source_id"], "bilibili")
        self.assertEqual(cfg["category"]["id"], "bili_gal")
        self.assertEqual(cfg["category"]["label"], "B站Gal")

    def test_every_monitored_account_has_the_tag_in_both_files(self):
        cfg = bili.load_config()
        roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
        by_handle = {a["handle"]: a for a in roster["accounts"]}
        self.assertTrue(cfg["accounts"], "至少要有一个监控账号")
        for a in cfg["accounts"]:
            self.assertIn("B站Gal", a["tags"])
            site = by_handle[a["handle"]]
            self.assertIn("B站Gal", site["tags"])
            self.assertEqual(site["category"], "bili_gal")
            self.assertEqual(site["source"], "bilibili")
            self.assertTrue(site["profile_url"].startswith("https://space.bilibili.com/"))
        self.assertTrue(any(c["id"] == "bili_gal" and c["label"] == "B站Gal"
                            for c in roster["categories"]))

    def test_load_config_rejects_untagged_or_duplicate_accounts(self):
        base = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        bad = json.loads(json.dumps(base))
        bad["accounts"][0]["tags"] = ["别的标签"]
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "cfg.json"
            p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "分类标签"):
                bili.load_config(p)
            dup = json.loads(json.dumps(base))
            dup["accounts"].append(dict(dup["accounts"][0]))
            p.write_text(json.dumps(dup, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "uid 重复"):
                bili.load_config(p)

    def test_xreader_sync_skips_non_x_sources(self):
        handles = sync.load_handles("galgame", ROSTER_PATH)
        self.assertNotIn(HANDLE, handles)
        self.assertNotIn("pikattoanime", handles)  # active=false 也不该进
        self.assertTrue(handles)
        self.assertEqual(len(handles), len(set(h.lower() for h in handles)))

    def test_roster_routes_bili_to_galgame_only(self):
        galgame = Roster.load(ROSTER_PATH, kind="galgame")
        voice = Roster.load(kind="voice")
        self.assertEqual(galgame.category_of(HANDLE), "bili_gal")
        self.assertTrue(galgame.belongs_to_kind(HANDLE))
        self.assertTrue(galgame.is_active(HANDLE))
        self.assertFalse(voice.belongs_to_kind(HANDLE))

    def test_site_uses_roster_profile_url_not_hardcoded_x(self):
        roster_ts = (ROOT / "src" / "lib" / "roster.ts").read_text(encoding="utf-8")
        layout = (ROOT / "src" / "layouts" / "DailyLayout.astro").read_text(encoding="utf-8")
        self.assertIn("export function profileUrlOf", roster_ts)
        self.assertIn("profile_url", roster_ts)
        self.assertIn("profileUrlOf", layout)
        self.assertNotIn("const profileUrl = (handle: string) => `https://x.com/${handle}`", layout)


class NormalizeTests(unittest.TestCase):
    def test_opus_text_and_pictures_are_kept(self):
        rec = _record()
        self.assertEqual(rec["source_id"], "bilibili")
        self.assertEqual(rec["item_id"], "1268953220126867464")
        self.assertEqual(rec["identity_key"], "bilibili:1268953220126867464")
        self.assertEqual(rec["canonical_url"],
                         "https://www.bilibili.com/opus/1268953220126867464")
        self.assertIn("『一夜之后』体验版已公开", rec["content"])
        self.assertEqual(rec["media"][0]["url"], "https://i0.hdslb.com/bfs/xxx.jpg")
        self.assertEqual(rec["metadata"]["account"], HANDLE)
        self.assertEqual(rec["metadata"]["uid"], UID)
        self.assertEqual(rec["metadata"]["tag"], "B站Gal")
        self.assertEqual(rec["metadata"]["stats"],
                         {"likes": 42, "retweets": 3, "replies": 7})
        self.assertFalse(rec["metadata"]["is_retweet"])

    def test_jump_url_fallback_and_day_precision(self):
        item = _item()
        item.pop("basic")
        rec = _record(item)
        self.assertEqual(rec["canonical_url"],
                         "https://www.bilibili.com/opus/1268953220126867464")
        self.assertEqual(rec["published_precision"], "second")
        self.assertTrue(rec["published_at"].endswith("+00:00"))
        self.assertIsNotNone(bili.day_of(rec))

    def test_forward_marks_kind_and_keeps_original_author(self):
        item = _item()
        item["type"] = "DYNAMIC_TYPE_FORWARD"
        item["orig"] = {
            "id_str": "999",
            "type": "DYNAMIC_TYPE_DRAW",
            "modules": {
                "module_author": {"name": "原作者", "pub_ts": 1762750000},
                "module_dynamic": {"major": {"opus": {"title": "原标题",
                                                       "summary": {"text": "原正文"}}}},
            },
        }
        rec = _record(item)
        self.assertTrue(rec["metadata"]["is_retweet"])
        self.assertEqual(rec["publisher"], "原作者")
        self.assertIn("转发 原作者", rec["content"])

    def test_adapter_roundtrip_into_daily_item(self):
        from daily.adapters.xreader import XReaderAdapter
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "bilibili.jsonl").write_bytes(
                (json.dumps(_record(), ensure_ascii=False) + "\n").encode("utf-8")
            )
            adapter = XReaderAdapter(Path(tmp))
            items = list(adapter.iter_items())
        self.assertEqual(adapter.malformed, [])
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it.key, "bilibili:1268953220126867464")
        self.assertEqual(it.source, "bilibili")
        self.assertEqual(it.account, HANDLE)
        self.assertEqual(it.kind, "post")
        self.assertIn("『一夜之后』体验版已公开", it.text)

    def test_jsonl_reader_survives_u2028_in_text(self):
        """正文带 U+2028 时不能按 splitlines 劈开（日报适配器踩过这个坑）。"""
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.jsonl"
            rec = _record()
            rec["content"] = "上\u2028下"
            p.write_bytes((json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8"))
            rows = bili._read_jsonl(p)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "上\u2028下")


class StorageTests(unittest.TestCase):
    def test_day_of_uses_jst_natural_day(self):
        # UTC 15:30 = JST 次日 00:30，必须落到次日那一片
        rec = {"published_at": "2026-11-10T15:30:00+00:00"}
        self.assertEqual(bili.day_of(rec), date(2026, 11, 11))
        self.assertIsNone(bili.day_of({"published_at": "not-a-date"}))

    def test_store_is_idempotent_and_mirror_rebuild_is_stable(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            items = Path(tmp) / "items"
            first = bili.store([_record()], root)
            self.assertEqual(sum(first.values()), 1)
            second = bili.store([_record()], root)
            self.assertEqual(sum(second.values()), 0)
            self.assertEqual(len(bili._read_jsonl(root / f"{list(first)[0].isoformat()}.jsonl")), 1)
            self.assertEqual(bili.rebuild_mirror(root, items), 1)
            self.assertEqual(bili.rebuild_mirror(root, items), 1)
            self.assertEqual(len(bili._read_jsonl(items / "bilibili.jsonl")), 1)
            self.assertEqual(bili.latest_day(root), list(first)[0])

    def test_mirror_appends_only_new_ids(self):
        with TemporaryDirectory() as tmp:
            items = Path(tmp) / "items"
            self.assertEqual(bili.mirror([_record()], items), 1)
            self.assertEqual(bili.mirror([_record()], items), 0)
            self.assertEqual(len(bili._read_jsonl(items / "bilibili.jsonl")), 1)

    def test_overview_writes_md_and_json(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            out = Path(tmp) / "out"
            bili.store([_record()], root)
            day = bili.day_of(_record())
            md, js = bili.overview(day, bili.load_config(), root, out)
            self.assertTrue(md.exists() and js.exists())
            text = md.read_text(encoding="utf-8")
            self.assertIn("B站Gal", text)
            self.assertIn("HOOKSOFT公式", text)
            self.assertEqual(json.loads(js.read_text(encoding="utf-8"))["count"], 1)


class RequestShapeTests(unittest.TestCase):
    def test_device_params_and_feed_endpoint(self):
        self.assertEqual(bili.FEED_URL,
                         "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space")
        for key in ("dm_img_list", "dm_img_str", "dm_cover_img_str", "dm_img_inter"):
            self.assertIn(key, bili.DEVICE_PARAMS)

    def test_sign_wbi_is_deterministic_with_a_pinned_key(self):
        import hashlib
        import types
        import urllib.parse
        original_key, original_time = bili.wbi_mixin_key, bili.time
        bili.wbi_mixin_key = lambda cookies, timeout: "A" * 32
        bili.time = types.SimpleNamespace(time=lambda: 1700000000)
        try:
            params = {"host_mid": UID, "timezone_offset": "-480"}
            one = bili.sign_wbi(dict(params), {}, 1.0)
            two = bili.sign_wbi(dict(params), {}, 1.0)
        finally:
            bili.wbi_mixin_key, bili.time = original_key, original_time
        self.assertEqual(one["wts"], "1700000000")
        self.assertEqual(len(one["w_rid"]), 32)
        self.assertEqual(one["w_rid"], two["w_rid"])
        canonical = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(one.items()) if k != "w_rid"
        )
        self.assertEqual(
            one["w_rid"],
            hashlib.md5((canonical + "A" * 32).encode("utf-8")).hexdigest(),
        )

    def test_sign_wbi_degrades_to_unsigned_when_key_missing(self):
        original = bili.wbi_mixin_key
        bili.wbi_mixin_key = lambda cookies, timeout: ""
        try:
            params = {"host_mid": UID}
            self.assertEqual(bili.sign_wbi(params, {}, 1.0), params)
        finally:
            bili.wbi_mixin_key = original


if __name__ == "__main__":
    unittest.main()
