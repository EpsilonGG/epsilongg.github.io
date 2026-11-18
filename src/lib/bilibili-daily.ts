import fs from 'node:fs';
import path from 'node:path';

/**
 * 日报「B站动态」栏的取数层（只读，站点层专用）。
 *
 * 2026-11-12 用户裁决：B 站账号抓到的**全部**动态都要在 Galgame 日报里呈现，
 * 且与「游戏制造商」「信息号」平行，单开一个「B站动态」栏目按钮。
 * 原始条目不进 `data/daily/<期号>/report.json`（那是受保护的 LLM 正本），
 * 也不进 Ci-en / .txt / .json 出口——这里直接从 B 站正本 JSONL 读，
 * 只在日报详情页的「详细」段渲染。LLM 会把其中一部分写成 `people[]` 的
 * 一句话概括（`handle=bili_<uid>` + `sources=[bilibili:<id>]`），那是正本
 * 自身的内容，跟这条原始条目旁路不是一回事。
 *
 * 2026-11-12 追加口径（同日用户裁决）：**同一个账号的归到一起**，合并后的
 * 正文超过 100 字就概括。所以取数层分三段：
 *   ① `parseBilibiliJsonl()` 逐条解析（宽容、去重、按时间升序）；
 *   ② `groupBilibiliRows()` 按账号（`bili_<uid>`）归并；
 *   ③ `summarizeBilibili()` 决定这一组是原样拼接还是压成 ≤100 字的概括。
 *
 * 2026-11-15 再加一段（用户裁决）：`people[]` 的概括行与第 ② 步的原文行会撞成
 * 「同一账号两行」，所以 ④ `mergeBilibiliDisplay()` 在展示前按账号去重——
 * 有概括的只留概括行、原文链接挂到行尾，没概括的才留正本行。全部动态的
 * 出处仍一条不少，只是不再把同一条消息说两遍。
 *
 * 2026-11-18 更新（用户裁决）：单个账号的条目**一律限 100 字以内**——
 * 上限从 150 收到 100；同账号多条仍归并成一条概括，每条原文链接照旧编号挂末尾。
 *
 * 为什么另起一个模块而不是改 `lib/daily.ts`：后者在日报保护集里
 * （`tests/test_daily_protection.py`），改它要登记授权豁免。取数层是纯函数 +
 * Node 内置模块，既能给 Astro 用，也能被 `node --test` 直接测。
 */

/** 与 `daily-bilibili-galgame.json:category.id` 一致；按钮文字在版式层另定。 */
export const BILIBILI_CATEGORY = 'bili_gal';

/** 读者看到的栏目名。名单里的标签是「B站Gal」（给周报/标签用），日报这里用「B站动态」。 */
export const BILIBILI_LABEL = 'B站动态';

/**
 * 单账号正文合并后超过这个字数就概括（用户口径：100 字，2026-11-18 从 150 收紧）。
 * 「字数」按**非空白码点**算：中文一字一个，空格/换行不占额度，
 * 这样同一段话在 `.jsonl` 里有没有换行都不会让阈值忽高忽低。
 */
export const BILIBILI_SUMMARY_LIMIT = 100;

/** 概括时每个账号至少要拿到的额度：账号再多也别把一句话切成半截。 */
const MIN_CLAUSE_QUOTA = 40;

/** 相似句合并的阈值（字符 3-gram 的 Jaccard 系数）。 */
const SIMILARITY = 0.7;
/** 包含度阈值：短句的 3-gram 有八成被长句包住，就当成同一句模板的重复。 */
const CONTAINMENT = 0.8;

const URL_RE = /https?:\/\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+/gi;
/** 话题标签整段是噪音（`#HIKARIFIELD# #GALGAME#`），正文里没有它的位置。 */
const TAG_RE = /#[^\s#]{1,30}#/g;
/** 作品名：`《》` 是作品 / 乐曲，`『』` 是本站统一的游戏名写法。 */
const TITLE_RE = /《[^》]{1,60}》|『[^』]{1,60}』/g;
/**
 * 零宽字符（B 站正文偶尔带 U+200B 开头），会让「字数」和显示都发毛。
 */
const ZERO_WIDTH_RE = /[\u200b-\u200f\ufeff]/g;
/**
 * 断句用的句末标点，以及断句时要跳过的成对符号。
 *
 * 不能在书名号里面断：`《淑女同萌！-Superior Entelecheia-》` 名字自带「！」，
 * 正则一断就成了「《淑女同萌！」这种半截书名号，后面的骨架归并全跟着错。
 */
const SENTENCE_END = '。！？!?；;\n';
const BRACKETS: Record<string, string> = {
  '《': '》', '『': '』', '【': '】', '〖': '〗', '［': '］', '「': '」',
};

export interface BilibiliRow {
  /** `bilibili:<动态 id>`，同一条动态只收一次。 */
  key: string;
  /** 名单里的合成 handle：`bili_<uid>`。 */
  handle: string;
  /** B 站动态正文原文（未清理，保留换行，便于查证与测试）。 */
  text: string;
  /** 动态原文链接（opus）。 */
  url: string;
  /** 发布者昵称，仅作兜底显示用；正式显示名走名单。 */
  publisher: string;
  publishedAt: string;
}

/** 一个账号在这一天的全部动态，压成一行。 */
export interface BilibiliGroup {
  handle: string;
  publisher: string;
  /** 展示用正文：≤100 字原样拼接，>100 字是概括。 */
  text: string;
  /** 这一行是不是概括出来的（页面上要标「概括」）。 */
  summarized: boolean;
  /** 归并了几条动态。 */
  count: number;
  /** 组内每条动态的原文链接，按时间升序（页面上编号列出，一条都不丢）。 */
  urls: string[];
  keys: string[];
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
 * 一条动态正文 → 单行纯文本：剥零宽字符、裸 URL、话题标签，换行压成空格。
 *
 * 剥 URL 是因为 B 站正文里贴的是裸链接（`https://store.hikarifield.co.jp/...`），
 * 页面上既点不动又占字数；每条动态都另给「原文」出口，信息不丢。
 */
export function cleanBilibiliText(text: string): string {
  return String(text ?? '')
    .replace(ZERO_WIDTH_RE, '')
    .replace(URL_RE, '')
    .replace(TAG_RE, '')
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+/g, ' ').trim())
    .filter((line) => line.length > 0)
    .join(' ');
}

/** 字数：去掉空白后的码点数（中文一字一个，emoji 也按码点算）。 */
export function charCount(text: string): number {
  return Array.from(String(text ?? '').replace(/\s+/g, '')).length;
}

function clip(text: string, limit: number): string {
  const chars = Array.from(text);
  if (chars.length <= limit) return text;
  const cut = chars.slice(0, Math.max(0, limit)).join('');
  // 尽量切在句末，别留「…首发折」这种半句。
  for (const mark of ['。', '！', '？', '!', '?', '；', ';']) {
    const index = cut.lastIndexOf(mark);
    if (index >= Math.floor(limit * 0.6)) return cut.slice(0, index + 1);
  }
  return cut;
}

/**
 * 按句末标点断句，**但不进书名号 / 方头括号里断**（理由见 `BRACKETS`）。
 * 未闭合的括号会让后面的内容并成一句，这是可接受的降级（概括照样截断）。
 */
function splitSentences(text: string): string[] {
  const out: string[] = [];
  let buffer = '';
  let closer = '';
  for (const char of Array.from(String(text ?? ''))) {
    if (closer) {
      buffer += char;
      if (char === closer) closer = '';
      continue;
    }
    if (BRACKETS[char]) {
      closer = BRACKETS[char];
      buffer += char;
      continue;
    }
    buffer += char;
    if (SENTENCE_END.includes(char)) {
      const piece = buffer.trim();
      if (piece) out.push(piece);
      buffer = '';
    }
  }
  const tail = buffer.trim();
  if (tail) out.push(tail);
  return out;
}

/** 去掉作品名后的「骨架」：六条不同作品的同款促销语，骨架是一模一样的。 */
function skeletonOf(text: string): string {
  return text
    .replace(TITLE_RE, '')
    .replace(/\s+/g, ' ')
    .replace(/^[\s，,、]+|[\s，,、]+$/g, '')
    .trim();
}

function trigrams(text: string): Set<string> {
  const chars = Array.from(text.replace(/\s+/g, ''));
  const out = new Set<string>();
  for (let i = 0; i + 3 <= chars.length; i += 1) out.add(chars.slice(i, i + 3).join(''));
  return out;
}

/**
 * 骨架是不是「同一句模板」：要么整体相近，要么短的整段被长的包住。
 *
 * 只用 Jaccard 会漏掉「同款模板 + 多一句补充」的情况（`体验版公开中！`
 * 对 `体验版公开中！▼下载请点这里…`），加一条包含度判据才盖得住。
 */
function similar(a: string, b: string): boolean {
  if (!a || !b) return false;
  if (a === b) return true;
  const left = trigrams(a);
  const right = trigrams(b);
  if (left.size === 0 || right.size === 0) return false;
  let shared = 0;
  for (const gram of left) if (right.has(gram)) shared += 1;
  return (
    shared / (left.size + right.size - shared) >= SIMILARITY
    || shared / Math.min(left.size, right.size) >= CONTAINMENT
  );
}

/**
 * 同账号的若干条动态 → 一行展示正文。
 *
 * 规则（可复现，不调模型）：
 * 1. 合计 ≤ limit 就原样拼接，一个字都不改——只剥 URL / 话题标签 / 零宽字符；
 * 2. 超了就按条数分额度，每条先取整句（不足额度就顺延下一句）；
 * 3. **首句骨架**相同或高度相似的条目并成一条，作品名收进末尾括号
 *    （`官方中文版现正于官网商城促销热卖中！（《A》、《B》）`），
 *    六条同款促销才不会被写成六行重复；
 * 4. 仍然超长就从尾部丢整句，末尾留一个省略号，绝不把句子切成半截。
 */
export function summarizeBilibili(
  parts: string[],
  limit: number = BILIBILI_SUMMARY_LIMIT,
): { text: string; summarized: boolean } {
  const cleaned = (parts ?? []).map(cleanBilibiliText).filter(Boolean);
  if (cleaned.length === 0) return { text: '', summarized: false };

  const full = cleaned.join(' ');
  if (charCount(full) <= limit) return { text: full, summarized: false };

  const quota = Math.max(MIN_CLAUSE_QUOTA, Math.floor(limit / cleaned.length));
  const merged: {
    text: string;
    key: string;
    titles: string[];
    count: number;
  }[] = [];
  for (const part of cleaned) {
    const sentences = splitSentences(part);
    if (sentences.length === 0) continue;
    let clause = '';
    for (const sentence of sentences) {
      clause = clause ? clause + sentence : sentence;
      if (charCount(clause) >= quota) break;
    }
    // 归并判据只看**首句骨架**：促销贴的第二句常常是价格 / 链接说明，
    // 带上它会把「同一句模板」拆成好几桶。作品名也只取首句里的——
    // 正文后半段提到的《游魂》《生命的备件》是代表作，不是这次宣传的作品。
    const lead = sentences[0];
    const key = skeletonOf(lead);
    const titles = [...new Set(lead.match(TITLE_RE) ?? [])];
    const hit = merged.find((item) => similar(item.key, key));
    if (hit) {
      hit.count += 1;
      for (const title of titles) if (!hit.titles.includes(title)) hit.titles.push(title);
    } else {
      merged.push({ text: clause, key, titles, count: 1 });
    }
  }

  const clauses = merged.map((item) => {
    if (item.count === 1) return item.text;
    // 并起来的那条保留首句原文（信息最全），只在后面补「另：其余作品名」；
    // 已经出现在正文里的作品名不重复列。条数由行尾注脚统一交代，
    // 不再往句子中间塞「（共 10 条）」——那会把一句读成两截。
    const extra = item.titles.filter((title) => !item.text.includes(title));
    return extra.length > 0 ? `${item.text}（另：${extra.join('、')}）` : item.text;
  });

  const joined = clauses.join('；');
  if (charCount(joined) <= limit) return { text: joined, summarized: true };

  // 留一个字给省略号，保证概括出来的整行不超过 limit。
  let kept = '';
  for (const clause of clauses) {
    const candidate = kept ? `${kept}；${clause}` : clause;
    if (charCount(candidate) > limit - 1) break;
    kept = candidate;
  }
  if (!kept) kept = clip(clauses[0] ?? '', limit - 1);
  return { text: `${kept}…`, summarized: true };
}

/**
 * 逐条动态 → 按账号归并的展示行（用户口径：同个账号的归到一起）。
 *
 * 顺序按每组第一条的时间走（`rows` 已经升序），所以「今天先说话的号」在上面，
 * 不随抓取顺序漂移。清理后正文为空的组直接丢掉，不摆空行。
 */
export function groupBilibiliRows(
  rows: BilibiliRow[],
  limit: number = BILIBILI_SUMMARY_LIMIT,
): BilibiliGroup[] {
  const order: string[] = [];
  const buckets = new Map<string, BilibiliRow[]>();
  for (const row of rows ?? []) {
    const key = row.handle || row.publisher || row.key;
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.push(row);
    } else {
      buckets.set(key, [row]);
      order.push(key);
    }
  }

  const groups: BilibiliGroup[] = [];
  for (const key of order) {
    const bucket = buckets.get(key) ?? [];
    const { text, summarized } = summarizeBilibili(bucket.map((row) => row.text), limit);
    if (!text) continue;
    groups.push({
      handle: bucket[0].handle,
      publisher: bucket[0].publisher,
      text,
      summarized,
      count: bucket.length,
      urls: bucket.map((row) => row.url),
      keys: bucket.map((row) => row.key),
      publishedAt: bucket[0].publishedAt,
    });
  }
  return groups;
}

/** `people[]` 里的一行；版式层传进来的对象字段更多也不影响这里。 */
export interface BilibiliSummaryPerson {
  handle: string;
  summary: string;
}

export interface BilibiliMerge {
  /** 每个 B 站账号的原文链接（含已被 LLM 概括的账号，概括行末尾要挂）。 */
  linksByHandle: Map<string, string[]>;
  /** 没有 LLM 概括、仍需单独展示正本正文的账号。 */
  remainingGroups: BilibiliGroup[];
  /** 「B站动态」栏最终行数 = 去重后的账号数（一个账号恰好一行）。 */
  accountCount: number;
}

/**
 * 「详细」栏 B 站动态的最终行集合（2026-11-15 用户口径）。
 *
 * 背景：B 站动态既会被 LLM 写进 `people[]` 的一句话概括，又会由
 * `groupBilibiliRows()` 从正本归并出一行原文 / 规则概括。两处都渲染时，
 * 同一个账号在「B站动态」按钮下会出现**两行**——先一句概括，后面又跟一大段
 * 原文，读起来像把同一条消息说了两遍。
 *
 * 口径：**有概括就不再放原文，一个账号只留一行**；原文链接仍挂到概括行末尾，
 * 一条都不丢。没有概括的账号照旧展示归并后的正文（≤100 字原样拼接，或规则概括），
 * 仍是一行一个账号。
 *
 * 匹配按 handle 小写：`people[]` 与正本里的 `bili_<uid>` 本该逐字一致，
 * 但大小写漂移不该让去重失效。`isBilibili` 由版式层传 `categoryOf()` 的结果，
 * 默认按名单铁律 `bili_<uid>` 兜底，这样纯函数不依赖名单模块也能单测。
 */
export function mergeBilibiliDisplay(
  people: BilibiliSummaryPerson[],
  groups: BilibiliGroup[],
  isBilibili: (handle: string) => boolean = (handle) => /^bili_\d+$/.test(handle),
): BilibiliMerge {
  const linksByHandle = new Map<string, string[]>();
  for (const group of groups ?? []) {
    linksByHandle.set(group.handle.toLowerCase(), group.urls ?? []);
  }

  const summarized = new Set<string>();
  for (const person of people ?? []) {
    const key = person.handle.toLowerCase();
    if (String(person.summary ?? '').trim() && linksByHandle.has(key)) {
      summarized.add(key);
    }
  }

  const remainingGroups = (groups ?? []).filter(
    (group) => !summarized.has(group.handle.toLowerCase()),
  );

  // `people[]` 里可能还有一个没抓到正本的 B 站号（老期号 / 断抓），它也占一行。
  const accounts = new Set<string>(linksByHandle.keys());
  for (const person of people ?? []) {
    if (isBilibili(person.handle)) accounts.add(person.handle.toLowerCase());
  }

  return { linksByHandle, remainingGroups, accountCount: accounts.size };
}

/** 原文链接组：概括行与正本行共用一套排版，免得两处各写一份慢慢漂。 */
export function bilibiliLinksHtml(urls: string[]): string {
  const escapes: Record<string, string> = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  };
  const escape = (value: string) =>
    String(value).replace(/[&<>"']/g, (char) => escapes[char] ?? char);
  return (urls ?? []).map((url, index) => {
    const label = (urls?.length ?? 0) > 1 ? `原文${index + 1} ↗` : '原文 ↗';
    return `<a class="daily-roster__bili-link" href="${escape(url)}" `
      + `target="_blank" rel="noopener noreferrer">${label}</a>`;
  }).join('');
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

/** 某一期覆盖日的 B 站动态（逐条）。没有当天正本就返回空数组。 */
export function loadBilibiliDynamics(covered: Date): BilibiliRow[] {
  const file = path.join(
    process.cwd(), 'data', 'bilibili', 'galgame', `${coveredDay(covered)}.jsonl`,
  );
  if (!fs.existsSync(file)) return [];
  return parseBilibiliJsonl(fs.readFileSync(file, 'utf-8'));
}

/** 某一期覆盖日的 B 站动态，已按账号归并、超过 100 字的已概括。 */
export function loadBilibiliGroups(
  covered: Date,
  limit: number = BILIBILI_SUMMARY_LIMIT,
): BilibiliGroup[] {
  return groupBilibiliRows(loadBilibiliDynamics(covered), limit);
}
