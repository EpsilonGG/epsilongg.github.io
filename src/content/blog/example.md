---
title: 示例文章（草稿）
description: 这是一篇用于验证内容集合、文章路由与 Markdown 渲染的示例草稿，默认不会发布到正式站点。
pubDate: 2026-01-01
tags:
  - 示例
draft: true
---

这是一篇**示例草稿**，只用于验证内容集合（Content Collections）、文章详情页路由与 Markdown 渲染效果。它默认设置了 `draft: true`，因此不会出现在首页、归档、RSS 与 sitemap 中，也不会生成 `/blog/example/` 页面。

要把它变成正式文章，请复制本文件为新的 Markdown 文件，填写真实的标题、日期和正文，并删除 `draft` 字段或改为 `false`。

## 支持的 Markdown 语法

### 段落与强调

普通段落，包含**加粗**、`行内代码`，以及[站内链接](/archive/)和[外部链接](https://docs.astro.build/)。

### 列表

无序列表：

- 第一项
- 第二项
  - 嵌套项
- 第三项

有序列表：

1. 第一步
2. 第二步
3. 第三步

### 引用

> 引用块用于强调一段独立的话。
> 它不应该被渲染成斜体，也不应该使用彩色背景。

### 代码块

```python
def greet(name: str) -> str:
    """一个用于检查代码块样式的示例函数。"""
    return f"你好，{name}"
```

很长的代码行应当可以横向滚动，而不是撑破页面布局：

```bash
npm run build && npx astro preview --port 4321
```

### 表格

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| title | string | 文章标题，不能为空 |
| pubDate | date | 首次发布日期 |
| tags | string[] | 标签，可为空 |

### 分割线

---

## 说明

这篇文章的内容不代表任何真实经历或观点，仅用于验证排版。发布真实文章时，请删除本文件或保持草稿状态。
