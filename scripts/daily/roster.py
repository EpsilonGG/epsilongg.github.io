"""名单与分类（M2.5）。

名单是**数据**，不是代码：`src/config/daily-roster.json`。结构由协议定（M2.5），
内容由人填。这里只负责读、查、排序，以及**把没登记的 handle 归到 `other` 并告警**。

三条规则：

* `active: false` 暂停某人，但**历史日报不动**——名单只影响以后怎么分组，不重写过去。
* 一个人只给一个 `category`。跨类用 `tags` 补充：多分类会让综合视图重复计数。
* 名单顺序即显示顺序。所以「谁先谁后」是编辑决定，不是脚本按条数算出来的。

**未知 handle 不丢弃、不报错**，归 `other` 并在 stderr 告警一行——
数据里出现名单外的人是正常现象（转发、新账号、写错 handle），
静默丢弃会让日报少一个人且没人发现。
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .model import Account

OTHER = "other"
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "src" / "config" / "daily-roster.json"


@dataclass
class Roster:
    categories: list[dict] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)

    # -- 读 ------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Roster":
        p = Path(path) if path else DEFAULT_PATH
        if not p.exists():
            return cls(categories=[{"id": OTHER, "label": "未归类"}], accounts=[])
        data = json.loads(p.read_text(encoding="utf-8"))
        categories = [
            {"id": str(c.get("id") or OTHER), "label": str(c.get("label") or c.get("id") or OTHER)}
            for c in data.get("categories") or []
        ]
        if not any(c["id"] == OTHER for c in categories):
            categories.append({"id": OTHER, "label": "未归类"})
        accounts = [
            Account(
                handle=str(a.get("handle") or "").strip(),
                name=str(a.get("name") or ""),
                category=str(a.get("category") or OTHER),
                active=bool(a.get("active", True)),
                tags=list(a.get("tags") or []),
            )
            for a in data.get("accounts") or []
            if str(a.get("handle") or "").strip()
        ]
        return cls(categories=categories, accounts=accounts)

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
