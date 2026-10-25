"""增量状态（M1.5）。

回答一个问题：**「这条上次是不是已经用过了」**。

`seen` 只保留 90 天——再久的条目不会再出现在窗口里，留着只是让 git diff 变噪音。
整个 `seen` 都能从 `issues` 重建，所以它丢了也不致命（`rebuild()`）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import SCHEMA_VERSION
from .migrate import check
from .model import parse_dt


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class State:
    schema_version: int = SCHEMA_VERSION
    # [{id, published_at, status, item_keys: [...]}]
    issues: list[dict] = field(default_factory=list)
    # key -> {first_seen, last_seen, content_hash}
    seen: dict[str, dict] = field(default_factory=dict)

    # -- 读写 ----------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "State":
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        check(data)  # 读到更高的主版本直接报错，不猜着读
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            issues=list(data.get("issues") or []),
            seen=dict(data.get("seen") or {}),
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "issues": list(self.issues),
            "seen": dict(self.seen),
        }

    # -- 写入 ----------------------------------------------------------
    def record_issue(
        self,
        issue_id: str,
        published_at: str,
        item_keys: list[str],
        status: str = "draft",
    ) -> dict:
        rec = {
            "id": issue_id,
            "published_at": published_at,
            "status": status,
            "item_keys": list(item_keys),
        }
        self.issues = [i for i in self.issues if i.get("id") != issue_id]
        self.issues.append(rec)
        self.issues.sort(key=lambda i: i.get("published_at") or "")
        return rec

    def mark_seen(
        self,
        key: str,
        first_seen: str = "",
        content_hash: str = "",
        seen_at: str = "",
    ) -> None:
        """记一条「处理过」。`seen_at` 传期号的发布时间，账本就与运行时刻无关了——
        否则每跑一次 `last_seen` 都变，git diff 全是噪音。"""
        stamp = seen_at or _now().isoformat()
        rec = self.seen.get(key) or {"first_seen": first_seen or stamp}
        rec["last_seen"] = stamp
        if content_hash:
            rec["content_hash"] = content_hash
        self.seen[key] = rec

    # -- 维护 ----------------------------------------------------------
    def prune(self, days: int = 90, now: datetime | None = None) -> int:
        """裁掉 `last_seen` 早于 `days` 天的条目，返回裁掉的条数。"""
        moment = now or _now()
        cutoff = moment - timedelta(days=days)
        drop = []
        for key, rec in self.seen.items():
            last = parse_dt(rec.get("last_seen") or rec.get("first_seen"))
            if last is not None and last < cutoff:
                drop.append(key)
        for key in drop:
            del self.seen[key]
        return len(drop)

    def rebuild(self, content_hashes: dict[str, str] | None = None) -> int:
        """从 `issues` 重建 `seen`。返回重建出的条数。"""
        hashes = content_hashes or {}
        seen: dict[str, dict] = {}
        for issue in self.issues:
            published = issue.get("published_at") or ""
            for key in issue.get("item_keys") or []:
                rec = seen.setdefault(key, {"first_seen": published})
                rec["last_seen"] = published
                if key in hashes:
                    rec["content_hash"] = hashes[key]
        self.seen = seen
        return len(seen)
