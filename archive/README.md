# archive/

放**已经不参与构建、不参与生产、但还有查阅价值**的东西。这里的一切都可以随时删，删之前只需要确认一件事：没有文档或脚本还在引用它。

建立于 2026-11-08。整理依据：`README/reports/workspace-status-2026-11-08.md` §3 与 `weekly-structure-and-p0-review-2026-11-08.html` §6。

---

## scripts/

| 路径 | 原用途 | 为什么留 |
| --- | --- | --- |
| `daily1/render.mjs`（43 KB） | 长图第 1 轮实验（2026-11-02）：18 套模板配色重排，HTML + Edge 截图 | 正式版是 `scripts/daily-image/render.mjs`。留作视觉方案对照 |
| `daily2/render.mjs`（249 B） | 第 2 轮实验，退化成一行转发 | 只剩历史意义 |
| `out/` | `daily_digest.py` 早期的默认输出目录（`26101822`–`26102222` 六期） | 旧期号格式（带小时）的产物，新管线不会再生成 |
| `daily_repair_sakuraemi.py` | 佐倉江美账号的一次性订正（`--check` / `--apply`），改 22 期正本的 identity 字段 | 已执行完。留作「批量订正怎么做」的范本 |

引用提醒：`docs/daily-image-method.md` 顶部有「路径变更」表，正文里的旧路径按那张表换算。

## reports/

| 路径 | 原用途 | 为什么留 |
| --- | --- | --- |
| `weekly-report-plan-2026-11.html` + `v2`–`v5` | 周报方案 6 轮迭代的过程稿 | **v6 是最终口径**，留在 `README/reports/`；v1–v5 只作决策痕迹 |
| `og-demo/` | OG / 晨报长图试验：`morning-paper.mjs`、两张样张、Noto 子集字体 | 长图已定稿到 `scripts/daily-image/render.mjs`。`NotoSub-*.ttf` 是**子集**，只含样例那几个字，正文会大面积空白——别拿它当正文字体 |

## asr-project/

`ASR project/` 的 4 个 HTML + 两份 md（`j.md` / `jn.md` 内容相同）。2026-10-21 的语音识别方案与站点集成规划，未入库、未纳入站点。

## audio-translate/

`tools/audio-translate/` 的源码与转写结果（2026-11-08 归档）。

- **保留了**：`asr.py` / `mt.py` / `pipeline.py` / `seg.py` / `slice_audio.py` / `srtio.py` / `check_subs.py` / `README.md`，以及 `out/`、`samples/`、`tests/`、`results/`（4 份 ASR 与翻译 JSON）。共约 177 KB。
- **删掉了**：`work/` 7.8 GB —— Qwen3 gguf 模型（3.5 GB）、ct2 模型（4.4 GB）、音频中间件与日志。模型可重新下载，音频是另一个项目的素材。
- 这个工具**与站点无关**，不属于本站的生产链。要跑起来得重新下模型。
