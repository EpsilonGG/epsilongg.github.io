# EpsilonGG · 个人主页

以个人简介和站点导航为入口的静态个人网站：首页先介绍「我是谁」，再提供名片、关于、链接库、归档四个入口，博客作为网站的一部分而不是主角。

- 站点地址：`https://epsilongg.github.io`（仓库：`github.com/EpsilonGG/epsilongg.github.io`）
- 技术栈：Astro 7（静态生成）、TypeScript、原生 CSS、Markdown + Content Collections（Zod 校验）
- 无前端框架、无数据库、无后端、无第三方托管平台
- 部署：GitHub Pages + GitHub Actions

---

## 1. 本地运行

需要 Node.js **>= 22.12**（本项目在 Node 22.22.2 上验证），以及 Python 3.9+（仅 README 同步脚本与单元测试需要）。

```bash
npm install      # 安装依赖
npm run dev      # 开发服务器，默认 http://localhost:4321
npm run build    # 生产构建，输出到 dist/
npm run preview  # 预览生产构建
npm run check    # Astro / TypeScript 类型检查
npm test         # Python 单元测试（README 同步脚本）
```

> 如果 `npm run dev` 提示端口被占用，可以用 `npm run dev -- --port 4322`。
>
> `astro` 版本锁定在 `7.3.8`：`astro@7.4.x` 要求 Node `>= 22.23.4`，在 22.22.x 上安装会报 `EBADENGINE`。升级 Astro 之前请先升级 Node。

---

## 2. 目录结构

```text
.
├── public/
│   ├── fonts/                 本地字体（Inter / Cormorant Garamond / Fira Code）+ 许可文本
│   ├── images/
│   │   ├── avatar.jpg         头像（460×460，与 GitHub 头像同步）
│   │   ├── blog/rurudo-unreal/  第一篇真实文章用的 11 张插图
│   │   ├── links/             友情链接徽章（88×31，按 2 倍图存放）
│   │   └── tools/             工具图标（48×48，按 2 倍图存放）
│   ├── favicon.svg
│   └── og-default.png         默认 Open Graph 分享图（1200×630）
├── src/
│   ├── components/            Header / Footer / 导航 / 链接行 / 链接列表 / 卡片 / 图标网格 / 徽章墙 / 最近文章 / 主题切换 / 阅读进度条
│   ├── config/                站点、个人资料、导航、链接、关于页的全部数据
│   ├── content/blog/          Markdown 文章
│   │   ├── rurudo-unreal-interview.md   第一篇真实文章
│   │   └── example.md                   草稿示例（draft: true，可以删除）
│   ├── content.config.ts      文章集合定义与 Zod 校验
│   ├── layouts/               BaseLayout（HTML 骨架与 SEO）/ ArticleLayout（文章阅读布局）
│   ├── lib/posts.ts           读取、排序、按年分组文章
│   ├── pages/                 路由：/ /links/ /me/ /morelinks/ /archive/ /blog/[slug]/ /404 /rss.xml /robots.txt
│   ├── scripts/theme.ts       主题状态的唯一实现
│   └── styles/                tokens / global / typography / components / fonts
├── scripts/sync_profile_readme.py   README 同步脚本
├── tests/test_readme_sync.py        同步脚本单元测试（22 个用例）
├── .github/workflows/         deploy.yml（部署）/ sync-profile-readme.yml（可选同步）
├── astro.config.mjs
└── package.json
```

设计约定：

- 颜色、字号、间距、圆角、动效时长只在 `src/styles/tokens.css` 定义，组件里不写死色值。
- 个人信息只存在 `src/config/*.json` / `*.ts`，页面组件不保存任何个人资料。
- 数据用 JSON（`site.json`、`profile.json`、`navigation.json`）是因为 README 同步脚本（Python）也要读取同一份数据，避免出现两份互相冲突的配置。

### 路由说明

| 路径 | 内容 |
| --- | --- |
| `/` | 首页：个人简介 → 站点导航 → 最近文章 → 页脚 |
| `/links/` | 名片页（主要平台入口） |
| `/me/` | 关于页 |
| `/morelinks/` | 链接库（分类展示） |
| `/archive/` | 文章归档，按年份分组 |
| `/blog/{slug}/` | 单篇文章，`slug` 即 Markdown 文件名 |
| `/rss.xml`、`/robots.txt`、`/sitemap-index.xml` | 自动生成 |
| 其他任意地址 | `404.html` |

**本站没有 `/blog/` 文章列表页**，这是有意设计：文章入口只有首页「最近文章」和 `/archive/`。直接访问 `/blog/` 会得到 404。

---

## 3. 当前状态

已经完成并验证的部分：

| 项目 | 状态 |
| --- | --- |
| 五个页面 + 文章页 + 404 | 构建通过，共 7 个页面 |
| 站点名称 / 域名 / 作者 / 邮箱 | 已填写为 EpsilonGG |
| 个人简介（姓名、定位、两段 intro、邮箱、description） | 已填写 |
| 头像 | 已下载到 `public/images/avatar.jpg`，并在 `profile.json` 中引用 |
| 第一篇真实文章 | `（译）INTERVIEW with rurudo——UNREAL 画集专访`，含 11 张本地插图 |
| 链接库改版 | 个人平台/项目用卡片、工具用图标网格、研究资料用列表、友情链接用 88×31 徽章墙 |
| 类型检查 | `npm run check`：29 个文件，0 error / 0 warning / 0 hint |
| 单元测试 | `npm test`：22 个用例全部通过 |
| 主题切换 / 阅读进度条 / 响应式 | 320 / 390 / 768 / 1280 宽度下无横向溢出 |
| GitHub Actions 部署工作流 | 已就绪，尚未触发过 |

仍为占位、需要你自己补的部分见第 4 节。

---

## 4. 需要你自己填写的内容

| 文件 | 字段 | 说明 |
| --- | --- | --- |
| `src/config/site.json` | `description` | 站点默认描述，当前是「个人主页：简介、名片、链接库与文章归档。」 |
| | `startYear` | 版权起始年份，当前 `2026` |
| | `email` | 公开邮箱，留空则 404 页不显示「报告问题」 |
| `src/config/profile.json` | `tagline` / `intro` / `description` | 已填写，可按需润色 |
| | `location` | 可选，当前为空（首页不显示地区） |
| `src/config/about.ts` | `intro` / `focusAreas` / `projects` / `experience` | `intro` 已填「不务正业的研究生」；后三项为空，`/me/` 对应区块显示「正在整理中」 |
| `src/config/links.ts` | `primaryLinks` | 已填 GitHub；其他平台可继续加，`/links/` 的「主要平台」区块会自动出现 |
| | `linkGroups` | 五个分类各有自己的 `layout`：个人平台/项目用卡片、工具用图标网格、研究与参考资料用列表、友情链接用徽章墙。见第 4.1 节 |
| `public/og-default.png` | 分享图 | 已按 EpsilonGG 生成；若改名需重新生成（见第 9 节） |
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
| `badges` | 88×31 徽章墙，纯图不带文字 | 友情链接 |

**加一个友情链接**：

1. 准备一张 88×31 的按钮图（对方站点通常有，或者自己做一张），放进 `public/images/links/`。建议存 2 倍图（176×62），在页面上仍按 88×31 显示，高分屏更清楚。
2. 在 `linkGroups` 里 `id: 'friends'` 那组的 `links` 中加一条：

```ts
{
  label: '友站名',              // 作为图片的 alt 文本，屏幕上不显示
  href: 'https://example.com/',
  badge: '/images/links/example.png',
}
```

3. 徽章默认灰度、鼠标悬停或键盘聚焦时恢复原色，这个效果由 CSS 控制，图片本身保持原色即可。

> 徽章下方**不渲染任何文字**，站点名必须写在图片里。这是为了保住 88×31 的紧凑规格——下面再挂一行长名字，徽章就白做小了。

**加一个工具图标**：把图标放进 `public/images/tools/`（按 48×48 显示，建议存 96×96），然后在 `tools` 组里加 `icon: '/images/tools/xxx.png'`。图标没填时会退化成文字方块，不会裂图。说明文字保持四个字左右，和图标同宽最整齐。

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
4. 打开 `https://epsilongg.github.io/` 确认首页；再检查 `/archive/`、`/links/`、`/me/`、`/morelinks/`、`/blog/rurudo-unreal-interview/`、`/rss.xml`、`/sitemap-index.xml`、`/robots.txt`，以及一个不存在的地址（应显示 404 页面）。

### 6.3 部署失败排查

| 现象 | 检查点 |
| --- | --- |
| Actions 报 `npm ci` 失败 | `package-lock.json` 是否已提交；Node 版本是否为 22 |
| 页面 404 | Pages 的 Source 是否选为 GitHub Actions；工作流是否成功 |
| 样式或图片丢失 | `site.json` 的 `url` 是否写成了仓库子路径；用户站点不要设置 `base` |
| 文章图片裂图 | 图片是否已提交到 `public/images/blog/...`；路径是否以 `/` 开头 |
| 深层文章刷新 404 | 属于 GitHub Pages 行为限制；本站所有页面都是预渲染的 `index.html`，正常情况不会出现 |
| canonical / RSS 域名错误 | 修改 `src/config/site.json` 的 `url` 后重新推送 |

### 6.4 关于 `url` 该写什么

写 **`https://epsilongg.github.io`**，也就是「协议 + 域名」，不要写 `https://github.com/EpsilonGG/epsilongg.github.io`。

原因：`site.json` 的 `url` 是站点根地址，`src/config/site.ts` 的 `absoluteUrl()` 会拿它拼出 canonical、Open Graph、RSS 与 sitemap 里的绝对链接。写成仓库地址会得到 `https://github.com/EpsilonGG/epsilongg.github.io/blog/xxx/` 这种并不存在的链接，搜索引擎和 RSS 阅读器都会拿到死链。仓库地址属于 GitHub，域名地址才是站点本身。

如果以后绑定了自定义域名（例如 `https://example.com`），只需要改这一处，其他文件不用动。

---

## 7. README 同步（可选）

`scripts/sync_profile_readme.py` 会把网站中的个人简介、主要入口、最近文章写入 GitHub Profile README 的三个指定区域。

个人资料仓库的 `README.md` 需要包含三对 Marker，顺序固定为 profile → navigation → posts：

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
- **Open Graph 图**：`public/og-default.png` 是静态图片（1200×630），修改姓名后可用任意工具重新生成一张覆盖它。
- **robots.txt** 由 `src/pages/robots.txt.ts` 按 `site.json` 的 `url` 生成，所以不在 `public/` 下，避免域名写两份。
- **主题**：默认浅色，用户选择保存在 `localStorage`；读取或写入失败时回退到浅色，不影响页面使用。首屏有内联脚本预先应用主题，避免闪烁。
- **移动端导航**：五个入口文字都很短，窄屏下换行显示而不是折叠菜单，因此没有额外的键盘交互与焦点管理负担。
- **转载文章**：第一篇是翻译作品，文首保留了原文出处、作者与版权说明。这类文章请自行确认授权范围。
