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
 */

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

export const admonitionPlugin = {
  name: 'article-admonition',
  /**
   * 访问器是「函数」而不是 `{ visit }` 对象（`hastPlugins` 那边才是对象写法）。
   * 返回一个节点 = 替换；返回 `undefined` = 原样保留。
   * @param {any} node
   */
  containerDirective(node) {
    const raw = String(node.name ?? '').toLowerCase();
    const kind = Object.prototype.hasOwnProperty.call(KINDS, raw) ? raw : 'note';
    const { label, rest } = splitLabel(node.children);
    const title = label || KINDS[kind];

    /** @type {any[]} */
    const children = [];

    // 标题用段落包一层，避免它和正文第一段粘在一起
    children.push({
      type: 'paragraph',
      data: { hProperties: { className: ['callout__title'] } },
      children: [{ type: 'text', value: title }],
    });

    children.push(...rest);

    // 返回值的类型要收窄成 satteri 的 `MdastVisitorResult`（它认的是 mdast 的
    // `Blockquote` 字面量类型），这里手工造节点只能是 `any`，否则 astro check 报 2322。
    /** @type {any} */
    const block = {
      type: 'blockquote',
      data: { hProperties: { className: ['callout', `callout--${kind}`] } },
      children,
    };
    return block;
  },
};

export default admonitionPlugin;
