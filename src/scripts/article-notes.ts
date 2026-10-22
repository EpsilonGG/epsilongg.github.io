/**
 * 文章注释：点击正文里的注释标记，在页面底部弹出一个小面板显示注释内容。
 *
 * 行为
 * ----
 * - 面板从底部滑出，右上角 × 关闭；Esc 关闭；点击面板外关闭。
 * - 关闭后焦点回到刚才点的那条注释标记，键盘用户不会迷路。
 * - 面板内容是从文末注释列表里克隆出来的，所以两处永远一致。
 * - 文章末尾的完整注释列表仍然存在，面板只是「就近看一眼」的快捷方式。
 */

const REF_SELECTOR = '.prose a[data-footnote-ref]';

/** 取必须存在的节点；缺了就说明模板被改坏了，直接放弃初始化。 */
function must<T>(value: T | null): T {
  if (value === null) {
    throw new Error('article-notes: 缺少必要的 DOM 节点');
  }
  return value;
}

function setup(): void {
  const root = document.getElementById('note-popover');
  if (!root) return;

  const popover = root;
  const panel = must(popover.querySelector<HTMLElement>('.note-popover__panel'));
  const body = must(popover.querySelector<HTMLElement>('.note-popover__body'));
  const label = must(popover.querySelector<HTMLElement>('.note-popover__label'));
  const closeButton = must(popover.querySelector<HTMLButtonElement>('.note-popover__close'));

  let activeRef: HTMLAnchorElement | null = null;

  function close(): void {
    if (popover.hidden) return;
    popover.hidden = true;
    if (activeRef) {
      activeRef.setAttribute('aria-expanded', 'false');
    }
    const previous = activeRef;
    activeRef = null;
    previous?.focus({ preventScroll: true });
  }

  function open(ref: HTMLAnchorElement): void {
    const href = ref.getAttribute('href') ?? '';
    if (!href.startsWith('#')) return;
    const target = document.getElementById(href.slice(1));
    if (!target) return;

    // 克隆文末那条注释，去掉「返回正文」的箭头
    const clone = target.cloneNode(true) as HTMLElement;
    clone.querySelectorAll('[data-footnote-backref]').forEach((node) => node.remove());

    body.replaceChildren(...Array.from(clone.childNodes));
    const index = ref.textContent?.trim() ?? '';
    label.textContent = index ? `注释 ${index}` : '注释';

    if (activeRef && activeRef !== ref) {
      activeRef.setAttribute('aria-expanded', 'false');
    }
    activeRef = ref;
    ref.setAttribute('aria-expanded', 'true');

    popover.hidden = false;
    panel.scrollTop = 0;
    panel.focus({ preventScroll: true });
  }

  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    const ref = target.closest<HTMLAnchorElement>(REF_SELECTOR);
    if (ref) {
      // 有面板可弹时就不跳转到文末；脚本没跑起来时链接仍然可用
      event.preventDefault();
      open(ref);
      return;
    }

    if (!popover.hidden && !popover.contains(target)) {
      close();
    }
  });

  closeButton.addEventListener('click', () => close());

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !popover.hidden) {
      event.preventDefault();
      close();
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setup, { once: true });
} else {
  setup();
}
