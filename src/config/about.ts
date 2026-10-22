/**
 * 「关于」页面的内容配置。
 *
 * 这里的文字全部是可编辑的占位内容，请在确认后替换为自己的真实信息。
 * 数组为空时，页面对应区块会显示一行简洁的提示，而不是渲染空区块。
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
  intro: [
    '这里是关于页面的简介段落，用来介绍个人背景、正在做的事情和长期关注的问题。',
    '内容在 src/config/about.ts 中维护，不需要修改页面组件。',
  ],
  focusAreas: [],
  projects: [],
  experience: [],
};
