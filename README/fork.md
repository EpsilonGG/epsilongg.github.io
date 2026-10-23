# Fork 指南：把它改成你自己的个人主页

[← 返回仓库首页](../README.md) ｜ [项目说明](project.md)

这个仓库本质上是「一套静态个人站的骨架 + 一堆 JSON 配置」。换成你自己的主页，需要动的地方其实只有 5 个配置文件加几张图，剩下的是部署。

下面按顺序走一遍，全程大约 30–60 分钟（不含写文章）。

---

## 0. 站点必须部署在域名根路径

这一条决定了你后面所有步骤能不能跑通，先说清楚。

站内链接一律写成**根绝对路径**，例如页头返回首页是 `href="/"`、页脚笔记是 `href="/blog/"`、图片是 `src="/images/avatar.jpg"`。这意味着：

| 你的仓库名               | 部署地址                                 | 能不能直接用          |
| ------------------- | ------------------------------------ | --------------- |
| `<你的用户名>.github.io` | `https://<你的用户名>.github.io/`         | ✅ 可以，什么都不用改     |
| 其他任意名字（如 `my-blog`） | `https://<你的用户名>.github.io/my-blog/` | ❌ 会整站 404 或样式全丢 |

想让它在项目站（带子路径）下工作，得把组件里所有 `href="/xxx"`、`src="/xxx"` 改成 `import.meta.env.BASE_URL + 'xxx'`，并在 `astro.config.mjs` 里加 `base`。本项目**没有**做这层适配，所以：

> **仓库名必须叫 `<你的用户名>.github.io`。** 或者绑定自定义域名（自定义域名也是根路径，同样没问题）。

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
  "ogImage": "/og-default.png",
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
| `public/og-default.png`      | 1200×630          | 分享到社交平台时预览图是原作者的   |
| `public/images/links/icons/` | 64×64 PNG         | 链接库的站点图标           |
| `public/images/people/`      | 64×64 PNG         | 常用链接里 GitHub 朋友的头像 |
| `public/images/tools/`       | 96×96 PNG（白色圆角方块） | 工具与服务的图标           |

头像可以直接用 GitHub 头像：把 `https://github.com/<你的用户名>.png?size=460` 的图片另存为 `avatar.jpg`（这个地址返回的其实是 JPEG，所以后缀写 `.jpg`）。

图片尺寸对不上不会报错，只是显示效果差一点。图标缺失时会退化成字母块，不会裂图。

---

## 4. 清掉示例内容

```bash
# 示例文章（连同插图一起删）
rm src/content/blog/rurudo-unreal-interview.md
rm src/content/blog/example.md
rm -rf public/images/blog/rurudo-unreal

# 原作者的文档（可选，留着也不影响构建）
rm -rf public/docs
```

删完之后 `npm run build` **仍然能通过**（已验证：0 篇文章时构建 6 个页面），归档页会显示「暂无文章。归档会随新文章发布自动更新。」，RSS 输出一个空的 channel。

> `public/images/people/`、`public/images/links/icons/`、`public/images/tools/` 里是原作者的图标素材。要删就先删 `links.ts` 里对应的条目，否则会留下裂图——顺序反了也不会报错，只是页面上出现空图标。

写第一篇文章的方法见[项目说明第 5 节](project.md#5-写文章)：文件名就是 URL，`pubDate` 必填。

---

## 5. 本地跑一遍

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # 确认能构建
npm run check    # 类型检查
```

需要 Node **≥ 22.12**。如果你装的是 22.23.x 以下但想升级 Astro，注意 `astro@7.4.x` 要求 Node ≥ 22.23.4，否则 `npm install` 会报 `EBADENGINE`；本仓库锁在 `astro@7.3.8` 就是为了兼容 Node 22.22。

---

## 6. 打开 GitHub Pages

1. 仓库 **Settings → Pages**。
2. **Build and deployment → Source** 选 **GitHub Actions**（不要选 "Deploy from a branch"）。
3. 回到 **Actions** 标签，等 `Deploy to GitHub Pages` 跑完（首次约 1–2 分钟）。
4. 打开 `https://<你的用户名>.github.io/`。

工作流 `.github/workflows/deploy.yml` 已经在仓库里：`push` 到 `main` 就自动构建 + 部署，里面依次执行 `npm ci` → `npm run check` → `npm run build` → 上传 `dist` → 部署。

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
2. 在它的 `README.md` 里放三对 Marker（顺序固定）：
   ```markdown








   ```
3. 把网站仓库和 profile 仓库克隆到同一个父目录，然后：
   ```bash
   python scripts/sync_profile_readme.py --readme ../<你的用户名>/README.md --check   # 先看要不要更新
   python scripts/sync_profile_readme.py --readme ../<你的用户名>/README.md           # 真正写入
   ```

完整原理、Actions 自动同步和 token 配置见 [`public/docs/github-profile-readme-guide.html`](../public/docs/github-profile-readme-guide.html)（部署后可在 `/docs/github-profile-readme-guide.html` 打开）。

---

## 9. 常见问题

**Q：`npm install` 报 `EBADENGINE`**  
Node 版本太低。装 Node 22.12 以上；或者别动 `package.json` 里锁定的 `astro` 版本。

**Q：Actions 里 `npm ci` 失败**  
`package-lock.json` 没提交。`git add package-lock.json` 后重新推。

**Q：页面 404**  
Pages 的 Source 没选 GitHub Actions，或者工作流失败了。先看 Actions 页面。

**Q：样式全丢、只有裸 HTML**  
几乎一定是仓库名不是 `<用户名>.github.io`，导致站点跑在子路径下而链接是根路径。改仓库名，或者去看第 0 节。

**Q：Actions 里还有一条 `pages build and deployment` 是红的**  
那是 GitHub 早期的 Jekyll 构建流水线，和本站无关。只要 `Deploy to GitHub Pages` 是绿的就可以忽略。

**Q：改完推送了，刷新没变化**  
GitHub Pages 有缓存，等 1–2 分钟，用 `Ctrl + F5` 强制刷新。

**Q：想绑定自己的域名**  
仓库 Settings → Pages → Custom domain 填域名，DNS 加一条 CNAME 指向 `<用户名>.github.io`。然后把 `site.json` 的 `url` 改成新域名，推送即可（其他文件不用动）。

**Q：可以商用 / 二次分发吗**  
这个仓库没有附 License 文件，默认保留所有权利。自己用、改成自己的主页没问题；要再分发或用于商业用途，请先联系作者。

---

## 附：最小改动速查

只想最快上线，改这 6 处就够：

```
src/config/site.json      name / url / author / email
src/config/profile.json   name / tagline / intro
public/images/avatar.jpg  换掉
public/favicon.svg        换掉
public/og-default.png     换掉
（仓库名改成 <用户名>.github.io）
```
