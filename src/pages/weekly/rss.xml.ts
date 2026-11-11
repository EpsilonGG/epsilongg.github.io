import rss from '@astrojs/rss';
import type { APIContext } from 'astro';

import { site } from '../../config/site';
import { getWeeklyReports, weeklyPath, publishedDate } from '../../lib/weekly';

/**
 * 周报归档 Feed，独立于 `/rss.xml`（只收笔记）与 `/daily/rss.xml`。
 *
 * 周报是「一周一次、由 AI 汇总」的内容，混进主 feed 会改变既有订阅者
 * 收到的东西；分开也和归档页的一级栏目结构对齐。
 */
export async function GET(context: APIContext) {
  const reports = getWeeklyReports();

  return rss({
    title: `${site.name} · 周报`,
    description: 'Galgame 周报：把每天的 Galgame 日报汇总成一期，按新作与作品情报整理',
    site: context.site ?? site.url,
    items: reports.map((report) => ({
      title: report.issue.title,
      description: report.description,
      // 真实发布时间（周六中午），不是覆盖窗口的结束日
      pubDate: publishedDate(report),
      link: weeklyPath(report.issue.id),
    })),
    customData: `<language>${site.lang}</language>`,
  });
}
