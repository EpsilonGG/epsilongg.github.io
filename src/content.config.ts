import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

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
    }),
});

/**
 * 日报集合：由本地 WorkBuddy（LLM）基于 X-Reader 抓取的推文生成的每日摘要。
 * 与 blog 分离，避免混入「笔记」归档；内容来源默认标记为 `ai`（AI 整理）。
 *
 * 正文三段全部是结构化字段，不写进 Markdown 正文——原因有三：
 * 1. 链接由 `handle` 拼出来（`https://x.com/<handle>`），模型不可能写错网址；
 * 2. `summary` 为空的条目自动不渲染，天然满足「当日没有活动就省略」；
 * 3. 上百人时这些字段要拿去做分类视图和 JSON 输出，藏在正文里就取不出来。
 *
 * **文件名即发布时间**：`YYMMDDHH.md`（八位数字，JST），如 `26103122.md`
 * 表示 2026-10-31 22:00。所以这里**没有 `pubDate` 字段**——时间只有文件名
 * 一个来源，不存在「URL 和日期对不上」这种状态。精确到小时是为了存档：
 * 同一天可以出多期，重跑不会覆盖上一期。
 */
const daily = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/daily' }),
  schema: z.object({
    /**
     * 副标题 = 今日看点的 50 字以内简报，显示在标题下方。
     * 不要写日期和账号名——日期在标题与「发布于」里已经有了，
     * 账号名读者扫一眼名单就知道，占掉这 50 字很浪费。
     * 超长会直接让构建失败；缺失只在构建日志里 warn（允许先出骨架再补）。
     */
    description: z
      .string()
      .trim()
      .min(1, 'description 不能是空字符串')
      .max(50, 'description 是「今日看点」的简报，必须 ≤ 50 字')
      .optional(),
    source: z.enum(['original', 'ai']).default('ai'),
    /** 当天有活动的账号（由抓取数据推导，不需要手写） */
    accounts: z.array(z.string().trim().min(1)).default([]),
    /**
     * 今日看点：排在最前面的概括性文本，每项一段。
     *
     * **只写三样东西**：① 名单前 9 的声优提到的重点；② 抓到的内容里
     * 本人对自己热度／排行的讨论；③ 特别活动（生誕祭、线下活动、销量里程碑）。
     * 其余一律进「详细」——看点一旦把每个人的事都概括一遍，就只是「详细」的
     * 加长版，读者还是要往下翻，那这一段就没有意义了。
     * 为空时页面会显示「待补充」提示，提醒还没跑完 LLM 那一步。
     */
    highlights: z.array(z.string().trim().min(1)).default([]),
    /** 名单内多人之间的互动，每项一条；为空则整段不渲染 */
    interactions: z.array(z.string().trim().min(1)).default([]),
    /**
     * 作品动态：一段话，汇总名单里的人在推上提到的作品进度
     * （制作中 / 正式发售 / 销量里程碑 / 上架平台）。
     *
     * 单独一段而不是塞进 highlights 或 people，是因为它是**跨人**的横向汇总：
     * 同一条「秋季促销两部破 5000 DL」会牵涉到好几个人，按人写会重复，
     * 按段写一句就够。**不加来源链接**——页面上每个人名已经链到主号，
     * 再给每条加引用会让这一段变成链接堆，读者反而看不出哪件事更重要。
     */
    works: z.string().trim().default(''),
    /**
     * 每人一句话（页面上叫「详细」）。渲染成 `[声优名](主号链接) ：summary`——
     * 名字是链接，summary 只写事，**不要再把 @handle 写进句子里**。
     * summary 为空即视为当日无活动，不渲染该行。
     */
    people: z
      .array(
        z.object({
          handle: z.string().trim().min(1),
          summary: z.string().trim().default(''),
        }),
      )
      .default([]),
    draft: z.boolean().default(false),
  }),
});

export const collections = { blog, daily };
