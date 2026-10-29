import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';
import { BLOG_TAGS, BLOG_TAG_HINT } from './config/tags';

/**
 * 文章集合。
 *
 * - 文件放在 src/content/blog/，每个文件一篇文章。
 * - 文件名（不含扩展名）就是 URL 中的 slug，因此修改标题不会改变既有链接。
 * - 构建时由 Zod 校验字段，字段缺失或类型错误会让构建失败并指出具体文件。
 */
const blog = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/blog' }),
  schema: z
    .object({
      title: z.string().trim().min(1, 'title 不能为空'),
      description: z.string().trim().min(1, 'description 不能是空字符串').optional(),
      pubDate: z.coerce.date(),
      updatedDate: z.coerce.date().optional(),
      tags: z.array(z.string().trim().min(1)).default([]),
      draft: z.boolean().default(false),
      /**
       * 内容来源 / 披露标记。
       * - `original`（默认）：本人原创，或转载/整理自其它网站但由人工完成。
       *   默认「笔记」列表（栏目名「原创与转载」）展示的就是这一类。
       * - `ai`：由 AI 参与整理/生成的文章。默认列表不包含，需要手动开启
       *   滑块后才会出现，单篇页面与列表项都会显示「AI 整理」标记作披露。
       */
      source: z.enum(['original', 'ai']).default('original'),
    })
    .superRefine((data, ctx) => {
      if (data.updatedDate && data.updatedDate.getTime() < data.pubDate.getTime()) {
        ctx.addIssue({
          code: 'custom',
          message: 'updatedDate 不能早于 pubDate',
          path: ['updatedDate'],
        });
      }

      /**
       * 标签是封闭集合（见 `src/config/tags.json`）：六个大格子之外一律不许新增。
       * 想加新标签，先改那份 JSON，而不是在文章里就地发明一个。
       */
      data.tags.forEach((tag, index) => {
        if (!BLOG_TAGS.includes(tag)) {
          ctx.addIssue({
            code: 'custom',
            message: `标签「${tag}」不在允许范围内。可用：${BLOG_TAG_HINT}。放不进去就写「其它」。`,
            path: ['tags', index],
          });
        }
      });
    }),
});

/**
 * 日报集合（M4 起读 JSON，不再读 Markdown）。
 *
 * 数据源是仓库根的 `data/daily/<期号>/report.json`——**不在 `src/` 里**：它是
 * 「要发布的正本」，由 `daily publish` 从工作区 `out/` 搬过来，和构建用的派生数据
 * （`src/data/image-manifest.json`）不是一类东西。`glob()` 的 `base` 可以指到
 * `src/` 之外，这一点在 M4.1 用七个真实期号验证过。
 *
 * 三件事因此一起退掉了：`render()`（正文本来就是空的）、`draft` 过滤（发布即上线，
 * 草稿留在 `out/`）、以及 frontmatter 里的 `title` / `pubDate`（由期号推导）。
 *
 * 字段与 `schemas/report.schema.json` 一一对应。**只加不改**：改名字要升
 * `schema_version` 并写迁移，否则老期号会读不出来。
 */

/** 一句带来源的话。`sources` 是条目键（`x:<id>`），页面不显示，用来回溯。 */
const claim = z.object({
  text: z.string().trim().min(1, 'claim.text 不能为空'),
  sources: z.array(z.string()).default([]),
});

/** 分类（聊人 / 聊音声 / 聊事情）。目前各期 `categories` 为空，站点按「空则整节不渲染」处理。 */
const category = z.object({
  id: z.string().trim().min(1),
  label: z.string().trim().min(1),
  summary: z.string().trim().default(''),
  highlights: z.array(claim).default([]),
  interactions: z.array(claim).default([]),
});

const dailyReports = defineCollection({
  loader: glob({
    base: './data/daily',
    pattern: '*/report.json',
    // 目录名就是期号：`261027/report.json` → id `261027`
    generateId: ({ entry }) => entry.split(/[\\/]/)[0],
  }),
  schema: z.object({
    schema_version: z.number().int().default(1),
    /**
     * 期号与时间。**期号 = 覆盖的那一天 + 哪一版 = 网址**（`YYMMDD`，JST）。
     *
     *   261029      声优版（声优 + 音声社团）
     *   261029-g    Galgame 版（游戏制造商 + 信息号）
     *   261029-2    同一天的第二期声优版
     *   261029-g2   同一天的第二个 Galgame 版
     *
     * 不带后缀的永远是声优版——10-29 之前的所有期号都是它，旧档不用迁移。
     * 期号里没有小时，因为一天的数据要到 JST 24:00 才闭合，真实出稿必然在次日凌晨——
     * 小时写进期号只会得到「比内容晚一天」或者「一个假时间」。发布时间单独记在
     * `published_at` 里，那个是真的。
     */
    issue: z.object({
      id: z
        .string()
        .regex(
          /^[0-9]{6}(?:-(?:g(?:[2-9]|[1-9][0-9])?|(?:[2-9]|[1-9][0-9])))?$/,
          '期号必须是 YYMMDD / YYMMDD-N / YYMMDD-g / YYMMDD-gN（N 从 2 起，最多两位）'
        ),
      published_at: z.string().trim().default(''),
      window: z.object({ start: z.string().optional(), end: z.string().optional() }).default({}),
      status: z.enum(['draft', 'confirmed']).default('draft'),
      confirmed_at: z.string().nullable().default(null),
    }),
    counts: z
      .object({
        items: z.number().int().nonnegative().default(0),
        accounts: z.number().int().nonnegative().default(0),
        late: z.number().int().nonnegative().default(0),
        skipped_duplicate: z.number().int().nonnegative().default(0),
      })
      .default({ items: 0, accounts: 0, late: 0, skipped_duplicate: 0 }),
    /**
     * 副标题 = 今日看点的 70 字以内简报，显示在标题下方。
     * 不要写日期和账号名——日期在标题与「发布于」里已经有了，
     * 账号名读者扫一眼名单就知道，占掉这 70 字很浪费。
     * 也**不要写「声优侧 / 厂商侧」**：读者看不到栏目边界，直接说人或公司。
     * 超长会直接让构建失败；为空只在构建日志里 warn（允许先出骨架再补）。
     */
    description: z.string().trim().max(70, 'description 是「今日看点」的简报，必须 ≤ 70 字').default(''),
    /**
     * 今日看点：排在最前面的概括性文本，每项一段。
     *
     * **只写三样东西**：① 名单前 9 的声优提到的重点；② 抓到的内容里
     * 本人对自己热度／排行的讨论；③ 特别活动（生誕祭、线下活动、销量里程碑）。
     * 其余一律进「详细」——看点一旦把每个人的事都概括一遍，就只是「详细」的
     * 加长版，读者还是要往下翻，那这一段就没有意义了。
     * 为空时页面会显示「待补充」提示，提醒还没跑完 LLM 那一步。
     */
    highlights: z.array(claim).default([]),
    /** 全局洞察（跨分类的观察）。为空则整节不渲染。 */
    insights: z.array(claim).default([]),
    /** 名单内多人之间的互动，每项一条；为空则整段不渲染 */
    interactions: z.array(claim).default([]),
    /**
     * 作品动态：**一条一个作品**，页面上按条渲染成列表。
     *
     * 以前是一整段话，读起来像新闻通稿，而且「多部作品同日发售」这种概括会把作品名
     * 吞掉——读者看不出到底是哪几部。改成数组之后，一条只说一个作品（或一件事），
     * 开始发售 / 预约的那条必须带作品名。
     *
     * 不带来源链接：人名在 people 里已经链到主号，再给每条加引用会变成链接堆。
     * 同一件事牵涉好几个人时可以写在一条里——但「几部作品同日发售」不行，那要一部一条。
     */
    works: z.array(z.string().trim().min(1)).max(24).default([]),
    categories: z.array(category).default([]),
    /**
     * 当天有活动的账号（含只出现在 highlights 里、没有 people 行的人）。
     * 正文里的 `@handle` 靠它变成链接——不在这个集合里就保持纯文本。
     */
    accounts: z.array(z.string().trim().min(1)).default([]),
    /**
     * 每人一句话（页面上叫「详细」）。渲染成 `[声优名](主号链接) ：summary`——
     * 名字是链接，summary 只写事，**不要再把 @handle 写进句子里**。
     * summary 为空即视为当日无活动，不渲染该行。
     *
     * 一个人可能有主号、小号、社团号（名单里同 `name` 的多个 handle）。
     * 内容合并到**一条**里叙述，`via` 记下还有哪些号参与了——
     * 页面在句末渲染成小一号、颜色变淡的账号名链接（显示 handle，不显示人名）。
     * 只列真正说了话的号；主号不重复进 `via`。
     */
    people: z
      .array(
        z.object({
          handle: z.string().trim().min(1),
          category: z.string().trim().default(''),
          summary: z.string().trim().default(''),
          via: z.array(z.string().trim().min(1)).default([]),
          sources: z.array(z.string()).default([]),
        }),
      )
      .default([]),
    provenance: z
      .object({
        generator: z.string().trim().default('daily'),
        prompt_version: z.number().int().default(1),
        cache_key: z.string().default(''),
        generated_at: z.string().default(''),
      })
      .default({ generator: 'daily', prompt_version: 1, cache_key: '', generated_at: '' }),
  }),
});

/**
 * 日报的**日语版**：`data/daily/<期号>/report.ja.json`（可选）。
 *
 * 单独一份文件、不进 `report.json`，理由有三条：
 * ① 正本由 `daily publish` 从 `out/` 搬过来，手写的内容放进去会被下一次重发冲掉；
 * ② `report.json` 有判卷（`apply` / `confirm`）管着，翻译不该走那条闸门；
 * ③ 没有日语版的期号就不该有按钮——「文件不存在」本身就是状态。
 *
 * 字段和中文版一一对应，只是每条从一段话变成一句话：日语比中文长，
 * 按中文的断句逐句翻，读起来最像播报。**缺人不会报错**（可以只翻一部分），
 * `DailyLayout` 会在构建日志里报被覆率。
 */
const dailyJa = defineCollection({
  loader: glob({
    base: './data/daily',
    pattern: '*/report.ja.json',
    generateId: ({ entry }) => entry.split(/[\\/]/)[0],
  }),
  schema: z.object({
    schema_version: z.number().int().default(1),
    /**
     * Ci-en のタイトル後半（钩子）。`【声優Xまとめ 10/27】` の前綴はコードが作るので、
     * ここには書かない——日付を手で持つと、いつか中身と日付がずれる。
     */
    hook: z.string().trim().max(40, '标题钩子 ≤ 40 字（列表里超了会被截）').default(''),
    description: z.string().trim().max(140, '日语版副标题 ≤ 140 字').default(''),
    /**
     * Ci-en 版の**中国語**副標題。空なら正本の `description` を使う。
     * 正本の副標題が厂商寄りでも、Ci-en 版は声优だけなので言い換えたいことがある。
     */
    description_zh: z.string().trim().max(70, '中文副标题 ≤ 70 字').default(''),
    highlights: z.array(z.string().trim().min(1)).default([]),
    /**
     * Ci-en 版に載せる中文 `highlights` の添字（0 起算）。
     *
     * Ci-en 版は声优栏目しか出さないので、厂商側だけの看点は落とす。落とす対象は
     * 内容を見ないと決められないので、言語ごとの自動判定ではなくここで選ぶ。
     * 空なら全部載せる。**`highlights` と同じ件数**にすること（闸门が見ている）。
     */
    highlight_indexes: z.array(z.number().int().min(0)).default([]),
    /** 中文正本と同じく一条一个作品（`cien.ts` 渲染成「・」行）。 */
    works: z.array(z.string().trim().min(1)).max(24).default([]),
    interactions: z.array(z.string().trim().min(1)).default([]),
    /** 中文版 `people` 的顺序就是这里的顺序；`handle` 必须对得上。 */
    people: z
      .array(
        z.object({
          handle: z.string().trim().min(1),
          summary: z.string().trim().min(1),
        }),
      )
      .default([]),
    insights: z.array(z.string().trim().min(1)).default([]),
  }),
});

export const collections = { blog, dailyReports, dailyJa };
