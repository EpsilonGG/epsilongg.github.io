// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

import { siteUrl } from './src/config/site.ts';

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
