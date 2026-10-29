# 日报构建日志

推进协议见 [`public/docs/dailyrp-projectstatus.html`](../public/docs/dailyrp-projectstatus.html) §9：
一个工作包一条，只记**实际输出**，不写「应该通过」。日期用本机时间。

---

## M1 · 架构与数据协议

**收尾** 2026-10-25 · **状态** 完成 · **范围** 只做协议，不做筛选（去重/增量/排序在 M2）

### 工作包

| 编号 | 产出 | 状态 | 备注 |
| --- | --- | --- | --- |
| M1.1 | `scripts/daily/{__init__,cli,__main__}.py`；`daily_digest.py` 变薄壳 | 完成 | 命令行参数一个没改，`git show HEAD` 对拍逐字节相同 |
| M1.2 | `scripts/daily/model.py` | 完成 | `Item` / `Account` / `Issue` / `Claim` / `Report` / `Engagement`，`to_dict()` 键序固定 |
| M1.3 | `scripts/daily/adapters/{base,xreader,fixture}.py` | 完成 | 三个方法的契约：`name` / `fingerprint()` / `iter_items()`；两个适配器过同一套契约测试 |
| M1.4 | `schemas/{item,report,generation}.schema.json` + `scripts/daily/schema.py` | 完成 | 零依赖校验器，10 个关键字：type / required / enum / minLength / maxLength / pattern / items / minItems / maxItems / properties |
| M1.5 | `scripts/daily/state.py` | 完成 | `load` / `save` / `prune(90)` / `rebuild()`；`seen` 可从 `issues` 重建 |
| M1.6 | `scripts/daily/migrate.py` | 完成 | 读到更高主版本直接 `VersionError`，不猜着读 |
| M1.7 | CLI + `--check-reproducible` | 完成 | 重新从磁盘读一遍再比，不是比内存里同一个列表 |
| M1.8 | `tests/test_daily_model.py`（22）、`tests/test_daily_adapters.py`（7） | 完成 | 新增 29 条；原有 69 条（含日报 9 条）一条未改 |

### 验收（实际输出）

```text
$ python -m unittest discover -s tests
Ran 98 tests in 33.418s
OK
```

```text
$ python scripts/daily_digest.py --items-dir scripts/sample_items \
    --date 2026-10-23 --at "2026-10-23 22:00" --check-reproducible
可复现：2 个文件、8896 字节，两次运行完全相同（26102322）
（退出码 0）
```

```text
$ diff -r oldout newout        # 重构前（git show HEAD:scripts/daily_digest.py）vs 重构后
（无输出 —— briefing 与 md 逐字节相同）
```

```text
$ npm run check
Result (52 files):
- 0 errors
- 0 warnings
- 0 hints

$ npm run build
[build] 13 page(s) built in 12.11s

$ npm run links
[links] 18 个页面 · 489 个站内链接（共 634 处引用） · 跳过 71 处外链 · 全部通过
```

### 遗留问题

- `--check-reproducible` 目前只覆盖 `briefing.txt` 与日报 Markdown。`report.json` 要等 M4 有正本之后再纳入。
- `Item.date()` 仍然按时间戳自带的时区（UTC）取日期——**这是有意保留的**：M1 不改行为，UTC 分桶的修复属于 M2.1。（已在 M2.1 解决）
- 校验器不实现 `$ref`，所以 `report.schema.json` 里的 claim 结构是内联的；以后 claim 字段一多，要么实现 `$ref`，要么改成代码生成。
- 适配器只有 `xreader` 与 `fixture`。新增数据源时必须同时加进 `tests/test_daily_adapters.py` 的契约测试，否则「一个源一个文件」就退化成「一个源一套特例」。

### 下一步

M2.1：`IssueWindow` 按 JST 自然日切窗，修掉 UTC 分桶。验收判据是 10-23 窗口从 26 条变 28 条、账号集合不变。

---

## M2 · 采集、增量与排序

**进度** 2026-10-25 · **状态** M2.1 完成，M2.2–M2.7 未开始

### M2.1 时间窗

| 编号 | 产出 | 状态 | 备注 |
| --- | --- | --- | --- |
| M2.1 | `scripts/daily/window.py`；改 `model.Item.date()`、`cli._select()` | 完成 | 窗口是半开区间 `[当天 00:00, 次日 00:00)`（JST）；`precision: day` 的条目单独落 `Selection.unsure` |
| M2.1 | `tests/test_daily_window.py`（18） | 完成 | 边界、半开区间、精度不足、四个桶互斥且求和等于输入、样例数据验收 |

**根因不是「排序写错了」，是分天写错了。** X-Reader 的时间戳是 UTC，旧代码直接
`dt.date()`，于是「一天」实际是 JST 09:00 → 次日 08:59，边界整体偏 9 小时。
修法是把 `Item.date()` 改成「先换算到 JST 再取日期」，窗口判定统一走 `IssueWindow`，
不再有第二处 `dt.date()`。

**精度不足的条目怎么办**：`precision: day` 只知道哪一天、不知道几点，无法判定落在哪个窗口。
判定规则是「日期 = 窗口当天」或「日期 = 窗口前一天」——因为来源要么按 UTC 要么按 JST 写日期，
UTC 写的 D 日最晚能落到 JST 的 D+1 日 00:00–08:59，所以 D+1 不可能进入 D 日窗口。
这类条目不混进 `Selection.items`，CLI 会在 stderr 提示一句、但仍按窗内处理——不静默丢数据。

### 验收（实际输出）

```text
$ python -m unittest discover -s tests
Ran 116 tests in 38.098s
OK
```

```text
$ cd scripts && python -m daily build --items-dir sample_items \
    --date 2026-10-23 --at "2026-10-23 22:00" --out /tmp/dailyout --md-out /tmp/dailyout/26102322.md
Wrote C:\Users\lenovo\AppData\Local\Temp\dailyout\26102322.briefing.txt (28 items)
Wrote Markdown -> C:\Users\lenovo\AppData\Local\Temp\dailyout\26102322.md  (期号 26102322，网址 /daily/26102322/)
```

```text
$ cd scripts && python -m daily build --items-dir sample_items \
    --date 2026-10-23 --at "2026-10-23 22:00" --check-reproducible
可复现：2 个文件、9685 字节，两次运行完全相同（26102322）
```

M1 时同一条命令是 8896 字节。差的 789 字节全部来自多出来的 2 条条目，不是回归。

```text
# 按天切分后求和 == 输入总数，且同一条不落进两天
$ python /tmp/probe_days.py
sum: 213 total: 213
cross-day duplicates: {'2113601516565311503': ['2026-10-23', '2026-10-23']}
```

最后那行不是跨天泄漏，是 M2.2 的已知问题：同一条推被两个账号各转一次，
两条记录的 `native_id` 相同，所以都落在 10-23。去重之后它会变成 1 条 + `amplifiers` 长度 2。

闸门第 4 条：10-23 窗口 26 → **28** 条，账号集合不变（仍是 6 个：
`asuparama40` / `mirai_chiroru` / `322yui3` / `suzuka_minase` / `re_re_tsubame` / `yuzuki_momoka`）。

```text
# 同一批数据、相邻四天，两种口径各切一次
$ python /tmp/probe_old.py
2026-10-21 utc 20 jst 16
2026-10-22 utc 40 jst 41
2026-10-23 utc 26 jst 28
2026-10-24 utc 0 jst 3
```

10-24 旧口径是 **0 条**——那 3 条凌晨的推全被算进了 10-23。这就是「数量差 2、集合差 8」
的来源：每天少几条、多几条，互相抵消之后看总数几乎看不出来。

### 遗留问题

- `_select()` 里 `if not day_items: day_items = items` 这个兜底还在：`--date` 一条都对不上时会把**整批数据**当成一天，生成一份覆盖全部历史的日报。M2.3 做五态归类时删掉它，现在先留着（M2.1 只改边界，不改兜底）。（已在 M2.3 删除）
- `Item.date()` 与 `IssueWindow` 是两条通往同一结论的路。`date()` 只用于「数据里最新的一天」这种粗判断，窗口判定必须走 `IssueWindow`——别在新代码里写第三处 `.date()`。
- 没有 `precision: day` 的真实样本，这条分支只有合成用例覆盖。等 RSS 适配器（M2 之后）进来才会有真数据。

### 下一步

M2.2：跨源去重。验收判据是 `2113601516565311503` 跑出来条目数 1、`amplifiers` 长度 2。

---

### M2.2–M2.7 去重、增量、排序、名单、导出

**收尾** 2026-10-25 · **状态** 完成

| 编号 | 产出 | 状态 | 备注 |
| --- | --- | --- | --- |
| M2.2 | `scripts/daily/dedupe.py` | 完成 | 身份键三级：`source+native_id` → 归一化 URL → 正文指纹；重复项不丢，账号并进 `amplifiers` |
| M2.3 | `scripts/daily/incremental.py` | 完成 | 五态 new / duplicate / updated / late / future，`commit()` 一次写账本 |
| M2.4 | `scripts/daily/order.py` | 完成 | items 按 `(published_at, source, native_id)`；accounts 按名单序 |
| M2.5 | `src/config/daily-roster.json` + `scripts/daily/roster.py` | 完成 | 11 个账号全在 `seiyuu`；未知 handle 归 `other` 并在 stderr 告警一行 |
| M2.6 | `scripts/daily/export.py` | 完成 | `out/<期号>.generate.json`：按分类分组 + 互动候选 + 低价值标记 |
| M2.7 | `tests/test_daily_incremental.py`（31） | 完成 | 去重、五态、排序、名单、导出、CLI 一条龙 |

**执行顺序不能换：切窗 → 判态 → 去重 → 排序 → 导出。**
账本按 `key` 记，同一条内容的多条记录必须**各自**判一次。先合并再判态的话，
10-23 那期第二次运行会报 `skipped_duplicate 27` 而不是 28——数字会随去重实现漂移。

**`amplifiers` 的语义定成「所有出现过这条内容的账号，含作者本人」。**
一条原创推去重后长度 1，被两人各转一次长度 2。这样「长度 ≥ 2」本身就是互动线索，
不用再判断谁转了谁。代价是字段名与「只有被转发才叫 amplify」的直觉不符，已在模块文档里写明。

**纯转发的人不进 `people` 表。** 他没有属于自己的条目，但会出现在 `interactions` 里——
「谁帮着扩散」照样写得出来，又不会被当成独立发言。`counts.accounts` 也只数拥有条目的人。

### 验收（实际输出）

```text
$ cd scripts && python -m daily build --items-dir sample_items --date 2026-10-23 \
    --at "2026-10-23 22:00" --out /tmp/s1 --md-out /tmp/s1/a.md --state /tmp/st.json
2026-10-23（JST） 窗口：27 条（去重后，原始 28）· 6 位账号 · 跳过重复 0 · 迟到 182 · 晚于窗口 3

$ ... --at "2026-10-23 23:00" --out /tmp/s2 ...        # 第二次
注意：这一期没有任何新条目。……
2026-10-23（JST） 窗口：0 条（去重后，原始 0）· 0 位账号 · 跳过重复 28 · 迟到 0 · 晚于窗口 3
```

第二次 `skipped_duplicate` 正好 28，`new` 为 0 —— 闸门第 1 条。

```text
$ python -m unittest discover -s tests
Ran 147 tests in 38.219s
OK
```

```text
$ cd scripts && python -m daily build --items-dir sample_items --date 2026-10-23 \
    --at "2026-10-23 22:00" --check-reproducible
可复现：3 个文件、32879 字节，两次运行完全相同（26102322）
```

三个产物一起比：`briefing.txt` / `.md` / `.generate.json`。

```text
$ ... --items-dir <只有一条 stranger_danger 的目录> --backfill
注意：1 个 handle 不在名单里，已归入 other：stranger_danger
2026-10-23（JST） 窗口：1 条（去重后，原始 1）· 1 位账号 · 跳过重复 0 · 迟到 0 · 晚于窗口 0
```

```text
$ npm run check   → 0 errors / 0 warnings / 0 hints（52 文件）
$ npm run build   → 18 page(s) built
$ npm run links   → 23 个页面 · 559 个站内链接（共 776 处引用） · 跳过 123 处外链 · 全部通过
```

### 遗留问题

- `build_briefing()` 每个账号只列互动数前 5 条。样例里 `stats` 全空 → 实际就是「时间上最早 5 条」，10-22 有 41 条时写手看不到后 9 条。补录这周时是从 `generate.json` 读全量才写全的。要么改成按时间取最近 N 条，要么在 briefing 里显式标「还有 N 条未列」。
- `late` 的判定只看账本里有没有这个 key，不看条目自带的 `first_seen`。两者不一致时以账本为准，但没有告警。
- `--backfill` 会把窗口外的条目直接丢掉再判态，所以补录时 `late` / `future` 恒为 0。这是有意的（补录不关心别的日子），但也意味着它不能用来发现迟到数据。
- 互动只抽「传播」与「正文 @」，没抽引用（quote）与回复链。真数据里回复链是主要的互动形态，M3 之前要补。
- 10-24 那一期没有发：样例数据的抓取截止在 10-24 05:09 JST，全天只有 3 条，发出去会让人以为那天只发生了三件事。等下一次完整抓取再补。

### 下一步

M3：出题与判卷分离（`prompt.py` / `validate.py` / `apply.py` / `confirm.py`）。
先做 M3.1 出题，因为这一周六期是手写填的，正好可以拿来当 M3 的对照组。

## 2026-10-29 · 日报拆成两版（声优 / Galgame）

### 为什么拆

一天出两份，而不是在一份里加栏目：

- **声优版**（`YYMMDD`）= 声优 128 条 + 音声社团 109 条。社团此前一直是 `active: false`，因为加进来会顶破单条 20 分钟超时线。
- **Galgame 版**（`YYMMDD-g`）= 游戏厂商 174 条 + 信息号 3 条。

两版的读者、栏目、数据来源都不同（社团是 DLsite 侧，厂商是 moepedia 侧）。合成一期会让「详细」的筛选按钮变成四选一，而且一边的噪音会挤掉另一边。

### 期号

`YYMMDD` 仍归声优版、不带后缀——这样已发布的 4 期（261025–261028）不用迁移。Galgame 版加 `-g`；同日第二期是 `-2` / `-g2`。

`parse_issue_id()` 返回 `(day, kind, seq)`，`issue_id_for(day, seq, kind)` 反向生成。`-1` 与 `-g1` 都判非法（第 1 期不写后缀）。

### 改了什么

| 位置 | 改动 |
| --- | --- |
| `src/config/daily-roster.json` | 只留声优版 237 条，社团全部 `active: true` |
| `src/config/daily-roster-galgame.json` | 新建，177 条（174 manufacturer + 3 info） |
| `scripts/daily/issue.py` | `VOICE` / `GALGAME` / `KIND_LABEL`，期号正则加 `-g` |
| `scripts/daily/roster.py` | 两版各一份默认路径；查询时合并（历史页面还能显示名字），分组只看本版 |
| `scripts/daily/cli.py` | `build --kind`；跨版条目跳过并告警；`ja` 只接受声优版 |
| `scripts/sync_xreader_accounts.py` | 写两份 yaml |
| `src/lib/daily.ts` | `DailyKind`、`KIND_LABEL`、标题 `X 日报 · YYYY-MM-DD 声优 / Galgame` |
| `src/lib/roster.ts` | 合并两份名单做查询，栏目顺序 seiyuu → circle → manufacturer → info → other |
| `DailyLayout.astro` | 默认亮哪个栏目按 `kind` 走 |

X-Reader 侧：`config/config.galgame.yaml`（`data_dir: data-galgame`）、`update-galgame.yml`（`03:10` / `15:10` UTC，超时 20 分钟）、`accounts.galgame.yaml`；`update.yml` 超时 20 → 30 分钟。

### 踩到的坑

- **派生字段漏进 JSON 出口。** `kind` 是站点从期号推导的，`[id].json.ts` 忘了剥掉，`check:daily` 立刻报「与 report.json 不是逐字节相同」。
- **合并查询层的副作用。** 手写的测试名单没有 `category_ids`，`belongs_to_kind()` 把条目全判成「另一版」丢掉 → 改成 `category_ids` 为空时一律放行。
- **金文件排序。** `newest_issue()` 原来按字符串排序，`-g` 后缀会把 `261022-g` 排到 `261028` 之后 → 改成按 `(day, 声优版优先, seq)` 解析后排序。

### 验收

```text
$ python -m unittest discover -s tests
Ran 255 tests in 3.072s
OK

$ npm run build
22 page(s) built

$ npm run check:daily
✓ 4 期：HTML + JSON + TXT 三种出口齐全，JSON 与正本逐字节相同
✓ 2 期有 Ci-en 出口
金文件一致：/daily/261025/ 的正文纯文本与基准逐字相同（66 行）

$ npm run links        → 27 个页面 · 985 个站内链接 · 全部通过
$ npm run check:prose  → 27 页 · 没有落单的加粗标记
```

端到端还跑过一次合成期号 `261022-g`（样例数据）：标题 `X 日报 · 2026-10-22 Galgame`，「详细」默认亮「游戏制造商」、另一个按钮是「信息号」，归档行显示 `10-22 Galgame`。验完删掉了，不污染存档。

### 遗留

- 厂商侧个人号 14 条（剧作者 8 / 导演 3 / 代表 3）还没入册，之后再补；入册时每条要挂 `max_items: 1`。
- 信息号候选 11 条（个人向 4 + 平台／媒体 7）仍在报告里，`@getchucom` / `@bugbug_info` 标了优先。
- Galgame 版还没有实盘数据：`data-galgame/` 要等 `update-galgame.yml` 第一次跑完才有。
