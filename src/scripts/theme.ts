/**
 * 主题状态的唯一实现。
 *
 * 页面首次绘制前的初始化脚本在 BaseLayout 中以内联方式执行（避免闪烁），
 * 交互逻辑在这里实现，ThemeToggle 组件只负责调用，不重复实现第二套逻辑。
 *
 * 所有 localStorage 访问都包在 try/catch 中：隐私模式、禁用存储或写入
 * 配额不足时，页面必须继续可用，只是无法记住用户的选择。
 */

export const THEME_STORAGE_KEY = 'theme';

export type Theme = 'light' | 'dark';

export const DEFAULT_THEME: Theme = 'light';

export function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark';
}

/** 读取已保存的主题；无值、非法值或读取异常时返回 null */
export function readStoredTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(value) ? value : null;
  } catch {
    return null;
  }
}

/** 保存主题；写入失败时静默忽略，不影响当前会话 */
export function storeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* 存储不可用：保持当前主题，不做任何提示 */
  }
}

export function getCurrentTheme(): Theme {
  const value = document.documentElement.dataset.theme;
  return isTheme(value) ? value : DEFAULT_THEME;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

export function toggleTheme(): Theme {
  const next: Theme = getCurrentTheme() === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  storeTheme(next);
  return next;
}
