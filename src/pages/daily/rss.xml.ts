import rss from '@astrojs/rss';
import type { APIContext } from 'astro';

import { site } from '../../config/site';
import { getDailyReports, dailyPath } from '../../lib/daily';

/**
 * 日报归档 Feed。
 *
 * 独立于 `/rss.xml`（那个只收「笔记」）。分开的理由：日报每天一期、
 * 而且是 AI 整理的，混进主 feed 会改变既有订阅者收到的东西。
 *
 * 存在的意义是「存档可订阅」——归档页只能翻，feed 能被阅读器收走。
 */
export async function GET(context: APIContext) {
  const reports = await getDailyReports();

  return rss({
    title: `${site.name} · 日报`,
    description: 'X（推特）声优动态日报，按小时编号存档',
    site: context.site ?? site.url,
    items: reports.map((report) => ({
      title: report.data.title,
      description: report.data.description ?? '',
      pubDate: report.data.pubDate,
      link: dailyPath(report),
    })),
    customData: `<language>${site.lang}</language>`,
  });
}
