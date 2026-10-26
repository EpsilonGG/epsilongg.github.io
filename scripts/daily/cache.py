"""M3.6 重跑缓存：输入没变就别重算，变了只标 stale，不自动覆盖。

为什么要这层：日报每天都要出，但**同一天重跑**很常见（补人、改名单、重试）。
没有缓存就只能靠人记住「这期已经确认过了」，一不小心就把定稿覆盖成草稿。

三条规则：

* `input_hash` 只吃「喂给模型的材料」——条目 key 与正文，按 key 排序。
  时间戳、抓取批次都不进 hash，否则同样的内容换个抓取时刻就判成变了。
* hash 与 `prompt_version` 都没变 → `fresh`，不重写题面、不动正本。
* hash 变了 → `stale`：题面重写（材料确实变了），但**正本不动**，
  等 `apply` 时由人决定要不要覆盖。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROMPT_VERSION = 1

FRESH = "fresh"
STALE = "stale"
MISS = "miss"


def input_hash(items: list[dict]) -> str:
    """材料指纹。只吃 key + text，且按 key 排序——与抓取顺序、时间戳无关。"""
    digest = hashlib.sha256()
    for item in sorted(items, key=lambda i: str(i.get("key") or "")):
        digest.update(str(item.get("key") or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item.get("text") or "").encode("utf-8"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


@dataclass
class Entry:
    category: str
    input_hash: str
    prompt_version: int = PROMPT_VERSION
    written_at: str = ""
    stale: bool = False

    def matches(self, digest: str) -> bool:
        return self.input_hash == digest and self.prompt_version == PROMPT_VERSION


@dataclass
class PromptCache:
    path: Path
    entries: dict[str, Entry] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "PromptCache":
        if not path.exists():
            return cls(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls(path=path)
        entries = {
            str(k): Entry(**v) for k, v in (data.get("entries") or {}).items() if isinstance(v, dict)
        }
        return cls(path=path, entries=entries)

    def save(self) -> None:
        payload = {"prompt_version": PROMPT_VERSION, "entries": {k: asdict(v) for k, v in self.entries.items()}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # -- 查 ------------------------------------------------------------
    def check(self, category: str, digest: str) -> str:
        entry = self.entries.get(category)
        if entry is None:
            return MISS
        return FRESH if entry.matches(digest) else STALE

    def record(self, category: str, digest: str, *, stale: bool = False) -> Entry:
        entry = Entry(
            category=category,
            input_hash=digest,
            written_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            stale=stale,
        )
        self.entries[category] = entry
        return entry
