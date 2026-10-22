import data from './navigation.json';

export interface NavItem {
  /** 导航显示文字 */
  label: string;
  /** 站内路径 */
  href: string;
  /** 一句话说明该页面的作用，用于首页导航区 */
  description: string;
}

export const navigation: NavItem[] = data as NavItem[];

/**
 * 首页导航区：首页本身是当前位置，不再重复放「首页」链接。
 */
export const homeNavigation: NavItem[] = navigation.filter(
  (item) => normalizePath(item.href) !== '/',
);

/** 去掉末尾斜杠，便于比较当前路径（Astro 默认 trailingSlash: 'ignore'） */
export function normalizePath(pathname: string): string {
  if (!pathname) return '/';
  const withoutQuery = pathname.split(/[?#]/)[0] ?? '/';
  const trimmed = withoutQuery.replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
}

export function isCurrentPath(currentPathname: string, href: string): boolean {
  return normalizePath(currentPathname) === normalizePath(href);
}
