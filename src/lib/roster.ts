import rosterData from '../config/daily-roster.json';

/**
 * 声优名单的查询层。
 *
 * 名字只存在一处（`src/config/daily-roster.json`）：同一个人有主号、小号、社团号，
 * 如果把名字也写进每一期日报，同一个人迟早会出现两种写法。所以 `report.json`
 * 里只有 handle，显示名在渲染时查这张表。
 *
 * 名单里没有的 handle 不报错——**退回显示 `@handle`**，由调用方决定要不要告警。
 * 硬失败会让「名单漏了一个人」升级成「整站构建不出来」，不成比例。
 */

interface RosterAccount {
  handle: string;
  name?: string;
  role?: string;
  category?: string;
}

interface RosterCategory {
  id: string;
  label: string;
}

const displayName = new Map<string, string>();
const order = new Map<string, number>();
const category = new Map<string, string>();

const OTHER = 'other';

/** 栏目（声优 / 社团 / 制造商 / 未归类），顺序即页面上的按钮顺序。 */
const categoryList: RosterCategory[] = (rosterData.categories as RosterCategory[] | undefined) ?? [];
const categoryLabel = new Map<string, string>(categoryList.map((item) => [item.id, item.label]));
const categoryRank = new Map<string, number>(categoryList.map((item, index) => [item.id, index]));

for (const [index, account] of (rosterData.accounts as RosterAccount[]).entries()) {
  const key = account.handle.toLowerCase();
  if (account.name) displayName.set(key, account.name);
  order.set(key, index);
  category.set(key, account.category || OTHER);
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

/** 栏目的中文名（声优 / 社团 / 制造商 / 未归类）。 */
export function categoryLabelOf(id: string): string {
  return categoryLabel.get(id) ?? id;
}

/** 栏目的显示顺序：声优 → 社团 → 制造商 → 未归类。 */
export function categoryRankOf(id: string): number {
  return categoryRank.get(id) ?? Number.MAX_SAFE_INTEGER;
}
