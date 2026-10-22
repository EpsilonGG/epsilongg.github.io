/**
 * 笔记页的搜索与标签筛选。
 *
 * 设计约束（来自项目计划）：
 * - 纯原生实现，不引入搜索库（Fuse.js / Lunr 等）。
 * - 不重复在构建期和运行期维护两套文章清单：筛选数据直接来自页面已有的
 *   DOM（每个 <li> 上挂的 data-title / data-description / data-tags）。
 * - 初始 HTML 已完整渲染文章列表；本脚本只负责隐藏/显示，不依赖 JS 才能看到内容。
 * - 搜索与标签筛选逻辑集中在此处，统一使用 AND 组合。
 * - 不做中文分词、拼写纠错或语义搜索，只做基本的子串匹配。
 */

interface ArchiveItem {
  /** 文章列表项（<li>） */
  el: HTMLElement;
  /** 所属年份分组（<section.archive-group>） */
  group: HTMLElement;
  /** 用于搜索匹配的索引字符串（标题 + 摘要 + 标签，已转小写） */
  haystack: string;
  /** 文章标签（用于标签筛选的精确匹配） */
  tags: string[];
}

function initArchiveFilter(): void {
  const root = document.querySelector<HTMLElement>('[data-archive-filter]');
  if (!root) return;

  const form = root.querySelector<HTMLFormElement>('[data-search-form]');
  const input = root.querySelector<HTMLInputElement>('[data-search-input]');
  const clearSearch = root.querySelector<HTMLButtonElement>('[data-search-clear]');
  const clearAll = root.querySelector<HTMLButtonElement>('[data-clear-all]');
  const countEl = root.querySelector<HTMLElement>('[data-result-count]');
  const emptyEl = root.querySelector<HTMLElement>('[data-search-empty]');
  const tagButtons = Array.from(
    root.querySelectorAll<HTMLButtonElement>('[data-tag-filter]'),
  );

  const items: ArchiveItem[] = Array.from(
    document.querySelectorAll<HTMLElement>('[data-search-item]'),
  ).map((el) => {
    let tags: string[] = [];
    try {
      const parsed = JSON.parse(el.dataset.tags ?? '[]');
      if (Array.isArray(parsed)) tags = parsed.map(String);
    } catch {
      tags = [];
    }
    const title = (el.dataset.title ?? '').toLowerCase();
    const description = (el.dataset.description ?? '').toLowerCase();
    const tagText = tags.join(' ').toLowerCase();
    return {
      el,
      group: el.closest<HTMLElement>('.archive-group') ?? el,
      haystack: `${title} ${description} ${tagText}`,
      tags,
    };
  });

  const apply = (): void => {
    const term = (input?.value ?? '').trim().toLowerCase();
    const activeTags = tagButtons
      .filter((btn) => btn.getAttribute('aria-pressed') === 'true')
      .map((btn) => (btn.dataset.tag ?? '').toLowerCase());

    let visible = 0;
    for (const item of items) {
      const matchesSearch = term === '' || item.haystack.includes(term);
      // 标签筛选：选中的标签文章必须全部具备（AND）
      const matchesTags =
        activeTags.length === 0 ||
        activeTags.every((t) => item.tags.some((it) => it.toLowerCase() === t));
      const show = matchesSearch && matchesTags;
      item.el.hidden = !show;
      if (show) visible += 1;
    }

    // 没有可见文章的年份分组整体隐藏，避免留下空标题
    const groups = new Set(items.map((i) => i.group));
    for (const g of groups) {
      const anyVisible = items.some((i) => i.group === g && !i.el.hidden);
      g.hidden = !anyVisible;
    }

    if (countEl) countEl.textContent = `共 ${visible} 篇`;
    if (emptyEl) emptyEl.hidden = visible !== 0;

    const hasActiveFilter = term !== '' || activeTags.length > 0;
    if (clearAll) clearAll.hidden = !hasActiveFilter;
  };

  // 输入即筛选（不区分大小写、首尾空格在 apply 内处理）
  input?.addEventListener('input', apply);

  // 提交按钮（语义化 / 键盘 Enter）不刷新页面
  form?.addEventListener('submit', (event) => {
    event.preventDefault();
    apply();
  });

  // 清空搜索框
  clearSearch?.addEventListener('click', () => {
    if (input) {
      input.value = '';
      input.focus();
    }
    apply();
  });

  // 标签切换（aria-pressed 表达选中状态，视觉状态由 CSS 处理）
  for (const btn of tagButtons) {
    btn.addEventListener('click', () => {
      const pressed = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', String(!pressed));
      apply();
    });
  }

  // 清除全部筛选：搜索与标签同时复位，并保留搜索关键词框的焦点
  clearAll?.addEventListener('click', () => {
    if (input) input.value = '';
    for (const btn of tagButtons) btn.setAttribute('aria-pressed', 'false');
    apply();
    input?.focus();
  });

  // 初始同步一次（无筛选时也应给出正确计数）
  apply();
}

// Astro 以 type="module" 引入本脚本，已处于 DOM 解析完成后执行，可直接初始化。
if (typeof document !== 'undefined') {
  initArchiveFilter();
}
