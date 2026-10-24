/**
 * 给正文里所有图片补上三个现代属性。
 *
 * - `loading="lazy"`：长文动辄几十张图，首屏不必全下。
 * - `decoding="async"`：解码不占主线程，滚动更顺。
 * - `referrerpolicy="no-referrer"`：请求图片时不带 Referer。
 *   这一条是给「远程图片」（直接引用原站 URL）准备的：
 *   不少站点靠 Referer 判断是不是自家页面在引用，带上本站域名会被拦；
 *   不带 Referer 基本都能过。本地图片加这条没有副作用。
 *
 * 注意这里**不**改 src，也不读文件，所以远程 URL 和本地路径走同一条路。
 */

/** @typedef {{ type: string, tagName?: string, properties?: Record<string, unknown>, children?: any[] }} HastNode */

const ATTRS = [
  ['loading', 'lazy'],
  ['decoding', 'async'],
  ['referrerpolicy', 'no-referrer'],
];

export const imageAttrsPlugin = {
  name: 'article-image-attrs',
  element: {
    filter: ['img'],
    /**
     * @param {any} node
     * @param {any} ctx
     */
    visit(node, ctx) {
      for (const [key, value] of ATTRS) {
        // 作者显式写过的（比如手写 figure 里想 eager 加载）就尊重原值
        if (node.properties?.[key] != null) continue;
        ctx.setProperty(node, key, value);
      }
    },
  },
};

export default imageAttrsPlugin;
