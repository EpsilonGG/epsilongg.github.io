/**
 * 草稿入口（保留兼容）：出 `pic/daily2/` 的八张对照稿。
 * 实现在 `scripts/daily-image/render.mjs`——终版长图走那边（`--final`）。
 */
process.argv.push('--drafts');
await import('../daily-image/render.mjs');
