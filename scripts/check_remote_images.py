#!/usr/bin/env python3
"""检查文章里引用的远程图片是否还能访问。

「轻量化转载」允许图片直接引用原站 URL、不落仓库，代价是原站删图或改
路径时页面会挂坏图，而构建过程发现不了（构建只拼 HTML，不请求图片）。
这个脚本就是补这个洞：把 src/content/blog/*.md 里的 http(s) 图片全部请求
一遍，报出状态码、类型和体积。

用法：
    python scripts/check_remote_images.py
    python scripts/check_remote_images.py --proxy http://127.0.0.1:7897
    python scripts/check_remote_images.py --only mages-asada-makoto-interview
    python scripts/check_remote_images.py --write-dims   # 顺便记录宽高，供构建期用

`--write-dims` 会把每张远程图的宽高写进 `src/data/remote-images.json`，
构建时 `src/lib/markdown-images.mjs` 读它给远程图补 `width` / `height`，
避免图片加载前页面高度为 0 导致的跳动（CLS）。

退出码：全部正常为 0，有坏链为 1（便于以后接进 CI）。
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG_DIR = ROOT / "src" / "content" / "blog"
DIMS_PATH = ROOT / "src" / "data" / "remote-images.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 代码块里的 URL 不算（示例、命令都可能带图片地址）
FENCE_RE = re.compile(r"```.*?```", re.S)
MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(\s*<?(https?://[^\s)<>\"']+)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"'](https?://[^\"']+)[\"']", re.I)

# 单张图超过这个体积就提示一下：远程图没法压缩，太大会拖慢首屏
BIG_IMAGE_BYTES = 800 * 1024


def find_remote_images(text: str) -> list[tuple[int, str, str]]:
    """返回 [(行号, url, 写法)]，行号从 1 开始，写法是 "md" 或 "html"。

    代码块内的地址会被忽略。
    """

    # 把代码块替换成等量空行，保住行号
    def blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    stripped = FENCE_RE.sub(blank, text)
    found: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(stripped.splitlines(), start=1):
        for regex, kind in ((MD_IMG_RE, "md"), (HTML_IMG_RE, "html")):
            for match in regex.finditer(line):
                found.append((lineno, match.group(1), kind))
    return found


def build_opener(proxy: str | None) -> urllib.request.OpenerDirector:
    handlers: list[urllib.request.BaseHandler] = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        # 显式直连，避免环境变量里的代理影响结果
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def probe(opener: urllib.request.OpenerDirector, url: str, referer: str | None, timeout: float):
    """请求图片开头 2KB。返回 (状态码, content-type, 总字节数或 None, 错误信息)。"""
    headers = {"User-Agent": UA, "Range": "bytes=0-2047", "Accept": "image/*,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            length = response.headers.get("Content-Range", "").rpartition("/")[2]
            if not length.isdigit():
                length = response.headers.get("Content-Length", "")
            size = int(length) if length.isdigit() else None
            return response.status, content_type, size, None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", "") if exc.headers else "", None, str(exc)
    except Exception as exc:  # noqa: BLE001 - 网络异常种类多，统一记录
        return None, "", None, f"{type(exc).__name__}: {exc}"


def human_size(size: int | None) -> str:
    if size is None:
        return "—"
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size // 1024} KB"


# JPEG 里带尺寸的 SOF 标记（SOF0..SOF15，排除 DHT/JPG/DAC）
_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def image_size(data: bytes) -> tuple[int, int] | None:
    """从图片字节里读出宽高，不依赖 Pillow。

    支持 PNG / JPEG / GIF / WebP（VP8X、VP8、VP8L）。认不出来返回 None。
    """
    if len(data) < 32:
        return None

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)

    if data[:6] in (b"GIF87a", b"GIF89a"):
        width, height = struct.unpack("<HH", data[6:10])
        return int(width), int(height)

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return width, height
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8 ":
            # 帧头：3 字节起始码 + 2 字节宽 + 2 字节高（低 14 位）
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
            return width, height
        return None

    if data[:2] == b"\xff\xd8":
        pos = 2
        while pos + 9 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in _JPEG_SOF:
                height, width = struct.unpack(">HH", data[pos + 5 : pos + 9])
                return int(width), int(height)
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                pos += 2
                continue
            seg_len = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
            pos += 2 + seg_len
        return None

    return None


def fetch_bytes(opener: urllib.request.OpenerDirector, url: str, timeout: float) -> bytes | None:
    """整张图下载下来（`--write-dims` 需要完整字节才能读到尺寸）。"""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"},
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status >= 400:
                return None
            return response.read()
    except Exception:  # noqa: BLE001 - 网络异常种类多
        return None


def write_dimensions(entries: list[tuple[str, bytes]], path: Path = DIMS_PATH) -> int:
    """把 [(url, 字节)] 的宽高写进 JSON，返回成功条数。"""
    images: dict[str, dict[str, int]] = {}
    for url, data in entries:
        size = image_size(data)
        if not size:
            continue
        width, height = size
        if width <= 0 or height <= 0:
            continue
        images[url] = {"w": width, "h": height, "bytes": len(data)}

    payload = {
        "$comment": "由 scripts/check_remote_images.py --write-dims 生成，请勿手改。",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "images": images,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(images)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查文章里引用的远程图片是否可访问")
    parser.add_argument("--only", help="只检查文件名包含该字符串的文章")
    parser.add_argument("--timeout", type=float, default=20.0, help="单张图的超时秒数")
    parser.add_argument("--proxy", help="走代理，例如 http://127.0.0.1:7897")
    parser.add_argument("--quiet", action="store_true", help="只输出有问题的条目")
    parser.add_argument(
        "--write-dims",
        action="store_true",
        help="顺便把远程图的宽高写进 src/data/remote-images.json",
    )
    args = parser.parse_args(argv)

    if not BLOG_DIR.is_dir():
        print(f"找不到文章目录：{BLOG_DIR}", file=sys.stderr)
        return 2

    files = sorted(BLOG_DIR.glob("*.md"))
    if args.only:
        files = [p for p in files if args.only in p.name]
    if not files:
        print("没有匹配的文章。", file=sys.stderr)
        return 2

    opener = build_opener(args.proxy)
    total = 0
    broken: list[str] = []
    big: list[str] = []
    only_no_referer: list[str] = []
    raw_html: list[str] = []
    downloaded: dict[str, bytes] = {}

    for path in files:
        entries = find_remote_images(path.read_text(encoding="utf-8"))
        if not entries:
            continue
        print(f"\n{path.name}（{len(entries)} 张远程图）")
        for lineno, url, kind in entries:
            total += 1
            # 先按「浏览器带外站 Referer」的最坏情况测；失败再按我们实际使用的
            # no-referrer 复测——插件已经给所有图片加了 referrerpolicy="no-referrer"
            status, ctype, size, error = probe(opener, url, "https://epsilongg.github.io/", args.timeout)
            note = ""
            if status is None or status >= 400:
                status2, ctype2, size2, error2 = probe(opener, url, None, args.timeout)
                if status2 is not None and status2 < 400:
                    status, ctype, size, error = status2, ctype2, size2, error2
                    note = "（仅无 Referer 可用）"
                    only_no_referer.append(f"{path.name}:{lineno} {url}")
                else:
                    error = error2 or error

            ok = status is not None and status < 400
            is_image = ctype.lower().startswith("image/") or ctype.lower().startswith("application/octet-stream")
            mark = "OK  " if ok and is_image else "FAIL"
            if not ok:
                broken.append(f"{path.name}:{lineno} {url} -> {status or error}")
            elif not is_image:
                broken.append(f"{path.name}:{lineno} {url} -> 不是图片（{ctype or '无 Content-Type'}）")
            if ok and size and size > BIG_IMAGE_BYTES:
                big.append(f"{path.name}:{lineno} {human_size(size)} {url}")

            # 手写 <img> 不经过 Markdown 插件，拿不到 referrerpolicy="no-referrer"
            if kind == "html":
                raw_html.append(f"{path.name}:{lineno} {url}")
                note += "（手写 <img>，无 no-referrer）"

            if args.quiet and ok and is_image and not note:
                continue
            print(f"  {mark}  {str(status or '—'):>4}  {ctype.split(';')[0] or '—':<16} {human_size(size):>8}  L{lineno}  {url}{note}")

            if args.write_dims and ok and is_image and url not in downloaded:
                data = fetch_bytes(opener, url, args.timeout)
                if data:
                    downloaded[url] = data

    if args.write_dims:
        written = write_dimensions(list(downloaded.items()))
        print(f"\n已把 {written} 张远程图的宽高写入 {DIMS_PATH.relative_to(ROOT)}。")
        if written < len(downloaded):
            print("有部分图片读不出宽高（格式不支持），构建时会退化成不带 width/height。")

    print("\n" + "-" * 72)
    print(f"共检查 {total} 张远程图，坏链 {len(broken)} 张。")
    if only_no_referer:
        print(f"\n有 {len(only_no_referer)} 张只能在不带 Referer 时访问——")
        print("这正是插件统一加 referrerpolicy=\"no-referrer\" 的原因，浏览器访问正常。")
    if raw_html:
        print(f"\n有 {len(raw_html)} 张写在手写 <img> 里：不经过 Markdown 插件，")
        print("不会自动加 loading / decoding / referrerpolicy。远程图建议改用 ![]() 写法。")
        for item in raw_html:
            print("  " + item)
    if big:
        print(f"\n体积超过 {human_size(BIG_IMAGE_BYTES)} 的有 {len(big)} 张，考虑本地化后压缩：")
        for item in big:
            print("  " + item)
    if broken:
        print("\n坏链清单：")
        for item in broken:
            print("  " + item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
