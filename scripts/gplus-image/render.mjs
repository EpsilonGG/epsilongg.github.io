/**
 * Gplus 日报竖版长图
 *
 *   node scripts/gplus-image/render.mjs 261119-gp [--out=<webp 路径>]
 *       默认写 public/images/gplus/<期号>.webp；`DailyLayout` 在「详细」栏之前引它。
 *
 * 与日报长图的区别：日报那张是「题目 + 今日要点 + 作品动态」，
 * Gplus 这张按用户 2026-11-22 的口径只放三段——**标题 / 洞察 / 互动**，
 * 因为 Gplus 定位是业界，没有作品表可放；详细栏本身就是长清单，不进图。
 *
 * 版式：浅色纸面 + 深红强调，衬线标题 + 无衬线正文；宽度 1080，高度随条数。
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'C:/Users/lenovo/Desktop/github page work';
const ISSUE = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : '261119-gp';
const OUT_ARG = (process.argv.find((a) => a.startsWith('--out=')) || '').replace('--out=', '');

const report = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/daily', ISSUE, 'report.json'), 'utf8'));
const issue = report.issue || {};
const dateISO = (issue.window?.start || '2026-11-19T00:00:00+09:00').slice(0, 10);
const WEEK = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'][
  new Date(`${dateISO}T12:00:00+09:00`).getDay()
];
const title = report.description || '';
const insights = (report.insights || []).map((x) => (typeof x === 'string' ? x : x.text));
const interactions = (report.interactions || []).map((x) => (typeof x === 'string' ? x : x.text));

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const listHtml = (items) =>
  items.map((t, i) => `<li><span class="num">${String(i + 1).padStart(2, '0')}</span><span class="txt">${esc(t)}</span></li>`).join('');

const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    width: 1080px; background: #F6F3EA; color: #1E1B16;
    font-family: "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .page { padding: 64px 72px 56px; }
  header { border-bottom: 4px solid #1E1B16; padding-bottom: 22px; margin-bottom: 40px; }
  .kicker {
    font-size: 20px; letter-spacing: .32em; text-transform: uppercase;
    color: #8C2F1E; font-weight: 700;
  }
  h1 {
    margin: 12px 0 0; font-size: 68px; line-height: 1.1; letter-spacing: .04em;
    font-family: "STSong", "SimSun", Georgia, serif; font-weight: 700;
  }
  .meta { margin-top: 14px; font-size: 22px; color: #6B6355; letter-spacing: .06em; }
  .block { margin-top: 44px; }
  .block h2 {
    margin: 0 0 18px; font-size: 26px; letter-spacing: .3em; color: #8C2F1E; font-weight: 800;
    display: flex; align-items: center; gap: 16px;
  }
  .block h2::after { content: ""; flex: 1; height: 2px; background: #D9D2C3; }
  .lead {
    margin: 0; font-size: 34px; line-height: 1.62; font-weight: 600;
    font-family: "STSong", "SimSun", Georgia, serif;
  }
  /* 双栏：21 条洞察 + 27 条互动单栏会拉到 1.5 万像素，双栏后与日报长图同一量级。
     用 CSS 多栏自动均衡，条目不跨栏（break-inside: avoid）。 */
  ol { list-style: none; margin: 0; padding: 0; column-count: 2; column-gap: 44px; }
  li { display: flex; gap: 14px; padding: 12px 0; border-top: 1px solid #E3DCCC; break-inside: avoid; }
  li:first-child { border-top: none; padding-top: 0; }
  .num {
    flex: 0 0 auto; font-size: 16px; font-weight: 800; color: #8C2F1E;
    font-variant-numeric: tabular-nums; padding-top: 6px; letter-spacing: .04em;
  }
  .txt { font-size: 21px; line-height: 1.62; }
  footer {
    margin-top: 52px; padding-top: 18px; border-top: 2px solid #1E1B16;
    font-size: 18px; color: #6B6355; display: flex; justify-content: space-between;
    letter-spacing: .05em;
  }
</style></head><body><div class="page">
  <header>
    <div class="kicker">Galgame X まとめ</div>
    <h1>Gplus 日报</h1>
    <div class="meta">${dateISO} · ${WEEK} · JST</div>
  </header>

  <section class="block">
    <h2>标题</h2>
    <p class="lead">${esc(title)}</p>
  </section>

  <section class="block">
    <h2>洞察</h2>
    <ol>${listHtml(insights)}</ol>
  </section>

  <section class="block">
    <h2>互动</h2>
    <ol>${listHtml(interactions)}</ol>
  </section>

  <footer>
    <span>epsilongg.github.io</span>
    <span>${ISSUE}</span>
  </footer>
</div></body></html>`;

const dest = OUT_ARG
  ? path.resolve(OUT_ARG)
  : path.join(ROOT, 'public', 'images', 'gplus', `${issue.id || ISSUE}.webp`);
fs.mkdirSync(path.dirname(dest), { recursive: true });

const pw = await import(
  pathToFileURL(path.join(ROOT, 'juya-news-card-main/node_modules/playwright/index.js')).href
);
const chromium = pw.chromium || pw.default?.chromium;

const browser = await chromium.launch({ channel: 'msedge', args: ['--font-render-hinting=none'] });
const page = await browser.newPage({ viewport: { width: 1080, height: 1200 }, deviceScaleFactor: 2 });
const tmp = path.join(path.dirname(dest), `.gplus-${issue.id || ISSUE}.html`);
fs.writeFileSync(tmp, html, 'utf8');
await page.goto('file://' + tmp.replace(/\\/g, '/'));
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(150);
const png = await page.screenshot({ fullPage: true });
const h = await page.evaluate(() => Math.round(document.querySelector('.page').getBoundingClientRect().height));
await browser.close();
fs.unlinkSync(tmp);

const sharp = (await import('sharp')).default;
await sharp(png).webp({ quality: 86, effort: 6 }).toFile(dest);
const kb = Math.round(fs.statSync(dest).size / 1024);
console.log(`${dest}  (${h}px @2x, ${kb}KB, 洞察 ${insights.length} 条 / 互动 ${interactions.length} 条)`);
