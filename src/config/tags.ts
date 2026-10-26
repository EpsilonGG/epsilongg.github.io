/**
 * 笔记标签的封闭集合。
 *
 * 为什么是封闭的：标签一旦随手新增，两年后会变成三十个只有一两篇的碎标签，
 * 筛选器排不下，读者也记不住。所以这里只留六个大格子，放不进去的一律归「其它」。
 *
 * 数据放在 `tags.json`，schema 与页面共用同一份，避免「校验放行、界面没有」这种错位。
 */
import data from './tags.json';

/** 允许出现在 frontmatter `tags` 里的全部取值，顺序即筛选器里的显示顺序 */
export const BLOG_TAGS: readonly string[] = data.tags;

/** 放不进任何具体分类时的兜底标签 */
export const FALLBACK_TAG = '其它';

/** 供报错信息使用的「允许值」提示串 */
export const BLOG_TAG_HINT = BLOG_TAGS.join(' / ');
