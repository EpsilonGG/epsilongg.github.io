/**
 * Ci-en 貼り付け用のテキスト（**中国語版 → 日本語版**の二本立て）。
 *
 * Ci-en の記事エディタは Markdown に近いが、**完全な Markdown ではない**。
 * 実際に通るのは次の 4 つだけ（本人の既存記事から確認済み）:
 *
 * - 見出し: `#` / `##`
 * - リンク: `[テキスト](URL)`（ラベル内の `**` は太字になる）
 * - 文字サイズ: `<span style="font-size: 150%">…</span>`
 * - 商品カード: `<product id='RJ…' />`（今回は使わない）
 *
 * 逆に **`-` の箇条書きは使わない**——Ci-en でどう化けるか確かめていない以上、
 * 貼った瞬間に崩れる可能性を残さない。箇条書きは `・` で書く。
 * `**` も**人名リンクのラベルの中だけ**に限る（本文の強調には使わない）。
 *
 * このモジュールは Astro にも JSON にも依存しない（名前解決は呼び出し側から
 * 関数で受け取る）。だから `node --test` でそのまま検証できる。
 *
 * 「誰を載せるか」もここでは決めない。呼び出し側（`lib/daily.ts`）が
 * **声優欄だけに絞った名簿**を渡す。絞り込みの判断は名簿側の仕事。
 */

/** 中国語版の 1 行（順序と「誰が載るか」の正本）。 */
export interface CienPerson {
  handle: string;
  via?: string[];
}

/** 一期の元情報。中国語版と日本語版で共有する。 */
export interface CienIssue {
  id: string;
  /** 発行時刻。時刻表示と出典の日付はここから作る（データに持たせない）。 */
  publishedAt: Date;
  /** 集計窓（ISO）。無ければ出典の時刻は書かない。 */
  windowStart?: string;
  /** 集計窓の終端（ISO）。 */
  windowEnd?: string;
  /** 本文に並べる人。**すでに欄で絞り込み済み**の前提で、この順に出す。 */
  people: CienPerson[];
}

/**
 * 一言語ぶんの本文。中国語版も日本語版も同じ形で渡す。
 *
 * `people` に無い人は出力から落ちるだけ。順序と人数は `CienIssue.people` が正本で、
 * ここに余分な handle（書き間違い）が混ざっても出さない。
 */
export interface CienBody {
  description?: string;
  highlights?: string[];
  works?: string;
  people?: { handle: string; summary: string }[];
}

export interface CienOptions {
  /** handle → 表示名（名簿から引く）。 */
  nameOf: (handle: string) => string;
  /** `@handle` をリンクにしてよい相手。この期に出てきた号だけ。 */
  handles?: Iterable<string>;
}

type Lang = 'zh' | 'ja';

/** 節の見出し。中国語版の「今日看点 / 作品动态 / 详细 / 出处」に対応。 */
const HEADINGS: Record<Lang, { highlights: string; works: string; people: string; source: string }> = {
  zh: { highlights: '今日看点', works: '作品动态', people: '详细', source: '出处' },
  ja: { highlights: '今日の注目', works: '作品動向', people: '詳細', source: '出典' },
};

/** `via` に別名義があるときの前置き。 */
const VIA_LABEL: Record<Lang, string> = { zh: '另有', ja: 'ほかに' };

const jaIssueFormat = new Intl.DateTimeFormat('ja-JP', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const jaDayFormat = new Intl.DateTimeFormat('ja-JP', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
});

const jaTimeFormat = new Intl.DateTimeFormat('ja-JP', {
  timeZone: 'Asia/Tokyo',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const zhIssueFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const zhDayFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const zhTimeFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Tokyo',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

/** `2026年10月27日 22:00`（JST） */
export function formatCienTime(date: Date): string {
  return jaIssueFormat.format(date);
}

/** 中国語版の時刻表示 `2026-10-27 22:00`（JST）。 */
export function formatCienTimeZh(date: Date): string {
  return zhIssueFormat.format(date).replace(/\//g, '-');
}

/**
 * 集計窓を `2026年10月27日 00:00〜24:00` の形にする。
 *
 * 終端が翌日の 00:00 のときは `24:00` と書く——`00:00〜00:00` は
 * 同じ瞬間を指しているように読めてしまう。
 */
function windowLabel(lang: Lang, start?: string, end?: string): string {
  if (!start) return '';
  const from = new Date(start);
  if (Number.isNaN(from.getTime())) return '';

  const dayFormat = lang === 'ja' ? jaDayFormat : zhDayFormat;
  const timeFormat = lang === 'ja' ? jaTimeFormat : zhTimeFormat;
  const tidy = (text: string) => (lang === 'ja' ? text : text.replace(/\//g, '-'));

  const day = tidy(dayFormat.format(from));
  const fromTime = timeFormat.format(from);

  if (!end) return `${day} ${fromTime}〜`;
  const to = new Date(end);
  if (Number.isNaN(to.getTime())) return `${day} ${fromTime}〜`;

  const toTime = timeFormat.format(to);
  const midnight = toTime === '00:00' && dayFormat.format(to) !== dayFormat.format(from);
  return `${day} ${fromTime}〜${midnight ? '24:00' : toTime}`;
}

/** 本文中の `@handle` を Ci-en のリンク記法にする。 */
function linkMentions(text: string, canonical: Map<string, string>): string {
  return text.replace(/@([A-Za-z0-9_]+)/g, (whole, handle: string) => {
    const name = canonical.get(handle.toLowerCase());
    if (!name) return whole;
    return `[@${name}](https://x.com/${name})`;
  });
}

/**
 * 人名の行。ラベルだけ太字にする——Ci-en では `**` がリンク内でだけ効くので、
 * 本文の強調に使うと原物のアスタリスクが出る。
 */
function personLine(
  handle: string,
  label: string,
  body: string,
  via: string[] | undefined,
  lang: Lang,
  canonical: Map<string, string>
): string {
  const extra =
    via && via.length > 0
      ? `（${VIA_LABEL[lang]} ${via.map((item) => `[@${item}](https://x.com/${item})`).join('、')}）`
      : '';
  return `・[**${label}**](https://x.com/${handle})：${linkMentions(body, canonical)}${extra}`;
}

/** 一言語ぶんの本文を組み立てる。 */
function renderBody(
  lang: Lang,
  body: CienBody,
  issue: CienIssue,
  options: CienOptions,
  canonical: Map<string, string>
): string {
  const headings = HEADINGS[lang];
  const blocks: string[] = [];

  // 時刻は `#` ではなく span。`#` は言語の見出しに使ってしまったので、
  // ここで大きくすると見出しが二段になって読みにくい。
  const time = lang === 'ja' ? formatCienTime(issue.publishedAt) : `${formatCienTimeZh(issue.publishedAt)}（日本时间）`;
  blocks.push(`<span style="font-size: 150%">${time}</span>`);

  if (body.description?.trim()) blocks.push(body.description.trim());

  const section = (heading: string, lines: string[]) => {
    if (lines.length === 0) return;
    blocks.push(`## ${heading}\n${lines.join('\n')}`);
  };

  section(
    headings.highlights,
    (body.highlights ?? []).map((text) => `・${linkMentions(text, canonical)}`)
  );
  section(headings.works, body.works?.trim() ? [body.works.trim()] : []);

  const summaries = new Map((body.people ?? []).map((person) => [person.handle, person.summary]));
  const roster = issue.people
    .map((person) => {
      const summary = summaries.get(person.handle);
      if (!summary?.trim()) return null;
      return personLine(
        person.handle,
        options.nameOf(person.handle),
        summary.trim(),
        person.via,
        lang,
        canonical
      );
    })
    .filter((line): line is string => line !== null);
  section(headings.people, roster);

  const window = windowLabel(lang, issue.windowStart, issue.windowEnd);
  blocks.push(
    lang === 'ja'
      ? `## ${headings.source}\nX の各アカウントのポスト${window ? `（${window} JST）` : ''}をもとにまとめました。`
      : `## ${headings.source}\n据 X 各账号的帖子整理${window ? `（${window} JST）` : ''}。`
  );

  return blocks.join('\n\n');
}

/**
 * Ci-en 用の本文を組み立てる。**中国語版 → 日本語版**の順に、それぞれ `#` で見出しを付ける。
 *
 * どちらの言語も `CienIssue.people` の順に並べ、片方に訳が無い人は落とす
 * （＝中国語版に無い人は出さない、日本語版に無い人も出さない）。
 * 格式変換だけを行い、要約はやり直さない。
 */
export function cienText(
  issue: CienIssue,
  zh: CienBody,
  ja: CienBody,
  options: CienOptions
): string {
  const canonical = new Map<string, string>();
  for (const handle of options.handles ?? []) {
    canonical.set(handle.toLowerCase(), handle);
  }

  return (
    [
      '# 中文版',
      renderBody('zh', zh, issue, options, canonical),
      '# 日本語版',
      renderBody('ja', ja, issue, options, canonical),
    ].join('\n\n') + '\n'
  );
}
