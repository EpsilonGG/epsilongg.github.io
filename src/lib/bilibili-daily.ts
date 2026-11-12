import fs from 'node:fs';
import path from 'node:path';

/**
 * 日报「B站动态」栏的取数层（只读，站点层专用）。
 *
 * 2026-11-12 用户裁决：B 站账号抓到的**全部**动态都要在 Galgame 日报里呈现，
 * 且与「游戏制造商」「信息号」平行，单开一个「B站动态」栏目按钮。
 * B 站条目不进 `data/daily/<期号>/report.json`（那是受保护的 LLM 正本），
 * 也不进 Ti-Ci-en / .txt / .json 出口——这里直接从 B 站正本 JSONL 读，
 * 只在日报详情页的「详细」段渲染原始条目。
 *
 * 为什么另起一个模块而不是改 `lib/daily.ts`：后者在日报保护集里
 * （`tests/test_daily_protection.py`），改它要登记授权豁免。取数层是纯函数 +
 * Node 内置模块，既能给 Astro 用，也能被 `node --test` 直接测。
 */

/** 与 `daily-bilibili-galgame.json:category.id` 一致；按钮文字在版式层另定。 */
export const BILIBILI_CATEGORY = 'bili_gal';

/** 读者看到的栏目名。名单里的标签是「B站Gal」（给周报/标签用），日报这里用「B站动态」。 */
export const BILIBILI_LABEL = 'B站动态';

export interface BilibiliRow {
  /** `bilibili:<动态 id>`，同一条动态只收一次。 */
  key: string;
  /** 名单里的合成 handle：`bili_<uid>`。 */
  handle: string;
  /** B 站动态正文（保留换行，页面用 `white-space: pre-line` 原样呈现）。 */
  text: string;
  /** 动态原文链接（opus）。 */
  url: string;
  /** 发布者昵称，仅作兜底显示用；正式显示名走名单。 */
  publisher: string;
  publishedAt: string;
}

interface RawRow {
  identity_key?: unknown;
  item_id?: unknown;
  content?: unknown;
  publisher?: unknown;
  canonical_url?: unknown;
  published_at?: unknown;
  metadata?: { account?: unknown; uid?: unknown } | null;
}

const str = (value: unknown): string =>
  typeof value === 'string' ? value : value == null ? '' : String(value);

/** 解析 B 站正本 JSONL；坏行跳过、按 identity_key 去重、按发布时间升序。 */
export function parseBilibiliJsonl(raw: string): BilibiliRow[] {
  const seen = new Set<string>();
  const rows: BilibiliRow[] = [];
  for (const line of String(raw || '').split(/\r?\n/)) {
    if (!line.trim()) continue;
    let data: RawRow;
    try {
      data = JSON.parse(line) as RawRow;
    } catch {
      continue; // 抓取时偶有半行；宁可少一条也不让整页构建失败
    }
    const id = str(data.item_id);
    const key = str(data.identity_key) || (id ? `bilibili:${id}` : '');
    const text = str(data.content).trim();
    const url = str(data.canonical_url);
    if (!key || !text || !url || seen.has(key)) continue;
    seen.add(key);
    const uid = str(data.metadata?.uid);
    rows.push({
      key,
      handle: str(data.metadata?.account) || (uid ? `bili_${uid}` : ''),
      text,
      url,
      publisher: str(data.publisher),
      publishedAt: str(data.published_at),
    });
  }
  rows.sort((a, b) => a.publishedAt.localeCompare(b.publishedAt) || a.key.localeCompare(b.key));
  return rows;
}

/**
 * 期号覆盖的那一天（JST 零点的 UTC 瞬时）→ B 站正本文件名 `YYYY-MM-DD`。
 * `covered` 取自 `lib/daily.ts:parseDailyId`，本身就是 JST 零点，加回 9 小时
 * 再取 UTC 日期即可，不依赖构建机器的本地时区。
 */
export function coveredDay(covered: Date): string {
  const jst = new Date(covered.getTime() + 9 * 60 * 60 * 1000);
  return jst.toISOString().slice(0, 10);
}

/** 某一期覆盖日的 B 站动态。没有当天正本就返回空数组（老期号、断抓都正常）。 */
export function loadBilibiliDynamics(covered: Date): BilibiliRow[] {
  const file = path.join(
    process.cwd(), 'data', 'bilibili', 'galgame', `${coveredDay(covered)}.jsonl`,
  );
  if (!fs.existsSync(file)) return [];
  return parseBilibiliJsonl(fs.readFileSync(file, 'utf-8'));
}
