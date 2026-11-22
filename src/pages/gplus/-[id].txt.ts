import type { APIContext } from 'astro';
import { getGplusReports, gplusName, gplusSourceUrl, type Gplus } from '../../lib/gplus';

/** Gplus 日报纯文字出口：`/gplus/Gplus_001.txt`，GFM Markdown。 */
export async function getStaticPaths() {
  const reports = await getGplusReports();
  return reports.map((report) => ({ params: { id: report.id }, props: { report } }));
}

function sourceSuffix(sources: string[]): string {
  const urls = sources.map(gplusSourceUrl).filter((u): u is string => Boolean(u));
  if (!urls.length) return '';
  return ' ' + urls.map((u, i) => `[原文${urls.length > 1 ? i + 1 : ''}](${u})`).join(' ');
}

export function plainText(report: Gplus): string {
  const { title, description, highlights, insights, interactions, people } = report.data;
  const lines: string[] = [`# **${title}**`, ''];
  if (description) lines.push(description, '');
  lines.push('## **今日看点**', '');
  for (const claim of highlights) lines.push(`- ${claim.text}${sourceSuffix(claim.sources)}`);
  if (interactions.length) {
    lines.push('', '## **账号互动**', '');
    for (const claim of interactions) lines.push(`- ${claim.text}${sourceSuffix(claim.sources)}`);
  }
  lines.push('', '## **详细**', '');
  for (const person of people) {
    if (!person.summary.trim()) continue;
    lines.push(`- ${gplusName(person.handle)}：${person.summary}${sourceSuffix(person.sources)}`);
  }
  if (insights.length) {
    lines.push('', '## **洞察**', '');
    for (const claim of insights) lines.push(`- ${claim.text}${sourceSuffix(claim.sources)}`);
  }
  return lines.join('\n') + '\n';
}

export function GET({ props }: APIContext) {
  const { report } = props as { report: Gplus };
  return new Response(plainText(report), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
