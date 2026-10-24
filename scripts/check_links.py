#!/usr/bin/env python3
"""检查构建产物里的站内链接是否都能落地。

静态站最常见的死法不是样式崩了，是某个页面改名之后还有人链着旧地址——
构建不会报错，浏览器也不会提醒，只有点进去的人看到 404。这个脚本在 CI 里
跑一遍 `dist/`，把「链了但文件不存在」和「锚点指向一个不存在的 id」都揪出来。

默认只查站内链接（本地文件比对，不联网、不依赖网速）。
加 `--external` 才会真的去请求外链——CI 里不用它：外站限流、挡爬虫、
偶发超时都会让流水线莫名其妙变红，外链腐烂是另一件事，该用定时任务查。

用法：
    python scripts/check_links.py                  # 查 dist/ 的站内链接
    python scripts/check_links.py --dist public    # 换目录
    python scripts/check_links.py --no-anchors     # 不查锚点
    python scripts/check_links.py --external       # 顺带请求外链（慢，慎用）

退出码：0 全部通过；1 有死链；2 目录不存在。
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIST = ROOT / 'dist'
SITE_CONFIG = ROOT / 'src' / 'config' / 'site.json'

# 这些协议不是「站内文件」，一律跳过
SKIP_SCHEMES = ('mailto:', 'tel:', 'javascript:', 'data:', 'sms:', 'ftp:')

# 只查这些属性上的地址
URL_ATTRS = {
    'a': ('href',),
    'link': ('href',),
    'script': ('src',),
    'img': ('src', 'srcset'),
    'source': ('src', 'srcset'),
    'video': ('src', 'poster'),
    'audio': ('src',),
    'iframe': ('src',),
    'embed': ('src',),
    'use': ('href', 'xlink:href'),
}

SRCSET_SPLIT = re.compile(r'\s*,\s*')


class LinkParser(HTMLParser):
    """把一页 HTML 里所有「会去取某个地址」的属性收集起来。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.anchor_names: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: (value or '') for name, value in attrs}

        element_id = attr_map.get('id')
        if element_id:
            self.ids.add(element_id)

        if tag == 'a':
            name = attr_map.get('name')
            if name:
                self.anchor_names.add(name)

        for attr in URL_ATTRS.get(tag, ()):
            value = attr_map.get(attr)
            if not value:
                continue
            if attr == 'srcset':
                # "a.webp 600w, b.webp 960w" —— 只取地址部分
                for candidate in SRCSET_SPLIT.split(value):
                    url = candidate.strip().split(' ')[0]
                    if url:
                        self.links.append(url)
            else:
                self.links.append(value)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def parse_html(text: str) -> LinkParser:
    parser = LinkParser()
    parser.feed(text)
    parser.close()
    return parser


def page_url(dist: Path, file: Path) -> str:
    """dist/blog/x/index.html -> /blog/x/；dist/404.html -> /404.html"""
    rel = file.relative_to(dist).as_posix()
    if rel.endswith('index.html'):
        rel = rel[: -len('index.html')]
        return '/' + rel if rel else '/'
    return '/' + rel


def is_skipped(url: str) -> bool:
    lowered = url.strip().lower()
    if not lowered or lowered.startswith('#'):
        return False  # 页内锚点要查
    if lowered.startswith('//'):
        return True
    return lowered.startswith(SKIP_SCHEMES)


def split_url(url: str) -> tuple[str, str]:
    """拆成 (路径, 锚点)。查询串对静态站无意义，直接丢掉。"""
    path, _, fragment = url.partition('#')
    path = path.split('?')[0]
    return path, fragment


def resolve(dist: Path, current_page: str, path: str) -> Path | None:
    """把一个站内路径解析成 dist 里的真实文件，找不到返回 None。"""
    if not path:
        # 纯锚点：指向当前页面自己
        target = current_page
    elif path.startswith('/'):
        target = path
    else:
        base = posixpath.dirname(current_page) or '/'
        target = posixpath.normpath(posixpath.join(base, path))

    target = unquote(target)
    # normpath 会吃掉结尾的斜杠，先记下来
    trailing = target.endswith('/') or target == '/'
    rel = target.lstrip('/')
    base_dir = dist / rel if rel else dist

    candidates: list[Path] = []
    if trailing:
        candidates.append(base_dir / 'index.html')
    else:
        candidates.append(base_dir)
        candidates.append(base_dir / 'index.html')
        candidates.append(base_dir.with_suffix('.html'))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def check(
    dist: Path,
    *,
    check_anchors: bool = True,
    origin: str = '',
) -> tuple[list[dict], dict]:
    """返回 (问题列表, 统计)。问题项形如 {kind, url, page, detail}。"""
    if not dist.is_dir():
        raise FileNotFoundError(dist)

    pages = sorted(dist.rglob('*.html'))
    issues: list[dict] = []
    # 锚点集合按文件缓存，同一页被引用多次时不重复解析
    id_cache: dict[Path, set[str]] = {}

    total_links = 0
    external_links = 0
    seen: set[tuple[str, str]] = set()

    for file in pages:
        html = file.read_text(encoding='utf-8', errors='replace')
        parser = parse_html(html)
        current = page_url(dist, file)

        for url in parser.links:
            url = url.strip()
            if is_skipped(url):
                continue
            total_links += 1

            parsed = urlparse(url)
            # 绝对地址：只在自己域名的前提下当站内链接处理，否则跳过
            if parsed.scheme in ('http', 'https'):
                if not origin or f'{parsed.scheme}://{parsed.netloc}' != origin.rstrip('/'):
                    external_links += 1
                    continue
                path = parsed.path or '/'
                fragment = parsed.fragment
            else:
                path, fragment = split_url(url)

            key = (current, path + ('#' + fragment if fragment else ''))
            if key in seen:
                continue
            seen.add(key)

            target = resolve(dist, current, path)
            if target is None:
                issues.append({'kind': 'missing', 'url': url, 'page': current, 'detail': path})
                continue

            if not (check_anchors and fragment and target.suffix == '.html'):
                continue

            ids = id_cache.get(target)
            if ids is None:
                parsed_target = parse_html(target.read_text(encoding='utf-8', errors='replace'))
                ids = parsed_target.ids | parsed_target.anchor_names
                id_cache[target] = ids

            if unquote(fragment) not in ids:
                issues.append(
                    {'kind': 'anchor', 'url': url, 'page': current, 'detail': fragment}
                )

    stats = {
        'pages': len(pages),
        'links': total_links,
        'unique': len(seen),
        'external': external_links,
        'issues': len(issues),
    }
    return issues, stats


def load_origin() -> str:
    """从 site.json 读站点域名，用来把绝对地址折回站内。"""
    try:
        data = json.loads(SITE_CONFIG.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    return str(data.get('url') or '').rstrip('/')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='检查构建产物里的站内链接')
    parser.add_argument('--dist', default=str(DEFAULT_DIST), help='构建产物目录，默认 dist/')
    parser.add_argument('--no-anchors', action='store_true', help='不检查 #锚点')
    parser.add_argument('--external', action='store_true', help='请求外链（默认不查）')
    parser.add_argument('--origin', default='', help='把该域名的绝对地址当站内链接，默认读 site.json')
    args = parser.parse_args(argv)

    dist = Path(args.dist).resolve()
    if not dist.is_dir():
        print(f'[links] 找不到目录 {dist}，先跑 npm run build', file=sys.stderr)
        return 2

    origin = args.origin or load_origin()
    issues, stats = check(dist, check_anchors=not args.no_anchors, origin=origin)

    for issue in issues:
        if issue['kind'] == 'missing':
            print(f"  死链  {issue['url']}  ←  {issue['page']}")
        else:
            print(f"  锚点  {issue['url']}  ←  {issue['page']}（找不到 id={issue['detail']}）")

    summary = (
        f"[links] {stats['pages']} 个页面 · {stats['unique']} 个站内链接"
        f"（共 {stats['links']} 处引用）"
    )
    if stats['external']:
        summary += f" · 跳过 {stats['external']} 处外链"
    if issues:
        print(f'{summary} · 发现 {len(issues)} 处问题')
        return 1
    print(f'{summary} · 全部通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
