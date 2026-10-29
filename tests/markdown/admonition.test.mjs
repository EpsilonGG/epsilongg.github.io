/**
 * 提示框插件（src/lib/markdown-admonition.mjs）的单元测试。
 *
 * 不跑 satteri，直接调 `containerDirective` 这个访问器函数——它就是
 * 「mdast 节点进、mdast 节点出」的纯函数。这里盯的是四件事：
 * 类型对不对、标题从哪来、正文有没有搬过去、未知类型会不会把内容弄丢。
 *
 * 跑法：npm run test:md
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { admonitionPlugin } from '../../src/lib/markdown-admonition.mjs';

/** 造一个正文段落 */
function para(value) {
  return { type: 'paragraph', children: [{ type: 'text', value }] };
}

/** `:::note[标题]` 里那个被标记为 directiveLabel 的段落 */
function label(value) {
  return { type: 'paragraph', data: { directiveLabel: true }, children: [{ type: 'text', value }] };
}

/** 造一个容器指令节点 */
function directive(name, children) {
  return { type: 'containerDirective', name, children };
}

/** 取输出里的标题文字 */
function titleOf(out) {
  return out.children[0].children[0].value;
}

test(':::note 变成带 callout 类的引用块，默认标题是「说明」', () => {
  const out = admonitionPlugin.containerDirective(directive('note', [para('正文。')]));

  assert.equal(out.type, 'blockquote');
  assert.deepEqual(out.data.hProperties.className, ['callout', 'callout--note']);
  assert.equal(titleOf(out), '说明');
  assert.deepEqual(out.children[0].data.hProperties.className, ['callout__title']);
});

test('五种类型的默认标题各不相同', () => {
  const expected = { note: '说明', tip: '技巧', important: '要点', warning: '注意', caution: '警告' };
  for (const [name, title] of Object.entries(expected)) {
    const out = admonitionPlugin.containerDirective(directive(name, [para('正文。')]));
    assert.deepEqual(out.data.hProperties.className, ['callout', `callout--${name}`]);
    assert.equal(titleOf(out), title);
  }
});

test(':::note[自定义标题] 用方括号里的字，并且不再重复出现', () => {
  const out = admonitionPlugin.containerDirective(
    directive('note', [label('自定义标题'), para('正文。')]),
  );

  assert.equal(titleOf(out), '自定义标题');
  // 标题段被摘走，只剩标题 + 正文两段
  assert.equal(out.children.length, 2);
  assert.equal(out.children[1].children[0].value, '正文。');
});

test('正文原样搬进引用块，顺序不变', () => {
  const out = admonitionPlugin.containerDirective(
    directive('tip', [para('第一段。'), para('第二段。')]),
  );

  assert.equal(out.children.length, 3); // 标题 + 两段
  assert.equal(out.children[1].children[0].value, '第一段。');
  assert.equal(out.children[2].children[0].value, '第二段。');
});

test('不认识的类型退化成 note，但内容绝不丢', () => {
  const out = admonitionPlugin.containerDirective(directive('danger', [para('还在。')]));

  assert.deepEqual(out.data.hProperties.className, ['callout', 'callout--note']);
  assert.equal(out.children[1].children[0].value, '还在。');
});

test('大小写混写也能认', () => {
  const out = admonitionPlugin.containerDirective(directive('WARNING', [para('正文。')]));
  assert.deepEqual(out.data.hProperties.className, ['callout', 'callout--warning']);
});

test('空指令不炸，至少产出一个只有标题的框', () => {
  const out = admonitionPlugin.containerDirective(directive('note', []));
  assert.equal(out.type, 'blockquote');
  assert.equal(out.children.length, 1);
  assert.equal(titleOf(out), '说明');
});
