/**
 * 竖版日报长图（生产入口）
 *
 *   node scripts/daily-image/render.mjs <期号> --final [--out=<webp 路径>]
 *       出终版长图，默认写 public/images/daily/<期号>.webp（publish 会调它）
 *
 *   node scripts/daily-image/render.mjs <期号>
 *       出 pic/daily2 的八张对照稿（旧入口 scripts/daily2/render.mjs 仍可用）
 *
 * 拼装来源：
 *
 * 拼装来源：
 *   作品消息 = 067 bentoGrid 的双栏瓦片
 *   今日要点 = 077 warmCard 的堆叠卡片
 *   头版     = 001 色块 / 012 竖轨 / 151 双框 / 077 衬线粗线 / 轨+框
 *   底色     = 木质色系
 *   字体     = 全篇偏粗，题目 900 → 区块 800 → 要点 600 → 作品 500
 *
 * 报头保持原样（声优日报 + 日期，无「覆盖全天 JST」）；页脚留空。
 * 「题目」= 导语段（report.description），06/07 两稿把它放大到 1.5× / 2×。
 *
 *   node scripts/daily2/render.mjs [期号]
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'C:/Users/lenovo/Desktop/github page work';
const ISSUE = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : '261101';
const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').replace('--only=', '');
const OUT = path.join(ROOT, 'pic', 'daily2');

const pw = await import(
  pathToFileURL(path.join(ROOT, 'juya-news-card-main/node_modules/playwright/index.js')).href
);
const chromium = pw.chromium || pw.default?.chromium;

const SANS = `"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif`;
const SERIF = `"STSong","SimSun",Georgia,serif`;
const GEO = `Georgia,"Times New Roman","STSong",serif`;

/* ------------------------------------------------------------------ 数据 */

const report = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/daily', ISSUE, 'report.json'), 'utf8'));
const issue = report.issue || {};
const dateISO = (issue.window?.start || '2026-11-01T00:00:00+09:00').slice(0, 10);
const [Y, M, D] = dateISO.split('-');
const WEEK = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'][
  new Date(`${dateISO}T12:00:00+09:00`).getDay()
];
const isG = String(issue.id || ISSUE).includes('-g');
const kindLabel = isG ? 'Galgame 日报' : '声优日报';
const kindEn = isG ? 'GALGAME DAILY' : 'SEIYUU DAILY';
// 报头上方那行小字。两版不一样——Galgame 版写「Galgame X まとめ」，
// 写成「声優Xまとめ」是把声优版的名字套过去了。
const kickerName = isG ? 'Galgame X まとめ' : '声優Xまとめ';

const works = report.works || [];
const highlights = (report.highlights || []).map((h) => (typeof h === 'string' ? h : h.text));

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/* ------------------------------------------------------------------ 木色底 */

const GRAIN = `repeating-linear-gradient(88deg, rgba(90,60,30,.022) 0 2px, transparent 2px 6px),
  radial-gradient(ellipse 76% 42% at 18% 0%, rgba(160,110,60,.10), transparent 62%)`;

/* ------------------------------------------------------------------ 稿件 */

// 012 竖轨那一套，06 / 07 复用，只换导语（题目）字号
const railCss = (leadSize, leadLh) => `
  .page{padding-top:0}
  .page::before{content:"";display:block;height:12px;margin:0 -64px 52px;
    background:linear-gradient(90deg,#5c3a1c,#8b5a2b 34%,#b07a3f 62%,#cfa06a 82%,#e2c49b)}
  .mast{padding-left:30px;border-left:11px solid var(--accent)}
  .kicker{color:var(--accent);letter-spacing:.3em;font-size:11px}
  .lead{font-size:${leadSize};line-height:${leadLh};margin-top:30px}
  .sec{margin-top:46px}
  .sec-head{border-bottom:2px solid var(--ink);padding-bottom:9px;margin-bottom:20px}
  .sec-no{background:var(--accent);color:#faf1df;padding:3px 9px;border-radius:3px;font-size:11px}
`;

const WOOD = {
  paper: '#efe2cb', card: '#faf1df', ink: '#342415', muted: '#7a5f3f',
  line: '#d6c2a2', accent: '#8b5a2b', accentInk: '#faf1df',
  body: SANS, display: SANS, dw: 900, tl: '-0.045em', r: '12px',
};

const DRAFTS = [
  {
    idx: '01', id: 'block', name: '001 色块头版',
    vars: {
      paper: '#f4ead9', card: '#fbf4e6', ink: '#3a2a19', muted: '#7c6448',
      line: '#ddcbb1', accent: '#8d5b33', accentInk: '#fbf3e6',
      body: SANS, display: SANS, dw: 900, ts: '78px', tl: '-0.03em', r: '18px',
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
      body: SANS, display: GEO, dw: 700, ts: '80px', tl: '0.02em', r: '2px',
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
      body: SANS, display: SERIF, dw: 700, ts: '84px', tl: '0.04em', r: '14px',
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
      body: SANS, display: SANS, dw: 900, ts: '82px', tl: '-0.04em', r: '10px',
    },
    css: `
      .mast{border:1.5px solid var(--ink);border-left:14px solid var(--accent);padding:0 32px 0 34px;align-items:stretch}
      .mast-left{padding:32px 0 28px}
      .mast-right{padding:34px 0 26px;display:flex;flex-direction:column;justify-content:flex-end}
      .kicker{color:var(--accent);letter-spacing:.28em;font-size:11px}
      .lead{margin-top:26px;padding-left:20px;border-left:5px solid var(--accent)}
      .sec{margin-top:46px}
      .sec-head{border-bottom:1.5px solid var(--ink);padding-bottom:9px;margin-bottom:20px}
      .sec-no{background:var(--accent);color:#f8eedb;padding:3px 8px;border-radius:2px;font-size:11px}
    `,
  },
  {
    idx: '06', id: 'rail-lead-15x', name: '012 竖轨 · 题目 1.5×',
    vars: { ...WOOD, ts: '84px' },
    css: railCss('31.5px', '1.6'),
  },
  {
    idx: '07', id: 'rail-lead-2x', name: '012 竖轨 · 题目 2×',
    vars: { ...WOOD, ts: '84px' },
    css: railCss('42px', '1.5'),
  },
  {
    // 四类正文各 ×1.2 向上取整：84→101 / 21→26 / 19.5→24 / 15.5→19
    idx: '08', id: 'rail-12x', name: '012 竖轨 · 全文字号 1.2×',
    vars: { ...WOOD, ts: '101px' },
    // 导语取 07 的 42px 再 ×1.2 = 50.4 → 51px
    css: `${railCss('51px', '1.42')}
      .hl p{font-size:24px;line-height:1.68}
      .hl li{padding:23px 28px}
      .hl .n{font-size:30px;min-width:52px}
      .sec-head h2{font-size:30px}
      .works p{font-size:19px;line-height:1.6}
      .works li{padding:19px 21px}
      .works .n{font-size:12px}
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

/* 077 式要点：堆叠卡片 */
.hl{list-style:none;display:flex;flex-direction:column;gap:12px}
.hl li{display:flex;gap:18px;align-items:flex-start;background:var(--card);border-radius:14px;
  padding:21px 26px;box-shadow:0 8px 20px -18px rgba(58,42,26,.75)}
.hl .n{flex:none;font-family:${SERIF};font-size:26px;font-weight:700;line-height:1.25;color:var(--accent);
  min-width:46px;font-variant-numeric:tabular-nums}
.hl p{font-size:19.5px;line-height:1.72;font-weight:600}

/* 067 式作品：双栏瓦片 */
.works{list-style:none;display:grid;grid-template-columns:1fr 1fr;gap:12px}
.works li{background:var(--card);border-radius:12px;padding:17px 19px;border:1px solid rgba(58,42,26,.06)}
.works .n{display:block;font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.1em;margin-bottom:7px;
  font-variant-numeric:tabular-nums}
.works p{font-size:15.5px;line-height:1.62;font-weight:500}
.works p,.hl p{text-wrap:pretty}
.foot{margin-top:auto;padding-top:48px}
`;

/* ------------------------------------------------------------------ 生成 */

function buildHtml(d) {
  const vars = Object.entries(d.vars).map(([k, v]) => `--${k}:${v}`).join(';');
  // 导语以逗号 / 句号为换行符：标点跟着上一句留在行尾，行首不出标点
  const leadHtml = esc(report.description || '')
    .replace(/([，。])/g, '$1<br>')
    .replace(/<br>$/, '');
  const hl = highlights
    .map((t, i) => `<li><span class="n">${String(i + 1).padStart(2, '0')}</span><p>${esc(t)}</p></li>`)
    .join('');
  const wk = works
    .map((t, i) => `<li><span class="n">${String(i + 1).padStart(2, '0')}</span><p>${esc(t)}</p></li>`)
    .join('');

  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>${esc(kindLabel)} ${dateISO}</title>
<style>${BASE}
body{${vars}}
${d.css}
</style></head><body>
<div class="page">
  <header class="mast">
    <div class="mast-left">
      <div class="kicker">${esc(kickerName)} · 第 ${esc(issue.id || ISSUE)} 期</div>
      <h1 class="title">${esc(kindLabel)}</h1>
      <div class="sub">${esc(kindEn)}</div>
    </div>
    <div class="mast-right">
      <div class="date">${Y}.${M}.${D}</div>
      <div class="dow">${WEEK}</div>
    </div>
  </header>

  <p class="lead">${leadHtml}</p>

  <section class="sec">
    <div class="sec-head"><span class="sec-no">01</span><h2>今日要点</h2><span class="sec-en">Highlights</span></div>
    <ol class="hl">${hl}</ol>
  </section>

  <section class="sec">
    <div class="sec-head"><span class="sec-no">02</span><h2>作品消息</h2><span class="sec-en">Works</span></div>
    <ul class="works">${wk}</ul>
  </section>

  <footer class="foot"></footer>
</div>
</body></html>`;
}

/* ---- 终版：publish 调这一支 ---- */

const FINAL = DRAFTS.find((d) => d.id === 'rail-12x');
const isFinal = process.argv.includes('--final');
const outArg = (process.argv.find((a) => a.startsWith('--out=')) || '').replace('--out=', '');

if (isFinal) {
  const dest = outArg
    ? path.resolve(outArg)
    : path.join(ROOT, 'public', 'images', 'daily', `${issue.id || ISSUE}.webp`);
  fs.mkdirSync(path.dirname(dest), { recursive: true });

  const browser = await chromium.launch({ channel: 'msedge', args: ['--font-render-hinting=none'] });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1200 }, deviceScaleFactor: 2 });
  const tmp = path.join(path.dirname(dest), `.daily-${issue.id || ISSUE}.html`);
  fs.writeFileSync(tmp, buildHtml(FINAL), 'utf8');
  await page.goto('file://' + tmp.replace(/\\/g, '/'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(150);
  // Playwright 只会截 PNG / JPEG，所以先拿 PNG 缓冲，再压成 WebP：
  // 同尺寸 q92 约 660KB，直出 PNG 是 1.6–1.8MB，一天两张、一年就是 1.2GB。
  const png = await page.screenshot({ fullPage: true });
  const h = await page.evaluate(() =>
    Math.round(document.querySelector('.page').getBoundingClientRect().height)
  );
  await browser.close();
  fs.unlinkSync(tmp);

  const sharp = (await import('sharp')).default;
  await sharp(png).webp({ quality: 92, effort: 6 }).toFile(dest);
  const kb = Math.round(fs.statSync(dest).size / 1024);
  console.log(`${dest}  (${h}px @2x, ${kb}KB)`);
  process.exit(0);
}

/* ---- 对照稿：pic/daily2 ---- */

fs.mkdirSync(OUT, { recursive: true });
const picked = ONLY ? DRAFTS.filter((d) => ONLY.split(',').includes(d.idx)) : DRAFTS;

const browser = await chromium.launch({ channel: 'msedge', args: ['--font-render-hinting=none'] });
const page = await browser.newPage({ viewport: { width: 1080, height: 1200 }, deviceScaleFactor: 2 });

const rows = [];
for (const d of picked) {
  const tmp = path.join(OUT, `.${d.idx}.html`);
  fs.writeFileSync(tmp, buildHtml(d), 'utf8');
  await page.goto('file://' + tmp.replace(/\\/g, '/'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(120);
  const file = path.join(OUT, `${d.idx}-${d.id}.png`);
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
    `${d.idx} ${d.id.padEnd(14)} ${info.h}px  题目 ${info.fs}px / ${info.lines} 行  ${(fs.statSync(file).size / 1024).toFixed(0)}KB`,
  );
}
await browser.close();

const cards = rows
  .map(
    (r) => `<a class="c" href="${r.file}" target="_blank">
    <div class="im"><img src="${r.file}" alt="${r.id}" loading="lazy"></div>
    <div class="meta"><span class="no">${r.idx}</span><b>${r.id}</b><span class="nm">${r.name}</span></div></a>`,
  )
  .join('\n');

fs.writeFileSync(
  path.join(OUT, 'index.html'),
  `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>组合稿 · ${ISSUE}</title>
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
<h1>竖版日报 · 组合稿 ${esc(issue.id || ISSUE)}</h1>
<p class="sub">067 作品双栏 · 077 要点卡片 · 001/012/151/077 头版 · 木质底 · 无数据条 / 无页脚 · 06/07 题目 1.5× / 2×</p>
<div class="grid">${cards}</div>
</body></html>`,
  'utf8',
);

console.log(`\n→ ${OUT}`);
