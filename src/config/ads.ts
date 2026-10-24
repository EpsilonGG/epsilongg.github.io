/**
 * 文章页右侧广告位的类型包装。
 *
 * 默认关闭，`slots` 为空。这一列在版面里本来就存在——它是给正文居中用的
 * 对称占位（左侧栏 13rem + 间隔 2rem，右侧同样一份），所以把广告放进去
 * 不会让正文移动一个像素。格式与开通步骤见 `README/ads.md`。
 */
import data from './ads.json';

export interface AdSlot {
  /** 横幅图片地址，放在 `public/` 下，例如 `/images/ads/xxx-200x200.png` */
  image: string;
  /** 点击跳转地址，联盟链接把跟踪参数一起写进来 */
  href: string;
  /** 横幅原始像素宽（写死，避免图片加载前后布局跳动） */
  width: number;
  /** 横幅原始像素高 */
  height: number;
  /** 替代文字；纯装饰性的广告图也应写一句，屏幕阅读器会读 */
  alt: string;
}

export interface AdsConfig {
  /** 总开关。false 时整个 <aside> 不渲染，产物里连标签都没有 */
  enabled: boolean;
  /** 广告性质标注，渲染在广告位上方（法规要求明示） */
  label: string;
  /** 竖排的横幅，按顺序从上到下 */
  slots: AdSlot[];
}

export const ads: AdsConfig = data as AdsConfig;

/** 有开关、也有内容，才真的渲染 */
export const hasAds: boolean = ads.enabled && ads.slots.length > 0;
