# 工作区现状说明（2026-11-08）

> 范围：`Desktop/github page work` 整仓。包括个人主页与笔记、日报双版自动化、周报/月报旁路工作台、以及全部遗留产物。
> 口径：只写**仓库里实际存在的东西**。数字取自 2026-11-08 上午的实测（`ls` / `git status` / 配置统计），不是计划值。
> 读者：下一次接手的自己，或者要判断「这块能不能动」的人。
>
> **同日下午已执行一批清理（2026-11-08）**：§4 的待办按用户逐条裁决处置过，本文部分路径已失效。
> 对账表见 [`weekly-structure-and-p0-review-2026-11-08.html`](weekly-structure-and-p0-review-2026-11-08.html) §6，
> 仍未做的记在 [`../../docs/backlog.md`](../../docs/backlog.md)。主要变化：
> `src/templates/` → `tools/templates/`；`tools/audio-translate/` 已删（源码留 `archive/audio-translate/`）；
> `scripts/daily1`/`daily2`/`out`/`daily_repair_sakuraemi.py` → `archive/scripts/`；
> `og-demo`、`weekly-report-plan` v1–v5 → `archive/reports/`；`out/` 由 1.1 GB 降到 216 MB。

---

## 0. 一句话现状

**个人主页与笔记是稳定的静态站；日报双版是每天自动跑的生产线（24 期存档、641 项测试全绿）；周报/月报是一整套写完但从未入库、也从未正式启用的只读旁路。**

三个数字概括当前的不平衡：

| 维度 | 状态 |
| --- | --- |
| 日报（生产） | 每天 23:15 自动出稿，六出口齐全，闸门齐全 |
| 周报（旁路） | 代码与 641 项测试里的 14 个测试文件**全部未提交**，`FORMALLY_ENABLED=False` |
| 月报（桩） | `scripts/monthly/` 只有一个 `__init__.py` |

---

## 1. 项目整体架构

### 1.1 三条内容线，一条技术底座

这个仓库不是「一个博客」，是**一个静态站 + 两条内容生产管线**。三者共用同一套构建与部署，但生产节奏完全不同。

| 内容线 | 谁产生 | 节奏 | 是否自动 | 入口 |
| --- | --- | --- | --- | --- |
| **个人主页 + 笔记** | 人写 Markdown | 不定期 | 否 | `/`、`/me/`、`/morelinks/`、`/blog/` |
| **日报（双版）** | X-Reader 抓取 + 本地 LLM 整理 | 每天一期 ×2 | 是（23:15） | `/daily/` |
| **周报 / 月报** | 日报正本 + 分句索引 + 人工勾选 | 每周/每月 | **否**（旁路，未启用） | 无页面 |

技术底座只有一层：

- **Astro 7 静态生成 + TypeScript + 原生 CSS + Markdown**，无前端框架、无数据库、无后端、无 CMS、无第三方托管。
- 数据全部是 JSON / JSONL，构建期由 `src/content.config.ts` 的 Zod 校验。
- 部署是 GitHub Pages + GitHub Actions（`deploy.yml`），push 即构建。
- 视觉铁律：黑白灰、圆角 6px、无阴影、中文不斜体；颜色/字号/间距只在 `src/styles/tokens.css` 定义。
- 个人信息只在 `src/config/`；`draft: true` 永不发布。代码 MIT，内容 CC BY-NC-SA 4.0。

### 1.2 构建产物长什么样

`npm run build` 产出 **54 个 HTML**：

```
6  静态页（/ /me/ /morelinks/ /blog/ /daily/ /404）
19 笔记详情（src/content/blog/*.md，example.md 是 draft 不生成）
24 日报详情（data/daily/<期号>/report.json 一期一页）
5  public/docs/ 的维护者指南（随站点发布，不进导航、不进 sitemap）
```

日报另有三个非 HTML 出口（JSON / TXT / JA.TXT）和两个独立 feed，所以实际文件数比 HTML 多。

### 1.3 目录分工

```
.
├── src/
│   ├── config/            ★ 唯一数据源：名单、标签、站点、个人资料
│   ├── content/blog/      笔记正文（Markdown）
│   ├── pages/             路由（14 个路由文件，展开成 54 页）
│   ├── lib/               期号解析、名单查询、Markdown 插件、Ci-en 渲染
│   ├── layouts/           Base / Article / Daily 三套布局
│   ├── components/        16 个组件
│   ├── styles/            tokens / global / typography / components / fonts
│   └── templates/         174 个视觉模板（★ 不参与构建，见 §3）
├── scripts/               ★ 所有生产脚本（根级 29 个 py + 若干子包）
│   ├── daily/             日报包（保护集，M6 前零改动）
│   ├── content/           统一内容层（18 模块 + 3 子包）
│   ├── weekly/            周报包（未启用）
│   ├── monthly/           月报桩（只有 __init__.py）
│   ├── daily-image/       日报长图渲染（Playwright → sharp WebP）
│   └── content.py         内容层门面
├── weekly_studio/         ★ 只读周报工作台（12 模块，未入库）
├── data/
│   ├── daily/<期号>/      日报正本（永久、进 git、站点只读这里）
│   ├── xreader/           抓取库的 14 天按日切片（进 git）
│   ├── period-sources/    周报「选中即固化」来源快照（进 git）
│   └── glossary.json      译名与术语表（68 条）
├── out/                   ★ 全部本地中间产物（gitignored，约 1.1 GB）
├── docs/                  架构与契约文档（6 篇 + architecture/ 7 篇）
├── README/reports/        一次性报告存档（29 份）
├── public/                静态资源 + 5 份维护者 HTML 指南
├── tests/                 38 个 py 测试 + 3 组 node 测试 + golden/
└── schemas/               3 份 JSON Schema（正本的唯一裁判）
```

### 1.4 数据流总图

```
                    ┌──────────── X-Reader 仓库（.xreader/，gitignored）────────────┐
                    │  update.yml        声优版 249 账号  04:05 / 15:05 UTC        │
                    │  update-galgame.yml Galgame 185 账号 04:15 / 15:15 UTC        │
                    │  产出 data/items/x.jsonl（append-only，14 MB / 1.1 万条）     │
                    └───────────────────────────┬──────────────────────────────────┘
                                                │ git pull + xreader_slice.py
                                                ▼
                    data/xreader/{voice,galgame}/YYYY-MM-DD.jsonl（14 天滚存）
                                                │
                                                ▼
   ┌────────────────────── 日报管线（每天 23:15 自动）──────────────────────┐
   │ trigger_fetch → daily_prepare → build → prompt → [LLM] → apply        │
   │ → confirm → [ja] → publish → push_site                                │
   └───────────────────────────┬──────────────────────────────────────────┘
                               ▼
              data/daily/<期号>/report.json（正本，永久）
                    │                          │
        ┌───────────┴──────────┐               └──────────────┐
        ▼                      ▼                              ▼
   六个出口               daily_clauses sync            weekly_studio
   /daily/ 页面           out/clauses/<期号>.json       只读派生
   rss / json / txt       分句 × 出处 × 原文全文        → out/weekly_studio/**
   ja.txt（Ci-en）                                      （不发布、无页面）
```

---

## 2. 抓取自动化技术细节

按用户口径分两个板块：**板块一 = 日报（每天都在跑）**；**板块二 = 非日报（周报/月报旁路）**，第二板块重点写它与日报的联动机制。

---

### 2.1 板块一：日报抓取自动化

#### 2.1.1 三个角色，三段责任

日报是「**CI 抓取 + 本地 LLM 摘要 + 站点 CI 部署**」的混合架构。刻意把「需要 LLM」的那一步留在本机，其余全自动、零成本、无服务器。

| 角色 | 位置 | 负责什么 |
| --- | --- | --- |
| **抓取侧** X-Reader | `.xreader/`（真正的 git clone，gitignored） | 每日抓 X，规范化成 `NormalizedItem`，append 进 `data/items/*.jsonl` 并 commit |
| **本地组装 + LLM** | 本仓 `scripts/` + WorkBuddy | 确定性组装骨架 → 出题 → 模型答题 → 判卷合并 |
| **发布侧** 本站 | `data/daily/` + Astro | 存正本、渲染六个出口、push 后 Actions 自动部署 |

**为什么 CI 里不跑 LLM**：X-Reader 与站点的 Actions 都在 GitHub 免费额度内；一旦把 LLM 放进 CI，就要 API key、要额度、要处理失败重试。现在 LLM 只在出稿那一次手动/半自动跑，摘要质量还能被人审。

#### 2.1.2 涉及的文件夹与文档区域

| 路径 | 角色 | 备注 |
| --- | --- | --- |
| `.xreader/` | 抓取库 checkout | gitignored。桌面那个位置两天被清两次，2026-11-01 搬进仓库目录 |
| `data/xreader/{voice,galgame}/` | 14 天按日切片 | **进 git**。`.xreader/` 丢了也能出稿 |
| `data/daily/<期号>/` | 正本 | **进 git，永久**。站点只读这里 |
| `out/<期号>/` | 工作区 | gitignored。草稿留在这里，构建永远看不到 |
| `out/<期号>.briefing.txt` | 喂模型的事实摘要 | gitignored |
| `out/<期号>.generate.json` | 题库（分类 + 条目 key） | gitignored |
| `schemas/report.schema.json` | 正本的唯一裁判（Python 侧） | 与 Zod 必须同步 |
| `schemas/generation.schema.json` | 模型回答的形状 | 含整期题的 `works` |
| `src/content.config.ts` | `dailyReports` 集合 + Zod | `glob('./data/daily', '*/report.json')` |
| `src/pages/daily/` | 6 个路由文件 | 归档 / 详情 / rss / json / txt / ja.txt |
| `src/lib/daily.ts` | 期号解析、按月分组、纯文本渲染 | |
| `src/lib/roster.ts` | 名单合并查询 | 历史期号是合并名单时代的产物 |
| `src/lib/cien.ts` | Ci-en 记法渲染 | 中文段 + 日文段 |
| `tests/golden/current.json` | 金文件基准指针 | 换基准一条命令 |

#### 2.1.3 工作流与相关文件

**抓取侧两个 workflow**（在 X-Reader 仓库，不在本仓）：

| workflow | 账号 | cron | 输出 | 超时 |
| --- | --- | --- | --- | --- |
| `update.yml` | 249（声优 138 + 社团 111） | `04:05` / `15:05` UTC | `data/items/x.jsonl` | 30 min |
| `update-galgame.yml` | 185（厂商 178 + 信息号 7） | `04:15` / `15:15` UTC（错开 10 分钟） | `data-galgame/items/x.jsonl` | 20 min |

**关键实证：cron 不可信。** 2026-10-26 ~ 10-31 的 12 次定时运行，run 创建时间全部比 cron 晚 **4.2–6.9 小时**，而 job 本身只要 3–19 分钟。`15:05 UTC`（JST 00:05）那轮实际是 JST 04:00–07:00 才落地。所以「当天闭合」只能靠 `workflow_dispatch`：

- `scripts/trigger_fetch.py` 按下后 **7 秒**创建 run，声优版 5 分 51 秒跑完，数据到本地约 **6 分钟**。
- cron 只当「笔记本没开时的保底」。

**本站唯一自动化（23:15 北京时间）**：

```
23:15  触发两版抓取（workflow_dispatch）
23:21  数据落地
       ↓ 等 5 分钟（给 nitter 索引留余量）
23:26  出稿（prepare → build → prompt → answer → apply → confirm → publish）
23:32  上线
       ↓
23:40  抓取退出码非 0 则补抓一次；补抓仍失败就不出残稿
```

**发布侧 workflow**（`deploy.yml`，push 到 main 触发）：

```
astro check → test:md → test:cien → build（含 optimize_images）→ links → check:daily → test → 部署
```

`paths-ignore: data/xreader/**`——只改切片时不重跑 3 分钟的构建。

#### 2.1.4 输出标准化内容的各个模块

`scripts/daily/` 是**保护集**（M6 前零改动），28 个模块按职责分四层：

| 层 | 模块 | 职责 |
| --- | --- | --- |
| **取数** | `window.py` | JST 自然日半开窗口 `[00:00, 次日 00:00)` |
| | `incremental.py` | 增量账本 `data/daily/state.json`，记录哪些条目已用过 |
| | `dedupe.py` | 按 `identity_key` 去重（转发/引用/同文多次抓取） |
| | `order.py` | 名单序 + 互动数排序 |
| | `roster.py` | 按名单分组、`role=main` 当行首、其余进 `via` |
| **成型** | `build.py` | 产出 `report.json` **骨架**（四段全空、`people` 每人一条空 summary） |
| | `model.py` | `NormalizedMessage` / `NormalizedItem` 数据模型 |
| | `schema.py` | JSON Schema 校验封装 |
| | `export.py` | briefing / generate.json 出口 |
| | `image.py` | 长图入口（调 `daily-image/render.mjs`） |
| **出题答题** | `prompt.py` | 出题：每条材料带来源 key（`[x:2113…]`），中文题面写明「只用简体中文叙述」 |
| | `cache.py` | 题面缓存，`PROMPT_VERSION` 现在 3；改题面规则必须 +1 |
| | `apply.py` | 判卷 + 合并：来源不存在 / handle 不在名单 / 长度超限 → **整份拒收**并指出哪一句 |
| | `validate.py` | 结构校验 |
| **定稿发布** | `audit.py` | 事后判卷：来源 key 是否真实、handle 是否名单内且本期有条目、长度 |
| | `confirm.py` | 定稿前再判一次，`status → confirmed` |
| | `publish.py` | 只认 `confirmed`，搬到 `data/daily/` |
| | `ja.py` | Ci-en 版：出题 + 判卷，产出 `report.ja.json` |
| | `issue.py` / `paths.py` / `version.py` | 期号规则、路径、版本 |
| | `migrate.py` | 旧格式迁移 |
| | `cli.py` / `__main__.py` | 命令入口 |

**根级脚本（编排层）**：

| 脚本 | 作用 |
| --- | --- |
| `daily_prepare.py` | ★ 自动化入口：pull → 数条数（0 条退 2 / 只到一半退 5）→ 调 build |
| `daily_digest.py` | ★ 规范唯一的组装脚本（`build` / `prompt` / `apply` / … 的兼容门面） |
| `xreader_slice.py` | 全量库 → 14 天按日切片 |
| `trigger_fetch.py` | `workflow_dispatch` 立刻抓 + 等完成 + pull + 验覆盖 |
| `daily_condense.py` | briefing 压缩成编辑视图（5.2 万 → 1.5 万 token） |
| `daily_golden.py` | 金文件：抓 `.prose` 纯文本逐字比对，`--switch` 换基准 |
| `check_daily_site.py` | 出口闸门：三产物齐全、JSON 与正本逐字节相同、两个 feed 不混 |
| `push_site.py` | 提交推送（GCM 取 token → 临时 askpass → 推完即删）。**必带 `--path`** |
| `sync_xreader_accounts.py` | 名单 → `accounts*.yaml`（两版分开写，只收 `active != false`） |
| `daily.sh` | 一键流程包装（组装 → 提示填摘要 → 打印 git 命令） |

#### 2.1.5 期号、两版与六个出口

**期号 = 被覆盖的那一天 + 哪一版，也是网址。** 格式 `YYMMDD`，JST。

| 期号 | 意思 |
| --- | --- |
| `261107` | 声优版第 1 期（不带后缀的永远是声优版） |
| `261107-g` | Galgame 版第 1 期 |
| `261107-2` / `261107-g2` | 同日第 2 期 |
| `261107-1` / `261107-g1` | **非法** |

期号不带小时：旧格式 `YYMMDDHH` 固定写 22:00，那是「名义发布时间」；真实出稿落在次日凌晨 01:2x，与「覆盖 00:00–24:00」自相矛盾。现在期号只说「哪一天、哪一版」，真实时刻交给 `issue.published_at`。

**六个出口**：

| 路由 | 是什么 |
| --- | --- |
| `/daily/` | 归档列表，按月分组 |
| `/daily/<期号>/` | 单期详情（`getStaticPaths`，无手写路由） |
| `/daily/rss.xml` | **独立**归档 feed（混进主 feed 会改变既有订阅者收到的东西） |
| `/daily/<期号>.json` | 与正本**逐字节相同** |
| `/daily/<期号>.txt` | 纯文本（复制粘贴 / M6 视频稿） |
| `/daily/<期号>.ja.txt` | Ci-en 版，中日双语，**只有声优版有** |

后三个由 `npm run check:daily` 守着：有一份 `report.json` 就必须有三份产物，JSON 与正本逐字节相同；有 `.ja.txt` 就必须有 `report.ja.json`。链接检查看不见这些文件——没有别处引用它们。

#### 2.1.6 名单：两份，按版分工

| | 声优版 `daily-roster.json` | Galgame 版 `daily-roster-galgame.json` |
| --- | --- | --- |
| 条数 | **250**（seiyuu 138 / circle 111 / other 1） | **186**（manufacturer 178 / info 7 / other 1） |
| 抓取账号 | 249（1 条 `active:false`） | 185 |
| Ci-en 出口 | 有 | 无 |

三条身份铁律：

1. **一个 handle 一条**。既是厂商又是社团（`@cube_staff`）、或本来就是某位声优主号（`@ayakaigasaki`），只保留已有那条，另一重身份写 `note`。
2. **广告号/官方号绝不能借同名挂进声优捆绑**。`girlscreationpr` 是 PR 号，2026-11-06 起 `category=other / active=false` + `note` 隔离。回归 `tests/test_roster_identity.py`。
3. **进哪版看写在哪份文件**。`belongs_to_kind()` 拦跨版。

降噪在名单的 `filter` 段，顺序固定：`drop_kinds → drop_if → keep_if`（白名单，仅媒体号）`→ prefer_if`（只排序）`→ max_items`。

---

### 2.2 板块二：非日报（周报 / 月报旁路）—— 以及它与日报的联动

#### 2.2.1 为什么是「旁路」

日报是保护集：`data/daily/**`、`scripts/daily/**`、日报 schema、`content.config.ts`、两条 workflow、23:15 自动化、`tests/golden/**` 在 M6 前**逐字节零改动**。

周报需要日报的产出，但**不能碰日报**。于是设计成只读旁路：

```
只读  data/daily/**  +  out/clauses/**  +  out/weekly-material/**
  ↓
只写  out/weekly_studio/**（gitignored）
  ↓
不发布、无页面、无调度、无 data/weekly/
```

`FORMALLY_ENABLED = False`。`publish` 子命令存在但一律拒绝（退 3），`-m` 被 M7 守卫拒。

#### 2.2.2 与日报联动的三个技术接点

这是本板块最需要讲清楚的部分：**周报不是重新解析 `x.jsonl`，而是站在日报的成果上。**

**接点一：只读证明（`daily_manifest.json`）**

工作台每次构建都算一遍 `data/daily/**` 全部文件的 **sha256**，落成 manifest。前后对比即可证明「日报一个字节都没被改」。这不是口头承诺，是可校验的证据。

**接点二：分句级出处索引（`out/clauses/<期号>.json`）**

日报「详细」栏每行本来就有 `sources: ["x:<id>"]`，但过去周报从不读它。这一层把「详细」按项目标点切成**带尾标点的分句**，给每句挂上已解析的原推链接，并把该行全部来源推文的完整原文留在本地索引里。

```
① 只读源   data/daily/<期号>/report.json     正本，永久，一字不改
           data/xreader/*/*.jsonl            40 天滚存切片，带转发关系
           out/*.generate.json               本机底稿
                │ 只读
                ▼
② 临时索引 out/clauses/<期号>.json           gitignored、懒生成、可删可重建
           分句 × 出处 × 原文全文
                │ 人工 / AI 勾选、改写
                ▼
③ 来源台账 data/period-sources/              进 git、永久、只存链接与元数据
```

关键设计：**懒生成**。`sync` 靠 `summary_fingerprint` 判断要不要重建，所以**完全不需要改 23:15 自动化**——日报每天照常出稿，索引在周报取料时补建即可。这是「不改保护集」的技术兑现方式。

精度口径（Q2 裁决）：`row` 算达标。索引里每句都标 `precision: clause | row | unresolved` 和 `exact_source`，**不猜**。`span_facts` 在索引阶段留空，M3 才按 `source_refs.text` 拆。

**接点三：素材包与「选中即固化」（M3）**

```
out/weekly-material/<pack_id>/
    window.json           窗口、两版分流、合并后的 source_refs
    daily_summaries.json  各天要点：description + highlights + works + interactions
    clauses.json          全量「人-分句」候选，带 dedupe_key / 归并组 / span_facts
    selection.md          人工勾选清单（改 [ ]→[x]，在「改写：」后写周报成稿）
    selected.json         勾选与改写的规范化结果
data/period-sources/<pack_id>.json   选中的原推链接快照，进 git、永久可追
```

命令链：`build → （人工编辑 selection.md）→ select → freeze → check`。

#### 2.2.3 `weekly_studio/`：只读工作台（12 模块）

这是 2026-11-06 夜起的**第二套**周报实现。与 `scripts/weekly/`（M1–M5 正式包）同名但职责不同，两套别混。

| 模块 | 职责 |
| --- | --- |
| `core.py` | 窗口、路径、只读边界 |
| `adapter.py` | 从日报正本 + 分句索引装配语料 |
| `catalog.py` | ★ 作品情报目录：按游戏折叠、按品牌归栏、梯队排序（106 KB，最大） |
| `full_preview.py` | 全量抓取库 → 周报预期输出（底板只做 Galgame） |
| `source_filter.py` | ★ §19 信息号整条剔除（第一道闸门） |
| `vndb_backtest.py` | §17 VNDB 回测：只回测「未标注品牌」作品小单元 |
| `editor.py` | 选材库 = 交互式工作台（每小单元一个「源」按钮，懒构建） |
| `render.py` | 初稿渲染（不写出处键/账号/链接） |
| `precision.py` | M2 精确度报告（开发工具，会打印 `@author`） |
| `cli.py` | `week / build / daily / draft / check / apply-decisions / preview / vndb` |
| `brand_rules.json` | 全部词表：梯队、别名、归栏、主语规则 |

**栏目结构（固定三栏）**：`作品情报 → 品牌/账号动向 → 看点`。

分流规则（确定性，不猜）：

```
检出作品名 → 作品情报
未检出作品 → 品牌动向
检出作品但命中 movement_rules（账号开设/开通）→ 品牌动向
people/interactions 既没作品也没命中 signals → 不发布，只计数
厂商作品消息 → 分类判定保留，但归栏并回品牌动向（move:<品牌>）
```

**两条不做的事**（都是实测得出的）：

1. **绝不做字符二元组模糊对齐**。实测可信度 38.1%。真实对齐率 voice 54.1% / galgame 60.3%，**不得为凑 80% 伪造**。
2. **`clause` 不升级进作品栏**。切开读不通，只作选材候选。

**§19 信息号整条剔除**（最新一道闸门）：`category/role=info` 的 handle → 来源键（URL / author / retweeted_by / publisher / quoted_author）**整键剔除** → 只靠这些键支撑的 claim / 候选分句 / `works[]` 整行一并剔除。`works[]` 另有两道逐字闸门：与已剔除分句整行字面包含，或以信息号 handle/显示名开头。证据落 `source_filter.json`，`check` 用 `residual_handles` 复核。

实测（261101-w-g）：7 个信息号 → 剔除来源键 66、claim 43、分句 74、整行 36（含以账号名开头 8）、`works` 9。

#### 2.2.4 两套 M1–M5，别混

| | A 套：`scripts/content/` + `scripts/weekly/` | B 套：`weekly_studio/` |
| --- | --- | --- |
| 文档 | `docs/architecture/weekly-m1-m5-delivery.md` | `docs/clause-source-index.md` §10 起 |
| 定位 | 统一内容层 + 周报正式包（M1–M5） | 只读工作台（旁路） |
| 规模 | `content/` 18 模块 + 3 子包；`weekly/` 12 模块 | 12 模块 |
| 状态 | `FORMALLY_ENABLED=False`，`publish` 退 3 | 无自动化、无页面、不 publish |
| 入口 | `python scripts/weekly.py prepare/draft/preview/finalize` | `python -m weekly_studio week/build/...` |

两套都算「做完了」，但都没启用。区别是 A 套有 `data/weekly/` 的设计但没写，B 套连设计都不碰。

#### 2.2.5 月报

`scripts/monthly/` **只有一个 `__init__.py`**。这是 M7 的边界桩，不是实现。

设计上的口径已经定了：`monthly_window`（`FIRST_MONTHLY_WINDOW_START=2026-10-26`，月报日 = 最后周五 + 2 天 00:30 JST），`WEEKLY_ID_RE` 与日报 `ID_RE` 独立。但代码没写。

#### 2.2.6 闸门矩阵

| 命令 | 管什么 | 当前 |
| --- | --- | --- |
| `python -m unittest discover -s tests` | 全部 Python 回归 | **641 tests OK (skipped=11)** |
| `node --test tests/cien/cien.test.mjs` | Ci-en 记法 | 17/17 |
| `node --test tests/markdown/*.test.mjs` | Markdown 插件 | 通过 |
| `python scripts/daily_clauses.py check --all` | 24 期分句索引指纹 / 无损 / 出处一致 | 全绿 |
| `npm run check:daily` | 六出口齐全 + 逐字节 + 金文件 | 通过 |
| `npm run check:weekly` | 周报站点出口（页面还没建，目前空转） | 通过 |
| `npm run links` | 站内死链（对产物跑，不联网） | 通过 |
| `npm run check:prose` | 排版（落单加粗等） | 通过 |
| `npm run check` | Astro / TS 类型 | 0 error |
| `weekly_studio check 261101-w --kind galgame` | 只读边界 + 信源区隔 + 残留链接 | 通过 |

**一条重要实证**：468 条测试全绿 ≠ 内容合格。D3 审计证明生命周期事件的 14 项发现里 11 项靠加关键词解决不了。测试覆盖的是语法与管线，不覆盖内容正确性。

---

## 3. 遗留产物与无用产物

先给结论：**`out/` 约 1.1 GB 全是可删的中间产物；真正的风险不是垃圾多，而是 58 项未提交的代码——整套周报子系统从未入库。**

### 3.1 `out/` 里的体积大头（全部 gitignored，可删）

| 路径 | 体积 | 原用途 | 现状 / 建议 |
| --- | --- | --- | --- |
| `out/_tmp/` | **929 MB** | 89 个临时文件：抓取日志、HTML 样张、一次性 py（`add_notes.py`、`bugbug_dl.py`…）、astrocheck 日志 | 纯垃圾。留 3–5 个还在用的，其余可删 |
| `out/_dryrun_real/` | 81 MB | 周报真实库 dry-run（12,757 → 674 事件 / 519 作品） | 验收证据。归档一次后可删 |
| `out/_trial/` | 48 MB | Galgame 单库试水（1,619 → 255 事件 / 20 成稿） | 卡点 D 的人工看稿对象，**先别删** |
| `out/dist-old/` | 38 MB | 旧 `dist` 备份 | 可删，`dist/` 随时可重建 |
| `out/_voice-weekly-backup-20261107/` | 14 MB | 声优版周报改版前的备份 | 改版已验收，可删 |
| `out/weekly_studio/` | 11 MB | 工作台实际产物（`preview/base/`、`vndb/`） | 当前工作对象，保留 |
| `out/clauses/` | 4.1 MB | 24 期分句索引 | **可删可重建**，但重建要跑一遍 |
| `out/weekly-material/` | 933 KB | M3 素材包 | 保留 |
| `out/2610xx/` 各期 | 0.4–0.9 MB | 各期工作区（草稿 + 答案 + 判卷） | 已发布的期可归档 |
| `out/_audit/` | 小 | `lifecycle_audit.py`（D3 审计脚本） | 归档到 `docs/` 或 `scripts/` |
| `out/_smoke/`、`out/_smoke_setup.py` | 小 | 冒烟测试 | 可删 |
| `out/xreader-check/` | 小 | 抓取覆盖核对 | 可删 |
| `out/*.log` | 小 | `build.log` / `preview.log` / `full-regression.log` | 可删 |

### 3.2 脚本层的遗留目录

| 路径 | 原用途 | 现状 / 建议 |
| --- | --- | --- |
| `scripts/daily1/render.mjs`（43 KB） | 长图第 1 轮实验（2026-11-02） | **正式版是 `scripts/daily-image/render.mjs`**。这两个是死代码，可删或移到 `docs/` 存档 |
| `scripts/daily2/render.mjs`（249 B） | 第 2 轮实验（几乎空的壳） | 同上 |
| `scripts/out/` | `daily_digest.py` 早期的默认输出目录，存 `26101822`–`26102222` 六期的 briefing / md / generate | 旧期号格式（带小时）的产物。可删 |
| `scripts/monthly/` | 月报包 | 只有 `__init__.py`。**是桩不是实现**，别误以为月报做了一半 |
| `scripts/daily_repair_sakuraemi.py` | 佐倉江美账号的一次性订正脚本 | 已执行完。可删或移入 `scripts/oneoff/` |
| `scripts/build_rt_compare.py`、`build_manufacturer_roster.py`、`build_roster_overview.py` | 生成 `README/reports/` 里的名单总表 HTML | 名单变了要重跑，**保留** |
| `scripts/daily_condense.py` | briefing 压缩（5.2 万 → 1.5 万 token） | 现走「出题」路线后用途变窄，但文件地图里仍在。保留观察 |
| `scripts/pic_index.mjs` | 长图模板样张索引（174 个模板） | 一次性，保留但不常用 |

### 3.3 根目录的整块外部产物

| 路径 | 体积 | 原用途 | 现状 / 建议 |
| --- | --- | --- | --- |
| `tools/audio-translate/` | **7.8 GB** | 本机 ASR + 翻译工具（`asr.py` / `mt.py` / `pipeline.py` / `slice_audio.py`） | gitignored。**完全独立于站点**，不属于这个项目。建议搬出去 |
| `juya-news-card-main/` | 37 MB（含 node_modules） | 上游 Next.js 模板库 checkout | gitignored。只抄了视觉语言，成品是 `scripts/daily-image/render.mjs`。可删 |
| `src/templates/` | 174 个 `.tsx` + `catalog.ts` + `meta.json` + `runtime-resolver.ts` | 从 juya 移植的视觉模板库，用来跑样张挑样式（对应 gitignored 的 `pic/`） | **不参与构建**（Astro 没装 React 集成，也没有任何页面引用）。要么正式收编，要么移出 `src/`——放在 `src/` 里最容易让人以为它是站点的一部分 |
| `ASR project/` | 4 个 HTML + `j.md` / `jn.md`（两份 8585 B 内容相同） | ASR 方案与站点集成规划（2026-10-21） | 未入库、未纳入站点。方案性文档，建议并入 `README/reports/` 或直接归档 |

### 3.4 文档层的遗留

| 路径 | 原用途 | 现状 / 建议 |
| --- | --- | --- |
| `README/reports/weekly-report-plan-2026-11.html` + `v2`–`v6` | 周报方案 6 轮迭代 | **v6 是最终口径**，v1–v5 是过程稿。建议只留 v6，其余归档 |
| `README/reports/` 其余 23 份 | 一次性报告：名单总表、ASR 选型、token 成本、M5/M6 选型、github 仓库扫描、分类模块提案… | 按约定都该放这里。多数是历史证据，不必删，但可加一份索引 |
| `README/reports/og-demo/` | OG / 晨报长图试验：`morning-paper.mjs`、`render.mjs`、两张样张、Noto 字体 | 长图已定稿到 `scripts/daily-image/render.mjs`，这里是试验残留。可删 |
| `docs/daily-build-log.md` | M1 起的构建日志，一个工作包一条，只记实际输出 | **历史日志，到 261029 附近**。保留，但别当现状读 |
| `docs/daily-scaling-plan.md` | 2026-10-25 的名单扩容方案（几十人 → 上百人） | 名单扩容**已落地**（250 / 186），文中「分类视图」部分未做。可标注「部分完成」 |
| `docs/daily-image-method.md` | 长图操作手册 | 有效，`rail-12x` 定稿口径在这里 |
| `docs/project-status` 系列（`public/docs/project-status.html`、`README/reports/project-status-2026-11-05.md`） | 项目完成度快照 | **数字已过时**（当时 432 条名单、468 测试）。以本文为准 |
| `src/content/blog/example.md` | 草稿示例，`draft: true` | 不发布。README 说可删，但它是 `draft` 机制的唯一活样例，建议留着 |
| `tests/daily-protection-waivers.json` | 日报保护集的显式授权白名单 | 2026-11-06 那批改动**已 commit**，按设计「diff 归零、豁免自动失效」→ **该把登记项删掉**。留着会让下一次改动误以为有授权 |

### 3.5 最大的遗留：58 项未提交改动

`git status` 显示 **58 项**未入库。其中绝大部分不是「忘了提交」，是**有意留在工作区**（避免把未启用的周报混进站点仓），但风险很高：

| 未入库内容 | 风险 |
| --- | --- |
| `weekly_studio/`（12 模块） | 整套只读工作台只存在于本机 |
| `scripts/weekly/`（12 模块）+ `scripts/content/`（18 模块 + 3 子包）+ `scripts/content.py` | M1–M5 正式包从未入库 |
| `docs/architecture/`（7 份）+ `docs/clause-source-index.md`（71 KB）+ `docs/weekly-report.md`（57 KB） | 全部契约与设计只在本地 |
| **14 个测试文件**（`test_weekly_*.py`、`test_daily_protection.py`、`test_roster_identity.py`、`test_daily_clauses.py`…） | 641 项测试里有相当一部分跑的是未入库代码 |
| `data/period-sources/` | 周报来源台账 |
| `src/templates/`（174 个 tsx） | 视觉模板库 |
| `ASR project/`、`README/reports/` 新增的 9 份 | 方案文档 |

**这意味着：换一台机器 clone 下来，`npm test` 会失败（测试文件在、被测代码不在），周报整套消失。**

另外 5 项是**已跟踪文件的修改**：`package.json`、`scripts/xreader_slice.py`、`src/config/daily-roster-galgame.json`、`tests/test_daily_incremental.py`、`README/reports/daily-m5-m6-options.html`。

---

## 4. 接下来的待办

按「不做会疼 / 做了才不疼 / 需要你拍板」分三档。

### 4.1 P0：不做会疼

| # | 事项 | 为什么现在做 | 具体动作 |
| --- | --- | --- | --- |
| 1 | **把周报子系统入库** | 58 项未提交 = 换机即失。这是当前唯一的单点故障 | 分批提交：① `docs/` + 测试（纯文档/纯测试，零风险）② `scripts/content/` + `scripts/weekly/` ③ `weekly_studio/` ④ `src/templates/` 单独裁决。用 `push_site.py --path` 逐批带 |
| 2 | **人工看稿（卡点 D）** | 阻塞所有 M6/M7 与生命周期实施。**不需要写代码，只需要看** | 打开 `out/_trial/261101-w/preview.html` + `out/weekly_studio/preview/base/`，确认：黑名单是否误伤真作品、A 档偏斜（167 A / 21 B / 0 C）能否接受、全 L0 是否可接受。**不要碰 finalize/publish，不要手改 report.json** |
| 3 | **裁决 B1–B4 + C1–C4** | 生命周期重构的前置。14 项发现里 11 项靠加关键词解决不了 | 建议顺序：先 B3/B4（低风险，保住「一行作品 + events[]」的 20/22 上限）→ B2（作品性五级优先级）→ B1/C1（保守处理）→ C2–C4 随设计落地 |
| 4 | **清理 `tests/daily-protection-waivers.json`** | 那批改动已 commit，豁免按设计失效。留着是误导 | 删掉已 commit 的登记项，只留仍生效的 |

### 4.2 P1：做了才不疼

| # | 事项 | 说明 |
| --- | --- | --- |
| 5 | `works[]` 补 `sources` | 后台 436 条 `works` 全无来源。这是「可回溯」链条上唯一的洞 |
| 6 | 栏目事实层缺口 | 价格 / 版本分档 / 周边通贩 / 汉化——现在抽不出来，只能靠人写 |
| 7 | §13.6 背景段三级降级 + 事件级跨期聚合 | 契约已写，代码未落 |
| 8 | 清 `out/` | `_tmp` 929 MB + `dist-old` 38 MB + `_dryrun_real` 81 MB + `_voice-weekly-backup` 14 MB ≈ **1.06 GB**。清之前确认 `_trial/` 留着（看稿用） |
| 9 | 归档实验脚本 | `scripts/daily1/`、`scripts/daily2/`、`scripts/out/`、`scripts/daily_repair_sakuraemi.py`。**删之前 grep 一次引用** |
| 10 | `src/templates/` 定性 | 174 个 tsx 不进构建却放在 `src/`。要么正式收编（装 React 集成、接进长图），要么移到 `tools/` 或删除 |
| 11 | `tools/audio-translate/` 搬出去 | 7.8 GB，与站点无关，放在工作区里只会让备份变慢 |
| 12 | 报告索引 | `README/reports/` 29 份没有索引，找东西靠文件名猜。加一份 `README/reports/INDEX.md` |
| 13 | 旧方案归档 | `weekly-report-plan` v1–v5、`og-demo/`、`ASR project/` 归到一个 `archive/` 子目录 |

### 4.3 P2：需要你拍板才能动

| # | 事项 | 卡在哪 |
| --- | --- | --- |
| 14 | **M6（日报接入周报）** | 要明确日报保护集的改动范围。目前 §10.1 是逐字节零改动，M6 不解这条，周报永远只能读派生 |
| 15 | **M7（月报 + 页面 + 调度）** | 要单独授权。`scripts/monthly/` 还是空桩；`FORMALLY_ENABLED` 要翻 True；要排期（Q2 抓取任务位置、Q4 数据新鲜度检查仍是假设，M1–M5 未读未动） |
| 16 | 生命周期重构落地 | 等 B1–B4 裁决。爆炸半径已 grep：`event_type` 只在 `models.py` 2 处 |
| 17 | 账号订正残留 | 12 行文案 / 15 条来源仍指向广告号原推。清内容需另做编辑裁决 |
| 18 | 存量账号口径 | 厂商侧个人号 14 + 个人向信息号 4 先存着（`max_items:1` + role）。要不要清 |
| 19 | Moepedia `drop_if` 的「周年」 | 与两媒体号口径相反，待定 |
| 20 | 术语表 51 → 60 条 | 目标 60–80，现 68 条（含新增）。补哪些由你定 |
| 21 | OG 带字版（satori） | CJK 字体是成本，值不值 |

### 4.4 每天实际要跑的（不是待办，是日常）

```bash
# 正常情况下 23:15 自动化已经跑完，人只需要看稿
python scripts/daily_prepare.py --kind voice      # 若自动化失败，手动补
python scripts/daily_prepare.py --kind galgame
# 出题 → 填 out/<期号>/answer/all.json → 判卷合并
python scripts/daily_digest.py prompt --issue <期号> --flat
python scripts/daily_digest.py apply --issue <期号> --answer out/<期号>/answer/all.json
python scripts/daily_digest.py confirm --issue <期号>
python scripts/daily_digest.py ja --issue <期号>        # 声优版才要
python scripts/daily_digest.py publish --issue <期号>
python scripts/push_site.py --path data/daily/ --path data/xreader/
```

环境两条：`export PATH="/c/Program Files/nodejs:$PATH"`；网络走 `https_proxy=http://127.0.0.1:7897`。

---

## 5. 一句话收尾

**站点这一层已经没什么可做的了；日报这一层稳定但内容深度不够；周报这一层代码写完、测试全绿、但一行都没入库也没启用。**

下一步最划算的动作不是加功能，是两件不写代码的事：**把周报入库（防丢）**，和**把 20 张成稿看完（解卡点）**。

---

*本文所有数字取自 2026-11-08 上午实测。若与 `public/docs/project-status.html`、`README/reports/project-status-2026-11-05.md` 冲突，以本文为准——那两份是 11-05 的快照，名单数、测试数都已过时。*
