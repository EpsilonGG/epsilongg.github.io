/**
 * 笔记源码里的 `:::` 指令写法体检。
 *
 * 为什么要有这一份：`:::video` 的地址如果写在**同一行**，Markdown 解析器会把
 * 那段文本整段丢掉——插件收到的 `children` 是空数组，页面上只剩一个空框，
 * 地址无影无踪。这种错**构建不报错、单元测试也测不到**（它们不解析 Markdown），
 * 只有人去看页面才会发现。所以直接在源码上查。
 *
 * 三条规则：
 *   1. `:::video https://…` —— 地址必须另起一行；
 *   2. `::: video`         —— 冒号后面不能有空格，否则整行原样印到页面上；
 *   3. 开的 `:::` 必须有配对的收尾，否则会把后面整篇文章吞进去。
 *
 * 围栏代码块里的内容不参与检查（那里写 `:::` 是在举例子）。
 *
 * 跑法：npm run test:md
 */

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';

const BLOG_DIR = new URL('../../src/content/blog/', import.meta.url);

/** 读所有笔记，返回 [{ name, lines }] */
function posts() {
  return readdirSync(BLOG_DIR)
    .filter((name) => name.endsWith('.md'))
    .sort()
    .map((name) => ({
      name,
      lines: readFileSync(new URL(name, BLOG_DIR), 'utf8').split(/\r?\n/),
    }));
}

/** 去掉 frontmatter 与围栏代码块，只留正文行（保留原行号） */
function bodyLines(lines) {
  const out = [];
  let inFence = false;
  let seenFrontmatter = false;
  let frontmatterDone = false;

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];

    // 开头那段 --- … --- 是 frontmatter
    if (i === 0 && line.trim() === '---') {
      seenFrontmatter = true;
      continue;
    }
    if (seenFrontmatter && !frontmatterDone) {
      if (line.trim() === '---') frontmatterDone = true;
      continue;
    }

    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;

    out.push({ no: i + 1, text: line });
  }
  return out;
}

/** 把一条规则套到所有笔记上，返回问题列表 */
function collect(check) {
  const problems = [];
  for (const post of posts()) {
    for (const line of bodyLines(post.lines)) {
      const message = check(line.text);
      if (message) problems.push(`${post.name}:${line.no}  ${message}`);
    }
  }
  return problems;
}

test(':::video 的地址必须单独占一行', () => {
  const problems = collect((text) =>
    /^\s*:::video\s+\S/.test(text)
      ? '地址写在了 :::video 同一行，解析器会把它整段丢掉——请另起一行'
      : '',
  );
  assert.deepEqual(problems, []);
});

test('::: 与指令名之间不能有空格', () => {
  const problems = collect((text) =>
    /^\s*:::\s+\w/.test(text) ? '::: 后面多了一个空格，整行会原样印到页面上' : '',
  );
  assert.deepEqual(problems, []);
});

test('每个 ::: 指令都有配对的收尾', () => {
  const problems = [];
  for (const post of posts()) {
    const open = [];
    for (const line of bodyLines(post.lines)) {
      const text = line.text.trim();
      if (/^:::\s*$/.test(text)) {
        if (open.length === 0) {
          problems.push(`${post.name}:${line.no}  多出一个收尾 :::`);
        } else {
          open.pop();
        }
        continue;
      }
      const start = text.match(/^:::(\w+)/);
      if (start) open.push(`${post.name}:${line.no}  ${start[1]}`);
    }
    for (const leftover of open) problems.push(`${leftover}  没有收尾 :::`);
  }
  assert.deepEqual(problems, []);
});

test('检查器本身能认出这三种错', () => {
  // 反向验证：规则不能写成永远通过的空壳。
  assert.ok(/^\s*:::video\s+\S/.test(':::video https://youtu.be/x'));
  assert.ok(/^\s*:::\s+\w/.test('::: video'));
  assert.ok(/^:::(\w+)/.test(':::video[标题]'));
  assert.ok(/^:::\s*$/.test(':::'));
  // 正常写法不该被判错
  assert.equal(/^\s*:::video\s+\S/.test(':::video[标题]'), false);
  assert.equal(/^\s*:::\s+\w/.test(':::note'), false);
});
