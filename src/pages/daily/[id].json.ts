import type { APIContext } from 'astro';

import { getDailyReports, type Daily } from '../../lib/daily';

/**
 * JSON 出口：`/daily/<期号>.json`。
 *
 * 和 HTML 页读的是**同一份** `data/daily/<期号>/report.json`，不另存一份数据——
 * 「一份数据多种 encoding」。给第三方、以后的 App、以及自己写脚本用。
 *
 * 输出的就是正本本身（去掉渲染时派生的 `title` / `pubDate` / `covered` / `seq`），
 * 包括 `sources`：页面不显示来源，但对外输出必须带，否则「这句话是从哪条推来的」就没法追。
 *
 * `schema_version` 也一并给出，外部消费方可以据此判断能不能读。
 */
export async function getStaticPaths() {
  const reports = await getDailyReports();
  return reports.map((report) => ({ params: { id: report.id }, props: { report } }));
}

export function GET({ props }: APIContext) {
  const { report } = props as { report: Daily };
  // 派生字段不进 JSON：它们由期号算出来，多存一份就多一处能和 issue 对不上的地方。
  // 出口必须与正本逐字节相同，所以新增派生字段时**这里也要加**——`check:daily` 盯着。
  const {
    title: _title,
    pubDate: _pubDate,
    covered: _covered,
    seq: _seq,
    ...canonical
  } = report.data;

  return new Response(JSON.stringify(canonical, null, 2) + '\n', {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
    },
  });
}
