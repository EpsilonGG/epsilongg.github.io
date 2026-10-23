/**
 * 文章页左侧栏交互。
 *
 * 三件事：
 * 1. 「置顶」按钮滚回页面顶部，并把焦点交给主区域（键盘用户不丢焦点）。
 * 2. 窄屏下「目录」图标展开 / 收起目录，点击目录项后自动收起。
 * 3. 滚动时高亮当前所在小节（scroll spy），用 rAF 节流，避免高频重排。
 *
 * 目录本身的滚动（超过 10 行时）由 CSS 的 overflow 完成，不需要脚本；
 * 没有 JavaScript 时目录仍是一组可点击的锚点链接。
 */

function initSidebar(): void {
  const root = document.querySelector<HTMLElement>('[data-article-sidebar]');
  if (!root) return;

  /* ---------- 置顶 ---------- */
  const topButton = root.querySelector<HTMLButtonElement>('[data-sidebar-top]');
  if (topButton) {
    topButton.addEventListener('click', () => {
      window.scrollTo({ top: 0 });
      // preventScroll：只交接焦点，不让浏览器再把页面滚到 #main 的顶部
      document.getElementById('main')?.focus({ preventScroll: true });
    });
  }

  /* ---------- 窄屏目录展开 ---------- */
  const toggle = root.querySelector<HTMLButtonElement>('[data-toc-toggle]');
  const toc = root.querySelector<HTMLElement>('[data-toc]');

  if (toggle && toc) {
    const setOpen = (open: boolean): void => {
      toc.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    };

    toggle.addEventListener('click', () => {
      setOpen(!toc.classList.contains('is-open'));
    });

    // 点目录项后收起，避免遮住刚跳到的正文
    toc.addEventListener('click', (event) => {
      if ((event.target as Element).closest('a')) setOpen(false);
    });
  }

  /* ---------- scroll spy ---------- */
  const links = Array.from(root.querySelectorAll<HTMLAnchorElement>('[data-toc-link]'));
  if (links.length === 0) return;

  const targets = links
    .map((link) => {
      const id = decodeURIComponent(link.getAttribute('href')?.slice(1) ?? '');
      const el = id ? document.getElementById(id) : null;
      return el ? { link, el } : null;
    })
    .filter((item): item is { link: HTMLAnchorElement; el: HTMLElement } => item !== null);

  if (targets.length === 0) return;

  let active: HTMLAnchorElement | null = null;
  let ticking = false;

  const update = (): void => {
    ticking = false;

    // 以视口上方 1/4 处为判定线：最后一个越过该线的标题即为当前小节
    const line = window.innerHeight * 0.25;
    let current = targets[0];

    for (const item of targets) {
      if (item.el.getBoundingClientRect().top <= line) {
        current = item;
      } else {
        break;
      }
    }

    if (current.link === active) return;

    active?.classList.remove('is-active');
    active?.removeAttribute('aria-current');
    current.link.classList.add('is-active');
    current.link.setAttribute('aria-current', 'true');
    active = current.link;
  };

  const schedule = (): void => {
    if (!ticking) {
      ticking = true;
      window.requestAnimationFrame(update);
    }
  };

  update();
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule, { passive: true });
}

if (typeof document !== 'undefined') {
  initSidebar();
}
