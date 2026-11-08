<div align="center">

# EpsilonGG

**学生物的 · 偶尔写点代码 · 不务正业ing**

Life Science ｜ Vibe Coding ｜ Galgame ｜ Doujin ASMR

[个人主页](https://epsilongg.github.io/) ·
[链接库](https://epsilongg.github.io/morelinks/) ·
[笔记](https://epsilongg.github.io/blog/) ·
[日报](https://epsilongg.github.io/daily/) ·
[邮箱](mailto:epsilongg.work@gmail.com)

</div>

---


## 在做的事

- **[X-rss](https://github.com/EpsilonGG/X-rss)** — 基于 Actions 的 X / Twitter RSS 聚合器
- **[X-Reader](https://github.com/EpsilonGG/X-Reader)** — 抓取 X、RSS 与 YouTube，推送 TG / QQ。本站日报的抓取侧就是它
- **[blog-template](https://github.com/EpsilonGG/blog-template)** — 这个站的模板版：Astro 静态主页，改几个 JSON 就能换成你的

## 个人站点导航

- [首页](https://epsilongg.github.io/) — 个人简介与站点入口
- [名片](https://epsilongg.github.io/me/) — 个人背景、主要平台、关注领域与项目概览
- [链接库](https://epsilongg.github.io/morelinks/) — 外部平台、工具、资源和项目链接
- [笔记](https://epsilongg.github.io/blog/) — 文章、研究记录与长期内容
- [日报](https://epsilongg.github.io/daily/) — 每天两期 X 日报：声优版与 Galgame 版，AI 整理

## 最近更新

<!-- RECENT:START -->
- [「11 月 5 日」其实是游戏的好发售日——同日发售的美少女 Roguelike《无尽幻樱阁》《恸哭幽光》，开发者谈「为什么敢贴着 GTA6 上」](https://epsilongg.github.io/blog/automaton-crymelight-mugenzakura-roundtable/)
- [以新作《anemoi》为轴织出的 Key 音乐轨迹——“KSL Live World 2026 – Sing with the Wind -”现场报道](https://epsilongg.github.io/blog/ksl-live-world-2026-report/)
- [为了"用更好的日文玩游戏"直接找开发者谈判的玩家，后来成了自由游戏翻译者——"边玩边译"这份工作严苛的幕后【访谈】](https://epsilongg.github.io/blog/automaton-toyoch-interview/)
<!-- RECENT:END -->

---

## 关于这个仓库

这里是 `epsilongg.github.io` 的源码：一个用 Astro 写的静态个人主页，外加一条每天自动运行的日报生产线。

**技术栈**：Astro 7（静态生成）+ TypeScript + 原生 CSS + Markdown。无前端框架、无数据库、无后端、无 CMS、无第三方托管，部署在 GitHub Pages。

### 三条内容线，一套底座

这个仓库不是「一个博客」，是**一个静态站 + 一条自动生产管线**。三条内容线共用同一套构建与部署，但生产节奏完全不同。

| 内容线 | 谁产生 | 节奏 | 自动 | 入口 |
| --- | --- | --- | --- | --- |
| **个人主页** | 手写 JSON / TS 配置 | 不定期 | 否 | `/`、`/me/`、`/morelinks/` |
| **笔记** | 手写 Markdown | 不定期 | 否 | `/blog/` |
| **日报（双版）** | X-Reader 抓取 + 本地 LLM 整理 | 每天一期 ×2 | 是 | `/daily/` |

构建产物只有这几类页面：静态页（首页 / 名片 / 链接库 / 笔记列表 / 日报归档 / 404）、每篇笔记一页、每期日报一页，外加 `public/docs/` 下的维护者指南。日报另有 JSON / TXT / Ci-en 三个非 HTML 出口和两个独立 feed。

### 目录

```text
.
├── src/
│   ├── config/            唯一数据源：站点、个人资料、导航、链接、两份日报名单、标签
│   ├── content/blog/      笔记正文（Markdown，文件名即 URL）
│   ├── pages/             路由：/ /me/ /morelinks/ /blog/ /daily/ /404 /rss.xml /robots.txt
│   ├── lib/               期号解析、名单查询、Markdown 插件、Ci-en 渲染
│   ├── layouts/           Base / Article / Daily 三套布局
│   ├── components/        Header / Footer / 导航 / 链接 / 卡片 / 主题与背景开关 / 阅读进度
│   └── styles/            tokens / global / typography / components / fonts
├── scripts/               构建脚本与日报生产线（Python + Node）
│   ├── daily/             日报包：窗口、增量、去重、组装、出题、判卷、定稿、发布
│   └── daily-image/       日报长图渲染（Playwright → sharp WebP）
├── data/
│   ├── daily/<期号>/      日报正本（进 git、永久、站点只读这里）
│   ├── xreader/           抓取库的按日切片（进 git，窗口内滚存）
│   └── glossary.json      译名与术语表
├── schemas/               3 份 JSON Schema：正本、生成题面、抓取条目
├── tests/                 Python 回归 + Markdown / Ci-en 的 node 测试 + golden 基准
├── public/                静态资源、字体、图片、5 份维护者 HTML 指南
├── docs/                  运营手册与架构契约
└── .github/workflows/     deploy.yml（构建部署）/ sync-profile-readme.yml（可选同步）
```

### 日报是怎么跑起来的

日报采用 **「CI 抓取 + 本地 LLM 摘要 + 站点 CI 部署」** 的混合方案：把「需要 LLM」的那一步留在本机，其余全自动、零成本、不需要服务器。

```text
X-Reader CI（每日两次抓取）→ data/items/*.jsonl
        ↓ git pull + 按日切片
data/xreader/{voice,galgame}/YYYY-MM-DD.jsonl
        ↓ 确定性组装（无 LLM）
out/<期号>/report.json 骨架 + briefing
        ↓ 出题 → 答题 → 判卷合并（唯一需要 LLM 的一步）
confirm → [Ci-en 版] → publish
        ↓
data/daily/<期号>/report.json  ← 站点只读这里
        ↓ push
deploy.yml：类型检查 → 构建 → 死链 → 日报出口校验 → 回归 → 部署
```

几条不能破的约定：

- **期号就是被覆盖的那一天，也是网址。** `YYMMDD`（JST）；声优版 `261107`，Galgame 版 `261107-g`，同日第二期 `261107-2` / `261107-g2`。`-1` / `-g1` 非法。
- **草稿留在 `out/`，进 `data/daily/` 就是已发布。** 位置本身就是状态，没有 `draft` 字段。
- **`sources` 是唯一能回溯的凭据。** 回答里的每一句都要指回一个来源 key，`apply` 逐条核对；来源不存在、handle 不在名单、长度超限，整份拒收。
- **两版是两次独立的 build。** 各读自己的库和名单，一份失败不拖住另一份。

完整流程、退出码、排查表见 [日报运营与维护指南](docs/daily-report-guide.md)。

### 常用命令

```bash
npm install      # 安装依赖
npm run dev      # 开发服务器 http://localhost:4321
npm run build    # 生产构建（含图片优化与搜索索引）
npm run check    # Astro / TypeScript 类型检查
npm run links    # 站内死链检查（要先 build）
npm test         # Python 回归
```

需要 Node **≥ 22.23.4**（`package.json` 的 `engines` 写死），以及 Python 3.9+（脚本与测试）。

### 设计约定

- 颜色、字号、间距、圆角、动效时长只在 `src/styles/tokens.css` 定义，组件里不写死色值。
- 个人信息只存在 `src/config/*.json` / `*.ts`，页面组件不保存任何个人资料。
- 数据用 JSON 是因为 README 同步脚本（Python）也要读同一份，避免两份互相冲突的配置。
- 站内链接一律写根绝对路径（`/blog/` 等），所以站点**必须部署在域名根路径**。
- `draft: true` 的文章永不发布：不出现在首页、归档、RSS、sitemap，也不生成页面。

---

## 文档

| 文档 | 内容 |
| --- | --- |
| [快速启动](README/quickstart.md) | 20 分钟把它变成你自己的主页：三步 + 上线检查清单 + 给 AI 的速查 |
| [项目说明](README/project.md) | 目录结构、路由、配置项、写文章、部署与排查 |
| [博客写作指南](README/blog-guide.md) | frontmatter、图片图注、注释（脚注）的写法与约定 |
| [Fork 指南](README/fork.md) | 从 fork 到上线（完整版）：子路径部署的改动清单、只要文字的做法、常见问题 |
| [广告位](README/ads.md) | 右侧栏广告位：默认关闭，怎么开、放得下什么尺寸、合规要求 |
| [日报运营与维护指南](docs/daily-report-guide.md) | 日报每天怎么出、期号规则、六出口、抓取侧、schema 与排查 |
| [日报长图方法](docs/daily-image-method.md) | 把一期日报渲染成一张晨报长图 |
| [译文口径](README/translation-style.md) | 译名与用词规范；词表本体在 `data/glossary.json` |
| [工作区现状](README/reports/workspace-status-2026-11-08.md) | 架构、抓取自动化细节、遗留产物与待办（2026-11-08 实测） |
| [主页 README 指南](https://epsilongg.github.io/docs/github-profile-readme-guide.html) | GitHub Profile README 怎么搭、怎么长期维护（浏览器直接打开） |
| [项目现状](https://epsilongg.github.io/docs/project-status.html) | 各部分完成度、已知不足与可优化点（浏览器直接打开） |

---

## 授权

**代码**（`src/`、`scripts/`、`tests/`、配置文件、工作流）用 [MIT](LICENSE)，随便拿去改、拿去用，保留版权声明即可。

**内容**（文章、译文、图片、文档）用 [CC BY-NC-SA 4.0](LICENSE-CONTENT)：署名、非商业、相同方式共享。

一句话：**代码随便用，内容不许商用。** 细节和译文/图片的特殊说明见 [LICENSE-CONTENT](LICENSE-CONTENT)。

---

<sub>Some Rights Reserved · 站点内容均来自于公开网络或博主自行创建，
未获得创作者本人同意时禁止以任意形式转载、分发。</sub>
