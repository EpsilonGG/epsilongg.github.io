/**
 * 笔记页的全文搜索、标签筛选与分页。
 *
 * 设计约束（来自项目计划）：
 * - 纯原生实现，不引入 UI 框架；搜索索引由构建期的 Pagefind 生成。
 * - 不重复在构建期和运行期维护两套文章清单：列表数据直接来自页面已有的
 *   DOM（每个 <li> 上挂的 data-title / data-description / data-tags）。
 * - 初始 HTML 已完整渲染文章列表；本脚本只负责隐藏/显示，不依赖 JS 才能看到内容。
 * - 搜索、标签筛选与来源筛选统一使用 AND 组合。
 * - **全文检索走 Pagefind**：索引只收文章正文（`.prose` 上挂了 data-pagefind-body），
 *   本脚本拿到命中 URL 的集合后，用它去筛选 DOM 里已有的列表项——这样年份分组、
 *   标签 AND、分页、AI 滑块全都不用改，也不会出现「索引里有、列表里没有」的孤儿结果。
 * - `astro dev` 下没有索引文件，此时退回「标题 + 摘要 + 标签」的子串匹配，开发时不至于没得搜。
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
  /** 去掉首尾斜杠的路径，用来和 Pagefind 返回的 URL 对齐 */
  path: string;
  /** 命中时显示正文片段的容器 */
  excerptEl: HTMLElement | null;
}

/** 每页最多显示的笔记数量 */
const PAGE_SIZE = 10;

/** Pagefind 浏览器端入口（构建产物，`astro dev` 下不存在）。 */
const PAGEFIND_ENTRY = `${import.meta.env.BASE_URL}pagefind/pagefind.js`;

interface PagefindData {
  url: string;
  excerpt: string;
}

interface PagefindApi {
  options: (options: Record<string, unknown>) => Promise<void>;
  search: (term: string) => Promise<{ results: Array<{ data: () => Promise<PagefindData> }> }>;
}

/** 同一页面内只加载一次；加载失败也记住，避免每次输入都重试一次 404。 */
let pagefindPromise: Promise<PagefindApi | null> | null = null;

function loadPagefind(): Promise<PagefindApi | null> {
  if (pagefindPromise) return pagefindPromise;
  const entry = new URL(PAGEFIND_ENTRY, window.location.origin).href;
  pagefindPromise = import(/* @vite-ignore */ entry)
    .then(async (mod: PagefindApi) => {
      await mod.options({ excerptLength: 24 });
      return mod;
    })
    .catch(() => null);
  return pagefindPromise;
}

/** 统一成 `/blog/xxx` 这种无尾斜杠形式，两侧比较才可靠。 */
function normalizePath(input: string): string {
  const path = input.startsWith('http') ? new URL(input).pathname : input;
  return path.replace(/\/+$/, '');
}

/**
 * 把 Pagefind 返回的片段渲染进列表项。
 *
 * Pagefind 的片段自带 `<mark>`，但中文上它会标错：搜「声优」时把「优秀」也标了
 * （分词后按词边界回标，跨词的字会被误伤）。所以这里只取**纯文本**，
 * 高亮自己按字面重做——找不到原文关键词就只显示片段、不标任何东西，
 * 宁可少一个记号，也不要让读者看到「高亮的地方跟关键词无关」。
 */
function renderExcerpt(el: HTMLElement, html: string, term: string): void {
  const text = (new DOMParser().parseFromString(html, 'text/html').body.textContent ?? '')
    .replace(/\s+/g, ' ')
    .trim();
  el.replaceChildren();
  if (!text) return;

  const needle = term.trim().toLowerCase();
  if (!needle) {
    el.textContent = text;
    return;
  }

  const haystack = text.toLowerCase();
  let from = 0;
  let hit = haystack.indexOf(needle);
  while (hit !== -1) {
    if (hit > from) el.append(text.slice(from, hit));
    const mark = document.createElement('mark');
    mark.textContent = text.slice(hit, hit + needle.length);
    el.append(mark);
    from = hit + needle.length;
    hit = haystack.indexOf(needle, from);
  }
  if (from < text.length) el.append(text.slice(from));
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
  const tagButtons = Array.from(root.querySelectorAll<HTMLButtonElement>('[data-tag-filter]'));

  // 「含 AI 整理」滑块：默认不勾选，勾选后列表才包含 AI 整理的文章。
  const aiToggle = root.querySelector<HTMLInputElement>('[data-ai-toggle]');
  // 列表栏目名：默认「原创与转载」，开启滑块后切换为「全部（含 AI 整理）」。
  // 它在筛选器外层（列表自己的小标题），所以要从 document 上取，不能在 root 里找。
  const listHeading = document.querySelector<HTMLElement>('[data-archive-list-heading]');

  const paginationNav = root.querySelector<HTMLElement>('[data-archive-pagination]');
  const prevBtn = root.querySelector<HTMLButtonElement>('[data-page-prev]');
  const nextBtn = root.querySelector<HTMLButtonElement>('[data-page-next]');
  const numbersEl = root.querySelector<HTMLElement>('[data-page-numbers]');
  const pageInfoEl = root.querySelector<HTMLElement>('[data-page-info]');

  const emptyDefault = emptyEl?.textContent ?? '';

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
    const link = el.querySelector<HTMLAnchorElement>('a[href]');
    return {
      el,
      group: el.closest<HTMLElement>('.archive-group') ?? el,
      haystack: `${title} ${description} ${tagText}`,
      tags,
      source,
      path: normalizePath(link?.pathname ?? ''),
      excerptEl: el.querySelector<HTMLElement>('[data-excerpt]'),
    };
  });

  /**
   * Pagefind 的检索结果。`matchTerm` 是这份结果对应的关键词——
   * 用户改了关键词但索引还没回来时，两者不相等，此时宁可退回子串匹配，
   * 也不要拿旧结果去筛新关键词。
   */
  let matchSet: Set<string> | null = null;
  let matchTerm = '';
  let excerpts = new Map<string, string>();
  let searchSeq = 0;
  let debounceTimer = 0;

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
    const rawTerm = (input?.value ?? '').trim();
    const term = rawTerm.toLowerCase();
    const activeTags = tagButtons
      .filter((btn) => btn.getAttribute('aria-pressed') === 'true')
      .map((btn) => (btn.dataset.tag ?? '').toLowerCase());
    // 默认（滑块未勾选）不显示 AI 整理文章；勾选后才纳入。
    const aiOn = aiToggle?.checked ?? false;
    // 索引结果与当前关键词对得上才用，否则退回子串匹配。
    const indexed = matchSet !== null && matchTerm === rawTerm;

    const matchesText = (item: ArchiveItem): boolean => {
      if (rawTerm === '') return true;
      return indexed ? matchSet!.has(item.path) : item.haystack.includes(term);
    };

    // 1. 先算「是否匹配筛选」，并记录到 data-matched 上
    const matched: ArchiveItem[] = [];
    let aiOnlyHits = 0;
    for (const item of items) {
      const matchesSearch = matchesText(item);
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
        // 只差「AI 滑块」这一道：空结果时提示用户去勾一下
        if (!aiOn && item.source === 'ai' && matchesSearch && matchesTags) aiOnlyHits += 1;
      }

      // 2. 命中时补一段正文片段，让读者看到「为什么搜到这篇」
      if (item.excerptEl) {
        const snippet = isMatch && rawTerm !== '' && indexed ? excerpts.get(item.path) : '';
        if (snippet) {
          renderExcerpt(item.excerptEl, snippet, rawTerm);
          item.excerptEl.hidden = false;
        } else {
          item.excerptEl.textContent = '';
          item.excerptEl.hidden = true;
        }
      }
    }

    // 3. 分页作用于筛选结果集
    const totalPages = Math.max(1, Math.ceil(matched.length / PAGE_SIZE));
    if (currentPage > totalPages) currentPage = totalPages;
    const start = (currentPage - 1) * PAGE_SIZE;
    const end = start + PAGE_SIZE;

    // 4. 可见性 = 匹配筛选 且 落在当前页
    for (const item of items) {
      const isMatch = item.el.hasAttribute('data-matched');
      const index = isMatch ? matched.indexOf(item) : -1;
      const onPage = isMatch && index >= start && index < end;
      item.el.hidden = !onPage;
    }

    // 5. 没有可见文章的年份分组整体隐藏，避免留下空标题
    const groups = new Set(items.map((i) => i.group));
    for (const g of groups) {
      const anyVisible = items.some((i) => i.group === g && !i.el.hidden);
      g.hidden = !anyVisible;
    }

    // 6. 计数显示筛选结果总数（而非当前页数量）
    if (countEl) countEl.textContent = `共 ${matched.length} 篇`;
    if (emptyEl) {
      emptyEl.hidden = matched.length !== 0;
      emptyEl.textContent =
        matched.length === 0 && aiOnlyHits > 0
          ? `没有匹配的文章。另有 ${aiOnlyHits} 篇 AI 整理的命中，勾选「含 AI 整理」可查看。`
          : emptyDefault;
    }
    // 栏目名随滑块状态切换：默认「原创与转载」，开启后「全部（含 AI 整理）」。
    if (listHeading) {
      listHeading.textContent = aiOn ? '全部（含 AI 整理）' : '原创与转载';
    }

    // 7. 分页控件
    renderPagination(totalPages);

    // 8. 清除全部筛选按钮
    const hasActiveFilter = rawTerm !== '' || activeTags.length > 0 || aiOn;
    if (clearAll) clearAll.hidden = !hasActiveFilter;
  };

  /** 跑一次全文检索，拿到命中集合后重绘。失败时保持 `matchSet = null`（子串回退）。 */
  const refreshSearch = async (): Promise<void> => {
    const rawTerm = (input?.value ?? '').trim();
    const seq = ++searchSeq;

    if (rawTerm === '') {
      matchSet = null;
      matchTerm = '';
      excerpts = new Map();
      apply();
      return;
    }

    const pagefind = await loadPagefind();
    if (seq !== searchSeq) return;
    if (!pagefind) {
      matchSet = null;
      matchTerm = '';
      apply();
      return;
    }

    try {
      const search = await pagefind.search(rawTerm);
      if (seq !== searchSeq) return;
      const results = await Promise.all(search.results.map((result) => result.data()));
      if (seq !== searchSeq) return;
      matchSet = new Set(results.map((result) => normalizePath(result.url)));
      excerpts = new Map(results.map((result) => [normalizePath(result.url), result.excerpt]));
      matchTerm = rawTerm;
      apply();
    } catch {
      matchSet = null;
      matchTerm = '';
      apply();
    }
  };

  // 输入即检索（防抖 160ms：打字过程中不必每个字符都查一次索引）。
  // 中文输入法组字期间（还在打拼音）不发请求——那会儿输入框里是「shengyou」，
  // 查出来必然是 0 篇，等 compositionend 再查一次就够了。
  let composing = false;
  const scheduleSearch = (): void => {
    currentPage = 1;
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => void refreshSearch(), 160);
  };
  input?.addEventListener('compositionstart', () => {
    composing = true;
  });
  input?.addEventListener('compositionend', () => {
    composing = false;
    scheduleSearch();
  });
  input?.addEventListener('input', () => {
    if (composing) return;
    scheduleSearch();
  });

  // 提交按钮（语义化 / 键盘 Enter）不刷新页面
  form?.addEventListener('submit', (event) => {
    event.preventDefault();
    currentPage = 1;
    void refreshSearch();
  });

  // 清空搜索框
  clearSearch?.addEventListener('click', () => {
    if (input) {
      input.value = '';
      input.focus();
    }
    currentPage = 1;
    void refreshSearch();
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
    void refreshSearch();
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

  // 支持 /blog/?q=关键词 直接进来就带着结果（也方便无头浏览器验收）
  const initialQuery = new URLSearchParams(window.location.search).get('q');
  if (initialQuery && input) input.value = initialQuery;
  if (initialQuery) {
    void refreshSearch();
  } else {
    // 初始同步一次（无筛选时也应给出正确计数与分页）
    apply();
  }
}

// Astro 以 type="module" 引入本脚本，已处于 DOM 解析完成后执行，可直接初始化。
if (typeof document !== 'undefined') {
  initArchiveFilter();
}
