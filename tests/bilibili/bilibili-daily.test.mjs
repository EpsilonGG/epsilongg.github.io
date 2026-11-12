import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  BILIBILI_CATEGORY,
  BILIBILI_LABEL,
  coveredDay,
  loadBilibiliDynamics,
  parseBilibiliJsonl,
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
