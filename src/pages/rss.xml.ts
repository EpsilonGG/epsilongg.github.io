import rss from '@astrojs/rss';
import type { APIContext } from 'astro';

import { site } from '../config/site';
import { profile } from '../config/profile';
import { getPublishedPosts, postPath } from '../lib/posts';

/**
 * RSS 2.0 Feed。
 *
 * - 只包含正式发布的文章（草稿已在 getPublishedPosts 中过滤）。
 * - 没有文章时仍然返回合法的空 Feed，构建不会失败。
 * - 链接使用站点正式域名的绝对地址。
 * - `source: ai` 的文章在标题前加「AI 整理」：站内列表靠滑块默认隐藏 + 徽标披露，
 *   feed 没有开关可翻，只能在标题里披露，否则订阅者收到的东西跟原创无从分辨。
 */
export async function GET(context: APIContext) {
  const posts = await getPublishedPosts();

  return rss({
    title: site.name,
    description: profile.description || site.description,
    site: context.site ?? site.url,
    items: posts.map((post) => ({
      title: post.data.source === 'ai' ? `[AI 整理] ${post.data.title}` : post.data.title,
      description: post.data.description ?? '',
      pubDate: post.data.pubDate,
      link: postPath(post),
    })),
    customData: `<language>${site.lang}</language>`,
  });
}
