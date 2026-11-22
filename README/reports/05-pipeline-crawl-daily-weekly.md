# 05 · 抓取 → 日报 → 周报 · 全流程与文件分工

> 写作目的：说清「一条推文 / 一条 B 站动态」从被抓到、到变成站点上一个字，中间经过哪些文件、谁写谁读、在哪里被砍。
> 精细度到**单文件**；只有「不解释就理解不了为什么这么拆」的地方才讲代码。
> 全部路径相对仓库根 `c:\Users\lenovo\Desktop\github page work`。
> 时点：2026-11-21（含当日三条新裁决：事实源回到原推、图片只收 X 原推、每条挂原文链接）。

---

## 0. 一张图看完全程

```
[独立仓 EpsilonGG/X-Reader]  update.yml / update-galgame.yml → nitter → data/items/x.jsonl
        │
        │ git pull（.xreader/）
        ├── scripts/sync_xreader_accounts.py ──► accounts.yaml / accounts.galgame.yaml（回给抓取侧）
        │
        ├── scripts/xreader_slice.py ──► data/xreader/{voice,galgame}/<JST日>.jsonl（40 天滚存，进 git）
        │
        └── scripts/bilibili_daily.py fetch ──► data/bilibili/galgame/<JST日>.jsonl（正本）
                                                └─镜像─► .xreader/data-galgame/items/bilibili.jsonl
        │
        ▼
[日报] daily_prepare.py → daily build → prompt →（LLM/人写 answer）→ apply → confirm
        │  out/<期号>/report.json（工作台，gitignore）
        │ daily publish（只发定稿）
        ▼
data/daily/<期号>/report.json（发布正本，进 git）
        │
        ├──────────────────────────┬──────────────────────────────┐
        ▼                          ▼                              ▼
src/lib/daily.ts          out/clauses/<期号>.json          weekly/out/corpus.json
src/pages/daily/*         （原文全文，gitignore）                  │
（B站旁路 bilibili-daily.ts）                                       ▼
                                                weekly build（7 步筛选 + 归栏 + 出稿）
                                                           │
                                  weekly/out/{draft.md, filter.html, image-preview-data.json}
                                                           │ backfill-media + 再 build
                                                           ▼
                                            python -m weekly publish（脱敏）
                                                           │
                                                           ▼
                                            data/weekly/vol_XXX/report.json（进 git）
                                                           │
                                            src/lib/weekly.ts → src/pages/weekly/*
                                                           ▼
                                            astro build → dist/ → GitHub Pages
```

一句话概括三段的分工：

| 段 | 谁做判断 | 产物形态 | 是否上线 |
| --- | --- | --- | --- |
| 抓取 | 脚本（确定性） | JSONL 原始条目 | 否 |
| 日报 | 脚本组装 + **一次 LLM 定稿**（人判卷） | `report.json` 结构化散文 | 是 |
| 周报 | 纯规则（**零 LLM**），只读日报与原文 | `report.json` + Markdown/HTML | 是 |

---

## 1. 磁盘分区：哪些是原料、哪些是工作台、哪些是正本

理解这套管线，先记住三块区域的性质，后面每个文件都属于其中之一。

| 区域 | 进 git | 写它的东西 | 读它的东西 | 性质 |
| --- | --- | --- | --- | --- |
| `data/xreader/` | ✅ | `xreader_slice.py` | `daily build` | 抓取原料，按日不可变 |
| `data/bilibili/` | ✅ | `bilibili_daily.py fetch` | 日报 B 站旁路、周报 | 第二个数据源的正本 |
| `out/` | ❌（`.gitignore`） | 日报各子命令 | 人 + LLM + 周报桥 | 工作台，可删可重建 |
| `data/daily/` | ✅ | `daily publish` | Astro、周报、分句索引 | **日报发布正本** |
| `out/clauses/` | ❌ | `daily_clauses.py sync` | 周报 corpus / pipeline | 原文全文索引（旁路） |
| `data/period-sources/` | ✅（只有链接与元数据） | `weekly_material.py freeze` | 月报/追溯 | 选中来源快照 |
| `weekly/out/` | ❌（`.gitignore`） | `weekly build` | 人（筛选页）、`publish` | **周报工作台** |
| `data/weekly/` | ✅ | `weekly publish` | `src/lib/weekly.ts` | **周报发布正本** |
| `dist/` | ❌ | `astro build` | GitHub Pages | 产物 |

两条由此而来的硬约束：

1. **站点代码永远只读正本**。`src/` 里没有任何一行 `read` 到 `weekly/out/` 或 `out/`；`scripts/check_weekly_publish.py` 把这个当闸门扫。
2. **工作台可以随便删**。`out/` 与 `weekly/out/` 都是派生物；删掉只损失「这次没发」，不会损失历史。

---

## 2. 抓取段

### 2.1 名单：三份正本，三种角色

| 文件 | 覆盖 | 谁读 |
| --- | --- | --- |
| `src/config/daily-roster.json` | 声优 + 音声社团（声优版） | 声优版日报、站点名单页 |
| `src/config/daily-roster-galgame.json` | 游戏制造商 + 信息号（Galgame 版） | Galgame 版日报、**周报身份层** |
| `src/config/daily-bilibili-galgame.json` | B 站监控号（`bili_<uid>`） | `bilibili_daily.py`、日报 B 站旁路 |

**`scripts/sync_xreader_accounts.py`** 把名单翻成 X-Reader 认识的 `accounts.yaml` / `accounts.galgame.yaml`。它的关键动作是**按 `source` 过滤**：只有缺省或 `source=x` 的账号才写进 YAML，`bili_*` 一律排除——否则 X-Reader 会拿一串数字 UID 去 Nitter 查一个不存在的 X 账号，抓取整轮变慢且报错。

这一步的存在意义是「两侧名单不同步」的两个隐性故障：抓了名单外的人（日报冒出没人认领的推文）、名单里的人没抓（看起来像她当天真没说话）。所以每次改名单都要重跑它。

### 2.2 X 抓取：外部仓 + 本地切片

抓取本体在**独立仓** `EpsilonGG/X-Reader`（两个 workflow：`update.yml` 声优版、`update-galgame.yml` Galgame 版），本仓库只消费它的库。

| 文件 | 作用 | 说明 |
| --- | --- | --- |
| `scripts/trigger_fetch.py` | 按一下立刻抓一轮并等数据落地 | GitHub `schedule` 是 best-effort，实测每次晚 4.2–6.9 小时；`workflow_dispatch` 是立刻创建。`--report` 只看延迟不触发；`--verify-only` 只查本地覆盖到几点 |
| `scripts/xreader_slice.py` | 全量库 → 按 JST 日切片 | 见下 |
| `scripts/daily_prepare.py` | **自动**调切片 | `git pull` 之后顺手刷新，`--no-slice` 关掉 |

`xreader_slice.py` 是本段唯一值得讲代码的地方，因为它决定了两件事：

- **为什么切片**：X-Reader 的库是 append-only 单文件（`x.jsonl` 14 MB、`data-galgame/items/x.jsonl` 5.3 MB），整份提交等于每天存一份全新整文件，一年 7 GB。切一片约 550 KB，一天新增一个不可变小文件。
- **为什么存原始行而不是反序列化再序列化**：字段顺序、浮点写法一变就和正本对不上，白白制造 diff。去重键优先 `identity_key`（`x:<id>`），退回 `item_id`。
- 保留 `KEEP_DAYS = 40`：日报只用昨天，但周报窗口 7 天、月报最长 35 天，所以要留够。
- 退出码 0 = 切完；2 = 抓取侧还没这个库（`data/items` 与 `data-galgame/items` 都不存在）。

产物：`data/xreader/voice/2026-11-21.jsonl`、`data/xreader/galgame/2026-11-21.jsonl`。`data/` 不在 `public/` 里，Astro 不会把它放进 `dist/`，`deploy.yml` 还额外钉了 `paths-ignore: data/xreader/**`。

### 2.3 B 站抓取：把「非 X 数据源」塞进同一条管线

| 文件 | 作用 |
| --- | --- |
| `scripts/bilibili_daily.py fetch` | 抓 `polymer/web-dynamic/v1/feed/space`，落 `data/bilibili/galgame/<JST日>.jsonl` |
| `scripts/bilibili_daily.py sync` | 从正本重建 `.xreader/data-galgame/items/bilibili.jsonl` 镜像 |
| `scripts/bilibili_daily.py check` | 校验名单正本自洽（不读 X 名单） |
| `scripts/bilibili_daily.py overview` | 某天内容概况（Markdown + JSON），排查用 |

它复用了参考实现的三个要点，但用 Python 标准库重写：接口调用形状、`buvid3/buvid4` 匿名引导 + `dm_img_*` 设备指纹、按 id 去重。**匿名请求风控率约 1/2～2/3**，所以默认带 WBI 签名，并保留 16 次重试预算（每次换新 buvid）。

镜像这一步是本段最巧的设计：`daily_prepare.py::items_dir_for()` 优先读 `.xreader/data-galgame/items/`，而 `scan_day()` / `XReaderAdapter` 只认 `*.jsonl` 与 `published_at`——于是 B 站动态会以 `[bilibili:<动态id>]` 的来源键自然出现在 briefing、题面与正文里，**日报管线一行都不用改**。

---

## 3. 日报段

### 3.1 入口与「谁在做决定」

| 入口 | 用途 | 备注 |
| --- | --- | --- |
| `scripts/daily_prepare.py` | 自动化第一步：拉数据 → 校验新鲜度 → 出骨架 | **确定性，不含 LLM** |
| `scripts/daily_digest.py` | 兼容薄壳，转发到 `scripts/daily/cli.py` | 一行逻辑都不写，只为保住旧命令与旧 import |
| `scripts/daily/cli.py` | 真实现（`build/prompt/apply/confirm/audit/publish/migrate/ja/state/version`） | `scripts/daily/__main__.py` 也指向它 |
| `scripts/daily.sh` | 提示式的「一键流程说明」 | 只打印下一步该跑什么，方便手跑 |

`daily_prepare.py` 之所以单独存在，是因为「今天到底有没有数据」必须由脚本回答——交给模型判断，它会在没数据时编出一期看起来正常的日报。它的退出码就是判断结果：

| 码 | 含义 | 该做什么 |
| --- | --- | --- |
| 0 | 骨架已生成 | 继续出题 |
| 2 | 目标日一条都没有 | 抓取没跑或失败，**不要**写这一期 |
| 3 | 抓取仓拉取失败 | 检查网络/凭据 |
| 5 | 只抓到一半（最后一条距 24:00 > 2 小时） | 先 `trigger_fetch.py` 补；确认要出残稿才加 `--allow-partial` |

### 3.2 `daily build` 内部：七个模块各管一件事

数据从 `data/xreader/galgame/<date>.jsonl`（或 `.xreader` 全量库）进来，按顺序过：

| 模块 | 职责 | 关键点 |
| --- | --- | --- |
| `scripts/daily/model.py` | `Item` 数据结构 | 全链路共用一种条目形状 |
| `scripts/daily/issue.py` | 期号规则 `YYMMDD` / `YYMMDD-g` / `-2` / `-g2` | 期号里**没有小时**（JST 24:00 才闭合），发布时刻单独存 `issue.published_at` |
| `scripts/daily/window.py` | 切 JST 窗口、判「迟到 / 未来 / 不确定」 | 窗口外与迟到分开统计，不混进正文 |
| `scripts/daily/roster.py` | 名单查询（类别、显示名、主号/小号/社团号） | 显示名唯一来源，避免叙述里写句柄 |
| `scripts/daily/filter.py` | 准入筛选（纯 RT、名单外、无实质内容…） | 被筛掉的留在 `merged` 里可查，不是静默丢弃 |
| `scripts/daily/dedupe.py` | 同文去重 | 同一轮抓取重复落同一条是常态 |
| `scripts/daily/order.py` | 排序 | 互动数、时间 |
| `scripts/daily/state.py` + `data/daily/state.json` | 已见条目记账 | 保证重跑同一期不会重复入选 |
| `scripts/daily/build.py` | 出 briefing + 正本骨架 | **不调模型、不决定写什么** |

产物（三个 + 一个状态）：

```
out/<期号>.briefing.txt     喂给 LLM 的原始事实摘要（含原文与互动数）
out/<期号>.generate.json    分类视图，给人看「哪些进了、哪些被筛」
out/<期号>/report.json      四段全空的骨架
data/daily/state.json       已见键（进 git）
```

`out/<期号>/` 目录本身由 `scripts/daily/paths.py` 统一定义（`prompt/` `answer/` `history/` `cache.json`），不让各模块各写一份路径。

### 3.3 出题 → 答题 → 判卷

| 步骤 | 文件 | 产物 |
| --- | --- | --- |
| 出题 | `scripts/daily/prompt.py` | `out/<期号>/prompt/all.md`（给人贴）+ `all.json`（算指纹） |
| 答题 | 人 / 本地 LLM | `out/<期号>/answer/all.json` |
| 判卷合并 | `scripts/daily/apply.py` + `validate.py` + `schema.py` | 不合格逐条列出；通过才写 `out/<期号>/report.json` |
| 缓存 | `scripts/daily/cache.py` | 同题面同答案不重复付费；`PROMPT_VERSION` 不升会继续用旧题面 |

题面里写四样东西，这是日报的全部内容：

- `summary`：今日看点简报（≤60，页面副标题）
- `works`：作品动态（**一条一个作品**）
- `interactions`：名单内多人互动
- `people[].summary`：每人一句话（空 = 当日无活动，不渲染）

`validate.py` 是「叙述里写显示名、不写句柄」这条规则的执行者；`schema.py` 保证写出去的东西结构合法（`schemas/report.schema.json`）。

### 3.4 定稿、日语版、发布

| 子命令 | 文件 | 动作 |
| --- | --- | --- |
| `confirm` | `scripts/daily/confirm.py` | `status → confirmed`，旧版进 `history/`；定稿后不许再合并，要改先 `reopen` |
| `audit` | `scripts/daily/audit.py` | 对已写好的正本事后判卷：来源能不能对上、人是不是本期的 |
| `ja` | `scripts/daily/ja.py` | Ci-en 日语版 → `report.ja.json`（只有声优版有这条出口） |
| `publish` | `scripts/daily/publish.py` | `out/` → `data/daily/`，三道规矩见下 |
| `migrate` | `scripts/daily/migrate.py` | 一次性把 Markdown 旧档迁成 `report.json` |

`publish.py` 的三道规矩，每一条都对应一次真实事故：

1. **只发定稿**。`status != confirmed` 直接拒绝——草稿进 `data/daily/` 就等于上线，而「上线」必须是人做过的动作。
2. **默认不覆盖**。已发布期号再发要显式 `--force`，否则「补一条摘要」会悄悄改掉可能已被引用的 JSON。
3. **落盘前先过 schema**。字段写错不该等到 `npm run build` 才炸。

### 3.5 日报的站点出口

| 文件 | 角色 |
| --- | --- |
| `src/content.config.ts` | `dailyReports` 集合，`base: './data/daily'`、`pattern: '*/report.json'`，目录名即期号 |
| `src/lib/daily.ts` | 派生 `title` / `pubDate` / `kind` / `seq`（**不写进数据**，少一个字段就少一处能和 URL 对不上的地方） |
| `src/lib/cien.ts` | Ci-en 版文本出口 |
| `src/lib/bilibili-daily.ts` | B 站旁路取数：解析 → 按账号归并 → 超 100 字概括 → 与 `people[]` 概括行去重 |
| `src/pages/daily/[...id].astro` | 详情页（`DailyLayout`） |
| `src/pages/daily/[id].json.ts` | `/daily/<期号>.json`，**与正本逐字节相同** |
| `src/pages/daily/[id].txt.ts` / `[id].ja.txt.ts` | 纯文字版（GFM Markdown，各级标题文字加粗、账号与原文链接齐全）/ Ci-en 粘贴用文本 |
| `src/pages/daily/index.astro` / `rss.xml.ts` | 归档页 / 日报独立 Feed |
| `scripts/check_daily_site.py` | 出口闸门：有一份正本就必须有三份产物、JSON 与正本逐字节相同、主 Feed 里不许混进 `/daily/` |

`data/daily/` 是 content collection，构建时读、**不复制**进 `dist/`——所以 `dist/data/` 从来不存在。

---

## 4. 中间桥：分句级出处索引

这一段是日报与周报之间唯一的连接件，也是最容易被误解的一层。

| 文件 | 作用 |
| --- | --- |
| `scripts/daily_clauses.py sync --all` | 读 `data/daily/<期号>/report.json` + `data/xreader/*/*.jsonl`，切分句、挂来源 → `out/clauses/<期号>.json` |
| `scripts/daily_clauses.py check --all` | 校验索引未过期且自洽（周报 `sync` 前置） |
| `scripts/daily_clauses.py export-links` | 导出 `data/period-sources/backfill-links.json`（只有链接与元数据，进 git） |

它**不参与日报生产**，产物全部落在保护集之外。为什么必须走旁路而不是往 `report.json` 里加字段：

- `tests/test_daily_protection.py` 用 `git diff` 把 `data/daily/`、`schemas/`、`scripts/daily/` 逐字节钉死在 HEAD，还断言 schema 顶层属性集合；
- 日报是唯一每天被判卷过的事实层，周报还在演进，不能让试验改它；
- 「摘要 ≤60 字」放宽也解决不了对齐问题：实测 55.0% 的行「分句数 ≠ 来源数」，因为逗号连接的常常只是同一条推文的补充。

所以这里把**原文全文**留在旁路：`out/clauses/<期号>.json` 里 `source_refs` 形如

```json
{ "x:1988...": { "url": "https://x.com/<handle>/status/1988...", "text": "本推原文……" } }
```

精度只有三档，绝不伪造：`clause`（答案里明确给了 sources）、`row`（继承整行）、`unresolved`。自动对齐试算只有 38.1% 可信，所以**这一层绝不用算法猜分句归哪条推文**。

2026-11-21 起，周报的「作品名 / 新作信号」判定全部改读这里的 `text`——这就是「按原推出稿、token 零增量」的物理基础：原文早就在本地，只是以前没人读。

---

## 5. 周报段

### 5.1 入口

`python -m weekly <子命令>`，实现全在 `weekly/` 包：

| 子命令 | 作用 |
| --- | --- |
| `build [--last-days 7 / --since / --until]` | 重建语料 + 筛选 + 归栏 + 出稿（**不联网**） |
| `backfill-media [--no-preview]` | 方案 C：回填候选源推的图片 URL 到 sidecar（唯一联网步骤） |
| `check` | 守恒 / 隔离 / 版式 / 事实 / 分流 / JS-Python parity |
| `check-site` | 发布正本 / 站点出口 / 内容闸门（CI 也跑） |
| `publish --issue vol_XXX` | 出 `data/weekly/<vol_XXX>/report.json` |
| `apply-decisions` | 把人工 `decisions.json` 落成筛选稿 |
| `drafts` | 出无图 / 有图两版试稿 |

`weekly/cli.py` 的 `cmd_build` 就是全流程主线，八行代码对应八个阶段：

```python
data_set = corpus.build(...)          # ① 语料
data_set = bilibili.attach(...)        # ② B 站第二数据源挂载
write_json(OUT / "corpus.json", ...)
result = pipeline.run(data_set, rules) # ③ 七步筛选 + 归栏
data = render.render_all(result, OUT)  # ④ 出稿（Markdown 为准）
editor.render_html(data, OUT/"filter.html")   # ⑤ 人工筛选台
preview = image_preview.build(rules)   # ⑥ 图片栏目
taxonomy / game_routing.build(rules)   # ⑦ 两张试验预览（独立 HTML）
drafts = draft_export.build(rules)     # ⑧ 正式版 weekly.md / weekly.html
```

### 5.2 语料层 `weekly/corpus.py`

- 读：`data/daily/*-g*/report.json`（Galgame 正本）+ `out/clauses/<issue>.json`
- 写：`weekly/out/corpus.json`
- 不做的事：不写 `data/`、不写 `out/clauses/`、不 publish
- 分句索引缺失的期号仍收正本散文，但标 `prose_only`，**不伪造出处**

产物里三块最常被下游用：`issues`（窗口内期号）、`source_refs`（`x:<id> → {url, text}`）、`daily_rows`（人-句候选）。

### 5.3 B 站挂载 `weekly/bilibili.py`

**不塞进 X 侧语料**——那套四类筛选 / 内容组去重 / 三值归栏有整套守恒断言与历史回测基线，混进一个没有 X handle、没有分句索引的数据源会把证据链全部漂掉。

它只在展示层单独成行，并过三道闸门（2026-11-21 定稿）：

| 闸 | 规则 | 落点 |
| --- | --- | --- |
| ① 过期贩卖 | 写明结束日且**成形时**已过期 → 整条删掉（判据在 `weekly/expiry.py`，X 侧同过这道） | 不进稿 |
| ② 认亲 | 按作品名 / 发布者映射到已有品牌-游戏子集 → 并入该子集，栏目随原组 | 可能进新作 |
| ③ 未认出 | 以 `B站 · <发布者>` 名义统一归入作品动向（作品情报），**一律不进新作** | 作品情报 |

追加口径：`rules.json:bilibili.never_new_publishers = ["HIKARIFIELD", "Galgame批评", "Galgame批評"]`。命中的发布者即使认亲到新作游戏组，也强制留在作品情报（临时口径，理由逐条写在规则文件里）：

| 发布者 | 为什么永不进新作 |
| --- | --- |
| HIKARIFIELD / HIKARI-FIELD | 海外发行、代理方，本身不是作品发布方；它宣布的是「已决定代理」，不是某社的新作发表 |
| Galgame批评 | 第三方周报汇总号。视频（`DYNAMIC_TYPE_AV`）、专栏（`ARTICLE`）、动态（`DRAW`）、转发（`FORWARD`）四类都是汇总稿或转述；一条【Gal周报】会同时提到十几部新作，按作品名认亲必被误提进新作 |

名字按 `_norm_brand()` 归一后比对（去空格 / 连接符 / `.` `_`，小写，剥「公式 / 官方 / official」后缀），所以 `HIKARI-FIELD` 与 `HIKARIFIELD`、`Galgame批评` 与 `Galgame批評` 都命中。

**只拦这个账号自己发的（2026-11-22 用户裁决）**：判定只比对 `publisher`（B 站发布者显示名），**不扫正文关键词**。柚子社official、DLsite、HOOKSOFT公式 这些号转述 HIKARIFIELD 的翻译版 / 多语版消息照常可进新作——正文里的「HIKARIFIELD」只是议题，不是发布者；而且「汉化 / 多语 / 海外版决定」本身就是新作证据（见 5.8）。成稿闸门 `new_section_hits()` 同口径：只看 `B站 · <发布者>` 与行首 `[<发布者>](链接)` 两个结构位，不做整句子串匹配。

**两道闸门，缺一不可**：`build_lines()` 按行把 `column` 压回作品情报，`check` 再逐行断言；但行认亲后会被并进某个游戏组，最终排在哪一栏由组决定。所以 `check` 还会跑 `bilibili.new_section_hits(draft, rules)` —— 直接扫**成稿的「新作」栏**，只在两个结构位（`B站 · <发布者>`、行首 `[<发布者>](链接)`）上认人，不拿整句做子串匹配（「海外版由 HIKARI FIELD 发行」这种正常句不该被判成漏过闸门）。回归见 `tests/test_weekly_bilibili.py` 的 `GateRoutingTests` / `NewSectionGuardTests`。

归并单位是「账号 × 作品小标题」，合并后超 150 字就纯规则概括（分额度取整句 → 骨架相同的合并），不调模型。

### 5.4 筛选层 `weekly/pipeline.py`：七步，顺序不可换

```
① 全量源索引 → ② 四类 + 转发提升 → ③ 原推正文层内容去重（留最新，源索引全留）
→ ④ 栏目强制词 / 生日词 / 过期贩售标注 → ⑤ 非 manufacturer 过筛除池
→ ⑥ 内容驱动三栏归栏（强制词覆盖）→ ⑦ 四层展示结构 + tier_order 排序
```

`account_class` 只进筛选层（准入 / 去重择一 / 走哪道池），**绝不参与 ⑥**。每条记录都带 `verdict` 与 `reason`，这是 `check` 能守恒的前提。

#### 过期贩售：`weekly/expiry.py`（2026-11-22 提到周报级）

口径：**成形时已经结束的贩售消息整条不进报**。原先只做在 B 站行上（`bilibili.attach` 里一段私有正则），X 侧照样留着「后日通贩 11/16 截止」这种已经失效的消息，所以现在抽成独立模块，两侧共用一份：

| 入口 | 谁调 | 判完做什么 |
| --- | --- | --- |
| X 侧 | `pipeline.annotate()` 标注 → `prefilter()` 置 `verdict=drop` | 记录留档（`records.json` + `evidence/prefilter.json`），正文不出现 |
| B 站侧 | `bilibili.attach()` 读正本时直接跳过 | 计入 `stats.bilibili_expired_sales` |
| 成稿闸门 | `weekly check` 逐行扫 `draft.md` | 还能判出过期贩售就红 |

判据只认**写明结束日**的，而且结束日必须与「截止 / 为止 / まで / 至 / 到 / 结束」连在一起、同一句还得带贩售词——正文里到处是发售日、开播日，不能见日期就当期限。支持这几种写法：`11月16日截止`、`到 11/16`、`受注到 12/1`、`到29日`、`12/2日为止`、`到今晚二十四点`。只有「日」的写法按该条自己的发布日补月份。

三种**不删**的情形（都会在证据里写理由）：

1. **没有结束日**：`现正于 Steam 促销热卖中` 这类常驻在售，无法证明已结束，不猜。
2. **结果通报**：`为11月9日截止的活动完成抽奖，已通知中奖者`、日文 `抽選を行い…ご連絡致しました`——期限过了，但这条讲的是结果。
3. **另一句有未来发售**：`预约到11/16截止。另公布新作12月25日发售。` 删掉会连带丢新闻，保留并注明「贩售已过，但另一句有未来发售」。同一句里的「11/27 发售作的特典提醒」不算——那是定语，主体仍是过期特典。

正本里会留 `policy.expired_sales_dropped` 与 `policy.expiry_basis`，后台能看出这期删了几条、按什么基准判的。回归见 `tests/test_weekly_expiry.py`（11 例）。

四个贴身模块：

| 模块 | 职责 |
| --- | --- |
| `weekly/identity.py` | 四类账号（manufacturer / info / creator / other）+ 转发提升 + 品牌/梯队解析；单一真源是 Galgame 名单 |
| `weekly/source_grounding.py` | **原推事实层**：剥 RT 前缀、引用推、裸 URL，取 `『』`/`《》` 作品名；零 LLM / 零联网 |
| `weekly/titles.py` | 题名规范化：中文题名缺失或是原文子串时才补；两边完全不同则保留中文 + `source_conflict` 待核 |
| `weekly/brackets.py` | 书名号归一（`『』`/`《》`/`「」`），纯规则 |

### 5.5 展示层 `weekly/render.py`：一次构建写出一整套文件

`render_all(result, OUT)` 一次写：

| 文件 | 用途 |
| --- | --- |
| `weekly/out/draft.md` | **唯一的正文真源**（Markdown） |
| `weekly/out/draft-selected.md` | 应用人工 `decisions.json` 后的版本 |
| `weekly/out/filter-data.json` | 筛选页数据 |
| `weekly/out/decisions.json` | 人工裁决记录 |
| `weekly/out/material.md` | 素材视图（给人核事实） |
| `weekly/out/records.json` | 每条记录的 verdict/reason 全量 |
| `weekly/out/manifest.json` | 本次构建清单（期号、窗口、计数） |
| `weekly/out/evidence/*.json` | `identity` / `dedupe` / `prefilter` / `annotation` / `title-groups` / `classification` / `rules-snapshot` |

2026-11-21 新增的**每条原文链接**就在这一层：`render.source_links(item)` 读 `item["sources"]`，一条来源挂 `[原文](url)`，多条按序编号 `[原文1](url1) [原文2](url2)`（同 URL 去重）。链接不进正文文句，只挂在行尾，样式是小号灰字。

### 5.6 人工台 `weekly/editor.py` + `weekly/parity.js`

`editor.py` 把 `filter-data.json` 渲染成 `weekly/out/filter.html`：内嵌 JS 的改动台，用来手工切栏目、改句子。它里面的 `buildMarkdown()` 必须与 `render.render_markdown()` **逐字节一致**——否则「在页面上看到的就是要发的」这句话不成立。

这个一致性由一个额外进程保证：`weekly check` 会用 node 跑 `weekly/parity.js`，对同一份数据分别跑 Python 与 JS 的渲染，比对输出。这是全仓唯一「用 JS 验 Python」的地方，改任一侧都必须同步另一侧。

### 5.7 图片：`image_preview.py` + `media_backfill.py`

| 文件 | 作用 |
| --- | --- |
| `weekly/media_backfill.py` | 方案 C：X-Reader 的 nitter RSS 解析器丢了 `<img>`，历史切片 `media[]` 几乎全空。这里对候选源推查一次公开 API，把图片 URL 落成 sidecar（`weekly/out/media-sidecar.json`） |
| `weekly/image_preview.py` | 合并 crawl `media` + sidecar，按梯队判定合格条目，出 `image-preview-data.json` / `image-preview.html` |

两条口径写死在 `rules.json:image_preview`：

- **有图推文不论几张只取第一张**，入口恒为原推 URL + `/photo/1`（`/photo/2` 及以上一律不出现）。
- **只收 X 原推**（`source_scope: "x"`）：键必须是 `x:<id>` 或 URL 命中 `x.com/.../status/`。B 站动态即使认亲并入 X 侧子集，也没有 `/photo/1` 入口，硬拼会出坏链——它只参与文本归栏，不进图片栏目，但仍计入诊断 `non_x_image_tweets_skipped`。

回归：`tests/test_weekly_image_preview.py`（2 例）。

### 5.8 新作判定 `weekly/game_routing.py`（兼两张试验预览）

| 文件 | 产物 | 状态 |
| --- | --- | --- |
| `weekly/taxonomy_preview.py` | 分类预览 HTML（按条目） | 已废弃，仍在跑，只作历史对照 |
| `weekly/game_routing.py` | 按游戏分流预览（哪些游戏组进新作） | **新作判定真源**：`new_work_labels()` 的游戏级标签 |

新作不是「按条目算」的，是「按游戏组算」的：一部游戏被判为新作，它下面所有条目整组上提到第一栏。这是 2026-11-10 之后的核心口径。

判定链条只有一条：`game_signals()` → `new_work_labels()`，出稿分流与分流预览读**同一份**结果（预览若自己另算，就会和初稿打架）。

**信号表（`rules.json:game_routing.signals`）**——命中即算新作证据：

| 信号 | 看什么 |
| --- | --- |
| 体验版 / 装盘 / 预约 / 店铺特典 | 宣发进程类 |
| 定档 / 日期发售 / 临发售 / 版本发售 / 发售日期公布 | 日期类（受下面的「过去日期」闸门约束） |
| 新作公开 / 新作开卖 | 显式新作表述 |
| 新CG公开 | **条件信号**：当期该组还有其它任何消息才算 |
| 本地化决定（2026-11-22） | 汉化 / 中文化 / 多语版 / 海外版 / 翻译版的「决定 / 确定 / 宣布」 |

**三条容易搞错的边界（都是用户裁决，写在这里是为了别再退回去）**：

1. **「汉化决定」算新作**——它说明将要出该语言的发行版本，是即将发行的新版本。但只认「决定 / 确定 / 宣布」这类将来时；`中文版已发售`、`中文版打折促销中` 这种完成时不算（信号正则里没有单独的「发售」动词）。
2. **影片公开不算新作，要交叉确认**——OP 影片 / PV / 开场动画公开本身不是新作证据。麻烦在于它常顺带回顾原作发售日，写法与定档一模一样（`2019年1月25日发售`），旧口径会把一部 2019 年的老作整组提进新作（真实案例：SMEE『向阳＊甜恋 Sugar*Style』）。处理办法是 `rules.json:game_routing.date_signals` + `game_routing.has_past_release_date()`：**同一段文本里写了已经过去的显式年月日，就不认其中的定档类信号**——过去的日期是追述，不是当期定档。只认带年份的 `YYYY年M月D日` / `YYYY/M/D`，光写「1月25日」不猜（跨年边界判不准）。真正的新作即使同时公开影片，也带着未来的发售日、预约或体验版信号，交叉确认照样过。
3. **不得用 `negative` 硬压「影片」**——一句「OP 影片公开，同时定档 12 月 25 日发售」是合法的新作消息，按句压掉会连真信号一起丢。所以走「日期是否过去」这条正交判据，而不是往负向词表里塞「影片」。

回归：`tests/test_weekly_game_routing.py` 的 `RetrospectiveDateAndLocalizationTests`（9 例，含 SMEE 真实案例、未来日期反例、完成时反例、无年份保守放过）。

### 5.9 正式版导出 `weekly/draft_export.py`

只读 `draft.md` + `image-preview-data.json`，只写 `weekly.md` / `weekly.html`：

- `weekly.md` 是**论坛可贴的纯文字版**（2026-11-22 裁决）：GFM Markdown、不插图，只留正本正文；工作台标题 / `>` 版式说明 / `**导语**` / 分隔线 / `publish.disabled_display_columns` 里的栏目全部剥掉。先由共用的 `public_markdown()` 剥净，再由 `forum_markdown()` 给各级标题文字套 `**`（kungal 论坛规则：`# **标题**`，井号后留空格）；剥掉这层加粗后就是 `data/weekly/<期号>/report.json:markdown`。**站点正本不加粗、不重发**；
- `weekly.html` 给每条插一张首图，插图前会先剥掉行尾的来源链接再匹配（`_SOURCE_TAIL` 正则），否则「同一句话 + 链接」匹配不上；
- 来源链接在 HTML 里带 `class="weekly-source"`，样式真源是 `src/styles/weekly.css`（小号、灰色、不换行、hover 下划线）。

### 5.10 发布 `weekly/publish.py`：正文规则与导出层共用

`weekly/out/` 是工作台：有内部版式说明、导语里的「测试窗口」、筛选页、未定稿徽章、全部证据文件。`data/weekly/<期号>/report.json` 是发布正本：只带对外该有的东西（元信息 / 导语 / 栏目统计 / 干净的正文与 HTML 片段）。

正文脱敏只有一份实现（`draft_export.public_markdown()`）；发布层再跑一次是幂等兜底——即使拿加粗过的 `weekly.md` 当输入，标题外层的 `**` 也会被剥掉，站点正文保持不加粗；然后重写导语、写出 JSON。期号 `vol_XXX` 从这里分配。

期号用 `vol_XXX`（用户指定），与日报的 `YYMMDD-g` 完全无关；「上一期 / 下一期」由已发布期号排序派生，不写进正本。

**同一期重发**：`publish` 目标已存在会直接报错。正确做法是先把 `data/weekly/vol_002/report.json` 备份并移走，再 `--issue vol_002`；**不要用 `--force`**（会另起 `vol_003`，把期号序列弄乱）。

### 5.11 周报的站点出口

| 文件 | 角色 |
| --- | --- |
| `src/lib/weekly.ts` | 直接读 `data/weekly/`（不用 content collection：改 `src/content.config.ts` 要过日报保护集豁免，而周报是「一份正本 → 多种出口」的扁平结构） |
| `src/pages/weekly/[id].astro` | 详情页（`WeeklyLayout` 渲染正本里的 HTML 片段） |
| `src/pages/weekly/[id].json.ts` | `/weekly/<期号>.json` |
| `src/pages/weekly/index.astro` | 归档页 |
| `src/pages/weekly/rss.xml.ts` | 周报独立 Feed |
| `src/styles/weekly.css` | 周报排版（含 `.weekly-source`） |
| `scripts/check_weekly_publish.py` | 发布正本 / 出口齐备 / `src/` 不许反向引用 `weekly/out/` |
| `scripts/check_weekly_site.py` | 站点侧闸门（历史 `vol_001` 因目录名不是新式期号会报 `目录名不是合法期号`，属已知遗留） |

---

## 6. 上线

| 文件 | 作用 |
| --- | --- |
| `.github/workflows/deploy.yml` | push 到 main 触发：`npm ci` → `npm run check` → `test:md` → `test:cien` → `build` → `links` → `check:daily` → `check:weekly` → `npm test` → upload `dist` → deploy Pages |
| `scripts/push_site.py` | 本地唯一推送口：**必须带 `--path`**，否则工作区里几十处未提交的 `README/reports` 改动会被卷进同一个 commit |

`deploy.yml` 里 `paths-ignore: data/xreader/**` 的意思是「如果**全部**改动都命中这条，就跳过部署」——日报发布同时改了 `data/daily/`，那次照常部署。

---

## 7. 命令速查

### 7.1 抓取（每天，JST 00:15 前后）

```bash
python scripts/trigger_fetch.py                 # 两版都抓，等落地，再 git pull
python scripts/bilibili_daily.py fetch          # B 站动态
python scripts/bilibili_daily.py sync           # 重建 .xreader 镜像
python scripts/sync_xreader_accounts.py --out .xreader/accounts.yaml   # 改名单后必跑
```

### 7.2 日报（Galgame 版）

```bash
python scripts/daily_prepare.py --kind galgame            # 拉数据 + 出骨架（退出码即判断）
python scripts/daily_digest.py prompt --issue 261120-g --flat
#   → out/261120-g/prompt/all.md；写好后存 out/261120-g/answer/all.json
python scripts/daily_digest.py apply --issue 261120-g --answer out/261120-g/answer/all.json
python scripts/daily_digest.py confirm --issue 261120-g  # 定稿
python scripts/daily_digest.py publish --issue 261120-g  # → data/daily/
python scripts/push_site.py -m "daily: 261120-g" --path data/daily/
```

声优版把 `-g` 去掉，并在 `confirm` 前多一条 `ja`。

### 7.3 周报（每周六）

```bash
python scripts/daily_clauses.py sync --all       # ① 刷新原文索引
python scripts/daily_clauses.py check --all      # ② 校验
python -m weekly build --last-days 7             # ③ 首轮构建（此时还没有图）
python -m weekly backfill-media --no-preview     # ④ 回填图片 URL（唯一联网）
python -m weekly build --last-days 7             # ⑤ 再构建一次，图才进正文
python -m weekly check                           # ⑥ 守恒 / 版式 / 事实 / 分流 / parity
python -m weekly publish --issue vol_003         # ⑦ 出正本
python -m weekly check-site                      # ⑧ 正本与出口闸门
python scripts/push_site.py -m "weekly: vol_003" \
  --path data/weekly/ --path weekly/ --path src/styles/weekly.css --path tests/
```

④ 必须在 ③ 之后：sidecar 回填读本轮 `corpus.json` / `filter-data.json` 取候选，所以「先建一次、回填、再建一次」是固定顺序，不是冗余。

---

## 8. 文件责任总表（谁写 / 谁读）

| 文件 | 写 | 读 |
| --- | --- | --- |
| `src/config/daily-roster*.json` | 人 | `roster.py`、`identity.py`、`sync_xreader_accounts.py` |
| `src/config/daily-bilibili-galgame.json` | 人 | `bilibili_daily.py`、`src/lib/bilibili-daily.ts` |
| `.xreader/accounts*.yaml` | `sync_xreader_accounts.py` | X-Reader 仓 |
| `data/xreader/{voice,galgame}/*.jsonl` | `xreader_slice.py` | `daily/build.py`、`daily_clauses.py` |
| `data/bilibili/galgame/*.jsonl` | `bilibili_daily.py fetch` | `bilibili-daily.ts`、`weekly/bilibili.py` |
| `out/<期号>.briefing.txt` | `daily build` | 人 / LLM |
| `out/<期号>/prompt/all.md` | `daily prompt` | 人 / LLM |
| `out/<期号>/answer/all.json` | 人 / LLM | `daily apply` |
| `out/<期号>/report.json` | `daily apply` / `confirm` | `daily publish` |
| `data/daily/<期号>/report.json` | `daily publish` | Astro 集合、`daily_clauses`、`weekly/corpus` |
| `out/clauses/<期号>.json` | `daily_clauses sync` | `weekly/corpus`、`weekly/pipeline` |
| `weekly/out/corpus.json` | `weekly build` | `pipeline`、`render`、`image_preview` |
| `weekly/out/draft.md` | `render` | `draft_export` |
| `weekly/out/filter.html` | `editor` | 人 |
| `weekly/out/media-sidecar.json` | `backfill-media` | `image_preview` |
| `weekly/out/image-preview-data.json` | `image_preview` | `draft_export`、`publish` |
| `weekly/out/weekly.md` / `.html` | `draft_export` | 人（终稿预览） |
| `data/weekly/vol_XXX/report.json` | `weekly publish` | `src/lib/weekly.ts` |
| `dist/` | `astro build` | GitHub Pages |

---

## 9. 红线（改之前先看这一节）

1. **`data/daily/`、`schemas/`、`scripts/daily/` 是保护集**，逐字节钉在 HEAD。改它们要过 `tests/test_daily_protection.py`，并登记 `tests/daily-protection-waivers.json`。
2. **周报不许读 `weekly/out/`**。站点侧只认 `data/weekly/`，`check_weekly_publish.py` 会扫。
3. **周报零 LLM**。事实判定一律走 `source_grounding.py`（读 `source_refs[].text`），不新增模型调用、不联网重抓。
4. **图片只收 X 原推**，每推首图 `/photo/1`。B 站动态不进图片栏目。
5. **每条小条目必挂 `[原文](url)`**（多来源编号）。`weekly check` 会逐条断言，缺一条就红。
6. **过期贩售必须删**：写明结束日、且成形时已结束的贩售消息整条不进报（`weekly/expiry.py`，X 侧与 B 站共用）。没有结束日的常驻在售不猜；结果通报、另一句有未来发售的保留并写理由。`weekly check` 逐行扫成稿兜底。
7. **B 站三道闸门 + never-new 名单**：过期贩卖删、认出品牌并入子集、认不出一律作品情报；`HIKARIFIELD` 与 `Galgame批评`（视频 / 专栏 / 动态 / 转发）永不出现在新作——行级压栏 + 成稿层扫描双保险。**只拦这两个号自己发的**，别家转述不拦。
8. **新作判定：影片不算、汉化算**。OP 影片 / PV 公开不构成新作证据；同一段文本里写了已过去的显式年月日，定档类信号不予采信（`date_signals`）。「汉化 / 多语 / 海外版 / 翻译版的**决定**」算新作，完成时的「已发售」不算。
9. **`publish` 不覆盖**。同期重发先移走旧正本；`--force` 会另起新期号。
10. **推送必须带 `--path`**。`push_site.py` 不带路径会把工作区其它改动卷进同一 commit。
11. **parity 双向维护**：`weekly/editor.py` 的 `buildMarkdown()` 与 `weekly/render.py` 的 `render_markdown()` 必须逐字节一致，改一侧必须改另一侧。
12. **`PROMPT_VERSION` 改了才换题面**。不升版本，`cache.py` 会继续命中旧题面，看起来「改了没生效」。

---

## 10. 排障速查

| 现象 | 先看 | 通常原因 |
| --- | --- | --- |
| 日报没出这一期 | `daily_prepare.py` 退出码 | 2 = 没数据；5 = 只抓到一半 |
| 日报里某人「当日无活动」 | `.xreader/accounts*.yaml` | 名单没同步到抓取侧 |
| 周报正文没图 | 是否漏了「回填后**再 build 一次**」 | 图片是第二次 build 才插进 `draft.md` |
| 周报图片 404 / 坏链 | `image-preview-data.json` 里的 `tweet_key` | 混进 `bilibili:*`（应被 `is_x_source` 拦掉） |
| 周报作品名错得离谱 | `out/clauses/<期号>.json` 的 `source_refs[].text` | 索引过期或缺失（`prose_only`），跑 `daily_clauses sync` |
| 周报缺原文链接 | `draft.md` 行尾 | `item["sources"]` 为空（B 站行本来只挂发布者链接） |
| 新作栏冒出 HIKARI / Galgame批评 | `weekly check` 报「新作栏混进了 never-new 发布者」 | 行被认亲并进新作游戏组；先看 `rules.json:bilibili.never_new_publishers` 是否登记了这个写法 |
| 老作的 OP 影片被提进新作 | `game_routing.game_signals()` 命中了哪个信号 | 影片消息里写了原作过去的发售日；确认 `rules.json:game_routing.date_signals` 含该信号名（`2019年1月25日发售` 这类应被 `has_past_release_date()` 拦掉） |
| 汉化 / 多语版消息没进新作 | 该段文本是「决定」还是「已发售」 | 只有决定 / 确定 / 宣布算新作证据；完成时表述不算 |
| 周报里仍有已结束的促销 | `weekly check` 报「初稿仍留有过期贩售」 | 结束日写法没被 `expiry._END_FORMS` 认出来（补一条写法）；或该条是结果通报 / 另一句有未来发售被保留 |
| `weekly check` 报 parity | 两侧 diff | 只改了一侧渲染函数 |
| 推送后线上没变 | Actions run 的 `head_sha` | `paths-ignore` 命中（只改了 `data/xreader/`） |

---

## 附：相关文档

| 文档 | 内容 |
| --- | --- |
| `README/publish-workflow.md` | 文章（非日报/周报）的抓原文 → 落站点 → 推送默认顺序 |
| `docs/daily-report-guide.md` | 日报内容口径（写什么、不写什么） |
| `docs/daily-image-method.md` | 日报配图方法 |
| `docs/clause-source-index.md` | 分句索引的设计与精度口径 |
| `docs/weekly-report.md` | 周报契约与排查（自动化任务的对外说明） |
| `weekly/rules.json` | 周报规则真源（`schema_version 10`），改口径先改这里 |
| `README/reports/03-daily.md` / `04-weekly.md` | 两个板块的现状与沿革 |
