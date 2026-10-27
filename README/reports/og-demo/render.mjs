/**
 * OG 卡片渲染原型 —— 证明「构建期生成 1200×630 PNG」这条路能走通。
 *
 * 三个必须自己做的动作，resvg 一个都不代劳：
 *   1. 断行：SVG <text> 不会自动换行，每行宽度得先算出来再切。
 *   2. 截断：超过 3 行要自己截并加省略号。
 *   3. 字体：loadSystemFonts 关掉，只喂仓库里那份子集，否则 CI 上是方框。
 *
 * 宽度用近似值算（CJK 1em / ASCII 0.56em / 空格 0.28em）。真做的时候
 * 换成 fontkit 量真实 advance width，这里的近似只为了看效果。
 *
 * 用法：node render.mjs <输出目录>
 */
import { Resvg } from '@resvg/resvg-js';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const OUT = process.argv[2] ?? '.';
const FONT_DIR = process.env.OG_FONT_DIR ?? '.';
const FONTS = ['NotoSub-400.ttf', 'NotoSub-700.ttf'].map((f) => join(FONT_DIR, f));

const W = 1200;
const H = 630;
const PAD = 84;
const INK = '#1a1a1a';
const MUTED = '#767676';
const FAINT = '#cfcfcf';
const RULE = '#e5e5e5';

const charW = (ch) => {
  const c = ch.codePointAt(0);
  if (ch === ' ') return 0.28;
  if (c >= 0x2e80) return 1.0;              // CJK / 全角标点
  if (/[iIl1.,:;'!|]/.test(ch)) return 0.3;
  if (/[A-Z]/.test(ch)) return 0.64;
  if (/[0-9]/.test(ch)) return 0.56;
  return 0.54;
};
const textW = (s, size) => [...s].reduce((n, ch) => n + charW(ch), 0) * size;

/** 按「不切断西文单词 + 中文禁则」的规则折行，返回行数组。 */
const CLOSE = '」』）】》〉、，。；：？！…—';
const OPEN = '「『（【《〈';

function wrap(text, size, maxWidth) {
  const chars = [...text];
  const lines = [];
  let line = '';
  let width = 0;
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    const w = charW(ch) * size;
    if (width + w > maxWidth && line) {
      let carry = '';
      // 禁则①：行首不能是收尾标点 —— 把上一个字一起带下去
      while (CLOSE.includes(ch) && line.length > 1) {
        carry = line.slice(-1) + carry;
        line = line.slice(0, -1);
      }
      // 禁则②：行尾不能是开头标点或破折号 —— 推到下一行
      let tail = '';
      while (OPEN.includes(line.slice(-1))) {
        tail = line.slice(-1) + tail;
        line = line.slice(0, -1);
      }
      // 西文单词尽量不拆：回退到最后一个空格
      const sp = line.lastIndexOf(' ');
      if (sp > 0 && /^[A-Za-z0-9]+$/.test(line.slice(sp + 1)) && /[A-Za-z0-9]/.test(ch)) {
        carry = line.slice(sp + 1) + carry;
        line = line.slice(0, sp);
      }
      lines.push(line);
      line = tail + carry + ch;
      width = textW(line, size);
    } else {
      line += ch;
      width += w;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** 截到 maxLines 行，末行加省略号。 */
function fit(text, size, maxWidth, maxLines) {
  const lines = wrap(text, size, maxWidth);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  let last = kept[maxLines - 1];
  while (textW(last + '…', size) > maxWidth) last = last.slice(0, -1);
  kept[maxLines - 1] = last + '…';
  return kept;
}

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/**
 * 自动缩字号：从 66 往下试，直到「不超过 3 行」且「末行不少于 4 字」。
 * 后者是防孤字 —— 一个「报」字独占一行，比缩小两号难看得多。
 */
function autoFit(text, maxWidth) {
  for (const size of [66, 62, 58, 54, 50, 46, 42]) {
    const lines = wrap(text, size, maxWidth);
    const lastLen = [...(lines.at(-1) ?? '')].length;
    if (lines.length <= 3 && lastLen >= 4) return { size, lines };
  }
  return { size: 42, lines: fit(text, 42, maxWidth, 3) };
}

function card({ kicker, title, meta, note }) {
  const { size: titleSize, lines } = autoFit(title, W - PAD * 2);
  const lineH = Math.round(titleSize * 1.34);
  const blockH = lines.length * lineH;
  // 标题在「页眉下沿」到「页脚下沿」之间垂直居中
  const top = 150;
  const bottom = H - 120;
  let y = Math.round(top + (bottom - top - blockH) / 2 + titleSize * 0.82);

  const body = lines
    .map((ln, i) => `<text x="${PAD}" y="${y + i * lineH}" font-size="${titleSize}" font-weight="700" fill="${INK}">${esc(ln)}</text>`)
    .join('\n  ');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <rect width="${W}" height="${H}" fill="#ffffff"/>
  <text x="${PAD}" y="96" font-size="30" font-weight="600" fill="${INK}" letter-spacing="0.5">EpsilonGG</text>
  <text x="${W - PAD}" y="96" font-size="24" fill="${MUTED}" text-anchor="end">${esc(kicker)}</text>
  <line x1="${PAD}" y1="126" x2="${W - PAD}" y2="126" stroke="${RULE}" stroke-width="1"/>
  ${body}
  <line x1="${PAD}" y1="${H - 96}" x2="${W - PAD}" y2="${H - 96}" stroke="${RULE}" stroke-width="1"/>
  <text x="${PAD}" y="${H - 52}" font-size="26" fill="${MUTED}">${esc(meta)}</text>
  <text x="${W - PAD}" y="${H - 52}" font-size="24" fill="${FAINT}" text-anchor="end">${esc(note)}</text>
</svg>`;
}

const cards = [
  {
    file: 'og-home.png',
    kicker: '个人主页',
    title: '写长文的人，与每天一期的声优日报',
    meta: '笔记 · 日报 · 2026',
    note: 'epsilongg.github.io',
  },
  {
    file: 'og-note.png',
    kicker: '笔记',
    title: '「天才们的光芒把眼睛晃坏了」——打越钢太郎谈新公司 CRASH KEYS 的真意，新作中止的苦境与今后的挑战【访谈】',
    meta: '翻译访谈 · 视觉小说 · 2026-10-26',
    note: 'epsilongg.github.io',
  },
  {
    // 日报的标题是日期，信息量为零 —— 卡片必须以「看点简报」为主角，
    // 日期退到页脚。这是 M5 唯一一处与笔记卡片结构不同的地方。
    file: 'og-daily.png',
    kicker: '日报',
    title: '多位声优集中放出新作与广播剧，收藏数与销量接连破线',
    meta: '2026 年 10 月 26 日 22:00',
    note: 'epsilongg.github.io',
  },
];

mkdirSync(OUT, { recursive: true });
for (const c of cards) {
  const svg = card(c);
  const png = new Resvg(svg, {
    fitTo: { mode: 'width', value: W },
    font: {
      fontFiles: FONTS,
      loadSystemFonts: false,   // 关键：CI 上没有中文字体
      defaultFontFamily: 'Noto Sans SC',
    },
  })
    .render()
    .asPng();
  writeFileSync(join(OUT, c.file), png);
  console.log(`${c.file}  ${(png.length / 1024).toFixed(0)} KB`);
}
