/**
 * 正文图片的两个构建期加工步骤。
 *
 * 分工
 * ----
 * - `imageAttrsPlugin`：给每个 `<img>` 补 `loading` / `decoding` / `referrerpolicy`，
 *   并在能查到尺寸时补 `width` / `height`（浏览器据此预留高度，图片没下完也不会跳版）。
 * - `imagePicturePlugin`：把有 WebP 变体的站内图片包进 `<picture>`，
 *   用 `<source type="image/webp" srcset>` 让浏览器按屏宽挑合适的一档。
 *
 * 数据从哪来
 * ----------
 * - `src/data/image-manifest.json`：`scripts/optimize_images.mjs` 生成，
 *   记录站内图片的原始宽高和 WebP 变体清单。
 * - `src/data/remote-images.json`：`scripts/check_remote_images.py --write-dims` 生成，
 *   记录远程图片（直接引用原站 URL 的图）的宽高。
 * 两个文件都是可选的：读不到就只做属性补全，不报错、不阻断构建。
 *
 * 为什么不用 Astro 的 `<Image>` 组件
 * ----------------------------------
 * 文章是纯 Markdown，图片路径写成 `/images/blog/...`，走的是 `public/` 原样拷贝，
 * 不经过 Astro 的图片管线。要换成 `<Image>` 得把 52 张图搬进 `src/assets/` 并改
 * 所有文章的写法——收益只是"少写一个脚本"，代价是写作体验变差，不划算。
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';


const ROOT = path.resolve(import.meta.dirname, '..', '..');
const LOCAL_MANIFEST = path.join(ROOT, 'src', 'data', 'image-manifest.json');
const REMOTE_MANIFEST = path.join(ROOT, 'src', 'data', 'remote-images.json');

/**
 * 正文可用宽度：桌面端是 `--measure`（38rem），窄屏是视口减去左右内边距（各 1.5rem）。
 * 和 tokens.css / global.css 里的值保持一致；改那边记得改这里。
 *
 * `block` 是独占一段的单图；`grid` 是并组后的图（连续多图并排，宽度只剩半栏，
 * 写 38rem 会让浏览器多下一倍的流量）。并组容器是 `minmax(13rem, 1fr)` +
 * 1rem 间距，38rem 宽时稳定是两列，每列约 18.5rem，取 19rem。
 */
export const IMAGE_SIZES = {
  block: '(max-width: 40rem) calc(100vw - 3rem), 38rem',
  grid: '(max-width: 34rem) calc(100vw - 3rem), 19rem',
};

const SIZES = IMAGE_SIZES.block;

const BASE_ATTRS = [
  ['loading', 'lazy'],
  ['decoding', 'async'],
  // 远程图片（直接引用原站 URL）带上本站 Referer 会被部分站点拦掉，索性一律不带
  ['referrerpolicy', 'no-referrer'],
];

/** @type {Map<string, { w: number, h: number }> | null} */
let dimensionCache = null;

function readJson(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

/** 合并本地与远程两份尺寸清单，键都是站内绝对路径或完整 URL */
function loadDimensions() {
  if (dimensionCache) return dimensionCache;

  const map = new Map();

  const local = readJson(LOCAL_MANIFEST);
  for (const [src, entry] of Object.entries(local?.images ?? {})) {
    if (entry && typeof entry.w === 'number' && typeof entry.h === 'number') {
      map.set(src, { w: entry.w, h: entry.h });
    }
  }

  const remote = readJson(REMOTE_MANIFEST);
  for (const [url, entry] of Object.entries(remote?.images ?? {})) {
    if (entry && typeof entry.w === 'number' && typeof entry.h === 'number' && !map.has(url)) {
      map.set(url, { w: entry.w, h: entry.h });
    }
  }

  dimensionCache = map;
  return map;
}

/** @type {Map<string, { w: number, src: string }[]> | null} */
let variantCache = null;

function loadVariants() {
  if (variantCache) return variantCache;
  const local = readJson(LOCAL_MANIFEST);
  const map = new Map();
  for (const [src, entry] of Object.entries(local?.images ?? {})) {
    const variants = Array.isArray(entry?.variants) ? entry.variants : [];
    const usable = variants.filter((v) => v && typeof v.w === 'number' && typeof v.src === 'string');
    if (usable.length > 0) map.set(src, usable);
  }
  variantCache = map;
  return map;
}

/** 测试用：丢掉缓存，让下次调用重新读盘 */
export function resetImageCaches() {
  dimensionCache = null;
  variantCache = null;
}

export const imageAttrsPlugin = {
  name: 'article-image-attrs',
  element: {
    filter: ['img'],
    /**
     * @param {any} node
     * @param {any} ctx
     */
    visit(node, ctx) {
      for (const [key, value] of BASE_ATTRS) {
        // 作者显式写过的（比如手写 figure 里想 eager 加载）就尊重原值
        if (node.properties?.[key] != null) continue;
        ctx.setProperty(node, key, value);
      }

      const src = node.properties?.src;
      if (typeof src !== 'string') return;
      const size = loadDimensions().get(src);
      if (!size) return;

      if (node.properties?.width == null) ctx.setProperty(node, 'width', size.w);
      if (node.properties?.height == null) ctx.setProperty(node, 'height', size.h);
    },
  },
};

export const imagePicturePlugin = {
  name: 'article-image-picture',
  element: {
    filter: ['img'],
    /**
     * @param {any} node
     * @param {any} ctx
     */
    visit(node, ctx) {
      const src = node.properties?.src;
      // 只处理站内绝对路径；远程图和相对路径没有本地变体
      if (typeof src !== 'string' || !src.startsWith('/')) return;

      const parent = ctx.parent(node);
      if (!parent) return;
      // 已经是 picture 里的 img 了（重复跑、或作者手写），不再套一层
      if (parent.type === 'element' && parent.tagName === 'picture') return;

      const variants = loadVariants().get(src);
      if (!variants || variants.length === 0) return;

      const srcset = variants.map((v) => `${v.src} ${v.w}w`).join(', ');

      // <picture> 里 <source> 必须排在 <img> 前面，所以整个结构一次建好，
      // 再用 replaceNode 顶掉原来的 <img>（img 节点本身被搬进新结构里）。
      ctx.replaceNode(node, {
        type: 'element',
        tagName: 'picture',
        properties: { className: ['article-picture'] },
        children: [
          {
            type: 'element',
            tagName: 'source',
            properties: { type: 'image/webp', srcSet: srcset, sizes: SIZES },
            children: [],
          },
          node,
        ],
      });
    },
  },
};

export default imageAttrsPlugin;
