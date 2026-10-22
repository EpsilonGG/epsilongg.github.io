/**
 * 站点级配置的类型包装。
 *
 * 数据本身放在 `site.json` 中，原因是 README 同步脚本（Python）也需要读取
 * 站点名称与正式域名，JSON 可以被两边直接读取，避免出现两份互相冲突的配置。
 */
import data from './site.json';

export interface SiteConfig {
  /** 站点名称，显示在 Header、Footer 与页面标题中 */
  name: string;
  /** 正式域名（GitHub Pages 用户站点根路径），不要以斜杠结尾 */
  url: string;
  /** 默认站点描述，用于首页与兜底 meta description */
  description: string;
  /** html lang 属性 */
  lang: string;
  /** 版权署名 */
  author: string;
  /** 版权起始年份 */
  startYear: number;
  /** 默认 Open Graph 分享图，留空则不输出 og:image */
  ogImage: string;
  /** 可选：GitHub 主页，留空则不在 Footer 显示 */
  github: string;
  /** 可选：公开联系邮箱，留空则不显示 */
  email: string;
}

export const site: SiteConfig = data as SiteConfig;

/** 去掉末尾斜杠的站点根地址，供 astro.config.mjs、RSS 与 sitemap 复用 */
export const siteUrl: string = site.url.replace(/\/+$/, '');

/** 把站内路径转换为正式域名的绝对地址 */
export function absoluteUrl(pathname: string): string {
  return new URL(pathname, `${siteUrl}/`).toString();
}
