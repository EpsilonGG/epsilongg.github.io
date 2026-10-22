import { getCollection, type CollectionEntry } from 'astro:content';

export type Post = CollectionEntry<'blog'>;

/**
 * 读取所有正式发布的文章，按发布日期倒序排列。
 *
 * 草稿（draft: true）在首页、归档、RSS 与静态路由中统一被过滤，
 * 因此默认不会出现在正式站点上。需要预览草稿时，把 frontmatter 中的
 * draft 改为 false 即可。
 */
export async function getPublishedPosts(): Promise<Post[]> {
  const posts = await getCollection('blog', ({ data }) => data.draft !== true);

  return posts.sort((a, b) => {
    const diff = b.data.pubDate.getTime() - a.data.pubDate.getTime();
    // 同一天发布时按 id 排序，保证每次构建顺序稳定
    return diff !== 0 ? diff : a.id.localeCompare(b.id);
  });
}

/** 文章详情页路径。id 即文件名（不含扩展名）。 */
export function postPath(post: Post): string {
  return `/blog/${post.id}/`;
}

/**
 * 统一的日期格式：YYYY-MM-DD。
 * 使用 UTC 取值，避免构建机器时区不同导致日期偏移。
 */
export function formatDate(date: Date): string {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function formatDateTime(date: Date): string {
  return date.toISOString();
}

export interface PostYearGroup {
  year: number;
  posts: Post[];
}

/** 按年份分组，年份与组内文章均为倒序，年份由真实数据生成。 */
export function groupPostsByYear(posts: Post[]): PostYearGroup[] {
  const groups = new Map<number, Post[]>();

  for (const post of posts) {
    const year = post.data.pubDate.getUTCFullYear();
    const bucket = groups.get(year);
    if (bucket) {
      bucket.push(post);
    } else {
      groups.set(year, [post]);
    }
  }

  return [...groups.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([year, items]) => ({ year, posts: items }));
}
