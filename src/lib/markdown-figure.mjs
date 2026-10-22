/**
 * 把「带 title 的图片」变成带图注的 figure。
 *
 * 写作约定：`![替代文字](/images/x.jpg "图注文字")`
 * Markdown 里的 title 会变成 `<img title>`，这里在构建阶段把它升级成
 * `<figure><img><figcaption>图注文字</figcaption></figure>`，
 * 这样图注是真正的 HTML 文本（可选中、可被搜索引擎读到），
 * 不依赖 JavaScript，也不会在页面加载后突然出现。
 *
 * 只处理「独占一个段落」的图片；行内小图标保持原样。
 */

/** @typedef {{ type: string, tagName?: string, properties?: Record<string, unknown>, children?: any[], value?: string }} HastNode */

const CAPTION_CLASS = 'article-figure__caption';
const FIGURE_CLASS = 'article-figure';

/** @param {any} node */
function isImageOnlyParagraph(node) {
  if (!node || node.type !== 'element' || node.tagName !== 'p') return false;
  const children = node.children ?? [];
  return children.length === 1 && children[0]?.type === 'element' && children[0].tagName === 'img';
}

export const figureCaptionPlugin = {
  name: 'article-figure-caption',
  element: {
    filter: ['img'],
    /**
     * @param {any} node
     * @param {any} ctx
     */
    visit(node, ctx) {
      const title = node.properties?.title;
      if (typeof title !== 'string' || title.trim() === '') return;

      const parent = ctx.parent(node);
      // 行内图片（段落里还有别的文字）不动
      if (!isImageOnlyParagraph(parent)) return;

      const caption = {
        type: 'element',
        tagName: 'figcaption',
        properties: { className: [CAPTION_CLASS] },
        children: [{ type: 'text', value: title.trim() }],
      };

      // 用 figure 替换整个段落，避免出现 <p><figure> 这种非法嵌套
      ctx.replaceNode(parent, {
        type: 'element',
        tagName: 'figure',
        properties: { className: [FIGURE_CLASS] },
        children: [node, caption],
      });

      // title 已经变成可见的图注，去掉避免鼠标悬停时重复出现
      ctx.setProperty(node, 'title', null);
    },
  },
};

export default figureCaptionPlugin;
