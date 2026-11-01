# `data/xreader/` — 抓取数据的按日切片

这里放 X-Reader 抓回来的推文，**按 JST 自然日切成一片一个文件**，供
`scripts/daily_prepare.py` 读。它是日报的原料，不是站点内容。

```
data/xreader/
  voice/2026-10-31.jsonl      声优版（声优 + 音声社团），对应 update.yml
  galgame/2026-10-31.jsonl    Galgame 版（制造商 + 信息号），对应 update-galgame.yml
```

每行就是 X-Reader 的 `NormalizedItem` 原样（不重新序列化，字段顺序与正本一致），
按 `published_at` 升序、`identity_key` 去重。

## 为什么切片，而不是把整份库搬进来

X-Reader 的库是 **append-only** 的单文件：`data/items/x.jsonl` 14 MB、
`data-galgame/items/x.jsonl` 5.3 MB，每天还在长。整份提交等于让 git 每天存一份
全新的整文件——一天 20 MB、一年 7 GB，仓库会被撑爆。

切一片约 550 KB（700 条上下），滚存 14 天约 7.5 MB；git 里 zlib 之后一天约 150 KB，
一年 55 MB 量级。这是「数据进仓库」能付得起的最低代价。

## 会不会出现在网站上

不会。`data/` 在仓库根，**不在 `public/` 里**。Astro 只把 `public/` 和路由生成的
页面放进 `dist/`；`data/daily/` 虽然也是 `data/` 下的，但它是 content collection，
构建时读、不复制。所以 `dist/data/` 从来不存在，`deploy.yml` 里也钉了
`paths-ignore: data/xreader/**`——只改这些文件不会触发部署。

公开可见的只有 GitHub 仓库本身（这个仓库是 public）。同样的数据在
`EpsilonGG/X-Reader` 里也是 public，所以这里不构成新的暴露。

## 谁写、谁读

| | |
|---|---|
| 写 | `scripts/xreader_slice.py`（`daily_prepare.py` 在 `git pull` 之后自动调用） |
| 读 | `scripts/daily_prepare.py` → `items_dir_for()`：`.xreader/` 在就用全量库，不在就用这里 |
| 保留 | 默认 14 天（`--keep`），窗口外的旧片自动删除 |

`.xreader/` 被 `.gitignore` 挡在外面，所以克隆下来只有这里的切片。这正好是
「抓取 checkout 又没了」时还能出稿的原因——不是备份，是**能用的副本**。

## 手动操作

```bash
python scripts/xreader_slice.py                 # 两版都切，滚存 14 天
python scripts/xreader_slice.py --keep 30       # 想回看更久
python scripts/xreader_slice.py --date 2026-10-31   # 只补某一天
python scripts/xreader_slice.py --dry-run       # 只看会写什么
```

要更早的历史，去 `.xreader/` 那份全量库（十年、11438 条），它不进仓库。
