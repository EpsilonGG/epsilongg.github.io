"""增量分类（M2.3）：把每一条归到一个可解释的类别里。

「增量」不是「只要新的」。一条推可能有五种身份，每种进不进今天的日报都不一样：

  * **new**       在窗口内，`key` 未见过            → 进
  * **duplicate** 在窗口内，`key` 已见过且 hash 未变 → 不进（计入 `skipped_duplicate`）
  * **updated**   在窗口内，`key` 已见过但 hash 变了 → 进（覆盖旧版本）
  * **late**      早于窗口起点，但**第一次**见到     → 不进当天，进 `late[]`
  * **future**    晚于窗口终点（时钟偏差/时区写错）   → 不进，进 `future[]` 隔离

「迟到」和「旧内容」的区别只有 `first_seen`：一条 10-01 的推，10-01 就抓到了，
它属于 10-01 那一期，今天重跑判 duplicate；10-25 才第一次抓到，那是**迟到数据**，
塞进 10-25 的日报会让读者以为今天发生了旧事。正确做法是记进 `late[]`，
由人决定要不要补一期历史——脚本不替人做这个决定。

判定用 `State.seen` 而不是条目自己的 `first_seen`：`seen` 是「我们处理过什么」的账本，
条目里的 `first_seen` 只是抓取方给的时间戳，两者不一致时以账本为准。
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Item
from .window import IMPRECISE, IssueWindow

NEW = "new"
DUPLICATE = "duplicate"
UPDATED = "updated"
LATE = "late"
FUTURE = "future"

STATES = (NEW, DUPLICATE, UPDATED, LATE, FUTURE)


@dataclass(frozen=True)
class Classification:
    """一次分类的结果。五个桶互不重叠，加起来等于输入。"""

    window: IssueWindow
    items: tuple[Item, ...] = ()      # new + updated，进日报
    updated: tuple[Item, ...] = ()
    duplicate: tuple[Item, ...] = ()
    late: tuple[Item, ...] = ()
    future: tuple[Item, ...] = ()

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def buckets(self) -> dict[str, tuple[Item, ...]]:
        updated_keys = {i.key for i in self.updated}
        return {
            NEW: tuple(i for i in self.items if i.key not in updated_keys),
            UPDATED: self.updated,
            DUPLICATE: self.duplicate,
            LATE: self.late,
            FUTURE: self.future,
        }

    def counts(self, accounts: int = 0) -> dict:
        return {
            "items": len(self.items),
            "accounts": accounts,
            "late": len(self.late),
            "skipped_duplicate": len(self.duplicate),
        }


def state_of(item: Item, seen: dict) -> str:
    """单条判定。`seen` 是 `State.seen`。"""
    rec = seen.get(item.key)
    if rec is None:
        return NEW
    if rec.get("content_hash") and rec["content_hash"] != item.hash():
        return UPDATED
    return DUPLICATE


def classify(items, window: IssueWindow, seen: dict | None = None) -> Classification:
    """按窗口与账本分类。窗口外的条目不参与 new/duplicate 判定。"""
    seen = seen or {}
    inside: list[Item] = []
    updated: list[Item] = []
    dup: list[Item] = []
    late: list[Item] = []
    future: list[Item] = []

    for item in items:
        moment = item.published_dt()
        if moment is None:
            # 没有时间戳的条目不进任何一期（调用方用 `window.select` 另行告警）
            continue
        if item.precision in IMPRECISE:
            # 只知道哪一天：用窗口自己的规则判定，规则只写一处
            if window.select([item]).unsure:
                inside.append(item)
            continue
        if moment < window.start:
            # 窗口之前：见过就是「过去某期已经处理过的旧内容」，静默略过——
            # 它不是今天的重复项，计进 skipped_duplicate 会让数字变成「全部历史」。
            # 没见过才是迟到数据，记下来由人决定补不补。
            if item.key not in seen:
                late.append(item)
            continue
        if moment >= window.end:
            future.append(item)
            continue
        verdict = state_of(item, seen)
        if verdict == NEW:
            inside.append(item)
        elif verdict == UPDATED:
            inside.append(item)
            updated.append(item)
        else:
            dup.append(item)

    return Classification(
        window=window,
        items=tuple(inside),
        updated=tuple(updated),
        duplicate=tuple(dup),
        late=tuple(late),
        future=tuple(future),
    )


def commit(state, classification: Classification, issue_id: str, published_at: str) -> None:
    """把这一期记进账本：条目与迟到项都算「处理过」，issue 记下用到的 key。

    `seen_at` 用期号的发布时间而不是当前时刻——账本因此与运行时间无关，
    同一批数据重跑两次，`state.json` 逐字节相同。
    """
    for item in classification.items:
        state.mark_seen(
            item.key, first_seen=item.first_seen, content_hash=item.hash(), seen_at=published_at
        )
    for item in classification.late:
        state.mark_seen(
            item.key, first_seen=item.first_seen, content_hash=item.hash(), seen_at=published_at
        )
    state.record_issue(
        issue_id,
        published_at,
        [item.key for item in classification.items],
        status="draft",
    )
