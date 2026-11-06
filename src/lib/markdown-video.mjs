/**
 * 把 `:::video` 编译成响应式的视频嵌入。
 *
 * 写作约定（和 `:::note` 同一套容器指令写法）：
 *
 *   :::video
 *   https://www.youtube.com/watch?v=VIDEO_ID
 *   :::
 *
 *   :::video[标题（可选，会变成 iframe 的 title 和下面的链接文字）]
 *   https://www.bilibili.com/video/BV1xx411c7mD
 *   :::
 *
 * 只认 YouTube 与 Bilibili 两家——它们的嵌入地址有稳定规律，可以纯静态拼出来，
 * 构建时不联网。其它站点（Vimeo、ニコニコ 等）没有需求，不做；写错了会退回
 * 提示框，内容不丢（见 `admonitionPlugin` 的兜底）。
 *
 * 三条取舍，都是照着同类博客的通行做法来的：
 *
 * 1. **16:9 的框由 CSS 撑，不写死 width/height。** iframe 用绝对定位铺满
 *    `.article-video__frame`，手机上不会横向溢出，也不会在加载前塌成 0 高。
 * 2. **YouTube 走 `youtube-nocookie.com`。** 播放前不落第三方 Cookie；
 *    `referrerpolicy` 只带 origin，不把完整页面地址递给对方。
 * 3. **永远留一条「在原站观看」的链接。** 嵌入被墙、被扩展拦掉、或者访客
 *    不想加载第三方脚本时，这行字是唯一的出口——Bilibili 与 YouTube 各自
 *    在对方的地盘上都可能打不开。
 */

/** YouTube：watch?v= / youtu.be / embed / shorts / live 都归一到同一个 11 位 ID */
const YOUTUBE =
  /(?:youtube(?:-nocookie)?\.com\/(?:watch\?(?:[^\s]*&)?v=|embed\/|shorts\/|live\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/;

/** Bilibili：新版 BV 号 */
const BILIBILI_BV =
  /(?:bilibili\.com\/video\/|player\.bilibili\.com\/player\.html\?(?:[^\s]*&)?bvid=)(BV[A-Za-z0-9]{10})/;

/** Bilibili：老版 av 号，仍然有效，顺手兼容 */
const BILIBILI_AV = /bilibili\.com\/video\/av(\d+)/i;

const PROVIDER_LABEL = { youtube: 'YouTube', bilibili: 'Bilibili' };

/** 属性值转义：`&` 要写成 `&amp;`，否则 URL 里的查询串会被浏览器吃掉一段 */
function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * 把一段视频地址解析成嵌入参数；认不出返回 null。
 * @param {string} url
 */
export function parseVideoUrl(url) {
  const raw = String(url ?? '').trim();
  if (!raw) return null;

  const youtube = raw.match(YOUTUBE);
  if (youtube) {
    const id = youtube[1];
    return {
      provider: 'youtube',
      id,
      // rel=0：播完别推一堆别人的视频，访谈页里那是最容易让人分心的东西
      src: `https://www.youtube-nocookie.com/embed/${id}?rel=0`,
      watch: `https://www.youtube.com/watch?v=${id}`,
    };
  }

  const bv = raw.match(BILIBILI_BV);
  if (bv) {
    return {
      provider: 'bilibili',
      id: bv[1],
      src: `https://player.bilibili.com/player.html?bvid=${bv[1]}&page=1&high_quality=1&danmaku=0`,
      watch: `https://www.bilibili.com/video/${bv[1]}`,
    };
  }

  const av = raw.match(BILIBILI_AV);
  if (av) {
    return {
      provider: 'bilibili',
      id: `av${av[1]}`,
      src: `https://player.bilibili.com/player.html?aid=${av[1]}&page=1&high_quality=1&danmaku=0`,
      watch: `https://www.bilibili.com/video/av${av[1]}`,
    };
  }

  return null;
}

/**
 * 从指令的正文里挖出第一个地址。
 *
 * 地址可能落在三种地方：纯文本（`https://…` 会被 GFM 自动变成链接）、
 * `<https://…>` 自动链接、以及 `[文字](url)`。三种都算。
 * @param {any[]} children
 */
function findUrl(children) {
  /** @type {string[]} */
  const candidates = [];

  const walk = (node) => {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'link' && node.url) candidates.push(String(node.url));
    if (node.type === 'text' && typeof node.value === 'string') {
      for (const hit of String(node.value).match(/https?:\/\/[^\s<>()]+/g) ?? []) {
        candidates.push(hit);
      }
    }
    if (Array.isArray(node.children)) node.children.forEach(walk);
  };

  (Array.isArray(children) ? children : []).forEach(walk);
  return candidates.find((url) => parseVideoUrl(url)) ?? '';
}

/**
 * `:::video` 的正文 → 一个 mdast `html` 节点。
 *
 * 认不出地址时返回 null，由调用方退回提示框——**内容绝不静默丢掉**。
 *
 * @param {any[]} children 指令正文（已摘掉 `:::video[标题]` 那个标签段）
 * @param {string} label   方括号里的标题，可为空
 */
export function videoDirective(children, label = '') {
  const url = findUrl(children);
  if (!url) return null;

  const video = parseVideoUrl(url);
  if (!video) return null;

  const provider = PROVIDER_LABEL[video.provider];
  const title = label || `${provider} 视频`;
  const linkText = label || `在 ${provider} 观看`;

  const value = [
    '<figure class="article-video">',
    '<div class="article-video__frame">',
    `<iframe src="${esc(video.src)}" title="${esc(title)}" loading="lazy"`,
    ' referrerpolicy="strict-origin-when-cross-origin"',
    ' allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"',
    ' allowfullscreen></iframe>',
    '</div>',
    '<figcaption class="article-video__caption">',
    `<a href="${esc(video.watch)}" target="_blank" rel="noopener noreferrer">${esc(linkText)}</a>`,
    '</figcaption>',
    '</figure>',
  ].join('');

  return { type: 'html', value };
}

export default videoDirective;
