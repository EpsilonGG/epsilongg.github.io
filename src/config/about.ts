/**
 * 「名片」页面的内容配置。
 *
 * 数组为空时，页面对应区块会显示一行简洁的提示，而不是渲染空区块。
 * 关注领域用英文表达，保持与其他条目的视觉一致性。
 */

export interface AboutEntry {
  title: string;
  /** 可选：时间范围，例如「2023 — 至今」 */
  period?: string;
  description: string;
  /** 可选：相关链接（站内路径或完整 URL） */
  href?: string;
}

export interface AboutConfig {
  /** 简介段落 */
  intro: string[];
  /** 关注领域 */
  focusAreas: string[];
  /** 当前进行的项目 */
  projects: AboutEntry[];
  /** 个人经历 / 研究经历 */
  experience: AboutEntry[];
}

export const about: AboutConfig = {
  intro: ['不务正业的研究生'],
  focusAreas: ['Galgame', 'Doujin ASMR/Games', 'Life Sciences', 'Vibe Coding'],
  projects: [
    {
      title: 'XB-JSONMD',
      href: 'https://github.com/EpsilonGG/XB-JSONMD',
      description: '多账号 X 抓取、日报与周报生成，并输出结构化 JSON 与 Markdown 的独立流水线。',
    },
    {
      title: 'VisualNovel-Interview-RSS',
      href: 'https://github.com/EpsilonGG/VisualNovel-Interview-RSS',
      description: '把 Galgame 开发者访谈整理成 RSS，并发布到 GitHub Pages。',
    },
    {
      title: 'blog-template',
      href: 'https://github.com/EpsilonGG/blog-template',
      description: '本站的主页模板：首页 / 名片 / 链接库 / 笔记，笔记自带一篇语法总览，改几个 JSON 就能上线。',
    },
  ],
  experience: [
    {
      title: '中山大学 海洋科学（本硕）',
      description: '参与鱼类疫病防治及饲料配方优化方向国家重点研发计划。',
    },
  ],
};
