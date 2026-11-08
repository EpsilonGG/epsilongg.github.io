/**
 * 每日晨报长图 —— 竖版（1080 宽，高度随内容）。
 *
 * 视觉方案：blackWhiteEditorial（黑白社论）为主体骨架，借 editorialMagazine 的
 * 报头/刊号/导语版式，新作清单用 swissStyle 的编号网格。三者的共同点是不依赖
 * 装饰色与阴影，只靠字重、字号、发丝线做层级——和站点 tokens 的黑白灰一致。
 *
 * 四块：报头 + 数据条 → 导语（反白块）→ 今日看点（编号）→ 新作热作（双栏平衡）。
 *
 * 用法：node morning-paper.mjs <report.json> [out.png]
 * 字体：默认本机 Windows 雅黑；CI/生产用 OG_FONTS 指向全量 Noto Sans SC。
 */
import { Resvg } from '@resvg/resvg-js';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

// 生产必须按 M5.2 固定一份「全量」CJK 字体（5–15 MB）。og-demo 里的 NotoSub-*.ttf 是子集，
// 只含样例那几个字，正文会大面积丢字，绝不能拿来出日报图。
const SYS_FONTS = ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/msyhbd.ttc'];
const FONTS = (process.env.OG_FONTS ? process.env.OG_FONTS.split(',') : SYS_FONTS).map((f) => f.trim());
const FAMILY = process.env.OG_FAMILY || 'Microsoft YaHei';

// ---- 站点 tokens（src/styles/tokens.css 的浅色主题）----
const W = 1080;
const PAD = 64;
const CW = W - PAD * 2;
const INK = '#1a1a1a'; // --color-text
const SUB = '#555555'; // --color-text-secondary
const MUTED = '#767676'; // --color-text-muted
const LINE = '#e5e5e5'; // --color-border
const STRONG = '#cfcfcf'; // --color-border-strong
const SUBTLE = '#f7f7f7'; // --color-bg-subtle

// ---- 文本度量（CJK 等宽 1em，西文按经验宽度）----
const charW = (ch) => {
  const c = ch.codePointAt(0);
  if (ch === ' ') return 0.28;
  if (c >= 0x2e80) return 1.0; // CJK / 假名 / 全角标点
  if (/[iIl1.,:;'!|]/.test(ch)) return 0.3;
  if (/[A-Z]/.test(ch)) return 0.64;
  if (/[0-9]/.test(ch)) return 0.56;
  return 0.54;
};
const textW = (s, size) => [...s].reduce((n, ch) => n + charW(ch), 0) * size;
const CLOSE = '」』）】》〉、，。；：？！…—・';
const OPEN = '「『（【《〈';

/** 西文单词/数字串整体不拆行（FANZA GAMES 不能断成 FANZA GA / MES）。 */
function tokenize(str) {
  const chars = [...str];
  const out = [];
  let buf = '';
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    const isAlnum = /[A-Za-z0-9]/.test(ch);
    // 单词内部的连接符：后面还跟字母/数字才算（句末的句号不算）
    const isJoiner = buf && /[.'’\-/&]/.test(ch) && /[A-Za-z0-9]/.test(chars[i + 1] || '');
    if (isAlnum || isJoiner) {
      buf += ch;
    } else {
      if (buf) {
        out.push(buf);
        buf = '';
      }
      out.push(ch);
    }
  }
  if (buf) out.push(buf);
  return out;
}

function wrap(text, size, maxWidth) {
  const tokens = tokenize(text);
  const lines = [];
  let line = '';
  let width = 0;
  const flush = () => {
    if (line) lines.push(line);
    line = '';
    width = 0;
  };
  for (const tk of tokens) {
    const tw = textW(tk, size);
    if (!line) {
      // 行首超长单词：退回按字切
      if (tw > maxWidth && [...tk].length > 1) {
        for (const ch of tk) {
          const cw = charW(ch) * size;
          if (width + cw > maxWidth && line) flush();
          line += ch;
          width += cw;
        }
      } else {
        line = tk;
        width = tw;
      }
      continue;
    }
    if (width + tw <= maxWidth) {
      line += tk;
      width += tw;
      continue;
    }
    // 行首禁则：闭合标点挂在上一行尾（允许溢出半个字）
    if (CLOSE.includes(tk)) {
      line += tk;
      flush();
      continue;
    }
    // 行尾禁则：开引号不留在行末
    let tail = '';
    while (OPEN.includes(line.slice(-1))) {
      tail = line.slice(-1) + tail;
      line = line.slice(0, -1);
    }
    flush();
    line = tail + tk;
    width = textW(line, size);
  }
  flush();
  return lines;
}

/** 超长文案：截断加 …，不缩字号（字号层级必须统一）。 */
function fit(text, size, maxWidth, maxLines) {
  const lines = wrap(text, size, maxWidth);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  let last = kept[maxLines - 1];
  while (textW(last + '…', size) > maxWidth && last.length > 1) last = last.slice(0, -1);
  kept[maxLines - 1] = last + '…';
  return kept;
}

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const parts = [];
let y = 0;

const text = (x, yy, size, weight, fill, str, opts = {}) => {
  const { anchor = 'start', track = 0 } = opts;
  const ls = track ? ` letter-spacing="${(track * size).toFixed(2)}"` : '';
  return `<text x="${x}" y="${yy}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}"${ls}>${esc(str)}</text>`;
};
const rule = (yy, color = LINE, sw = 1, x1 = PAD, x2 = W - PAD) =>
  `<line x1="${x1}" y1="${yy}" x2="${x2}" y2="${yy}" stroke="${color}" stroke-width="${sw}"/>`;
const vrule = (xx, y1, y2, color = LINE) =>
  `<line x1="${xx}" y1="${y1}" x2="${xx}" y2="${y2}" stroke="${color}" stroke-width="1"/>`;
const box = (x, yy, w, h, fill, radius = 0) =>
  `<rect x="${x}" y="${yy}" width="${w}" height="${h}" rx="${radius}" fill="${fill}"/>`;

// ---- 解析 report.json ----
const report = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const id = report.issue.id;
const mm = id.match(/^(\d{2})(\d{2})(\d{2})(?:-g\d*)?$/);
if (!mm) throw new Error(`期号不合法：${id}`);
const year = 2000 + parseInt(mm[1], 10);
const month = parseInt(mm[2], 10);
const day = parseInt(mm[3], 10);
const isGal = id.includes('-g');
const kindLabel = isGal ? 'Galgame 日报' : '声优日报';
const dateDot = `${year}.${String(month).padStart(2, '0')}.${String(day).padStart(2, '0')}`;
const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
const weekday = WEEK[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
const dateCn = `${year} 年 ${month} 月 ${day} 日`;
const counts = report.counts || {};

// ---- 报头 ----
y = 64;
parts.push(text(PAD, y, 18, 600, MUTED, 'EPSILONGG · DAILY', { track: 0.16 }));
parts.push(text(W - PAD, y, 18, 600, MUTED, `NO. ${id}`, { anchor: 'end', track: 0.16 }));
y = 76;
parts.push(rule(y, STRONG, 1));

y = 178;
parts.push(text(PAD, y, 92, 700, INK, kindLabel));
parts.push(text(W - PAD, y - 34, 42, 700, INK, dateDot, { anchor: 'end' }));
parts.push(text(W - PAD, y, 18, 400, MUTED, `${weekday} · 覆盖 ${month}-${String(day).padStart(2, '0')} 全天（JST）`, { anchor: 'end' }));

// 双线（报头压线）
y = 208;
parts.push(rule(y, INK, 7));
y = 221;
parts.push(rule(y, INK, 1));

// ---- 数据条（标签在上、数字在下：竖排避开数字宽度不可测的问题）----
const stats = [
  [String(counts.items ?? '—'), '条动态'],
  [String(counts.accounts ?? '—'), '个账号'],
  [String((report.highlights || []).length), '条看点'],
  [String((report.works || []).length), '条新作'],
];
const cell = CW / stats.length;
stats.forEach(([num, label], i) => {
  const x = PAD + cell * i;
  parts.push(text(x, 262, 34, 700, INK, num));
  parts.push(text(x, 292, 16, 400, MUTED, label, { track: 0.08 }));
  if (i > 0) parts.push(vrule(x - 22, 238, 300, LINE));
});
y = 330;
parts.push(rule(y, LINE, 1));

// ---- 导语（反白块）----
y += 34;
const leadText = report.description || '';
const leadLines = fit(leadText, 30, CW - 88, 2);
const leadH = 52 + leadLines.length * 44 + 26;
parts.push(box(PAD, y, CW, leadH, INK, 6));
// 四角 accent（blackWhiteEditorial 的记号，反白版）
const A = 16;
const ay = y + 16;
const ax2 = PAD + CW - 16;
parts.push(`<path d="M${PAD + 16} ${ay + A} V${ay} H${PAD + 16 + A}" fill="none" stroke="#ffffff" stroke-width="2"/>`);
parts.push(`<path d="M${ax2 - A} ${ay} H${ax2} V${ay + A}" fill="none" stroke="#ffffff" stroke-width="2"/>`);
parts.push(`<path d="M${PAD + 16} ${y + leadH - 16 - A} V${y + leadH - 16} H${PAD + 16 + A}" fill="none" stroke="#ffffff" stroke-width="2"/>`);
parts.push(`<path d="M${ax2 - A} ${y + leadH - 16} H${ax2} V${y + leadH - 16 - A}" fill="none" stroke="#ffffff" stroke-width="2"/>`);
parts.push(text(PAD + 44, y + 40, 16, 600, '#a0a0a0', '本期导语', { track: 0.12 }));
let ly = y + 40 + 40;
for (const ln of leadLines) {
  parts.push(text(PAD + 44, ly, 30, 500, '#ffffff', ln));
  ly += 44;
}
y += leadH + 80;

// ---- 区块标题 ----
function sectionHeader(no, title, note = '') {
  parts.push(text(W - PAD, y, 54, 700, STRONG, no, { anchor: 'end' }));
  parts.push(box(PAD, y - 32, 8, 36, INK));
  parts.push(text(PAD + 22, y, 38, 700, INK, title));
  if (note) {
    const tw = textW(title, 38);
    parts.push(text(PAD + 22 + tw + 14, y - 2, 18, 400, MUTED, note));
  }
  y += 22;
  parts.push(rule(y, INK, 2));
  y += 40;
}

// ---- 01 今日看点 ----
const highlights = (report.highlights || []).slice(0, 4);
sectionHeader('01', '今日看点', `${highlights.length} 条`);
highlights.forEach((h, i) => {
  parts.push(text(PAD, y, 30, 700, STRONG, String(i + 1).padStart(2, '0')));
  const lines = fit(h.text, 28, CW - 62, 3);
  for (const ln of lines) {
    parts.push(text(PAD + 62, y, 28, 400, INK, ln));
    y += 41;
  }
  y += 20;
});
y += 18;

// ---- 02 新作热作（双栏平衡）----
const works = (report.works || []).slice(0, 24);
sectionHeader('02', '新作热作', `${works.length} 条`);
const COL_GAP = 44;
const colW = (CW - COL_GAP) / 2;
const WSIZE = 24;
const WLH = 35;
const ITEM_GAP = 13;
const IDX = 34;

// 先量高，再按高度对半分栏
const measured = works.map((w, i) => {
  const lines = fit(w, WSIZE, colW - IDX, 3);
  return { i, lines, h: lines.length * WLH + ITEM_GAP };
});
const totalH = measured.reduce((n, m) => n + m.h, 0);
let acc = 0;
let split = measured.length;
for (let i = 0; i < measured.length; i++) {
  acc += measured[i].h;
  if (acc >= totalH / 2) {
    split = i + 1;
    break;
  }
}
const cols = [measured.slice(0, split), measured.slice(split)];
const worksTop = y;
let maxBottom = y;
cols.forEach((col, ci) => {
  const x = PAD + ci * (colW + COL_GAP);
  let cy = worksTop;
  for (const item of col) {
    parts.push(text(x, cy, 17, 700, STRONG, String(item.i + 1).padStart(2, '0')));
    item.lines.forEach((ln, li) => {
      parts.push(text(x + IDX, cy, WSIZE, 400, INK, ln));
      if (li < item.lines.length - 1) cy += WLH;
    });
    cy += WLH + ITEM_GAP;
  }
  maxBottom = Math.max(maxBottom, cy - ITEM_GAP);
});
parts.push(vrule(PAD + colW + COL_GAP / 2, worksTop - 26, maxBottom, LINE));
y = maxBottom + 46;

// ---- 页脚 ----
parts.push(rule(y, INK, 1));
y += 34;
parts.push(text(PAD, y, 19, 600, SUB, 'epsilongg.github.io/daily/', { track: 0.04 }));
parts.push(
  text(W - PAD, y, 19, 400, MUTED, `${dateCn} ${kindLabel} · 由结构化数据自动生成`, { anchor: 'end' }),
);
y += 46;

const H = y;

// 四角 accent（整张图的黑白社论记号）
const C = 18;
const M = 22;
const corners = [
  `M${M} ${M + C} V${M} H${M + C}`,
  `M${W - M - C} ${M} H${W - M} V${M + C}`,
  `M${M} ${H - M - C} V${H - M} H${M + C}`,
  `M${W - M - C} ${H - M} H${W - M} V${H - M - C}`,
]
  .map((d) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="2"/>`)
  .join('');

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<rect width="${W}" height="${H}" fill="#ffffff"/>
${parts.join('\n')}
${corners}
</svg>`;

const out = process.argv[3] || join(HERE, `morning-${id}.png`);
mkdirSync(dirname(out), { recursive: true });
const png = new Resvg(svg, {
  fitTo: { mode: 'width', value: W },
  font: { fontFiles: FONTS, loadSystemFonts: false, defaultFontFamily: FAMILY },
}).render().asPng();
writeFileSync(out, png);
console.log(`wrote ${out} (${W}x${H}, ${(png.length / 1024).toFixed(0)} KB)`);
