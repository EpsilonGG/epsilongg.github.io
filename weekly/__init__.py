"""weekly · Galgame 周报正式版管线（四类筛选 / 三栏展示 / 带图 HTML）。

只读仓库既有的 Galgame 日报数据（`data/daily/`、`out/clauses/`），只写 `weekly/out/`；
不进 `data/weekly/`、不上页面、不 publish。

入口：`python -m weekly build` / `python -m weekly check`。

三栏＝**新作 / 作品情报 / 业界动向**。归栏仍是三值（作品情报 / 品牌动向 / 业界动向，
记在 `sections[].column`，作为「为什么这么分类」的证据）；展示时 `品牌动向` 并入
`作品情报`，并把整组新作提到第一栏——合并只发生在展示层，`item["display_column"]`
由 `pipeline.apply_display_columns()` 一次算好，Python 与编辑器 JS 都只读不算。

旧版（`weekly_studio/` 只读工作台、`weekly-draft-*` 两版试稿）已归档到
`archive/weekly_studio/` 与 `archive/weekly-out/`。
"""

__version__ = "2.0.0"
