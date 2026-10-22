/**
 * 外部链接数据。
 *
 * 名片页（/me/）与链接库（/morelinks/）都从这里读取数据，
 * 页面组件中不硬编码任何个人链接。
 *
 * 注意：
 * - 只填写可以确认的真实地址，不要填写猜测或未经验证的账号。
 * - 没有内容的分类会自动隐藏，不会渲染空区块。
 * - 每个分类用 layout 决定渲染方式，不写则按 'list' 渲染。
 * - 分类可以再拆成 subgroups（子栏目），子栏目之间自动画一条分隔线。
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
  /** 图标：badges 布局里显示 22×22，icons 布局里显示 48×48 */
  icon?: string;
  /** 没有图标时显示的字母块，省略则取 label 首字 */
  monogram?: string;
  /** 卡片右上角的次要信息，例如 Python */
  meta?: string;
}

/** 分类的渲染方式 */
export type GroupLayout = 'list' | 'cards' | 'icons' | 'badges';

/** 子栏目：同一个大分类下再分小组，组间用分隔线隔开 */
export interface LinkSubGroup {
  /** 稳定的子栏目标识 */
  id: string;
  /** 子栏目标题 */
  title: string;
  /** 渲染方式，默认继承外层，再缺省为 list */
  layout?: GroupLayout;
  links: LinkItem[];
}

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
  /** 子栏目：写了 subgroups 就忽略 links，子栏目之间自动分隔 */
  subgroups?: LinkSubGroup[];
}

/**
 * 名片页（/me/）的「主要平台」区块。
 * 留空时该区块不渲染，其余内容（简介、关注领域、项目与经历）照常显示。
 */
export const primaryLinks: LinkItem[] = [
  { label: 'GitHub', href: 'https://github.com/EpsilonGG', description: '代码与项目仓库' },
];

/**
 * 链接库分类。分类由配置驱动，页面组件不硬编码链接。
 * 顺序即页面顺序：个人平台 → 项目 → 工具 → 参考资料 → 常用链接。
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
        description: '技术参考',
        icon: '/images/tools/mdn.png',
      },
      {
        label: 'Astro 文档',
        href: 'https://docs.astro.build/',
        description: '框架文档',
        icon: '/images/tools/astro.png',
      },
      {
        label: 'GitHub Pages',
        href: 'https://docs.github.com/pages',
        description: '托管部署',
        icon: '/images/tools/github-pages.png',
      },
      {
        label: 'ChatGPT',
        href: 'https://chatgpt.com/',
        description: '对话模型',
        icon: '/images/tools/chatgpt.png',
      },
      {
        label: 'Google AI Studio',
        href: 'https://aistudio.google.com/',
        description: '模型调试',
        icon: '/images/tools/aistudio.png',
      },
      {
        label: 'Google Colab',
        href: 'https://colab.research.google.com/',
        description: '在线笔记本',
        icon: '/images/tools/colab.png',
      },
      {
        label: 'ErgouTree 工具箱',
        href: 'https://github.com/ergou10086/ErgouTreeImageToolsBox',
        description: '图像处理',
        monogram: 'ET',
      },
      {
        label: '小雪工具箱',
        href: 'https://github.com/xueayi/XiaoXue-Video-Tools',
        description: '视频图像处理',
        monogram: '雪',
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
    id: 'common',
    title: '常用链接',
    description: '常去的地方和朋友的主页。',
    links: [],
    subgroups: [
      {
        id: 'github',
        title: 'GitHub',
        layout: 'badges',
        links: [
          {
            label: 'xueayi',
            href: 'https://github.com/xueayi',
            description: '小雪',
            icon: '/images/people/xueayi.png',
          },
          {
            label: 'eryuemu',
            href: 'https://github.com/eryuemu',
            description: '二月木',
            icon: '/images/people/eryuemu.png',
          },
          {
            label: 'JupiterFeng',
            href: 'https://github.com/JupiterFeng',
            description: 'JianrenJun',
            icon: '/images/people/JupiterFeng.png',
          },
          {
            label: 'GalTransl',
            href: 'https://github.com/GalTransl',
            description: 'GalTransl 翻译工具',
            icon: '/images/people/GalTransl.png',
          },
          {
            label: 'ergou10086',
            href: 'https://github.com/ergou10086',
            description: 'ErgouTree',
            icon: '/images/people/ergou10086.png',
          },
        ],
      },
      {
        id: 'acg',
        title: 'ACG 资源',
        layout: 'badges',
        links: [
          {
            label: 'Galgame批评',
            href: 'https://space.bilibili.com/2072586344',
            description: 'B站评论',
            icon: '/images/links/icons/galgame-piping.png',
          },
          {
            label: 'YMGAL',
            href: 'https://www.ymgal.games/',
            description: '资料库',
            icon: '/images/links/icons/ymgal.png',
          },
          {
            label: 'DLsite',
            href: 'https://www.dlsite.com/',
            description: '同人贩售',
            icon: '/images/links/icons/dlsite.png',
          },
          {
            label: 'Ci-en',
            href: 'https://ci-en.dlsite.com/',
            description: '创作者支援',
            icon: '/images/links/icons/ci-en.png',
          },
          {
            label: 'CnGal',
            href: 'https://www.cngal.org/',
            description: '国产 Galgame 资料',
            icon: '/images/links/icons/cngal.png',
          },
          {
            label: '2DFan',
            href: 'https://galge.fun/',
            description: '攻略与补丁',
            icon: '/images/links/icons/2dfan.png',
          },
          {
            label: 'Hikarinagi',
            href: 'https://www.hikarinagi.org/',
            description: '资讯与评测',
            icon: '/images/links/icons/hikarinagi.png',
          },
          {
            label: '鲲Galgame',
            href: 'https://www.kungal.com/',
            description: '资源站',
            icon: '/images/links/icons/kungal.png',
          },
          {
            label: 'Bangumi',
            href: 'https://bgm.tv/',
            description: '番组计划',
            icon: '/images/links/icons/bangumi.png',
          },
          {
            label: 'VNDB',
            href: 'https://vndb.org/',
            description: '视觉小说数据库',
            monogram: 'V',
          },
          {
            label: '批评空间',
            href: 'https://erogamescape.dyndns.org/~ap2/ero/toukei_kaiseki/',
            description: 'ErogameScape 评分',
            icon: '/images/links/icons/erogamescape.png',
          },
          {
            label: '南+论坛',
            href: 'https://www.south-plus.net/',
            description: 'South Plus',
            monogram: '南',
          },
        ],
      },
    ],
  },
];

/** 判断是否为外部链接（用于决定 target / rel） */
export function isExternalHref(href: string): boolean {
  return /^https?:\/\//i.test(href);
}
