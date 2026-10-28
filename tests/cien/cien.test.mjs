import assert from 'node:assert/strict';
import test from 'node:test';

import { cienText, formatCienTime } from '../../src/lib/cien.ts';

/**
 * Ci-en 貼り付け用テキストの契約テスト。
 *
 * ここで守るのは**中身ではなく記法**。Ci-en のエディタが受け付けるのは
 * 見出し `##` / リンク `[..](..)` / `<span style="font-size: 150%">` だけなので、
 * 「貼った瞬間に崩れる書き方」が混ざっていないことを機械に見張らせる。
 */

const issue = {
  id: '26102722',
  publishedAt: new Date('2026-10-27T13:00:00Z'), // = 2026-10-27 22:00 JST
  windowStart: '2026-10-27T00:00:00+09:00',
  windowEnd: '2026-10-28T00:00:00+09:00',
  people: [
    { handle: 're_re_tsubame', via: ['sub_one'] },
    { handle: 'suzuka_minase', via: [] },
    { handle: 'not_translated', via: [] },
  ],
};

const ja = {
  description: '生誕祭と9周年が中心。',
  highlights: ['@re_re_tsubame の感想文が掲載された。'],
  works: '発売面では…',
  interactions: ['@unknown_account が反応した。'],
  people: [
    { handle: 're_re_tsubame', summary: '感想文をリポストした。' },
    { handle: 'suzuka_minase', summary: '配信で夏まで進めた。' },
    { handle: 'typo_handle', summary: 'この行は出ない。' },
  ],
  insights: [],
};

const options = {
  nameOf: (handle) => (handle === 're_re_tsubame' ? '柚木つばめ' : handle),
  handles: ['re_re_tsubame', 'suzuka_minase'],
};

const text = cienText(issue, ja, options);

test('見出しは ## で、タイトルだけ span で大きくする', () => {
  const lines = text.split('\n');
  assert.equal(lines[0], '<span style="font-size: 150%">【X まとめ】2026年10月27日 22:00</span>');

  const headings = lines.filter((line) => line.startsWith('#'));
  for (const heading of headings) {
    assert.ok(heading.startsWith('## '), `見出しが ## 以外で始まっている: ${heading}`);
  }
  assert.deepEqual(headings, ['## 今日の注目', '## 作品動向', '## やりとり', '## 詳細', '## 出典']);
});

test('Ci-en で化ける書き方を混ぜない（**強調 / - 箇条書き / 生 HTML リンク）', () => {
  assert.ok(!text.includes('**'), '**強調** は使わない');
  assert.ok(!/^\s*[-*+] /m.test(text), '- の箇条書きは使わない（・で書く）');
  assert.ok(!text.includes('<a '), 'リンクは [..](..) で書く');
  assert.ok(!text.includes('<iframe'), 'chobit の埋め込みは今回の範囲外');
});

test('リンクは [テキスト](URL) 形式', () => {
  assert.match(text, /^・\[柚木つばめ\]\(https:\/\/x\.com\/re_re_tsubame\)：/m);
  assert.match(text, /（ほかに \[@sub_one\]\(https:\/\/x\.com\/sub_one\)）/);
});

test('本文中の @handle は名单にある号だけリンクにする', () => {
  assert.match(text, /\[@re_re_tsubame\]\(https:\/\/x\.com\/re_re_tsubame\)/);
  // 名单外はそのまま残す（リンク先が無いより文字で残す）
  assert.ok(text.includes('@unknown_account'));
  assert.ok(!text.includes('https://x.com/unknown_account'));
});

test('「詳細」は中国語版の順で、訳の無い人と居ない handle は出さない', () => {
  const detail = text.split('## 詳細\n')[1].split('\n\n## 出典')[0].split('\n');
  assert.deepEqual(detail, [
    '・[柚木つばめ](https://x.com/re_re_tsubame)：感想文をリポストした。（ほかに [@sub_one](https://x.com/sub_one)）',
    '・[suzuka_minase](https://x.com/suzuka_minase)：配信で夏まで進めた。',
  ]);
});

test('空の節は見出しごと出さない', () => {
  assert.ok(!text.includes('## 所感'));
});

test('出典は集計窓を JST で書き、終端が翌日 0 時なら 24:00 にする', () => {
  assert.ok(text.includes('（2026年10月27日 00:00〜24:00 JST）'));
  assert.equal(formatCienTime(new Date('2026-10-27T13:00:00Z')), '2026年10月27日 22:00');
});

test('末尾は改行ひとつだけ', () => {
  assert.ok(text.endsWith('\n'));
  assert.ok(!text.endsWith('\n\n'));
});
