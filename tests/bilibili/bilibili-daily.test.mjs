import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  BILIBILI_CATEGORY,
  BILIBILI_LABEL,
  BILIBILI_SUMMARY_LIMIT,
  charCount,
  cleanBilibiliText,
  coveredDay,
  groupBilibiliRows,
  loadBilibiliDynamics,
  loadBilibiliGroups,
  parseBilibiliJsonl,
  summarizeBilibili,
} from '../../src/lib/bilibili-daily.ts';

/**
 * 日报「B站动态」栏取数层的契约测试（2026-11-12）。
 *
 * 这一层刻意**不碰**受保护的日报正本：直接从 B 站 JSONL 读原始动态。
 * 这里钉住三件事：① 解析是宽容的（坏行 / 空行 / 重复都不能让整页构建失败）
 * ② 覆盖日 → 文件名的 JST 换算不依赖构建机时区 ③ 抓到的动态一条不少、且
 * 身份仍是名单里的 `bili_<uid>`，不会被误当成 X 账号。
 */

const row = (overrides = {}) =>
  JSON.stringify({
    identity_key: 'bilibili:1001',
    source_id: 'bilibili',
    item_id: '1001',
    content: '【告知】\n発売日が決定しました',
    publisher: 'HOOKSOFT公式',
    canonical_url: 'https://www.bilibili.com/opus/1001',
    published_at: '2026-11-10T05:45:15+00:00',
    metadata: {
      account: 'bili_3632310624717268',
      uid: '3632310624717268',
      tag: 'B站Gal',
    },
    ...overrides,
  });

test('栏目常量与名单 category.id / 日报显示名一致', () => {
  assert.equal(BILIBILI_CATEGORY, 'bili_gal');
  assert.equal(BILIBILI_LABEL, 'B站动态');
});

test('正常行解析出 key / handle / 原文链接，正文里的换行保留', () => {
  const parsed = parseBilibiliJsonl(row());
  assert.equal(parsed.length, 1);
  assert.deepEqual(parsed[0], {
    key: 'bilibili:1001',
    handle: 'bili_3632310624717268',
    text: '【告知】\n発売日が決定しました',
    url: 'https://www.bilibili.com/opus/1001',
    publisher: 'HOOKSOFT公式',
    publishedAt: '2026-11-10T05:45:15+00:00',
  });
});

test('坏行 / 空行 / 缺正文 / 缺链接都跳过，不让整页构建失败', () => {
  const raw = [
    '{"this is not json',
    '',
    '   ',
    row({ content: '   ' }),
    row({ item_id: '1002', identity_key: 'bilibili:1002', canonical_url: '' }),
    row(),
  ].join('\n');
  assert.equal(parseBilibiliJsonl(raw).length, 1);
  assert.equal(parseBilibiliJsonl('').length, 0);
  assert.equal(parseBilibiliJsonl(null).length, 0);
});

test('同一条动态按 identity_key 去重；没有 identity_key 时用 item_id 造一个', () => {
  const raw = [row(), row({ content: '抓重了' })].join('\n');
  assert.equal(parseBilibiliJsonl(raw).length, 1);

  const noKey = row({ identity_key: undefined });
  assert.equal(parseBilibiliJsonl(noKey)[0].key, 'bilibili:1001');
});

test('metadata.account 缺失时按 uid 合成 bili_<uid>，绝不退回 X 形状', () => {
  const parsed = parseBilibiliJsonl(
    row({ metadata: { uid: '3546838852438089', tag: 'B站Gal' } })
  );
  assert.equal(parsed[0].handle, 'bili_3546838852438089');
});

test('按发布时间升序；同一时刻按 key 稳定排序', () => {
  const raw = [
    row({ identity_key: 'bilibili:b', item_id: 'b', published_at: '2026-11-10T12:00:00+00:00' }),
    row({ identity_key: 'bilibili:a', item_id: 'a', published_at: '2026-11-10T03:00:00+00:00' }),
    row({ identity_key: 'bilibili:z', item_id: 'z', published_at: '2026-11-10T12:00:00+00:00' }),
  ].join('\n');
  assert.deepEqual(parseBilibiliJsonl(raw).map((r) => r.key), [
    'bilibili:a',
    'bilibili:b',
    'bilibili:z',
  ]);
});

test('coveredDay：期号覆盖的 JST 零点 → 正本文件名（不依赖机器时区）', () => {
  // 261110-g 的 covered 是 2026-11-10 00:00 JST = 2026-11-09 15:00 UTC
  assert.equal(coveredDay(new Date('2026-11-09T15:00:00Z')), '2026-11-10');
  // 跨月 / 跨年也要落在 JST 那一天
  assert.equal(coveredDay(new Date('2026-10-31T15:00:00Z')), '2026-11-01');
  assert.equal(coveredDay(new Date('2026-12-31T15:00:00Z')), '2027-01-01');
});

test('loadBilibiliDynamics 读到当天正本，条数与行数一致', () => {
  const rows = loadBilibiliDynamics(new Date('2026-11-09T15:00:00Z')); // 2026-11-10 JST
  const lines = readFileSync('data/bilibili/galgame/2026-11-10.jsonl', 'utf-8')
    .split(/\r?\n/)
    .filter((line) => line.trim()).length;
  assert.equal(rows.length, lines);
  assert.ok(rows.length > 0);
});

test('正本里的动态身份是 bili_<uid> + opus 链接，不是 X 账号', () => {
  const rows = loadBilibiliDynamics(new Date('2026-11-09T15:00:00Z'));
  for (const r of rows) {
    assert.match(r.key, /^bilibili:\d+$/);
    assert.match(r.handle, /^bili_\d+$/);
    assert.match(r.url, /^https:\/\/www\.bilibili\.com\/opus\/\d+$/);
    assert.ok(r.text.length > 0);
  }
});

test('没有当天正本时返回空数组（老期号 / 断抓都正常，不摆空按钮）', () => {
  assert.deepEqual(loadBilibiliDynamics(new Date('2020-01-01T15:00:00Z')), []);
});

/**
 * 2026-11-12 追加口径：同个账号的归到一起，合并后超过 150 字就概括。
 * 下面钉住「归并 / 阈值 / 概括质量 / 链接不丢」四件事。
 */

test('清理：剥裸链接、话题标签、零宽字符，换行压成单行', () => {
  assert.equal(
    cleanBilibiliText('\u200b正文 https://store.hikarifield.co.jp/shop/x\n#GALGAME# #STEAM# 尾巴'),
    '正文 尾巴',
  );
  assert.equal(cleanBilibiliText('第一行\n第二行'), '第一行 第二行');
  assert.equal(cleanBilibiliText(''), '');
});

test('字数按非空白码点算：中文一字一个，空格与换行不占额度', () => {
  assert.equal(charCount('一二三'), 3);
  assert.equal(charCount('一 二\n三'), 3);
  assert.equal(charCount('  '), 0);
  assert.equal(BILIBILI_SUMMARY_LIMIT, 150);
});

test('合计不超过 150 字就原样拼接，一个字都不改', () => {
  const { text, summarized } = summarizeBilibili(['【告知】发售日决定', '【补充】体验版公开']);
  assert.equal(summarized, false);
  assert.equal(text, '【告知】发售日决定 【补充】体验版公开');
});

test('超过 150 字就概括，结果不超过上限并以省略号收尾', () => {
  const long = Array.from({ length: 3 }, (_, i) => `第${i}条情报，${'内容很长'.repeat(40)}`);
  const { text, summarized } = summarizeBilibili(long);
  assert.equal(summarized, true);
  assert.ok(charCount(text) <= BILIBILI_SUMMARY_LIMIT, `实际 ${charCount(text)} 字`);
  assert.ok(text.endsWith('…'));
});

test('同款模板的六条促销并成一句，其余作品名收进「另：」', () => {
  const names = ['甲', '乙', '丙', '丁', '戊', '己'];
  const parts = names.map(
    (name, i) => `《作品${name}》官方中文版现正于官网商城促销热卖中！仅需${20 + i}元即可入手！`,
  );
  const { text, summarized } = summarizeBilibili(parts);
  assert.equal(summarized, true);
  assert.equal(text.split('促销热卖中').length - 1, 1); // 六条同款只留一句
  assert.ok(text.includes('（另：'));
  assert.ok(text.includes('《作品乙》'));
  assert.ok(charCount(text) <= BILIBILI_SUMMARY_LIMIT);
});

test('断句不切书名号：《A！B》这种带感叹号的作品名保持完整', () => {
  const filler = '补充说明'.repeat(10);
  const parts = ['甲！乙', '丙！丁', '戊！己'].map(
    (name) => `《${name}》官方中文版现正于官网商城促销热卖中！${filler}！`,
  );
  const { text, summarized } = summarizeBilibili(parts);
  assert.equal(summarized, true);
  assert.ok(text.includes('《甲！乙》'), '书名号被切断了');
  assert.ok(text.includes('《丙！丁》'));
  assert.equal((text.match(/《/g) ?? []).length, (text.match(/》/g) ?? []).length);
});

test('同账号归并成一组：顺序、条数、原文链接一条不丢', () => {
  const rows = parseBilibiliJsonl(
    [
      row({ identity_key: 'bilibili:1', item_id: '1', published_at: '2026-11-10T01:00:00+00:00' }),
      row({ identity_key: 'bilibili:2', item_id: '2', published_at: '2026-11-10T02:00:00+00:00' }),
      row({
        identity_key: 'bilibili:3',
        item_id: '3',
        published_at: '2026-11-10T03:00:00+00:00',
        publisher: '别的号',
        metadata: { account: 'bili_1', uid: '1', tag: 'B站Gal' },
      }),
    ].join('\n'),
  );
  const groups = groupBilibiliRows(rows);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].count, 2);
  assert.deepEqual(groups[0].keys, ['bilibili:1', 'bilibili:2']);
  assert.deepEqual(groups[0].urls, [
    'https://www.bilibili.com/opus/1001',
    'https://www.bilibili.com/opus/1001',
  ]);
  assert.equal(groups[0].handle, 'bili_3632310624717268');
  assert.equal(groups[1].handle, 'bili_1');
  assert.equal(groups[1].count, 1);
});

test('真实正本：17 条动态归并成 11 个账号，链接与条目一条不少', () => {
  const covered = new Date('2026-11-10T15:00:00Z'); // 2026-11-11 JST
  const rows = loadBilibiliDynamics(covered);
  const groups = loadBilibiliGroups(covered);
  assert.equal(rows.length, 17);
  assert.equal(groups.length, 11);
  assert.equal(
    groups.reduce((sum, group) => sum + group.urls.length, 0),
    rows.length,
  );
  for (const group of groups) {
    assert.ok(charCount(group.text) <= BILIBILI_SUMMARY_LIMIT, `${group.handle} 超长`);
    assert.ok(group.text.length > 0);
    assert.ok(!group.text.includes('http'), '正文里不该残留裸链接');
    assert.ok(!group.text.includes('#'), '正文里不该残留话题标签');
  }
  assert.ok(groups.some((group) => group.summarized));
  assert.ok(groups.every((group) => group.handle.startsWith('bili_')));
});
