/* 从 filter.html 内联 JS 里取出 buildMarkdown，用同一份数据跑一遍。
   check 命令把它与 Python 产出的 draft-selected.md 逐字节比对。
   用法：node weekly/parity.js weekly/out

   仓库 package.json 是 "type": "module"，所以这里用 ESM 语法。
*/
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = process.argv[2] || path.join(here, 'out');
const html = fs.readFileSync(path.join(outDir, 'filter.html'), 'utf8');
// 版式规则（FMT / has / ordered）与 buildMarkdown 一起取，保证两边同源。
const start = html.indexOf('  var FMT=');
const end = html.indexOf('  function download(', start);
if (start < 0 || end < 0) {
  console.error('buildMarkdown / format block not found in filter.html');
  process.exit(2);
}
const fn = html.slice(start, end);
const DATA = JSON.parse(fs.readFileSync(path.join(outDir, 'filter-data.json'), 'utf8'));
const decisions = JSON.parse(fs.readFileSync(path.join(outDir, 'decisions.json'), 'utf8'));
const buildMarkdown = new Function('DATA', fn + '\nreturn buildMarkdown;')(DATA);
process.stdout.write(buildMarkdown(decisions));
