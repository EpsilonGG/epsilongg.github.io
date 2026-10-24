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

退出码：全部正常为 0，有坏链为 1（便于以后接进 CI）。
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG_DIR = ROOT / "src" / "content" / "blog"

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查文章里引用的远程图片是否可访问")
    parser.add_argument("--only", help="只检查文件名包含该字符串的文章")
    parser.add_argument("--timeout", type=float, default=20.0, help="单张图的超时秒数")
    parser.add_argument("--proxy", help="走代理，例如 http://127.0.0.1:7897")
    parser.add_argument("--quiet", action="store_true", help="只输出有问题的条目")
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
