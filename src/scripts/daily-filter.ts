/**
 * 日报「详细」栏的栏目筛选。
 *
 * 为什么默认只看一个栏目：声优一天几十条，社团、厂商、信息号是零到几条。混在一列里，
 * 那几个人的话会被埋在中间，谁都不会读到——而它恰恰是「今天有哪个社/厂说话」的唯一线索。
 * 默认亮哪个由**版**决定：声优版亮「声优」，Galgame 版亮「游戏制造商」。
 *
 * 交互是**多选**，不是单选：
 *   默认 声优亮 → 点音声社团（两个都亮，列表 = 声优 + 社团）
 *   → 再点声优（只剩社团亮，列表 = 社团）
 * 「只看社团」不用先全清再选，少一次点击。
 *
 * 状态不进 URL、不进 localStorage：日报是一期一页，没有值得分享的筛选组合，
 * 存下来反而会让「我上次关了声优」变成下次的困惑。
 *
 * 和笔记页的标签筛选是同一套语义（`aria-pressed` 表达选中），样式也共用。
 */

const root = document.querySelector<HTMLElement>('[data-daily-filter]');
const list = document.querySelector<HTMLElement>('[data-daily-roster]');
const emptyHint = document.querySelector<HTMLElement>('[data-daily-filter-empty]');

if (root && list) {
  const buttons = [...root.querySelectorAll<HTMLButtonElement>('[data-category-filter]')];
  const items = [...list.querySelectorAll<HTMLElement>('[data-category]')];

  const apply = (): void => {
    const active = new Set(
      buttons
        .filter((button) => button.getAttribute('aria-pressed') === 'true')
        .map((button) => button.dataset.category ?? '')
    );

    let shown = 0;
    for (const item of items) {
      const match = active.has(item.dataset.category ?? '');
      // 用 hidden 而不是 class：屏幕阅读器也会跟着跳过，不只是看不见
      item.hidden = !match;
      if (match) shown += 1;
    }

    if (emptyHint) emptyHint.hidden = shown > 0;
  };

  for (const button of buttons) {
    button.addEventListener('click', () => {
      const pressed = button.getAttribute('aria-pressed') === 'true';
      button.setAttribute('aria-pressed', pressed ? 'false' : 'true');
      apply();
    });
  }

  apply();
}
