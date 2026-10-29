# Fork 指南：把它改成你自己的个人主页（完整版）

[← 返回仓库首页](../README.md) ｜ [快速启动](quickstart.md) ｜ [项目说明](project.md)

这个仓库本质上是「一套静态个人站的骨架 + 一堆 JSON 配置」。换成你自己的主页，需要动的地方其实只有 5 个配置文件加几张图，剩下的是部署。

> **只想尽快上线？** 看[快速启动](quickstart.md)，一页三步走完。
> 这一份是完整版：子路径部署怎么改、只做文字备份怎么做、以及踩过的坑。

下面按顺序走一遍，全程大约 30–60 分钟（不含写文章）。

---

## 0. 站点必须部署在域名根路径

这一条决定了你后面所有步骤能不能跑通，先说清楚。

站内链接一律写成**根绝对路径**，例如页头返回首页是 `href="/"`、页脚笔记是 `href="/blog/"`、图片是 `src="/images/avatar.jpg"`。这意味着：

| 你的仓库名               | 部署地址                                 | 能不能直接用          |
| ------------------- | ------------------------------------ | --------------- |
| `<你的用户名>.github.io` | `https://<你的用户名>.github.io/`         | ✅ 可以，什么都不用改     |
| 其他任意名字（如 `my-blog`） | `https://<你的用户名>.github.io/my-blog/` | ❌ 会整站 404 或样式全丢 |

> **仓库名必须叫 `<你的用户名>.github.io`。** 或者绑定自定义域名（自定义域名也是根路径，同样没问题）。

### 0.1 非要放在子路径下的话

本项目**没有**做这层适配，但它需要的改动是确定的，照着做大约半天。目标是让所有站内地址都带上 `/my-blog` 前缀：

| 位置 | 怎么改 |
| --- | --- |
| `astro.config.mjs` | 加 `base: '/my-blog'` |
| 组件 / 页面里的 `href="/…"` | 改成 `` `${import.meta.env.BASE_URL}…` ``；建议封一个 `withBase()` 工具函数，别散着改 |
| `src/config/navigation.json` | 里面存的是根路径，渲染时统一过一遍 `withBase()` |
| Markdown 里的 `/images/…` | 在 `src/lib/markdown-images.mjs` 里加一步：站内绝对路径前面拼 `base` |
| `site.json` 的 `ogImage` | 同样要拼 `base`，否则分享图指向域名根 |
| `rss.xml.ts` | RSS 里的绝对链接要手动补 `base`；`@astrojs/sitemap` 会自动带上，不用管 |

改完之后 `npm run links` 会立刻告诉你漏了哪几处——它按 `dist/` 里的真实文件比对，前缀不对就是死链。

---

## 1. 拿到代码

三种方式，选一种：

| 方式                | 命令 / 操作                                | 适合         |
| ----------------- | -------------------------------------- | ---------- |
| Fork              | 仓库右上角 **Fork**                         | 想保留和原仓库的关联 |
| 下载 zip            | **Code → Download ZIP**，解压后 `git init` | 想从零开始，不要历史 |
| Use this template | 仓库右上角 **Use this template**（若已开启）      | 同上，但操作更顺手  |

Fork 之后，仓库名默认还是 `epsilongg.github.io`，**必须改名**：

> 仓库页 → **Settings** → **Repository name** → 改成 `<你的用户名>.github.io` → **Rename**

GitHub 允许同名仓库存在，但只有 `<用户名>.github.io` 这个名字才会被当成用户站点。

---

## 2. 改这 5 个文件

全在 `src/config/` 下。改完这 5 个，站点的「内容」就完全是你的了。

### 2.1 `site.json` —— 站点本身

```json
{
  "name": "你的名字",
  "url": "https://你的用户名.github.io",
  "description": "一句话描述这个站",
  "author": "你的名字",
  "startYear": 2026,
  "ogImage": "/og/default.jpg",
  "github": "https://github.com/你的用户名",
  "email": "你的邮箱"
}
```

- **`url` 只写「协议 + 域名」**，不要带结尾斜杠，更不要写成 `https://github.com/你/你.github.io`。canonical、Open Graph、RSS、sitemap 全靠它拼绝对地址，写错就是一堆死链。
- `github` / `email` 留空则页脚不显示对应链接，不会报错。
- `startYear` 是版权起始年份，页脚会显示 `© 2026–2026` 或 `© 2026`。

### 2.2 `profile.json` —— 首页上的你

```json
{
  "name": "你的名字",
  "tagline": "一句话定位",
  "intro": ["第一段自我介绍", "第二段"],
  "avatar": "/images/avatar.jpg",
  "email": "你的邮箱",
  "description": "个人主页"
}
```

`intro` 是数组，每一项渲染成一个段落；留空则不显示。

### 2.3 `about.ts` —— `/me/` 名片页

`intro`（一段话）、`focusAreas`（关注领域，字符串数组）、`projects`（`{ title, href, description }`）、`experience`（`{ title, description }`）。任何一项留空，页面对应区块显示「正在整理中」，不会报错。

### 2.4 `navigation.json` —— 首页的站点导航

首页中间那排入口。`href` 用站内路径（例如 `/me/`），`description` 会显示在名称下面。

### 2.5 `links.ts` —— 名片页（/me/「主要平台」）与链接库

两个导出：`primaryLinks`（名片页 /me/ 的「主要平台」）和 `linkGroups`（链接库的五个分类）。四种排版（`list` / `cards` / `icons` / `badges`）的用法见[项目说明第 4.1 节](project.md#41-链接库的四种排版)。

**最省事的做法**：把 `linkGroups` 里现成的示例（GitHub 朋友、ACG 资源、工具）整组删掉，只留你真正想放的。删空的分类不会渲染。

---

## 3. 换图

| 文件                           | 要求                | 不换会怎样              |
| ---------------------------- | ----------------- | ------------------ |
| `public/images/avatar.jpg`   | 1:1，建议 ≥ 400×400  | 显示的是原作者的 GitHub 头像 |
| `public/favicon.svg`         | 浏览器标签页图标          | 显示原作者的图标           |
| `public/og/default.jpg`      | 1200×630          | 分享到社交平台时预览图是原作者的   |
| `public/images/links/icons/` | 64×64 PNG         | 链接库的站点图标           |
| `public/images/people/`      | 64×64 PNG         | 常用链接里 GitHub 朋友的头像 |
| `public/images/tools/`       | 96×96 PNG（白色圆角方块） | 工具与服务的图标           |

头像可以直接用 GitHub 头像：把 `https://github.com/<你的用户名>.png?size=460` 的图片另存为 `avatar.jpg`（这个地址返回的其实是 JPEG，所以后缀写 `.jpg`）。

图片尺寸对不上不会报错，只是显示效果差一点。图标缺失时会退化成字母块，不会裂图。

---

## 4. 清掉示例内容

```bash
# 示例文章（连同插图一起删）
rm src/content/blog/example.md
rm src/content/blog/rurudo-unreal-interview.md
rm -rf public/images/blog/rurudo-unreal

# 原作者的文档（可选，留着也不影响构建）
rm -rf public/docs
```

删完之后 `npm run build` **仍然能通过**（已验证：0 篇文章时构建 6 个页面），笔记页会显示「暂无文章」，RSS 输出一个空的 channel。

> `public/images/people/`、`public/images/links/icons/`、`public/images/tools/` 里是原作者的图标素材。要删就先删 `links.ts` 里对应的条目，否则会留下裂图——顺序反了也不会报错，只是页面上出现空图标。

写第一篇文章的方法见[项目说明第 5 节](project.md#5-写文章)：文件名就是 URL，`pubDate` 必填。

---

## 5. 本地跑一遍

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # 确认能构建
npm run check    # 类型检查
npm run links    # 站内死链检查（要先 build）
```

需要 Node **≥ 22.23.4**。`astro@7.4` 的 `engines` 有这个硬下限，低于它 `npm install` 会报 `EBADENGINE`。仓库里的 `package.json` 已经把这条写进去了，`nvm use 24` 之类切一下最省事。

---

## 6. 打开 GitHub Pages

1. 仓库 **Settings → Pages**。
2. **Build and deployment → Source** 选 **GitHub Actions**（不要选 "Deploy from a branch"）。
3. 回到 **Actions** 标签，等 `Deploy to GitHub Pages` 跑完（首次约 1–2 分钟）。
4. 打开 `https://<你的用户名>.github.io/`。

工作流 `.github/workflows/deploy.yml` 已经在仓库里：`push` 到 `main` 就自动跑一遍，顺序是

```
npm ci → npm run check → npm run test:md → npm run build → npm run links → npm test → 上传 dist → 部署
```

任何一步红了就不会发布——所以**推上去变红，先看 Actions 里是哪一步**，别急着怀疑 Pages。

> **Fork 来的仓库第一次可能需要在 Actions 页面点一次 “I understand my workflows, go ahead and enable them”。**

---

## 7. 上线检查清单

- [ ] 仓库名是 `<用户名>.github.io`
- [ ] `site.json` 的 `url` 是 `https://<用户名>.github.io`（无斜杠、无子路径）
- [ ] 首页、`/me/`、`/morelinks/`、`/blog/` 都能打开
- [ ] 文章页能打开，图片正常显示
- [ ] 随便输一个不存在的地址，显示 404 页面而不是 GitHub 的默认 404
- [ ] `/rss.xml` 里的域名是你自己的
- [ ] 深色模式正常（右上角切换按钮）
- [ ] 手机宽度下没有横向滚动条
- [ ] 页脚的版权年份和署名是你自己的

---

## 8. 可选：把你的 GitHub 主页 README 也接上

这个仓库还带了一个 Python 脚本，可以把网站里的简介、导航、最近文章同步到你的 **GitHub Profile README**（即 `<用户名>/<用户名>` 仓库里的 `README.md`）。

1. 新建一个和用户名同名的仓库，勾选 Add a README file。
2. 在它的 `README.md` 里放三对 Marker（顺序固定：profile → navigation → posts）：

   ```markdown
   <!-- PROFILE:START -->
   <!-- PROFILE:END -->

   <!-- NAV:START -->
   <!-- NAV:END -->

   <!-- POSTS:START -->
   <!-- POSTS:END -->
   ```

3. 把网站仓库和 profile 仓库克隆到同一个父目录，然后：

   ```bash
   python scripts/sync_profile_readme.py --readme ../<你的用户名>/README.md --check   # 先看要不要更新
   python scripts/sync_profile_readme.py --readme ../<你的用户名>/README.md           # 真正写入
   ```

只替换 Marker 之间的内容，Marker 之外的手写内容逐字保留；Marker 缺失、重复或顺序错乱会直接报错退出，不会瞎猜位置。

完整原理、Actions 自动同步和 token 配置见 [`public/docs/github-profile-readme-guide.html`](../public/docs/github-profile-readme-guide.html)（部署后可在 `/docs/github-profile-readme-guide.html` 打开）。

---

## 9. 另开一个账号做文字备份

场景：另开一个 GitHub 账号，把仓库 fork 过去，只用来给公众号 / B 站专栏的文章留一份可搜索、可直链的网页备份。三条路径，**第一条不需要改任何代码**。

### 9.1 路径 A · 新账号 + 同名仓库（推荐，零改动）

子路径部署的所有麻烦，都来自「仓库名不是 `<name>.github.io`」。只要新账号下建的仓库**正好叫这个名字**，Pages 就挂在域名根上，现在这套根绝对路径全部直接可用。

1. 新 GitHub 账号下新建仓库 `<新账号名>.github.io`（必须一字不差）
2. 把本仓库的 `src/`、`public/`、`scripts/`、`tests/`、`astro.config.mjs`、`package*.json`、`.github/` 拷过去（或直接 fork 后改 remote）
3. 改四个文件（见下表），这是唯一必须动的地方
4. 删掉不需要的内容（见 9.2）
5. 仓库 Settings → Pages → Source 选 **GitHub Actions**
6. push 一次，等一分钟

| 文件 | 改什么 |
| --- | --- |
| `src/config/site.json` | 站名、`url`（改成新域名，OG 图靠它）、描述、起始年 |
| `src/config/profile.json` | 姓名、简介、头像、邮箱 |
| `src/config/navigation.json` | 导航项；只留「笔记」一项也完全可以 |
| `src/config/about.ts` | 名片页内容，或者直接删掉这个页面（见 9.2） |

### 9.2 只做文字备份时，删掉这些

| 删什么 | 后果 |
| --- | --- |
| `src/pages/me.astro`、`morelinks.astro` | 名片页与链接库消失。**必须同时改 `navigation.json`**，否则导航里留死链 |
| `src/config/links.ts`、`about.ts` 与链接库组件 | 没人引用就不会报错，留着也不影响构建 |
| `src/content/blog/` 下不要的文章 + `public/images/blog/` 对应目录 | 删文章记得连图一起删，否则 `npm run images` 会继续给它们出变体 |
| `public/docs/` 整个目录 | 那几份 HTML 指南是写给这个项目自己的，新站用不上 |
| `scripts/sync_profile_readme.py`、`tests/test_readme_sync.py`、`.github/workflows/sync-profile-readme.yml` | 这套东西只服务「把站点内容同步到 GitHub 主页 README」，备份站不需要 |
| `public/og/default.jpg` | 换成自己的分享图，1200×630（`npm run og` 会覆盖） |

删完记得跑一次 `npm run build && npm run links`。**构建不会因为死链报错**（导航里写了个不存在的页面照样输出），死链检查会。

### 9.3 路径 B · 非要子路径部署的话

见[第 0.1 节](#01-非要放在子路径下的话)的改动清单，大约半天工作量。

### 9.4 路径 C · 根本不要站点，只要文字

如果目标只是「把文章搬进公众号后台」，那连 fork 都不用：直接打开线上的文章页，全选复制，粘进编辑器。Markdown 里的 `**加粗**` 和列表粘过去会变成纯文本，需要重新排一遍——所以**真正省事的做法是留着 `.md` 源文件本身**，它才是内容的真身，HTML 只是它的一种渲染结果。

### 9.5 备份时绕不开的三个现实问题

- **公众号正文基本不能带外链**。译文里的原文出处链接会被折叠或要求改写成文字，建议在正文末尾统一写「原文：xxx（链接见站点）」，站点那份保留可点的链接
- **图片要重新上传**。公众号不接受外链图床，本地图得再传一遍；本站的 WebP 变体不用带过去，原图（`.jpg` / `.png`）才是通用格式
- **授权跟着仓库走**。fork 出去后 `LICENSE`（MIT）和 `LICENSE-CONTENT`（CC BY-NC-SA）也一起过去了。备份自己的文章没问题；如果备份的是别人的译文，**出处必须一起保留**——那是 CC 署名的要求，也是原作者的底线

---

## 10. 常见问题

**Q：`npm install` 报 `EBADENGINE`**  
Node 版本太低。`astro@7.4` 要求 Node ≥ 22.23.4，切到 Node 24 最省事。

**Q：Actions 里 `npm ci` 失败**  
`package-lock.json` 没提交。`git add package-lock.json` 后重新推。

**Q：页面 404**  
Pages 的 Source 没选 GitHub Actions，或者工作流失败了。先看 Actions 页面。

**Q：`npm run links` 报死链**  
按提示改链接，或者把那个页面补回来。它只查站内（本地文件比对），报出来的都是真死链。常见来源：改了文章文件名（slug 就是文件名）、删了页面没改导航、标题改了但目录锚点没跟着变。

**Q：样式全丢、只有裸 HTML**  
几乎一定是仓库名不是 `<用户名>.github.io`，导致站点跑在子路径下而链接是根路径。改仓库名，或者去看第 0 节。

**Q：Actions 里还有一条 `pages build and deployment` 是红的**  
那是 GitHub 早期的 Jekyll 构建流水线，和本站无关。只要 `Deploy to GitHub Pages` 是绿的就可以忽略。

**Q：改完推送了，刷新没变化**  
GitHub Pages 有缓存，等 1–2 分钟，用 `Ctrl + F5` 强制刷新。

**Q：想绑定自己的域名**  
仓库 Settings → Pages → Custom domain 填域名，DNS 加一条 CNAME 指向 `<用户名>.github.io`。然后把 `site.json` 的 `url` 改成新域名，推送即可（其他文件不用动）。

**Q：可以商用 / 二次分发吗**  
代码是 [MIT](../LICENSE)，随便用；文章、译文、图片是 [CC BY-NC-SA 4.0](../LICENSE-CONTENT)，可以转载但要署名、非商业、相同方式共享。**内容不许商用**，译文还要保留原文出处。

---

## 附：最小改动速查

只想最快上线，改这 6 处就够：

```
src/config/site.json      name / url / author / email
src/config/profile.json   name / tagline / intro
public/images/avatar.jpg  换掉
public/favicon.svg        换掉
public/og/default.jpg     换掉（或改 scripts/make_og.mjs 的 BG）
（仓库名改成 <用户名>.github.io）
```
