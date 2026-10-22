import { absoluteUrl } from '../config/site';

/**
 * robots.txt 由站点配置生成，避免把正式域名硬编码在静态文件里。
 * sitemap 由 @astrojs/sitemap 生成，索引文件为 /sitemap-index.xml。
 */
export function GET() {
  const body = [
    'User-agent: *',
    'Allow: /',
    '',
    `Sitemap: ${absoluteUrl('/sitemap-index.xml')}`,
    '',
  ].join('\n');

  return new Response(body, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
