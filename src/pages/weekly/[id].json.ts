import type { APIContext } from 'astro';

import { getWeeklyReports, type WeeklyReport } from '../../lib/weekly';

/**
 * JSON 出口：`/weekly/<期号>.json`。
 *
 * 输出就是发布正本本身，不另存一份数据——「一份数据多种 encoding」。
 * 与日报的 `<期号>.json` 同构，区别是周报正本已经是对外形态，
 * 没有需要剔除的派生字段。
 */
export function getStaticPaths() {
  return getWeeklyReports().map((report) => ({
    params: { id: report.issue.id },
    props: { report },
  }));
}

export function GET({ props }: APIContext) {
  const { report } = props as { report: WeeklyReport };
  return new Response(JSON.stringify(report, null, 2) + '\n', {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
    },
  });
}
