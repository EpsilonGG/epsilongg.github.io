#!/usr/bin/env python3
"""B 站动态日抓 —— Galgame 日报的第二个数据源（`source_id=bilibili`）。

背景
----
前期调研过四个 B 站开源实现（Go CLI、两个 nonebot 插件、一个 pnpm 工作区），
都不能直接跑：没有 Go 工具链 / 绑死 QQ 机器人与 aiosqlite / 要整个 pnpm workspace。
参考实现已经清理掉，这里把它们可复用的三件事用 Python 标准库重写：

* `x/polymer/web-dynamic/v1/feed/space` 的调用形状；
* buvid3/buvid4 匿名引导与 `dm_img_*` 设备指纹；
* 「首轮只建基线 + 按 id 去重」的增量思路。

**名单与 X 抓取管线彻底分家**（2026-11-11 用户裁决）：监控账号的正本只有
`src/config/daily-bilibili-galgame.json` 这一份，X 名单
`src/config/daily-roster-galgame.json` 里不出现任何 `bili_*` / `bili_gal`；
站点查询层与日报名单层各自单独读入这份 B 站名单。

实测结论（2026-11-11，HOOKSOFT公式 UID 3632310624717268）
--------------------------------------------------------
* 旧接口 `api.vc.bilibili.com/dynamic_svr/v1/...` 已下线，404。
* 新接口**匿名裸请求一律 HTTP 412**；必须带 buvid 系列 Cookie 与 `dm_img_*` 设备参数。
* **WBI 签名有用**：同一时段 A/B 各 8 次，签名 4/8 拿到 13 条、不签名 1/8
  （`_bili_probe4.py`）。一开始误判成「签名反被拒」，其实只是风控命中率抖动——
  这个接口的 `-352` / `code=0 但 0 条` 都是**概率性**的，小样本结论不可靠。
  所以默认签名，同时保留少量不签名尝试做兜底。
* 可用组合：`timezone_offset=-480` + `dm_img_*` 设备参数 + 每次新取的 buvid 系列 Cookie
  + WBI 签名（wts / w_rid）+ 精简请求头（只要 UA / Referer，**不要** Origin / sec-ch-ua）。
* 匿名请求有概率被风控（HTTP 412 / code=-352 / code=0 但 0 条），单次成功率约 1/3～1/2，
  所以必须**换新的 buvid 重试**。默认 16 次预算，实测能稳定拿到全部 13 条动态。
  若配了登录 Cookie（`BILI_COOKIE` 或 secrets 文件），风控概率显著下降，仍保留重试兜底。

数据流
------
    feed/space → 归一化 NormalizedItem → data/bilibili/galgame/<JST日>.jsonl（正本，提交进仓库）
                                    ↘ .xreader/data-galgame/items/bilibili.jsonl（镜像，给 daily build 读）

`daily_prepare.py::items_dir_for()` 会优先读 `.xreader/data-galgame/items/`，
`scan_day()` / `XReaderAdapter` 只认 `*.jsonl` 和 `published_at`，所以**日报管线一行都不用改**：
B 站动态会以 `[bilibili:<动态id>]` 的来源 key 出现在 briefing / generate.json / 题面里，
可被 LLM 引到 highlights / works / people。名单里的 `bili_gal` 栏目负责页面上的显示名与筛选按钮。

用法
----
    python scripts/bilibili_daily.py check
    python scripts/bilibili_daily.py fetch                    # 抓取 + 落盘 + 镜像 + 最新一天的内容概况
    python scripts/bilibili_daily.py fetch --date 2026-11-10
    python scripts/bilibili_daily.py fetch --dry-run          # 只探测，不写文件
    python scripts/bilibili_daily.py sync                     # 从正本重建镜像
    python scripts/bilibili_daily.py overview --date 2026-11-10

退出码：0 成功；2 配置/名单错；3 抓取全被风控拒绝；4 参数错。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "src" / "config" / "daily-bilibili-galgame.json"
DATA_ROOT = REPO_ROOT / "data" / "bilibili" / "galgame"
XREADER_ITEMS = REPO_ROOT / ".xreader" / "data-galgame" / "items"
OUT_ROOT = REPO_ROOT / "out"

JST = timezone(timedelta(hours=9))
UTC = timezone.utc
SOURCE_ID = "bilibili"
TAG = "B站Gal"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REFERER = "https://www.bilibili.com/"
SPI_URL = "https://api.bilibili.com/x/frontend/finger/spi"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
FEED_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"

# WBI 签名用的固定置换表（B 站 Web 端公开算法，与前期参考实现一致）。
MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)
WBI_TTL = 1800  # mixin key 半小时一换够了，键本身按天轮换

# 设备指纹：B 站风控只检查「有没有、像不像浏览器」，不校验真实设备。
DEVICE_PARAMS = {
    "dm_img_list": "[]",
    "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
    "dm_cover_img_str": (
        "QU5HTEUgKEludGVsLCBJbnRlbChSKSBVSEQgR3JhcGhpY3MgKDB4MDAwMDlCQzQpIERpcmVjdDNEMTEg"
        "dnNfNV8wIHBzXzVfMCwgRDNEMTEpR29vZ2xlIEluYy4gKEludGVsKQ"
    ),
    "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
}

COOKIE_FILE = Path.home() / ".workbuddy-ai" / "secrets" / "bilibili_cookie"


class Refused(Exception):
    """风控拒绝（412 / -352 / 静默空页）。调用方换新 buvid 重试。"""


# -- 配置 ---------------------------------------------------------------

def load_config(path: Path = CONFIG_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    accounts = data.get("accounts") or []
    seen: set[str] = set()
    for a in accounts:
        uid = str(a.get("uid") or "").strip()
        if not uid.isdigit():
            raise ValueError(f"账号 {a.get('name')!r} 的 uid 不是纯数字：{uid!r}")
        if uid in seen:
            raise ValueError(f"uid 重复：{uid}")
        seen.add(uid)
        if not str(a.get("handle") or "").strip():
            raise ValueError(f"账号 {a.get('name')!r} 缺 handle")
        if TAG not in (a.get("tags") or []):
            raise ValueError(f"账号 {a.get('name')!r} 没打 {TAG} 分类标签")
    if (data.get("source_id") or SOURCE_ID) != SOURCE_ID:
        raise ValueError("source_id 必须是 bilibili")
    return data


def active_accounts(config: dict) -> list[dict]:
    return [a for a in config.get("accounts") or [] if a.get("active", True) is not False]


def check_config(config: dict) -> list[str]:
    """B 站名单正本的**自洽**校验（2026-11-11 用户裁决）。

    绝不读 X 名单：两条名单 / 抓取管线各自独立，新增 B 站监控号只改
    `src/config/daily-bilibili-galgame.json` 一处。站点查询层与日报名单层
    都从这份文件派生，所以这里把「它们要读的字段」逐一验齐。
    """
    problems: list[str] = []
    if (config.get("source_id") or SOURCE_ID) != SOURCE_ID:
        problems.append("source_id 必须是 bilibili")
    cat = config.get("category") or {}
    cat_id, cat_label = str(cat.get("id") or ""), str(cat.get("label") or "")
    if cat_label != TAG:
        problems.append(f"category.label 应为 {TAG}，实际 {cat_label!r}")
    if not cat_id:
        problems.append("缺 category.id")
    categories = config.get("categories") or []
    if not any(str(c.get("id")) == cat_id and str(c.get("label")) == TAG
               for c in categories):
        problems.append(f"categories 缺 {cat_id} / {TAG}（站点查询层与日报名单层都读它）")
    if not (config.get("accounts") or []):
        problems.append("监控账号为空")
    for a in config.get("accounts") or []:
        uid = str(a.get("uid") or "")
        handle = str(a.get("handle") or "")
        name = str(a.get("name") or "")
        if not name:
            problems.append(f"{uid} 缺 name（页面会显示裸 handle）")
        if handle != "bili_" + uid:
            problems.append(f"{uid} 的 handle 应为 bili_<uid>，实际 {handle!r}")
        if str(a.get("source")) != SOURCE_ID:
            problems.append(f"{handle} 缺 source=bilibili")
        if str(a.get("category")) != cat_id:
            problems.append(f"{handle} 的 category 应为 {cat_id}")
        if TAG not in (a.get("tags") or []):
            problems.append(f"{handle} 没打 {TAG} 标签")
        url = str(a.get("profile_url") or "")
        if not url.startswith("https://space.bilibili.com/" + uid + "/"):
            problems.append(f"{handle} 的 profile_url 不是该 UID 的 B 站空间：{url!r}")
    return problems


# -- HTTP ---------------------------------------------------------------

def _opener() -> urllib.request.OpenerDirector:
    proxy = os.environ.get("BILI_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener()


def _get(url: str, params: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params), headers=headers
    )
    with _opener().open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def fresh_cookies(timeout: float) -> dict:
    """每次重试都换一套匿名 buvid——风控是按 buvid 会话记的。"""
    payload = _get(SPI_URL, {}, {"User-Agent": UA, "Referer": REFERER}, timeout)
    body = payload.get("data") or {}
    if not body.get("b_3"):
        raise Refused("finger/spi 没返回 b_3")
    now = int(time.time())
    return {
        "buvid3": body["b_3"],
        "buvid4": body.get("b_4", ""),
        "b_nut": str(now),
        "b_lsid": f"{(now % 0xFFFFFF) | 0x100000:X}_{now * 1000:X}".upper(),
        "_uuid": "%08X-%04X-%04X-%04X-%012Xinfoc" % (
            now & 0xFFFFFFFF, now & 0xFFFF, now & 0xFFFF, now & 0xFFFF, now
        ),
    }


def login_cookies() -> dict:
    """可选：登录 Cookie 能大幅降低风控概率。不写进仓库，只从环境/本地 secrets 读。"""
    raw = os.environ.get("BILI_COOKIE", "").strip()
    if not raw and COOKIE_FILE.exists():
        raw = COOKIE_FILE.read_text(encoding="utf-8").strip()
    out: dict = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            if k and v:
                out[k] = v
    return out


_WBI_CACHE: dict = {"key": "", "at": 0.0}


def wbi_mixin_key(cookies: dict, timeout: float) -> str:
    """从 `/x/web-interface/nav` 取当天的 img/sub key，混成 32 位 mixin key。

    短时缓存：一次 fetch 会重试很多轮，没必要每轮都多打一次 nav。
    拿不到就返回空串，调用方退回不签名请求，不让签名本身成为新的失败点。
    """
    now = time.time()
    if _WBI_CACHE["key"] and now - _WBI_CACHE["at"] < WBI_TTL:
        return _WBI_CACHE["key"]
    headers = {"User-Agent": UA, "Referer": REFERER}
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    try:
        payload = _get(NAV_URL, {}, headers, timeout)
        wbi = (payload.get("data") or {}).get("wbi_img") or {}
        stem = lambda u: str(u).rsplit("/", 1)[-1].rsplit(".", 1)[0]
        raw = stem(wbi.get("img_url") or "") + stem(wbi.get("sub_url") or "")
        key = "".join(raw[i] for i in MIXIN_KEY_ENC_TAB if i < len(raw))[:32]
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, ValueError, KeyError, TypeError, AttributeError):
        return ""
    if len(key) == 32:
        _WBI_CACHE.update(key=key, at=now)
        return key
    return ""


def sign_wbi(params: dict, cookies: dict, timeout: float) -> dict:
    """按 WBI 口径加 `wts` / `w_rid`；拿不到 mixin key 就原样返回。"""
    key = wbi_mixin_key(cookies, timeout)
    if not key:
        return params
    signed = dict(params)
    signed["wts"] = str(int(time.time()))
    parts = []
    for name in sorted(signed):
        value = str(signed[name])
        for char in "!'()*":
            value = value.replace(char, "")
        parts.append(
            urllib.parse.quote(name, safe="") + "=" + urllib.parse.quote(value, safe="")
        )
    signed["w_rid"] = hashlib.md5(("&".join(parts) + key).encode("utf-8")).hexdigest()
    return signed


def feed_page(uid: str, offset: str, cookies: dict, timeout: float,
              *, signed: bool = True, accept: bool = False) -> dict:
    params = {
        "host_mid": uid,
        "timezone_offset": "-480",
        "features": "itemOpusStyle",
        "platform": "web",
        "web_location": "333.999",
    }
    params.update(DEVICE_PARAMS)
    if offset:
        params["offset"] = offset
    headers = {"User-Agent": UA, "Referer": REFERER}
    # 实测：Origin / sec-ch-ua 反而触发 -352；这里最多只多带一个 Accept。
    if accept:
        headers["Accept"] = "application/json, text/plain, */*"
    ck = dict(cookies)
    ck.update(login_cookies())
    if ck:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in ck.items())
    if signed:
        params = sign_wbi(params, ck, timeout)
    try:
        payload = _get(FEED_URL, params, headers, timeout)
    except urllib.error.HTTPError as exc:
        raise Refused(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Refused(f"网络错误 {type(exc).__name__}") from exc
    if payload.get("code") != 0:
        raise Refused(f"code={payload.get('code')} {payload.get('message')}")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise Refused("data 不是对象")
    return data


def fetch_dynamics(uid: str, *, max_attempts: int = 16, timeout: float = 15.0,
                   max_pages: int = 4, pause: float = 0.8, log=print) -> list[dict]:
    """抓一个 UID 的动态列表；每次尝试换 buvid，被拒就退避重试。"""
    items: list[dict] = []
    offset = ""
    for page in range(max_pages):
        page_items: list[dict] = []
        has_more = False
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            try:
                cookies = fresh_cookies(timeout)
                # 签名命中率高但偶尔也被拒；每 4 次留一次不签名，避免「签名路径
                # 本身出问题」时整轮全灭。Accept 头同理，只是轻度轮换。
                data = feed_page(
                    uid, offset, cookies, timeout,
                    signed=(attempt % 4 != 0),
                    accept=(attempt % 3 == 2),
                )
            except Refused as exc:
                last_error = str(exc)
                log(f"    第 {attempt}/{max_attempts} 次被拒：{last_error}")
                if attempt < max_attempts:
                    time.sleep(min(pause * attempt, 4.0))
                continue
            page_items = [i for i in (data.get("items") or []) if i.get("id_str")]
            has_more = bool(data.get("has_more"))
            offset = str(data.get("offset") or "")
            # 首页空 = 风控静默拒绝（正常账号不会一条都没有）；翻页空才算到底。
            if page == 0 and not page_items:
                log(f"    第 {attempt}/{max_attempts} 次返回空页，按风控重试")
                if attempt < max_attempts:
                    time.sleep(min(pause * attempt, 4.0))
                continue
            log(f"    第 {attempt} 次成功：本页 {len(page_items)} 条")
            break
        else:
            raise Refused(
                f"UID {uid} 连续 {max_attempts} 次被风控拒绝（第 {page + 1} 页，最后：{last_error}）"
            )
        items.extend(page_items)
        if not has_more or not offset or not page_items:
            break
        time.sleep(pause)
    return items


# -- 归一化 -------------------------------------------------------------

def _text_of(item: dict) -> tuple[str, str, list[dict]]:
    """返回 (正文, 标题, 图片列表)。

    `features=itemOpusStyle` 会把图文动态升级成 opus：正文搬进
    `module_dynamic.major.opus.summary.text`，老的 `desc.text` 变成 null。
    视频/专栏/转发各有自己的 major 分支，逐个兜住，别把正文丢成空串。
    """
    dyn = ((item.get("modules") or {}).get("module_dynamic") or {})
    desc = ((dyn.get("desc") or {}).get("text") or "").strip()
    major = dyn.get("major") or {}
    title = ""
    text = desc
    pics: list[dict] = []

    opus = major.get("opus") or {}
    if opus:
        title = str(opus.get("title") or "").strip()
        summary = (opus.get("summary") or {}).get("text") or ""
        if summary.strip():
            text = summary.strip()
        for pic in opus.get("pics") or []:
            if pic.get("url"):
                pics.append({"type": "image", "url": pic["url"]})
    if not text:
        archive = major.get("archive") or {}
        article = major.get("article") or {}
        text = str(archive.get("title") or article.get("title") or "").strip()
        if archive.get("desc"):
            text = (text + "\n" + str(archive["desc"])).strip()
    draw = major.get("draw") or {}
    for pic in draw.get("items") or []:
        if pic.get("src"):
            pics.append({"type": "image", "url": pic["src"]})

    # 转发动态：正文可能在 orig 里，补一行说明 + 原作者。
    orig = item.get("orig") or {}
    if orig:
        orig_text, orig_title, orig_pics = _text_of(orig)
        author = ((orig.get("modules") or {}).get("module_author") or {}).get("name") or ""
        if orig_text or orig_title:
            label = f"转发 {author}：" if author else "转发："
            extra = (orig_title + "\n" + orig_text).strip() if orig_title else orig_text
            text = (text + "\n" + label + extra).strip() if text else label + extra
        pics = pics or orig_pics
    return text, title, pics


def _url_of(item: dict) -> str:
    basic = item.get("basic") or {}
    jump = str(basic.get("jump_url") or "")
    if not jump:
        major = ((item.get("modules") or {}).get("module_dynamic") or {}).get("major") or {}
        jump = str((major.get("opus") or {}).get("jump_url") or "")
    if jump.startswith("//"):
        return "https:" + jump
    if jump.startswith("http"):
        return jump
    return f"https://www.bilibili.com/opus/{item.get('id_str')}"


def normalize(item: dict, account: dict, fetched_at: str) -> dict:
    """一条动态 → X-Reader 形状的 `NormalizedItem`（日报管线只认这些字段）。"""
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    stat = modules.get("module_stat") or {}
    dynamic_id = str(item.get("id_str") or "").strip()
    ts = int(author.get("pub_ts") or 0)
    published = datetime.fromtimestamp(ts, UTC).isoformat() if ts else ""
    text, title, pics = _text_of(item)
    uid = str(account["uid"])
    dtype = str(item.get("type") or "")
    is_forward = dtype in ("DYNAMIC_TYPE_FORWARD", "DYNAMIC_TYPE_REPOST") or bool(item.get("orig"))
    orig_author = ((item.get("orig") or {}).get("modules") or {}).get("module_author") or {}
    publisher = str(orig_author.get("name") or author.get("name") or account["name"])
    content = (title + "\n" + text).strip() if title and title not in text else text

    def count(key: str) -> int:
        node = stat.get(key) or {}
        return int(node.get("count") or 0) if isinstance(node, dict) else 0

    return {
        "identity_key": f"{SOURCE_ID}:{dynamic_id}",
        "source_id": SOURCE_ID,
        "item_id": dynamic_id,
        "content": content,
        "publisher": publisher,
        "canonical_url": _url_of(item),
        "published_at": published,
        "published_precision": "second",
        "fetched_at": fetched_at,
        "media": pics,
        "metadata": {
            "account": account["handle"],
            "uid": uid,
            "dynamic_type": dtype,
            "title": title,
            "is_retweet": is_forward,
            "is_reply": False,
            "is_quote": False,
            "stats": {
                "likes": count("like"),
                "retweets": count("forward"),
                "replies": count("comment"),
            },
            "provider": "web-dynamic/feed-space",
            "route": "anonymous-buvid",
            "tag": TAG,
        },
    }


# -- 存储 ---------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    """逐行读。**不能用 `read_text().splitlines()`**：`str.splitlines()` 会把 U+2028
    当换行，而 `json.dumps(ensure_ascii=False)` 不转义它——B 站动态正文里真有这个
    字符时，一条合法记录会被劈成两半静默丢掉（`daily/adapters/xreader.py` 踩过）。
    文件迭代只认 \\r / \\n，安全。
    """
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path.write_bytes(payload.encode("utf-8"))


def latest_day(root: Path = DATA_ROOT) -> date:
    """正本里最新的一天。没给 --date 时概况就出这天，不用猜「今天还是昨天」。"""
    days = []
    for path in root.glob("*.jsonl"):
        try:
            days.append(date.fromisoformat(path.stem))
        except ValueError:
            continue
    return max(days) if days else datetime.now(JST).date()


def day_of(record: dict) -> date | None:
    try:
        moment = datetime.fromisoformat(record["published_at"])
    except (ValueError, KeyError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(JST).date()


def store(records: list[dict], root: Path = DATA_ROOT) -> dict[date, int]:
    """按 JST 自然日 append，且**同 id 只存一次**。返回 {日期: 新增条数}。"""
    buckets: dict[date, dict[str, dict]] = {}
    for rec in records:
        day = day_of(rec)
        if day is None:
            continue
        buckets.setdefault(day, {})
    for day, bucket in buckets.items():
        for row in _read_jsonl(root / f"{day.isoformat()}.jsonl"):
            bucket[str(row.get("item_id") or "")] = row
    added: dict[date, int] = {}
    for rec in records:
        day = day_of(rec)
        if day is None:
            continue
        bucket = buckets[day]
        key = str(rec.get("item_id") or "")
        if key and key not in bucket:
            bucket[key] = rec
            added[day] = added.get(day, 0) + 1
    for day, bucket in buckets.items():
        rows = sorted(bucket.values(), key=lambda r: (r.get("published_at") or "", r.get("item_id") or ""))
        _write_jsonl(root / f"{day.isoformat()}.jsonl", rows)
    return added


def mirror(records: list[dict], items_dir: Path = XREADER_ITEMS) -> int:
    """把新记录 append 进 `daily build` 会读的 items 目录（同样按 id 去重）。"""
    path = items_dir / f"{SOURCE_ID}.jsonl"
    known = {str(r.get("item_id") or "") for r in _read_jsonl(path)}
    fresh = [r for r in records if str(r.get("item_id") or "") not in known]
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            for r in fresh:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(fresh)


def rebuild_mirror(root: Path = DATA_ROOT, items_dir: Path = XREADER_ITEMS) -> int:
    """从正本重建整份镜像（换机器 / `.xreader` 丢了时用）。"""
    rows: dict[str, dict] = {}
    for path in sorted(root.glob("*.jsonl")):
        for r in _read_jsonl(path):
            key = str(r.get("item_id") or "")
            if key:
                rows[key] = r
    ordered = sorted(rows.values(), key=lambda r: (r.get("published_at") or "", r.get("item_id") or ""))
    _write_jsonl(items_dir / f"{SOURCE_ID}.jsonl", ordered)
    return len(ordered)


# -- 概况 ---------------------------------------------------------------

def overview(day: date, config: dict, root: Path = DATA_ROOT,
             out_dir: Path = OUT_ROOT) -> tuple[Path, Path]:
    """出一份人读的「日报内容概况」：按账号分组列当天动态，供出稿时参考。"""
    accounts = active_accounts(config)
    by_handle = {str(a["handle"]): a for a in accounts}
    rows = [r for r in _read_jsonl(root / f"{day.isoformat()}.jsonl")
            if (day_of(r) == day and (r.get("metadata") or {}).get("account") in by_handle)]
    rows.sort(key=lambda r: (r.get("published_at") or "", r.get("item_id") or ""))

    lines = [f"# B 站动态概况 · {day.isoformat()}（JST）", "",
             f"> 分类标签：{TAG} · {len(accounts)} 个监控账号 / 当天 {len(rows)} 条动态", ""]
    for a in accounts:
        subset = [r for r in rows if (r.get("metadata") or {}).get("account") == a["handle"]]
        lines.append(f"## {a['name']}（UID {a['uid']}）")
        if not subset:
            lines += ["", "- 当天无动态", ""]
            continue
        lines.append("")
        for r in subset:
            moment = datetime.fromisoformat(r["published_at"]).astimezone(JST)
            dtype = (r.get("metadata") or {}).get("dynamic_type", "")
            title = (r.get("metadata") or {}).get("title") or ""
            body = " ".join((r.get("content") or "").split())
            if len(body) > 220:
                body = body[:220] + "…"
            lines.append(
                f"- [{moment:%H:%M} JST · `{dtype}`] "
                f"[{title or '动态'}]({r.get('canonical_url')}) — {body}"
            )
        lines.append("")
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"{day.isoformat()}.bilibili.md"
    js = out_dir / f"{day.isoformat()}.bilibili.json"
    md.write_text("\n".join(lines), encoding="utf-8")
    js.write_text(json.dumps({
        "date": day.isoformat(), "tag": TAG, "accounts": len(accounts),
        "count": len(rows), "items": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return md, js


# -- CLI ----------------------------------------------------------------

def _parse_day(value: str | None) -> date:
    if not value:
        return datetime.now(JST).date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"--date 要是 YYYY-MM-DD，收到 {value!r}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Galgame 日报 · B 站动态日抓")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="校验 B 站名单正本自洽（不读 X 名单）")

    f = sub.add_parser("fetch", help="抓取动态并落盘")
    f.add_argument("--date", help="JST 自然日（默认今天）；只影响概况与日志，不影响抓全量")
    f.add_argument("--config", type=Path, default=CONFIG_PATH)
    f.add_argument("--items-dir", type=Path, default=XREADER_ITEMS)
    f.add_argument("--data-root", type=Path, default=DATA_ROOT)
    f.add_argument("--max-attempts", type=int, default=16)
    f.add_argument("--timeout", type=float, default=15.0)
    f.add_argument("--max-pages", type=int, default=4)
    f.add_argument("--no-mirror", action="store_true", help="只写正本，不写 .xreader 镜像")
    f.add_argument("--no-overview", action="store_true", help="不生成人读的内容概况")
    f.add_argument("--dry-run", action="store_true", help="只探测，不写任何文件")

    s = sub.add_parser("sync", help="从正本重建 .xreader 镜像")
    s.add_argument("--data-root", type=Path, default=DATA_ROOT)
    s.add_argument("--items-dir", type=Path, default=XREADER_ITEMS)

    o = sub.add_parser("overview", help="生成某天的内容概况（Markdown + JSON）")
    o.add_argument("--date", required=True)
    o.add_argument("--config", type=Path, default=CONFIG_PATH)
    o.add_argument("--data-root", type=Path, default=DATA_ROOT)
    o.add_argument("--out", type=Path, default=OUT_ROOT)

    args = parser.parse_args(argv)
    try:
        config = load_config(args.config if hasattr(args, "config") else CONFIG_PATH)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    if args.command == "check":
        problems = check_config(config)
        if problems:
            for p in problems:
                print("✗ " + p, file=sys.stderr)
            return 2
        print(f"✓ {TAG} 名单正本自洽：{len(config['accounts'])} 个监控账号（与 X 名单无关）")
        return 0

    if args.command == "sync":
        n = rebuild_mirror(args.data_root, args.items_dir)
        print(f"镜像重建完成：{args.items_dir / (SOURCE_ID + '.jsonl')}（{n} 条）")
        return 0

    if args.command == "overview":
        try:
            day = _parse_day(args.date)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 4
        md, js = overview(day, config, args.data_root, args.out)
        print(f"概况：{md}\n      {js}")
        return 0

    # fetch
    accounts = active_accounts(config)
    if not accounts:
        print("名单里没有 active 的监控账号", file=sys.stderr)
        return 2
    fetched_at = datetime.now(UTC).isoformat()
    all_records: list[dict] = []
    failed: list[str] = []
    for a in accounts:
        print(f"抓取 {a['name']}（UID {a['uid']}）…")
        try:
            items = fetch_dynamics(
                str(a["uid"]), max_attempts=args.max_attempts,
                timeout=args.timeout, max_pages=args.max_pages,
            )
        except Refused as exc:
            print(f"  ✗ {exc}", file=sys.stderr)
            failed.append(f"{a['name']}: {exc}")
            continue
        records = [normalize(i, a, fetched_at) for i in items]
        print(f"  ✓ 拿到 {len(records)} 条动态")
        all_records.extend(records)

    if failed and not all_records:
        print("所有账号都被风控拒绝；未写任何文件", file=sys.stderr)
        return 3
    if args.dry_run:
        print(f"--dry-run：共 {len(all_records)} 条，未写文件")
        return 0

    added = store(all_records, args.data_root)
    total_new = sum(added.values())
    print(f"正本：新增 {total_new} 条，分布在 {len(added)} 个 JST 自然日")
    for day in sorted(added):
        print(f"  data/bilibili/galgame/{day.isoformat()}.jsonl +{added[day]}")
    if not args.no_mirror:
        n = rebuild_mirror(args.data_root, args.items_dir)
        print(f"镜像：{args.items_dir / (SOURCE_ID + '.jsonl')}（共 {n} 条）")
    if not args.no_overview:
        day = _parse_day(args.date) if args.date else latest_day(args.data_root)
        md, js = overview(day, config, args.data_root, OUT_ROOT)
        print(f"概况：{md}\n      {js}（{day.isoformat()} JST）")
    if failed:
        print("以下账号本次失败（正本与镜像仍按已抓到的写入）：", file=sys.stderr)
        for line in failed:
            print("  " + line, file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
