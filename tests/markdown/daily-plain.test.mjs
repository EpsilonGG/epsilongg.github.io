import assert from 'node:assert/strict';
import test from 'node:test';

import { dailyPlainMarkdown, sourceUrl } from '../../src/lib/daily-plain.ts';

/**
 * 日报 `/daily/<id>.txt` 的契约测试。
 *
 * 目标是论坛可直接贴的 GFM：标题/列表/绝对链接，没有图片，没有正本以外的内容；
 * 「详细」每行保留账号主页和该条的原推链接。
 */

const data = {
  title: 'X 日报 · 2026-11-20 Galgame',
  description: '今天有几条新作情报。',
  highlights: [{ text: '『A』海外版决定。' }, { text: 'B 社团开卖。' }],
  works: ['『A』公开新图。'],
  categories: [{ label: '游戏制造商', summary: '今天很热闹。' }],
  interactions: [{ text: '甲转了乙。' }],
  people: [
    {
      handle: 'brand_a',
      summary: '公布『A』海外版。',
      via: ['info_b'],
      sources: ['x:123', 'bilibili:456', 'x:123', 'unknown:1'],
    },
    { handle: 'brand_empty', summary: '   ', via: [], sources: [] },
  ],
  insights: [{ text: '汉化变多。' }],
};

const identity = {
  nameOf: (handle) => (handle === 'brand_a' ? '品牌 A' : `@${handle}`),
  profileUrlOf: (handle) => (handle === 'brand_a'
    ? 'https://www.bilibili.com/space/1'
    : `https://x.com/${handle}`),
};

test('sourceUrl 只拼绝对 URL，且只认合法的来源键', () => {
  assert.equal(sourceUrl('x:123'), 'https://x.com/i/web/status/123');
  assert.equal(sourceUrl('bilibili:456'), 'https://www.bilibili.com/opus/456');
  assert.equal(sourceUrl(' x:789 '), 'https://x.com/i/web/status/789');
  for (const bad of ['unknown:1', 'x:', 'x:abc', 'x:1:2', 'bilibili:-1']) {
    assert.equal(sourceUrl(bad), null, bad);
  }
});

test('纯文字版是 GFM：H1/H2、列表、绝对链接，没有图片', () => {
  const out = dailyPlainMarkdown(data, identity);
  assert.ok(out.startsWith('# X 日报 · 2026-11-20 Galgame\n'));
  assert.deepEqual(
    [...out.matchAll(/^## (.+)$/gm)].map((m) => m[1]),
    ['今日看点', '作品动态', '分类摘要', '互动', '详细', '洞察']
  );
  assert.match(out, /^- 甲转了乙。$/m);
  assert.ok(!out.includes('!['), '纯文字版不该有图片语法');
  assert.ok(!out.includes('<img'));
  assert.ok(!out.includes('data/daily/'));
  for (const url of out.matchAll(/\]\(([^)]+)\)/g)) {
    assert.match(url[1], /^https?:\/\//, `链接必须是绝对 URL：${url[1]}`);
  }
});

test('详细栏保留账号、via 与逐条原文链接，且不重复', () => {
  const out = dailyPlainMarkdown(data, identity);
  const line = out.split('\n').find((l) => l.startsWith('- [品牌 A]'));
  assert.ok(line);
  assert.match(line, /^- \[品牌 A\]\(https:\/\/www\.bilibili\.com\/space\/1\)（@brand_a）：/);
  assert.match(line, /\[@info_b\]\(https:\/\/x\.com\/info_b\)/);
  assert.match(line, /\[原文1\]\(https:\/\/x\.com\/i\/web\/status\/123\)/);
  assert.match(line, /\[原文2\]\(https:\/\/www\.bilibili\.com\/opus\/456\)/);
  assert.equal((line.match(/原文1/g) ?? []).length, 1, '同一条来源只写一次');
  assert.ok(!line.includes('原文3'), '未知来源键不造链接');
  assert.ok(!out.includes('brand_empty'), '空概括的账号不输出');

  const unknown = dailyPlainMarkdown(
    { ...data, people: [{ handle: 'new_person', summary: '一句话。', via: [], sources: [] }] },
    identity
  );
  assert.match(unknown, /^- \[@new_person\]\(https:\/\/x\.com\/new_person\)：一句话。$/m);
});

test('正本的字句逐字保留，没有二次概括', () => {
  const out = dailyPlainMarkdown(data, identity);
  for (const text of ['『A』海外版决定。', 'B 社团开卖。', '『A』公开新图。',
                      '游戏制造商：今天很热闹。', '公布『A』海外版。', '汉化变多。']) {
    assert.ok(out.includes(text), `丢了正本原句：${text}`);
  }
  assert.ok(out.endsWith('\n'));
});
