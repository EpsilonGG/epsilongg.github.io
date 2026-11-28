# Gplus 日报／周报 · 目标计划（2026-11-22 修订）

> 状态：**日报（`YYMMDD-gp`）已定稿并上线**——栏目结构（今日看点 / 总结 / 长图 / 详细）、显示名、名义分条、点名与长图口径都按 2026-11-22 的裁决落地，之后只改内容不改结构；**周报（`Gplus_XXX`）未做**。  
> 依据：名单 1-1 HTML、Galplus 目标计划初稿、11-22 真实抓取与出稿结果。  
> 一句话定位：**Gplus 不是「另一份 Galgame 周报」，而是以名单 1-1 全集为抓取与分析范围、以业界动向与账号交互为主线的增量日报／周报**；日报期号为 `YYMMDD-gp`，周报期号留作 `Gplus_XXX`（周报未做）。

---

## 0 · 已确认的范围（用户 2026-11-22 裁决）

| 维度      | 裁决                                                                                                           |
| ------- | ------------------------------------------------------------------------------------------------------------ |
| 抓取范围    | **名单 1-1 全集**：4 张表合并后的 403 个唯一 X 号（剧本/导演/制作人、画师/原画/角色设计/音乐/声优、Galgame 品牌、其他·信息号・泛游戏媒体）                       |
| 包含      | 所有 Galgame 日报信息号（23 个 `info` 账号 + Moepedia）                                                                  |
| 不包含     | Galgame 日报「其它」号（唯一不在 1-1 的 `jita_gf`）、任何 B 站账号                                                               |
| 分析范围    | 同抓取范围，403 个号全部进入标题、要点与「详细」选材                                                                                 |
| 标题/看点取材 | 分析范围内**转推次数较多的推文**、**讨论较多的关键字主题**、**单个账号的要点**；所有叙述由真实推文支撑，不凭空生成                                              |
| 【详细】呈现  | 同抓取范围：当天有原创推文的所有号，按创作者/品牌/信息号分组                                                                              |
| 期号      | 日报 **`YYMMDD-gp`**（如 `261119-gp`），排在 `/daily/` 原入口；周报才用 `Gplus_XXX`；与 `YYMMDD` / `YYMMDD-g` / `vol_XXX` 各自独立 |
| 站点      | 复用现有 `/daily/` 集合、布局、纯文字与 RSS 出口；**没有独立 `/gplus/` 栏目**                                                       |
| 先做      | 近三天（11.19–21）日报出稿 + 推送测试；**周报先不做**                                                                           |
| 格式      | 与现有两份日报（声优版 / Galgame 版）完全相同，只多一种 `-gp` 期号与筛选按钮                                                              |

---

## 1 · 11.19–21 日报测试（已完成）

### 1.1 实际执行链路

```
src/config/gplus-roster.json           名单 1-1 全集 403 个 X 号（正本，新增）
        │  scripts/gplus_fetch.py
        ▼  Nitter RSS，经本机 7897 代理，14 并发；CI 上直连
out/gplus/raw/<handle>.json           工作区原始抓取（gitignore）
        │  scripts/gplus_slice.py
        ▼  按 JST 自然日切片 + 40 天滚动保留
data/xreader/gplus/2026-11-{19,20,21}.jsonl
        │  out/gplus/digest/*.md       规则层摘要（RT 聚集、关键词、逐号原文）
        ▼  逐期出稿（LLM 根据摘要写中文叙述，每条挂来源 id）
out/gplus/reports/Gplus_00{1,2,3}.json
        │  scripts/gplus_publish.py    来源/名单/期号/格式闸门；转成 YYMMDD-gp
        ▼
data/daily/2611{19,20,21}-gp/report.json
        │  原 dailyReports 集合 + DailyLayout + /daily/ 出口
        ▼
线上 /daily/261119-gp/、261120-gp/、261121-gp/（含 .txt / .json / RSS）
```

### 1.2 三重抓取覆盖（实测）

| JST 日 | 抓到推文 | 有原创推文的账号 | 占 403 号比例 |
| ----- | ---: | -------: | --------: |
| 11-19 |  247 |      105 |       26% |
| 11-20 |  526 |      154 |       38% |
| 11-21 |  411 |      118 |       29% |

403 个号里很多本来就不每天发推，所以 26%–38% 是正常覆盖，不是抓取失败。原始抓取 403/403 号全部成功，收到 7,880 条推文。

### 1.3 出稿口径（与另两份日报一致）

- `report.json` 字段与日报**完全相同**，含 `categories` 与 `counts.late` / `counts.skipped_duplicate` 默认值（否则 `check:daily` 会因 JSON 出口非逐字节相同而红）。
- `works` 恒为空：Gplus 只写业界动向与账号要点，不做「作品动态」列表。
- 每条 highlight / insight / interaction 与「详细」每行都带 `x:<id>` 来源；`-` 版纯文字出口把来源转成 `[原文](https://x.com/i/web/status/<id>)`。
- 「详细」里写名单显示名，不写 `@handle`；叙述文本里禁止出现句柄，由 publish 闸门机械拦截。
- **「互动」与「洞察」不限条数**（2026-11-22 用户裁决，2026-11-26 扩到三期通用）：这两栏是对当日素材的归纳，条数由证据决定——有几条站得住的交叉互动就写几条，有几条跨账号观察就写几条，**上不封顶、下不设下限**（确实没有就输出空数组，页面整段不渲染）。判断标准只有「每条都能挂到真实来源 id」，不再为了凑数或控篇幅增删。`highlights`（今日看点）同样不限条数（2026-11-26 用户裁决，出稿不再设任何条数上限）；编排上仍把最能一屏读完的放在前面。
- **显示名只写主名**（2026-11-22 用户裁决）：详细栏不写罗马字，除非名字本身就是全英文（`Go-1`、`SMEE` 这类照写）。名单 1-1 的 `<span class="romaji">` 是读音/别名，不进显示名；`go-1` 这种原名全小写的，取别名里的正式写法 `Go-1`。
- **全年龄 / 非全年龄名义分成不同条目**（2026-11-22 用户裁决，同日修正）：不是把两个名义用 `｜` 拼成一条，而是**两条独立条目**——`桜咲 千依` 与 `藤咲 ウサ／琉花 あか` 各自成条，各写当天实际署名的那个名义。落在数据上就是 `people[]` 里同一个 `handle` 可以出现两行、每行带 `name`（不写就退回名单名字）；当天只发了一边，就只留那一条。叙述文本里也按作品署名写单个名义，不写拼起来的复合名。`src/config/gplus-roster.json` 的账号级名字取成人向主名 `藤咲 ウサ／琉花 あか`（handle 本身就是 hujisakiusa），全年龄名义靠条目级 `name` 覆盖；`scripts/daily/audit.py` 只放行「同名 handle 两行且各带 name 且 name 不同」，否则仍判重复。
- **互动 / 洞察必须点名**（同日）：每条都要写清「哪条报道 / 哪部作品 / 谁做的动作」，作品名用《》，一次 1–3 部即可；禁止「多部作品」「某作品」「多家厂商」这类泛称（素材里查得到名字就不许泛写）。
- **「互动」+「洞察」合成一栏「总结」**（2026-11-22 定稿）：页面上不再各占一段 `<h2>`，只保留一个 **总结** 段落，里面把 洞察 / 互动 做成两个**可折叠栏目**（与「详细」的栏目筛选是同一套按钮、同一份 `src/scripts/daily-filter.ts`，两栏默认都亮）；纯文字版同步成 `## 总结` + `### 洞察` / `### 互动`。页面顺序固定：今日看点 → 总结 → 长图 → 详细（详细永远最后）。**Gplus 日报的栏目结构到此定稿**，以后只改内容不改栏目。
- **每期出竖版长图**（同日）：`node scripts/gplus-image/render.mjs <期号> --final` 输出 `public/images/gplus/<期号>.webp`，内容只有 导语（不写「标题」栏目名）/ 洞察 / 互动（即「总结」那段的两个子栏），由 `DailyLayout` 插在「详细」栏之前；详细栏本身不进图。
- **出图模板模式**（同日追加）：出图脚本照搬声优日报的 BASE + DRAFTS 八套模板（`--only=01,08` 出对照稿到 `pic/gplus-image/`，终版固定 `08 rail-12x`），木色底 / 竖轨 / 双栏卡片 / q92 WebP 与声优日报一致；版式细节见 `docs/daily-image-method.md` §10。
- 页面标题由期号派生：`X 日报 · 2026-11-19 Gplus` 等三期；副标题见各期 `description`。

### 1.4 站点接入（用户 2026-11-22 修正：不要独立栏目）

- **不新建集合、不新建页面**：Gplus 正本落在 `data/daily/261119-gp/` 等目录，沿用 `dailyReports` 的 glob（`*/report.json`）与同一份 Zod schema。
- 期号正则在 `content.config.ts` / `schemas/report.schema.json` / `scripts/daily/issue.py` / `src/lib/daily.ts` 四处同步扩出 `YYMMDD-gp`；`DailyKind` 增加 `gplus`，归档筛选按钮加 `Gplus`。
- 显示名查 `src/lib/roster.ts`：名单 1-1 作为**兜底**并入（已有 handle 不改），新增 `creator` / `brand` 两个栏目 id；`info` 沿用 Galgame 版栏目。
- `/daily/`、`/daily/<id>.txt`、`/daily/<id>.json`、`/daily/rss.xml` 四个出口自动覆盖三期，无需新路由。
- **正文段序（2026-11-22 定稿）**：今日看点 → **总结**（洞察 / 互动两个可折叠栏目）→ 长图 → **详细**，`详细` 固定为最后一栏。改动落在 `src/layouts/DailyLayout.astro` + `src/scripts/daily-filter.ts`（按组遍历）+ `src/styles/components.css` 的 `.daily-summary`；声优版与 Galgame 版仍是「互动」「洞察」两段，不被这条影响。
- 保护集按要求改动并登记 `tests/daily-protection-waivers.json`（batch `gplus-daily-entry-2026-11-22`）；取数脚本 `scripts/daily/` 与判卷脚本未改。

### 1.5 定时任务（2026-11-23 用户裁决：并进 23:15 自动化；同日同步玩家号回复常规模式）

- **一个自动化跑三期**：WorkBuddy 自动化 `2dd4cc0c-7725-4819-85db-f45d4a704e9e`（`FREQ=DAILY;BYHOUR=23;BYMINUTE=15`）现在按 **声优 → Galgame → Gplus** 串行跑完三期。
- **11.22 那期即常规模板**：2026-11-23 把 `gplus_replies.py` 的玩家号本人回复抓取写进自动化第 3.1 步（清缓存 → `gplus_fetch.py` → `gplus_replies.py` → `gplus_slice.py` → `gplus_digest.py`），出稿口径照已发布的 `Gplus_004.json`（11.22）。回复抓取失败只报告、不阻塞 RSS 主线。`out/gplus/reports/` 是 gitignored 工作台，跨运行可能不在，按样板字段新建即可。
- **每天开抓前必须清缓存**：两个抓取脚本是「文件存在＝缓存」，昨天的 JSON 留着会让全号报 cached、切片无当天数据、digest 退 2。清的是 `out/gplus/raw/`、`out/gplus/replies/`、`out/gplus/thread_replies/` 三处的 `*.json`，不碰 data/ 正本、reports 与 digest。
- **必须显式传代理**（2026-11-24 事故）：`gplus_fetch.py` / `gplus_replies.py` 都加 `--proxy http://127.0.0.1:7897`。自动探测当时拿一个死掉的 `nitter.jaydenha.uk` 当探针，误判成「无代理」→ 405 号全走直连、每号 3 端点 ×2 次 ×20s 超时，抓了 64 分钟、372 个 raw 全 error，当晚无 Gplus 期。修法：`pick_proxy()` 改探可用实例、`ENDPOINTS` 把 `nitter.cf` 提到首位、前 24 个全失败即熔断（`summary.json:aborted=true`）；自动化命令仍显式传 `--proxy` 兜底。
- **实例清单复核（2026-11-25）**：经 7897 实测 `<base>/<handle>/rss` 与 `/<handle>` HTML profile——可用并写进两个抓取脚本的 `ENDPOINTS`：`nitter.cf`（主）、`nitter.gq`、`xitter.gq`、`teapawt.org`（后三个为新增，真实号 RSS/HTML 都 200、1.4–3.6s，20 条 RSS / 15 个 timeline-item）；`nitter.meowing.monster` 9s 且偶发 404/429，只在 RSS 保留末位。不收录：`nitter.jaydenha.uk`（死）、`nitter.mie.foundation`（真实号 429）、`xnologin.com` / `nitter.xitter.cc` / `nitter.tiekoetter.com`（Anubis「not a bot」页）、`goyimx.com`（HTML 418、慢）。三个新实例同属 Teapawt 系，是主机级冗余、不是独立上游；主实例失效时仍要核对 digest 的 `last=` 与条数。
- **顺序**：声优先提取、先出稿，Galgame 其次，Gplus 最后；`daily_prepare`／`daily_digest` 只服务前两期。
- **转发口径（2026-11-25 用户裁决，三期通用）**：题面标 `repost` / `转发自 @xxx` / digest `RT @xxx:` 的条目是转发，写 highlights / works / interactions / people 必须写「A 转发了 B 的消息」，不能把被转内容记成 A 的原创。反面教材：261124 把 mirai_chiroru 转的『Cinnamon☆JewelryBox』公告写成「大山チロル精选集开订」。数据层 `Item.from_xreader()` 兜底识别 Nitter inline RT（`author_name` 形如 `RT @orig (by @owner)`），`PROMPT_VERSION` 升 7；Gplus digest 新增 `## Reposts` 段逐条列 `[id] -> @原作者`。
- **不再有固定等待**：原来抓取完成后那条 `sleep 300` 已删掉，数据落地（退出码 0）就开工；抓取失败仍按 23:40 补抓一次。
- **各自推送**：每期 `confirm → publish → 长图 → push_site.py` 一条龙，推完再开下一期；不再攒到最后一起推。Gplus 的 push 带 `--path data/daily/ --path data/xreader/gplus/ --path public/images/gplus/`。
- **Gplus 的取数改成可复现脚本**：新增 `scripts/gplus_digest.py`，从 `data/xreader/gplus/<JST 日期>.jsonl` 生成 `out/gplus/digest/<日期>.md`（`items/accounts/originals` + RT 集群 + 关键词词频 + 按账号分组的原文），最后一行打印 `last=HH:MM JST` 供覆盖闸门判断（距 24:00 超 2 小时即重抓一次，仍不全就跳过这一期）。此前这三份 digest 是手工生成的，定时任务里不能这么干。
- Gplus 出稿仍是「写 `out/gplus/reports/Gplus_NNN.json` → `gplus_publish.py` 闸门 → 写 `data/daily/YYMMDD-gp/`」。

---

## 2 · 目的（不变部分）

1. 现有日报的正本只覆盖 203 个号；名单 1-1 里 201 个创作者/剧本/画师号从未进自动出稿。
2. 现有周报以作品/品牌为一级维度，装不下「同一周期里厂商—信息号—创作者—从业者之间的交互」。
3. Gplus 的抓取与分析都用全集，因此能同时看到「品牌宣布了什么」和「谁在转发、讨论、补充」，这正是原来两份日报都做不到的。
4. 多开一条抓取线，避免把 403 个号塞进现有 202 号抓取线导致单条 job 过长。

---

## 3 · 实现方式

### 3.1 名单与抓取

- `src/config/gplus-roster.json`：406 个号（2026-11-25 补入 `randall_kznr` / `KulVario0`；2026-11-29 用户要求补入个人号 `melu_mechie`／芽留メチエ，group=info、role=个人号），字段 `handle / name / group / section / tier / role / brand / tags / last30 / last`；`group` ∈ `creator|brand|info`。另有可选布尔字段 `reply_scope`（2026-11-23 起）：只标玩家／评论总结向的 12 个号，与 `group` 无关，供回复抓取用。这是唯一可写正本。
- X-Reader 仓另开 `update-gplus.yml` + `config/config.galplus.yaml`（`data-galplus`），`accounts.galplus.yaml` 由 roster 生成；**本次测试用站点仓的 `scripts/gplus_fetch.py` 直连 Nitter 完成**，尚未在 X-Reader 仓落 workflow。两条路都要保证 403 号、独立 data_dir、独立 concurrency group。
- 本机必须显式 `--proxy http://127.0.0.1:7897`；默认代理（65312）打不开 Nitter，直连超时。CI 上直连可用。
- RSS 路由单号 20 条上限，403 号一次约 1.5 分钟（14 并发）；统计的「转推」来自 RSS 的 `RT by @…:` 文本前缀。
- **回复抓取（2026-11-23 起）**：`gplus_fetch.py` 的 RSS 出口拿不到任何回复（`is_reply` 硬编码 false），但 X-Reader 仓已有 `parsers/nitter_html.py`，能读 `div.replying-to`；本机 `nitter.jaydenha.uk` 的 HTML 403/429、`nitter.meowing.monster` 是 Anubis 验证页，而 `nitter.cf` 实测 200（profile 与 status 页都可用）。因此新增 `scripts/gplus_replies.py`：
  - **账号范围（用户裁决）**：只抓 `reply_scope: true` 的 12 个号——`youtan0309`、`cloud668`、`aikouka23`、`masanlive`、`hiro_in`、`seiya_saiga`、`akibablog`、`AKOUtw`、`Nooksite`、`erogeAreAlive`、`randall_kznr`（Randall，FAKKU 英文编辑／设计）、`KulVario0`（Vario，ErogeAreAlive 运营／推理游戏评论）。日本官方媒体／商店号（famitsu、dengeki、DLsite 等）不抓，它们的回复多是广告与抽奖灌水。
  - **内容范围（用户裁决）**：只收**这 12 个号本人发出的回复**，不收旁人在它们推文下的评论。实现上是 profile HTML 里带 `replying-to` 的 timeline item（`route=html`），加上 status 页里作者属于 reply_scope 的条目（`route=status-html` / `parent_tweet_id` / `parent_author`）；后者覆盖「账号在自己的评论区里回别人」的情况。旁人评论由 `scope_replies()` 过滤掉，缓存里的旧评论每次运行都会重新过滤并从磁盘删除（`prune_cache`），不会因名单收缩而残留。
  - Nitter status 页没有 `replying-to` 标记，日期只到分钟、正文空白会被压掉，所以这类条目**只新增、不覆盖**已有 RSS 项。
  - 限制：profile 只给最新约 20 条，回复若不在当前窗口就抓不到；不是完整评论归档。status 页可能夹带多层回复，parent 一律记所请求的那条推。每号最多开 `--per-account`（默认 3）条原创推的 status 页。

### 3.2 出稿与闸门

- `scripts/gplus_slice.py` 按 JST 日切片、保留 40 天，并把 `out/gplus/replies/`（本人回复）与 `out/gplus/thread_replies/`（自己评论区里的本人回复）合进同一天文件；保留窗口锚定**已有切片的最新日**，不因 raw 里的老推或当天零星推新建/挤掉日片；已有条目逐字节保留，`route=html` 的同 id 项替换 RSS 项，`route=status-html` 只新增。只用 `--raw out/gplus/raw-empty` 可以先合回复、不碰 raw。`out/gplus/digest/` 是规则层工作台（RT 聚集、关键词频次、逐号原文），不进正本。
- `scripts/gplus_publish.py` 检查：草稿期号格式、`status=confirmed`、每条来源能在 `data/xreader/gplus/` 解析到真实推文、`people[].handle` 在名单内（现 405 号）、叙述里没有 `@handle`、`works` 为空；发布时按 `window.start` 转成 `YYMMDD-gp`，补上 Zod 默认字段后写进 `data/daily/`。
- 站点出口只读 `data/daily/`（含三期 `-gp` 正本）；`out/gplus/` 与 `data/xreader/gplus/` 不进 Astro 构建，但后者要提交，供闸门校验来源。

### 3.3 与既有日报／周报的关系

- 日报的取数与判卷代码（`scripts/daily/`、`data/daily/` 的既有期号）完全只读；只扩了期号正则与版式支持的几处。
- 周报（`vol_XXX`）**仍未开始**：`weekly/rules.json`、`data/weekly/` 一个字节都没改。
- 后续做 Gplus 周报时才启用 `Gplus_XXX` 期号；它可只读引用 `-gp` 日报正本做去重与聚合。

---

## 4 · 开展方案

| 阶段        | 状态      | 目标                                                   | 通过闸门                               |
| --------- | ------- | ---------------------------------------------------- | ---------------------------------- |
| P0 范围裁定   | 完成      | 403 号全集、排除 B 站与 `jita_gf`、`YYMMDD-gp`/`Gplus_XXX` 分工 | 用户裁决                               |
| P1 抓取     | 完成      | 403/403 号抓到 7,880 条；切出 3 天                           | 目标日有数据；来源 key 可解析                  |
| P2 三期日报出稿 | 完成      | 草稿 Gplus_001/002/003 → 正本 261119/120/121-gp，逐条挂原文    | `gplus_publish.py --check-only` 全绿 |
| P3 站点接入   | 完成      | 并入 `/daily/`：期号正则、筛选按钮、名单兜底                          | `npm run build` 通过；55 期出口齐全        |
| P4 推送测试   | 完成      | 站点仓 commit + push，公开 API 核 SHA                       | 远端 HEAD 一致                         |
| P4b 入口修正  | 完成      | 撤掉独立 `/gplus/`；703 项单测 + `check:daily` + `links` 全绿  | 三期落在 `/daily/2611{19,20,21}-gp/`   |
| P5 周报     | **未开始** | 以 Gplus 日报正本为料，业界事件与交互聚合                             | 另行裁决                               |

---

## 5 · 关键命令

```bash
python scripts/gplus_fetch.py --concurrency 14 --proxy http://127.0.0.1:7897 --out out/gplus/raw
python scripts/gplus_replies.py --concurrency 3 --proxy http://127.0.0.1:7897 \
  --raw out/gplus/raw --out out/gplus/replies --threads-dir out/gplus/thread_replies
python scripts/gplus_slice.py --raw out/gplus/raw --keep 40
python scripts/gplus_digest.py --date 2026-11-19   # 写 out/gplus/digest/2026-11-19.md，日期省略＝昨天（JST）
python scripts/gplus_publish.py --all --check-only
python scripts/gplus_publish.py --all
export PATH="/c/Program Files/nodejs:$PATH"
npm run build
python scripts/push_site.py -m "gplus: merge 3-day test into daily as YYMMDD-gp" \
  --path src/config/gplus-roster.json \
  --path src/content.config.ts \
  --path src/lib/daily.ts \
  --path src/lib/roster.ts \
  --path src/layouts/DailyLayout.astro \
  --path src/pages/daily/index.astro \
  --path src/pages/daily/rss.xml.ts \
  --path src/pages/gplus/ --path src/lib/gplus.ts --path src/layouts/GplusLayout.astro \
  --path data/gplus/ --path data/daily/261119-gp/ --path data/daily/261120-gp/ --path data/daily/261121-gp/ \
  --path data/xreader/gplus/ \
  --path scripts/gplus_fetch.py --path scripts/gplus_slice.py --path scripts/gplus_publish.py \
  --path scripts/daily/issue.py --path schemas/report.schema.json \
  --path tests/daily-protection-waivers.json \
  --path README/reports/galplus-weekly-goal-plan.md --path README/reports/INDEX.md
```

- 推送一律带 `--path`：工作区常驻大量 README/reports 未提交改动，不带会被卷进同一 commit。
- 本机 node 22 不够，构建前切到系统 node 24（`/c/Program Files/nodejs`）。构建末尾清理 `dist/.prerender/.vite` 可能被沙箱拦一次，不影响产物。
- 没有 `gh`；查 Actions 用 WebFetch 读公开 API `https://api.github.com/repos/EpsilonGG/epsilongg.github.io/actions/runs?per_page=5`。

---

## 6 · 风险与对策

| 风险                    | 对策                                                         |
| --------------------- | ---------------------------------------------------------- |
| 抓取号里很多当天不发言，详细栏看起来「空」 | 26%–38% 是真实覆盖；出稿只覆盖有原创推文的号，不补空行                            |
| RSS 拿不到引用/回复元数据，交互栏偏薄 | 12 个玩家/评论号走 `gplus_replies.py` 的 Nitter HTML（本人回复，含自己评论区里的回复），其余号仍只有 RSS；要全覆盖得开 X-Reader 第三条 html-first 抓取线 |
| 与既有日报重复               | Gplus 叙述走「业界/交互」口径，`works` 恒空；双版日报不动                       |
| 期号与日报混淆               | 日报统一 `YYMMDD`/`-g`/`-gp`，用 `DailyKind` 区分；周报才用 `Gplus_XXX` |
| 推送卷进无关改动              | 严格 `--path` 白名单；推送后公开 API 核 SHA                            |

---

## 7 · 下一步（待裁决）

- [x] 栏目结构与排期已定稿（2026-11-23）：互动 + 洞察合成「总结」，并进 23:15 自动化，顺序 声优 → Galgame → Gplus，各自推送、无固定等待。
- [ ] 是否在归档筛选里长期保留 `Gplus` 按钮？（目前已加）
- [x] 玩家号回复已落地（2026-11-23）：profile HTML 拿本人回复 + status 页拿自己评论区里的本人回复，只保留 reply_scope 10 号作者，已合进 `data/xreader/gplus/`（28 条）。
- [ ] 是否把 HTML 回复抓取扩到更多玩家号，或在 X-Reader 仓开第三条 html-first 抓取线？
- [ ] Gplus 周报何时开始？是否接受 `Gplus_XXX` 独立序号（日报不再用它）？
