# 项目说明

[← 返回仓库首页](../README.md) ｜ [Fork 指南](fork.md)

以个人简介和站点导航为入口的静态个人网站：首页先介绍「我是谁」，再提供名片、链接库、归档三个入口，博客作为网站的一部分而不是主角。

- 站点地址：`https://epsilongg.github.io`（仓库：`github.com/EpsilonGG/epsilongg.github.io`）
- 技术栈：Astro 7（静态生成）、TypeScript、原生 CSS、Markdown + Content Collections（Zod 校验）
- 无前端框架、无数据库、无后端、无第三方托管平台
- 部署：GitHub Pages + GitHub Actions

---

## 1. 本地运行

需要 Node.js **>= 22.23.4**（`package.json` 的 `engines` 写死；`astro@7.4` 起有这个下限），以及 Python 3.9+（构建脚本与单元测试需要）。

```bash
npm install      # 安装依赖
npm run dev      # 开发服务器，默认 http://localhost:4321
npm run build    # 生产构建，输出到 dist/（含图片优化与搜索索引）
npm run preview  # 预览生产构建
npm run check    # Astro / TypeScript 类型检查
npm run links    # 站内死链检查（要先 build）
npm test         # Python 回归（日报、内容层、周报与脚本）
```

> 如果 `npm run dev` 提示端口被占用，可以用 `npm run dev -- --port 4322`。
>
> 改完东西的标准门禁顺序是：`npm run check` → `npm run build` → `npm run links` → `npm test`。日报另有 `npm run check:daily`，见第 3 节。

---

## 2. 目录结构

```text
.
├── README.md                  仓库首页（与 GitHub Profile README 基本一致）
├── README/                    文档
│   ├── project.md             本文件：项目说明
│   ├── quickstart.md          20 分钟改成自己的主页
│   ├── blog-guide.md          博客写作指南（frontmatter / 图注 / 注释）
│   ├── translation-style.md   译文口径（词表本体在 data/glossary.json）
│   ├── fork.md                如何 fork 出你自己的个人主页
│   ├── ads.md                 右侧广告位（默认关闭）
│   └── reports/               一次性报告存档（含工作区现状）
├── public/
│   ├── docs/                  给维护者看的 HTML 指南，部署后可在 /docs/ 下直接访问
│   │   ├── github-profile-readme-guide.html   主页 README 怎么搭、怎么维护
│   │   ├── project-status.html                项目现状：完成度、不足与可优化点
│   │   ├── notes-maintenance.html             笔记栏目的维护约定
│   │   └── ai-articles-proposal.html          AI 整理类文章的区分机制
│   ├── fonts/                 本地字体（Inter / Cormorant Garamond / Fira Code）+ 许可文本
│   ├── images/
│   │   ├── avatar.jpg         头像（460×460，与 GitHub 头像同步）
│   │   ├── bg/sky.jpg|webp    可选背景图（1920 宽）
│   │   ├── blog/<slug>/       每篇文章的本地插图（按出现顺序 01、02…）
│   │   ├── daily/             日报长图（`npm run images` 之外单独出）
│   │   ├── links/icons/       常用链接的小图标（按 22×22 显示，存 64×64）
│   │   ├── people/            GitHub 朋友的头像（按 22×22 显示，存 64×64）
│   │   └── tools/             工具图标（48×48 白色圆角方块，按 2 倍图存放）
│   ├── favicon.svg
│   └── og/default.jpg         默认 Open Graph 分享图（1200×630，由 npm run og 生成）
├── src/
│   ├── components/            Header / Footer / 导航 / 链接 / 卡片 / 图标网格 / 徽章墙 / 最近文章 / 主题与背景开关 / 阅读进度条
│   ├── config/                ★ 唯一数据源
│   │   ├── site.json          站点名、域名、描述、作者
│   │   ├── profile.json       首页个人简介与头像
│   │   ├── about.ts           名片页内容
│   │   ├── navigation.json    顶部导航
│   │   ├── links.ts           链接库
│   │   ├── tags.json          笔记标签的封闭集合
│   │   ├── daily-roster.json          日报名单·声优版
│   │   └── daily-roster-galgame.json  日报名单·Galgame 版
│   ├── content/blog/          笔记正文（Markdown，文件名即 URL）
│   ├── content.config.ts      blog 与 dailyReports 两个集合的 Zod 校验
│   ├── layouts/               BaseLayout / ArticleLayout / DailyLayout
│   ├── lib/                   posts（笔记）· daily（期号与纯文本）· roster（名单）· cien（Ci-en 记法）· markdown 插件
│   ├── pages/                 路由：/ /me/ /morelinks/ /blog/ /daily/ /404 /rss.xml /robots.txt
│   ├── scripts/theme.ts       主题状态的唯一实现
│   ├── scripts/background.ts  背景图开关状态的唯一实现
│   └── styles/                tokens / global / typography / components / fonts
├── scripts/
│   ├── daily/                 日报包：窗口、增量、去重、排序、组装、出题、判卷、定稿、发布、Ci-en
│   ├── daily-image/           日报长图渲染（render.mjs）
│   ├── content/               统一内容层：规范化、实体、事件、评分、快照、状态
│   ├── daily_prepare.py       日报自动化入口（拉取 → 数条数 → 出骨架）
│   ├── daily_digest.py        日报命令门面（build / prompt / apply / confirm / ja / publish）
│   ├── xreader_slice.py       抓取全量库 → 按日切片
│   ├── trigger_fetch.py       立刻触发抓取并等完成
│   ├── check_daily_site.py    日报出口闸门
│   ├── check_links.py         站内死链
│   ├── push_site.py           提交推送（必带 --path）
│   ├── sync_profile_readme.py README 同步
│   └── make_og.mjs / optimize_images.mjs  分享图与 WebP 变体
├── data/
│   ├── daily/<期号>/          日报正本（进 git、永久、站点只读这里）
│   ├── xreader/               抓取库的按日切片（进 git，窗口内滚存）
│   ├── period-sources/        日报来源回填台账
│   └── glossary.json          译名与术语表
├── schemas/                   3 份 JSON Schema：report / generation / item
├── tests/                     Python 回归 + markdown / cien 的 node 测试 + golden 基准
├── docs/                      运营手册与架构契约
├── .github/workflows/         deploy.yml（部署）/ sync-profile-readme.yml（可选同步）
├── astro.config.mjs
└── package.json
```

设计约定：

- 颜色、字号、间距、圆角、动效时长只在 `src/styles/tokens.css` 定义，组件里不写死色值。
- 个人信息只存在 `src/config/*.json` / `*.ts`，页面组件不保存任何个人资料。
- 数据用 JSON（`site.json`、`profile.json`、`navigation.json`）是因为 README 同步脚本（Python）也要读取同一份数据，避免出现两份互相冲突的配置。
- 站内链接一律写成根绝对路径（`/blog/` 等），所以站点**必须部署在域名根路径**。这条限制的具体影响见 [Fork 指南](fork.md#0-站点必须部署在域名根路径)。
- 页头是 `1fr auto 1fr` 三栏网格：站名 / 导航 / 开关。两边等宽导航才会真正居中，**不要**改回 `space-between`。
- 背景图（`/images/bg/sky.*`）是可选功能，默认关闭，宽于 1280px 才生效。它由 `<html>` 上的三层背景画出来（纸面 → 纱 → 照片），**不参与布局**；纸面宽度 `--paper-w`、纱的浓度 `--bg-veil` 都在 tokens.css。不要改成给 `body` 设 `max-width`——那会把文章页 68rem 的网格挤坏。
- `data/` 不在 `public/` 里，构建时读取、不进 `dist/`；`deploy.yml` 也对 `data/xreader/**` 设了 `paths-ignore`。

### 路由说明

| 路径 | 内容 |
| --- | --- |
| `/` | 首页：个人简介 → 站点导航 → 最近文章 → 页脚 |
| `/me/` | 名片页（简介、主要平台、关注领域、项目与经历） |
| `/morelinks/` | 链接库（分类展示） |
| `/blog/` | 笔记（文章列表）：按年份分组，支持搜索、标签筛选与分页 |
| `/blog/{slug}/` | 单篇文章，`slug` 即 Markdown 文件名 |
| `/daily/` | 日报归档：按月分组，一行一期（日期 + 看点简报） |
| `/daily/{期号}/` | 单期日报详情，`getStaticPaths` 从内容集合生成，没有手写路由 |
| `/daily/rss.xml` | 日报归档 feed，**独立于**主 `/rss.xml`（主 feed 只收笔记） |
| `/daily/{期号}.json` | 与正本 `report.json` 逐字节相同的 JSON 出口 |
| `/daily/{期号}.txt` | 纯文本出口（复制粘贴用） |
| `/daily/{期号}.ja.txt` | Ci-en 版（中日双语），只有声优版生成 |
| `/rss.xml`、`/robots.txt`、`/sitemap-index.xml` | 自动生成 |
| 其他任意地址 | `404.html` |

**本站有 `/blog/` 文章列表页**（即「笔记」页）：文章入口为首页「最近文章」、单篇文章的上一篇/下一篇导航，以及 `/blog/`（按年份分组、可搜索、可按标签筛选、分页）。

### 日报（`/daily/`）

日报是站内唯一自动生产的内容。它不写 Markdown：`data/daily/<期号>/report.json` 是正本，页面只渲染它的结构化字段。

**期号就是被覆盖的那一天 + 哪一版，也是网址。** 格式 `YYMMDD`（JST）：

| 期号 | 意思 |
| --- | --- |
| `261107` | 声优版第 1 期（**不带后缀的永远是声优版**） |
| `261107-g` | Galgame 版第 1 期 |
| `261107-2` / `261107-g2` | 同一天的第二个声优版 / Galgame 版 |
| `261107-1` / `261107-g1` | **写错了**，第 1 期不写后缀 |

期号不带小时：真实出稿落在次日凌晨，和「覆盖 00:00–24:00」的窗口对齐；真实发布时刻存在 `issue.published_at`。

**四段版式，顺序固定**：`highlights`（今日看点）→ `works`（作品动态，一条一个作品）→ `interactions`（互动）→ `people`（名单，一人一句）。空段整节不渲染。

**两版分工**：声优版用 `daily-roster.json`（声优 + 音声社团），Galgame 版用 `daily-roster-galgame.json`（游戏厂商 + 信息号）。两版是两次独立的 build，各读自己的库，一份失败不拖住另一份。Ci-en 出口只有声优版有。

**位置就是状态**：草稿留在 `out/`，`publish` 搬到 `data/daily/` 才算发布；正本里没有 `draft` 字段。`sources` 是唯一能回溯的凭据，页面不显示，但 `.json` 出口会原样输出。

运营流程、退出码、抓取侧的 cron 实测、schema 与排查表见 [日报运营与维护指南](../docs/daily-report-guide.md)。

---

## 3. 当前状态

> 本节只写**结构性事实**（哪些线在跑、靠什么闸门守着），不写页数与用例数——那些每天都在变，写进来必然过时。
> 要数字和逐项待办，读 [工作区现状](reports/workspace-status-2026-11-08.md)（实测快照）或 [`public/docs/project-status.html`](../public/docs/project-status.html)（完成度总表与剩余项）。

| 子系统 | 状态 |
| --- | --- |
| 站点构建 | `npm run build` 通过，产物进 `dist/`；push 到 `main` 由 `deploy.yml` 自动部署到 `https://epsilongg.github.io` |
| 个人主页 / 名片 / 链接库 | 数据齐备，改 `src/config/` 即可，无需动组件 |
| 笔记 | 20 篇 Markdown（含 1 篇 `draft: true` 的示例）；标签封闭集合、搜索、分页、图注与脚注插件均可用 |
| 日报双版 | 每天自动出稿：抓取 → 组装 → 出题答题 → 判卷 → 定稿 → 发布。六出口齐全，金文件守着渲染不漂移 |
| 日报长图 | `scripts/daily-image/render.mjs` 定稿 `rail-12x`；失败只告警，不阻断日报 |
| 类型检查 | `npm run check` 0 error |
| 回归 | `npm test`（Python）+ `npm run test:md` + `npm run test:cien`，均在 `deploy.yml` 里跑 |
| 出口闸门 | `npm run check:daily`：三产物齐全、JSON 与正本逐字节相同、两个 feed 不混、金文件一致 |
| 死链 | `npm run links` 对构建产物跑，只查站内、不联网 |
| 空站点降级 | 删掉全部文章后仍可构建，归档页显示「暂无文章」，RSS 输出空频道 |

日报的保护集（`data/daily/**`、`scripts/daily/**`、日报 schema、`content.config.ts` 的日报集合、两条抓取 workflow、金文件）在 M6 前按约定**零改动**，改动需走 `tests/daily-protection-waivers.json` 的显式授权登记。

仍为占位、需要你自己补的部分见第 4 节。

---

## 4. 需要你自己填写的内容

| 文件 | 字段 | 说明 |
| --- | --- | --- |
| `src/config/site.json` | `description` | 站点默认描述，当前是「EpsilonGG 的个人主页」 |
| | `startYear` | 版权起始年份，当前 `2026` |
| | `email` | 公开邮箱，留空则 404 页不显示「报告问题」 |
| `src/config/profile.json` | `tagline` / `intro` / `description` | 已填写，可按需润色 |
| | `location` | 可选，当前为空（首页不显示地区） |
| `src/config/about.ts` | `intro` / `focusAreas` / `projects` / `experience` | 已填写 |
| `src/config/links.ts` | `primaryLinks` | 已填 GitHub；其他平台可继续加，`/me/`（名片页）的「主要平台」区块会自动出现 |
| | `linkGroups` | 五个分类各有自己的 `layout`：个人平台/项目用卡片、工具用图标网格、研究与参考资料用列表、常用链接用小按钮墙（内部再分 GitHub / ACG 资源两个子栏目）。见第 4.1 节 |
| `public/og/default.jpg` | 分享图 | 已按 EpsilonGG 生成；`npm run og` 从 `images/bg/sky.jpg` 重切 |
| `src/content/blog/example.md` | 草稿示例 | 可以删除 |

填写原则：只写能确认的真实信息，不要为了填满而编造。所有数组留空时，页面会显示一行简洁提示而不是空区块，不会报错。

### 头像同步

`public/images/avatar.jpg` 是从 GitHub 头像地址 `https://github.com/EpsilonGG.png?size=460` 下载的（该地址实际返回 JPEG，所以文件后缀是 `.jpg`），尺寸 460×460。

- 在 GitHub 更换头像后，**仓库里的这张图不会自动更新**，需要重新下载覆盖：把上面 URL 的图片另存为 `public/images/avatar.jpg` 再提交。
- 想换成本地图片时，保持 1:1、不小于 200×200，然后确认 `profile.json` 的 `avatar` 路径是 `/images/avatar.jpg`（或改路径）。
- 想暂时不显示头像，把 `profile.json` 的 `avatar` 设为空字符串即可，首页会自动隐藏头像区。

### 4.1 链接库的四种排版

`/morelinks/` 的每个分类按 `layout` 字段渲染，不写就是 `list`：

| `layout` | 样子 | 当前用在 |
| --- | --- | --- |
| `list` | 竖排，左侧名称右侧说明 | 研究与参考资料 |
| `cards` | 卡片网格，右上角一条次要信息（`meta`） | 个人平台、项目与代码仓库 |
| `icons` | 48×48 倒角方形图标 + 下方名称与四字说明 | 工具与服务 |
| `badges` | 一排小按钮（22px 图标 + 站名），桌面一行五个 | 常用链接 → GitHub / ACG 资源 |

**`badges` 是 HTML + CSS 画的，不是图片。** 所以放大不会糊、深色模式自动适配、加一个链接只要改一行数据，不需要再做按钮图。宽度按 `7.5rem` 自动填充：内容区 688px 时一行正好 5 个，窗口变窄会自动降到 4 / 3 / 2 列。

**加一个常用链接**：

1. 图标放进 `public/images/links/icons/`（页面上按 22×22 显示，存 64×64 就够清晰）。
2. 在 `linkGroups` 里 `id: 'common'` 的 `subgroups` 中找到对应子栏目，加一条：

```ts
{
  label: '友站名',                                  // 按钮上的文字
  href: 'https://example.com/',
  icon: '/images/links/icons/example.png',          // 省略则退化成字母块
  monogram: '友',                                   // 可选：字母块显示什么字
}
```

3. 图标默认灰度、鼠标悬停或键盘聚焦时恢复原色，这个效果由 CSS 控制，图片本身保持原色即可。

**加一个 GitHub 朋友**：头像下载到 `public/images/people/<用户名>.png`（GitHub 头像地址后面加 `&s=160` 就能拿到大图），`label` 写 GitHub 用户名，`icon` 指向那张头像。

**加一个工具图标**：把图标放进 `public/images/tools/`（页面上按 48×48 显示，存 96×96），然后在 `tools` 组里加 `icon: '/images/tools/xxx.png'`。不写 `icon` 时会退化成白色圆角方块 + 字母（`monogram` 可指定），不会裂图。说明文字保持四个字左右，和图标同宽最整齐。

**再分一层子栏目**：一个分类想再分小组时，用 `subgroups` 代替 `links`，子栏目之间会自动画一条分隔线：

```ts
{
  id: 'common',
  title: '常用链接',
  links: [],                       // 有 subgroups 时这个留空
  subgroups: [
    { id: 'github', title: 'GitHub', layout: 'badges', links: [/* … */] },
    { id: 'acg', title: 'ACG 资源', layout: 'badges', links: [/* … */] },
  ],
}
```

---

## 5. 写文章

在 `src/content/blog/` 新建 `my-post.md`，**文件名就是 URL**（`/blog/my-post/`），改标题不会改链接。

```yaml
---
title: 文章标题
description: 一句话摘要，会出现在首页、归档与 RSS
pubDate: 2026-03-01
updatedDate: 2026-03-05   # 可选，不能早于 pubDate
tags:
  - 笔记
draft: false              # 可选，默认 false
---
```

- `title` 不能为空；日期必须合法；`tags` 必须是字符串数组。字段错误会让 `npm run build` 失败并指出具体文件。
- `draft: true` 的文章不会出现在首页、归档、RSS、sitemap，也不会生成页面（开发环境同样如此）。需要预览草稿时把 `draft` 改为 `false`。
- 不支持 `.mdx`（未安装 MDX 集成）。

### 文章里插图

图片放进 `public/images/blog/<文章名>/`，Markdown 里用根路径引用：

```markdown
![替代文字](/images/blog/my-post/01.jpg)
```

第一篇真实文章 `rurudo-unreal-interview.md` 里用的是原始 HTML `<img>`，因为需要显式写宽高和懒加载：

```html
<img src="/images/blog/rurudo-unreal/01.jpg" alt="插图：C99 主视觉图 画师：Hiten" width="1000" height="1411" loading="lazy" decoding="async">
```

两种写法都能正常显示。写 `<img>` 时**务必带上 `width` 和 `height`**，否则图片加载前页面高度会跳动（CLS）。Astro 的 Markdown 处理器默认不会给 `public/` 里的图片加尺寸，所以这类长图文用显式 HTML 更稳。

---

## 6. 部署到 GitHub Pages

### 6.1 首次推送

仓库名必须是 `epsilongg.github.io`（用户站点，部署在根路径，**不需要 `base`**）。

```bash
# 0. 先确认 git 身份（本机当前未配置，直接 commit 会失败）
git config user.name "EpsilonGG"
git config user.email "epsilongg.work@gmail.com"

# 1. 提交（仓库已初始化在 main 分支，文件已暂存）
git add .
git commit -m "init: personal site"

# 2. 关联远程并推送（先在 GitHub 建好空仓库 epsilongg.github.io，不要勾选 README）
git remote add origin https://github.com/EpsilonGG/epsilongg.github.io.git
git push -u origin main
```

### 6.2 打开 Pages

1. 仓库 **Settings → Pages**。
2. **Build and deployment → Source** 选择 **GitHub Actions**（不要选 "Deploy from a branch"）。
3. 回到 **Actions** 标签，等待 `Deploy to GitHub Pages` 运行完成（首次约 1–2 分钟）。
4. 打开 `https://epsilongg.github.io/` 确认首页；再检查 `/blog/`、`/me/`、`/morelinks/`、`/daily/`、一篇文章页、一期日报页、`/rss.xml`、`/daily/rss.xml`、`/sitemap-index.xml`、`/robots.txt`，以及一个不存在的地址（应显示 404 页面）。

### 6.3 部署失败排查

| 现象 | 检查点 |
| --- | --- |
| Actions 报 `npm ci` 失败 | `package-lock.json` 是否已提交；Node 版本是否为 22 |
| 页面 404 | Pages 的 Source 是否选为 GitHub Actions；工作流是否成功 |
| 样式或图片丢失 | `site.json` 的 `url` 是否写成了仓库子路径；用户站点不要设置 `base` |
| 文章图片裂图 | 图片是否已提交到 `public/images/blog/...`；路径是否以 `/` 开头 |
| 深层文章刷新 404 | 属于 GitHub Pages 行为限制；本站所有页面都是预渲染的 `index.html`，正常情况不会出现 |
| canonical / RSS 域名错误 | 修改 `src/config/site.json` 的 `url` 后重新推送 |
| 多出一条 `pages build and deployment` 失败 | 这是 GitHub 早期的 Jekyll 构建流水线，与本站无关。只要 `Deploy to GitHub Pages` 成功、Pages 的 Source 是 GitHub Actions，可以忽略 |

### 6.4 关于 `url` 该写什么

写 **`https://epsilongg.github.io`**，也就是「协议 + 域名」，不要写 `https://github.com/EpsilonGG/epsilongg.github.io`。

原因：`site.json` 的 `url` 是站点根地址，`src/config/site.ts` 的 `absoluteUrl()` 会拿它拼出 canonical、Open Graph、RSS 与 sitemap 里的绝对链接。写成仓库地址会得到 `https://github.com/EpsilonGG/epsilongg.github.io/blog/xxx/` 这种并不存在的链接，搜索引擎和 RSS 阅读器都会拿到死链。仓库地址属于 GitHub，域名地址才是站点本身。

如果以后绑定了自定义域名（例如 `https://example.com`），只需要改这一处，其他文件不用动。

---

## 7. README 同步（可选）

`scripts/sync_profile_readme.py` 会把网站中的个人简介、主要入口、最近文章写入 GitHub Profile README 的三个指定区域。完整说明见 [`public/docs/github-profile-readme-guide.html`](../public/docs/github-profile-readme-guide.html)（部署后可在 `/docs/github-profile-readme-guide.html` 打开）。

个人资料仓库（与用户名同名的仓库，例如 `EpsilonGG/EpsilonGG`）的 `README.md` 需要包含三对 Marker，顺序固定为 profile → navigation → posts：

```markdown
<!-- PROFILE:START -->
<!-- PROFILE:END -->

<!-- NAV:START -->
<!-- NAV:END -->

<!-- POSTS:START -->
<!-- POSTS:END -->
```

本地运行：

```bash
# 写入
python scripts/sync_profile_readme.py --readme ../EpsilonGG/README.md

# 只检查（严格只读，不写文件）
python scripts/sync_profile_readme.py --readme ../EpsilonGG/README.md --check
```

退出码：`0` 成功 / 已同步，`1` `--check` 检测到需要更新，`2` Marker 结构错误，`3` 输入错误。

行为约定：

- 只替换 Marker 之间的内容，Marker 之外的手写内容逐字保留。
- Marker 缺失、重复、顺序错误或嵌套时直接报错退出，不猜测插入位置。
- 相同输入重复执行结果一致；内容没有变化时不写文件。
- 写文件采用「临时文件 + 原子替换」，失败不会留下半写入的文件。

### 7.1 本站 README 的「最近更新」

本站 `README.md` 只用了 `RECENT` 一对 Marker（脚本允许只用部分区域），内容 = 最近三篇笔记的标题链接，按 `pubDate` 倒序。

**它不需要手工维护，也不依赖本地推送。** `.github/workflows/sync-readme-recent.yml` 每月 1 日与 15 日（UTC 00:17，北京时间 08:17）在 GitHub 上跑一次：

```
checkout 线上仓库 → sync_profile_readme.py --readme README.md
→ 有变化就 commit + push（只改 README.md，没变化就什么都不做）
```

几个刻意的选择：

- **定时而不是 push 触发**：README 只是门面，晚两周更新没有代价；每次 push 都跑会让历史里塞满机器人提交。
- **不会死循环**：用默认 `GITHUB_TOKEN` 推送产生的 push 事件不会再触发任何 workflow，既不会重跑本任务，也不会触发 `deploy.yml`（README 不在站点产物里，本来也不需要重新部署）。
- **只读线上仓库**：`src/content/blog/` 与 `src/config/` 都从 checkout 出来的版本读，本地有没有未提交的改动完全无关。
- **幂等**：脚本在内容没变时不写文件，那一步就产生不了提交。

想手动刷一次：

```bash
python scripts/sync_profile_readme.py --readme README.md
python scripts/sync_profile_readme.py --readme README.md --check   # 只比对，不写
```

> 定时任务会在服务端给 `main` 加提交，本地因此会落后一格。`push_site.py` 推送前会先 `fetch`，落后就 `rebase --autostash` 再推——所以 23:15 的日报自动化不会被它挡住。

跨仓库自动同步工作流 `.github/workflows/sync-profile-readme.yml` 只在手动触发时运行。启用前需要：

1. 创建 fine-grained token，只授予个人资料仓库的 **Contents: Read and write** 权限。
2. 在网站仓库 **Settings → Secrets and variables → Actions** 添加 `PROFILE_README_TOKEN`。
3. 在 Actions 页面手动运行 `Sync profile README`，`readme_repo` 填 `EpsilonGG/EpsilonGG`，先用 `dry_run: true` 试跑。

未配置该 Secret 时工作流会自动跳过，**不会影响网站的构建与部署**。

---

## 8. 回滚

```bash
git log --oneline -10                 # 查看最近提交
git show <commit> -- path/to/file     # 查看某次提交对文件的改动

git checkout -- path/to/file          # 丢弃某个文件的未提交修改（危险，会丢失本地改动）

git revert <commit>                   # 生成一个反向提交，撤销某次错误提交（推荐）
git push                              # 推送后自动触发部署

git restore --source=<commit> -- path/to/file   # 把单个文件恢复到某个历史版本
```

`git reset --hard` 会丢弃工作区与暂存区的改动，除非确认没有需要保留的内容，否则不要使用。

回滚后确认：Actions 中 `Deploy to GitHub Pages` 成功、首页与文章页可访问、`/rss.xml` 内容已恢复。

---

## 9. 其他说明

- **字体**：Inter（可变字重 100–900）、Cormorant Garamond（400）、Fira Code（可变字重 300–700），全部本地托管在 `public/fonts/`，许可文本同目录。中文使用系统字体回退（PingFang SC / 微软雅黑 / 思源黑体），因此中文渲染效果随系统而异，这是有意取舍（不引入几 MB 的中文字体）。
- **Open Graph 图**：`public/og/default.jpg` 是静态图片（1200×630），由 `npm run og` 从背景图切出；每篇笔记另有 `public/og/blog/<slug>.jpg`。
- **robots.txt** 由 `src/pages/robots.txt.ts` 按 `site.json` 的 `url` 生成，所以不在 `public/` 下，避免域名写两份。
- **主题**：默认浅色，用户选择保存在 `localStorage`；读取或写入失败时回退到浅色，不影响页面使用。首屏有内联脚本预先应用主题，避免闪烁。
- **移动端导航**：五个入口文字都很短，窄屏下换行显示而不是折叠菜单，因此没有额外的键盘交互与焦点管理负担。
- **转载文章**：第一篇是翻译作品，文首保留了原文出处、作者与版权说明。这类文章请自行确认授权范围。
- **`public/docs/`**：放给维护者看的说明性文件（目前 5 份 HTML 指南）。因为在 `public/` 下，它们会随站点一起发布，可通过 `/docs/<文件名>` 直接打开；不在导航里，也不会进 sitemap。
