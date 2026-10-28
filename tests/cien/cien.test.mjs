import assert from 'node:assert/strict';
import test from 'node:test';

import { cienText, formatCienDayZh, formatCienMonthDay } from '../../src/lib/cien.ts';

/**
 * Ci-en 貼り付け用テキストの契約テスト。
 *
 * ここで守るのは**中身ではなく記法と並び**。Ci-en のエディタが受け付けるのは
 * 見出し `#` / `##`、リンク `[..](..)`、`<span style="font-size: 150%">` だけなので、
 * 「貼った瞬間に崩れる書き方」が混ざっていないこと、
 * そしてタイトル → 中国語版 → 日本語版の順で並んでいることを機械に見張らせる。
 */

const issue = {
  id: '261027',
  // 期号是「覆盖的那一天」，不是发布时刻。生产里 parseDailyId 给的是 JST 零点
  day: new Date('2026-10-26T15:00:00Z'), // = 2026-10-27 00:00 JST
  windowStart: '2026-10-27T00:00:00+09:00',
  windowEnd: '2026-10-28T00:00:00+09:00',
  hook: '柚木つばめ生誕祭、川乃瀬由羽は9周年',
  people: [
    { handle: 're_re_tsubame', via: ['sub_one'] },
    { handle: 'suzuka_minase', via: [] },
    { handle: 'not_translated', via: [] },
  ],
};

const zh = {
  description: '柚木つばめ生日祭与川乃瀬由羽九周年直播撑场。',
  highlights: ['@re_re_tsubame 的感想文被转发，@unknown_account 也提了一句。'],
  works: '发售面上…',
  people: [
    { handle: 're_re_tsubame', summary: '转发了粉丝写的生日祭感想。' },
    { handle: 'suzuka_minase', summary: '直播打到夏天。' },
    { handle: 'not_translated', summary: '中文版有这句，日语版没有。' },
  ],
};

const ja = {
  description: '生誕祭と9周年が並んだ一日。',
  highlights: ['@re_re_tsubame の感想文が掲載された。'],
  works: '発売面では…',
  interactions: ['この節はもう出さない。'],
  people: [
    { handle: 're_re_tsubame', summary: '感想文をリポストした。' },
    { handle: 'suzuka_minase', summary: '配信で夏まで進めた。' },
    { handle: 'typo_handle', summary: 'この行は出ない。' },
  ],
};

const options = {
  nameOf: (handle) => (handle === 're_re_tsubame' ? '柚木つばめ' : handle),
  handles: ['re_re_tsubame', 'suzuka_minase'],
};

const text = cienText(issue, zh, ja, options);
const lines = text.split('\n');
const headings = lines.filter((line) => line.startsWith('#'));

test('1 行目は固定のタイトル。日付は覆盖日から作る', () => {
  assert.equal(lines[0], '【声優Xまとめ 10/27】柚木つばめ生誕祭、川乃瀬由羽は9周年');
  assert.equal(formatCienMonthDay(new Date('2026-10-27T13:00:00Z')), '10/27');
  assert.equal(formatCienDayZh(new Date('2026-10-27T13:00:00Z')), '2026-10-27');
});

test('钩子が空でもタイトルは壊れない', () => {
  const bare = cienText({ ...issue, hook: '' }, zh, ja, options);
  assert.equal(bare.split('\n')[0], '【声優Xまとめ 10/27】');
});

test('タイトル → 中国語版 → 日本語版の順で、その二つだけが # の見出し', () => {
  assert.deepEqual(
    headings.filter((line) => line.startsWith('# ')),
    ['# 中文版', '# 日本語版']
  );
  assert.ok(text.indexOf('# 日本語版') > text.indexOf('# 中文版'));
  for (const heading of headings) {
    assert.ok(/^#{1,2} /.test(heading), `見出しの形がおかしい: ${heading}`);
  }
});

test('各版の中は ## の小見出しだけで、やりとり の節は出さない', () => {
  assert.deepEqual(headings, [
    '# 中文版',
    '## 今日看点',
    '## 作品动态',
    '## 详细',
    '## 出处',
    '# 日本語版',
    '## 今日の注目',
    '## 作品動向',
    '## 詳細',
    '## 出典',
  ]);
  assert.ok(!text.includes('やりとり'));
  assert.ok(!text.includes('互动'));
});

test('日付は中国語版にだけ、時刻はどこにも書かない', () => {
  assert.ok(text.includes('2026-10-27（日本时间）'));
  assert.ok(!text.includes('22:00'), '公開時刻は読者にとって情報ではない');
  // 日本語版は日付の行から始まらず、副標題（無ければ見出し）から始まる
  assert.ok(text.split('# 日本語版\n\n')[1].startsWith('生誕祭と9周年が並んだ一日。'));
  assert.ok(!text.includes('<span'), '大きさ指定は使っていない（大きくする対象がもう無い）');
});

test('Ci-en で化ける書き方を混ぜない（- 箇条書き / 生 HTML リンク / iframe）', () => {
  assert.ok(!/^\s*[-*+] /m.test(text), '- の箇条書きは使わない（・で書く）');
  assert.ok(!text.includes('<a '), 'リンクは [..](..) で書く');
  assert.ok(!text.includes('<iframe'), 'chobit の埋め込みは今回の範囲外');
});

test('** は人名リンクのラベルの中でだけ使う', () => {
  const rest = text.replace(/\[\*\*[^*\n]+\*\*\]\(/g, '');
  assert.ok(!rest.includes('**'), '本文の強調に ** を使わない（Ci-en では原物が出る）');
});

test('人名は [**名前**](URL)：一行、中国語版も日本語版も同じ形', () => {
  assert.match(text, /^・\[\*\*柚木つばめ\*\*\]\(https:\/\/x\.com\/re_re_tsubame\)：转发了粉丝写的生日祭感想。/m);
  assert.match(text, /^・\[\*\*柚木つばめ\*\*\]\(https:\/\/x\.com\/re_re_tsubame\)：感想文をリポストした。/m);
  assert.match(text, /（ほかに \[\@sub_one\]\(https:\/\/x\.com\/sub_one\)）/);
});

test('本文中の @handle は名单にある号だけリンクにする', () => {
  assert.match(text, /\[@re_re_tsubame\]\(https:\/\/x\.com\/re_re_tsubame\)/);
  // 名单外はそのまま残す（リンク先が無いより文字で残す）
  assert.ok(text.includes('@unknown_account'));
  assert.ok(!text.includes('https://x.com/unknown_account'));
});

test('「详细」は中国語版の順で、訳の無い人と居ない handle は出さない', () => {
  const zhDetail = text.split('## 详细\n')[1].split('\n\n## 出处')[0].split('\n');
  assert.deepEqual(zhDetail, [
    '・[**柚木つばめ**](https://x.com/re_re_tsubame)：转发了粉丝写的生日祭感想。（另有 [@sub_one](https://x.com/sub_one)）',
    '・[**suzuka_minase**](https://x.com/suzuka_minase)：直播打到夏天。',
    '・[**not_translated**](https://x.com/not_translated)：中文版有这句，日语版没有。',
  ]);

  const jaDetail = text.split('## 詳細\n')[1].split('\n\n## 出典')[0].split('\n');
  assert.deepEqual(jaDetail, [
    '・[**柚木つばめ**](https://x.com/re_re_tsubame)：感想文をリポストした。（ほかに [@sub_one](https://x.com/sub_one)）',
    '・[**suzuka_minase**](https://x.com/suzuka_minase)：配信で夏まで進めた。',
  ]);
});

test('出典は集計窓を JST で書き、終端が翌日 0 時なら 24:00 にする', () => {
  assert.ok(text.includes('据 X 各账号的帖子整理（2026-10-27 00:00〜24:00 JST）。'));
  assert.ok(text.includes('（2026年10月27日 00:00〜24:00 JST）'));
});

test('末尾は改行ひとつだけ', () => {
  assert.ok(text.endsWith('\n'));
  assert.ok(!text.endsWith('\n\n'));
});
