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
 */
const daily = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/daily' }),
  schema: z.object({
    title: z.string().trim().min(1, 'title 不能为空'),
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
    pubDate: z.coerce.date(),
    source: z.enum(['original', 'ai']).default('ai'),
    /** 当天有活动的账号（由抓取数据推导，不需要手写） */
    accounts: z.array(z.string().trim().min(1)).default([]),
    /**
     * 今日看点：排在最前面的概括性文本，每项一段。
     * 为空时页面会显示「待补充」提示，提醒还没跑完 LLM 那一步。
     */
    highlights: z.array(z.string().trim().min(1)).default([]),
    /** 名单内多人之间的互动，每项一条；为空则整段不渲染 */
    interactions: z.array(z.string().trim().min(1)).default([]),
    /** 每人一句话（页面上叫「详细」），链接由 handle 生成；summary 为空即视为当日无活动 */
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
