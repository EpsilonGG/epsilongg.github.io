# X 每日推特日报 — 日常运营指南与维护指南

> 适用项目：EpsilonGG 个人站（`github.com/EpsilonGG/epsilongg.github.io`，本机路径 `Desktop\github page work`）
> 配套工具：X-Reader（抓取+规范化）。X-rss 仓库的"储存地"= `X-rss-workspace`。
> 最后更新：2026-10-25

---

## 0. 项目概览（混合架构，先读这段）

日报采用 **「CI 抓取 + 本地 LLM 摘要 + 站点 CI 部署」** 的混合方案，把"需要 LLM"的那一步留在你本机的 WorkBuddy，其余全自动、免费、不需要服务器。

涉及三个角色：

| 角色 | 位置 | 负责什么 |
| --- | --- | --- |
| **X-Reader（抓取侧）** | GitHub 上的 X-Reader 仓库；本机 checkout 在 `X-rss-workspace/X-Reader` | 每日自动抓取 X 推文，规范化为 `NormalizedItem`，写入并提交 `data/items/*.jsonl` |
| **本地组装 + 本地 LLM** | 站点仓库 `scripts/daily_digest.py` + `scripts/daily.sh`，外加本机 WorkBuddy | 把 `data/items` 确定性组装成 `src/content/daily/<期号>.md` 骨架；由 WorkBuddy 填 `highlights` / `works` / `interactions` / `people` |
| **站点仓库（发布侧）** | `Desktop\github page work` = `epsilongg.github.io` | 存放脚本与产出 `.md`；`git push` 后 Actions 自动构建部署到 GitHub Pages |

**数据流（每天一次）：**

```
X-Reader CI (每日 17:10 UTC)
   └─ fetch → 写 data/items/x.jsonl → git commit/push 进 X-Reader 仓库
        │
   本地：git pull X-Reader 仓库（拿到最新 data/items）
        │
   本地：python scripts/daily_digest.py --items-dir <X-Reader>/data/items
        └─ 产出 src/content/daily/<期号>.md（四段全空的骨架）
        │
   本地 WorkBuddy：读 briefing，填今日看点 / 作品动态 / 互动 / 每人一句
        │
   本地：git add src/content/daily/<期号>.md && commit && push
        │
   站点 Actions (deploy.yml)：astro check → test:md → build → links → test → 部署
```

**为什么这么设计：** X-Reader 与站点的 Actions 都在 GitHub 免费额度内；CI 里**不跑 LLM**、不需要 API key、不需要 VPS。只有"写摘要"这一步在你本机 WorkBuddy 完成一次，零额外成本。

> ⚠️ **Sotwe 作为补充 X 源：** 已做过可行性评估，结论为**不可行**（时间线为 JS 渲染，`selectolax` 无法提取；无公开 API；无头浏览器违反项目约束）。按规范已 STOP，未改动任何代码。扩充来源请优先在 X-Reader 内加 provider/route。

---

## 日报的文件、期号与存档

**文件名就是发布时间，也是网址。** 一期日报对应一个文件：

```
src/content/daily/26103122.md   →   /daily/26103122/
                    ││││││││
                    ││││││└┴─ 22 时（JST）
                    │││└┴───── 31 日
                    │└──────── 10 月
                    └───────── 26 年
```

格式 `YYMMDDHH`，八位数字，**日本时间（JST）**。2026-10-31 22:00（JST）= `26103122`。

**为什么精确到小时。** 只到天的话 `2026-10-31.md` 一天只能有一个，补一次就把上一期冲掉；精确到小时后每跑一次都是新文件，旧的一期自动留档——这就是「带存档」的实现方式。代价是同一天可能有多期，所以归档列表**按天不合并**，一行一期。

因为时间只有文件名一个来源，frontmatter 里**没有 `title`、也没有 `pubDate`**：

- 标题由期号推导：`X 日报 · 2026-10-31 22:00`；
- 发布时间由期号推导（`src/lib/daily.ts` 的 `parseDailyId`），手改日期不可能和 URL 对不上。

文件名不合规（不是八位数字、或 `26103231` 这种不存在的日期）会让**构建直接失败**并指出是哪个文件。

### 三条路由

| 路由 | 是什么 |
| --- | --- |
| `/daily/` | 归档列表，按月分组，一行一期（时间 + 看点简报） |
| `/daily/<期号>/` | 单期详情，`getStaticPaths` 从内容集合生成，没有手写路由 |
| `/daily/rss.xml` | **归档 feed**，独立于主 `/rss.xml`（那个只收「笔记」） |

> 独立 feed 的理由：日报每天一期且是 AI 整理的，混进主 feed 会改变既有订阅者收到的东西。分开后，归档页能翻，feed 能被阅读器收走。

---

## 日报的版式（四段，顺序固定）

站点只渲染 frontmatter，不渲染 Markdown 正文。四段的顺序和格式都是定死的：

| 顺位 | 字段 | 内容 | 没有内容时 |
| --- | --- | --- | --- |
| 1 | `highlights` | **今日看点**：只写三样东西——①名单前 9 的声优提到的重点 ②内容里本人对自己热度／排行的讨论 ③特别活动（生誕祭、线下活动、销量里程碑） | 页面显示「今日看点待补充」，构建日志警告 |
| 2 | `works` | **作品动态**：**一段话**汇总账号提到的作品进度（制作中 / 正式发售 / 销量里程碑 / 上架）。可以点名是谁说的，**不加来源链接** | 整段不渲染 |
| 3 | `interactions` | **互动**：名单内多人之间的互动，每项一条，写成文字 | 整段不渲染 |
| 4 | `people` | **详细**：每人一句话，渲染成 `[声优名](主号链接) ：一句话` | `summary` 为空的条目自动不渲染 |

另有一个副标题字段 `description`，显示在标题下方：

| 字段 | 内容 | 约束 |
| --- | --- | --- |
| `description` | **今日看点的简报**，一句话说清今天最值得看的事 | **≤ 50 字**；超长构建直接失败；不写日期、不罗列账号名 |

几条硬规则：

- **看点不是「详细」的加长版**。它只负责挑出当天最该被看见的 2–3 件事：前 9 名（按作品数）的人说了什么、有没有人聊自己的热度／排行、有没有特别活动。**其余全部下沉到「详细」**——一条一条写在那儿，读者想细看再往下翻。以前把五个人塞进一段（「其余几位各有各的节奏：……」）正是这次要修掉的问题。
- **作品动态必须是一段话，且不带链接**。它是横向汇总：同一个促销会牵涉好几个人，按人写会重复，按段写一句就够。**不要加来源网址**——人名在「详细」里已经链到主号，再给每条加引用会让这一段变成链接堆。
- **副标题不是「日期 + 摘要（@账号1 / @账号2）」**。日期在标题和「发布于」里已经有了，账号名读者扫一眼「详细」就知道，占掉这 50 字很浪费。写成 `柚木つばめ生誕祭前夜，「FIRST FLIGHT」明日会场生配信，几位放出新作预告` 这样。
- **「详细」里的一行是 `声优名（链接） ：一句话`**。名字由名单 `src/config/daily-roster.json` 的 `name` 提供，链接由 `handle` 拼成 `https://x.com/<handle>`，**模型既不写名字也不写网址**——写成字段后模型只负责句子，两样都不可能错。
- **`summary` 里不要再写 `@handle`**。名字已经显示在行首了，句子里再写一遍等于同一行出现两次账号。
- **当日没有活动的人直接省略**：`summary` 留空即可，不需要删条目。
- **不展示互动量**（点赞、转发、阅读数）。这些数字只在 `out/<期号>.briefing.txt` 里给模型判断轻重用，不进站点内容。
- 正文里的 `@handle` 会自动变成主页链接，但**只认名单里的人**（`accounts` + `people` 里的 handle），名单外的 @ 保持纯文本。

> 为什么四段全放 frontmatter 而不是写进 Markdown 正文：上百人时这些字段要拿去做分类视图、JSON 输出和筛选，藏在正文里就取不出来。详见 [日报扩容方案](daily-scaling-plan.md)。

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

- `--date YYYY-MM-DD`：可选，**汇总哪一天的数据**（默认取数据里最新一天）。注意这和期号是两件事：`--date` 选数据，期号是发布时间。
- `--at "2026-10-31 22:00"`：可选，**指定发布时间**（JST），决定期号。不写就取当前小时。
- `--force`：默认**拒绝覆盖已存在的期号**——覆盖等于删掉一期存档。确实要重写同一期时才加。
- `--per-account N`：可选，briefing 里每个账号最多写几条，**默认不截**（有几条写几条）。给了数就按（互动数, 发布时间）从高到低截。只在「某人一天刷了 30 条把 briefing 撑爆」时才用。
- **`active: false` 的账号（社团号、制造商号）照旧进名单，但条目不进这一期**：脚本会把跳过的账号名打到 stderr。这两类现在全是 `active: false`，等日报要收它们的动态时再逐个打开。
- **名单三类实体**：`seiyuu`（声优，128 条 / 98 人）、`circle`（同人音声社团，109 条）、`manufacturer`（游戏厂商，173 条）。**一个 handle 只建一条**——同一个号既是厂商的又是社团的（`@cube_staff`、`@pachipachisoft`），或本来就是某位声优的主号（`@ayakaigasaki`），只保留已有那条，另一重身份写进 `note`。身份靠 `tags` 区分：声优 `["声优","创作者"]`、社团 `["创作者","音声"]`、厂商 `["创作者","游戏"]`，有社团号的声优补 `"音声"`，近十年拿过萌えゲーアワード的厂商补 `"Moe Award"`。
- 产出：
  - `src/content/daily/<期号>.md` —— 站点内容的**骨架**：frontmatter 里 `accounts` 已按名单序排好，`highlights` / `interactions` 是空数组、`works` 是空串，`people` 每人一条 `summary: ""`，正文只有一个待填说明的注释。
  - `out/<期号>.briefing.txt` —— 喂给 LLM 的事实摘要（推文原文 + 互动数都在这里，已被 `.gitignore` 忽略，属本地中间产物）。
- **注意：脚本不再把推文原文写进 `.md`**，只写骨架。要写摘要必须看 `briefing.txt`。
- **空跑预览（无真实数据）：** 直接 `./scripts/daily.sh 2026-10-24`，会用仓库内的 `scripts/sample_items/` 样例数据生成一份预览，方便测试流程。补一期过去的用 `AT="2026-10-24 21:00" ./scripts/daily.sh 2026-10-24`。

### 步骤 2 — 让本地 WorkBuddy 填写日报内容（唯一需要 LLM 的地方）

对 WorkBuddy 说：**"填写今天的日报"**。它会：

1. 读 `out/<期号>.briefing.txt`（推文原文与互动数都在这里）；
2. 填 `src/content/daily/<期号>.md` 的**四段 + 副标题**：
   - `description`：副标题，**今日看点的 50 字以内简报**（脚本留的是「今日 N 位账号有更新，看点待补」占位，必须改写）；
   - `highlights`：今日看点，**只写前 9 的重点 / 自述热度 / 特别活动**，其余下沉到「详细」；
   - `works`：作品动态，**一段话**，不带来源链接；
   - `interactions`：名单内谁和谁有互动、互动内容是什么，每项一条；**没有就留空数组**；
   - `people[].summary`：每人一句话，**不写 @handle**（行首已经显示名字了）；**当日没活动的留空**；
3. 不改 `accounts` / `people[].handle`——这些是脚本从数据推导的，手改会跟抓取数据对不上。`title` 与 `pubDate` 已经不在 frontmatter 里了，标题和发布时间都由文件名推导。

> 这一步就是"用 WorkBuddy 本地跑完需要 LLM 的部分"。LLM 不碰 API、不进 CI。
> 填完可以直接构建预览：`npm run dev` 看 `/daily/<期号>/`。

### 步骤 3 — 提交并推送站点仓库

```bash
git add src/content/daily/<期号>.md
git commit -m "daily: <期号>"
git push
```

推送后 `deploy.yml` 会自动构建并部署到 GitHub Pages，**无需手动构建**。

### 步骤 4（可选）— 在站点核对

部署完成后访问：
- 列表页：`/daily/`
- 详情页：`/daily/<期号>/`
确认四段都渲染了：今日看点在前、作品动态其次、互动再次、「详细」每行都能点到主页；「详细」里没有空链接、句子开头不再重复 @handle；副标题是一句 50 字以内的看点简报，不是「日期 + 账号名」。

### 日常常见问题

| 情况 | 处理 |
| --- | --- |
| 某天没有新推文 | digest 仍会生成骨架，但 `accounts` 为空；这种日子直接跳过、不发布即可（骨架页会显示「今日看点待补充」） |
| 数据还没抓到 | 先 `git pull` X-Reader 仓库，或等 CI（17:10 UTC）跑完再操作 |
| 想补过去的某天 | 用 `--date YYYY-MM-DD` 选数据，`--at "2026-10-24 21:00"` 定发布期号；数据 append-only 会保留历史 |
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
| `src/content.config.ts` | `daily` 内容集合的 Zod schema（**没有** `title` / `pubDate`，两者由文件名推导） |
| `src/lib/daily.ts` | 期号解析（`parseDailyId` / `toDailyId`）、`getDailyReports()`、按月分组、`dailyPath()` |
| `src/layouts/DailyLayout.astro` | 日报详情页布局（复用 `BaseLayout`，含"AI 整理"徽章、上/下篇导航） |
| `src/pages/daily/index.astro` | `/daily/` 归档列表（按月分组） |
| `src/pages/daily/[...id].astro` | `/daily/<期号>/` 详情页（`getStaticPaths`） |
| `src/pages/daily/rss.xml.ts` | `/daily/rss.xml` 归档 feed（独立于主 feed） |
| `src/config/navigation.json` | 顶部导航的"日报"入口 |
| `src/content/daily/<期号>.md` | **产出**：每期的日报内容，文件名即发布时间 |

### 2.2 X-Reader 端（抓取侧）

- **仓库：** `X-rss-workspace/X-Reader`（对应 GitHub 上的 X-Reader 仓库）。
- **CI：** `X-Reader/.github/workflows/update.yml`，每日 `17:10 UTC` 跑；`python main.py` 后 `git add data && commit && push`（只提交 `data/`）。
- **数据：** 规范存储是 `data/items/<source_id>.jsonl`（`NormalizedItem`，**append-only**）。X 数据 `source_id` 为 `x`，落在 `data/items/x.jsonl`。
- **加/减监控账号：** 改 `X-Reader/accounts.yaml`（不是站点仓库）。digest 的 `accounts` frontmatter 是根据数据**自动推导**的，无需手改。
- **加 RSS / YouTube 源：** 改 `X-Reader/config/config.yaml`。⚠️ 注意：digest 当前读取 `items/` 目录下**所有** `*.jsonl`；若以后引入非 X 源，日报会混入它们。要么只传 `data/items/x*.jsonl`，要么给 digest 加 `--source x` 过滤（见 §2.6）。

### 2.3 日报 frontmatter schema（`src/content.config.ts` 的 `daily` 集合）

```ts
{
  // 没有 title / pubDate：标题和发布时间由文件名（YYMMDDHH）推导
  description?: string;          // 可选，但一旦写了必须 ≤50 字（今日看点简报）
  source: 'original' | 'ai';     // 默认 'ai'
  accounts: string[];            // 默认 []，当天有活动的账号（脚本推导）
  highlights: string[];          // 默认 []，今日看点：前 9 重点 / 自述热度 / 特别活动
  works: string;                 // 默认 ''，作品动态：一段话，不带来源链接
  interactions: string[];        // 默认 []，多人互动，每项一条
  people: { handle: string; summary: string }[];  // 默认 []，summary 为空即不渲染
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
| 互动数（仅排序 + briefing） | `metadata.stats.{likes,retweets,replies,views}` |
| 媒体 | `media[].url` → 渲染为纯链接 `[媒体](url)`（**不**触发本地图片优化流水线） |
| 按日期分组 | `published_at`（回退 `fetched_at`） |
| 过滤 | `is_meaningful === false` 的条目会被跳过 |

> 若 X-Reader 改了 `NormalizedItem` 字段名，**这里是对应修改点**。`src/content.config.ts` 一般不需要动，除非你要新增对外展示的字段。

### 2.5 CI / 部署失败排查（站点仓库 `deploy.yml`）

流水线顺序：`astro check` → `test:md` → `build`（含 `optimize_images`）→ `links` → `test`。

| 阶段 | 常见原因 / 处理 |
| --- | --- |
| `astro check` 失败 | 多半是 `daily` schema 与某篇 `.md` 的 frontmatter 不符（如 `description` 超过 50 字）。**文件名不是 `YYMMDDHH` 会在 `build` 阶段抛错**，报错信息里带文件名 |
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
     （期号自动取当前 JST 小时；补旧的可加 --at "2026-10-24 21:00"）
  3) 让 WorkBuddy 填 description（≤50 字）/ highlights / works / interactions / people[].summary
  4) git add src/content/daily/<期号>.md && git commit -m "daily: <期号>" && git push

期号：YYMMDDHH（JST）。2026-10-31 22:00 → 26103122 → /daily/26103122/
存档：/daily/（按月分组） 订阅：/daily/rss.xml
```

### 为什么同一天可以有多期

期号带小时，所以「上午抓一次、晚上补一次」是两个文件、两个网址，互不覆盖。
归档列表按天**不合并**，一行一期，时间用等宽数字对齐，扫一眼就知道某天出了几期。
这也意味着重复运行 `daily_digest.py` 不会毁掉旧稿——除非显式 `--force`。
