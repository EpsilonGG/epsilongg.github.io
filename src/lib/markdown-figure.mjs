/**
 * 把「带 title 的图片」变成带图注的 figure。
 *
 * 写作约定：`![替代文字](/images/x.jpg "图注文字")`
 * Markdown 里的 title 会变成 `<img title>`，这里在构建阶段把它升级成
 * `<figure><img><figcaption>图注文字</figcaption></figure>`，
 * 这样图注是真正的 HTML 文本（可选中、可被搜索引擎读到），
 * 不依赖 JavaScript，也不会在页面加载后突然出现。
 *
 * 认得的四种结构（都要求图片「独占一个段落」）：
 *
 *   p > img                 ← 普通图片
 *   p > picture > img       ← 已被 markdown-images.mjs 包过 WebP 的图片
 *   p > a > img             ← 点击可放大的图片
 *   p > a > picture > img   ← 两者叠加
 *
 * 另外：连续两张以上「带图注的独占段落图」会自动并成一组
 * `<div class="article-figure-grid">`，窄屏一行一张、宽屏并排。
 * 行内小图标（段落里还有别的文字）一律不动。
 *
 * 实现上有一处坑值得记住：satteri 的 `after(root)` 钩子里拿到的是**副本**，
 * 在那里改 `root.children` 不会影响输出。所以「并组」这件事必须在
 * element visitor 里用 `replaceNode` / `removeChildAt` 完成。
 */

import { IMAGE_SIZES } from './markdown-images.mjs';

const CAPTION_CLASS = 'article-figure__caption';
const FIGURE_CLASS = 'article-figure';
const GRID_CLASS = 'article-figure-grid';

/**
 * 并排之后每张图只剩半栏宽，`sizes` 必须跟着改，否则浏览器按 38rem 挑图，
 * 白白多下一倍流量。取值见 markdown-images.mjs 的 IMAGE_SIZES.grid。
 */
const GRID_SIZES = IMAGE_SIZES.grid;

/** 段落里只允许有一个元素子节点，且必须是这几种之一 */
const MEDIA_TAGS = new Set(['img', 'picture', 'a']);

/** 每个文档开始时清空：记录已经并进某组的图片（按 src 认，satteri 的节点身份不稳定） */
let consumedSrcs = new Set();

/**
 * 从段落里取出「这一段的图片」以及「要被搬进 figure 的那个顶层节点」。
 * @param {any} paragraph
 * @returns {{ img: any, top: any } | null}
 */
function readImageParagraph(paragraph) {
  if (!paragraph || paragraph.type !== 'element' || paragraph.tagName !== 'p') return null;

  const children = paragraph.children ?? [];
  // 只认「独占一个段落」：一个元素子节点，且没有夹带文字
  if (children.length !== 1) return null;

  const top = children[0];
  if (!top || top.type !== 'element' || !MEDIA_TAGS.has(top.tagName)) return null;

  if (top.tagName === 'img') return { img: top, top };

  if (top.tagName === 'picture') {
    // <picture> 里除了 <img> 还可能有若干个 <source>，所以不能要求只有一个子节点
    const inner = top.children ?? [];
    const imgs = inner.filter((c) => c?.type === 'element' && c.tagName === 'img');
    const others = inner.filter(
      (c) => c?.type === 'element' && c.tagName !== 'img' && c.tagName !== 'source',
    );
    if (imgs.length !== 1 || others.length > 0) return null;
    return { img: imgs[0], top };
  }

  // top.tagName === 'a'
  const inner = top.children ?? [];
  if (inner.length !== 1) return null;

  const media = inner[0];
  if (!media || media.type !== 'element') return null;

  if (media.tagName === 'img') return { img: media, top };
  if (media.tagName === 'picture') {
    const imgs = (media.children ?? []).filter((c) => c?.type === 'element' && c.tagName === 'img');
    if (imgs.length !== 1) return null;
    return { img: imgs[0], top };
  }
  return null;
}

/** 段落之间会留下换行产生的纯空白文本节点，扫描相邻图时要把它们当空气 */
function isWhitespaceText(node) {
  return node?.type === 'text' && /^\s*$/.test(node.value ?? '');
}

/** 从段落里读出图注文字，没有就返回 null */function readCaption(found) {
  const title = found?.img?.properties?.title;
  if (typeof title !== 'string') return null;
  const trimmed = title.trim();
  return trimmed === '' ? null : trimmed;
}

/**
 * 把 figure 里所有 `<picture><source>` 的 `sizes` 换成并排尺寸。
 * 图片可能被 `<a>` 包着，所以要递归找。
 */
function applyGridSizes(ctx, node) {
  for (const child of node.children ?? []) {
    if (child?.type !== 'element') continue;
    if (child.tagName === 'source') {
      ctx.setProperty(child, 'sizes', GRID_SIZES);
    } else if (child.tagName === 'picture' || child.tagName === 'a') {
      applyGridSizes(ctx, child);
    }
  }
}

/** 造一个 figure 节点（图片 + 图注）。properties 是只读的，只能通过 ctx.setProperty 改。 */
function buildFigure(ctx, found, captionText) {
  // title 已经变成可见的图注，去掉避免鼠标悬停时重复出现
  ctx.setProperty(found.img, 'title', null);

  return {
    type: 'element',
    tagName: 'figure',
    properties: { className: [FIGURE_CLASS] },
    children: [
      found.top,
      {
        type: 'element',
        tagName: 'figcaption',
        properties: { className: [CAPTION_CLASS] },
        children: [{ type: 'text', value: captionText }],
      },
    ],
  };
}

export const figureCaptionPlugin = {
  name: 'article-figure-caption',
  /** 每篇文档开始时重置状态 */
  before() {
    consumedSrcs = new Set();
  },
  element: {
    filter: ['img'],
    /**
     * @param {any} node
     * @param {any} ctx
     */
    visit(node, ctx) {
      const src = node.properties?.src;
      if (typeof src === 'string' && consumedSrcs.has(src)) return;

      // 从 img 往上找到「独占一段」的那个段落：最多三层（picture / a / p）
      let paragraph = null;
      let cursor = node;
      for (let depth = 0; depth < 3; depth += 1) {
        const parent = ctx.parent(cursor);
        if (!parent || parent.type !== 'element') return;
        if (parent.tagName === 'p') {
          paragraph = parent;
          break;
        }
        cursor = parent;
      }
      if (!paragraph) return;

      const found = readImageParagraph(paragraph);
      // 段落里除了这张图还有别的东西 → 行内图片，不动。
      // 按 src 比对而不是对象身份：satteri 的节点是惰性物化的，
      // 同一个节点在不同时机读出来可能是不同的包装对象。
      if (!found || found.img?.properties?.src !== src) return;

      const captionText = readCaption(found);
      if (!captionText) return;

      const figure = buildFigure(ctx, found, captionText);
      if (typeof src === 'string') consumedSrcs.add(src);

      // 看看后面还有没有「同样带图注的独占段落图」，有就一起并组
      const parent = ctx.parent(paragraph);
      const index = ctx.indexOf(paragraph);
      const siblings = parent?.children;

      /** @type {any[]} */
      const extraFigures = [];
      /** @type {number[]} */
      const extraIndexes = [];

      if (Array.isArray(siblings) && typeof index === 'number') {
        for (let k = index + 1; k < siblings.length; k += 1) {
          const sibling = siblings[k];
          if (isWhitespaceText(sibling)) continue;

          const siblingFound = readImageParagraph(sibling);
          const siblingCaption = readCaption(siblingFound);
          const siblingSrc = siblingFound?.img?.properties?.src;
          if (!siblingFound || !siblingCaption) break;

          extraFigures.push(buildFigure(ctx, siblingFound, siblingCaption));
          extraIndexes.push(k);
          if (typeof siblingSrc === 'string') consumedSrcs.add(siblingSrc);
        }
      }

      if (extraFigures.length === 0) {
        ctx.replaceNode(paragraph, figure);
        return;
      }

      // 两张以上：并成一组。先替换第一段，再从后往前删掉后面那几段，
      // 倒序删可以保证前面的下标不受影响。
      const group = [figure, ...extraFigures];
      for (const member of group) applyGridSizes(ctx, member);

      ctx.replaceNode(paragraph, {
        type: 'element',
        tagName: 'div',
        properties: { className: [GRID_CLASS] },
        children: group,
      });

      for (let k = extraIndexes.length - 1; k >= 0; k -= 1) {
        ctx.removeChildAt(parent, extraIndexes[k]);
      }
    },
  },
};

export default figureCaptionPlugin;
