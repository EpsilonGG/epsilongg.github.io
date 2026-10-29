# 快速启动：20 分钟把这个仓库变成你的主页

[← 返回仓库首页](../README.md) ｜ [完整 Fork 指南](fork.md) ｜ [项目说明](project.md)

只想尽快上线，看这一页就够了。遇到问题、想改结构、想绑自定义域名，再去翻[完整 Fork 指南](fork.md)。

---

## 前提：仓库名必须是 `<你的用户名>.github.io`

站内链接全部写成根绝对路径（`/blog/`、`/images/x.jpg`）。只有仓库名是 `<用户名>.github.io` 时，站点才部署在域名根路径上；叫别的名字会跑到 `https://<用户名>.github.io/仓库名/` 下面，整站样式和链接一起失效。

Fork 之后默认还叫 `epsilongg.github.io`，记得改名：**Settings → Repository name → 改成 `<用户名>.github.io`**。

> 本项目**没有**做子路径部署适配。真要放在子路径下，改动清单见[完整 Fork 指南第 0 节](fork.md#0-站点必须部署在域名根路径)。

---

## 三步

### 第 1 步 · 拿代码

仓库右上角 **Use this template**（若已开启）或 **Fork**，然后按上面的前提改名。

### 第 2 步 · 改 6 处

| 改什么 | 文件 | 改哪几个字段 |
| --- | --- | --- |
| 站点本身 | `src/config/site.json` | `name` / `url` / `description` / `author` / `github` / `email` |
| 首页上的你 | `src/config/profile.json` | `name` / `tagline` / `intro` / `avatar` |
| 名片页 | `src/config/about.ts` | `intro` / `focusAreas` / `projects` / `experience` |
| 首页导航 | `src/config/navigation.json` | 每个入口的 `label` / `href` / `description` |
| 链接库 | `src/config/links.ts` | `primaryLinks`、`linkGroups`（现成的示例整组删掉最省事） |
| 三张图 | `public/images/avatar.jpg`、`public/favicon.svg`、`public/og/default.jpg` | 前两张直接覆盖；分享图改 `scripts/make_og.mjs` 的 `BG` 后跑 `npm run og` |

`site.json` 里的 **`url` 只写「协议 + 域名」**，不带结尾斜杠、不带子路径。canonical、Open Graph、RSS、sitemap 全靠它拼绝对地址，写错就是一堆死链。

头像可以直接用 GitHub 的：把 `https://github.com/<用户名>.png?size=460` 另存为 `avatar.jpg`。

### 第 3 步 · 打开 Pages

仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**（不要选 “Deploy from a branch”），然后去 **Actions** 标签等 `Deploy to GitHub Pages` 变绿。

首次约 1–2 分钟。Fork 来的仓库可能要先点一次 **“I understand my workflows, go ahead and enable them”**。

---

## 本地跑一遍（可选，但建议）

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # 确认能构建
npm run check    # 类型检查
npm run links    # 站内死链检查（要先 build）
```

需要 Node **≥ 22.23.4**（`astro@7.4` 的硬性要求，`package.json` 里写死了）。

---

## 上线检查 6 条

- [ ] 仓库名是 `<用户名>.github.io`
- [ ] `site.json` 的 `url` 是 `https://<用户名>.github.io`（无斜杠、无子路径）
- [ ] 首页、`/me/`、`/morelinks/`、`/blog/` 都能打开
- [ ] 文章页图片正常，图注在图片下方、左边缘和图片对齐
- [ ] 随便输一个不存在的地址，看到的是本站 404 页而不是 GitHub 默认 404
- [ ] 页脚的版权年份和署名是你自己的

---

## 接下来读什么

| 想做的事 | 看哪份 |
| --- | --- |
| 改结构、加页面、绑域名、排查构建失败 | [项目说明](project.md) |
| 写第一篇文章（frontmatter、图注、注释） | [博客写作指南](blog-guide.md) |
| 子路径部署、只要文字、授权怎么跟着走 | [完整 Fork 指南](fork.md) |
| 开右侧广告位 | [广告位说明](ads.md) |

---

## 给 AI / agent 的一页速查

让模型帮你改这个仓库时，把下面这段直接贴给它，能省掉它自己摸索的时间：

```
仓库：Astro 7 静态个人主页，Node ≥ 22.23.4，零后端零依赖框架。
构建：npm run build（会先跑 scripts/optimize_images.mjs 生成 WebP）
门禁：npm run check（0 错）→ npm run build → npm run links → npm test → npm run test:md
必须改：src/config/{site,profile,navigation}.json、about.ts、links.ts
         以及 public/images/avatar.jpg、public/favicon.svg、scripts/make_og.mjs（分享图源）
不能碰：src/styles/tokens.css 是唯一的样式数值来源，组件里不许写死颜色/字号/间距
个人信息：只允许出现在 src/config/，页面组件里不许硬编码姓名、域名
路由：/ /me/ /morelinks/ /blog/ /blog/<slug>/，必须部署在域名根路径
文章：src/content/blog/<slug>.md，文件名即 URL；图片写 ![alt](/path "图注")
```

完整的约定和踩坑记录在[项目说明](project.md)，比这段长得多，但值得在动手前扫一眼。
