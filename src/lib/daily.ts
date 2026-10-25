import { getCollection, type CollectionEntry } from 'astro:content';

type DailyEntry = CollectionEntry<'daily'>;

/**
 * 日报条目。
 *
 * 时间不在 frontmatter 里写，而是从文件名解析出来——文件名是唯一事实来源，
 * 手改日期不可能和 URL 对不上。
 */
export type Daily = Omit<DailyEntry, 'data'> & {
  data: DailyEntry['data'] & { title: string; pubDate: Date };
};

/**
 * 日报编号：`YYMMDDHH`，八位数字，日本时间（JST）。
 *
 * 例：2026-10-31 22:00（JST）→ `26103122`。
 *
 * 精确到小时是为了**存档**：同一天可以出多期，重跑不会覆盖上一期。
 * 只到天的话，`2026-10-23.md` 一天只能有一个，补一次就把原稿冲掉了。
 */
export const DAILY_ID_PATTERN = /^(\d{2})(\d{2})(\d{2})(\d{2})$/;

/** JST 相对 UTC 的偏移（分钟）。固定值，不依赖运行环境时区。 */
const JST_OFFSET_MINUTES = 9 * 60;

/** 把 `26103122` 解析成 Date；格式不合法或日期不存在（如 2 月 30 日）返回 null。 */
export function parseDailyId(id: string): Date | null {
  const match = DAILY_ID_PATTERN.exec(id);
  if (!match) return null;

  const year = 2000 + Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23) return null;

  const offset = JST_OFFSET_MINUTES * 60 * 1000;
  const date = new Date(Date.UTC(year, month - 1, day, hour) - offset);

  // Date.UTC 会把 2 月 30 日进位成 3 月 2 日，回读一次才能确认真实存在
  const back = new Date(date.getTime() + offset);
  if (
    back.getUTCFullYear() !== year ||
    back.getUTCMonth() !== month - 1 ||
    back.getUTCDate() !== day ||
    back.getUTCHours() !== hour
  ) {
    return null;
  }

  return date;
}

/** 反向：把 Date 写成编号。给测试和脚本对齐用。 */
export function toDailyId(date: Date): string {
  const back = new Date(date.getTime() + JST_OFFSET_MINUTES * 60 * 1000);
  const pad = (value: number, width = 2) => String(value).padStart(width, '0');
  return (
    pad(back.getUTCFullYear() % 100) +
    pad(back.getUTCMonth() + 1) +
    pad(back.getUTCDate()) +
    pad(back.getUTCHours())
  );
}

const issueTimeFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const issueDayFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const issueMonthFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: 'long',
});

/** `2026/10/23 22:00` → 统一成 `2026-10-23 22:00`。 */
function normalize(text: string): string {
  return text.replace(/\//g, '-');
}

/** `2026-10-23 22:00`（JST） */
export function formatIssueTime(date: Date): string {
  return normalize(issueTimeFormat.format(date));
}

/** `2026-10-23`（JST） */
export function formatIssueDay(date: Date): string {
  return normalize(issueDayFormat.format(date));
}

/** `2026 年 10 月`（JST），归档分组用 */
export function formatIssueMonth(date: Date): string {
  return issueMonthFormat.format(date);
}

/** 归档用的月份键，`2026-10`，只用于分组和排序。 */
export function issueMonthKey(date: Date): string {
  return formatIssueDay(date).slice(0, 7);
}

/**
 * 读取所有已发布的日报，按发布时间倒序排列。
 * 草稿（draft: true）被过滤，与 blog 集合保持一致。
 */
export async function getDailyReports(): Promise<Daily[]> {
  const entries = await getCollection('daily', ({ data }) => data.draft !== true);

  const reports: Daily[] = entries.map((entry) => {
    const issuedAt = parseDailyId(entry.id);
    if (!issuedAt) {
      throw new Error(
        `[daily] 文件名 "${entry.id}" 不是合法的 YYMMDDHH 编号。` +
          '例：2026-10-31 22:00（JST）应命名为 26103122.md。'
      );
    }
    return {
      ...entry,
      data: {
        ...entry.data,
        // 标题也是派生的：一期日报的标题就是它的时间，没有别的信息量
        title: `X 日报 · ${formatIssueTime(issuedAt)}`,
        pubDate: issuedAt,
      },
    };
  });

  // 同一小时内只可能有一个文件；用 id 兜底保证顺序稳定
  return reports.sort(
    (a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime() || b.id.localeCompare(a.id)
  );
}

/** 按月份分组，保持倒序。归档列表用。 */
export function groupByMonth(reports: Daily[]): { key: string; label: string; items: Daily[] }[] {
  const groups: { key: string; label: string; items: Daily[] }[] = [];
  for (const report of reports) {
    const key = issueMonthKey(report.data.pubDate);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.items.push(report);
    } else {
      groups.push({ key, label: formatIssueMonth(report.data.pubDate), items: [report] });
    }
  }
  return groups;
}

/** 日报详情页路径。id 即文件名（不含扩展名）。 */
export function dailyPath(post: Daily): string {
  return `/daily/${post.id}/`;
}

export { formatDate } from './posts';
