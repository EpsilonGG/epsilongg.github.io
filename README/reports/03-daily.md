# 03 · 日报

> 对应板块：`/daily/`（声优版 `YYMMDD` + Galgame 版 `YYMMDD-g`）
> 摘要日期：2026-11-17 · 原始报告存 `_archive-2026-11/`，未删除

## 板块现状（截至 2026-11-16）

- 最新两期 `261115` / `261115-g` 已上线，含 Ci-en `.ja.txt`。声优版 395 条 / 102 账号，Galgame 版 115 条 / 43 账号。
- 名单：声优版 248 号、Galgame 版 188 号，B 站 63 个 active 账号（独立配置）。名单正本在 `src/config/daily-roster.json` 与 `daily-roster-galgame.json`。
- 自动化：每天 23:15 抓取 → **声优 → Galgame → Gplus** 串行出三期（2026-11-23 起三期都在同一条自动化里，取消原来的 5 分钟等待），每期 confirm → publish → 长图 → **立刻各自推送**；已于 11-16 迁到 WorkBuddy（ID `2dd4cc0c…`）。运营流程见 `docs/daily-report-guide.md`，Gplus 的链路见 `README/reports/galplus-weekly-goal-plan.md` §1.5。

## 名单是怎么攒出来的（三份候选池调查的合并结论）

日报现在的名单是**多轮增量筛出来**的，原始调查留着是为了回答「为什么是这些账号」：

- **第一版 Galgame 名单**（10-28）：シナリオ 7 / 原画 14 / 导演 1 / 信息号 2，后被第二轮取代。
- **第二轮 · 信息号 + 厂商侧个人号**（10-29）：实查 182 个 handle，建议收录 27、排除 29、13 个「重试才活」。结论是**信息号能用（13 个，有人在替读者筛选），厂商侧个人号质量差一档（14 个，作者偶尔发推不算信源）**。这就是 P2-18 那批存量的出处。
- **同人音声社团池**（10-25）：从 swsem 1,450 个社团按「近三年作品数 > 5」筛出 344 家，116 家拿到 X 账号；252 家的 cast 已在初代声优名单里。由此决定按社团分类前先要解决「同一条推文算声优还是算社团」，否则重复计数。
- **厂商名单只读视图**（10-27）：174 条 `category: manufacturer`，由 `scripts/build_manufacturer_roster.py` 从 JSON 生成，改名单要改 JSON 再重跑。
- **在册总表**（11-07）：两版合计 433 条全部在用、未入册候选 18 条；由 `scripts/build_roster_overview.py` 生成。

## 文案与出稿的几次口径修正

- **语言修复**（11-06）：曾有一批文案漂成日文，逐条修复记录存 JSON；`scripts/daily_repair_language.py` 把它当对照表读，**只有文案字符串在表里**。已修完，留作证据。
- **转发条目怎么落地**（10-25 实测 26102522）：名单外 66 个 handle 全是名单内成员的转发，转发者 100% 可读。比的是「放在哪一栏、以谁的名义说」：方案 A 只归名（信息最全但重度转发者那行会变清单），方案 B 另起行（后来实际采用 `dedupe.py` 的 `identity_key` 处理）。2026-11-16 又做了 B 站去重，实现「一个账号一行」。
- **token 成本**（10-26）：一期约 5.2 万 token 的构成与压缩空间。后来改走「出题」路线，成本结构已变，数字只作历史参考。

## 图片与视频稿（M5 / M6）

- **M5 长图已落地**：当时比了四条路线，最小可用路径是 4 个包不是 8 个；做法是 Playwright 渲染 → sharp 转 WebP，见 `docs/daily-image-method.md`。
- **M6 视频稿未做**：三条路线，产物是五份文本；唯一没定的参数是时长。选型比较、代价与顺序见原始报告，**开工前先读**。
- 已决定不做：OG 带字版（satori）。

## 分句出处 → 周报取料（M0–M4）

- 里程碑规划 `daily-clause-source-weekly-material-plan`（v2）定的链路：日报分句级出处 → `out/clauses/**` → 周报取料。M0–M4 已落地。
- M0 只读样张 `m0-clause-sample`（11-05）演示「日报分句 → 周报原材料」，机制已实现，样张留作证据。
- `daily-weekly-monthly-redesign`（11-05）比了四条三报架构路线，选的是 **S0 维持现路线**。
- 待补：`works[]` 的 432 条没有 `sources`，将来从 `out/clauses/**` 反补；§13.6 事件级跨期聚合（契约已写、代码未落）。

## 当前维护（不在归档）

- `galgame-directors-list-1-1.html` — 名单 1-1：导演／剧本／画师汇总（附录 1–5，现 28／34／119 人），后续继续人工补人；由 `out/_tmp/galgame_staff/list_1_1.py` 生成并覆盖。
- `galgame-brand-history-missing-accounts.html` — 四份 Galgame 人员名单相对 11-13 品牌全历史报告的缺失账号（1,475 条，已排除报告内已有账号，并剔除声优／音乐板块）；由 `out/_tmp/galgame_staff/build_missing_vs_brand_history.py` 生成。

## 原始报告（都在 `_archive-2026-11/`）

| 原始报告 | 内容 | 引用方 / 状态 |
| --- | --- | --- |
| `daily-roster-2026-10.html` | 在册 433 条总表（11-07 生成） | `scripts/build_roster_overview.py` 产出目标，改名单重跑即覆盖 |
| `galgame-accounts-2026-10.html` | 第二轮信息号 + 厂商侧个人号 | P2-18 出处；`scripts/build_roster_overview.py` 生成页引用 |
| `dlsite-circle-roster.html` | 344 家社团候选池 | `scripts/build_roster_overview.py` 生成页引用 |
| `manufacturer-roster.html` | 厂商名单 174 条只读视图 | `scripts/build_manufacturer_roster.py` 产出目标 |
| ~~`galgame-roster.html`~~ | 第一版 Galgame 名单 | 2026-11-17 已删除；29 个账号（24 定稿＋5 泛媒体）移入名单 1-1 附录 2 |
| `galgame-brand-history-staff-2026-11-13.html` | 品牌全历史作品 × 四类人员单子 | 保留在归档；表二 27 人／表三 30 人／表四 109 人＋人工补入 10 人（佑真 @2yuuma8 等）移入名单 1-1 附录 3／4／5，报告本体继续供人工筛查 |
| `daily-language-repair-2026-11-06.json` | 文案修复逐条记录 | `scripts/daily_repair_language.py` 对照表，已同步路径 |
| `daily-rt-handling.html` | 转发条目方案对比 | `scripts/build_rt_compare.py` 产出目标 |
| `daily-token-cost.html` | token 成本构成 | 历史（成本结构已变） |
| `daily-m5-m6-options.html` | 长图/视频选型 | `docs/daily-report-guide.md`、`docs/daily-image-method.md`、已发布页引用 |
| `daily-clause-source-weekly-material-plan-2026-11-05.md` | 分句出处 + 周报取料规划 v2 | `docs/clause-source-index.md`、`scripts/weekly_material.py` 引用 |
| `daily-weekly-monthly-redesign-2026-11-05.md` | 三报架构重设计 | 决策痕迹（选 S0） |
| `m0-clause-sample-2026-11-05.md` | M0 只读样张 | `docs/clause-source-index.md` 引用 |
