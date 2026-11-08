# 一次性报告索引

这里放的是**某个时间点的证据与方案**，不是现行文档。现行口径看：

- 项目怎么跑 → `README.md` / `README/project.md`
- 日报怎么运营 → `docs/daily-report-guide.md`
- 工作区现在什么状态 → `workspace-status-2026-11-08.md`（**最新的一份现状**）

**读之前先看「状态」列**：标「历史」的只说明当时怎么想，别当现状引用；标「已被取代」的只留作决策痕迹。

---

## 项目现状与进展

| 文件 | 是什么 | 状态 |
| --- | --- | --- |
| `workspace-status-2026-11-08.md` | 整仓现状：架构、抓取自动化、遗留产物、待办（P0/P1/P2） | **现行**（数字以此为准） |
| `project-progress-2026-11-06.md` | M1–M5 周报交付与 D3 审计的进度报告 | 历史（周报未入库那版口径） |
| `project-status-2026-11-05.md` | 完成度快照 + 卡点 A–F + B1–B4 / C1–C4 待裁决项 | 历史（**卡点与裁决项的原始定义在这里**） |
| `project-progress-2026-10.html` | 建站期进展报告 | 历史 |
| `weekly-structure-and-p0-review-2026-11-08.html` | 两套周报目录的分层分析、卡点 D 与 B/C 裁决项的通俗解释、P2-18 存量账号名单 | **现行** |

## 日报

| 文件 | 是什么 | 状态 |
| --- | --- | --- |
| `daily-token-cost.html` | 一期 5.2 万 token 的构成与压缩空间 | 历史（后改走「出题」路线，成本结构已变） |
| `daily-rt-handling.html` | 转发条目怎么落地的方案对比（26102522 实测） | 历史（现按 `dedupe.py` 的 `identity_key` 处理） |
| `daily-m5-m6-options.html` | 长图与视频稿的选型、代价与顺序 | 部分有效（M5 长图已落地，M6 未做） |
| `daily-language-repair-2026-11-06.json` | 文案漂成日文那次修复的逐条记录 | 证据（已修完，保留备查） |
| `category-module-proposal.html` | 笔记页底部「分类」模块可行性 | 未采纳 |

## 周报 / 月报

| 文件 | 是什么 | 状态 |
| --- | --- | --- |
| `weekly-report-plan-v6-2026-11-04.html` | 周报 v6 方案：「全览是工作台，预览版是产品」 | **最终口径**（v1–v5 已归档到 `archive/reports/`） |
| `daily-clause-source-weekly-material-plan-2026-11-05.md` | 分句级出处 + 周报取料的里程碑规划（M0–M4） | 现行（M0–M4 已落地） |
| `daily-weekly-monthly-redesign-2026-11-05.md` | 三报架构重设计：四条路线与取舍 | 现行（选的是 S0 维持现路线） |
| `m0-clause-sample-2026-11-05.md` | M0 只读样张：日报分句 → 周报原材料 | 证据（样张，机制已实现） |

## 名单

| 文件 | 是什么 | 状态 |
| --- | --- | --- |
| `daily-roster-2026-10.html` | 两版在册 433 条的名单总表 | 历史（现 433 条但分版口径变过） |
| `galgame-accounts-2026-10.html` | Galgame 名单第二轮：信息号 + 厂商侧个人号 | 历史（**P2-18 那批存量的出处**） |
| `galgame-roster.html` | Galgame 版第一版名单 | 历史 |
| `dlsite-va-roster.html` | DLsite 同人音声声优榜单与 X 账号 | 历史（候选池来源） |
| `dlsite-circle-roster.html` | 近三年作品数 > 5 的同人音声社团 | 历史（候选池来源） |
| `dlsite-game-brand-roster.html` | 近五年出过商业美少女游戏的厂商 | 历史（候选池来源） |
| `manufacturer-roster.html` | 厂商名单 174 条 | 历史（现 178） |

## 语音 / ASR（与站点无关，已归档代码）

| 文件 | 是什么 | 状态 |
| --- | --- | --- |
| `asr-models-2026-10.html` | 语音识别选型调查（MOSS / Qwen3-ASR 等） | 历史 |
| `asr-private-stack-2026-10.html` | 高敏感场景的本地语音栈（免费 / 离线 / 可审计） | 历史 |

## 其它

| 文件 | 是什么 | 状态 |
| --- | --- | --- |
| `github-repo-scan-2026-10.html` | 五个人的 GitHub 仓库扫描 | 历史 |
| `notes-extensions-2026-10.html` | 笔记拓展功能参考（fuwari / PaperMod / Quartz） | 历史（未采纳） |

---

## 已归档（不在本目录）

2026-11-08 把过程稿与试验残留移到了 `archive/`，这里只留最终口径：

| 原路径 | 现在 |
| --- | --- |
| `weekly-report-plan-2026-11.html` + `v2`–`v5` | `archive/reports/` |
| `og-demo/`（晨报长图试验） | `archive/reports/og-demo/` |
| `ASR project/`（方案性文档） | `archive/asr-project/` |
| `scripts/daily1/`、`scripts/daily2/`、`scripts/out/` | `archive/scripts/` |
| `scripts/daily_repair_sakuraemi.py` | `archive/scripts/` |
| `tools/audio-translate/`（7.8 GB 模型与音频） | 代码与转写结果留在 `archive/audio-translate/`，模型已删 |
| `src/templates/`（174 个 tsx） | `tools/templates/`（gitignored） |

## 加新报告时

1. 文件名带日期：`主题-YYYY-MM-DD.md|html`；同一主题多轮迭代用 `-v2`、`-v3`，**只把最终版留在本目录**。
2. 在对应分组里加一行，写清「是什么」和「状态」。
3. 报告里引用的数字要带日期。**不要在这里写会被下个月推翻的页数/用例数。**
