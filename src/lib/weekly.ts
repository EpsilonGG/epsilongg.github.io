import fs from 'node:fs';
import path from 'node:path';

/**
 * Galgame 周报的数据层。
 *
 * 数据源是仓库根的 `data/weekly/<期号>/report.json`，由 `python -m weekly publish`
 * 从工作台产物脱敏后写出。**这里只读这一层，绝不读工作台目录（weekly 包下的
 * out/）**——那里面有
 * 选材证据、未定稿说明和筛选页，是本地工作台，不该上线。
 * `scripts/check_weekly_publish.py` 会把这条约束当闸门查。
 *
 * 不用 `astro:content` 是有意的：日报的内容集合定义在受保护的
 * `src/content.config.ts`，为周报去改那份文件要过日报保护集豁免；
 * 周报是「一份正本 → 多种出口」的扁平结构，直接读目录更简单。
 */

export interface WeeklyColumn {
  label: string;
  brands: number;
  items: number;
}

export interface WeeklyReport {
  schema_version: number;
  generator: string;
  issue: {
    id: string;
    title: string;
    published_at: string;
    window: { start: string; end: string };
    status: 'published';
    previous: string | null;
  };
  description: string;
  lead: string;
  columns: WeeklyColumn[];
  stats: {
    source_issues: number;
    brands: number;
    items: number;
    images: number;
    raw_records: number;
  };
  policy: {
    new_work_label_source: string;
    new_work_signal_groups: string[];
    new_work_manual_overrides: number;
    human_review: boolean;
    selection_mode: string;
    decisions_human_confirmed: number;
    disabled_display_columns: string[];
  };
  source_issues: string[];
  markdown: string;
  content_html: string;
}

/** 期号就是 `vol_XXX`，与日报的 `YYMMDD-g` 完全无关。 */
export const WEEKLY_ID_PATTERN = /^vol_\d{3,}$/;

/** `process.cwd()` 在 `npm run build` 时是仓库根（本机 scripts 也是这个口径）。 */
const DATA_DIR = path.join(process.cwd(), 'data', 'weekly');

const publishedFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

/** `2026/11/14 13:00` → `2026-11-14 13:00` */
function normalize(text: string): string {
  return text.replace(/\//g, '-');
}

/** 发布时间按 JST 显示（与日报同口径），RSS 里仍用原始 Date 排序。 */
export function formatWeeklyPublished(date: Date): string {
  return normalize(publishedFormat.format(date));
}

/** 读取全部已发布周报，按期号倒序（vol_002 在 vol_001 前面）。 */
export function getWeeklyReports(): WeeklyReport[] {
  if (!fs.existsSync(DATA_DIR)) return [];

  const reports: WeeklyReport[] = [];
  for (const entry of fs.readdirSync(DATA_DIR, { withFileTypes: true })) {
    if (!entry.isDirectory() || !WEEKLY_ID_PATTERN.test(entry.name)) continue;
    const file = path.join(DATA_DIR, entry.name, 'report.json');
    if (!fs.existsSync(file)) continue;
    const report = JSON.parse(fs.readFileSync(file, 'utf-8')) as WeeklyReport;
    if (report.issue?.id !== entry.name) {
      throw new Error(
        `[weekly] ${entry.name}/report.json 的 issue.id 是 ${report.issue?.id}，与目录名不一致。`,
      );
    }
    if (report.issue.status !== 'published') {
      throw new Error(`[weekly] ${entry.name} 不是已发布正本（status=${report.issue.status}）。`);
    }
    reports.push(report);
  }
  return reports.sort((a, b) => b.issue.id.localeCompare(a.issue.id));
}

export type WeeklyIssue = WeeklyReport['issue'];

export function weeklyPath(id: string): string {
  return `/weekly/${id}/`;
}

export function weeklyJsonPath(id: string): string {
  return `/weekly/${id}.json`;
}

export function publishedDate(report: WeeklyReport): Date {
  const parsed = new Date(report.issue.published_at);
  return Number.isNaN(parsed.getTime()) ? new Date(0) : parsed;
}
