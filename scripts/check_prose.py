# -*- coding: utf-8 -*-
"""正文渲染体检：找「Markdown 没生效、把标记当正文印出来」的地方。

构建产物是唯一的事实来源——Markdown 解析正确时加粗是 `<strong>`，出错时
`**` 会原样留在正文里。所以这里不看源码，直接扫 `dist/**/*.html`。

## 两类已知的坑

**一、加粗标记落在中文标点后面**

CommonMark 判定 `**` 能不能收尾，看它前后是不是「字母」。`**小川公貴（Ogawa Koki）**先生`
里的收尾 `**` 前面是 `）`、后面是 `先`，既不满足右翼也不满足左翼，于是整对标记
被当成普通字符印出来。写成 `**小川公貴**（Ogawa Koki）先生` 就正常——
加粗只包名字，罗马音放在括号里本来也更合理。

**二、成对的半角波浪线被当成删除线**

日文副标题里的 `～` 如果敲成半角 `~`，两个 `~` 之间的整段会渲染成 `<del>`。
副标题一律用全角 `～`，所以博客页里 `<del>` 的数量应当为 0。

## 什么时候跑

`npm run check:prose`，构建之后。`<code>` / `<pre>` 里的星号是示例代码
（README 教程那页整段都是），扫的时候先剔掉。
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

# 这些容器里出现 `**` 是正常的：示例代码、行内代码
_OPAQUE = re.compile(r"<(code|pre|script|style)\b.*?</\1>", re.S | re.I)
_BOLD = re.compile(r"\*\*")
_DEL = re.compile(r"<del\b", re.I)
_TAG = re.compile(r"<[^>]+>")


def pages():
    for base, _dirs, files in os.walk(DIST):
        for name in files:
            if name.endswith(".html"):
                yield os.path.join(base, name)


def snippet(text: str, at: int) -> str:
    """出错位置前后各取一段，去掉标签，方便直接定位到那句话。"""
    raw = text[max(0, at - 60) : at + 60]
    return re.sub(r"\s+", " ", _TAG.sub("", raw)).strip()


def main() -> int:
    if not os.path.isdir(DIST):
        print("[prose] 没有 dist/，先 npm run build", file=sys.stderr)
        return 2

    problems: list[str] = []
    scanned = 0
    for path in sorted(pages()):
        rel = os.path.relpath(path, DIST).replace(os.sep, "/")
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        scanned += 1

        visible = _OPAQUE.sub("", html)
        for match in _BOLD.finditer(visible):
            problems.append(f"{rel}  正文里有字面 **：…{snippet(visible, match.start())}…")
            break  # 一页报一处就够，免得同一段刷屏

        # 删除线只在博客正文里算错；文档页讲 Markdown 语法时可能故意写
        if rel.startswith("blog/") and _DEL.search(visible):
            problems.append(f"{rel}  出现 <del>：半角 ~ 被当成了删除线，副标题请用全角 ～")

    if problems:
        for line in problems:
            print("[prose] " + line, file=sys.stderr)
        print(f"[prose] {len(problems)} 处需要人工修（扫了 {scanned} 页）", file=sys.stderr)
        return 1

    print(f"[prose] {scanned} 页 · 没有落单的加粗标记，也没有误渲染的删除线")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
