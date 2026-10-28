import { getCollection, type CollectionEntry } from 'astro:content';

import { cienText } from './cien';
import { categoryOf, nameOf } from './roster';

type DailyEntry = CollectionEntry<'dailyReports'>;

/**
 * 日报条目。
 *
 * M4 起数据源是 `data/daily/<期号>/report.json`（见 `content.config.ts`）。
 * `title` 与 `pubDate` 仍然是**派生**的，不写在数据里：
 * 一期日报的标题就是它的发布时间，没有别的信息量；发布时间就是期号。
 * 少一个字段，就少一处能和 URL 对不上的地方。
 */
export type Daily = Omit<DailyEntry, 'data'> & {
  data: DailyEntry['data'] & { title: string; pubDate: Date };
};

/** 渲染层真正用到的数据形状（`.txt` 出口也用它）。 */
export type DailyData = Daily['data'];

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
 *
 * 「已发布」= 在 `data/daily/` 里有一份 `report.json`。草稿留在工作区 `out/`，
 * 不搬过来就不上线——所以这里没有 `draft` 过滤，位置本身就是状态。
 */
export async function getDailyReports(): Promise<Daily[]> {
  const entries = await getCollection('dailyReports');

  // 空目录会安静地渲染出一个「暂无日报」的归档页，看起来像正常状态。
  // 但日报是每天自动发的，空了就是链路断了，必须让构建失败。
  if (entries.length === 0) {
    throw new Error(
      '[daily] data/daily 里没有任何 report.json。' +
        '日报由 `daily publish` 从 out/<期号>/ 搬过来；如果刚做完迁移，检查 glob 的 base 是否指对了。'
    );
  }

  const reports: Daily[] = entries.map((entry) => {
    const issuedAt = resolvePublishedAt(entry);
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

  // 同一小时内只可能有一期；用 id 兜底保证顺序稳定
  return reports.sort(
    (a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime() || b.id.localeCompare(a.id)
  );
}

/**
 * 发布时间以 `issue.published_at` 为准，缺失或解析不出来时退回期号。
 *
 * 两个来源都留着是因为它们本来就该一致：期号是 `published_at` 的紧凑写法。
 * 万一不一致，`published_at` 优先——它带着时区，能表达期号表达不了的东西；
 * 而期号必须永远能推回时间，否则这个期号本身就是错的。
 */
function resolvePublishedAt(entry: DailyEntry): Date {
  const raw = entry.data.issue.published_at;
  if (raw) {
    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  const fromId = parseDailyId(entry.id);
  if (fromId) return fromId;
  throw new Error(
    `[daily] ${entry.id} 的发布时间既没有合法的 issue.published_at，期号本身也不是 YYMMDDHH。` +
      '例：2026-10-31 22:00（JST）对应期号 26103122。'
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

/** 日报详情页路径。id 即目录名（八位期号）。 */
export function dailyPath(post: Daily): string {
  return `/daily/${post.id}/`;
}

/**
 * 纯文本出口 `/daily/<id>.txt` 的正文。
 *
 * 给两件事用：① 复制粘贴到别处；② M6 的视频稿——口播稿要从「读者已经看到的那段字」
 * 出发，而不是从另一份摘要出发，否则画面和文字会对不上。
 *
 * 所以这里**只做格式转换，不做二次概括**：段落顺序、句子、人名全部和页面一致。
 * 差别只有两个：人名后面带上 `@handle`（纯文本里没有链接，不留 handle 就找不回人），
 * 以及 `via` 写成「另有 @x」。
 */
export function plainText(report: Daily): string {
  const { data } = report;
  const lines: string[] = [data.title, `${formatIssueTime(data.pubDate)}（日本时间）`];

  if (data.description) {
    lines.push('', data.description);
  }

  const section = (heading: string, body: string[]) => {
    if (body.length === 0) return;
    lines.push('', heading, ...body);
  };

  section(
    '今日看点',
    data.highlights.map((claim) => claim.text)
  );
  section('作品动态', data.works ? [data.works] : []);
  section(
    '分类摘要',
    data.categories.filter((c) => c.summary).map((c) => `${c.label}：${c.summary}`)
  );
  section(
    '互动',
    data.interactions.map((claim) => claim.text)
  );
  section(
    '详细',
    data.people
      .filter((person) => person.summary.trim().length > 0)
      .map((person) => {
        const extra = person.via.length > 0 ? `（另有 ${person.via.map((v) => `@${v}`).join('、')}）` : '';
        return `${nameOf(person.handle)}（@${person.handle}）：${person.summary}${extra}`;
      })
  );
  section(
    '洞察',
    data.insights.map((claim) => claim.text)
  );

  return lines.join('\n') + '\n';
}

/** 日语版条目（`data/daily/<期号>/report.ja.json`，可选）。 */
export type DailyJa = CollectionEntry<'dailyJa'>;

/**
 * 读取所有日语版，按期号索引。
 *
 * 没有日语版的期号就不在 Map 里——页面上「没有按钮」和「翻译缺失」是同一件事，
 * 不需要另一个布尔字段来表达。
 */
export async function getDailyJapanese(): Promise<Map<string, DailyJa>> {
  const entries = await getCollection('dailyJa');
  return new Map(entries.map((entry) => [entry.id, entry]));
}

/**
 * 日语版出口 `/daily/<id>.ja.txt` 的正文：Ci-en へ貼り付けるためのもの。
 *
 * 中文版 `plainText()` と同じく、書いてあることを組み替えるだけで、
 * 新しく要約はしない。違いは ① 日本語であること ② Ci-en の記法に合わせること
 * ③ **中国語版を先に置いて、そのあとに日本語版を続ける**こと。
 *
 * 載せるのは**声优栏目**だけ。制造商 / 社团 那两栏是给站内看的，
 * 贴到 Ci-en 上只会把「今天谁有动静」这件事埋掉。判断在这里做，
 * `lib/cien.ts` 只管格式——它连名簿都不知道。
 */
export function cienReport(report: Daily, ja: DailyJa): string {
  const { data } = report;
  const people = data.people.filter((person) => categoryOf(person.handle) === 'seiyuu');

  // Ci-en 版に載せる看点。`highlight_indexes` で選ぶ——「厂商側だけの看点は落とす」
  // という判断は中身を見ないとできないので、言語をまたぐ自動判定にはしない。
  // 空なら全部載せる（＝選んでいない期は今までどおり）。
  const picks = ja.data.highlight_indexes;
  const highlights =
    picks.length > 0
      ? picks
          .map((index) => data.highlights[index]?.text)
          .filter((text): text is string => Boolean(text))
      : data.highlights.map((claim) => claim.text);

  return cienText(
    {
      id: report.id,
      publishedAt: data.pubDate,
      windowStart: data.issue.window.start,
      windowEnd: data.issue.window.end,
      hook: ja.data.hook,
      people: people.map((person) => ({ handle: person.handle, via: person.via })),
    },
    {
      description: ja.data.description_zh || data.description,
      highlights,
      works: data.works,
      people: people.map((person) => ({ handle: person.handle, summary: person.summary })),
    },
    ja.data,
    {
      nameOf,
      handles: [...data.accounts, ...data.people.flatMap((p) => [p.handle, ...p.via])],
    },
  );
}

export { formatDate } from './posts';
