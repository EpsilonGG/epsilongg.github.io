/**
 * 把 `:::note` 这类容器指令编译成带样式的提示框。
 *
 * 为什么要自己写：`satteri` 的 `features.directive` 只负责**解析** `:::`，
 * 不给 hast 处理器，于是整块内容在 mdast→hast 那一步被**静默丢掉**——
 * 开着这个开关而不挂插件，等于给自己埋一个「内容消失」的坑。这里补上处理器。
 *
 * 写作约定（与 fuwari / Obsidian 一致）：
 *
 *   :::note
 *   正文。
 *   :::
 *
 *   :::warning[自定义标题]
 *   正文。
 *   :::
 *
 * 认得的五种：note / tip / important / warning / caution（未知名字原样退化成
 * note，宁可样式不对也不要丢内容）。输出是 `<blockquote class="callout …">`，
 * 语义上本来就该是引用块，样式在 components.css 的 `.callout` 一族。
 *
 * 另外 `:::video` 交给 `markdown-video.mjs` 处理（同一个访问器里分派，而不是
 * 再注册一个插件——两个插件都写 `containerDirective` 时，先跑的那个会把
 * `:::video` 变成提示框，后跑的再也看不见它）。认不出地址就退回下面的 note。
 *
 * 一个救不回来的坑：`:::video https://…` 把地址写在**同一行**时，解析器直接
 * 丢掉那段文本（`children` 是空数组），插件拿不到任何原文。所以这里对「空的
 * video 指令」单独给一句能看懂的提示——至少页面上不会出现一个什么都没有的框。
 * 真正的防线在 `tests/markdown/directive-syntax.test.mjs`：构建期就拦下来。
 */

import { videoDirective } from './markdown-video.mjs';

/** 五种类型：名字 → 中文默认标题 */
const KINDS = {
  note: '说明',
  tip: '技巧',
  important: '要点',
  warning: '注意',
  caution: '警告',
};

/**
 * 取出指令的标题：`:::note[标题]` 会被解析成第一个 `data.directiveLabel`
 * 的段落，把它摘出来当标题，剩下的才是正文。
 * @param {any[]} children
 */
function splitLabel(children) {
  const list = Array.isArray(children) ? [...children] : [];
  const first = list[0];
  if (first?.type === 'paragraph' && first.data?.directiveLabel) {
    const text = (first.children ?? [])
      .map((c) => (c?.type === 'text' ? c.value : ''))
      .join('')
      .trim();
    return { label: text, rest: list.slice(1) };
  }
  return { label: '', rest: list };
}

/**
 * 造一个提示框节点：标题段 + 正文。
 *
 * 返回值的类型要收窄成 satteri 的 `MdastVisitorResult`（它认的是 mdast 的
 * `Blockquote` 字面量类型），这里手工造节点只能是 `any`，否则 astro check 报 2322。
 *
 * @param {string} kind 五种类型之一
 * @param {string} title 标题文字
 * @param {any[]} children 正文
 * @returns {any}
 */
function buildCallout(kind, title, children) {
  return {
    type: 'blockquote',
    data: { hProperties: { className: ['callout', `callout--${kind}`] } },
    children: [
      // 标题用段落包一层，避免它和正文第一段粘在一起
      {
        type: 'paragraph',
        data: { hProperties: { className: ['callout__title'] } },
        children: [{ type: 'text', value: title }],
      },
      ...children,
    ],
  };
}

export const admonitionPlugin = {
  name: 'article-admonition',
  /**
   * 访问器是「函数」而不是 `{ visit }` 对象（`hastPlugins` 那边才是对象写法）。
   * 返回一个节点 = 替换；返回 `undefined` = 原样保留。
   * @param {any} node
   */
  containerDirective(node) {
    const raw = String(node.name ?? '').toLowerCase();
    const { label, rest } = splitLabel(node.children);

    // 视频先分派走：认得出地址就出 iframe，认不出就往下走成 note，内容不丢。
    if (raw === 'video') {
      const video = videoDirective(rest, label);
      if (video) return video;

      // 地址写在同一行时解析器已经把文本丢了，这里只能明说，不能给一个空框。
      if (rest.length === 0) {
        return buildCallout('caution', '视频地址没读到', [
          {
            type: 'paragraph',
            children: [
              {
                type: 'text',
                value:
                  ':::video 里的地址要单独占一行。写在 :::video 同一行的话，'
                  + 'Markdown 解析器会把它整段丢掉，这里什么也拿不到。',
              },
            ],
          },
        ]);
      }
    }

    const kind = Object.prototype.hasOwnProperty.call(KINDS, raw) ? raw : 'note';
    return buildCallout(kind, label || KINDS[kind], rest);
  },
};

export default admonitionPlugin;
