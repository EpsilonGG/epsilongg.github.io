/**
 * 背景图开关的状态。
 *
 * 和 theme.ts 一样：页面首次绘制前的初始化脚本在 BaseLayout 中内联执行
 * （避免先白后花地闪一下），交互逻辑在这里，BackgroundToggle 只负责调用。
 *
 * 只有宽屏才会真的显示照片，但这个开关本身在任何宽度都记住用户的选择——
 * 用户在 27 寸屏上开了，换个窄窗口看代码时不该被悄悄改回关闭。
 */

export const BACKGROUND_STORAGE_KEY = 'bg';

export type BackgroundMode = 'on' | 'off';

export const DEFAULT_BACKGROUND: BackgroundMode = 'off';

export function isBackgroundMode(value: unknown): value is BackgroundMode {
  return value === 'on' || value === 'off';
}

/** 读取已保存的选择；无值、非法值或读取异常时返回 null */
export function readStoredBackground(): BackgroundMode | null {
  try {
    const value = window.localStorage.getItem(BACKGROUND_STORAGE_KEY);
    return isBackgroundMode(value) ? value : null;
  } catch {
    return null;
  }
}

/** 保存选择；写入失败时静默忽略，不影响当前会话 */
export function storeBackground(mode: BackgroundMode): void {
  try {
    window.localStorage.setItem(BACKGROUND_STORAGE_KEY, mode);
  } catch {
    /* 存储不可用：保持当前状态，不做任何提示 */
  }
}

export function getCurrentBackground(): BackgroundMode {
  const value = document.documentElement.dataset.bg;
  return isBackgroundMode(value) ? value : DEFAULT_BACKGROUND;
}

export function applyBackground(mode: BackgroundMode): void {
  document.documentElement.dataset.bg = mode;
}

export function toggleBackground(): BackgroundMode {
  const next: BackgroundMode = getCurrentBackground() === 'on' ? 'off' : 'on';
  applyBackground(next);
  storeBackground(next);
  return next;
}
