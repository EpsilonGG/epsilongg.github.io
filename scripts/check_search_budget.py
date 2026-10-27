# -*- coding: utf-8 -*-
"""搜索索引的体积闸门（构建后由 `npm run search:index` 调用）。

Pagefind 的索引是构建产物，不提交仓库，但会跟着站点一起部署：
读者第一次搜索时才拉 pagefind.js + wasm + 命中的索引分片，所以它不等于首屏开销，
但总量失控意味着「搜索一次要拉的东西」也在失控。

实测口径（2026-10-27，8 篇文章 / 8.2 万字，含长访谈）：
  - 索引本体（index/ + fragment/）≈ 290 KB，平均每篇约 36 KB，约 3.5 KB / 千字；
  - 核心运行时（pagefind.js + worker + wasm）≈ 200 KB，和篇数无关。
按这个斜率，50 篇（每篇约 1 万字）≈ 1.8 MB，正好撞上 2 MB 阈值。

阈值定在 2 MB：到了这个量级就该降档成「只索引小标题」，而不是让读者
一次搜索拉一份几 MB 的索引。真需要放宽，先想清楚读者要付多少流量。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = os.path.join(ROOT, "dist", "pagefind")
LIMIT = 2 * 1024 * 1024

# 运行时资源：pagefind.js / worker / wasm / css
RUNTIME_SUFFIXES = (".js", ".wasm", ".css", ".pf_meta")

# 官方 UI 包：我们用自己的搜索框，这几份永远不会被请求（pagefind.js 也不引用它们）。
# 留着只是白白多部署 430 KB，删掉前先确认核心脚本确实没引用。
UNUSED_UI = (
    "pagefind-ui.js",
    "pagefind-ui.css",
    "pagefind-component-ui.js",
    "pagefind-component-ui.css",
    "pagefind-modular-ui.js",
    "pagefind-modular-ui.css",
    "pagefind-highlight.js",
)


def human(num):
    return "%.1f KB" % (num / 1024.0) if num < 1024 * 1024 else "%.2f MB" % (num / 1024.0 / 1024.0)


def prune_unused_ui():
    core_path = os.path.join(BUNDLE, "pagefind.js")
    if not os.path.exists(core_path):
        return []
    with open(core_path, "r", encoding="utf-8", errors="ignore") as f:
        core = f.read()
    removed = []
    for name in UNUSED_UI:
        path = os.path.join(BUNDLE, name)
        # 核心脚本一旦引用了它，就不许删（版本升级改了结构时靠这行兜住）
        if os.path.exists(path) and name not in core:
            os.remove(path)
            removed.append(name)
    return removed


def main():
    if not os.path.isdir(BUNDLE):
        print("[search] dist/pagefind 不存在：先跑 npm run build（它在 astro build 之后调 pagefind）")
        return 1

    removed = prune_unused_ui()
    if removed:
        print("[search] 删掉未使用的官方 UI 包 %d 个：%s" % (len(removed), ", ".join(removed)))

    total = 0
    runtime = 0
    index = 0
    for dirpath, _dirnames, filenames in os.walk(BUNDLE):
        for name in filenames:
            size = os.path.getsize(os.path.join(dirpath, name))
            total += size
            if name.endswith(RUNTIME_SUFFIXES):
                runtime += size
            else:
                index += size

    articles = 0
    blog_dir = os.path.join(ROOT, "dist", "blog")
    if os.path.isdir(blog_dir):
        articles = len([d for d in os.listdir(blog_dir) if os.path.isdir(os.path.join(blog_dir, d))])

    print("[search] dist/pagefind 合计 %s（阈值 %s）" % (human(total), human(LIMIT)))
    print("[search]   索引与片段 %s / 运行时 %s / %d 篇文章" % (human(index), human(runtime), articles))
    if articles:
        print("[search]   平均每篇 %.1f KB" % (index / float(articles) / 1024.0))

    if total > LIMIT:
        print("[search] 超预算：把索引降档成只收小标题（pagefind.yml），或拆分成多语言/多子站。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
