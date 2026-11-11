import galgameRoster from '../config/daily-roster-galgame.json';
import voiceRoster from '../config/daily-roster.json';
import bilibiliRoster from '../config/daily-bilibili-galgame.json';

/**
 * 名单的查询层。
 *
 * 2026-10-29 起名单拆成两份（声优版 / Galgame 版），这里**合并成一张查询表**：
 * 名字、栏目、显示顺序都只有一处来源，页面按 handle 查就行。
 *
 * 2026-11-11 用户裁决：B 站监控号与 X 名单**不写进同一个文件**。第三份
 * `daily-bilibili-galgame.json` 是 B 站正本，这里只做一次形状适配后并入查询表；
 * X 的两份名单里不再出现 `bili_*` / `bili_gal`。合并只影响查询，不影响分组。
 *
 * 为什么要合并而不是按版各读一份：历史期号（`261025`–`261028`）是合并名单时代的
 * 产物，`people` 里同时有声优和制造商。如果渲染时只读声优版，那些旧页面上的人名
 * 会全部退回裸 `@handle`。合并只影响**查询**，不影响分组——分组看的是当期实际
 * 出现的栏目（`DailyLayout` 的 `categoriesPresent`）。
 *
 * 名单里没有的 handle 不报错——**退回显示 `@handle`**，由调用方决定要不要告警。
 * 硬失败会让「名单漏了一个人」升级成「整站构建不出来」，不成比例。
 */

interface RosterAccount {
  handle: string;
  name?: string;
  role?: string;
  category?: string;
  /** 缺省 / "x" 是 X 账号；"bilibili" 等是别的抓取源 */
  source?: string;
  /** 非 X 账号的主页。没写就退回 `https://x.com/<handle>` */
  profile_url?: string;
}

interface RosterCategory {
  id: string;
  label: string;
}

interface RosterFile {
  categories?: RosterCategory[];
  accounts?: RosterAccount[];
}

/** B 站名单是独立文件，形状与 X 名单略有不同（`category` / `categories` / `source_id`）。 */
const bilibiliFile: RosterFile = {
  categories: (bilibiliRoster.categories ?? [bilibiliRoster.category]) as RosterCategory[],
  accounts: (bilibiliRoster.accounts as unknown as RosterAccount[]).map((account) => ({
    ...account,
    source: account.source ?? bilibiliRoster.source_id,
  })),
};

// 顺序即栏目按钮顺序：声优版 → Galgame 版 → B站Gal（非 X 源排最后，other 永远垫底）。
const FILES: RosterFile[] = [
  voiceRoster as RosterFile,
  galgameRoster as RosterFile,
  bilibiliFile,
];

const displayName = new Map<string, string>();
const order = new Map<string, number>();
const category = new Map<string, string>();
/** 非 X 数据源账号的主页（`bili_<uid>` → B 站空间）。X 账号不进这张表。 */
const profileUrl = new Map<string, string>();

const OTHER = 'other';

/**
 * 栏目（声优 / 音声社团 / 游戏制造商 / 信息号 / 未归类），顺序即按钮顺序。
 * 先按文件顺序收（声优版在前），`未归类` 永远排最后。
 */
const categoryList: RosterCategory[] = [];
for (const file of FILES) {
  for (const item of file.categories ?? []) {
    if (item.id === OTHER) continue;
    if (!categoryList.some((existing) => existing.id === item.id)) categoryList.push(item);
  }
}
categoryList.push({ id: OTHER, label: '未归类' });

const categoryLabel = new Map<string, string>(categoryList.map((item) => [item.id, item.label]));
const categoryRank = new Map<string, number>(categoryList.map((item, index) => [item.id, index]));

let index = 0;
for (const file of FILES) {
  for (const account of file.accounts ?? []) {
    const key = account.handle.toLowerCase();
    if (account.name) displayName.set(key, account.name);
    if (!order.has(key)) order.set(key, index++);
    category.set(key, account.category || OTHER);
    if (account.profile_url) profileUrl.set(key, account.profile_url);
  }
}

/**
 * 账号主页。名单里带 `profile_url` 的非 X 账号（B 站动态监控号）走它，
 * 其余一律 X 主页——老数据里没有 source 字段，不能因为新增字段改变历史链接。
 */
export function profileUrlOf(handle: string): string {
  return profileUrl.get(handle.toLowerCase()) ?? `https://x.com/${handle}`;
}

/** 名单里的显示名；不在名单（或该条没有 `name`）返回 null。 */
export function displayNameOf(handle: string): string | null {
  return displayName.get(handle.toLowerCase()) ?? null;
}

/** 显示名，查不到就退回 `@handle`。 */
export function nameOf(handle: string): string {
  return displayNameOf(handle) ?? `@${handle}`;
}

/** 名单顺序（越小越靠前）。不在名单的排在最后，保持稳定。 */
export function rosterIndex(handle: string): number {
  return order.get(handle.toLowerCase()) ?? Number.MAX_SAFE_INTEGER;
}

/**
 * 这个号属于哪个栏目。名单里没有就归 `other`——
 * 「名单漏了一个人」不该让整页崩掉，最多是它落在「未归类」里。
 */
export function categoryOf(handle: string): string {
  return category.get(handle.toLowerCase()) ?? OTHER;
}

/** 栏目的中文名（声优 / 音声社团 / 游戏制造商 / 信息号 / 未归类）。 */
export function categoryLabelOf(id: string): string {
  return categoryLabel.get(id) ?? id;
}

/** 栏目的显示顺序：声优 → 音声社团 → 游戏制造商 → 信息号 → 未归类。 */
export function categoryRankOf(id: string): number {
  return categoryRank.get(id) ?? Number.MAX_SAFE_INTEGER;
}
