/**
 * 返回顶部按钮（仅笔记页使用）。
 *
 * 设计约束（来自项目计划）：
 * - 纯原生实现，不引入动画库。
 * - 顶部时隐藏，向下滚动超过阈值后显示。
 * - 使用 window.scrollTo({ top: 0 })；平滑滚动由全局 CSS 的
 *   scroll-behavior 控制，prefers-reduced-motion 下会自动降级为瞬时滚动。
 * - 滚动监听使用 passive + requestAnimationFrame 节流，避免高频重排。
 * - 静态站点无 SPA 导航，脚本随页面卸载而销毁，无需手动清理监听器。
 */

function initBackToTop(): void {
  const button = document.querySelector<HTMLButtonElement>('[data-back-to-top]');
  if (!button) return;

  // 滚动超过约一个半屏高度后显示按钮，避免刚滚动一点就冒出来
  const threshold = 320;
  let ticking = false;

  const update = (): void => {
    ticking = false;
    const show = window.scrollY > threshold;
    button.classList.toggle('is-visible', show);
  };

  const onScroll = (): void => {
    if (!ticking) {
      ticking = true;
      window.requestAnimationFrame(update);
    }
  };

  update();
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });

  button.addEventListener('click', () => {
    window.scrollTo({ top: 0 });
    // 将焦点移到主区域，保证键盘用户点击后焦点跟随到页面顶部。
    // preventScroll：否则浏览器会把页面滚到 #main 的顶部，而不是页面顶部。
    const main = document.getElementById('main');
    if (main) main.focus({ preventScroll: true });
  });
}

if (typeof document !== 'undefined') {
  initBackToTop();
}
