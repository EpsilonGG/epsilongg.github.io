"""名单与分类（M2.5 / 2026-10-29 拆版）。

名单是**数据**，不是代码。2026-10-29 起一天出两份日报，所以名单也拆成两份：

    src/config/daily-roster.json          声优版（category: seiyuu / circle）
    src/config/daily-roster-galgame.json  Galgame 版（category: manufacturer / info）

`kind`（`voice` / `galgame`）是**版**，决定用哪份名单、哪几个栏目、期号带不带 `-g`。
它和 `category`（栏目）不是一回事：栏目决定条目落在页面上哪个按钮下。

加载时会把**另一份名单的账号也并进来**（排在后面），只用于「这个人叫什么、在不在名单里」。
理由：历史期号（`261025`–`261028`）是合并名单时代的产物，`people` 里有制造商，
如果只读声优版，那些旧页面上的人名会全部退回裸 `@handle`。合并只影响查询，
不影响分组——分组只看本版名单的 `categories`。

三条规则不变：

* `active: false` 暂停某人，但**历史日报不动**——名单只影响以后怎么分组，不重写过去。
* 一个人只给一个 `category`。跨类用 `tags` 补充：多分类会让综合视图重复计数。
* 名单顺序即显示顺序。所以「谁先谁后」是编辑决定，不是脚本按条数算出来的。
  `role`（main/sub/announce/circle/brand/info/other）只是给人看的元数据，脚本不据此过滤。

**未知 handle 不丢弃、不报错**，归 `other` 并在 stderr 告警一行——
数据里出现名单外的人是正常现象（转发、新账号、写错 handle），
静默丢弃会让日报少一个人且没人发现。
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .issue import GALGAME, VOICE
from .model import Account

OTHER = "other"
CONFIG_DIR = Path(__file__).resolve().parents[2] / "src" / "config"

# 版 → 名单文件。`--roster` 可以覆盖本版那一份，另一份仍按这里找。
DEFAULT_PATHS = {
    VOICE: CONFIG_DIR / "daily-roster.json",
    GALGAME: CONFIG_DIR / "daily-roster-galgame.json",
}
DEFAULT_PATH = DEFAULT_PATHS[VOICE]


@dataclass
class Roster:
    categories: list[dict] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    # 账号级降噪规则，`{handle(小写): 原始 dict}`。原样带着不解析：
    # 解析与报错在 `filter.py` 里，名单只管「谁有什么规则」。
    filters: dict[str, dict] = field(default_factory=dict)
    # 本版的栏目 id（不含 other）。用来判断「这条属于另一版」。
    kind: str = VOICE
    category_ids: list[str] = field(default_factory=list)

    # -- 读 ------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path | None = None, kind: str = VOICE) -> "Roster":
        if kind not in DEFAULT_PATHS:
            raise ValueError(f"名单类型只能是 {'/'.join(DEFAULT_PATHS)}，收到 {kind!r}")
        primary = Path(path) if path else DEFAULT_PATHS[kind]
        secondary = [
            p for k, p in DEFAULT_PATHS.items() if k != kind and p != primary
        ]

        categories: list[dict] = []
        accounts: list[Account] = []
        filters: dict[str, dict] = {}
        seen: set[str] = set()

        for index, p in enumerate([primary, *secondary]):
            if not p.exists():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            if index == 0:
                categories = [
                    {
                        "id": str(c.get("id") or OTHER),
                        "label": str(c.get("label") or c.get("id") or OTHER),
                    }
                    for c in data.get("categories") or []
                ]
            for a in data.get("accounts") or []:
                handle = str(a.get("handle") or "").strip()
                if not handle or handle.lower() in seen:
                    continue
                seen.add(handle.lower())
                accounts.append(
                    Account(
                        handle=handle,
                        name=str(a.get("name") or ""),
                        category=str(a.get("category") or OTHER),
                        active=bool(a.get("active", True)),
                        tags=list(a.get("tags") or []),
                        role=str(a.get("role") or "main"),
                    )
                )
                if isinstance(a.get("filter"), dict):
                    filters[handle.lower()] = a["filter"]

        if not categories:
            categories = [{"id": OTHER, "label": "未归类"}]
        if not any(c["id"] == OTHER for c in categories):
            categories.append({"id": OTHER, "label": "未归类"})

        return cls(
            categories=categories,
            accounts=accounts,
            filters=filters,
            kind=kind,
            category_ids=[c["id"] for c in categories if c["id"] != OTHER],
        )

    # -- 查 ------------------------------------------------------------
    @property
    def index(self) -> dict[str, int]:
        return {a.handle: i for i, a in enumerate(self.accounts)}

    def index_of(self, handle: str) -> int:
        """名单序；不在名单里的排最后（`len(accounts)`）。"""
        return self.index.get(handle, len(self.accounts))

    def is_known(self, handle: str) -> bool:
        return handle in self.index

    def account(self, handle: str) -> Account | None:
        i = self.index.get(handle)
        return self.accounts[i] if i is not None else None

    def category_of(self, handle: str) -> str:
        acct = self.account(handle)
        return acct.category if acct else OTHER

    def is_active(self, handle: str) -> bool:
        acct = self.account(handle)
        return acct.active if acct else True

    def belongs_to_kind(self, handle: str) -> bool:
        """这个号是不是本版的（名单外的号算「是」，由未知 handle 的告警单独处理）。

        手工构造的 `Roster`（测试里常见）没有 `category_ids`，这时一律算「是」——
        否则一个空栏目表会把所有条目都判成「另一版」。
        """
        acct = self.account(handle)
        if acct is None or not self.category_ids:
            return True
        return acct.category in self.category_ids or acct.category == OTHER

    def label_of(self, category_id: str) -> str:
        for c in self.categories:
            if c["id"] == category_id:
                return str(c["label"])
        return category_id

    def unknown(self, handles) -> list[str]:
        return sorted({h for h in handles if h and not self.is_known(h)})

    # -- 告警 ----------------------------------------------------------
    def warn_unknown(self, handles, stream=None) -> list[str]:
        """未知 handle 归 other 并在 stderr 告警一行。返回未知列表，方便测试。"""
        missing = self.unknown(handles)
        if missing:
            out = stream or sys.stderr
            print(
                f"注意：{len(missing)} 个 handle 不在名单里，已归入 {OTHER}："
                + "、".join(missing),
                file=out,
            )
        return missing
