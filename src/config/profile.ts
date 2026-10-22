/**
 * 个人资料配置的类型包装。
 *
 * 数据放在 `profile.json`：Astro 页面与 README 同步脚本（Python）读取同一份文件，
 * 保证首页、名片页与 GitHub Profile README 的个人信息永远一致。
 */
import data from './profile.json';

export interface Profile {
  /** 公开使用的姓名或名称 */
  name: string;
  /** 一句简短的座右铭或个人定位 */
  tagline: string;
  /** 2–4 段个人介绍，每段一个字符串 */
  intro: string[];
  /** 可选：头像图片路径（放在 public/images/ 下），留空则不显示头像 */
  avatar: string;
  /** 可选：所在城市，留空则不显示 */
  location: string;
  /** 可选：公开联系邮箱，留空则不显示 */
  email: string;
  /** 可选：用于 SEO 与 RSS 的简介摘要 */
  description: string;
}

export const profile: Profile = data as Profile;
