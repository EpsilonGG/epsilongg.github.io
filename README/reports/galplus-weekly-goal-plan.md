# Gplus 日报／周报 · 目标计划（2026-11-22 修订）

> 状态：**日报测试稿已并入 `/daily/` 入口并推送；周报未做**。  
> 依据：名单 1-1 HTML、Galplus 目标计划初稿、11-22 真实抓取与出稿结果。  
> 一句话定位：**Gplus 不是「另一份 Galgame 周报」，而是以名单 1-1 全集为抓取与分析范围、以业界动向与账号交互为主线的增量日报／周报**；日报期号为 `YYMMDD-gp`，周报期号留作 `Gplus_XXX`（周报未做）。

---

## 0 · 已确认的范围（用户 2026-11-22 裁决）

| 维度      | 裁决                                                                                     |
| ------- | -------------------------------------------------------------------------------------- |
| 抓取范围    | **名单 1-1 全集**：4 张表合并后的 403 个唯一 X 号（剧本/导演/制作人、画师/原画/角色设计/音乐/声优、Galgame 品牌、其他·信息号・泛游戏媒体） |
| 包含      | 所有 Galgame 日报信息号（23 个 `info` 账号 + Moepedia）                                            |
| 不包含     | Galgame 日报「其它」号（唯一不在 1-1 的 `jita_gf`）、任何 B 站账号                                         |
| 分析范围    | 同抓取范围，403 个号全部进入标题、要点与「详细」选材                                                           |
| 标题/看点取材 | 分析范围内**转推次数较多的推文**、**讨论较多的关键字主题**、**单个账号的要点**；所有叙述由真实推文支撑，不凭空生成                        |
| 【详细】呈现  | 同抓取范围：当天有原创推文的所有号，按创作者/品牌/信息号分组                                                        |
| 期号      | 日报 **`YYMMDD-gp`**（如 `261119-gp`），排在 `/daily/` 原入口；周报才用 `Gplus_XXX`；与 `YYMMDD` / `YYMMDD-g` / `vol_XXX` 各自独立 |
| 站点      | 复用现有 `/daily/` 集合、布局、纯文字与 RSS 出口；**没有独立 `/gplus/` 栏目**                              |
| 先做      | 近三天（11.19–21）日报出稿 + 推送测试；**周报先不做**                                                     |
| 格式      | 与现有两份日报（声优版 / Galgame 版）完全相同，只多一种 `-gp` 期号与筛选按钮                                     |

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
- 页面标题由期号派生：`X 日报 · 2026-11-19 Gplus` 等三期；副标题见各期 `description`。

### 1.4 站点接入（用户 2026-11-22 修正：不要独立栏目）

- **不新建集合、不新建页面**：Gplus 正本落在 `data/daily/261119-gp/` 等目录，沿用 `dailyReports` 的 glob（`*/report.json`）与同一份 Zod schema。
- 期号正则在 `content.config.ts` / `schemas/report.schema.json` / `scripts/daily/issue.py` / `src/lib/daily.ts` 四处同步扩出 `YYMMDD-gp`；`DailyKind` 增加 `gplus`，归档筛选按钮加 `Gplus`。
- 显示名查 `src/lib/roster.ts`：名单 1-1 作为**兜底**并入（已有 handle 不改），新增 `creator` / `brand` 两个栏目 id；`info` 沿用 Galgame 版栏目。
- `/daily/`、`/daily/<id>.txt`、`/daily/<id>.json`、`/daily/rss.xml` 四个出口自动覆盖三期，无需新路由。
- 保护集按要求改动并登记 `tests/daily-protection-waivers.json`（batch `gplus-daily-entry-2026-11-22`）；取数脚本 `scripts/daily/` 与判卷脚本未改。

---

## 2 · 目的（不变部分）

1. 现有日报的正本只覆盖 203 个号；名单 1-1 里 201 个创作者/剧本/画师号从未进自动出稿。
2. 现有周报以作品/品牌为一级维度，装不下「同一周期里厂商—信息号—创作者—从业者之间的交互」。
3. Gplus 的抓取与分析都用全集，因此能同时看到「品牌宣布了什么」和「谁在转发、讨论、补充」，这正是原来两份日报都做不到的。
4. 多开一条抓取线，避免把 403 个号塞进现有 202 号抓取线导致单条 job 过长。

---

## 3 · 实现方式

### 3.1 名单与抓取

|   |   |   |
| - | - | - |

- `src/config/gplus-roster.json`：403 个号，字段 `handle / name / group / section / tier / role / brand / tags / last30 / last`；`group` ∈ `creator|brand|info`。这是唯一可写正本。
- X-Reader 仓另开 `update-gplus.yml` + `config/config.galplus.yaml`（`data-galplus`），`accounts.galplus.yaml` 由 roster 生成；**本次测试用站点仓的 `scripts/gplus_fetch.py` 直连 Nitter 完成**，尚未在 X-Reader 仓落 workflow。两条路都要保证 403 号、独立 data_dir、独立 concurrency group。
- 本机必须显式 `--proxy http://127.0.0.1:7897`；默认代理（65312）打不开 Nitter，直连超时。CI 上直连可用。
- RSS 路由单号 20 条上限，403 号一次约 1.5 分钟（14 并发）；`html` 路由在本机返回 403，故引用/回复元数据目前拿不到，统计的「转推」来自 RSS 的 `RT by @…:` 文本前缀。

### 3.2 出稿与闸门

- `scripts/gplus_slice.py` 按 JST 日切片、保留 40 天；`out/gplus/digest/` 是规则层工作台（RT 聚集、关键词频次、逐号原文），不进正本。
- `scripts/gplus_publish.py` 检查：草稿期号格式、`status=confirmed`、每条来源能在 `data/xreader/gplus/` 解析到真实推文、`people[].handle` 在 403 名单内、叙述里没有 `@handle`、`works` 为空；发布时按 `window.start` 转成 `YYMMDD-gp`，补上 Zod 默认字段后写进 `data/daily/`。
- 站点出口只读 `data/daily/`（含三期 `-gp` 正本）；`out/gplus/` 与 `data/xreader/gplus/` 不进 Astro 构建，但后者要提交，供闸门校验来源。

### 3.3 与既有日报／周报的关系

- 日报的取数与判卷代码（`scripts/daily/`、`data/daily/` 的既有期号）完全只读；只扩了期号正则与版式支持的几处。
- 周报（`vol_XXX`）**仍未开始**：`weekly/rules.json`、`data/weekly/` 一个字节都没改。
- 后续做 Gplus 周报时才启用 `Gplus_XXX` 期号；它可只读引用 `-gp` 日报正本做去重与聚合。

---

## 4 · 开展方案

| 阶段        | 状态        | 目标                                       | 通过闸门                               |
| --------- | --------- | ---------------------------------------- | ---------------------------------- |
| P0 范围裁定   | 完成        | 403 号全集、排除 B 站与 `jita_gf`、`YYMMDD-gp`/`Gplus_XXX` 分工 | 用户裁决                    |
| P1 抓取     | 完成        | 403/403 号抓到 7,880 条；切出 3 天               | 目标日有数据；来源 key 可解析                  |
| P2 三期日报出稿 | 完成        | 草稿 Gplus_001/002/003 → 正本 261119/120/121-gp，逐条挂原文 | `gplus_publish.py --check-only` 全绿 |
| P3 站点接入   | 完成 | 并入 `/daily/`：期号正则、筛选按钮、名单兜底             | `npm run build` 通过；55 期出口齐全            |
| P4 推送测试   | 完成 | 站点仓 commit + push，公开 API 核 SHA           | 远端 HEAD 一致                         |
| P4b 入口修正  | 完成 | 撤掉独立 `/gplus/`；703 项单测 + `check:daily` + `links` 全绿 | 三期落在 `/daily/2611{19,20,21}-gp/` |
| P5 周报     | **未开始**   | 以 Gplus 日报正本为料，业界事件与交互聚合                 | 另行裁决                               |

---

## 5 · 关键命令

```bash
python scripts/gplus_fetch.py --concurrency 14 --proxy http://127.0.0.1:7897 --out out/gplus/raw
python scripts/gplus_slice.py --raw out/gplus/raw --keep 40
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

| 风险                    | 对策                                                       |
| --------------------- | -------------------------------------------------------- |
| 抓取号里很多当天不发言，详细栏看起来「空」 | 26%–38% 是真实覆盖；出稿只覆盖有原创推文的号，不补空行                          |
| RSS 拿不到引用/回复元数据，交互栏偏薄 | 当前交互只认 RSS 文本里的 RT 链；要更厚必须在 X-Reader 仓开 html-first 线（未做） |
| 与既有日报重复               | Gplus 叙述走「业界/交互」口径，`works` 恒空；双版日报不动                     |
| 期号与日报混淆               | 日报统一 `YYMMDD`/`-g`/`-gp`，用 `DailyKind` 区分；周报才用 `Gplus_XXX` |
| 推送卷进无关改动              | 严格 `--path` 白名单；推送后公开 API 核 SHA                          |



---

## 7 · 下一步（待裁决）

- [ ] 三期测试稿的标题与取舍是否符合「业界」定位？不符合就备份后移走 `data/daily/2611{19,20,21}-gp/` 再重发（不要 `--force`）。
- [ ] 是否在归档筛选里长期保留 `Gplus` 按钮？（目前已加）
- [ ] 是否开 X-Reader 第三条抓取线，用 html-first 拿引用/回复，把「账号互动」做厚？
- [ ] Gplus 周报何时开始？是否接受 `Gplus_XXX` 独立序号（日报不再用它）？
