/**
 * 笔记页的搜索、标签筛选与分页。
 *
 * 设计约束（来自项目计划）：
 * - 纯原生实现，不引入搜索库（Fuse.js / Lunr 等）。
 * - 不重复在构建期和运行期维护两套文章清单：筛选数据直接来自页面已有的
 *   DOM（每个 <li> 上挂的 data-title / data-description / data-tags）。
 * - 初始 HTML 已完整渲染文章列表；本脚本只负责隐藏/显示，不依赖 JS 才能看到内容。
 * - 搜索与标签筛选逻辑集中在此处，统一使用 AND 组合。
 * - 不做中文分词、拼写纠错或语义搜索，只做基本的子串匹配。
 * - 分页：每页最多 PAGE_SIZE 篇；分页作用于「筛选后的结果集」，与搜索/标签联动。
 *   没有 JS 时所有文章照常显示（分页控件默认 hidden，由脚本在有多页时才显示）。
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
  /** 内容来源：original（默认）/ ai（AI 整理） */
  source: string;
}

/** 每页最多显示的笔记数量 */
const PAGE_SIZE = 10;

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

  // 「含 AI 整理」滑块：默认不勾选，勾选后列表才包含 AI 整理的文章。
  const aiToggle = root.querySelector<HTMLInputElement>('[data-ai-toggle]');
  // 列表栏目名：默认「原创与转载」，开启滑块后切换为「全部（含 AI 整理）」。
  const listHeading = root.querySelector<HTMLElement>('[data-archive-list-heading]');

  const paginationNav = root.querySelector<HTMLElement>('[data-archive-pagination]');
  const prevBtn = root.querySelector<HTMLButtonElement>('[data-page-prev]');
  const nextBtn = root.querySelector<HTMLButtonElement>('[data-page-next]');
  const numbersEl = root.querySelector<HTMLElement>('[data-page-numbers]');
  const pageInfoEl = root.querySelector<HTMLElement>('[data-page-info]');

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
    const source = el.dataset.source ?? 'original';
    return {
      el,
      group: el.closest<HTMLElement>('.archive-group') ?? el,
      haystack: `${title} ${description} ${tagText}`,
      tags,
      source,
    };
  });

  let currentPage = 1;

  const renderPagination = (totalPages: number): void => {
    if (!paginationNav) return;
    if (totalPages <= 1) {
      paginationNav.hidden = true;
      return;
    }
    paginationNav.hidden = false;
    if (pageInfoEl) pageInfoEl.textContent = `第 ${currentPage} / ${totalPages} 页`;
    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
    if (numbersEl) {
      numbersEl.replaceChildren();
      for (let page = 1; page <= totalPages; page++) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'archive-pagination__num';
        btn.textContent = String(page);
        btn.setAttribute('data-page', String(page));
        if (page === currentPage) btn.setAttribute('aria-current', 'page');
        numbersEl.appendChild(btn);
      }
    }
  };

  const apply = (): void => {
    const term = (input?.value ?? '').trim().toLowerCase();
    const activeTags = tagButtons
      .filter((btn) => btn.getAttribute('aria-pressed') === 'true')
      .map((btn) => (btn.dataset.tag ?? '').toLowerCase());
    // 默认（滑块未勾选）不显示 AI 整理文章；勾选后才纳入。
    const aiOn = aiToggle?.checked ?? false;

    // 1. 先算「是否匹配筛选」，并记录到 data-matched 上
    const matched: ArchiveItem[] = [];
    for (const item of items) {
      const matchesSearch = term === '' || item.haystack.includes(term);
      // 标签筛选：选中的标签文章必须全部具备（AND）
      const matchesTags =
        activeTags.length === 0 ||
        activeTags.every((t) => item.tags.some((it) => it.toLowerCase() === t));
      // 来源筛选：未开启滑块时排除 AI 整理文章。
      const matchesSource = aiOn || item.source !== 'ai';
      const isMatch = matchesSearch && matchesTags && matchesSource;
      if (isMatch) {
        item.el.setAttribute('data-matched', '');
        matched.push(item);
      } else {
        item.el.removeAttribute('data-matched');
      }
    }

    // 2. 分页作用于筛选结果集
    const totalPages = Math.max(1, Math.ceil(matched.length / PAGE_SIZE));
    if (currentPage > totalPages) currentPage = totalPages;
    const start = (currentPage - 1) * PAGE_SIZE;
    const end = start + PAGE_SIZE;

    // 3. 可见性 = 匹配筛选 且 落在当前页
    for (const item of items) {
      const isMatch = item.el.hasAttribute('data-matched');
      const index = isMatch ? matched.indexOf(item) : -1;
      const onPage = isMatch && index >= start && index < end;
      item.el.hidden = !onPage;
    }

    // 4. 没有可见文章的年份分组整体隐藏，避免留下空标题
    const groups = new Set(items.map((i) => i.group));
    for (const g of groups) {
      const anyVisible = items.some((i) => i.group === g && !i.el.hidden);
      g.hidden = !anyVisible;
    }

    // 5. 计数显示筛选结果总数（而非当前页数量）
    if (countEl) countEl.textContent = `共 ${matched.length} 篇`;
    if (emptyEl) emptyEl.hidden = matched.length !== 0;
    // 栏目名随滑块状态切换：默认「原创与转载」，开启后「全部（含 AI 整理）」。
    if (listHeading) {
      listHeading.textContent = aiOn ? '全部（含 AI 整理）' : '原创与转载';
    }

    // 6. 分页控件
    renderPagination(totalPages);

    // 7. 清除全部筛选按钮
    const hasActiveFilter = term !== '' || activeTags.length > 0 || aiOn;
    if (clearAll) clearAll.hidden = !hasActiveFilter;
  };

  // 输入即筛选（重置到第 1 页，避免停留在无结果的页码）
  input?.addEventListener('input', () => {
    currentPage = 1;
    apply();
  });

  // 提交按钮（语义化 / 键盘 Enter）不刷新页面
  form?.addEventListener('submit', (event) => {
    event.preventDefault();
    currentPage = 1;
    apply();
  });

  // 清空搜索框
  clearSearch?.addEventListener('click', () => {
    if (input) {
      input.value = '';
      input.focus();
    }
    currentPage = 1;
    apply();
  });

  // 标签切换（aria-pressed 表达选中状态，视觉状态由 CSS 处理）
  for (const btn of tagButtons) {
    btn.addEventListener('click', () => {
      const pressed = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', String(!pressed));
      currentPage = 1;
      apply();
    });
  }

  // 「含 AI 整理」滑块：勾选即把 AI 整理文章并入列表，并回到第 1 页
  aiToggle?.addEventListener('change', () => {
    currentPage = 1;
    apply();
  });

  // 清除全部筛选：搜索与标签同时复位，并保留搜索关键词框的焦点
  clearAll?.addEventListener('click', () => {
    if (input) input.value = '';
    for (const btn of tagButtons) btn.setAttribute('aria-pressed', 'false');
    if (aiToggle) aiToggle.checked = false;
    currentPage = 1;
    apply();
    input?.focus();
  });

  // 分页：上一页 / 下一页
  prevBtn?.addEventListener('click', () => {
    if (currentPage > 1) {
      currentPage -= 1;
      apply();
    }
  });
  nextBtn?.addEventListener('click', () => {
    currentPage += 1;
    apply();
  });
  // 页码按钮（事件委托）
  numbersEl?.addEventListener('click', (event) => {
    const target = (event.target as HTMLElement).closest('[data-page]');
    if (!target) return;
    const page = Number.parseInt(target.getAttribute('data-page') ?? '1', 10);
    if (!Number.isNaN(page)) {
      currentPage = page;
      apply();
    }
  });

  // 初始同步一次（无筛选时也应给出正确计数与分页）
  apply();
}

// Astro 以 type="module" 引入本脚本，已处于 DOM 解析完成后执行，可直接初始化。
if (typeof document !== 'undefined') {
  initArchiveFilter();
}
