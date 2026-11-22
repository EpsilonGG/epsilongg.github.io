/**
 * Gplus 日报竖版长图（生产入口）
 *
 *   node scripts/gplus-image/render.mjs <期号> --final [--out=<webp 路径>]
 *       出终版长图，默认写 public/images/gplus/<期号>.webp
 *
 *   node scripts/gplus-image/render.mjs <期号> [--only=01,08]
 *       出模板对照稿（pic/gplus-image/），不写生产图
 *
 * 模板模式照抄 `scripts/daily-image/render.mjs`（声优日报）：
 *   - 同一份 BASE 版式 + DRAFTS 变量/CSS 覆盖，多套头版与字号可比对；
 *   - 终版固定选 `rail-12x`；--only 只跑指定稿；对照稿附 index.html 联络表；
 *   - 木质底 / 竖轨 / 卡片瓦片 / 衬线点题 / 逗号句号断行 / text-wrap:pretty；
 *   - Playwright 截 PNG 缓冲 -> sharp 压 WebP，不落中间 PNG。
 *
 * 与声优日报的差别只在栏目：Gplus 没有作品表，按用户 2026-11-22 口径只放
 * 「导语 / 洞察 / 互动」——导语直接跟在报头后，**不写「标题」这种栏目名**；
 * 洞察与互动都是长条目，两段都用双栏，避免单栏把 40+ 条拉到 1.5 万像素。
 * 详细栏本身是逐账号清单，不进图。
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'C:/Users/lenovo/Desktop/github page work';
const ISSUE = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : '261119-gp';
const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').replace('--only=', '');
const OUT_ARG = (process.argv.find((a) => a.startsWith('--out=')) || '').replace('--out=', '');
const isFinal = process.argv.includes('--final');
const OUT_DRAFT = path.join(ROOT, 'pic', 'gplus-image');

const report = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/daily', ISSUE, 'report.json'), 'utf8'));
const issue = report.issue || {};
const dateISO = (issue.window?.start || '2026-11-19T00:00:00+09:00').slice(0, 10);
const [Y, M, D] = dateISO.split('-');
const WEEK = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'][
  new Date(`${dateISO}T12:00:00+09:00`).getDay()
];
const title = report.description || '';
const insights = (report.insights || []).map((x) => (typeof x === 'string' ? x : x.text));
const interactions = (report.interactions || []).map((x) => (typeof x === 'string' ? x : x.text));

const esc = (s) =>
  String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

/* ------------------------------------------------------------------ 字体 / 底色 */

const SANS = `"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif`;
const SERIF = `"STSong","SimSun",Georgia,serif`;
const GEO = `Georgia,"Times New Roman","STSong",serif`;

// 与声优日报同一张木色底：88deg 细木纹 + 左上角暖光（透明度 <= .10，再重会脏）
const GRAIN = `repeating-linear-gradient(88deg, rgba(90,60,30,.022) 0 2px, transparent 2px 6px),
  radial-gradient(ellipse 76% 42% at 18% 0%, rgba(160,110,60,.10), transparent 62%)`;

const WOOD = {
  paper: '#efe2cb', card: '#faf1df', ink: '#342415', muted: '#7a5f3f',
  line: '#d6c2a2', accent: '#8b5a2b', accentInk: '#faf1df',
  body: SANS, display: SANS, dw: 900, ts: '101px', tl: '-0.045em', r: '12px',
};

/* ------------------------------------------------------------------ 模板 */

// 012 竖轨那一套，06 / 07 / 08 复用，只换导语（题目）字号
const railCss = (leadSize, leadLh) => `
  .page{padding-top:0}
  .page::before{content:"";display:block;height:12px;margin:0 -64px 52px;
    background:linear-gradient(90deg,#5c3a1c,#8b5a2b 34%,#b07a3f 62%,#cfa06a 82%,#e2c49b)}
  .mast{padding-left:30px;border-left:11px solid var(--accent)}
  .kicker{color:var(--accent);letter-spacing:.3em;font-size:11px}
  .lead{font-size:${leadSize};line-height:${leadLh};margin-top:30px}
  .sec{margin-top:46px}
  .sec-head{border-bottom:2px solid var(--ink);padding-bottom:9px;margin-bottom:20px}
  .sec-no{background:var(--accent);color:var(--accentInk);padding:3px 9px;border-radius:3px;font-size:11px}
`;

const DRAFTS = [
  {
    idx: '01', id: 'block', name: '001 色块头版',
    vars: {
      paper: '#f4ead9', card: '#fbf4e6', ink: '#3a2a19', muted: '#7c6448',
      line: '#ddcbb1', accent: '#8d5b33', accentInk: '#fbf3e6',
      body: SANS, display: SANS, dw: 900, ts: '68px', tl: '-0.03em', r: '18px',
    },
    css: `
      .mast{background:var(--accent);color:#fbf3e6;border-radius:20px;padding:46px 42px 40px;align-items:flex-end}
      .mast .kicker{color:rgba(251,243,230,.7)}
      .mast .title{color:#fbf3e6}
      .mast .date{color:#fbf3e6}
      .mast .dow{color:rgba(251,243,230,.68)}
      .mast .sub{color:rgba(251,243,230,.5)}
      .lead{margin-top:26px;padding-left:20px;border-left:5px solid var(--accent)}
      .sec{margin-top:46px}
      .sec-head{border-bottom:1px solid #d8c4a6;padding-bottom:11px;margin-bottom:20px}
    `,
  },
  {
    idx: '02', id: 'rail', name: '012 竖轨头版',
    vars: { ...WOOD, ts: '84px' },
    css: railCss('21px', '1.78'),
  },
  {
    idx: '03', id: 'frame', name: '151 双框头版',
    vars: {
      paper: '#ede4d6', card: '#f8f0e2', ink: '#2e2318', muted: '#6f5c44',
      line: '#cfbda0', accent: '#7c5b3a', accentInk: '#f8f0e2',
      body: SANS, display: GEO, dw: 700, ts: '72px', tl: '0.02em', r: '2px',
    },
    css: `
      .mast{border:1.5px solid var(--ink);padding:30px 32px 26px;position:relative;align-items:flex-end}
      .mast::before{content:"";position:absolute;inset:5px;border:1px solid #b9a583;pointer-events:none}
      .title{font-family:${GEO};font-weight:700}
      .kicker{font-family:${GEO};font-style:italic;letter-spacing:.24em;font-size:11px;color:#7a6650}
      .sub{letter-spacing:.4em;font-size:10px;color:#8d7a63}
      .date{font-family:${GEO};font-weight:400;font-size:24px}
      .lead{margin-top:24px;font-family:${GEO};font-size:21px;line-height:1.85;padding-bottom:18px;border-bottom:1px solid #cfbda0}
      .sec{margin-top:42px}
      .sec-head{border-bottom:1.5px solid var(--ink);padding-bottom:9px;margin-bottom:20px}
      .sec-head h2{font-family:${GEO};letter-spacing:.05em}
      .sec-no{font-family:${GEO};font-style:italic;color:#7a6650}
      .sec-en{font-family:${GEO};font-style:italic}
    `,
  },
  {
    idx: '04', id: 'serif-rule', name: '077 衬线粗线头版',
    vars: {
      paper: '#f6ebd7', card: '#fdf7ea', ink: '#3d2b17', muted: '#7f6547',
      line: '#e0cdae', accent: '#b07a3f', accentInk: '#fdf7ea',
      body: SANS, display: SERIF, dw: 700, ts: '76px', tl: '0.04em', r: '14px',
    },
    css: `
      .title{font-family:${SERIF};font-weight:700;letter-spacing:.06em}
      .kicker{color:#a58a66}
      .mast{border-bottom:3px solid var(--accent);padding-bottom:20px}
      .lead{margin-top:24px;font-size:21px}
      .sec{margin-top:48px}
      .sec-head{border-bottom:3px solid var(--accent);padding-bottom:10px;margin-bottom:18px}
      .sec-head h2{font-family:${SERIF};letter-spacing:.1em;font-size:28px}
      .sec-en{display:none}
    `,
  },
  {
    idx: '05', id: 'rail-frame', name: '012 竖轨 + 151 双框',
    vars: {
      paper: '#ebdcc2', card: '#f8eedb', ink: '#32220f', muted: '#75593a',
      line: '#d2bd9b', accent: '#6e4a2c', accentInk: '#f8eedb',
      body: SANS, display: SANS, dw: 900, ts: '74px', tl: '-0.04em', r: '10px',
    },
    css: `
      .mast{border:1.5px solid var(--ink);border-left:14px solid var(--accent);padding:0 32px 0 34px;align-items:stretch}
      .mast-left{padding:32px 0 28px}
      .mast-right{padding:34px 0 26px;display:flex;flex-direction:column;justify-content:flex-end}
      .kicker{color:var(--accent);letter-spacing:.28em;font-size:11px}
      .lead{margin-top:26px;padding-left:20px;border-left:5px solid var(--accent)}
      .sec{margin-top:46px}
      .sec-head{border-bottom:1.5px solid var(--ink);padding-bottom:9px;margin-bottom:20px}
      .sec-no{background:var(--accent);color:var(--accentInk);padding:3px 8px;border-radius:2px;font-size:11px}
    `,
  },
  {
    idx: '06', id: 'lead-15x', name: '012 竖轨 · 题目 1.5×',
    vars: { ...WOOD, ts: '84px' },
    css: railCss('31.5px', '1.6'),
  },
  {
    idx: '07', id: 'lead-2x', name: '012 竖轨 · 题目 2×',
    vars: { ...WOOD, ts: '84px' },
    css: railCss('42px', '1.5'),
  },
  {
    // 终版：声优日报的 08 rail-12x 头版 + 木质底 + 卡片瓦片；
    // 长条目正文保留 21px（与旧 Gplus 图同密度），再放大 40+ 条会翻倍高度。
    idx: '08', id: 'rail-12x', name: '012 竖轨 · 全文字号 1.2×',
    vars: { ...WOOD, ts: '101px' },
    css: `${railCss('51px', '1.42')}
      .list .txt{font-size:21px;line-height:1.62}
      .list .num{font-size:18px;min-width:32px}
      .sec-head h2{font-size:30px}
    `,
  },
];

/* ------------------------------------------------------------------ 基础版式 */

const BASE = `
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px}
body{background:var(--paper);color:var(--ink);font-family:var(--body);font-size:19px;line-height:1.7;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.page{position:relative;width:1080px;min-height:1500px;padding:64px 64px 62px;display:flex;flex-direction:column;
  overflow:hidden;background:${GRAIN},var(--paper)}
.mast{display:flex;justify-content:space-between;align-items:flex-end;gap:36px;position:relative}
.kicker{font-size:12px;letter-spacing:.26em;color:var(--muted);margin-bottom:18px;text-transform:uppercase;font-weight:600}
.title{font-family:var(--display);font-weight:var(--dw);font-size:var(--ts);line-height:1.04;
  letter-spacing:var(--tl);white-space:nowrap}
.sub{font-size:10px;letter-spacing:.34em;color:var(--muted);margin-top:14px;text-transform:uppercase;font-weight:600}
.mast-right{text-align:right;flex:none;padding-bottom:8px}
.date{font-size:28px;font-weight:800;letter-spacing:-.01em;font-variant-numeric:tabular-nums;white-space:nowrap}
.dow{font-size:12px;color:var(--muted);margin-top:8px;letter-spacing:.1em;white-space:nowrap;font-weight:600}
.lead{margin-top:28px;font-size:21px;line-height:1.78;font-weight:600;letter-spacing:.01em;text-wrap:pretty;
  word-break:keep-all;overflow-wrap:anywhere}
.sec{margin-top:48px}
.sec-head{display:flex;align-items:baseline;gap:13px}
.sec-no{font-size:12px;color:var(--accent);letter-spacing:.1em;font-weight:800}
.sec-head h2{font-size:27px;font-weight:800;letter-spacing:.02em;line-height:1.25}
.sec-en{margin-left:auto;font-size:10px;letter-spacing:.26em;color:var(--muted);text-transform:uppercase;font-weight:600}

/* 洞察 / 互动共用双栏卡片瓦片：长条目不跨栏 */
.list{list-style:none;column-count:2;column-gap:44px}
.list li{display:flex;gap:14px;align-items:flex-start;background:var(--card);border-radius:var(--r);
  padding:17px 19px;border:1px solid rgba(58,42,26,.06);margin-bottom:12px;break-inside:avoid;
  box-shadow:0 8px 20px -18px rgba(58,42,26,.75)}
.list .num{flex:none;font-family:${SERIF};font-size:16px;font-weight:700;line-height:1.4;color:var(--accent);
  min-width:30px;font-variant-numeric:tabular-nums;padding-top:2px}
.list .txt{font-size:19px;line-height:1.62;font-weight:500;text-wrap:pretty;word-break:keep-all;overflow-wrap:anywhere}
.foot{margin-top:auto;padding-top:48px;display:flex;justify-content:space-between;
  font-size:11px;letter-spacing:.12em;color:var(--muted)}
`;

/* ------------------------------------------------------------------ 生成 */

function buildHtml(d) {
  const vars = Object.entries(d.vars).map(([k, v]) => `--${k}:${v}`).join(';');
  // 导语以逗号 / 句号为换行符：标点跟着上一句留在行尾，行首不出标点
  const leadHtml = esc(title)
    .replace(/([，。])/g, '$1<br>')
    .replace(/<br>$/, '');
  const listHtml = (items) =>
    items
      .map(
        (t, i) =>
          `<li><span class="num">${String(i + 1).padStart(2, '0')}</span><span class="txt">${esc(t)}</span></li>`
      )
      .join('');

  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Gplus 日报 ${dateISO}</title>
<style>${BASE}
body{${vars}}
${d.css}
</style></head><body>
<div class="page">
  <header class="mast">
    <div class="mast-left">
      <div class="kicker">Galgame X まとめ · 第 ${esc(issue.id || ISSUE)} 期</div>
      <h1 class="title">Gplus 日报</h1>
      <div class="sub">GPLUS DAILY</div>
    </div>
    <div class="mast-right">
      <div class="date">${Y}.${M}.${D}</div>
      <div class="dow">${WEEK}</div>
    </div>
  </header>

  <!-- 导语不挂「标题」栏目名：跟声优日报一样，报头下面直接是题目段 -->
  <p class="lead">${leadHtml}</p>

  <section class="sec">
    <div class="sec-head"><span class="sec-no">01</span><h2>洞察</h2><span class="sec-en">Insights</span></div>
    <ol class="list">${listHtml(insights)}</ol>
  </section>

  <section class="sec">
    <div class="sec-head"><span class="sec-no">02</span><h2>互动</h2><span class="sec-en">Interactions</span></div>
    <ol class="list">${listHtml(interactions)}</ol>
  </section>

  <footer class="foot"><span>epsilongg.github.io</span><span>${esc(issue.id || ISSUE)}</span></footer>
</div>
</body></html>`;
}

/* ---- 终版：publish / 手跑 --final 走这一支 ---- */

const FINAL = DRAFTS.find((d) => d.id === 'rail-12x');

if (isFinal) {
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
  fs.writeFileSync(tmp, buildHtml(FINAL), 'utf8');
  await page.goto('file://' + tmp.replace(/\\/g, '/'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(150);
  const png = await page.screenshot({ fullPage: true });
  const h = await page.evaluate(() =>
    Math.round(document.querySelector('.page').getBoundingClientRect().height)
  );
  await browser.close();
  fs.unlinkSync(tmp);

  const sharp = (await import('sharp')).default;
  // q86 是旧 Gplus 图的体积（1.4–1.7MB）；这里跟声优日报统一 q92，
  // 密集中文会大一些，但仍比中间 PNG 小一个数量级。
  await sharp(png).webp({ quality: 92, effort: 6 }).toFile(dest);
  const kb = Math.round(fs.statSync(dest).size / 1024);
  console.log(
    `${dest}  (${h}px @2x, ${kb}KB, 洞察 ${insights.length} 条 / 互动 ${interactions.length} 条)`
  );
  process.exit(0);
}

/* ---- 对照稿：pic/gplus-image ---- */

fs.mkdirSync(OUT_DRAFT, { recursive: true });
const picked = ONLY ? DRAFTS.filter((d) => ONLY.split(',').includes(d.idx)) : DRAFTS;

const pw = await import(
  pathToFileURL(path.join(ROOT, 'juya-news-card-main/node_modules/playwright/index.js')).href
);
const chromium = pw.chromium || pw.default?.chromium;
const browser = await chromium.launch({ channel: 'msedge', args: ['--font-render-hinting=none'] });
const page = await browser.newPage({ viewport: { width: 1080, height: 1200 }, deviceScaleFactor: 2 });

const rows = [];
for (const d of picked) {
  const tmp = path.join(OUT_DRAFT, `.${d.idx}.html`);
  fs.writeFileSync(tmp, buildHtml(d), 'utf8');
  await page.goto('file://' + tmp.replace(/\\/g, '/'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(120);
  const file = path.join(OUT_DRAFT, `${d.idx}-${d.id}.png`);
  await page.screenshot({ path: file, fullPage: true });
  const info = await page.evaluate(() => {
    const l = document.querySelector('.lead');
    const cs = getComputedStyle(l);
    return {
      h: Math.round(document.querySelector('.page').getBoundingClientRect().height),
      lines: Math.round(l.getBoundingClientRect().height / parseFloat(cs.lineHeight)),
      fs: Math.round(parseFloat(cs.fontSize)),
    };
  });
  fs.unlinkSync(tmp);
  rows.push({ ...d, file: path.basename(file), ...info });
  console.log(
    `${d.idx} ${d.id.padEnd(14)} ${info.h}px  题目 ${info.fs}px / ${info.lines} 行  ${(fs.statSync(file).size / 1024).toFixed(0)}KB`
  );
}
await browser.close();

const cards = rows
  .map(
    (r) => `<a class="c" href="${r.file}" target="_blank">
    <div class="im"><img src="${r.file}" alt="${r.id}" loading="lazy"></div>
    <div class="meta"><span class="no">${r.idx}</span><b>${r.id}</b><span class="nm">${r.name}</span></div></a>`
  )
  .join('\n');

fs.writeFileSync(
  path.join(OUT_DRAFT, 'index.html'),
  `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Gplus 模板对照 · ${ISSUE}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#efe6d8;color:#2e2318;font-family:"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif;padding:48px 40px 80px}
h1{font-size:26px;font-weight:800;letter-spacing:-.01em}
p.sub{color:#7a6650;font-size:13px;margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:26px;margin-top:32px}
.c{text-decoration:none;color:inherit;display:block}
.im{background:#fbf4e6;border:1px solid #ddcbb1;border-radius:8px;overflow:hidden;aspect-ratio:1080/1500}
.im img{width:100%;height:100%;object-fit:cover;object-position:top;display:block}
.c:hover .im{border-color:#6e4a2c}
.meta{display:flex;align-items:baseline;gap:8px;margin-top:10px;font-size:13px;flex-wrap:wrap}
.no{color:#8a7150;font-variant-numeric:tabular-nums}
.meta b{font-weight:700}
.nm{color:#7a6650;font-size:12px}
</style></head><body>
<h1>Gplus 日报 · 模板对照 ${esc(issue.id || ISSUE)}</h1>
<p class="sub">沿用声优日报出图模式：001/012/151/077 头版 · 木色底 · 双栏卡片 · 终版 08 rail-12x</p>
<div class="grid">${cards}</div>
</body></html>`,
  'utf8',
);

console.log(`\n→ ${OUT_DRAFT}`);
