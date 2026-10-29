import { getCollection, type CollectionEntry } from 'astro:content';

import { profile } from '../config/profile';
import { cienText } from './cien';
import { categoryOf, nameOf } from './roster';

type DailyEntry = CollectionEntry<'dailyReports'>;

/** 日报的两种版本。2026-10-29 起一天出两份，期号带 `-g` 的是 Galgame 版。 */
export type DailyKind = 'voice' | 'galgame';

/** 版 → 页面上的名字。标题、归档、按钮都用这一份。 */
export const KIND_LABEL: Record<DailyKind, string> = {
  voice: '声优',
  galgame: 'Galgame',
};

/**
 * 日报条目。
 *
 * M4 起数据源是 `data/daily/<期号>/report.json`（见 `content.config.ts`）。
 * `title` / `pubDate` / `covered` / `kind` / `seq` 仍然是**派生**的，不写在数据里：
 * 期号说明「这是哪一天、哪一版」，`issue.published_at` 说明「什么时候发的」，
 * 标题就是把这两件事拼起来。少一个字段，就少一处能和 URL 对不上的地方。
 */
export type Daily = Omit<DailyEntry, 'data'> & {
  data: DailyEntry['data'] & {
    title: string;
    /** 真实发布时间（`issue.published_at`），RSS 与页面「发布于」用它。 */
    pubDate: Date;
    /** 期号覆盖的那一天（JST 零点）。归档分组、标题、Ci-en 标题用它。 */
    covered: Date;
    /** 这一期是哪一版：`voice`（声优 + 音声社团）/ `galgame`（制造商 + 信息号）。 */
    kind: DailyKind;
    /** 同一天同一版里的第几期。第 1 期是 1，`261027-2` 是 2。 */
    seq: number;
  };
};

/** 渲染层真正用到的数据形状（`.txt` 出口也用它）。 */
export type DailyData = Daily['data'];

/**
 * 日报编号：`YYMMDD`（日本时间），类型后缀与期序号。
 *
 *   261029      声优版
 *   261029-g    Galgame 版
 *   261029-2    同一天的第二期声优版
 *   261029-g2   同一天的第二个 Galgame 版
 *
 * **不带后缀的永远是声优版**：10-29 之前的所有期号都是声优版，旧档不用迁移。
 *
 * **不带小时是刻意的**：一天的数据要到 JST 24:00 才闭合（抓取 CI 每天 15:00 UTC
 * 跑最后一次），真实出稿必然在次日凌晨。小时写进期号只有两种结果——写真实时间，
 * 期号比内容晚一天；钉个假时间，页面上的「发布于」就是错的（旧格式的 22:00 正是如此）。
 * 期号只说「哪一天、哪一版」，发布时间交给 `issue.published_at`。
 */
export const DAILY_ID_PATTERN = /^(\d{2})(\d{2})(\d{2})(?:-(g?)(\d*))?$/;

/** JST 相对 UTC 的偏移（分钟）。固定值，不依赖运行环境时区。 */
const JST_OFFSET_MINUTES = 9 * 60;

/**
 * 把期号解析成「覆盖的那一天」「哪一版」「第几期」。
 * 格式不合法或日期不存在（如 2 月 30 日）返回 null。
 */
export function parseDailyId(id: string): { day: Date; kind: DailyKind; seq: number } | null {
  const match = DAILY_ID_PATTERN.exec(id);
  if (!match) return null;

  const year = 2000 + Number(match[1]);
  const month = Number(match[2]);
  const dayOfMonth = Number(match[3]);
  const kindChar = match[4];
  const digits = match[5] ?? '';

  let kind: DailyKind = 'voice';
  let seq = 1;
  if (kindChar === 'g') {
    kind = 'galgame';
    if (digits !== '') seq = Number(digits);
  } else if (kindChar === '') {
    // `-` 后面既没有 g 也没有数字：`261029-` 是写错了
    if (digits === '') return null;
    seq = Number(digits);
  }
  // 第 1 期不写后缀：`-1` / `-g1` 是写错，不是等价写法
  if (seq < 1 || (digits !== '' && seq < 2)) return null;
  if (month < 1 || month > 12 || dayOfMonth < 1 || dayOfMonth > 31) return null;

  const offset = JST_OFFSET_MINUTES * 60 * 1000;
  const date = new Date(Date.UTC(year, month - 1, dayOfMonth) - offset);

  // Date.UTC 会把 2 月 30 日进位成 3 月 2 日，回读一次才能确认真实存在
  const back = new Date(date.getTime() + offset);
  if (
    back.getUTCFullYear() !== year ||
    back.getUTCMonth() !== month - 1 ||
    back.getUTCDate() !== dayOfMonth
  ) {
    return null;
  }

  return { day: date, kind, seq };
}

/** 反向：把「覆盖的那一天 + 哪一版 + 第几期」写成期号。给测试和脚本对齐用。 */
export function toDailyId(day: Date, seq = 1, kind: DailyKind = 'voice'): string {
  const back = new Date(day.getTime() + JST_OFFSET_MINUTES * 60 * 1000);
  const pad = (value: number, width = 2) => String(value).padStart(width, '0');
  const base = pad(back.getUTCFullYear() % 100) + pad(back.getUTCMonth() + 1) + pad(back.getUTCDate());
  if (kind === 'galgame') return `${base}-g${seq > 1 ? seq : ''}`;
  return seq <= 1 ? base : `${base}-${seq}`;
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
    const parsed = parseDailyId(entry.id);
    if (!parsed) {
      throw new Error(
        `[daily] ${entry.id} 不是合法的期号（YYMMDD / YYMMDD-N / YYMMDD-g / YYMMDD-gN，JST）。` +
          '例：2026-10-29 的声优版是 261029，Galgame 版是 261029-g。'
      );
    }
    const suffix = parsed.seq > 1 ? `（第 ${parsed.seq} 期）` : '';
    return {
      ...entry,
      data: {
        ...entry.data,
        // 标题 = 日期 + 哪一版。几点发的写在「发布于」里——期号已经没有小时了
        title: `X 日报 · ${formatIssueDay(parsed.day)} ${KIND_LABEL[parsed.kind]}${suffix}`,
        pubDate: resolvePublishedAt(entry, parsed.day),
        covered: parsed.day,
        kind: parsed.kind,
        seq: parsed.seq,
      },
    };
  });

  // 归档顺序按「覆盖的那一天」，不按发布时间：补录旧日期时，旧的那期不该跳到最上面。
  // 同一天里声优版在前、Galgame 版在后，同一版按第几期倒序。
  return reports.sort(
    (a, b) =>
      b.data.covered.getTime() - a.data.covered.getTime() ||
      (a.data.kind === b.data.kind ? 0 : a.data.kind === 'voice' ? -1 : 1) ||
      b.data.seq - a.data.seq
  );
}

/**
 * 发布时间以 `issue.published_at` 为准，缺失或解析不出来时退回期号那一天。
 *
 * 期号现在只有日期，所以兜底值没有小时——它只用来排序和显示「发布于」，
 * 而「覆盖哪一天」是期号给的，不会因为这里兜底而漂移。
 */
function resolvePublishedAt(entry: DailyEntry, covered: Date): Date {
  const raw = entry.data.issue.published_at;
  if (raw) {
    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  return covered;
}

/** 按月份分组，保持倒序。归档列表用。 */
export function groupByMonth(reports: Daily[]): { key: string; label: string; items: Daily[] }[] {
  const groups: { key: string; label: string; items: Daily[] }[] = [];
  for (const report of reports) {
    const key = issueMonthKey(report.data.covered);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.items.push(report);
    } else {
      groups.push({ key, label: formatIssueMonth(report.data.covered), items: [report] });
    }
  }
  return groups;
}

/** 日报详情页路径。id 即目录名（`YYMMDD` 或 `YYMMDD-N`）。 */
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
  // 标题里已经有「哪一天」，不再单起一行写「覆盖 … 00:00–24:00（日本时间）」
  const lines: string[] = [data.title];

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
  if (data.kind !== 'voice') {
    // Ci-en 播报只有声优那一栏。Galgame 版（`-g`）没有对应出口——
    // 早失败好过贴一份「今天没有声优动静」的空播报。
    throw new Error(`[daily] ${report.id} 是 Galgame 版，Ci-en 出口只给声优版。`);
  }
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
      // Ci-en 标题的 `10/27` 是**覆盖的那一天**，不是发稿那一刻——发稿在次日凌晨
      day: data.covered,
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
      // 連絡先は `profile.json` ひとつが正本。`report.ja.json` には持たせない——
      // 每期让它写一遍，迟早出现一个打错的地址。
      contact: profile.email,
    },
  );
}

export { formatDate } from './posts';
