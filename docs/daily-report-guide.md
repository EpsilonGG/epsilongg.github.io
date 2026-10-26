# X 每日推特日报 — 日常运营指南与维护指南

> 适用项目：EpsilonGG 个人站（`github.com/EpsilonGG/epsilongg.github.io`，本机路径 `Desktop\github page work`）
> 配套工具：X-Reader（抓取+规范化）。X-rss 仓库的"储存地"= `X-rss-workspace`。
> 最后更新：2026-10-26（M3.9：出稿改走「出题 → 答题 → 判卷合并」，`confirm` 定稿前再判一次；
> 金文件基准期改成可切换的 `tests/golden/current.json`）

---

## 0. 项目概览（混合架构，先读这段）

日报采用 **「CI 抓取 + 本地 LLM 摘要 + 站点 CI 部署」** 的混合方案，把"需要 LLM"的那一步留在你本机的 WorkBuddy，其余全自动、免费、不需要服务器。

涉及三个角色：

| 角色 | 位置 | 负责什么 |
| --- | --- | --- |
| **X-Reader（抓取侧）** | GitHub 上的 X-Reader 仓库；本机 checkout 在 `X-rss-workspace/X-Reader` | 每日自动抓取 X 推文，规范化为 `NormalizedItem`，写入并提交 `data/items/*.jsonl` |
| **本地组装 + 本地 LLM** | 站点仓库 `scripts/daily_digest.py` + `scripts/daily.sh`，外加本机 WorkBuddy | 把 `data/items` 确定性组装成 `out/<期号>/report.json` 骨架；由 WorkBuddy 填 `description` / `highlights` / `works` / `interactions` / `people` |
| **站点仓库（发布侧）** | `Desktop\github page work` = `epsilongg.github.io` | 存放脚本与 `data/daily/<期号>/report.json`；`git push` 后 Actions 自动构建部署到 GitHub Pages |

**数据流（每天一次）：**

```
X-Reader CI (每日 03:00 / 15:00 UTC)
   └─ fetch → 写 data/items/x.jsonl → git commit/push 进 X-Reader 仓库
        │
   本地：git pull X-Reader 仓库（拿到最新 data/items）
        │
   本地：python scripts/daily_digest.py --items-dir <X-Reader>/data/items
        └─ 产出 out/<期号>/report.json（四段全空的骨架）+ briefing
        │
   本地 WorkBuddy：读 briefing，填今日看点 / 作品动态 / 互动 / 每人一句
        │
   本地：confirm 定稿 → publish 搬到 data/daily/<期号>/report.json
        │
   本地：git add data/daily/<期号>/ && commit && push
        │
   站点 Actions (deploy.yml)：astro check → test:md → build → links → check:daily → test → 部署
```

**为什么这么设计：** X-Reader 与站点的 Actions 都在 GitHub 免费额度内；CI 里**不跑 LLM**、不需要 API key、不需要 VPS。只有"写摘要"这一步在你本机 WorkBuddy 完成一次，零额外成本。

> ⚠️ **Sotwe 作为补充 X 源：** 已做过可行性评估，结论为**不可行**（时间线为 JS 渲染，`selectolax` 无法提取；无公开 API；无头浏览器违反项目约束）。按规范已 STOP，未改动任何代码。扩充来源请优先在 X-Reader 内加 provider/route。

---

## 日报的文件、期号与存档

**目录名就是发布时间，也是网址。** 一期日报对应一个目录（M4 之前是一个 `.md` 文件）：

```
data/daily/26103122/report.json   →   /daily/26103122/
           ││││││││
           ││││││└┴─ 22 时（JST）
           │││└┴───── 31 日
           │└──────── 10 月
           └───────── 26 年
```

格式 `YYMMDDHH`，八位数字，**日本时间（JST）**。2026-10-31 22:00（JST）= `26103122`。

**为什么精确到小时。** 只到天的话 `2026-10-31` 一天只能有一个，补一次就把上一期冲掉；精确到小时后每跑一次都是新目录，旧的一期自动留档——这就是「带存档」的实现方式。代价是同一天可能有多期，所以归档列表**按天不合并**，一行一期。

因为时间只有期号一个来源，`report.json` 里**没有 `title`、也没有 `pubDate`**：

- 标题由期号推导：`X 日报 · 2026-10-31 22:00`；
- 发布时间优先取 `issue.published_at`，缺失时退回期号（`src/lib/daily.ts` 的 `resolvePublishedAt`），手改日期不可能和 URL 对不上。

期号不合规（不是八位数字、或 `26103231` 这种不存在的日期）会让**构建直接失败**并指出是哪一期。

### 五个出口

| 路由 | 是什么 |
| --- | --- |
| `/daily/` | 归档列表，按月分组，一行一期（时间 + 看点简报）；顶部有「看最新一期」与月份锚点 |
| `/daily/<期号>/` | 单期详情，`getStaticPaths` 从内容集合生成，没有手写路由 |
| `/daily/rss.xml` | **归档 feed**，独立于主 `/rss.xml`（那个只收「笔记」） |
| `/daily/<期号>.json` | **JSON**，与 `data/daily/<期号>/report.json` 逐字节相同（含 `sources`），给第三方/脚本 |
| `/daily/<期号>.txt` | **纯文本**，给复制粘贴和 M6 的视频稿；只换格式，不重新概括 |

> 独立 feed 的理由：日报每天一期且是 AI 整理的，混进主 feed 会改变既有订阅者收到的东西。分开后，归档页能翻，feed 能被阅读器收走。
>
> 后两个出口由 `npm run check:daily` 守着：有一份 `report.json` 就必须有三份产物，且 JSON 与正本逐字节相同。链接检查看不见这两个文件——没有别处引用它们。

---

## 日报的版式（四段，顺序固定）

站点只渲染 `report.json` 的结构化字段，没有 Markdown 正文。四段的顺序和格式都是定死的：

| 顺位 | 字段 | 内容 | 没有内容时 |
| --- | --- | --- | --- |
| 1 | `highlights` | **今日看点**：只写三样东西——①名单前 9 的声优提到的重点 ②内容里本人对自己热度／排行的讨论 ③特别活动（生誕祭、线下活动、销量里程碑） | 页面显示「今日看点待补充」，构建日志警告 |
| 2 | `works` | **作品动态**：**一段话**汇总账号提到的作品进度（制作中 / 正式发售 / 销量里程碑 / 上架）。可以点名是谁说的，**不加来源链接** | 整段不渲染 |
| 3 | `interactions` | **互动**：名单内多人之间的互动，每项一条，写成文字 | 整段不渲染 |
| 4 | `people` | **详细**：每人一句话，渲染成 `[声优名](主号链接) ：一句话` | `summary` 为空的条目自动不渲染 |

另有两个字段，目前各期都是空的，**空则整节不渲染**——它们是给「按分类出稿」的那天准备的：

| 字段 | 渲染成 | 什么时候有值 |
| --- | --- | --- |
| `categories[].summary` | 「分类摘要」一节，每个分类一行 | 一期按「聊人 / 聊音声 / 聊事情」分开出题时 |
| `insights` | 「洞察」一节，跨分类的观察 | 全局题（`prompt --reduce`）产出 |

还有一个副标题字段 `description`，显示在标题下方：

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

> 为什么四段是结构化字段而不是一段 Markdown 正文：上百人时这些字段要拿去做分类视图、JSON 输出和筛选，藏在正文里就取不出来。M4 之前它们放在 frontmatter 里，M4 之后放在 `report.json` 里，理由一样。详见 [日报扩容方案](daily-scaling-plan.md)。

---

## 一、日常运营指南（每天生成日报）

每天（早晨或你方便的时间）生成前一天/当天的推特日报，只需 4 步。

### 步骤 0 — 确认/获取当天数据

digest 读取的目录是 **X-Reader checkout 的 `data/items`**。两种方式拿到数据：

- **方式 A（推荐，用 CI 已抓的数据）：** 在 `X-rss-workspace/X-Reader` 里执行 `git pull`，拉取 CI 提交的 `data/items/`。
- **方式 B（本地现抓）：** 在 `X-rss-workspace/X-Reader` 里执行 `python main.py --json`（需要该仓库的依赖与凭证）。

> CI 每天 **`03:00` 与 `15:00` UTC** 各跑一次。`15:00 UTC` = **JST 00:00**，
> 那一刻 JST 自然日刚好闭合，所以此后拉到的就是完整的一天。
> 换算到北京时间是 11:00 与 23:00，**日报在 23:00 之后跑才有完整数据**。

**一条命令做完步骤 0–1（自动化走的就是这条）：**

```bash
DAILY_PROXY=http://127.0.0.1:7897 python scripts/daily_prepare.py
```

它做三件事：`git pull` 抓取仓库 → 按 JST 自然日数一遍条数 → 调 digest 出骨架。
默认处理「昨天的 JST 自然日」，`--date 2026-10-25` 可指定，`--no-pull` 跳过拉取。

| 退出码 | 含义 | 该怎么办 |
|---|---|---|
| 0 | 骨架已生成 | 继续步骤 2 |
| 2 | 目标日在数据里**一条都没有** | 抓取侧没跑或失败，**不要写这一期** |
| 3 | 抓取仓库拉取失败 | 检查网络/代理，同样不要写 |

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
  - `out/<期号>/report.json` —— 站点内容的**正本骨架**：`accounts` 已按名单序排好，`highlights` / `interactions` 是空数组、`works` 是空串，`people` 每人一条 `summary: ""`（主号一行、其余号进 `via`），`issue.status` 是 `draft`。
  - `out/<期号>.briefing.txt` —— 喂给 LLM 的事实摘要（推文原文 + 互动数都在这里，已被 `.gitignore` 忽略，属本地中间产物）。
  - `out/<期号>.generate.json` —— M3 的题库（分类与条目 key），`prompt` / `apply` 用它。
- **注意：脚本不再把推文原文写进正本**，只写骨架。要写摘要必须看 `briefing.txt`。
- **站点读的不是这个文件。** 站点读 `data/daily/<期号>/report.json`，由步骤 2.6 的 `publish` 搬过去。草稿留在 `out/`，构建永远看不到它。
- **空跑预览（无真实数据）：** 直接 `./scripts/daily.sh 2026-10-24`，会用仓库内的 `scripts/sample_items/` 样例数据生成一份预览，方便测试流程。补一期过去的用 `AT="2026-10-24 21:00" ./scripts/daily.sh 2026-10-24`。

### 步骤 2 — 出题、答题、判卷合并（唯一需要 LLM 的地方）

对 WorkBuddy 说：**"填写今天的日报"**。从 M3.9 起，这条路不再是「直接改正本」，
而是三步，中间那一步才是模型：

```bash
python scripts/daily_digest.py prompt --issue <期号> --flat   # 出题
#   …读 out/<期号>/prompts/all.md，把回答写成 out/<期号>/answer/all.json…
python scripts/daily_digest.py apply --issue <期号> --answer out/<期号>/answer/all.json   # 判卷 + 合并
```

**为什么绕这一圈。** 以前是直接改 `report.json`，`apply` 的判卷完全不生效——
七期已发布的正本里 `people[].sources` 全是空数组，没有一处能被机器验证。
现在题面里每条材料都带来源 key（`[x:2113…]`），回答里的每句话都要指回一个 key，
`apply` 逐条核对：来源不存在、handle 不在名单里、长度超限，都会**整份拒收**并指出是哪一句。

**题面 `prompts/all.md` 里有什么**：本期全部条目，按账号分组，每条前面是 `[key] @账号 · 时间 · 类型`，
外加本期的 handles 清单和回答模板。它是**唯一的事实来源**——只写里面有的东西。

**回答 `answer/all.json` 的形状**（`category` 固定 `"all"`）：

```json
{
  "category": "all",
  "summary": "今日看点的简报，≤50 字，会直接当页面副标题",
  "works": "作品动态：一段话汇总制作中／发售／销量里程碑，不加链接",
  "highlights": [{"text": "…", "sources": ["x:2113…"]}],
  "interactions": [{"text": "…", "sources": ["x:2114…"]}],
  "people": [{"handle": "…", "summary": "…", "sources": ["x:2115…"]}]
}
```

编辑口径（这部分是人的决定，判卷管不了）：

- `summary`：**今日看点的 50 字以内简报**，不写日期、不罗列账号名。超长直接判失败。
- `highlights`：2–4 条，**只写前 9 的重点 / 自述热度 / 特别活动**，其余下沉到「详细」。
- `works`：**一段话**，不带来源链接（人名在 `people` 里已经链到主号）。
- `interactions`：名单内谁和谁有互动，每项一条；**没有就留空数组**。
- `people[].summary`：每人一句话，**不写 @handle**（行首已经显示名字了）；**当日没活动的留空**。
- 不要改 `accounts` / `people[].handle` / `people[].via`——脚本推导的。标题与发布时间由期号推导，不在数据里。

**一人一行，不管他今天用了几个号。** 名单里同 `name` 的主号、小号、社团号在
`build_report` 里已经合成一行：行首是主号，其余号写进 `via`，页面在句末渲染成
小一号、颜色变淡的 `@handle` 链接（显示账号名，不显示人名）。
所以写摘要时要把几个号的内容**串成一句话**，别按号拆开；写成小号 handle 也会并回同一行：

```json
{
  "handle": "ayumi_sarah",
  "summary": "预告 potte 新作（与 北見六花 共演）…；社团号补上新作预告收藏破 200、11 月中旬发售。",
  "via": ["potte1919"]
}
```

**转发条目归到转发者名下。** 名单外的 handle 不会进 `people`——它们是名单内成员转发的
原发账号（`metadata.retweeted_by` 可读）。写的时候挂在转发者那一行，用「转发了…的内容」
「转发提到了…」「动态是…」这类说法，怎么通顺怎么来，不要生硬地一律「转发了」。

> 这一步就是"用 WorkBuddy 本地跑完需要 LLM 的部分"。LLM 不碰 API、不进 CI。
> `apply` 之后可以直接构建预览：`npm run dev` 看 `/daily/<期号>/`。

### 步骤 2.5 — 判卷（随时可跑，也能查已发布的期）

```bash
python scripts/daily_digest.py audit --issue <期号>                 # 查工作区
python scripts/daily_digest.py audit --issue <期号> --published     # 查 data/daily/ 里那份
```

两种严格度：新写的稿子默认 `--strict`（每条 claim 必须有来源）；
`daily.migrate` 迁移来的旧正本自动走宽松模式（没有来源只提醒，来源写错仍然算错）。
`confirm` 定稿前会自动跑一次，不过就不许定稿；确实要跳过加 `--no-audit`。

`audit` 会报两类东西，别混：

| 级别 | 例子 | 会拦定稿吗 |
| --- | --- | --- |
| 错误 | 来源 key 不存在、handle 不在名单、重复出现、副标题超 50 字 | 会 |
| 提醒 | 没有来源（宽松模式）、名单里有但本期没条目、摘要为空 | 不会 |

「名单里有但本期没条目」只算提醒是有意的：重复判定、从提及里补录，都会造成这种情况，
两者都合法。**凭空造人**会先撞上「不在名单里」。

### 步骤 2.6 — 分类出稿（可选，暂未启用）

现在一期就是一篇（`category="all"`），所以用 `--flat`。等真要按「聊人 / 聊音声 / 聊事情」分栏时，
改用分类链路，判卷完全通用：

```bash
python scripts/daily_digest.py prompt --issue <期号>            # 每个分类一份题
#   …回答存成 out/<期号>/answer/<分类>.json…
python scripts/daily_digest.py prompt --issue <期号> --reduce   # 分类答完再出全局题（description + 今日看点）
python scripts/daily_digest.py apply  --issue <期号>            # 一次合并全部回答
```

`report.json` 的 `categories` / `insights` 两个字段就是给这条路留的，现在是空的（页面整节不渲染）。

### 步骤 2.6 — 发布（把正本搬到站点读的位置）

```bash
python scripts/daily_digest.py publish --issue <期号>
```

`out/<期号>/report.json` → `data/daily/<期号>/report.json`。三条规矩：

- **只发定稿**：`status` 不是 `confirmed` 直接拒绝——草稿进 `data/daily/` 就等于上线；
- **默认不覆盖**：已经发布过的期号再发要显式 `--force`，避免「补一句摘要」悄悄改掉一份可能被引用过的 JSON；
- **落盘前先过 schema**：字段写错在这里报，而不是等到 `npm run build`。

发布完 `npm run build`（本地要先 `mv dist` 绕开安全删除阈值）就能看到这一期。**没有 publish 这一步，站点不会变**——这是 M4 之前最常踩的坑。

### 步骤 3 — 提交并推送站点仓库

```bash
python scripts/push_site.py -m "daily: <期号>" --path data/daily/
```

**必须带 `--path`**：不带时脚本是 `git add -A`，工作区里任何未提交的改动都会卷进这一期日报的
commit（2026-10-26 就把一篇 496 行的新访谈卷进了「docs: 抓取侧改成每天两跑」，提交信息与内容对不上）。
带上之后只提交该路径，其余改动留在工作区并打印出来。

**不要直接 `git push`**：这台机器上它会在走到 `git-credential-manager.exe` 时被 SIGTERM 掉，
连 `--dry-run` 都过不去。`push_site.py` 换成「GCM 取 token → 临时 askpass 脚本 → 推完立刻删」，
直连会 schannel 握手失败，所以默认走 `127.0.0.1:7897` 代理（`--proxy` 可改）。

推送后 `deploy.yml` 会自动构建并部署到 GitHub Pages，**无需手动构建**。
本机 `npm run build` 会撞上安全删除阈值（单轮 ≥50 文件）而失败，真要本地构建先把 `dist` 移走。

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
| `apply` 报「来源不存在」 | 回答里的 key 抄错了。题面 `prompts/all.md` 里每条材料前面的 `[x:…]` 才是合法值，不要自己拼 |
| `confirm` 说判卷没过 | 按输出的路径改正本/回答；真要让缺来源的稿子过去才用 `--no-audit`（会记一笔） |
| 构建日志出现「N 行不是合法 JSON，已跳过」 | 抓取文件里有坏行。先看是哪几行（脚本会打印 `文件名#行号`），再看 X-Reader 那边是不是写到一半被杀 |
| 金文件红了（`check:daily` 报 diff） | 先看 diff 是「版式真的变了」还是「内容真的改了」。确认是有意的，再 `npm run golden:daily:switch` 换基准；**不要为了让它变绿而无脑重抓** |

---

## 二、维护指南（改东西 / 出问题时看这里）

### 2.1 文件地图（站点仓库 `github page work`）

| 文件 | 作用 |
| --- | --- |
| `scripts/daily_digest.py` | ★ **规范、唯一的组装脚本**（无 LLM 的一半）。**不要再改 `X-rss-workspace/daily-report/digest.py`**，那是被取代的旧原型 |
| `scripts/daily_prepare.py` | ★ **自动化入口**：`git pull` 抓取仓库 → 数目标日条数（0 条退 2）→ 调 digest 出骨架。确定性、无 LLM |
| `scripts/daily_condense.py` | 把 briefing 压成编辑视图（去 URL／互动数／纯转发，关键词优先）。5.2 万 → 1.5 万 token |
| `scripts/daily/` | M1–M4 的包：`build` / `window` / `incremental` / `dedupe` / `order` / `export` / `prompt` / `apply` / `validate` / `audit` / `confirm` / `publish` / `migrate` |
| `scripts/daily/audit.py` | ★ M3.9 事后判卷：来源 key 是否真实、handle 是否名单内且本期有条目、长度。`confirm` 定稿前自动跑 |
| `scripts/daily_golden.py` | M4.8 金文件：抓 `.prose` 纯文本比对；基准期在 `tests/golden/current.json`，`--switch` 换基准 |
| `scripts/check_daily_site.py` | M4 出口闸门：三种产物齐全、JSON 与正本逐字节相同、两个 Feed 不混、跑金文件 |
| `schemas/report.schema.json` | 正本的唯一裁判（Python 与 Zod 都按它） |
| `schemas/generation.schema.json` | 模型回答的形状（含整期题的 `works`） |
| `tests/golden/current.json` | 金文件基准指针（`{"id": "26102522"}`），换基准用 `npm run golden:daily:switch` |
| `README/reports/daily-m5-m6-options.html` | M5（图片）/ M6（视频稿）的选型比较、代价与顺序。开工前先读 |
| `scripts/push_site.py` | 提交并推送，绕开本机 `git push` 被 SIGTERM 的问题（GCM 取 token → 临时 askpass → 推完即删）。**日报要带 `--path data/daily/`**，否则 `git add -A` 会卷进无关改动 |
| `scripts/sync_xreader_accounts.py` | 站点名单 → `X-Reader/accounts.yaml`（只写 `seiyuu` 且 `active != false`）。`--check` 只比对 |
| `scripts/daily.sh` | 一键流程包装：组装 → 提示用 WorkBuddy 填摘要 → 打印 git 命令 |
| `scripts/rss_to_items.py` | 把 X-rss-main 的**真实** RSS feeds（`output/feeds_processed/*.xml`）转成 NormalizedItem JSONL（账号/原文链接/内容均为真实；该 RSS 源不含媒体与互动数） |
| `scripts/sample_items/x.jsonl` | 预览/测试数据。现由 `rss_to_items.py` 从 X-rss-main 真实 feeds 生成（**真实推文**，非编造） |
| `src/content.config.ts` | `dailyReports` 集合：`glob({ base: './data/daily', pattern: '*/report.json' })` + Zod（**没有** `title` / `pubDate`，两者由期号推导） |
| `src/lib/daily.ts` | 期号解析（`parseDailyId` / `toDailyId`）、`getDailyReports()`、按月分组、`dailyPath()`、`plainText()`（`.txt` 出口） |
| `src/lib/roster.ts` | 名单查询：`nameOf()` / `displayNameOf()`，页面与 `.txt` 共用 |
| `src/layouts/DailyLayout.astro` | 日报详情页布局（复用 `BaseLayout`，含"AI 整理"徽章、纯文本版链接、上/下篇导航） |
| `src/pages/daily/index.astro` | `/daily/` 归档列表（按月分组） |
| `src/pages/daily/[...id].astro` | `/daily/<期号>/` 详情页（`getStaticPaths`） |
| `src/pages/daily/rss.xml.ts` | `/daily/rss.xml` 归档 feed（独立于主 feed） |
| `src/pages/daily/[id].json.ts` | `/daily/<期号>.json`：与正本逐字节相同的 JSON 出口 |
| `src/pages/daily/[id].txt.ts` | `/daily/<期号>.txt`：纯文本出口（复制粘贴 / M6 视频稿） |
| `src/config/navigation.json` | 顶部导航的"日报"入口 |
| `data/daily/<期号>/report.json` | **产出（已发布）**：站点读的正本，目录名即发布时间 |
| `out/<期号>/report.json` | 工作区正本（草稿/已定稿），`publish` 才搬到 `data/daily/` |

### 2.2 X-Reader 端（抓取侧）

- **仓库：** `X-rss-workspace/X-Reader`（= `github.com/EpsilonGG/X-Reader`，**是真正的 git clone**，`git pull` 能拿到 CI 提交的数据）。
- **CI：** `X-Reader/.github/workflows/update.yml`，每日 **`03:00` 与 `15:00` UTC** 各跑一次。
  `15:00 UTC` = **JST 00:00**，正好是 JST 自然日闭合的时刻，所以这一次的数据就是完整的一天；
  一天两跑是因为 Nitter RSS 每个账号最多返回约 20 条，单跑会丢掉话多的人最早那几条。
  `python main.py` 之后 `git add data && commit && push`（只提交 `data/`）。
- **数据：** 规范存储是 `data/items/<source_id>.jsonl`（`NormalizedItem`，**append-only**）。X 数据 `source_id` 为 `x`，落在 `data/items/x.jsonl`。
- **加/减监控账号：** **不要手改 `accounts.yaml`**，它由站点名单生成：
  ```bash
  python scripts/sync_xreader_accounts.py --out "<X-Reader>/accounts.yaml"
  python scripts/sync_xreader_accounts.py --out ... --check   # 只比对，不一致退 1
  ```
  只写 `category: seiyuu` 且 `active != false` 的条目（现在是 128 个）。社团号与厂商号是
  `active: false`，不会被写进去。正本里的 `accounts` 由数据**自动推导**，同样不用手改。
- **实例可靠性：** 公共 Nitter 实例大半已死（410 / 451 / 403 / 人机验证页）。2026-10-26 实测 13 个里只有 1 个能出 feed，
  `config/config.yaml` 里按「能用的排前面」重排过。`providers/nitter.py` 会校验响应**是不是 feed**——
  200 但内容是验证页时记为这个实例失败并继续下一个，否则会静默返回「今天没人发推」。
- **加 RSS / YouTube 源：** 改 `X-Reader/config/config.yaml`。⚠️ 注意：digest 当前读取 `items/` 目录下**所有** `*.jsonl`；若以后引入非 X 源，日报会混入它们。要么只传 `data/items/x*.jsonl`，要么给 digest 加 `--source x` 过滤（见 §2.6）。

### 2.3 正本 schema（`data/daily/<期号>/report.json` + `content.config.ts` 的 `dailyReports`）

两份定义必须同步：`schemas/report.schema.json`（Python 侧，`apply` / `publish` 用它校验）与
`src/content.config.ts` 的 Zod（构建期用它校验）。**只加不改**——改名字要升 `schema_version` 并写迁移。

```jsonc
{
  "schema_version": 1,
  "issue": {
    "id": "26102322",                        // 八位期号，必须和目录名一致
    "published_at": "2026-10-23T22:00:00+09:00",
    "window": { "start": "...", "end": "..." },  // JST 自然日 [00:00, 次日 00:00)
    "status": "draft | confirmed",           // publish 只认 confirmed
    "confirmed_at": "..." | null
  },
  "counts": { "items": 0, "accounts": 6, "late": 0, "skipped_duplicate": 0 },
  "description": "≤50 字，今日看点简报",
  "highlights":   [{ "text": "...", "sources": ["x:123"] }],
  "insights":     [{ "text": "...", "sources": ["x:123"] }],   // 空则整节不渲染
  "interactions": [{ "text": "...", "sources": ["x:123"] }],   // 空则整段不渲染
  "works": "一段话，不带来源链接",
  "categories": [{ "id": "people", "label": "聊人", "summary": "..." }],  // 空则整节不渲染
  "accounts": ["handle", "..."],             // 正文 @提及 的链接白名单
  "people": [{ "handle": "...", "category": "", "summary": "...", "via": ["..."], "sources": ["x:123"] }],
  "provenance": { "generator": "daily.build", "prompt_version": 1, "cache_key": "", "generated_at": "" }
}
```

- **`sources` 是唯一能回溯的凭据**：页面不显示，但 `/daily/<期号>.json` 会原样输出。
- **`title` / `pubDate` 不在数据里**：由期号推导，多存一份就多一处能和 URL 对不上的地方。
- **改字段：** 先改 `schemas/report.schema.json`，再改 `content.config.ts` 的 Zod，然后：
  - `scripts/daily/build.py` 的 `build_report()`（骨架输出）；
  - `scripts/daily/apply.py` 的 `new_report()` / `_merge_people()`（合并时的兜底形状）；
  - `DailyLayout.astro` 与 `src/lib/daily.ts` 的 `plainText()`（两处都要展示新字段）。
- **没有 `draft` 字段**：草稿留在 `out/`，进 `data/daily/` 就是已发布。位置本身就是状态。

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
| `astro check` 失败 | 多半是 `dailyReports` 的 Zod 与某份 `report.json` 不符（如 `description` 超过 50 字）。**目录名不是 `YYMMDDHH` 会在 `build` 阶段抛错**，报错信息里带期号 |
| 改了摘要但线上没变 | 忘了 `publish`：站点读 `data/daily/`，不读 `out/`。这是 M4 之前最常踩的坑 |
| 构建说「data/daily 里没有任何 report.json」 | `glob` 的 base 指错了，或 `data/daily/` 被清空。这条是硬失败——日报是每天自动发的，空了就是链路断了 |
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

### 2.8 金文件：怎么换基准期（一条命令）

`npm run check:daily` 除了核对三种出口，还会拿一期的「正文纯文本」和快照逐字比对，
用来保证「改数据源 / 改渲染之后，读者看到的字一个没变」。

基准期**不写在代码里**，在 `tests/golden/current.json`：

```json
{ "id": "26102522", "captured_at": "2026-10-26T12:11:38+00:00" }
```

换基准就一条命令（`--id` 省略时自动取 `data/daily/` 里最新的一期）：

```bash
npm run golden:daily:switch            # 换成最新一期
npm run golden:daily:switch -- --id 26102322
```

它做两件事：从 `dist` 重抓一份 `tests/golden/daily-<期号>.txt`，再把 `current.json` 指过去。
旧快照保留不删——切回去是免费的，删了就得重新 build 才能抓。

**什么时候该换**：改版式（新增区块、调整顺序）且确认是有意的；或者要修改某一期的内容。
**什么时候不该换**：金文件红了但你不知道为什么红——那说明有东西变了，先查清楚。

### 2.9 可能的改进（非必须）

1. 给 `daily_digest.py` 加 `--source x` 过滤，避免以后混入 RSS/YouTube 数据。
2. 把"步骤 2 填摘要"也脚本化，进一步减少手动步骤（权衡见 §2.6）。
3. 给 `daily.sh` 增加自动 `git add/commit/push`（目前只打印命令，避免误提交）。
4. `counts.items` 在迁移的七期里是 0（原始条目库已清）。只有 `26102522` 的真值还能从
   `out/26102522.generate.json` 里读回来（342 条），其余六期补不了——要么接受，要么在
   JSON 出口里加一句说明。
5. `report.json` 的 `categories` / `insights` 两个字段现在是空的（分类出稿还没启用），
   页面整节不渲染。这是给 M4 之后留的口子，不是 bug。

---

## 三、一句话速查

```
每天：
  1) git -C X-rss-workspace/X-Reader pull        # 拿 CI 抓的数据
  2) python scripts/daily_digest.py --items-dir X-rss-workspace/X-Reader/data/items
     （期号自动取当前 JST 小时；补旧的可加 --at "2026-10-24 21:00"）
  3) python scripts/daily_digest.py prompt --issue <期号> --flat
     让 WorkBuddy 读 out/<期号>/prompts/all.md，把回答写成 out/<期号>/answer/all.json
     （summary ≤50 字 / works / highlights / interactions / people[].summary，每条带 sources）
     python scripts/daily_digest.py apply --issue <期号> --answer out/<期号>/answer/all.json
  4) python scripts/daily_digest.py confirm --issue <期号>   # 定稿（会再判一次卷）
     python scripts/daily_digest.py publish --issue <期号>   # 搬到 data/daily/
  5) python scripts/push_site.py -m "daily: <期号>" --path data/daily/

期号：YYMMDDHH（JST）。2026-10-31 22:00 → 26103122 → /daily/26103122/
存档：/daily/（按月分组） 订阅：/daily/rss.xml
出口：/daily/<期号>.json（正本逐字节相同） · /daily/<期号>.txt（纯文本）
判卷：python scripts/daily_digest.py audit --issue <期号> [--published]
```

### 为什么同一天可以有多期

期号带小时，所以「上午抓一次、晚上补一次」是两个文件、两个网址，互不覆盖。
归档列表按天**不合并**，一行一期，时间用等宽数字对齐，扫一眼就知道某天出了几期。
这也意味着重复运行 `daily_digest.py` 不会毁掉旧稿——除非显式 `--force`。
