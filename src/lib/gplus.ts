/**
 * Gplus 日报的取数与派生层。
 *
 * 期号是 `Gplus_XXX`（XXX 至少三位，独立序列），正本在 `data/gplus/<期号>/report.json`。
 * 与 `lib/daily.ts` 分开是因为期号规则不同；字段形状一致，页面因此能长得一样。
 * 名单显示名取自 `src/config/gplus-roster.json`（名单 1-1 全集 403 个 X 号）。
 */
import { getCollection, type CollectionEntry } from 'astro:content';
import gplusRoster from '../config/gplus-roster.json';

type GplusEntry = CollectionEntry<'gplusReports'>;

/** 期号覆盖的日期按 JST 取（日报惯例）；不能用 UTC 的 formatDate，否则 JST 00:00 会退回前一天。 */
const issueDayFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});
function formatIssueDay(date: Date): string {
  return issueDayFormat.format(date).replace(/\//g, '-');
}

export const GPLUS_ID_PATTERN = /^Gplus_(\d{3,})$/;

export function parseGplusId(id: string): { seq: number } | null {
  const match = GPLUS_ID_PATTERN.exec(id);
  return match ? { seq: Number(match[1]) } : null;
}

export type Gplus = Omit<GplusEntry, 'data'> & {
  data: GplusEntry['data'] & {
    title: string;
    pubDate: Date;
    covered: Date | null;
    seq: number;
  };
};

export type GplusData = Gplus['data'];

type RosterAccount = { handle: string; name: string; group: string; brand?: string };
const roster = gplusRoster.accounts as RosterAccount[];
const nameMap = new Map(roster.map((a) => [a.handle.toLowerCase(), a.name]));
const groupMap = new Map(roster.map((a) => [a.handle.toLowerCase(), a.group]));

export function gplusName(handle: string): string {
  return nameMap.get(handle.toLowerCase()) ?? `@${handle}`;
}

export function groupOf(handle: string): string {
  return groupMap.get(handle.toLowerCase()) ?? 'other';
}

export function isRosterHandle(handle: string): boolean {
  return nameMap.has(handle.toLowerCase());
}

export const GROUP_LABEL: Record<string, string> = {
  creator: '创作者・从业者',
  brand: '品牌・厂商',
  info: '信息号・媒体',
  other: '其它',
};

export function gplusProfileUrl(handle: string): string {
  return `https://x.com/${handle}`;
}

function dateFrom(s: string | undefined): Date | null {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

export async function getGplusReports(): Promise<Gplus[]> {
  const reports = await getCollection('gplusReports');
  return reports
    .map((entry) => {
      const parsed = parseGplusId(entry.id);
      if (!parsed) return null;
      const window = entry.data.issue.window;
      const covered = dateFrom(window?.start) ?? dateFrom(entry.data.issue.published_at);
      const pubDate = dateFrom(entry.data.issue.published_at) ?? new Date(0);
      const day = covered ? formatIssueDay(covered) : entry.id;
      return {
        ...entry,
        data: {
          ...entry.data,
          title: `Gplus 日报 · ${day}`,
          pubDate,
          covered,
          seq: parsed.seq,
        },
      } satisfies Gplus;
    })
    .filter((r): r is Gplus => r !== null)
    .sort((a, b) => b.data.seq - a.data.seq || b.data.pubDate.getTime() - a.data.pubDate.getTime());
}

export function gplusSourceUrl(key: string): string | null {
  const match = /^x:(\d+)$/.exec(key);
  return match ? `https://x.com/i/web/status/${match[1]}` : null;
}
