import type { APIContext } from 'astro';

import { getDailyReports, plainText, type Daily } from '../../lib/daily';

/**
 * 纯文本出口：`/daily/<期号>.txt`。
 *
 * 给复制粘贴用，也给 M6 的视频稿用——口播稿要从「读者已经看到的那段字」出发，
 * 而不是从另一份摘要出发。所以它和 HTML 页读同一份 `report.json`，
 * 转换逻辑在 `lib/daily.ts` 的 `plainText()` 里（只换格式，不重新概括）。
 */
export async function getStaticPaths() {
  const reports = await getDailyReports();
  return reports.map((report) => ({ params: { id: report.id }, props: { report } }));
}

export function GET({ props }: APIContext) {
  const { report } = props as { report: Daily };

  return new Response(plainText(report), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
