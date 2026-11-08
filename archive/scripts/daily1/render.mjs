/**
 * 竖版日报渲染器（pic/daily1）
 *
 * 用 18 个 juya-news-card 模板的配色 / 字体 / 装饰语言，
 * 重排成「题目 → 今日要点 → 作品消息」的竖图文本版式。
 *
 *   node scripts/daily1/render.mjs [期号] [--only=001,012]
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'C:/Users/lenovo/Desktop/github page work';
// playwright 装在 vendored 的 juya-news-card-main 里，从脚本位置解析不到，按绝对路径加载
const pw = await import(
  pathToFileURL(path.join(ROOT, 'juya-news-card-main/node_modules/playwright/index.js')).href
);
const chromium = pw.chromium || pw.default?.chromium;
const ISSUE = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : '261101';
const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').replace('--only=', '');
const OUT = path.join(ROOT, 'pic', 'daily1');

const SANS = `"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif`;
const SERIF = `"STSong","SimSun",Georgia,serif`;
const KAI = `"STKaiti","KaiTi","Noto Sans SC",serif`;
const MONO = `"Cascadia Mono","Consolas","Noto Sans SC",monospace`;
const GEO = `Georgia,"Times New Roman","STSong",serif`;

/* ------------------------------------------------------------------ 数据 */

const report = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/daily', ISSUE, 'report.json'), 'utf8'));
const issue = report.issue || {};
const day = String(issue.id || ISSUE).slice(0, 4);
const dateISO = (issue.window?.start || '2026-11-01T00:00:00+09:00').slice(0, 10);
const [Y, M, D] = dateISO.split('-');
const WEEK = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'][new Date(`${dateISO}T12:00:00+09:00`).getDay()];
const published = (issue.published_at || '').slice(0, 16).replace('T', ' ');
const kindLabel = String(issue.id || ISSUE).includes('-g') ? 'Galgame 日报' : '声优日报';
const kindEn = String(issue.id || ISSUE).includes('-g') ? 'GALGAME DAILY' : 'SEIYUU DAILY';

const counts = report.counts || {};
const works = report.works || [];
const highlights = (report.highlights || []).map((h) => (typeof h === 'string' ? h : h.text));
const stats = [
  [String(counts.items ?? '—'), '条动态'],
  [String(counts.accounts ?? '—'), '个账号'],
  [String(highlights.length), '条要点'],
  [String(works.length), '条作品'],
];

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/* ------------------------------------------------------------------ 样式 */

/**
 * 每个条目 = 一个模板的视觉语言。
 * vars 控制基底，css 覆盖细节（招牌装饰都在这里）。
 */
const STYLES = [
  {
    idx: '001', id: 'claudeStyle', name: '暖调卡片反转',
    vars: {
      paper: '#f0eee6', card: '#fffdf9', ink: '#4a403a', muted: '#6d635f',
      line: '#ddd7cd', accent: '#c96442', accentInk: '#ffffff',
      body: SANS, display: SANS, dw: 700, ts: '74px', tl: '-0.02em', r: '20px',
    },
    css: `
      .mast{background:var(--accent);color:#fff;border-radius:var(--r);padding:44px 44px 40px;align-items:flex-end}
      .mast .kicker,.mast .sub,.mast .dow{color:rgba(255,255,255,.72)}
      .mast .title,.mast .date{color:#fff}
      .rules{display:none}
      .stats{margin-top:26px;background:var(--card);border-radius:16px;padding:22px 26px}
      .lead{margin-top:26px;background:var(--card);border-radius:16px;padding:30px 34px;font-size:22px;line-height:1.78;border-left:5px solid var(--accent)}
      .sec{margin-top:44px}
      .sec-head{border:0;padding-bottom:0;margin-bottom:18px}
      .sec-head h2{font-size:24px}
      .hl li{background:var(--card);border-radius:14px;padding:20px 24px;gap:16px}
      .hl .n{font-size:24px;min-width:44px;color:var(--accent)}
      .works li{background:var(--card);border:0;border-radius:12px;padding:16px 22px;margin-bottom:8px}
      .works .n{width:38px;padding-top:4px;color:#a89b8f}
    `,
  },
  {
    idx: '012', id: 'adobeSpectrum', name: '创意工具光谱',
    vars: {
      paper: '#fafafa', card: '#ffffff', ink: '#323232', muted: '#6e6e6e',
      line: '#e0e0e0', accent: '#ff8a00', accentInk: '#ffffff',
      body: SANS, display: SANS, dw: 700, ts: '80px', tl: '-0.035em', r: '4px',
    },
    css: `
      .page{padding-top:0}
      .page::before{content:"";display:block;height:10px;margin:0 -64px 54px;
        background:linear-gradient(90deg,#ff8a00,#ff9d2e 35%,#ffb347 62%,#ffcf8a 82%,#ffe3c2)}
      .mast{padding-left:28px;border-left:9px solid var(--accent);align-items:flex-end}
      .kicker{color:var(--accent);letter-spacing:.3em;font-size:12px}
      .r1{height:1px;background:var(--ink);margin-top:4px}
      .r2{height:1px;background:var(--ink)}
      .stats{margin-top:24px}
      .stat b{font-size:34px;letter-spacing:-.03em}
      .stat span{letter-spacing:.16em;font-size:12px}
      .sec-no{background:var(--accent);color:#fff;padding:3px 8px;border-radius:2px;font-size:12px}
      .sec-head{border-bottom:2px solid var(--ink);padding-bottom:10px}
      .hl .n{font-family:${MONO};font-size:26px;color:var(--accent);min-width:48px}
      .hl li{padding-bottom:16px;border-bottom:1px solid var(--line)}
      .works li{border-bottom:1px solid var(--line)}
      .works .n{font-family:${MONO};color:var(--accent);font-size:12px}
    `,
  },
  {
    idx: '024', id: 'variableTypography', name: '可变字体',
    vars: {
      paper: '#0a0a0a', card: '#141414', ink: '#f7f7f7', muted: '#8f8f8f',
      line: '#262626', accent: '#ff6b6b', accentInk: '#0a0a0a',
      body: SANS, display: SANS, dw: 900, ts: '88px', tl: '-0.045em', r: '8px',
    },
    css: `
      .title{font-weight:900}
      .title .thin{font-weight:200;color:#b9b9b9}
      .kicker{font-family:${MONO};color:#4ecdc4;letter-spacing:.18em}
      .sub{color:#f9ca24}
      .r1{height:4px;background:linear-gradient(90deg,#ff6b6b,#f9ca24 40%,#4ecdc4 75%,#a29bfe)}
      .r2{display:none}
      .stat b{font-weight:800}
      .stat span{color:#7d7d7d}
      .stat + .stat{border-left-color:#242424}
      .lead{color:#e6e6e6;font-weight:300;letter-spacing:-.01em}
      .sec-head{border-bottom-color:#242424}
      .sec-head h2{font-weight:800}
      .sec-en{color:#5a5a5a;font-family:${MONO}}
      .sec-no{color:#4ecdc4;font-family:${MONO}}
      .hl .n{font-weight:200;font-size:44px;min-width:64px;color:transparent;-webkit-text-stroke:1px #ff6b6b;line-height:1.1}
      .hl li:nth-child(2) .n{-webkit-text-stroke-color:#f9ca24}
      .hl li:nth-child(3) .n{-webkit-text-stroke-color:#4ecdc4}
      .hl li:nth-child(4) .n{-webkit-text-stroke-color:#a29bfe}
      .hl p{font-weight:350;color:#ededed}
      .works li{border-bottom-color:#1e1e1e}
      .works .n{font-family:${MONO};color:#5f5f5f}
      .works p{font-weight:350;color:#dcdcdc}
      .foot{color:#5a5a5a}
    `,
  },
  {
    idx: '054', id: 'minimalism', name: '极简主义',
    vars: {
      paper: '#ffffff', card: '#ffffff', ink: '#1a1a1a', muted: '#666666',
      line: '#e5e5e5', accent: '#1a1a1a', accentInk: '#ffffff',
      body: SANS, display: SANS, dw: 300, ts: '92px', tl: '-0.04em', r: '0',
    },
    css: `
      .page{padding:96px 84px 56px}
      .title{font-weight:350}
      .kicker{letter-spacing:.42em;font-size:11px;margin-bottom:26px}
      .sub{display:none}
      .r1{height:1px;background:#1a1a1a}
      .r2{display:none}
      .stats{margin-top:30px}
      .stat b{font-size:28px;font-weight:400}
      .stat span{letter-spacing:.2em;font-size:11px;margin-top:8px}
      .lead{font-size:26px;line-height:1.8;font-weight:300;margin-top:44px;max-width:860px;color:#2a2a2a}
      .sec{margin-top:64px}
      .sec-head{border-bottom:0;padding-bottom:0;margin-bottom:28px;align-items:center}
      .sec-head h2{font-size:13px;font-weight:500;letter-spacing:.4em;text-transform:uppercase}
      .sec-no{font-size:11px;color:#999;letter-spacing:.2em}
      .sec-en{display:none}
      .sec-head::after{content:"";flex:1;height:1px;background:#e5e5e5;margin-left:18px}
      .hl{gap:34px}
      .hl .n{font-size:12px;color:#999;min-width:34px;font-weight:400;padding-top:9px;letter-spacing:.08em}
      .hl p{font-size:21px;line-height:1.8;font-weight:300}
      .works li{border-bottom:0;padding:9px 0}
      .works .n{font-size:11px;color:#bbb;width:36px;padding-top:8px}
      .works p{font-size:18px;line-height:1.75;color:#333;font-weight:300}
    `,
  },
  {
    idx: '067', id: 'bentoGrid', name: '便当格风格',
    vars: {
      paper: '#fafaf7', card: '#ffffff', ink: '#1D1D1F', muted: '#6E6E73',
      line: '#e6e6e1', accent: '#0071E3', accentInk: '#ffffff',
      body: SANS, display: SANS, dw: 700, ts: '78px', tl: '-0.035em', r: '20px',
    },
    css: `
      .mast{align-items:center}
      .kicker{color:var(--accent)}
      .r1,.r2{display:none}
      .stats{margin-top:32px;gap:12px}
      .stat{flex:1;border-radius:16px;padding:20px 20px 18px;background:#FFF5D9}
      .stat:nth-child(2){background:#FFE8E8}
      .stat:nth-child(3){background:#E8F1FF}
      .stat:nth-child(4){background:#E9F7EC}
      .stat + .stat{border:0;padding-left:20px}
      .stat b{font-size:30px;letter-spacing:-.03em}
      .stat span{font-size:12px;letter-spacing:.04em;color:#4a4a4f}
      .lead{margin-top:16px;background:var(--ink);color:#fff;border-radius:20px;padding:32px 36px;font-size:22px;line-height:1.72}
      .sec{margin-top:40px}
      .sec-head{border:0;padding-bottom:0;margin-bottom:20px}
      .sec-head h2{font-size:25px;letter-spacing:-.02em}
      .sec-en{color:#a1a1a6}
      .hl{display:grid;grid-template-columns:1fr 1fr;gap:12px}
      .hl li{display:block;background:#fff;border-radius:16px;padding:22px 22px 24px}
      .hl li:nth-child(1){background:#FFF9EA}
      .hl li:nth-child(2){background:#FFF1F1}
      .hl li:nth-child(3){background:#EEF5FF}
      .hl li:nth-child(4){background:#EEF8F1}
      .hl .n{font-size:13px;color:var(--accent);min-width:0;margin-bottom:10px;font-weight:600;letter-spacing:.06em}
      .hl p{font-size:17.5px;line-height:1.65}
      .works{display:grid;grid-template-columns:1fr 1fr;gap:10px}
      .works li{display:block;background:#fff;border:0;border-radius:14px;padding:16px 18px;margin:0}
      .works .n{width:auto;font-size:11px;color:#a1a1a6;margin-bottom:8px;padding:0;letter-spacing:.06em}
      .works p{font-size:15.5px;line-height:1.6}
    `,
  },
  {
    idx: '077', id: 'warmCard', name: '温暖卡片',
    vars: {
      paper: '#f0eee6', card: '#fbf9f6', ink: '#4a403a', muted: '#6d635f',
      line: '#e2dbd0', accent: '#c96442', accentInk: '#ffffff',
      body: SANS, display: SERIF, dw: 700, ts: '80px', tl: '-0.01em', r: '16px',
    },
    css: `
      .title{font-family:${SERIF};font-weight:700;letter-spacing:.02em}
      .kicker{color:#a8988c}
      .r1{height:2px;background:var(--accent)}
      .r2{height:1px;background:#ded5c8;margin-top:5px}
      .stats{margin-top:26px}
      .stat b{color:#4a403a}
      .lead{margin-top:34px;background:var(--card);border-radius:16px;padding:30px 34px;font-size:22px;line-height:1.8;
        box-shadow:0 10px 30px -18px rgba(74,64,58,.35)}
      .sec{margin-top:46px}
      .sec-head{border-bottom:0;padding-bottom:0;margin-bottom:20px}
      .sec-head h2{font-family:${SERIF};font-size:27px;letter-spacing:.04em}
      .sec-no{color:#e09f3e}
      .hl li{background:var(--card);border-radius:16px;padding:22px 26px;gap:18px;box-shadow:0 10px 30px -20px rgba(74,64,58,.4)}
      .hl .n{font-family:${SERIF};color:var(--accent);font-size:26px;min-width:44px}
      .works li{background:var(--card);border:0;border-radius:14px;padding:15px 22px;margin-bottom:9px}
      .works .n{width:38px;padding-top:4px;color:#b8a99a}
    `,
  },
  {
    idx: '078', id: 'springFestival', name: '春节',
    vars: {
      paper: '#fdf6ec', card: '#fffdf8', ink: '#3a1c1c', muted: '#8a6a5e',
      line: '#e8d8c3', accent: '#b71c1c', accentInk: '#f7e3b5',
      body: SANS, display: SERIF, dw: 700, ts: '82px', tl: '0.02em', r: '22px',
    },
    css: `
      .page{background:
        radial-gradient(circle at 88% 4%, rgba(183,28,28,.10), transparent 42%),
        radial-gradient(circle at 6% 96%, rgba(212,175,55,.12), transparent 40%), #fdf6ec}
      .mast{background:var(--accent);color:#f7e3b5;border-radius:22px;padding:46px 44px 40px;align-items:flex-end;
        box-shadow:0 8px 24px -8px rgba(183,28,28,.35)}
      .mast .title{color:#fdf6ec;font-family:${SERIF};letter-spacing:.06em}
      .mast .kicker{color:#e6b98a}
      .mast .date{color:#f7e3b5}
      .mast .dow{color:#d9a97c}
      .mast .sub{color:#c98a5a}
      .rules{display:none}
      .stats{margin-top:24px;padding:0 4px}
      .stat b{color:var(--accent)}
      .stat span{color:#8a6a5e}
      .stat + .stat{border-left:1px solid #e8d8c3}
      .lead{margin-top:26px;font-size:22px;line-height:1.8;padding:26px 30px;border:1px solid #e8d8c3;border-radius:16px;background:rgba(255,255,255,.6)}
      .sec{margin-top:44px}
      .sec-head{border-bottom:1px solid #d4af37;padding-bottom:12px}
      .sec-head h2{font-family:${SERIF};letter-spacing:.1em;color:var(--accent)}
      .sec-no{color:#d4af37}
      .sec-en{color:#b99b6a}
      .hl li{padding:18px 22px;background:rgba(255,255,255,.65);border:1px solid #ecdcbe;border-radius:14px}
      .hl .n{color:#fff;background:var(--accent);width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;min-width:38px;margin-top:2px}
      .works li{border-bottom:1px dashed #e0cdb0}
      .works .n{color:#b71c1c;font-weight:700}
    `,
  },
  {
    idx: '081', id: 'hyperMinimal', name: '超极简风格',
    vars: {
      paper: '#ffffff', card: '#ffffff', ink: '#111111', muted: '#999999',
      line: '#e5e5e5', accent: '#111111', accentInk: '#ffffff',
      body: SANS, display: SANS, dw: 800, ts: '104px', tl: '-0.055em', r: '0',
    },
    css: `
      .page{padding:104px 76px 60px}
      .title{font-weight:800}
      .kicker{letter-spacing:.34em;font-size:11px;color:#bbb;margin-bottom:30px}
      .sub{display:none}
      .mast-right{padding-bottom:14px}
      .date{font-size:24px;font-weight:400;color:#666;letter-spacing:-.02em}
      .dow{font-size:11px;letter-spacing:.2em;color:#bbb}
      .r1{height:1px;background:#111}
      .r2{display:none}
      .stats{margin-top:34px}
      .stat b{font-size:26px;font-weight:600}
      .stat span{font-size:11px;letter-spacing:.2em;color:#aaa;margin-top:9px}
      .lead{margin-top:52px;font-size:25px;line-height:1.85;font-weight:300;color:#1c1c1c;max-width:880px;letter-spacing:-.005em}
      .sec{margin-top:70px}
      .sec-head{border-bottom:0;padding-bottom:0;margin-bottom:30px}
      .sec-head h2{font-size:14px;font-weight:500;letter-spacing:.34em}
      .sec-no{font-size:10px;color:#ccc;letter-spacing:.2em}
      .sec-en{display:none}
      .sec-head::after{content:"";flex:1;height:1px;background:#eee;margin-left:20px}
      .hl{gap:38px}
      .hl .n{font-size:11px;color:#ccc;min-width:32px;font-weight:400;padding-top:10px}
      .hl p{font-size:21px;line-height:1.8;font-weight:300;color:#222}
      .works li{border-bottom:0;padding:8px 0}
      .works .n{font-size:10px;color:#ccc;width:32px;padding-top:9px}
      .works p{font-size:17.5px;line-height:1.8;color:#333;font-weight:300}
      .foot{color:#ccc}
    `,
  },
  {
    idx: '106', id: 'wabiSabi', name: '侘寂美学',
    vars: {
      paper: '#f0ede8', card: '#f7f4ef', ink: '#3d3530', muted: '#6b5d52',
      line: '#d4cfc7', accent: '#8b7355', accentInk: '#f0ede8',
      body: SERIF, display: SERIF, dw: 400, ts: '80px', tl: '0.08em', r: '2px',
    },
    css: `
      .page{background:radial-gradient(circle at 34% 16%, rgba(139,115,85,.06), transparent 56%), #f0ede8}
      .mast-right::after{content:"侘";display:block;margin:18px 0 0 auto;width:44px;height:44px;
        border:1px solid #a89684;color:#8b7355;font-family:${SERIF};font-size:22px;line-height:42px;
        text-align:center;letter-spacing:0}
      .title{font-family:${SERIF};font-weight:400;letter-spacing:.1em}
      .kicker{font-family:${SERIF};color:#9a8b7c;letter-spacing:.3em}
      .sub{color:#a89684;letter-spacing:.4em}
      .r1{height:1px;background:#a89684}
      .r2{height:1px;background:#d4cfc7;margin-top:7px}
      .stat b{font-family:${SERIF};font-weight:400;font-size:28px}
      .stat span{letter-spacing:.18em;color:#8a7c6e}
      .lead{font-family:${SERIF};font-size:23px;line-height:1.95;color:#4a4038;margin-top:38px;letter-spacing:.02em}
      .sec{margin-top:56px}
      .sec-head{border-bottom:1px solid #c9c0b8;padding-bottom:12px}
      .sec-head h2{font-family:${SERIF};font-weight:400;letter-spacing:.16em;font-size:24px}
      .sec-no{color:#a89684;font-size:12px;letter-spacing:.2em}
      .sec-en{display:none}
      .hl{gap:26px}
      .hl .n{font-family:${SERIF};color:#8b7355;font-size:20px;min-width:42px;padding-top:4px}
      .hl p{font-family:${SERIF};font-size:20px;line-height:1.95;letter-spacing:.015em}
      .works li{border-bottom:1px solid #ddd8d0;padding:12px 0}
      .works .n{font-family:${SERIF};color:#a89684;width:40px;padding-top:5px}
      .works p{font-family:${SERIF};font-size:18.5px;line-height:1.85;letter-spacing:.015em}
    `,
  },
  {
    idx: '107', id: 'japandi', name: '日北融合',
    vars: {
      paper: '#faf9f6', card: '#ffffff', ink: '#2c2a27', muted: '#8b8179',
      line: '#eae8e3', accent: '#b5a694', accentInk: '#2c2a27',
      body: SANS, display: SANS, dw: 500, ts: '78px', tl: '-0.02em', r: '8px',
    },
    css: `
      .page{padding-top:0}
      .page::before{content:"";display:block;height:8px;margin:0 -64px 58px;background:#c4b49a}
      .title{font-weight:500;letter-spacing:-.02em}
      .kicker{color:#a69c8e;letter-spacing:.3em;font-size:11px}
      .r1{height:1px;background:#dad6ce}
      .r2{display:none}
      .stats{margin-top:26px;background:#f1ece2;border-radius:4px;padding:20px 22px}
      .stat b{font-weight:500;font-size:27px}
      .stat span{letter-spacing:.16em;font-size:11px;color:#a69c8e}
      .lead{margin-top:40px;font-size:23px;line-height:1.85;font-weight:300;color:#3a3835;max-width:900px}
      .sec{margin-top:56px}
      .sec-head{border-bottom:1px solid #dad6ce;padding-bottom:14px;margin-bottom:24px}
      .sec-head h2{font-weight:500;font-size:22px;letter-spacing:.08em}
      .sec-no{color:#c4b49a;font-size:11px;letter-spacing:.2em}
      .sec-en{color:#b5a694;font-size:10px;letter-spacing:.3em}
      .hl{gap:30px}
      .hl .n{font-size:12px;color:#b5a694;min-width:36px;padding-top:10px;letter-spacing:.1em}
      .hl p{font-size:20px;line-height:1.85;font-weight:300;color:#33312e}
      .works li{border-bottom:1px solid #efedE8;padding:12px 0}
      .works .n{font-size:11px;color:#b5a694;width:38px;padding-top:7px}
      .works p{font-size:18px;line-height:1.8;font-weight:300;color:#3a3835}
    `,
  },
  {
    idx: '108', id: 'midCenturyModern', name: '中世纪现代',
    vars: {
      paper: '#f4e8d8', card: '#fbf3e7', ink: '#1a1510', muted: '#6d5f4c',
      line: '#d4c5b0', accent: '#e67e50', accentInk: '#1a1510',
      body: SANS, display: GEO, dw: 700, ts: '84px', tl: '-0.01em', r: '12px',
    },
    css: `
      .page{background:
        radial-gradient(circle at 92% 6%, rgba(74,144,164,.18), transparent 34%),
        radial-gradient(circle at 84% 10%, rgba(230,126,80,.20), transparent 26%), #f4e8d8}
      .title{font-family:${GEO};font-weight:700}
      .kicker{color:#8a6f52;letter-spacing:.3em;font-size:11px}
      .r1{height:5px;background:#1a1510}
      .r2{height:1px;background:#1a1510;margin-top:5px}
      .stat b{font-family:${GEO};font-size:32px}
      .stat span{letter-spacing:.14em;color:#7d6b55}
      .lead{margin-top:32px;font-size:22px;line-height:1.78;border-left:6px solid var(--accent);padding-left:24px}
      .sec{margin-top:50px}
      .sec-head{border-bottom:2px solid #1a1510;padding-bottom:10px}
      .sec-head h2{font-family:${GEO};font-size:27px;letter-spacing:.01em}
      .sec-no{font-family:${GEO};color:#e67e50;font-size:16px}
      .sec-en{color:#8a6f52}
      .hl .n{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;
        background:#e67e50;color:#1a1510;font-size:16px;min-width:44px;font-weight:700;margin-top:2px}
      .hl li:nth-child(2) .n{background:#4a90a4;color:#fff}
      .hl li:nth-child(3) .n{background:#5da862;color:#fff}
      .hl li:nth-child(4) .n{background:#d4a574;color:#1a1510}
      .hl p{font-size:20px;line-height:1.7}
      .works li{border-bottom:1px solid #d4c5b0;padding:12px 0}
      .works .n{font-family:${GEO};color:#8a6f52;width:40px;padding-top:4px}
      .works p{font-size:18px;line-height:1.72}
    `,
  },
  {
    idx: '111', id: 'braunFunctional', name: '功能主义工业设计',
    vars: {
      paper: '#fafafa', card: '#ffffff', ink: '#1a1a1a', muted: '#6e6e6e',
      line: '#e5e5e5', accent: '#ff6b00', accentInk: '#ffffff',
      body: SANS, display: SANS, dw: 700, ts: '80px', tl: '-0.04em', r: '0px',
    },
    css: `
      .kicker{font-family:${MONO};color:#8a8a8a;letter-spacing:.22em;font-size:11px}
      .kicker b{color:var(--accent)}
      .r1{height:3px;background:#1a1a1a}
      .r2{height:1px;background:#dcdcdc;margin-top:4px}
      .stats{margin-top:24px;border:1px solid #1a1a1a;border-radius:0}
      .stat{padding:18px 20px}
      .stat + .stat{border-left:1px solid #1a1a1a}
      .stat b{font-size:30px;letter-spacing:-.03em}
      .stat span{font-size:11px;letter-spacing:.16em;color:#7a7a7a}
      .lead{margin-top:26px;font-size:21px;line-height:1.75;padding-left:16px;border-left:3px solid var(--accent)}
      .sec{margin-top:46px}
      .sec-head{border-bottom:2px solid #1a1a1a;padding-bottom:9px}
      .sec-head h2{font-size:22px;letter-spacing:.1em}
      .sec-no{background:var(--accent);color:#fff;font-size:11px;padding:3px 7px;font-family:${MONO}}
      .sec-en{font-family:${MONO};font-size:10px;letter-spacing:.24em}
      .hl .n{font-family:${MONO};color:var(--accent);font-size:28px;min-width:52px;line-height:1.15}
      .hl li{border-bottom:1px solid #e5e5e5;padding-bottom:16px}
      .works{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid #1a1a1a;border-left:1px solid #1a1a1a}
      .works li{border:0;border-right:1px solid #1a1a1a;border-bottom:1px solid #1a1a1a;padding:14px 16px;display:block}
      .works .n{width:auto;font-family:${MONO};font-size:10px;color:#9a9a9a;margin-bottom:6px;padding:0;letter-spacing:.1em}
      .works p{font-size:15.5px;line-height:1.6}
    `,
  },
  {
    idx: '112', id: 'mujiAnonymous', name: '无品牌极简',
    vars: {
      paper: '#fafaf8', card: '#f4f3f0', ink: '#3e3c3a', muted: '#8b8179',
      line: '#e3e0d9', accent: '#8b4513', accentInk: '#fafaf8',
      body: SANS, display: SANS, dw: 400, ts: '72px', tl: '0.14em', r: '0px',
    },
    css: `
      .mast{border:1px solid #d9d5cc;padding:34px 32px 30px;align-items:flex-end}
      .title{font-weight:400;letter-spacing:.18em}
      .kicker{letter-spacing:.3em;font-size:10px;color:#9c948a;margin-bottom:16px}
      .sub{letter-spacing:.46em;font-size:10px;color:#b0a79c}
      .date{font-size:22px;font-weight:400;letter-spacing:.06em;color:#5c574f}
      .dow{font-size:10px;letter-spacing:.2em}
      .rules{display:none}
      .stats{margin-top:0;border:1px solid #d9d5cc;border-top:0;padding:20px 32px}
      .stat b{font-size:25px;font-weight:400}
      .stat span{font-size:10px;letter-spacing:.2em;color:#a39a90;margin-top:7px}
      .stat + .stat{border-left:1px solid #e3e0d9;padding-left:22px}
      .lead{margin-top:36px;font-size:21px;line-height:1.9;font-weight:300;color:#45423e;letter-spacing:.02em}
      .sec{margin-top:52px}
      .sec-head{border-bottom:1px solid #d9d5cc;padding-bottom:10px}
      .sec-head h2{font-size:16px;font-weight:400;letter-spacing:.32em}
      .sec-no{color:#b0a79c;font-size:10px;letter-spacing:.2em}
      .sec-en{font-size:9px;letter-spacing:.3em;color:#b0a79c}
      .hl{gap:26px}
      .hl .n{font-size:10px;color:#8b4513;min-width:32px;padding-top:9px;letter-spacing:.14em}
      .hl p{font-size:19px;line-height:1.9;font-weight:300;letter-spacing:.02em}
      .works li{border-bottom:1px solid #e9e6df;padding:12px 0}
      .works .n{font-size:10px;color:#b0a79c;width:34px;padding-top:7px;letter-spacing:.1em}
      .works p{font-size:17.5px;line-height:1.8;font-weight:300;letter-spacing:.02em;color:#45423e}
    `,
  },
  {
    idx: '140', id: 'sumiStyle', name: '墨绘',
    vars: {
      paper: '#fafafa', card: '#ffffff', ink: '#1a1a1a', muted: '#5d5d5d',
      line: '#dcdcdc', accent: '#b9382b', accentInk: '#ffffff',
      body: SERIF, display: SERIF, dw: 700, ts: '86px', tl: '0.06em', r: '0px',
    },
    css: `
      .page{background:radial-gradient(ellipse 66% 24% at 24% 8%, rgba(26,26,26,.10), transparent 62%), #fafafa}
      .mast-right::after{content:"聲";display:block;margin:16px 0 0 auto;width:46px;height:46px;
        background:var(--accent);color:#fff;font-family:${SERIF};font-size:24px;line-height:46px;
        text-align:center;border-radius:2px;letter-spacing:0}
      .title{font-family:${SERIF};font-weight:700;letter-spacing:.1em}
      .kicker{font-family:${SERIF};color:#7a7a7a;letter-spacing:.28em}
      .sub{color:#9a9a9a;letter-spacing:.4em}
      .r1{height:3px;background:#1a1a1a}
      .r2{height:1px;background:#c9c9c9;margin-top:5px}
      .stat b{font-family:${SERIF};font-size:30px}
      .stat span{letter-spacing:.16em}
      .lead{font-family:${SERIF};font-size:23px;line-height:1.9;margin-top:34px;letter-spacing:.02em;color:#2a2a2a}
      .sec{margin-top:52px}
      .sec-head{border-bottom:2px solid #1a1a1a;padding-bottom:10px}
      .sec-head h2{font-family:${SERIF};font-size:26px;letter-spacing:.2em;font-weight:700}
      .sec-no{color:var(--accent);font-size:12px;letter-spacing:.14em}
      .sec-en{display:none}
      .hl .n{font-family:${SERIF};color:var(--accent);font-size:22px;min-width:44px;padding-top:3px;font-weight:700}
      .hl p{font-family:${SERIF};font-size:20px;line-height:1.85;letter-spacing:.015em}
      .works li{border-bottom:1px solid #dcdcdc;padding:12px 0}
      .works .n{font-family:${SERIF};color:var(--accent);width:38px;padding-top:4px;font-size:13px}
      .works p{font-family:${SERIF};font-size:18.5px;line-height:1.8;letter-spacing:.015em}
      .foot{border-top:2px solid #1a1a1a;padding-top:14px}
    `,
  },
  {
    idx: '151', id: 'etchingStyle', name: '铜版蚀刻',
    vars: {
      paper: '#f5f3f0', card: '#fcfaf7', ink: '#2a2826', muted: '#5a5856',
      line: '#d0ccc4', accent: '#2a2826', accentInk: '#f5f3f0',
      body: SERIF, display: GEO, dw: 700, ts: '82px', tl: '0.02em', r: '0px',
    },
    css: `
      .mast{border:1px solid #2a2826;padding:30px 32px 26px;position:relative}
      .mast::before{content:"";position:absolute;inset:5px;border:1px solid #c8c3ba;pointer-events:none}
      .title{font-family:${GEO};letter-spacing:.03em}
      .kicker{font-family:${GEO};letter-spacing:.26em;font-size:11px;color:#6f6a63;font-style:italic}
      .sub{letter-spacing:.4em;font-size:10px;color:#8b857c}
      .date{font-family:${GEO};font-size:24px;font-weight:400}
      .rules{display:none}
      .stats{margin-top:18px;padding:16px 4px;border-bottom:1px solid #d0ccc4}
      .stat b{font-family:${GEO};font-size:27px;font-weight:400}
      .stat span{font-size:10px;letter-spacing:.2em;color:#7c766e}
      .lead{margin-top:26px;font-family:${SERIF};font-size:22px;line-height:1.9;font-style:normal;color:#33302c}
      .sec{margin-top:46px}
      .sec-head{border-bottom:1px solid #2a2826;padding-bottom:9px}
      .sec-head h2{font-family:${GEO};font-size:24px;letter-spacing:.06em}
      .sec-no{font-family:${GEO};color:#7c766e;font-style:italic}
      .sec-en{font-family:${GEO};font-style:italic;letter-spacing:.2em;color:#8b857c}
      .hl .n{font-family:${GEO};font-style:italic;color:#2a2826;font-size:26px;min-width:46px}
      .hl p{font-size:19.5px;line-height:1.85;font-family:${SERIF}}
      .works li{border-bottom:1px dotted #b9b3a9;padding:11px 0}
      .works .n{font-family:${GEO};font-style:italic;color:#7c766e;width:40px;padding-top:5px}
      .works p{font-family:${SERIF};font-size:18px;line-height:1.8}
      .foot{border-top:1px solid #2a2826;padding-top:12px;font-family:${GEO};font-style:italic}
      .page::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:.5;
        background:repeating-linear-gradient(135deg, rgba(42,40,38,.028) 0 1px, transparent 1px 5px)}
    `,
  },
  {
    idx: '159', id: 'cleanLineComic', name: '清线漫画',
    vars: {
      paper: '#ffffff', card: '#ffffff', ink: '#1a1a1a', muted: '#5a5a5a',
      line: '#1a1a1a', accent: '#1a1a1a', accentInk: '#ffffff',
      body: KAI, display: KAI, dw: 700, ts: '84px', tl: '0.02em', r: '2px',
    },
    css: `
      .page{background:
        radial-gradient(circle, rgba(26,26,26,.13) 1px, transparent 1.2px) 0 0/10px 10px,
        #fff}
      .mast{border:2px solid #1a1a1a;padding:28px 30px 24px;background:#fff;align-items:flex-end}
      .title{font-family:${KAI};font-weight:700;letter-spacing:.03em}
      .kicker{font-family:${KAI};color:#4a4a4a;letter-spacing:.24em}
      .sub{font-family:${GEO};letter-spacing:.34em;font-size:10px;color:#777}
      .rules{display:none}
      .stats{margin-top:14px;border:2px solid #1a1a1a;border-top:0;padding:18px 24px;background:#fff}
      .stat b{font-family:${KAI};font-size:28px}
      .stat span{font-family:${KAI};letter-spacing:.14em;color:#666}
      .lead{margin-top:22px;font-family:${KAI};font-size:22px;line-height:1.85;border:2px solid #1a1a1a;padding:22px 26px;background:#fff}
      .sec{margin-top:44px}
      .sec-head{border-bottom:2px solid #1a1a1a;padding-bottom:8px}
      .sec-head h2{font-family:${KAI};font-size:26px;letter-spacing:.08em}
      .sec-no{font-family:${GEO};color:#1a1a1a;font-size:13px}
      .sec-en{font-family:${GEO};font-size:10px;letter-spacing:.24em;color:#777}
      .hl li{border:2px solid #1a1a1a;padding:18px 22px;background:#fff;gap:18px}
      .hl .n{font-family:${GEO};width:38px;height:38px;border:2px solid #1a1a1a;border-radius:50%;
        display:flex;align-items:center;justify-content:center;font-size:14px;min-width:38px;margin-top:2px}
      .hl p{font-family:${KAI};font-size:20px;line-height:1.8}
      .works li{border-bottom:1px solid #c9c9c9;padding:11px 0}
      .works .n{font-family:${GEO};color:#8a8a8a;width:38px;padding-top:6px}
      .works p{font-family:${KAI};font-size:18.5px;line-height:1.78}
    `,
  },
  {
    idx: '166', id: 'limitedAnimation', name: '有限动画',
    vars: {
      paper: '#dfe6e9', card: '#ffffff', ink: '#2d3436', muted: '#636e72',
      line: '#b2bec3', accent: '#a29bfe', accentInk: '#2d3436',
      body: SANS, display: SANS, dw: 800, ts: '82px', tl: '-0.03em', r: '0px',
    },
    css: `
      .mast{background:var(--accent);padding:40px 38px 34px;align-items:flex-end;
        box-shadow:8px 8px 0 #2d3436}
      .mast .title{color:#2d3436}
      .mast .kicker{color:#4b4470}
      .mast .sub{color:#4b4470;letter-spacing:.3em}
      .mast .date{color:#2d3436;font-weight:800}
      .mast .dow{color:#4b4470}
      .rules{display:none}
      .stats{margin-top:26px;gap:10px}
      .stat{background:#fff;border:0;padding:16px 18px;box-shadow:4px 4px 0 #2d3436}
      .stat:nth-child(2){background:#74b9ff}
      .stat:nth-child(3){background:#55efc4}
      .stat:nth-child(4){background:#ffeaa7}
      .stat + .stat{border:0;padding-left:18px}
      .stat b{font-size:26px}
      .stat span{font-size:11px;letter-spacing:.1em;color:#2d3436;text-transform:uppercase}
      .lead{margin-top:26px;background:#fff;padding:26px 30px;font-size:21px;line-height:1.75;box-shadow:6px 6px 0 #2d3436}
      .sec{margin-top:44px}
      .sec-head{border-bottom:0;padding-bottom:0;margin-bottom:18px}
      .sec-head h2{font-size:22px;letter-spacing:.16em;text-transform:uppercase;background:#2d3436;color:#fff;padding:6px 12px}
      .sec-no{color:#2d3436;font-size:13px;font-weight:800}
      .sec-en{color:#636e72;font-size:10px;letter-spacing:.24em}
      .hl{gap:14px}
      .hl li{background:#fff;padding:18px 22px;box-shadow:5px 5px 0 #2d3436;gap:16px}
      .hl li:nth-child(2){background:#74b9ff}
      .hl li:nth-child(3){background:#55efc4}
      .hl li:nth-child(4){background:#ffeaa7}
      .hl .n{font-size:24px;font-weight:800;color:#2d3436;min-width:40px;line-height:1.2}
      .hl p{font-size:19px;line-height:1.65;font-weight:500}
      .works li{background:#fff;border:0;padding:14px 18px;margin-bottom:8px;box-shadow:4px 4px 0 #b2bec3}
      .works .n{width:34px;font-weight:800;color:#636e72;padding-top:4px}
      .works p{font-size:17.5px;line-height:1.65;font-weight:400}
    `,
  },
  {
    idx: '172', id: 'stopMotion', name: '定格',
    vars: {
      paper: '#e8dcc4', card: '#f5f0e6', ink: '#3d2914', muted: '#6b5233',
      line: '#c9b896', accent: '#d4a574', accentInk: '#3d2914',
      body: SANS, display: SANS, dw: 700, ts: '80px', tl: '-0.01em', r: '4px',
    },
    css: `
      .page{background:
        repeating-linear-gradient(92deg, rgba(61,41,20,.035) 0 2px, transparent 2px 7px), #e8dcc4}
      .mast{background:#f5f0e6;padding:38px 36px 32px;border:2px solid #3d2914;align-items:flex-end;
        box-shadow:8px 8px 0 rgba(61,41,20,.22), 4px 4px 0 rgba(61,41,20,.14)}
      .title{font-weight:700}
      .kicker{font-family:${MONO};color:#8b7355;letter-spacing:.2em;font-size:11px}
      .sub{font-family:${MONO};letter-spacing:.3em;color:#a0926b;font-size:10px}
      .date{font-family:${MONO};font-weight:700}
      .dow{font-family:${MONO};color:#8b7355;font-size:11px}
      .rules{display:none}
      .stats{margin-top:26px}
      .stat{background:rgba(245,240,230,.75);border:1px dashed #b8a88a;padding:14px 16px}
      .stat + .stat{border-left:1px dashed #b8a88a;padding-left:16px;margin-left:8px}
      .stat b{font-size:26px}
      .stat span{font-size:11px;letter-spacing:.1em;color:#6b5233}
      .lead{margin-top:26px;background:#f5f0e6;border:2px solid #3d2914;padding:26px 30px;font-size:21px;line-height:1.8;
        box-shadow:4px 4px 0 rgba(61,41,20,.16)}
      .sec{margin-top:46px}
      .sec-head{border-bottom:2px dashed #3d2914;padding-bottom:10px}
      .sec-head h2{font-size:24px;letter-spacing:.06em}
      .sec-no{background:#3d2914;color:#e8dcc4;padding:2px 8px;font-family:${MONO};font-size:11px}
      .sec-en{font-family:${MONO};font-size:10px;letter-spacing:.2em;color:#8b7355}
      .hl{gap:14px}
      .hl li{background:#f5f0e6;border:2px solid #3d2914;padding:18px 22px;gap:16px;box-shadow:3px 3px 0 rgba(61,41,20,.18)}
      .hl .n{font-family:${MONO};font-size:22px;color:#8b4513;min-width:44px;line-height:1.25}
      .hl p{font-size:19px;line-height:1.75}
      .works li{background:rgba(245,240,230,.7);border:0;border-bottom:1px dashed #b8a88a;padding:12px 14px}
      .works .n{font-family:${MONO};color:#8b7355;width:36px;padding-top:5px}
      .works p{font-size:17.5px;line-height:1.7}
    `,
  },
];

/* ------------------------------------------------------------------ HTML */

const BASE_CSS = `
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px}
body{background:var(--paper);color:var(--ink);font-family:var(--body);font-size:19px;line-height:1.7;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.page{position:relative;width:1080px;min-height:1560px;padding:72px 64px 48px;display:flex;flex-direction:column;overflow:hidden}
.mast{display:flex;justify-content:space-between;align-items:flex-end;gap:36px}
.kicker{font-size:13px;letter-spacing:.26em;color:var(--muted);margin-bottom:18px;text-transform:uppercase}
.title{font-family:var(--display);font-weight:var(--dw);font-size:var(--ts);line-height:1.04;
  letter-spacing:var(--tl);color:var(--ink);white-space:nowrap}
.sub{font-size:11px;letter-spacing:.34em;color:var(--muted);margin-top:14px;text-transform:uppercase}
.mast-right{text-align:right;flex:none;padding-bottom:6px}
.date{font-size:28px;font-weight:700;letter-spacing:-.01em;font-variant-numeric:tabular-nums;white-space:nowrap}
.dow{font-size:12px;color:var(--muted);margin-top:8px;letter-spacing:.1em;white-space:nowrap}
.rules{margin-top:26px}
.rules i{display:block}
.r1{height:6px;background:var(--ink)}
.r2{height:1px;background:var(--line);margin-top:6px}
.stats{display:flex;margin-top:22px}
.stat{flex:1}
.stat b{display:block;font-size:30px;line-height:1.15;font-variant-numeric:tabular-nums}
.stat span{display:block;font-size:12px;color:var(--muted);margin-top:6px;letter-spacing:.1em}
.stat + .stat{border-left:1px solid var(--line);padding-left:24px}
.lead{margin-top:34px;font-size:23px;line-height:1.75}
.lead,.hl p,.works p{text-wrap:pretty}
.sec{margin-top:52px}
.sec-head{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:24px}
.sec-no{font-size:13px;color:var(--accent);letter-spacing:.1em;font-weight:700}
.sec-head h2{font-size:26px;font-weight:700;letter-spacing:.02em;line-height:1.3}
.sec-en{margin-left:auto;font-size:10px;letter-spacing:.26em;color:var(--muted);text-transform:uppercase}
.hl{list-style:none;display:flex;flex-direction:column;gap:18px}
.hl li{display:flex;gap:20px;align-items:flex-start}
.hl .n{flex:none;font-size:30px;font-weight:700;line-height:1.2;color:var(--accent);font-variant-numeric:tabular-nums;min-width:52px}
.hl p{font-size:20px;line-height:1.7}
.works{list-style:none;display:flex;flex-direction:column}
.works li{display:flex;gap:18px;padding:13px 0;border-bottom:1px solid var(--line)}
.works .n{flex:none;width:44px;font-size:13px;color:var(--muted);padding-top:6px;font-variant-numeric:tabular-nums}
.works p{font-size:18.5px;line-height:1.68}
.foot{margin-top:auto;padding-top:40px;display:flex;justify-content:space-between;align-items:flex-end;
  font-size:11px;color:var(--muted);letter-spacing:.08em;gap:20px}
`;

function buildHtml(style) {
  const vars = Object.entries(style.vars).map(([k, v]) => `--${k}:${v}`).join(';');
  const statsHtml = stats
    .map(([n, l]) => `<div class="stat"><b>${esc(n)}</b><span>${esc(l)}</span></div>`)
    .join('');
  const hlHtml = highlights
    .map((t, i) => `<li><span class="n">${String(i + 1).padStart(2, '0')}</span><p>${esc(t)}</p></li>`)
    .join('');
  const worksHtml = works
    .map((t, i) => `<li><span class="n">${String(i + 1).padStart(2, '0')}</span><p>${esc(t)}</p></li>`)
    .join('');

  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>${esc(kindLabel)} ${dateISO} · ${style.id}</title>
<style>${BASE_CSS}
body{${vars}}
${style.css}
</style></head>
<body>
<div class="page">
  <header class="mast">
    <div class="mast-left">
      <div class="kicker">声優Xまとめ · 第 ${esc(issue.id || ISSUE)} 期</div>
      <h1 class="title">${esc(kindLabel)}</h1>
      <div class="sub">${esc(kindEn)}</div>
    </div>
    <div class="mast-right">
      <div class="date">${Y}.${M}.${D}</div>
      <div class="dow">${WEEK} · 覆盖全天 JST</div>
    </div>
  </header>

  <div class="rules"><i class="r1"></i><i class="r2"></i></div>

  <div class="stats">${statsHtml}</div>

  <p class="lead">${esc(report.description || '')}</p>

  <section class="sec">
    <div class="sec-head"><span class="sec-no">01</span><h2>今日要点</h2><span class="sec-en">Highlights</span></div>
    <ol class="hl">${hlHtml}</ol>
  </section>

  <section class="sec">
    <div class="sec-head"><span class="sec-no">02</span><h2>作品消息</h2><span class="sec-en">Works</span></div>
    <ul class="works">${worksHtml}</ul>
  </section>

  <footer class="foot">
    <span>${esc(kindLabel)} · ${esc(issue.id || ISSUE)} · 发布于 ${esc(published)} JST</span>
    <span>${esc(String(counts.items ?? ''))} 条动态 / ${esc(String(counts.accounts ?? ''))} 个账号</span>
  </footer>
</div>
</body></html>`;
}

/* ------------------------------------------------------------------ 渲染 */

fs.mkdirSync(OUT, { recursive: true });

const picked = ONLY ? STYLES.filter((s) => ONLY.split(',').includes(s.idx)) : STYLES;
const browser = await chromium.launch({ channel: 'msedge', args: ['--font-render-hinting=none'] });
const page = await browser.newPage({ viewport: { width: 1080, height: 1200 }, deviceScaleFactor: 2 });

const rows = [];
for (const s of picked) {
  const html = buildHtml(s);
  const tmp = path.join(OUT, `.${s.idx}.html`);
  fs.writeFileSync(tmp, html, 'utf8');
  await page.goto('file://' + tmp.replace(/\\/g, '/'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(120);
  const file = path.join(OUT, `${s.idx}-${s.id}.png`);
  await page.screenshot({ path: file, fullPage: true });
  const box = await page.evaluate(() => {
    const el = document.querySelector('.page');
    return { h: Math.round(el.getBoundingClientRect().height) };
  });
  fs.unlinkSync(tmp);
  rows.push({ ...s, file: path.basename(file), h: box.h });
  console.log(`${s.idx} ${s.id.padEnd(20)} ${box.h}px  ${(fs.statSync(file).size / 1024).toFixed(0)}KB`);
}
await browser.close();

/* ------------------------------------------------------------------ 联络表 */

const cards = rows
  .map(
    (r) => `<a class="c" href="${r.file}" target="_blank">
    <div class="im"><img src="${r.file}" alt="${r.id}" loading="lazy"></div>
    <div class="meta"><span class="no">${r.idx}</span><b>${r.id}</b><span class="nm">${r.name}</span></div>
  </a>`,
  )
  .join('\n');

fs.writeFileSync(
  path.join(OUT, 'index.html'),
  `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>竖版日报 · ${ISSUE}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#f5f5f3;color:#1a1a1a;font-family:"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif;padding:48px 40px 80px}
h1{font-size:26px;font-weight:700;letter-spacing:-.01em}
p.sub{color:#767676;font-size:13px;margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:26px;margin-top:32px}
.c{text-decoration:none;color:inherit;display:block}
.im{background:#fff;border:1px solid #e5e5e5;border-radius:6px;overflow:hidden;aspect-ratio:1080/1560}
.im img{width:100%;height:100%;object-fit:cover;object-position:top;display:block}
.c:hover .im{border-color:#1a1a1a}
.meta{display:flex;align-items:baseline;gap:8px;margin-top:10px;font-size:13px;flex-wrap:wrap}
.no{color:#767676;font-variant-numeric:tabular-nums}
.meta b{font-weight:600}
.nm{color:#767676;font-size:12px}
</style></head><body>
<h1>竖版日报 · ${esc(issue.id || ISSUE)}</h1>
<p class="sub">18 套模板的配色与排版语言 · 题目 / 今日要点 / 作品消息 · 点击看原图</p>
<div class="grid">${cards}</div>
</body></html>`,
  'utf8',
);

console.log(`\n→ ${OUT}`);
