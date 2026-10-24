// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { satteri } from '@astrojs/markdown-satteri';

import { siteUrl } from './src/config/site.ts';
import { figureCaptionPlugin } from './src/lib/markdown-figure.mjs';
import { imageAttrsPlugin } from './src/lib/markdown-image-attrs.mjs';

/**
 * 站点部署在 GitHub Pages 用户站点（username.github.io），
 * 因此生产地址是根路径，不需要设置 `base`。
 *
 * 如果以后改为项目站点（username.github.io/repo/），
 * 需要同时设置 `base: '/repo'` 并检查站内绝对链接。
 */
export default defineConfig({
  site: siteUrl,
  trailingSlash: 'ignore',
  build: {
    format: 'directory',
  },
  integrations: [
    sitemap({
      // 404 页面不应出现在 sitemap 中
      filter: (page) => !page.replace(/\/$/, '').endsWith('/404'),
    }),
  ],
  markdown: {
    // 用 Sätteri 处理器并把脚注标题本地化；同时挂上「图片 title → figure 图注」的插件
    processor: satteri({
      features: {
        gfm: {
          footnotes: { label: '注释' },
        },
      },
      // 顺序：先补图片属性（lazy / async / no-referrer），再把带 title 的图升级成 figure
      hastPlugins: [imageAttrsPlugin, figureCaptionPlugin],
    }),
    shikiConfig: {
      themes: {
        light: 'github-light',
        dark: 'github-dark',
      },
      // 让代码块颜色由 data-theme 驱动，而不是只跟随系统偏好
      defaultColor: false,
    },
  },
});
