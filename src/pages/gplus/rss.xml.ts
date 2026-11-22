import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { site } from '../../config/site';
import { getGplusReports } from '../../lib/gplus';

/** Gplus 日报归档 Feed：与日报主 feed 分开，避免改变既有订阅者的内容。 */
export async function GET(context: APIContext) {
  const reports = await getGplusReports();
  return rss({
    title: `${site.name} · Gplus 日报`,
    description: '名单 1-1 全集的 Galgame 业界日报：创作者、品牌与信息号的动向',
    site: context.site ?? site.url,
    items: reports.map((report) => ({
      title: report.data.title,
      description: report.data.description ?? '',
      pubDate: report.data.pubDate,
      link: `/gplus/${report.id}/`,
    })),
    customData: `<language>${site.lang}</language>`,
  });
}
