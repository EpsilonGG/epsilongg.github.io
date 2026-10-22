/**
 * 外部链接数据。
 *
 * 名片页（/links/）与链接库（/morelinks/）都从这里读取数据，
 * 页面组件中不硬编码任何个人链接。
 *
 * 注意：
 * - 只填写可以确认的真实地址，不要填写猜测或未经验证的账号。
 * - 没有内容的分类会自动隐藏，不会渲染空区块。
 * - 下面「研究与参考资料」「工具与服务」中的条目是真实可访问的公开资源，
 *   仅作为结构示例，请按需替换为自己的常用链接。
 */

export interface LinkItem {
  /** 链接显示名称 */
  label: string;
  /** 完整 URL 或站内路径 */
  href: string;
  /** 一句话说明 */
  description?: string;
  /** 可选标签，仅用于展示，首版不做筛选 */
  tags?: string[];
}

export interface LinkGroup {
  /** 稳定的分类标识 */
  id: string;
  /** 分类标题 */
  title: string;
  /** 分类说明，可省略 */
  description?: string;
  links: LinkItem[];
}

/**
 * 名片页的主要入口（个人平台）。
 * 留空时名片页只显示姓名、定位与站内入口，不显示空区块。
 */
export const primaryLinks: LinkItem[] = [
  { label: 'GitHub', href: 'https://github.com/EpsilonGG', description: '代码与项目仓库' },
];

/**
 * 链接库分类。分类由配置驱动，页面组件不硬编码链接。
 */
export const linkGroups: LinkGroup[] = [
  {
    id: 'platforms',
    title: '个人平台',
    description: '在其他平台上可以找到我的地方。',
    links: [],
  },
  {
    id: 'projects',
    title: '项目与代码仓库',
    description: '正在维护的代码与项目记录。',
    links: [],
  },
  {
    id: 'research',
    title: '研究与参考资料',
    description: '长期回看的文档与资料。',
    links: [
      {
        label: 'MDN Web Docs',
        href: 'https://developer.mozilla.org/',
        description: 'Web 平台技术参考。',
        tags: ['参考'],
      },
      {
        label: 'Astro 文档',
        href: 'https://docs.astro.build/',
        description: '本站使用的静态站点框架文档。',
        tags: ['工具'],
      },
    ],
  },
  {
    id: 'tools',
    title: '工具与服务',
    description: '日常使用、值得推荐的工具。',
    links: [
      {
        label: 'GitHub Pages 文档',
        href: 'https://docs.github.com/pages',
        description: '本站的托管与部署说明。',
        tags: ['工具'],
      },
    ],
  },
  {
    id: 'others',
    title: '其他',
    description: '',
    links: [],
  },
];

/** 判断是否为外部链接（用于决定 target / rel） */
export function isExternalHref(href: string): boolean {
  return /^https?:\/\//i.test(href);
}
