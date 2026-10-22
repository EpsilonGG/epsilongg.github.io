/**
 * 外部链接数据。
 *
 * 名片页（/links/）与链接库（/morelinks/）都从这里读取数据，
 * 页面组件中不硬编码任何个人链接。
 *
 * 注意：
 * - 只填写可以确认的真实地址，不要填写猜测或未经验证的账号。
 * - 没有内容的分类会自动隐藏，不会渲染空区块。
 * - 每个分类用 layout 决定渲染方式，不写则按 'list' 渲染。
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
  /** 徽章图片，仅 badges 布局使用，标准尺寸 88×31（文件按 2 倍图存放） */
  badge?: string;
  /** 图标图片，仅 icons 布局使用，正方形（文件按 2 倍图存放） */
  icon?: string;
  /** 卡片右上角的次要信息，例如 Python */
  meta?: string;
}

/** 分类的渲染方式 */
export type GroupLayout = 'list' | 'cards' | 'icons' | 'badges';

export interface LinkGroup {
  /** 稳定的分类标识 */
  id: string;
  /** 分类标题 */
  title: string;
  /** 分类说明，可省略 */
  description?: string;
  /** 渲染方式，默认 list */
  layout?: GroupLayout;
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
 * 顺序即页面顺序：个人平台 → 项目 → 工具 → 参考资料 → 友情链接。
 */
export const linkGroups: LinkGroup[] = [
  {
    id: 'platforms',
    title: '个人平台',
    description: '在其他平台上可以找到我的地方。',
    layout: 'cards',
    links: [
      {
        label: 'GitHub',
        href: 'https://github.com/EpsilonGG',
        description: '代码与项目仓库。',
        meta: '外部',
      },
    ],
  },
  {
    id: 'projects',
    title: '项目与代码仓库',
    description: '正在维护的代码与项目记录。',
    layout: 'cards',
    links: [
      {
        label: 'X-rss',
        href: 'https://github.com/EpsilonGG/X-rss',
        description: '基于 GitHub Actions 的 X / Twitter RSS 聚合器，自动生成标准 RSS 并发布到 Pages。',
        meta: 'Python',
      },
      {
        label: 'X-Reader',
        href: 'https://github.com/EpsilonGG/X-Reader',
        description: '抓取 X、RSS 与 YouTube 的更新，推送到 Telegram 和 QQ。',
        meta: 'Python',
      },
    ],
  },
  {
    id: 'tools',
    title: '工具与服务',
    description: '日常使用、值得推荐的工具。',
    layout: 'icons',
    links: [
      {
        label: 'MDN Web Docs',
        href: 'https://developer.mozilla.org/',
        description: 'Web 平台技术参考。',
        icon: '/images/tools/mdn.png',
      },
      {
        label: 'Astro 文档',
        href: 'https://docs.astro.build/',
        description: '本站使用的框架文档。',
        icon: '/images/tools/astro.png',
      },
      {
        label: 'GitHub Pages',
        href: 'https://docs.github.com/pages',
        description: '本站的托管与部署。',
        icon: '/images/tools/github-pages.png',
      },
    ],
  },
  {
    id: 'research',
    title: '研究与参考资料',
    description: '长期回看的文献与资料。',
    links: [
      {
        label: 'PubMed',
        href: 'https://pubmed.ncbi.nlm.nih.gov/',
        description: '生物医学文献检索。',
        tags: ['文献'],
      },
      {
        label: 'NCBI',
        href: 'https://www.ncbi.nlm.nih.gov/',
        description: '序列、基因组与数据库资源。',
        tags: ['数据'],
      },
      {
        label: 'Google Scholar',
        href: 'https://scholar.google.com/',
        description: '跨库学术搜索。',
        tags: ['检索'],
      },
    ],
  },
  {
    id: 'friends',
    title: '友情链接',
    description: '经常串门的地方。',
    layout: 'badges',
    links: [
      {
        label: 'Galgame批评',
        href: 'https://space.bilibili.com/2072586344',
        description: 'B站评论',
        badge: '/images/links/galgame-piping.png',
      },
      {
        label: 'YMGAL',
        href: 'https://www.ymgal.games/',
        description: '资料库',
        badge: '/images/links/ymgal.png',
      },
      {
        label: 'DLsite',
        href: 'https://www.dlsite.com/',
        description: '同人贩售',
        badge: '/images/links/dlsite.png',
      },
      {
        label: 'Ci-en',
        href: 'https://ci-en.dlsite.com/',
        description: '创作者支援',
        badge: '/images/links/ci-en.png',
      },
    ],
  },
];

/** 判断是否为外部链接（用于决定 target / rel） */
export function isExternalHref(href: string): boolean {
  return /^https?:\/\//i.test(href);
}
