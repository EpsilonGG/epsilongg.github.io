# 日报图片生成方法（Morning-Paper Image）

> **用途**：把 `data/daily/<id>/report.json` 渲染成一张「每日晨报」长图。
> **读者**：agent（或下次接手的自己）。本文件是**操作手册**，照 §0 就能出图；§3 是这次重选的风格方案与理由。
> **关联文档**：`README/reports/daily-m5-m6-options.html` §9.6（M5 目标）；`docs/daily-report-guide.md`（日报运营流程）；`schemas/report.schema.json`（数据契约）；`src/styles/tokens.css`（配色来源）。

---

## 0. TL;DR（下次直接出图）

```bash
export PATH="/c/Program Files/nodejs:$PATH"

# 1) 确认依赖（resvg 目前靠 --no-save 存在 node_modules，没写进 package.json）
ls node_modules/@resvg/resvg-js/package.json || npm i @resvg/resvg-js --no-save

# 2) 出图（默认本机 Windows 雅黑；CI/生产用 OG_FONTS 指全量 Noto Sans SC）
node README/reports/og-demo/morning-paper.mjs \
  data/daily/261101/report.json \
  README/reports/og-demo/morning-261101.png

# 3) 目视验收：报头 / 数据条 / 导语 / 今日看点 / 新作热作 / 页脚 六块都在，
#    无缺字方框、无溢出、无双栏串行
```

- **输出**：竖版长图，宽 1080px，高随内容（261101 实测 1080×2196）。
- 只读 `report.json`，不写回；不碰 `src/templates`（那是另一套 React 卡片，见 §5）。

---

## 1. 输出规格

| 项 | 值 |
|---|---|
| 方向 | 竖版长图 |
| 宽 | 固定 1080px |
| 高 | 随内容（resvg `fitTo: {mode:'width'}`） |
| 边距 | 左右 64px（内容宽 952） |
| 配色 | **直接取站点 tokens**：墨 `#1a1a1a` / 次级 `#555` / 弱 `#767676` / 分隔 `#e5e5e5` / 强调分隔 `#cfcfcf` / 反白块 `#1a1a1a` 底 + 白字 |
| 圆角 | 6px（只有导语反白块用；其余直角） |
| 阴影 | 无 |
| 字体 | 单一无衬线（本机雅黑 / 生产 Noto Sans SC），**不用斜体、不用衬线** |
| 板块 | ① 报头 ② 数据条 ③ 导语（反白块）④ 今日看点 ⑤ 新作热作（双栏）⑥ 页脚 |

目标观感：报纸头版，不是 OG 分享卡（OG 仍走 `scripts/make_og.mjs`，只裁图不加字）。

---

## 2. 数据源（report.json）

唯一输入：`data/daily/<id>/report.json`（构建产物，`status: confirmed`）。

| 板块 | 字段 | 形态 | 上限 |
|---|---|---|---|
| 报头 | `issue.id` 派生 | `261101` → 2026.11.01；含 `-g` → Galgame 日报，否则声优日报 | — |
| 数据条 | `counts.items` / `counts.accounts` / `highlights.length` / `works.length` | 数字 | — |
| 导语 | `description` | 字符串 | ≤70 字（schema 硬限） |
| 今日看点 | `highlights[].text` | 对象数组 | ≤4 条（图里取前 4） |
| 新作热作 | `works[]` | **字符串数组，一条一个作品** | ≤24 条（图里取前 24） |

**期号解析**：日期来自 `id` 本身（JST 被覆盖的那一天），**不是** `issue.published_at`。正则 `^(\d{2})(\d{2})(\d{2})(?:-g\d*)?$`。

**注意**：`works` 是数组不是段落；「开始发售/预约」的条目必须写作品名。图片逐条渲染，不做合并。

---

## 3. 风格方案选型（2026-11-02 重选）

### 3.1 结论

**主体骨架用 `blackWhiteEditorial`（黑白社论），报头借 `editorialMagazine`（杂志社论）的刊号/刊头，新作清单借 `swissStyle` 的编号网格。**

三者的共同点正好对上本站铁律：**不靠装饰色、不靠阴影，只靠字重、字号、发丝线和留白做层级**。所以可以零依赖地在 SVG 里复刻，不需要把 React 那套跑起来。

### 3.2 为什么是它（对比表）

| 候选 | 加分 | 减分 | 判决 |
|---|---|---|---|
| **blackWhiteEditorial** | 强对比、发丝线、四角 accent、可反白块、天然黑白 | 原版是 1920×1080 卡片网格 | **选它当骨架** |
| editorialMagazine | 刊号/页码/装饰线/首字下沉，报头感最强 | 主色是金色 `#c9a227`，破本站黑白灰；衬线标题 | 只借**版式**，不借色与字 |
| swissStyle | 严格网格、编号、无衬线、纯黑白 | 卡片描边 2px 偏重；横向画布 | 只借**编号 + 网格** |
| newsCard | 描边卡片、栏目色条 | 硬投影 + 30px 大圆角，违反本站约定 | 弃 |
| minimalism / hyperMinimal | 极简留白 | 信息密度撑不住 20 条新作 | 备选（条目少时可用） |
| gridPoster / bauhaus | 海报张力强 | 装饰性抢内容，日报要的是可读 | 弃 |

### 3.3 借来的三个记号（都在 `morning-paper.mjs` 里）

1. **四角 accent**（blackWhiteEditorial）：整图四角 18×18 的 L 形 2px 描边，内缩 22px。反白块里也放一份白色版。
2. **报头双线**（报纸传统 + editorialMagazine 的刊头）：`EPSILONGG · DAILY` + `NO. <期号>` 一行 → 发丝线 → 大标题 + 右侧日期 → 7px 粗线 + 1px 细线压底。
3. **编号网格**（swissStyle）：区块号 `01`/`02` 用 54px `#cfcfcf` 靠右；条目序号 `01…20` 用 17px 同色，与正文左对齐成一列。

### 3.4 明确不做的

- 不做首字下沉（CJK 下沉字要单独排版，收益低、易错位）。
- 不用衬线标题：字体管线只钉一份无衬线，混排要额外钉字体，得不偿失。
- 不加阴影、不加彩色栏目条、不用大圆角。

---

## 4. 渲染路径 A —— SVG + resvg（唯一在用）

### 4.1 文件与依赖

- 脚本：`README/reports/og-demo/morning-paper.mjs`（手工拼 SVG → `@resvg/resvg-js` → PNG）。
- `@resvg/resvg-js` **当前在 `node_modules` 但不在 `package.json`**（`--no-save` 装的）。生产应转正为 `devDependencies`。
- 字体：默认 `C:/Windows/Fonts/msyh.ttc` + `msyhbd.ttc`（仅本机）。生产/CI 用环境变量覆盖：
  ```
  OG_FONTS="path/NotoSansSC-Regular.ttf,path/NotoSansSC-Bold.ttf"
  OG_FAMILY="Noto Sans SC"
  ```

### 4.2 版式骨架（改模板时按这张表改，别凭感觉）

| 元素 | 尺寸 / 位置 |
|---|---|
| 报头 kicker | 18px / 600 / `#767676` / 字距 0.16em；左 `EPSILONGG · DAILY`，右 `NO. <id>` |
| 报头发丝线 | y=76，1px `#cfcfcf` |
| 主标题 | 92px / 700 / `#1a1a1a`，基线 y=178 |
| 右侧日期 | 42px / 700，基线 = 标题基线 − 34；副行 18px `#767676`，基线 = 标题基线 |
| 双线 | y=208 粗 7px + y=221 细 1px |
| 数据条 | 数字 34px/700 基线 262，单位 16px `#767676` 基线 292，列间 1px 竖线（238–300）；下沿 1px 线 y=330 |
| 导语反白块 | 整幅 952×`(52 + 行数×44 + 26)`，圆角 6，四角白 L 形；标签 16px `#a0a0a0`；正文 30px/500 白 |
| 区块标题 | 左侧 8×36 黑条 + 38px/700 标题 + 18px 备注；右侧 54px `#cfcfcf` 编号；下压 2px 黑线 |
| 看点条目 | 序号 30px/700 `#cfcfcf`；正文 28px，行高 41，最多 3 行，左缩进 62 |
| 新作双栏 | 栏宽 `(952−44)/2 = 454`，栏间距 44，中缝 1px 竖线；序号 17px `#cfcfcf`，正文 24px，行高 35，最多 3 行，左缩进 34 |
| 分栏 | 按「每条实测行高累加 ≥ 总高一半」切，不按条数均分 |
| 页脚 | 1px 黑线 → 左 `epsilongg.github.io/daily/`，右 `<日期> <版名> · 由结构化数据自动生成`，19px |

### 4.3 文本度量与断行（今天新写的两块，改之前先读）

- **`charW()` 估算**：CJK/假名/全角标点 = 1.0em，大写 0.64，数字 0.56，窄标点 0.3，空格 0.28。**只用于 CJK 正文**，够准。
- **西文不能按字断**：`tokenize()` 先把 `[A-Za-z0-9]` 连成的串（含 `. ' - / &` 连接符）当**一个 token**，整体换行。否则会出现 `FANZA GA` / `MES` 这种断词。单个 token 超栏宽才退回按字切。
- **禁则**：行首禁则（`」』）】、，。？！…` 等）把标点挂在上一行尾，允许溢出半个字；行尾禁则（`「『（【`）把开引号带到下一行。
- **截断而非缩字号**：`fit(text, size, width, maxLines)` 超行数就截断加 `…`。**不要退回「按宽度缩字号」**，那会让字号层级乱掉。

### 4.4 已知坑（踩过，必看）

1. **绝不能用 og-demo 的 `NotoSub-*.ttf`**：那是子集，只含样例那几个字，正文会大面积空白（resvg 找不到字形连方框都不画）。**正文必须全量 CJK**。
2. **`loadSystemFonts:false` + 显式 `fontFiles`**：否则不同机器字体不同，跨机结果不一致。
3. **数字宽度不可测**：雅黑数字是比例宽（`1` 很窄），估算值和实际对不上，横向「数字 + 单位」紧排必撞。**所以数据条改成上下堆叠**（数字在上、单位在下）——这是设计上的规避，不是偷懒。
4. **报头日期与副行基线至少差 30px**：42px 的大数字基线只比 18px 副行高 8px 会直接叠字。
5. **区块标题与上一块至少隔 48px**：黑条顶端算起，太近会糊成一片。
6. **四角 accent 离页脚文字至少 20px**：否则像挂在文字尾巴上。
7. 默认字体路径是 Windows 专用；**CI（Linux）必须靠 `OG_FONTS` 覆盖**，否则直接报错退出。
8. resvg 产出**字节稳定**（自带字体解析），这是选它而不是无头 Chrome / sharp 的主因。

---

## 5. 渲染路径 B —— `src/templates`（React/TSX，当前仍是 orphaned）

- 181 个视觉风格组件（`src/templates/*.tsx`），每个导出 `TemplateConfig`：`render(data, scale) => ReactElement`。
- 数据形状 `GeneratedContent`：`{ mainTitle: string; cards: Array<{icon, title, desc}> }`。
- 画布**固定 1920×1080 横向**，内容是「主标题 + N 张卡片」网格。
- 入口：`index.ts`（`TEMPLATES`）、`catalog.ts`（`THEME_CATEGORIES` + 默认 `claudeStyle`）、`meta.json`。

**为什么现在不用它**：

1. 组件 `import '../types'` / `'../utils/template'` / `'../utils/layout-calculator'`，这些文件在本仓库不存在，且 `package.json` 没有 `react` —— 直接编译必失败。
2. 画布 1920×1080 横向卡片网格 ≠ 晨报竖版长图；改自适应高度等于重写组件。
3. fit 逻辑在浏览器端 `useLayoutEffect` 里，SSR 出来是未适配版式，要再跑无头浏览器。
4. HTML→截图依赖系统字体与浏览器版本，**跨机字节不稳定**，和 §4.4-8 相反。

**真要接的话**（大工程，先和用户确认）：装 `react` + `react-dom` + TSX 加载器 → 补齐 `src/types.ts`、`src/utils/template.ts`、`src/utils/layout-calculator.ts` → `renderToStaticMarkup` 出 HTML → Playwright 截图 → 把 `report.json` 映射成 `GeneratedContent`。

**现阶段结论**：只要「晨报长图」，**不需要**路径 B。它的价值是**抄视觉语言**（§3.3），零新增依赖。

> 更正（2026-11-02）：`src/types.ts` / `src/utils/*` 在**它自己的仓库**（`juya-news-card-main/`）里是齐的，
> 缺的只是我们根目录那一份。所以整套跑图是可行的，见 §8。

---

## 6. 下次出图 checklist

1. 有 `confirmed` 的 `data/daily/<id>/report.json`。
2. `@resvg/resvg-js` 在 `node_modules`。
3. 字体就绪：本机雅黑可直接跑；CI 必须设 `OG_FONTS`。
4. 跑 §0 的命令。
5. 目视验收（逐条过）：
   - 报头：`NO.` 期号、日期、星期、副行无叠字；
   - 数据条：四格数字与单位不撞；
   - 导语：反白块内文字不贴边、四角记号在块内；
   - 看点：序号列齐、≤4 条；
   - 新作：双栏高度接近、无 `FANZA GA / MES` 式断词、无串栏；
   - 页脚：四角 accent 不压字。
6. Galgame 版回归跑一遍（`data/daily/<id>-g/report.json`）：`Galgame 日报` 标题比 `声优日报` 宽 3 倍，容易顶到日期。

---

## 7. 待办 / 决策点（需用户拍板）

- [ ] **字体**：钉死全量 `Noto Sans SC`（M5.2），写进依赖、记 SHA、不进 git。
- [ ] **`package.json`**：`@resvg/resvg-js` 从 `--no-save` 转正为 `devDependencies`。
- [ ] **生产化**：脚本从 `og-demo` 提升进 `scripts/daily/`，是否随日报发布自动出图。
- [ ] **音声推荐板块**：数据源待定（`people[]` / `works[]` 关键词过滤 / 新增 `recommendations` 字段）。
- [ ] **条目数上限**：现在取前 24 条；261101 实测 20 条已到 2196px 高，24 条会接近 2600px。要不要给「长图上限」定个值（比如超过 22 条就截断并注明「另有 N 条见网页」）。

---

## 8. 竖版日报（`pic/daily1`）—— 18 套模板配色重排

用户从 174 张横版样图里挑了 18 个喜欢的（001 012 024 054 067 077 078 081 106 107 108 111 112 140 151 159 166 172），
要的是**竖图文本排版**，含「题目 / 今日要点 / 作品消息」三块，不是横版卡片网格。

### 8.1 做法

`juya-news-card-main` 那套组件只能出 1920×1080 卡片网格，改自适应高度等于重写。
所以**只借它的视觉语言，不借它的渲染**：把 18 个模板的配色、字体、招牌装饰抽成 18 组 CSS 变量 + 覆盖样式，
套同一套竖版骨架，用 **HTML + Edge（playwright `channel:'msedge'`）** 截图 —— 文本流由浏览器排，不用手算字宽。

```bash
# 依赖：playwright 装在 vendored 的 juya-news-card-main/node_modules 里，脚本按绝对路径加载
node scripts/daily1/render.mjs 261101              # 全量 18 套
node scripts/daily1/render.mjs 261101 --only=001,024
```

产出 `pic/daily1/NNN-<id>.png`（1080 CSS 宽 × DSF 2 = 2160px，高度随内容 2170–2750px）+ `index.html` 联络表。

### 8.2 竖版骨架（1080 宽，padding 72/64）

| 区块 | 规格 |
|---|---|
| kicker | 13px / 字距 .26em，`声優Xまとめ · 第 <id> 期` |
| 题目 | 72–104px，`--ts` 控制；右侧日期 28px + 星期 12px |
| 双线 | 6px 粗 + 1px 细（`--r1/--r2`） |
| 数据条 | 四格：条动态 / 个账号 / 条要点 / 条作品，30px 数字 + 12px 标签 |
| 导语 | 23px / 1.75（`description`，≤70 字） |
| 01 今日要点 | 序号列 52px + 20px 正文 |
| 02 作品消息 | 序号列 44px + 18.5px 正文，发丝线分隔，20 条 |
| 页脚 | 11px，`发布于 … JST` + 计数 |

18 套的差异只在变量和 `.css` 覆盖里：字体（黑体 / 宋体 / 楷体 / 等宽）、圆角、反白块、硬投影、
双框、印章、网点、木色条。结构不动，所以加第 19 套只需再写一个对象。

### 8.3 坑

1. **`import 'playwright'` 解析的是脚本所在目录**，不是 cwd —— 脚本在 `scripts/daily1/`，包在 `juya-news-card-main/node_modules`，
   必须 `import(pathToFileURL(<abs>/node_modules/playwright/index.js))`，且它是 CJS，要取 `pw.chromium || pw.default.chromium`。
2. **`radial-gradient(circle at 100% 0, …)` 当装饰会糊成一大块灰盘**（159 初版），漫画风改用网点 `repeating` 点阵。
3. **中文孤字换行**：`text-wrap: pretty` 对 `.lead/.hl p/.works p` 有效，不加会出现「伊倉える 生 / 日」这种单字行。
4. **宋体类（STSong）在小字号偏细**，正文别低于 18px；楷体（STKaiti）做漫画风刚好，但只适合短句。
5. **平滑径向渐变会让 PNG 体积翻倍**（106 从 735KB → 1369KB），要压体积就把渐变改平涂。
6. 印章这类装饰用 `.mast-right::after{content:"聲"}` 加，不改进 HTML 模板，18 套共用一份骨架。

### 8.4 组合稿（`pic/daily2`）

用户挑元素重排：**067 作品双栏 + 077 要点卡片 + 001/012/151/077 四种头版 + 木质底 + 全篇偏粗 + 去掉数据条**。

`scripts/daily2/render.mjs` 是独立一套（骨架去掉了 `.stats`，字重阶梯改为 题目 900 / 区块 800 / 要点 600 / 作品 500）。
五稿 = 五种头版：`01 block`（001 色块，胡桃木 `#8d5b33`）、`02 rail`（012 竖轨 + 顶部木色渐变条）、
`03 frame`（151 双框 + Georgia 衬线）、`04 serif-rule`（077 衬线 + 3px 粗线压标题与区块头）、`05 rail-frame`（012 轨 + 151 框）。

- **竖轨别用绝对定位的 `::after`**：`top:0;bottom:0` 相对 padding box，视觉上会探出框线；直接用 `border-left:14px`
  让竖轨成为盒子的一部分，四个角天然对齐（05 初版踩过）。
- 粗线别用 `::after + align-self:flex-end` 去贴基线（在 `align-items:baseline` 的 flex 行里会跑到文字顶），
  改成给 `.sec-head` 一条 `border-bottom:3px` 最稳。
- 木色底 = `repeating-linear-gradient(88deg,…2px)` 细木纹 + 一个左上角暖色 radial，透明度 ≤0.10，再重会脏。

#### 第二轮：题目放大（题目 = 导语段，不是报头）

**术语澄清**：用户说的「题目」是标题下面那句 `description`（「阳向葵ゅか 交代频道被删后的去向…」），
**不是**报头的「声优日报」。报头保持原样：`声优日报` + 右侧日期，只把 `覆盖全天 JST` 删掉，`dow` 只剩星期。

- **报头别改两层**。曾经按「题目=报头标题」理解，把标题改成 `X 日报 · 2026-11-01 声优` 并拆成上下两层，
  被用户打回（「表头不变，表头回退」）。报头永远是「大标题 + 右日期」这一行。
- **页脚整块清空**：`<footer class="foot"></footer>` 只留 40px 内边距，不写「发布于」「条动态」。
- **题目三档**：21px（原大）/ 31.5px（1.5×）/ 42px（2×）。1.5× 与 2× 都会折成两行，21px 本期正好一行。
- **导语断行必须 `word-break:keep-all`**：中文默认逐字断，42px 时会把「伊倉える」劈成「伊 / 倉える」。
  加 `keep-all` 后只在空格处断，人名与作品名不会被拆；再配 `overflow-wrap:anywhere` 兜底防溢出。

#### 第三轮：导语按标点断行 + 全文字号 1.2×

- **导语换行符 = 逗号 / 句号**：`description.replace(/([，。])/g,'$1<br>')`，标点留在上一句行尾（行首不出标点），
  末尾多出来的 `<br>` 要 `replace(/<br>$/,'')` 掉。这样人名、作品名永远不会被劈开，也省掉 `keep-all` 兜底。
  261101 的导语正好两句：`…被删后的去向，` / `…伊倉える 生日`。
- **1.2× 向上取整**（`08 rail-12x`）：标题 84→101、导语 **42→51**（在 07 的 2× 基础上再 ×1.2，不是从 21 起算）、
  要点正文 19.5→24、作品正文 15.5→19。
  字号一放大，原来的区块标题 27px 和要点序号 26px 就被正文追平了，所以同步提到 30px，否则层级塌掉。
- 放大后整张 2678px（比 02 的 2231px 高 20%）；20 条仍是双栏，没有溢出。51px 时导语第二行刚好占满 88% 宽度，
  再长就会折成三行——`overflow-wrap:anywhere` 兜着，不会溢出画布。

---

## 9. 生产化：长图接进发布流程（2026-11-02）

终版 = `08 rail-12x`（012 竖轨 + 木质底 + 067 作品双栏 + 077 要点卡片），页脚留白比对照稿再高 20%
（`padding-bottom` 52→62、`.foot` padding-top 40→48，合计 92→110）。

### 9.1 入口与调用链

```
scripts/daily-image/render.mjs  <期号> --final [--out=<webp>]  # 生产：一张终版长图
scripts/daily-image/render.mjs  <期号>                          # 对照：pic/daily2 的八张
scripts/daily2/render.mjs                                       # 旧入口，只转发到上面（--drafts）
```

`python -m scripts.daily publish --issue <期号>` 写完 `data/daily/<期号>/report.json` 之后自动调
`scripts/daily/image.py` → node → Edge 截图（PNG 缓冲）→ sharp 压 WebP q92 → `public/images/daily/<期号>.webp`。
两版都走同一条路（Galgame 版靠期号里的 `-g` 自己认）。

- `--no-image` 只发 JSON（调试用）。
- 图挂了**不拦发布**：文字版才是正本，缺图在页面上是看得见的。stderr 打 `⚠ 长图没出成` 并给补跑命令。
- `image.py` 找 node 先看 PATH，再看 `C:/Program Files\nodejs\node.exe`——自动化里不继承交互式 PATH。

### 9.2 页面

`DailyLayout.astro` 在「作品动态」之后插 `.daily-figure`，`public/images/daily/<期号>.webp` 存在才渲染
（老期号没有这个文件，不留空框）。宽高用 `sharp(file).metadata()` 读，不写死比例——
WebP 有 VP8/VP8L/VP8X 三种头，自己拆容易踩坑；sharp 本来就是构建期依赖（`npm run images` 在用）。

**`import.meta.url` 拼不出 public 路径**——构建时组件指向虚拟模块，`fs.existsSync` 永远 false，
页面静默少一块。要用 `path.join(process.cwd(), 'public/images/daily', ...)`。

### 9.3 推送与定时任务

`push_site.py` 的 `--path` 现在要三条：`data/daily/`、`data/xreader/`、`public/images/daily/`。
少最后一条，线上页面就没有那张图。定时任务（23:15 那条）已同步改写。

### 9.4 体积

**已改用 WebP q92（`effort: 6`）**：Playwright 只会截 PNG/JPEG，所以先拿 PNG 缓冲再让 sharp 压，
不落中间文件。实测 `261101` 1.6 MB → **640 KB**（−61%）、`261101-g` 1.8 MB → **708 KB**（−61%），
一天两张 ≈ 1.3 MB 进 git，一年约 480 MB。1:1 看字边缘没有色晕和块效应。

代价是多一次 sharp 编码（约 1 秒/张），以及 `render.mjs` 多一个 `import('sharp')`——
从脚本目录往上找到根 `node_modules`，不用装到 `scripts/daily-image/` 下。

备选（都没用）：JPEG q86 约 815 KB（丢透明、色带更明显）、1080 宽 PNG 约 500 KB（清晰度不够）。
木纹那层 `repeating-linear-gradient(…2px)` 是高频噪点，压缩率差的主因。
