#!/usr/bin/env python3
"""把网站中的公开内容同步到 GitHub Profile README 的指定区域。

设计要点
--------
1. 只替换三个 Marker 之间的内容，Marker 之外的手写内容永远不会被修改。
2. Marker 缺失、重复、顺序错误或嵌套时直接报错退出，不做任何猜测。
3. 同样输入重复执行结果一致（幂等）；内容没有变化时不写文件。
4. ``--check`` 是严格的只读模式：只比较，不写入，无论成功或失败。

用法
----
    python scripts/sync_profile_readme.py --readme ../profile/README.md
    python scripts/sync_profile_readme.py --readme ../profile/README.md --check

退出码
------
    0  成功（``--check`` 时表示已经同步）
    1  ``--check`` 检测到需要更新
    2  README 结构错误（Marker 缺失、重复、顺序错误或嵌套）
    3  输入错误（文件不存在、配置读取失败、参数错误）

依赖：仅使用 Python 标准库，建议 Python 3.12+。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

EXIT_OK = 0
EXIT_DIFF = 1
EXIT_STRUCTURE = 2
EXIT_INPUT = 3

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_CONFIG_PATH = REPO_ROOT / "src" / "config" / "site.json"
PROFILE_CONFIG_PATH = REPO_ROOT / "src" / "config" / "profile.json"
NAVIGATION_CONFIG_PATH = REPO_ROOT / "src" / "config" / "navigation.json"
BLOG_DIR = REPO_ROOT / "src" / "content" / "blog"

# 三个区域及其 Marker。Marker 必须唯一、成对、按 BLOCK_ORDER 的顺序出现。
MARKERS: dict[str, tuple[str, str]] = {
    "profile": ("<!-- PROFILE:START -->", "<!-- PROFILE:END -->"),
    "navigation": ("<!-- NAV:START -->", "<!-- NAV:END -->"),
    "posts": ("<!-- POSTS:START -->", "<!-- POSTS:END -->"),
}

BLOCK_ORDER: tuple[str, ...] = ("profile", "navigation", "posts")

DEFAULT_MAX_POSTS = 5


class SyncError(Exception):
    """输入或 README 结构问题。携带建议的退出码。"""

    def __init__(self, message: str, exit_code: int = EXIT_STRUCTURE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class PostSummary:
    """README 中展示一篇文章所需的最小信息。"""

    title: str
    slug: str
    published: date


# ---------------------------------------------------------------------------
# 读取项目数据
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as error:
        raise SyncError(f"找不到配置文件：{path}", EXIT_INPUT) from error
    except json.JSONDecodeError as error:
        raise SyncError(f"配置文件不是合法的 JSON：{path}（{error}）", EXIT_INPUT) from error


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_frontmatter(text: str, source: str = "<unknown>") -> dict[str, Any]:
    """解析 Markdown 头部 frontmatter 的常用子集。

    只支持本项目文章实际用到的写法：``key: value`` 与 ``key:`` 后跟
    ``- item`` 列表。这样就不需要引入第三方 YAML 依赖。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SyncError(f"文章缺少 frontmatter：{source}", EXIT_INPUT)

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise SyncError(f"文章 frontmatter 没有结束标记：{source}", EXIT_INPUT)

    data: dict[str, Any] = {}
    list_key: str | None = None

    for raw_line in lines[1:end_index]:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            if list_key is None:
                raise SyncError(f"frontmatter 列表项缺少字段名：{source}", EXIT_INPUT)
            data[list_key].append(_strip_quotes(stripped[2:].strip()))
            continue

        if ":" not in stripped:
            raise SyncError(f"frontmatter 无法解析的行：{source} -> {stripped}", EXIT_INPUT)

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = []
            list_key = key
        else:
            data[key] = _strip_quotes(value)
            list_key = None

    return data


def _parse_date(value: Any, source: str) -> date:
    text = str(value).strip()
    # 允许 "2026-01-01" 与 "2026-01-01T08:00:00+08:00" 两种写法
    candidate = text[:10]
    try:
        return date.fromisoformat(candidate)
    except ValueError as error:
        raise SyncError(f"pubDate 不是合法日期：{source} -> {text}", EXIT_INPUT) from error


def collect_posts(blog_dir: Path = BLOG_DIR) -> list[PostSummary]:
    """读取正式发布的文章，按发布日期倒序（同日按 slug 升序）。"""
    if not blog_dir.exists():
        return []

    posts: list[PostSummary] = []
    for path in sorted(blog_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise SyncError(f"无法读取文章：{path}（{error}）", EXIT_INPUT) from error

        meta = parse_frontmatter(text, path.name)
        draft_value = str(meta.get("draft", "false")).strip().lower()
        if draft_value in {"true", "yes", "1"}:
            continue

        title = str(meta.get("title", "")).strip()
        if not title:
            raise SyncError(f"文章 title 不能为空：{path.name}", EXIT_INPUT)

        posts.append(
            PostSummary(
                title=title,
                slug=path.stem,
                published=_parse_date(meta.get("pubDate", ""), path.name),
            )
        )

    posts.sort(key=lambda item: (-item.published.toordinal(), item.slug))
    return posts


# ---------------------------------------------------------------------------
# 生成 Markdown 片段
# ---------------------------------------------------------------------------


def _absolute(site_url: str, path: str) -> str:
    return f"{site_url.rstrip('/')}/{path.lstrip('/')}"


def render_profile_block(profile: Mapping[str, Any]) -> str:
    """个人简介：姓名与定位一行，随后是简介段落。"""
    name = str(profile.get("name", "")).strip()
    tagline = str(profile.get("tagline", "")).strip()
    if not name:
        raise SyncError("profile.json 中的 name 不能为空", EXIT_INPUT)

    lines: list[str] = []
    headline = f"**{name}**"
    if tagline:
        headline = f"{headline} · {tagline}"
    lines.append(headline)

    intro = profile.get("intro") or []
    paragraphs = [str(item).strip() for item in intro if str(item).strip()]
    if paragraphs:
        lines.append("")
        for paragraph in paragraphs:
            lines.append(paragraph)
            lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def render_navigation_block(site: Mapping[str, Any], navigation: Sequence[Mapping[str, Any]]) -> str:
    """网站主要入口：每个入口一行，附一句说明。"""
    site_url = str(site.get("url", "")).strip()
    if not site_url:
        raise SyncError("site.json 中的 url 不能为空", EXIT_INPUT)

    lines: list[str] = []
    for item in navigation:
        label = str(item.get("label", "")).strip()
        href = str(item.get("href", "")).strip()
        description = str(item.get("description", "")).strip()
        if not label or not href:
            continue
        url = site_url.rstrip("/") + "/" if href == "/" else _absolute(site_url, href)
        if description:
            lines.append(f"- [{label}]({url}) — {description}")
        else:
            lines.append(f"- [{label}]({url})")

    return "\n".join(lines) if lines else "暂无导航内容。"


def render_posts_block(
    site: Mapping[str, Any],
    posts: Sequence[PostSummary],
    max_posts: int = DEFAULT_MAX_POSTS,
) -> str:
    """最近文章：标题链接 + 日期；没有文章时给一行说明。"""
    site_url = str(site.get("url", "")).strip()
    if not site_url:
        raise SyncError("site.json 中的 url 不能为空", EXIT_INPUT)

    if not posts:
        return "文章归档正在整理中。"

    lines: list[str] = []
    for post in list(posts)[: max(0, max_posts)]:
        url = _absolute(site_url, f"/blog/{post.slug}/")
        lines.append(f"- [{post.title}]({url}) · {post.published.isoformat()}")

    return "\n".join(lines)


def build_blocks(
    site: Mapping[str, Any],
    profile: Mapping[str, Any],
    navigation: Sequence[Mapping[str, Any]],
    posts: Sequence[PostSummary],
    max_posts: int = DEFAULT_MAX_POSTS,
) -> dict[str, str]:
    return {
        "profile": render_profile_block(profile),
        "navigation": render_navigation_block(site, navigation),
        "posts": render_posts_block(site, posts, max_posts),
    }


# ---------------------------------------------------------------------------
# 校验与替换
# ---------------------------------------------------------------------------


def locate_blocks(text: str) -> dict[str, tuple[int, int]]:
    """校验 Marker 并返回每个区域在文本中的 [start, end) 区间。

    区间包含开始标记与结束标记本身，便于整段替换。
    """
    spans: dict[str, tuple[int, int]] = {}

    for name in BLOCK_ORDER:
        start_marker, end_marker = MARKERS[name]
        start_count = text.count(start_marker)
        end_count = text.count(end_marker)

        if start_count == 0:
            raise SyncError(f"缺少开始标记 {start_marker}")
        if end_count == 0:
            raise SyncError(f"缺少结束标记 {end_marker}")
        if start_count > 1:
            raise SyncError(f"开始标记 {start_marker} 出现了 {start_count} 次，必须唯一")
        if end_count > 1:
            raise SyncError(f"结束标记 {end_marker} 出现了 {end_count} 次，必须唯一")

        start = text.index(start_marker)
        end = text.index(end_marker)
        if end < start:
            raise SyncError(f"区域 {name} 的结束标记出现在开始标记之前")

        spans[name] = (start, end + len(end_marker))

    # 顺序与嵌套检查：每个区域必须完整位于前一个区域之后
    for previous, current in zip(BLOCK_ORDER, BLOCK_ORDER[1:]):
        if spans[current][0] < spans[previous][1]:
            raise SyncError(
                f"区域 {current} 与区域 {previous} 的顺序错误或存在嵌套，"
                "应依次为 profile → navigation → posts"
            )

    return spans


def apply_blocks(text: str, blocks: Mapping[str, str]) -> str:
    """把三个区域替换为给定内容，其余内容逐字保留。"""
    spans = locate_blocks(text)

    parts: list[str] = []
    cursor = 0
    for name in BLOCK_ORDER:
        start, end = spans[name]
        start_marker, end_marker = MARKERS[name]
        content = blocks[name].strip("\n")
        parts.append(text[cursor:start])
        parts.append(f"{start_marker}\n{content}\n{end_marker}")
        cursor = end
    parts.append(text[cursor:])

    return "".join(parts)


# ---------------------------------------------------------------------------
# 文件读写
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except FileNotFoundError as error:
        raise SyncError(f"找不到 README 文件：{path}", EXIT_INPUT) from error
    except OSError as error:
        raise SyncError(f"无法读取 README 文件：{path}（{error}）", EXIT_INPUT) from error


def _write_text(path: Path, text: str) -> None:
    """先写临时文件再原子替换，避免失败时留下半写入的文件。"""
    temp_path = path.with_name(path.name + ".sync-tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        temp_path.replace(path)
    except OSError as error:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise SyncError(f"无法写入 README 文件：{path}（{error}）", EXIT_INPUT) from error


def sync_file(readme_path: Path, blocks: Mapping[str, str], check: bool = False) -> int:
    """同步单个文件，返回退出码。

    ``check=True`` 时绝不写入文件。
    """
    current = _read_text(readme_path)
    expected = apply_blocks(current, blocks)

    if check:
        if expected != current:
            print(f"需要更新：{readme_path}")
            print("运行时不加 --check 即可写入。")
            return EXIT_DIFF
        print(f"已同步：{readme_path}")
        return EXIT_OK

    if expected == current:
        print(f"没有变化：{readme_path}")
        return EXIT_OK

    _write_text(readme_path, expected)
    print(f"已更新：{readme_path}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把网站的公开内容同步到 GitHub Profile README 的指定区域。",
    )
    parser.add_argument(
        "--readme",
        required=True,
        type=Path,
        help="目标 README 文件路径（个人资料仓库中的 README.md）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查是否需要更新，不写入文件；需要更新时返回退出码 1",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=DEFAULT_MAX_POSTS,
        help=f"最近文章条数上限（默认 {DEFAULT_MAX_POSTS}）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        site = _read_json(SITE_CONFIG_PATH)
        profile = _read_json(PROFILE_CONFIG_PATH)
        navigation = _read_json(NAVIGATION_CONFIG_PATH)
        posts = collect_posts()
        blocks = build_blocks(site, profile, navigation, posts, args.max_posts)
        return sync_file(args.readme, blocks, check=args.check)
    except SyncError as error:
        print(f"错误：{error}", file=sys.stderr)
        return error.exit_code


if __name__ == "__main__":
    sys.exit(main())
