#!/usr/bin/env python3
"""按作品名查 VNDB，吐出「厂牌 + 发售年」的脚注草稿。

背景：站点每篇笔记都要给游戏作品加脚注（制作/发行方 + 发售年，主线作品给到日），
以前靠手搜官网和 VNDB 网页。2026-10-31 起统一走 VNDB 的公开 API v2，不再用月幕
（月幕没有人物反查、限流更紧、`mode=accurate` 会串到同名老作品）。

VNDB 这边的情况：
- 公开查询不需要 token，限流 200 次 / 5 分钟；结果落在 `.cache/vndb/`，同一关键词
  第二次零请求（缓存 30 天）。
- 中文名取 `titles[lang=zh-Hans]`；没有就退回日文原名（`alttitle`）。厂牌取
  `developers[].original`（没有则 `name`），与站内「SAGA PLANETS / Frontwing」写法一致。
- 18 禁与否不猜，读该作品最早一次正式版的 `has_ero` / `minage`。
- **日期可能差一天**：Steam 独占或跨时区发售的作品，VNDB 与 Steam 会差一天
  （ATRI：VNDB 2020-06-18 / Steam 2020-06-19）。写进正文前对一眼官方或 Steam。

匹配策略是「宁可报错也不猜」：只在标题（含中日英别名、罗马字）完全相等时才自动取；
搜索到多条又没一条完全相等，就列出候选、退出码 2，让人用 `--pick` 指定。

用法：

    python scripts/vndb_game.py 金色ラブリッチェ
    python scripts/vndb_game.py 金色ラブリッチェ --pick 2
    python scripts/vndb_game.py --id v21852
    python scripts/vndb_game.py ATRI --json
    python scripts/vndb_game.py 月姬 --refresh

退出码：0 = 命中并输出脚注；2 = 需要人挑（候选列表）或查不到；1 = 网络/接口错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.vndb.org/kana"
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "vndb"
CACHE_TTL = 30 * 24 * 3600

# VNDB 要求一个能识别调用方的 UA，别用默认的 Python-urllib。
UA = "EpsilonGG-site-tool/0.1 (+https://github.com/EpsilonGG)"

VN_FIELDS = (
    "id,title,alttitle,titles{lang,title,latin,official},released,"
    "developers{id,name,original},platforms,image.url,olang"
)
REL_FIELDS = (
    "id,title,released,platforms,minage,has_ero,official,freeware,patch,"
    "vns{id,rtype},producers{name,original,developer,publisher}"
)
CACHE_VERSION = 2

PLATFORM_LABEL = {
    "win": "PC",
    "ps4": "PS4",
    "ps5": "PS5",
    "psv": "PS Vita",
    "psp": "PSP",
    "ps3": "PS3",
    "ps2": "PS2",
    "swi": "Switch",
    "and": "Android",
    "ios": "iOS",
    "web": "Web",
    "vnd": "FOMA",
    "mob": "手机",
    "lin": "Linux",
    "mac": "macOS",
}


class ApiError(RuntimeError):
    pass


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"User-Agent": UA, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 429:
            raise ApiError("VNDB 限流（200 次 / 5 分钟），等几分钟再跑") from exc
        raise ApiError(f"VNDB 返回 {exc.code}：{detail}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(
            f"连不上 VNDB（{exc.reason}）。这台机器要走代理：\n"
            "  export https_proxy=http://127.0.0.1:7897"
        ) from exc


def _cache_path(key: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.json"


def cache_read(key: str, ttl: int = CACHE_TTL) -> dict | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if ttl and time.time() - payload.get("_cached_at", 0) > ttl:
        return None
    return payload.get("data")


def cache_write(key: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"_key": key, "_cached_at": time.time(), "data": data}
    _cache_path(key).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def search_vn(keyword: str, limit: int = 10) -> list[dict]:
    data = _post(
        "/vn",
        {
            "filters": ["search", "=", keyword],
            "fields": VN_FIELDS,
            "sort": "searchrank",
            "results": limit,
        },
    )
    return data.get("results") or []


def fetch_vn(vid: str) -> dict:
    data = _post("/vn", {"filters": ["id", "=", vid], "fields": VN_FIELDS, "results": 1})
    results = data.get("results") or []
    if not results:
        raise ApiError(f"VNDB 上没有 {vid}")
    return results[0]


def fetch_releases(vid: str) -> list[dict]:
    data = _post(
        "/release",
        {
            "filters": ["vn", "=", ["id", "=", vid]],
            "fields": REL_FIELDS,
            "sort": "released",
            "results": 50,
        },
    )
    return data.get("results") or []


def norm(text: str) -> str:
    """全半角、大小写、空格与常见分隔符都不参与比对。"""
    text = unicodedata.normalize("NFKC", text or "").lower()
    for ch in " 　~～〜・:：-－—–_、,，.。'\"「」『』()（）[]【】":
        text = text.replace(ch, "")
    return text


def title_variants(vn: dict) -> list[str]:
    """参与「完全匹配」判断的标题，含罗马字转写（用户可能只记得英文名）。"""
    out = [vn.get("title") or "", vn.get("alttitle") or ""]
    for item in vn.get("titles") or []:
        out.extend([item.get("title") or "", item.get("latin") or ""])
    return [t for t in out if t]


def display_aliases(vn: dict) -> list[str]:
    """展示用的别名，只留中日英，转写和韩俄译本不列。"""
    out = []
    for item in vn.get("titles") or []:
        if item.get("lang") in {"ja", "en", "zh-Hans", "zh-Hant"} and item.get("title"):
            out.append(item["title"])
    return list(dict.fromkeys(out))


def display_name(vn: dict) -> tuple[str, str]:
    """返回（中文名，日文原名）。中文名缺失时两者相同。"""
    ja = vn.get("alttitle") or vn.get("title") or ""
    zh = None
    for item in vn.get("titles") or []:
        if item.get("lang") == "zh-Hans" and item.get("title"):
            zh = item["title"]
            break
    if zh is None:
        for item in vn.get("titles") or []:
            if item.get("lang") == "zh-Hant" and item.get("title"):
                zh = item["title"]
                break
    return (zh or ja), ja


def developer_names(vn: dict) -> list[str]:
    names = []
    for dev in vn.get("developers") or []:
        names.append(dev.get("original") or dev.get("name") or "")
    return [n for n in names if n]


def pick_release(vn: dict, releases: list[dict]) -> dict | None:
    """找出「这部作品的正式版」那一次发售。

    只看标题会翻车：VNDB 上不少作品的第一次发售是体验版（`rtype=trial`），
    《樱之诗》就有 2008 年的体验版，照它写会变成「2008 年发售、全年龄」。
    所以要求 vns 里这部作品的 rtype 是 complete，再优先与 VN 自己的
    `released`（VNDB 认定的首发日）同一天、且是 PC 版的那一条。
    """
    complete = [
        rel
        for rel in releases
        if rel.get("official")
        and not rel.get("patch")
        and not rel.get("freeware")
        and any(
            link.get("id") == vn["id"] and link.get("rtype") == "complete"
            for link in (rel.get("vns") or [])
        )
    ]
    if not complete:
        return None
    same_day = [rel for rel in complete if rel.get("released") == vn.get("released")]
    pool = same_day or complete
    pc = [rel for rel in pool if "win" in (rel.get("platforms") or [])]
    return sorted(pc or pool, key=lambda rel: rel.get("released") or "9999")[0]


def fmt_date(released: str | None) -> str:
    if not released or released in {"TBA", "unknown"}:
        return "未定"
    parts = released.split("-")
    if len(parts) == 3:
        return f"{int(parts[0])} 年 {int(parts[1])} 月 {int(parts[2])} 日"
    if len(parts) == 2:
        return f"{int(parts[0])} 年 {int(parts[1])} 月"
    if len(parts) == 1 and parts[0].isdigit():
        return f"{int(parts[0])} 年"
    return released


def platform_label(vn: dict, release: dict | None) -> str:
    plats = (release or {}).get("platforms") or vn.get("platforms") or []
    if "win" in plats:
        return "PC"
    for code in plats:
        if code in PLATFORM_LABEL:
            return PLATFORM_LABEL[code]
    return PLATFORM_LABEL.get(plats[0], plats[0]) if plats else "PC"


def is_adult(release: dict | None) -> bool:
    if not release:
        return False
    if release.get("has_ero"):
        return True
    return (release.get("minage") or 0) >= 18


def publisher_names(vn: dict, release: dict | None) -> list[str]:
    """发行方：只在和开发方不同时才列（多数作品是同一家）。"""
    if not release:
        return []
    devs = set(developer_names(vn))
    out = []
    for prod in release.get("producers") or []:
        if prod.get("publisher") and not prod.get("developer"):
            name = prod.get("original") or prod.get("name") or ""
            if name and name not in devs:
                out.append(name)
    return out


def build_record(vn: dict, releases: list[dict]) -> dict:
    zh, ja = display_name(vn)
    rel = pick_release(vn, releases)
    devs = developer_names(vn)
    return {
        "id": vn["id"],
        "url": f"https://vndb.org/{vn['id']}",
        "title_zh": zh,
        "title_ja": ja,
        "titles": display_aliases(vn),
        "developers": devs,
        "publishers": publisher_names(vn, rel),
        # 日期以 VN 的 released 为准（VNDB 认定的首发日），版本只用来判 18 禁与平台
        "released": vn.get("released"),
        "release_id": (rel or {}).get("id"),
        "release_date": vn.get("released"),
        "platform": platform_label(vn, rel),
        "adult": is_adult(rel),
        "platforms": vn.get("platforms") or [],
    }


def has_cjk(text: str) -> bool:
    return any("\u3040" <= ch <= "\u9fff" or "\u30a0" <= ch <= "\u30ff" for ch in text)


def footnote_title(rec: dict) -> str:
    """脚注里的作品名：中文名优先，但全拉丁的标题保持原名（《ATRI -My Dear Moments-》）。"""
    ja, zh = rec["title_ja"], rec["title_zh"]
    if not zh or zh == ja:
        return ja
    if not has_cjk(ja):
        return ja
    return zh


def footnote(rec: dict) -> str:
    dev = "、".join(rec["developers"]) or "（厂牌待补）"
    if rec.get("publishers"):
        dev += f"（发行：{'、'.join(rec['publishers'])}）"
    ero = "18 禁 " if rec["adult"] else ""
    # 厂牌是拉丁字母时要空一格，全角括号结尾时不空
    sep = "" if dev.endswith("）") else " "
    return (
        f"《{footnote_title(rec)}》。{dev}{sep}于 {fmt_date(rec['release_date'])}"
        f"发售的 {ero}{rec['platform']} 游戏。"
    )


def render(rec: dict) -> str:
    head = (
        f"{rec['title_ja']}  ({rec['id']})"
        if rec["title_zh"] == rec["title_ja"]
        else f"{rec['title_ja']}  →  {rec['title_zh']}  ({rec['id']})"
    )
    lines = [
        head,
        f"  厂牌    {'、'.join(rec['developers']) or '（VNDB 未填）'}",
    ]
    if rec.get("publishers"):
        lines.append(f"  发行    {'、'.join(rec['publishers'])}")
    lines.append(
        f"  发售    {rec['release_date']}"
        f"（{rec['platform']} / {'18 禁' if rec['adult'] else '全年龄'}）"
    )
    others = [t for t in rec["titles"] if t not in {rec["title_ja"], rec["title_zh"]}]
    if others:
        lines.append("  别名    " + " / ".join(others))
    lines.append(f"  链接    {rec['url']}")
    lines.append(f"  脚注    {footnote(rec)}")
    return "\n".join(lines)


def render_candidates(results: list[dict], keyword: str) -> str:
    lines = [f"「{keyword}」没有完全匹配的作品，挑一条重跑（--pick N）：", ""]
    for idx, vn in enumerate(results, 1):
        zh, ja = display_name(vn)
        devs = "、".join(developer_names(vn)) or "-"
        lines.append(
            f"  {idx}. {vn['id']}  {ja}  |  {zh}  |  {vn.get('released') or '未定'}  |  {devs}"
        )
    lines.append("")
    lines.append(f"  python scripts/vndb_game.py {keyword!r} --pick 1")
    return "\n".join(lines)


def resolve(args: argparse.Namespace) -> tuple[dict | None, str]:
    """返回（记录, 候选文本）。记录为 None 时说明需要人挑或查不到。"""
    ttl = 0 if args.refresh else CACHE_TTL
    key = f"v{CACHE_VERSION}:id:{args.id}" if args.id else f"v{CACHE_VERSION}:q:{norm(args.keyword)}"
    if args.pick:
        # 人工挑过的结果单独存，别让同一个关键词下次直接拿到它
        key += f"#{args.pick}"

    if not args.no_cache:
        cached = cache_read(key, ttl)
        if cached:
            return cached, ""

    if args.id:
        vn = fetch_vn(args.id)
        candidates = [vn]
    else:
        candidates = search_vn(args.keyword)
        if not candidates:
            return None, f"VNDB 搜不到「{args.keyword}」。换个写法（日文原名 / 罗马字）再试。"

    target = None
    if args.pick:
        if args.pick > len(candidates):
            return None, f"只有 {len(candidates)} 条候选，--pick {args.pick} 越界。"
        target = candidates[args.pick - 1]
    else:
        wanted = norm(args.keyword) if args.keyword else ""
        exact = [c for c in candidates if wanted and wanted in {norm(t) for t in title_variants(c)}]
        if len(exact) == 1:
            target = exact[0]
        elif len(candidates) == 1:
            target = candidates[0]

    if target is None:
        return None, render_candidates(candidates, args.keyword or args.id)

    releases = fetch_releases(target["id"])
    rec = build_record(target, releases)
    if not args.no_cache:
        cache_write(key, rec)
        cache_write(f"v{CACHE_VERSION}:id:{rec['id']}", rec)
    return rec, ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按作品名查 VNDB，输出厂牌 + 发售年的脚注草稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python scripts/vndb_game.py 金色ラブリッチェ\n"
            "  python scripts/vndb_game.py 月姬 --pick 2\n"
            "  python scripts/vndb_game.py --id v21852 --json"
        ),
    )
    parser.add_argument("keyword", nargs="?", help="作品名（日文原名 / 中文名 / 罗马字都行）")
    parser.add_argument("--id", help="直接给 VNDB id，如 v21852（与作品名二选一）")
    parser.add_argument("--pick", type=int, help="候选列表里的序号，从 1 开始")
    parser.add_argument("--json", action="store_true", help="输出 JSON，给别的脚本用")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存重新查")
    parser.add_argument("--no-cache", action="store_true", help="不读也不写缓存")
    args = parser.parse_args()

    if not args.keyword and not args.id:
        parser.error("给一个作品名，或者 --id v21852")
    if args.keyword and args.id:
        parser.error("作品名和 --id 只能给一个")

    try:
        rec, note = resolve(args)
    except ApiError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    if rec is None:
        print(note, file=sys.stderr)
        return 2

    print(json.dumps(rec, ensure_ascii=False, indent=1) if args.json else render(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
