import { getCollection, type CollectionEntry } from 'astro:content';

export type Daily = CollectionEntry<'daily'>;

/**
 * 读取所有已发布的日报，按发布日期倒序排列。
 * 草稿（draft: true）被过滤，与 blog 集合保持一致。
 */
export async function getDailyReports(): Promise<Daily[]> {
  const reports = await getCollection('daily', ({ data }) => data.draft !== true);
  return reports.sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());
}

/** 日报详情页路径。id 即文件名（不含扩展名）。 */
export function dailyPath(post: Daily): string {
  return `/daily/${post.id}/`;
}

export { formatDate } from './posts';
