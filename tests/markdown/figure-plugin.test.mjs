/**
 * 图注插件（src/lib/markdown-figure.mjs）的单元测试。
 *
 * 这里不跑 satteri，只用手搭的 hast 树 + 一个最小 ctx 来测插件自己的逻辑：
 * 单图、连续多图并组、行内图不动、带链接的图、picture 包装。
 *
 * 跑法：npm run test:md
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { figureCaptionPlugin } from '../../src/lib/markdown-figure.mjs';

/** 造一个最简 hast 元素 */
function el(tagName, properties = {}, children = []) {
  return { type: 'element', tagName, properties, children };
}

function text(value) {
  return { type: 'text', value };
}

/** 段落包一张图 */
function imgParagraph(src, title, { linked = false, picture = false } = {}) {
  let media = el('img', { src, alt: 'a', ...(title ? { title } : {}) });
  if (picture) {
    media = el('picture', { className: ['article-picture'] }, [
      el('source', { type: 'image/webp', srcSet: `${src.replace('.jpg', '.webp')} 600w` }),
      media,
    ]);
  }
  if (linked) media = el('a', { href: 'https://example.com/' }, [media]);
  return el('p', {}, [media]);
}

/**
 * 最小可用的 visitor ctx：只实现插件真正用到的那几个方法。
 * @param {any} root
 */
function makeCtx(root) {
  const parents = new Map();

  const index = (node) => {
    for (const [child, parent] of parents) {
      if (child === node) return parent.children.indexOf(node);
    }
    return undefined;
  };

  const link = (node, parent) => {
    if (node && typeof node === 'object') {
      parents.set(node, parent);
      if (Array.isArray(node.children)) for (const child of node.children) link(child, node);
    }
  };
  link(root, null);

  return {
    parent(node) {
      return parents.get(node);
    },
    indexOf(node) {
      return index(node);
    },
    replaceNode(node, newNode) {
      const parent = parents.get(node);
      assert.ok(parent, 'replaceNode 的节点必须在树里');
      const at = parent.children.indexOf(node);
      parent.children.splice(at, 1, newNode);
      parents.delete(node);
      link(newNode, parent);
    },
    removeChildAt(node, at) {
      const [removed] = node.children.splice(at, 1);
      if (removed) parents.delete(removed);
    },
    setProperty(node, key, value) {
      if (!node.properties) node.properties = {};
      if (value === null) delete node.properties[key];
      else node.properties[key] = value;
    },
  };
}

/** 走一遍插件：先 before()，再对每张 img 调 visit（模拟 satteri 的遍历顺序） */
function run(root) {
  const ctx = makeCtx(root);
  figureCaptionPlugin.before();
  const imgs = [];
  const walk = (node) => {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'element' && node.tagName === 'img') imgs.push(node);
    if (Array.isArray(node.children)) node.children.forEach(walk);
  };
  walk(root);
  for (const img of imgs) figureCaptionPlugin.element.visit(img, ctx);
  return root;
}

test('单张带 title 的图变成 figure', () => {
  const root = { type: 'root', children: [imgParagraph('/a.jpg', '图注')] };
  run(root);

  const figure = root.children[0];
  assert.equal(figure.tagName, 'figure');
  assert.equal(figure.children[0].tagName, 'img');
  assert.equal(figure.children[1].tagName, 'figcaption');
  assert.equal(figure.children[1].children[0].value, '图注');
  // title 已经搬进图注，img 上不该再留
  assert.equal(figure.children[0].properties.title, undefined);
});

test('没有 title 的图保持原样', () => {
  const root = { type: 'root', children: [imgParagraph('/a.jpg', null)] };
  run(root);
  assert.equal(root.children[0].tagName, 'p');
});

test('行内图（段落里还有文字）不动', () => {
  const p = el('p', {}, [text('前面'), el('img', { src: '/a.jpg', title: '不该出现' }), text('后面')]);
  const root = { type: 'root', children: [p] };
  run(root);
  assert.equal(root.children[0].tagName, 'p');
  assert.equal(root.children[0].children.length, 3);
});

test('连续两张图并成一组', () => {
  const root = {
    type: 'root',
    children: [imgParagraph('/a.jpg', '甲'), imgParagraph('/b.jpg', '乙')],
  };
  run(root);

  assert.equal(root.children.length, 1);
  const grid = root.children[0];
  assert.equal(grid.tagName, 'div');
  assert.deepEqual(grid.properties.className, ['article-figure-grid']);
  assert.equal(grid.children.length, 2);
  assert.ok(grid.children.every((c) => c.tagName === 'figure'));
});

test('中间夹着空白文本也算连续', () => {
  const root = {
    type: 'root',
    children: [imgParagraph('/a.jpg', '甲'), text('\n'), imgParagraph('/b.jpg', '乙')],
  };
  run(root);
  const grid = root.children.find((c) => c.tagName === 'div');
  assert.ok(grid, '应该并成一组');
  assert.equal(grid.children.length, 2);
});

test('中间隔着正文就不并组', () => {
  const root = {
    type: 'root',
    children: [
      imgParagraph('/a.jpg', '甲'),
      el('p', {}, [text('正文')]),
      imgParagraph('/b.jpg', '乙'),
    ],
  };
  run(root);
  assert.equal(root.children.filter((c) => c.tagName === 'figure').length, 2);
  assert.equal(root.children.filter((c) => c.tagName === 'div').length, 0);
});

test('三张连排只生成一组', () => {
  const root = {
    type: 'root',
    children: [
      imgParagraph('/a.jpg', '甲'),
      imgParagraph('/b.jpg', '乙'),
      imgParagraph('/c.jpg', '丙'),
    ],
  };
  run(root);
  const grids = root.children.filter((c) => c.tagName === 'div');
  assert.equal(grids.length, 1);
  assert.equal(grids[0].children.length, 3);
});

test('被 <a> 包住的图也能出图注，链接保留', () => {
  const root = { type: 'root', children: [imgParagraph('/a.jpg', '链接图', { linked: true })] };
  run(root);

  const figure = root.children[0];
  assert.equal(figure.tagName, 'figure');
  assert.equal(figure.children[0].tagName, 'a');
  assert.equal(figure.children[0].properties.href, 'https://example.com/');
  assert.equal(figure.children[1].children[0].value, '链接图');
});

test('被 <picture> 包住的图也能出图注，picture 保留', () => {
  const root = { type: 'root', children: [imgParagraph('/a.jpg', '图注', { picture: true })] };
  run(root);

  const figure = root.children[0];
  assert.equal(figure.tagName, 'figure');
  assert.equal(figure.children[0].tagName, 'picture');
  // picture 里 source 在前、img 在后，不能被拆开
  assert.equal(figure.children[0].children[0].tagName, 'source');
  assert.equal(figure.children[0].children[1].tagName, 'img');
});

test('并组后把 sizes 改成半栏宽度', () => {
  const root = {
    type: 'root',
    children: [
      imgParagraph('/a.jpg', '甲', { picture: true }),
      imgParagraph('/b.jpg', '乙', { picture: true }),
    ],
  };
  run(root);

  const grid = root.children[0];
  assert.equal(grid.tagName, 'div');
  for (const figure of grid.children) {
    const source = figure.children[0].children.find((c) => c.tagName === 'source');
    assert.ok(source, 'picture 里应该还有 source');
    // 并排之后每张图只剩半栏，不能继续声明 38rem
    assert.match(source.properties.sizes, /19rem/);
    assert.doesNotMatch(source.properties.sizes, /38rem/);
  }
});

test('并组之后再遍历不会重复包装', () => {
  const root = {
    type: 'root',
    children: [imgParagraph('/a.jpg', '甲'), imgParagraph('/b.jpg', '乙')],
  };
  const ctx = makeCtx(root);
  figureCaptionPlugin.before();
  const first = root.children[0].children[0];
  const second = root.children[1].children[0];

  figureCaptionPlugin.element.visit(first, ctx);
  // 第二张图已经被并进组里，再单独访问一次不应该再套一层
  figureCaptionPlugin.element.visit(second, ctx);

  const grids = root.children.filter((c) => c.tagName === 'div');
  assert.equal(grids.length, 1);
  assert.equal(grids[0].children.length, 2);
});
