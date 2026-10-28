import type { APIContext } from 'astro';

import { cienReport, getDailyJapanese, getDailyReports, type Daily, type DailyJa } from '../../lib/daily';

/**
 * 日语版出口：`/daily/<期号>.ja.txt`。
 *
 * 用途只有一个：**贴到 Ci-en 当播报**。所以它不是「中文纯文本版的翻译副本」，
 * 而是按 Ci-en 记法排过版的一份正文——见 `lib/cien.ts` 顶部对记法的说明。
 *
 * 只有存在 `data/daily/<期号>/report.ja.json` 的期号才有这个出口。
 * 没有日语版的期号不生成文件、页面上也不挂按钮，链接不会 404。
 */
export async function getStaticPaths() {
  const [reports, japanese] = await Promise.all([getDailyReports(), getDailyJapanese()]);

  return reports
    .filter((report) => japanese.has(report.id))
    .map((report) => ({
      params: { id: report.id },
      props: { report, ja: japanese.get(report.id)! },
    }));
}

export function GET({ props }: APIContext) {
  const { report, ja } = props as { report: Daily; ja: DailyJa };

  return new Response(cienReport(report, ja), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
