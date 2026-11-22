/**
 * 日报纯文字出口（`/daily/<id>.txt`）的 Markdown 排版。
 *
 * 目标平台是 kungal 论坛的 GFM 编辑器（见 https://www.kungal.com/topic/1225）：
 * 只能用 `#` 标题、`[..](https://..)` 链接、`-` 列表这些基础语法；不放图片，
 * 链接一律绝对 URL（论坛里相对地址会被当成站内地址）。这里只做格式转换，
 * 段落顺序、句子、人名都照日报正本，不重新概括、不补正本没有的内容。
 *
 * 单独成模块是为了能脱离 Astro（daily.ts 依赖 `astro:content`）做契约测试。
 */

export interface PlainClaim {
  text: string;
}

export interface PlainCategory {
  label: string;
  summary: string;
}

export interface PlainPerson {
  handle: string;
  summary: string;
  via: string[];
  sources?: string[];
}

export interface DailyPlainData {
  title: string;
  description?: string;
  highlights: PlainClaim[];
  works: string[];
  categories: PlainCategory[];
  interactions: PlainClaim[];
  people: PlainPerson[];
  insights: PlainClaim[];
}

/** 名字 / 主页由名单查，排版层不认识名单文件。 */
export interface PlainIdentity {
  nameOf(handle: string): string;
  profileUrlOf(handle: string): string;
}

/**
 * 正本里的来源键 → 绝对 URL。
 *
 * `x:<tweet id>` 用 `/i/web/status/`，不拼 handle：一条 `sources` 里可能混着
 * 转发的别人推文，按账号名拼会拼出坏链。`bilibili:<opus id>` 同理。
 * 不认识的键返回 null，宁可少一条链接也不造 URL。
 */
export function sourceUrl(key: string): string | null {
  const match = /^(x|bilibili):([0-9]+)$/.exec(key.trim());
  if (!match) return null;
  return match[1] === 'x'
    ? `https://x.com/i/web/status/${match[2]}`
    : `https://www.bilibili.com/opus/${match[2]}`;
}

function sourceLinks(sources: string[] | undefined): string {
  const urls = [...new Set((sources ?? []).map(sourceUrl).filter((url): url is string => url !== null))];
  if (urls.length === 0) return '';
  return ' ' + urls.map((url, index) => {
    const label = urls.length === 1 ? '原文' : `原文${index + 1}`;
    return `[${label}](${url})`;
  }).join(' ');
}

export function dailyPlainMarkdown(data: DailyPlainData, identity: PlainIdentity): string {
  const lines: string[] = [`# ${data.title}`];

  if (data.description?.trim()) {
    lines.push('', data.description.trim());
  }

  // 段落型栏目：一条一行，段间空行（论坛编辑器把裸回车合并成一行）。
  // 列表型栏目：跟页面一致用 `- `，论坛的列表语法按 GFM 走。
  const paragraphs = (heading: string, items: string[]) => {
    const body = items.map((text) => text.trim()).filter(Boolean);
    if (body.length > 0) lines.push('', `## ${heading}`, '', body.join('\n\n'));
  };
  const bullets = (heading: string, items: string[]) => {
    const body = items.map((text) => text.trim()).filter(Boolean);
    if (body.length > 0) lines.push('', `## ${heading}`, '', body.map((text) => `- ${text}`).join('\n'));
  };

  paragraphs('今日看点', data.highlights.map((claim) => claim.text));
  bullets('作品动态', data.works);
  bullets(
    '分类摘要',
    data.categories.filter((category) => category.summary.trim()).map(
      (category) => `${category.label}：${category.summary}`
    )
  );
  bullets('互动', data.interactions.map((claim) => claim.text));

  const people = data.people
    .filter((person) => person.summary.trim().length > 0)
    .map((person) => {
      const handle = person.handle;
      // 名单外的 nameOf 本来就返回 `@handle`，别再写一遍括号。
      const name = identity.nameOf(handle);
      const suffix = name === `@${handle}` ? '' : `（@${handle}）`;
      const via = person.via.length > 0
        ? `（另有 ${person.via.map((h) => `[@${h}](${identity.profileUrlOf(h)})`).join('、')}）`
        : '';
      return `[${name}](${identity.profileUrlOf(handle)})${suffix}：` +
        `${person.summary.trim()}${via}${sourceLinks(person.sources)}`;
    });
  bullets('详细', people);
  bullets('洞察', data.insights.map((claim) => claim.text));

  return lines.join('\n') + '\n';
}
