# 报告索引 · README/reports

本目录保留 **5 份按站点板块整理的现行摘要 + 1 份继续维护的名单 + 1 份缺口对比表 + 1 份强化方案 + 2 份实施/目标计划（审查稿）**（`galgame-directors-list-1-1.html`、`galgame-brand-history-missing-accounts.html`、`galgame-daily-weekly-enhancement-2026-11-19.html`、`galgame-daily-weekly-enhancement-plan.md`、`galplus-weekly-goal-plan.md`）。一次性原始报告已移入 [`_archive-2026-11/`](_archive-2026-11/)（没有删除），摘要里的「原始报告」表给出逐份路径与留存理由。

## 按板块读

| 文件 | 对应站点板块 | 什么时候读 |
| --- | --- | --- |
| [`01-site-overview.md`](01-site-overview.md) | 全局（仓库、部署、git、待办） | 想知道「这仓库现在什么状态、接下来做什么」 |
| [`02-home-and-notes.md`](02-home-and-notes.md) | `/`、`/me/`、`/morelinks/`、`/blog/` | 想改首页/名片/链接库，或判断笔记页要不要加功能 |
| [`03-daily.md`](03-daily.md) | `/daily/`（双版日报） | 动日报前：名单、语言、转发、长图、分句出处 |
| [`04-weekly.md`](04-weekly.md) | `/weekly/`（含月报规划） | 动周报前：口径、分类、业界动向、方案沿革 |
| [`05-pipeline-crawl-daily-weekly.md`](05-pipeline-crawl-daily-weekly.md) | 抓取 → 日报 → 周报 全链路 | 想知道「一条推文经过哪些文件、在哪一步被砍、谁写谁读」 |

## 现行口径在哪

摘要会过期。以下才是**真源**，数字和裁决以它们为准：

- 项目怎么跑 → `README.md` / `README/project.md`
- 日报怎么运营 → `docs/daily-report-guide.md`
- 周报契约与排查 → `docs/weekly-report.md` / `weekly/rules.json`
- 待办与决定 → `docs/backlog.md`
- 名单正本 → `src/config/daily-roster.json`、`src/config/daily-roster-galgame.json`
- Galgame 人工筛选名单（继续维护）→ [`galgame-directors-list-1-1.html`](galgame-directors-list-1-1.html)
- Galgame 名单缺口对比 → [`galgame-brand-history-missing-accounts.html`](galgame-brand-history-missing-accounts.html)：四份人员名单里有、但 11-13 品牌全历史报告里没有的账号
- Galgame 日报／周报强化方案 → [`galgame-daily-weekly-enhancement-2026-11-19.html`](galgame-daily-weekly-enhancement-2026-11-19.html)：以名单 1-1 为底座，日报互动做厚（创作者进抓取 + 预计算互提候选 + 四类判据）、周报业界动态上线（三处 rules 开关 + A/B/C/D 信源分级），另附七个其它方向
- 上述方案的可执行版（审查稿）→ [`galgame-daily-weekly-enhancement-plan.md`](galgame-daily-weekly-enhancement-plan.md)：按批次拆分动作、闸门与回退，复核了 11-20 仓库漂移，并给出首批 20 个创作者 handle；尚未实施
- Gplus 日报／周报目标计划（2026-11-22 修订）→ [`galplus-weekly-goal-plan.md`](galplus-weekly-goal-plan.md)：以「业界事件 + 人/组织交互」为定位，名单 1-1 全集 403 个 X 号为抓取与分析范围，独立 `Gplus_XXX` 期号；11.19–21 三期日报测试稿已出稿并推送，周报暂缓

## 约定

1. 摘要按**站点板块**分，不按时间分；同一板块的多轮报告合成一份，原始件进归档。
2. 报告里的数字都带日期。**不要在这里写会被下个月推翻的页数/用例数。**
3. 新增一次性调查产物直接写进 `_archive-2026-11/`，只在对应板块摘要里加一行索引。
4. 被代码或文档引用的文件（如 `daily-language-repair-2026-11-06.json`）移动时，必须同步改引用方路径——本次已全部改完。

## 变更记录

- 2026-11-08：首轮归档，周报 v1–v5 等移入 `archive/reports/`。
- 2026-11-17 上午：17 份一次性报告（55 MB）移入 `_archive-2026-11/`；主目录降到 ~1 MB。
- 2026-11-17 中午：剩下 22 份按板块合并为 5 份摘要，原始件全部移入 `_archive-2026-11/`。详见 [`01-site-overview.md`](01-site-overview.md) 的「整理沿革」。
- 2026-11-17 晚上：`galgame-directors-list-1-1-2026-11-13.html` 重命名并移回本目录为 `galgame-directors-list-1-1.html`，后续继续筛，暂不归档。
- 2026-11-17 晚上：新增 `galgame-brand-history-missing-accounts.html`，列出四份 Galgame 人员名单相对 11-13 品牌全历史报告的缺失账号。
- 2026-11-19：曾生成 `galgame-scenario-writers-2016-2026.html`（近十年剧本作者调查），同日按用户要求删除，成果并入 1-1 的剧本表。
- 2026-11-19：新增 `galgame-daily-weekly-enhancement-2026-11-19.html`，基于名单 1-1 的日报互动／周报业界动态强化方案（含其它方向建议与实施顺序）。
- 2026-11-20：新增 `galgame-daily-weekly-enhancement-plan.md`（审查稿），把方案拆成可回退批次，标明联系方式项已上线、只做验收。
- 2026-11-22：新增 `galplus-weekly-goal-plan.md`（审查稿），定义 Galplus 的定位、第三条抓取线、独立期号与 P0–P4 阶段；同日按用户裁决改为日报先行（`Gplus_XXX`），完成 11.19–21 三期测试稿并上线 `/gplus/`，周报保留为目标未实施。

归档目录清单：[`_archive-2026-11/README.md`](_archive-2026-11/README.md)。
