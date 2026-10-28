/**
 * Ci-en 貼り付け用の日本語テキスト。
 *
 * Ci-en の記事エディタは Markdown に近いが、**完全な Markdown ではない**。
 * 実際に通るのは次の 4 つだけ（本人の既存記事から確認済み）:
 *
 * - 見出し: `#` / `##`
 * - リンク: `[テキスト](URL)`
 * - 文字サイズ: `<span style="font-size: 150%">…</span>`
 * - 商品カード: `<product id='RJ…' />`（今回は使わない）
 *
 * 逆に **`-` の箇条書きと `**強調**` は使わない**——Ci-en でどう化けるか確かめて
 * いない以上、貼った瞬間に崩れる可能性を残さない。箇条書きは `・` で書く。
 *
 * このモジュールは Astro にも JSON にも依存しない（名前解決は呼び出し側から
 * 関数で受け取る）。だから `node --test` でそのまま検証できる。
 */

/** 中国語版の 1 行（順序と「誰が載るか」の正本）。 */
export interface CienPerson {
  handle: string;
  via?: string[];
}

/** 中国語版の一期（日本語版と突き合わせるための最小限）。 */
export interface CienIssue {
  id: string;
  /** 発行時刻。タイトルと出典の日付はここから作る（データに持たせない）。 */
  publishedAt: Date;
  /** 集計窓（ISO）。無ければ出典の時刻は書かない。 */
  windowStart?: string;
  windowEnd?: string;
  people: CienPerson[];
}

/**
 * 日本語版の本文（`data/daily/<期号>/report.ja.json`）。
 *
 * 中国語版と**同じ順序・同じ人数**で書く。欠けている行は出力から落ちるだけで
 * エラーにならないので、ビルド時に `DailyLayout` が被覆率を警告する。
 */
export interface CienJapanese {
  description?: string;
  highlights?: string[];
  works?: string;
  interactions?: string[];
  people?: { handle: string; summary: string }[];
  insights?: string[];
}

export interface CienOptions {
  /** handle → 表示名（名单から引く）。 */
  nameOf: (handle: string) => string;
  /** `@handle` をリンクにしてよい相手。この期に出てきた号だけ。 */
  handles?: Iterable<string>;
}

/** 節の見出し。中国語版の「今日看点 / 作品动态 / 互动 / 详细 / 洞察」に対応。 */
const HEADINGS = {
  highlights: '今日の注目',
  works: '作品動向',
  interactions: 'やりとり',
  people: '詳細',
  insights: '所感',
} as const;

const issueFormat = new Intl.DateTimeFormat('ja-JP', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const dayFormat = new Intl.DateTimeFormat('ja-JP', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
});

const timeFormat = new Intl.DateTimeFormat('ja-JP', {
  timeZone: 'Asia/Tokyo',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

/** `2026年10月27日 22:00`（JST） */
export function formatCienTime(date: Date): string {
  return issueFormat.format(date);
}

/**
 * 集計窓を `2026年10月27日 00:00〜24:00` の形にする。
 *
 * 終端が翌日の 00:00 のときは `24:00` と書く——`00:00〜00:00` は
 * 同じ瞬間を指しているように読めてしまう。
 */
function windowLabel(start?: string, end?: string): string {
  if (!start) return '';
  const from = new Date(start);
  if (Number.isNaN(from.getTime())) return '';

  const day = dayFormat.format(from);
  const fromTime = timeFormat.format(from);

  if (!end) return `${day} ${fromTime}〜`;
  const to = new Date(end);
  if (Number.isNaN(to.getTime())) return `${day} ${fromTime}〜`;

  const toTime = timeFormat.format(to);
  const midnight = toTime === '00:00' && dayFormat.format(to) !== day;
  return `${day} ${fromTime}〜${midnight ? '24:00' : toTime}`;
}

/**
 * 本文中の `@handle` を Ci-en のリンク記法にする。
 *
 * 名单に無い handle はそのまま残す（リンク先が無いより、文字で残すほうがいい）。
 */
function linkMentions(text: string, canonical: Map<string, string>): string {
  return text.replace(/@([A-Za-z0-9_]+)/g, (whole, handle: string) => {
    const name = canonical.get(handle.toLowerCase());
    if (!name) return whole;
    return `[@${name}](https://x.com/${name})`;
  });
}

function profileLink(handle: string, label: string): string {
  return `[${label}](https://x.com/${handle})`;
}

/**
 * 日本語版の本文を組み立てる。
 *
 * 中国語版の `plainText()` と同じく**格式変換だけ**を行う。順序も人数も
 * 中国語版に従い、日本語側に無い行は落とす（＝中国語版に無い行は出さない）。
 */
export function cienText(issue: CienIssue, ja: CienJapanese, options: CienOptions): string {
  const canonical = new Map<string, string>();
  for (const handle of options.handles ?? []) {
    canonical.set(handle.toLowerCase(), handle);
  }

  const blocks: string[] = [];

  // 見出しは `#` ではなく span。Ci-en の記事タイトルと二重になるのを避けつつ、
  // 一等地だけ大きくする（本人の既存記事と同じ使い方）。
  blocks.push(`<span style="font-size: 150%">【X まとめ】${formatCienTime(issue.publishedAt)}</span>`);

  if (ja.description?.trim()) blocks.push(ja.description.trim());

  const section = (heading: string, lines: string[]) => {
    if (lines.length === 0) return;
    blocks.push(`## ${heading}\n${lines.join('\n')}`);
  };

  section(
    HEADINGS.highlights,
    (ja.highlights ?? []).map((text) => `・${linkMentions(text, canonical)}`)
  );
  section(HEADINGS.works, ja.works?.trim() ? [ja.works.trim()] : []);
  section(
    HEADINGS.interactions,
    (ja.interactions ?? []).map((text) => `・${linkMentions(text, canonical)}`)
  );

  // 「詳細」は中国語版の people 順に並べる。日本語側に無い人は落とし、
  // 中国語版に居ない handle は（書き間違いなので）出さない。
  const summaries = new Map((ja.people ?? []).map((person) => [person.handle, person.summary]));
  const roster = issue.people
    .map((person) => {
      const summary = summaries.get(person.handle);
      if (!summary?.trim()) return null;
      const extra =
        person.via && person.via.length > 0
          ? `（ほかに ${person.via.map((via) => profileLink(via, `@${via}`)).join('、')}）`
          : '';
      return `・${profileLink(person.handle, options.nameOf(person.handle))}：${linkMentions(
        summary.trim(),
        canonical
      )}${extra}`;
    })
    .filter((line): line is string => line !== null);
  section(HEADINGS.people, roster);

  section(
    HEADINGS.insights,
    (ja.insights ?? []).map((text) => `・${linkMentions(text, canonical)}`)
  );

  const window = windowLabel(issue.windowStart, issue.windowEnd);
  blocks.push(
    `## 出典\nX の各アカウントのポスト${window ? `（${window} JST）` : ''}をもとにまとめました。`
  );

  return blocks.join('\n\n') + '\n';
}
