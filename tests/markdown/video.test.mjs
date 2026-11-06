/**
 * 视频嵌入（src/lib/markdown-video.mjs）的单元测试。
 *
 * 和提示框那份一样，不跑 satteri，直接调纯函数。这里盯的是四件事：
 * 地址能不能认出来、认出来的地址拼成什么、认不出时会不会把内容吞掉、
 * 属性值有没有转义（`&` 不转义会把 Bilibili 的查询串吃掉一半）。
 *
 * 跑法：npm run test:md
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { admonitionPlugin } from '../../src/lib/markdown-admonition.mjs';
import { parseVideoUrl, videoDirective } from '../../src/lib/markdown-video.mjs';

/** 造一个正文段落（纯文本） */
function para(value) {
  return { type: 'paragraph', children: [{ type: 'text', value }] };
}

/** 造一个 GFM 自动链接段落：`https://…` 在真实管线里会变成 link 节点 */
function linkPara(url) {
  return {
    type: 'paragraph',
    children: [{ type: 'link', url, children: [{ type: 'text', value: url }] }],
  };
}

/** 从输出里抠出 iframe 的 src */
function srcOf(out) {
  return out.value.match(/<iframe src="([^"]+)"/)[1];
}

// ── 认地址 ────────────────────────────────────────────────────────────────

test('YouTube 的各种写法都归一成同一个 ID', () => {
  const forms = [
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://www.youtube.com/watch?list=PL123&v=dQw4w9WgXcQ',
    'https://youtu.be/dQw4w9WgXcQ',
    'https://www.youtube.com/embed/dQw4w9WgXcQ',
    'https://www.youtube.com/shorts/dQw4w9WgXcQ',
    'https://m.youtube.com/watch?v=dQw4w9WgXcQ',
  ];
  for (const url of forms) {
    const hit = parseVideoUrl(url);
    assert.equal(hit?.provider, 'youtube', url);
    assert.equal(hit?.id, 'dQw4w9WgXcQ', url);
  }
});

test('YouTube 走 nocookie 域名，并且 rel=0', () => {
  const hit = parseVideoUrl('https://youtu.be/dQw4w9WgXcQ');
  assert.equal(hit.src, 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0');
  assert.equal(hit.watch, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
});

test('Bilibili 的 BV 号与老 av 号都认', () => {
  const bv = parseVideoUrl('https://www.bilibili.com/video/BV1V8x96kE6c');
  assert.equal(bv?.provider, 'bilibili');
  assert.equal(bv?.src, 'https://player.bilibili.com/player.html?bvid=BV1V8x96kE6c&page=1&high_quality=1&danmaku=0');

  const av = parseVideoUrl('https://www.bilibili.com/video/av170001');
  assert.equal(av?.provider, 'bilibili');
  assert.equal(av?.id, 'av170001');
  assert.equal(av?.watch, 'https://www.bilibili.com/video/av170001');
});

test('认不出的地址返回 null，不瞎猜', () => {
  assert.equal(parseVideoUrl('https://vimeo.com/12345'), null);
  assert.equal(parseVideoUrl('https://www.youtube.com/watch?v=short'), null);
  assert.equal(parseVideoUrl(''), null);
});

// ── 拼输出 ────────────────────────────────────────────────────────────────

test('输出是 figure + 16:9 的框 + iframe + 回原站的链接', () => {
  const out = videoDirective([linkPara('https://youtu.be/dQw4w9WgXcQ')]);

  assert.equal(out.type, 'html');
  assert.match(out.value, /^<figure class="article-video">/);
  assert.match(out.value, /<div class="article-video__frame">/);
  assert.match(out.value, /loading="lazy"/);
  assert.match(out.value, /allowfullscreen/);
  assert.match(out.value, /referrerpolicy="strict-origin-when-cross-origin"/);
  // 没给标题时，链接文字退成「在 X 观看」，用户永远有出口
  assert.match(out.value, />在 YouTube 观看</);
});

test('iframe 的 title 与链接文字都取方括号里的标题', () => {
  const out = videoDirective([linkPara('https://youtu.be/dQw4w9WgXcQ')], '联动告知 PV');

  assert.match(out.value, /title="联动告知 PV"/);
  assert.match(out.value, />联动告知 PV</);
});

test('纯文本里的地址也认（GFM 没开自动链接时）', () => {
  const out = videoDirective([para('顺便放一下 https://youtu.be/dQw4w9WgXcQ 这个')]);
  assert.ok(out, '夹在句子里的地址也要能认出来');
});

test('Bilibili 的查询串里 `&` 要转义成 &amp;，否则后半截参数会被浏览器吃掉', () => {
  const out = videoDirective([linkPara('https://www.bilibili.com/video/BV1V8x96kE6c')]);
  assert.match(srcOf(out), /bvid=BV1V8x96kE6c&amp;page=1&amp;high_quality=1&amp;danmaku=0/);
});

test('标题里的引号和尖括号被转义，不会把属性截断', () => {
  const out = videoDirective([linkPara('https://youtu.be/dQw4w9WgXcQ')], '他说"这样"<就好>');
  assert.match(out.value, /title="他说&quot;这样&quot;&lt;就好&gt;"/);
  assert.doesNotMatch(out.value, /title="他说"这样"/);
});

test('认不出地址时返回 null，交给调用方兜底（内容不丢）', () => {
  assert.equal(videoDirective([para('这里没有链接')]), null);
  assert.equal(videoDirective([para('https://vimeo.com/12345')]), null);
  assert.equal(videoDirective([]), null);
});

// ── 与提示框插件的分派 ────────────────────────────────────────────────────

test(':::video 走视频分支，不会变成提示框', () => {
  const node = {
    type: 'containerDirective',
    name: 'video',
    children: [linkPara('https://youtu.be/dQw4w9WgXcQ')],
  };
  const out = admonitionPlugin.containerDirective(node);

  assert.equal(out.type, 'html');
  assert.match(out.value, /<figure class="article-video">/);
});

test(':::video 里没有能认的地址时，退回提示框而不是消失', () => {
  const node = {
    type: 'containerDirective',
    name: 'video',
    children: [para('链接忘了贴')],
  };
  const out = admonitionPlugin.containerDirective(node);

  assert.equal(out.type, 'blockquote');
  assert.deepEqual(out.data.hProperties.className, ['callout', 'callout--note']);
  assert.equal(out.children[1].children[0].value, '链接忘了贴');
});

test(':::note 不受影响', () => {
  const out = admonitionPlugin.containerDirective({
    type: 'containerDirective',
    name: 'note',
    children: [para('正文。')],
  });
  assert.equal(out.type, 'blockquote');
  assert.deepEqual(out.data.hProperties.className, ['callout', 'callout--note']);
});
