# X 每日推特日报 — 日常运营指南与维护指南

> 适用项目：EpsilonGG 个人站（`github.com/EpsilonGG/epsilongg.github.io`，本机路径 `Desktop\github page work`）
> 配套工具：X-Reader（抓取+规范化）。X-rss 仓库的"储存地"= `X-rss-workspace`。
> 最后更新：2026-10-24

---

## 0. 项目概览（混合架构，先读这段）

日报采用 **「CI 抓取 + 本地 LLM 摘要 + 站点 CI 部署」** 的混合方案，把"需要 LLM"的那一步留在你本机的 WorkBuddy，其余全自动、免费、不需要服务器。

涉及三个角色：

| 角色 | 位置 | 负责什么 |
| --- | --- | --- |
| **X-Reader（抓取侧）** | GitHub 上的 X-Reader 仓库；本机 checkout 在 `X-rss-workspace/X-Reader` | 每日自动抓取 X 推文，规范化为 `NormalizedItem`，写入并提交 `data/items/*.jsonl` |
| **本地组装 + 本地 LLM** | 站点仓库 `scripts/daily_digest.py` + `scripts/daily.sh`，外加本机 WorkBuddy | 把 `data/items` 确定性组装成 `src/content/daily/<date>.md`；由 WorkBuddy 填写 `<!--AI_SUMMARY-->` |
| **站点仓库（发布侧）** | `Desktop\github page work` = `epsilongg.github.io` | 存放脚本与产出 `.md`；`git push` 后 Actions 自动构建部署到 GitHub Pages |

**数据流（每天一次）：**

```
X-Reader CI (每日 17:10 UTC)
   └─ fetch → 写 data/items/x.jsonl → git commit/push 进 X-Reader 仓库
        │
   本地：git pull X-Reader 仓库（拿到最新 data/items）
        │
   本地：python scripts/daily_digest.py --items-dir <X-Reader>/data/items
        └─ 产出 src/content/daily/<date>.md（含 <!--AI_SUMMARY--> 占位）
        │
   本地 WorkBuddy：读取 briefing / .md，写中文摘要，替换 <!--AI_SUMMARY-->
        │
   本地：git add src/content/daily/<date>.md && commit && push
        │
   站点 Actions (deploy.yml)：astro check → test:md → build → links → test → 部署
```

**为什么这么设计：** X-Reader 与站点的 Actions 都在 GitHub 免费额度内；CI 里**不跑 LLM**、不需要 API key、不需要 VPS。只有"写摘要"这一步在你本机 WorkBuddy 完成一次，零额外成本。

> ⚠️ **Sotwe 作为补充 X 源：** 已做过可行性评估，结论为**不可行**（时间线为 JS 渲染，`selectolax` 无法提取；无公开 API；无头浏览器违反项目约束）。按规范已 STOP，未改动任何代码。扩充来源请优先在 X-Reader 内加 provider/route。

---

## 一、日常运营指南（每天生成日报）

每天（早晨或你方便的时间）生成前一天/当天的推特日报，只需 4 步。

### 步骤 0 — 确认/获取当天数据

digest 读取的目录是 **X-Reader checkout 的 `data/items`**。两种方式拿到数据：

- **方式 A（推荐，用 CI 已抓的数据）：** 在 `X-rss-workspace/X-Reader` 里执行 `git pull`，拉取 CI 提交的 `data/items/`。
- **方式 B（本地现抓）：** 在 `X-rss-workspace/X-Reader` 里执行 `python main.py --json`（需要该仓库的依赖与凭证）。

> CI 每天 **17:10 UTC**（≈ 北京时间次日 01:10）跑一次。digest 默认取数据里"最新的一天"，所以你随时跑都能拿到最近一个完整日。

### 步骤 1 — 组装日报草稿（确定性、无 LLM）

```bash
cd "Desktop/github page work"
python scripts/daily_digest.py --items-dir "<X-rss-workspace>/X-Reader/data/items"
```

- `--date YYYY-MM-DD`：可选，指定报告日期（默认取数据里最新一天）。
- 产出：
  - `src/content/daily/<date>.md` —— 站点内容（frontmatter + `<!--AI_SUMMARY-->` 占位 + 按账号分组的推文列表）。
  - `out/<date>.briefing.txt` —— 喂给 LLM 的事实摘要（已被 `.gitignore` 忽略，属本地中间产物）。
- **空跑预览（无真实数据）：** 直接 `./scripts/daily.sh 2026-10-24`，会用仓库内的 `scripts/sample_items/` 样例数据生成一份预览，方便测试流程。

### 步骤 2 — 让本地 WorkBuddy 填写 AI 摘要（唯一需要 LLM 的地方）

对 WorkBuddy 说：**"填写今天的日报 AI 摘要"**。它会：

1. 读取 `out/<date>.briefing.txt`（或 `src/content/daily/<date>.md` 里的分组列表）；
2. 用中文写出当日要点摘要（谁发了什么、重点、值得关注的数据）；
3. 把 `src/content/daily/<date>.md` 中的 `<!--AI_SUMMARY-->` 替换为该摘要。

> 这一步就是"用 WorkBuddy 本地跑完需要 LLM 的部分"。LLM 不碰 API、不进 CI。

### 步骤 3 — 提交并推送站点仓库

```bash
git add src/content/daily/<date>.md
git commit -m "daily: <date>"
git push
```

推送后 `deploy.yml` 会自动构建并部署到 GitHub Pages，**无需手动构建**。

### 步骤 4（可选）— 在站点核对

部署完成后访问：
- 列表页：`/daily/`
- 详情页：`/daily/<date>/`
确认摘要渲染、推文链接、互动数正常。

### 日常常见问题

| 情况 | 处理 |
| --- | --- |
| 某天没有新推文 | digest 仍会生成当天 `.md`，但分组可能为空；可跳过当天，或手写一篇简短摘要 |
| 数据还没抓到 | 先 `git pull` X-Reader 仓库，或等 CI（17:10 UTC）跑完再操作 |
| 想补过去的某天 | 用 `--date YYYY-MM-DD`；digest 会筛那一天的记录（数据 append-only 会保留历史） |
| 想换 Python 解释器 | `daily.sh` 顶部 `PY="${PYTHON:-python3}"`，可改为本机 Python 路径；或直接用 `PY=... bash scripts/daily.sh` |

---

## 二、维护指南（改东西 / 出问题时看这里）

### 2.1 文件地图（站点仓库 `github page work`）

| 文件 | 作用 |
| --- | --- |
| `scripts/daily_digest.py` | ★ **规范、唯一的组装脚本**（无 LLM 的一半）。**不要再改 `X-rss-workspace/daily-report/digest.py`**，那是被取代的旧原型 |
| `scripts/daily.sh` | 一键流程包装：组装 → 提示用 WorkBuddy 填摘要 → 打印 git 命令 |
| `scripts/rss_to_items.py` | 把 X-rss-main 的**真实** RSS feeds（`output/feeds_processed/*.xml`）转成 NormalizedItem JSONL（账号/原文链接/内容均为真实；该 RSS 源不含媒体与互动数） |
| `scripts/sample_items/x.jsonl` | 预览/测试数据。现由 `rss_to_items.py` 从 X-rss-main 真实 feeds 生成（**真实推文**，非编造） |
| `src/content.config.ts` | `daily` 内容集合的 Zod schema |
| `src/lib/daily.ts` | `getDailyReports()`、`dailyPath()` 等取数函数 |
| `src/layouts/DailyLayout.astro` | 日报详情页布局（复用 `BaseLayout`，含"AI 整理"徽章、上/下篇导航） |
| `src/pages/daily/index.astro` | `/daily/` 列表页 |
| `src/pages/daily/[...date].astro` | `/daily/<date>/` 详情页（`getStaticPaths`） |
| `src/config/navigation.json` | 顶部导航的"日报"入口 |
| `src/content/daily/<date>.md` | **产出**：每天的日报内容 |

### 2.2 X-Reader 端（抓取侧）

- **仓库：** `X-rss-workspace/X-Reader`（对应 GitHub 上的 X-Reader 仓库）。
- **CI：** `X-Reader/.github/workflows/update.yml`，每日 `17:10 UTC` 跑；`python main.py` 后 `git add data && commit && push`（只提交 `data/`）。
- **数据：** 规范存储是 `data/items/<source_id>.jsonl`（`NormalizedItem`，**append-only**）。X 数据 `source_id` 为 `x`，落在 `data/items/x.jsonl`。
- **加/减监控账号：** 改 `X-Reader/accounts.yaml`（不是站点仓库）。digest 的 `accounts` frontmatter 是根据数据**自动推导**的，无需手改。
- **加 RSS / YouTube 源：** 改 `X-Reader/config/config.yaml`。⚠️ 注意：digest 当前读取 `items/` 目录下**所有** `*.jsonl`；若以后引入非 X 源，日报会混入它们。要么只传 `data/items/x*.jsonl`，要么给 digest 加 `--source x` 过滤（见 §2.6）。

### 2.3 日报 frontmatter schema（`src/content.config.ts` 的 `daily` 集合）

```ts
{
  title: string;                 // 必填
  description?: string;          // 可选
  pubDate: Date;                 // 必填（Zod coerce）
  source: 'original' | 'ai';     // 默认 'ai'
  accounts: string[];            // 默认 []
  draft: boolean;                // 默认 false
}
```

- **改字段：** 在 `content.config.ts` 的 `daily` schema 改 Zod，并相应修改：
  - `daily_digest.py` 的 `build_markdown()` 头部（frontmatter 输出）；
  - `DailyLayout.astro` 的渲染逻辑（如果要展示新字段）。
- **`draft: true`：** 该日报不会被 `getDailyReports()` 列出，也不进导航——可用于暂存未完成的日报。

### 2.4 digest.py 与 NormalizedItem 字段映射（维护关键点）

digest 实际使用的字段：

| 用途 | 字段 |
| --- | --- |
| 推文正文 | `content`（回退 `title`） |
| 账号显示名 | `publisher`（回退 `metadata.account`） |
| "原文"链接 | `canonical_url` |
| 互动数（排序+展示） | `metadata.stats.{likes,retweets,replies,views}` |
| 媒体 | `media[].url` → 渲染为纯链接 `[媒体](url)`（**不**触发本地图片优化流水线） |
| 按日期分组 | `published_at`（回退 `fetched_at`） |
| 过滤 | `is_meaningful === false` 的条目会被跳过 |

> 若 X-Reader 改了 `NormalizedItem` 字段名，**这里是对应修改点**。`src/content.config.ts` 一般不需要动，除非你要新增对外展示的字段。

### 2.5 CI / 部署失败排查（站点仓库 `deploy.yml`）

流水线顺序：`astro check` → `test:md` → `build`（含 `optimize_images`）→ `links` → `test`。

| 阶段 | 常见原因 / 处理 |
| --- | --- |
| `astro check` 失败 | 多半是 `daily` schema 与某篇 `.md` 的 frontmatter 不符（如 `title` 为空、`pubDate` 无法解析）。修 frontmatter 或 schema |
| `test:md` 失败 | 只跑 `tests/markdown/*.test.mjs`，**与日报无关**，基本不会因日报触发 |
| `build` 失败 | 图片/链接语法问题；日报媒体只用纯链接，风险低 |
| `links` 失败 | `check_links.py` 查站内死链。日报"原文"指向 `x.com`，一般可用；若个别帖子 404 会报死链——可在 links 配置把 `x.com` 加例外，或确认链接正确 |
| `test` 失败 | Python unittest，与日报无关 |

> 本机没有 `gh` CLI 时无法在本地 poll CI 状态；直接去 GitHub 仓库的 **Actions** 页面查看运行结果。

### 2.6 成本与边界

- **整个方案零额外成本：** X-Reader 与站点的 Actions 都在 GitHub 免费额度内；不需要 VPS、不需要 LLM API key（LLM 只在本机 WorkBuddy 跑一次）。
- **Sotwe 源：** 可行性评估已判定不可行，未改动代码（见 §0 提示）。
- **LLM 自动化（可选改进）：** 若想进一步减少手动步骤，可把"步骤 2 填摘要"脚本化（例如接本地 LLM/API），但需注意这会把 key/额度带进本地流程——当前刻意保留手动，便于你审校摘要质量。

### 2.7 旧副本说明

`X-rss-workspace/daily-report/digest.py` 是早期原型，**已被 `github page work/scripts/daily_digest.py` 取代**。以后一律以站点仓库内的为准；旧文件可删除或仅留作参考，**不要基于它继续改**。

### 2.8 可能的改进（非必须）

1. 给 `daily_digest.py` 加 `--source x` 过滤，避免以后混入 RSS/YouTube 数据。
2. 把"步骤 2 填摘要"也脚本化，进一步减少手动步骤（权衡见 §2.6）。
3. 给 `daily.sh` 增加自动 `git add/commit/push`（目前只打印命令，避免误提交）。

---

## 三、一句话速查

```
每天：
  1) git -C X-rss-workspace/X-Reader pull        # 拿 CI 抓的数据
  2) python scripts/daily_digest.py --items-dir X-rss-workspace/X-Reader/data/items
  3) 让 WorkBuddy 填 <!--AI_SUMMARY-->
  4) git add src/content/daily/<date>.md && git commit -m "daily: <date>" && git push
```
