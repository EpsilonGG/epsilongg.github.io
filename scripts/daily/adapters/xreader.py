"""X-Reader 适配器（M1.3）。

输入是 X-Reader 产出的 `NormalizedItem` JSONL（`data/items/*.jsonl`）。
这个文件是**唯一**知道 X-Reader 字段名的地方——它改字段只改这里。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator

from ..model import Item
from .base import SourceAdapter


class XReaderAdapter(SourceAdapter):
    name = "x"

    def __init__(self, items_dir: str | Path) -> None:
        self.items_dir = Path(items_dir)

    # -- 契约 ----------------------------------------------------------
    def paths(self) -> list[Path]:
        if not self.items_dir.exists():
            return []
        # 排序保证不同机器上的顺序一致（glob 的返回顺序不保证）
        return sorted(self.items_dir.glob("*.jsonl"), key=lambda p: p.name)

    def fingerprint(self) -> str:
        """文件名 + 内容的 sha256。不看 mtime——跨机器要能对上。"""
        h = hashlib.sha256()
        for path in self.paths():
            h.update(path.name.encode("utf-8"))
            h.update(b"\0")
            h.update(path.read_bytes())
            h.update(b"\0")
        return "sha256:" + h.hexdigest()

    def iter_items(self) -> Iterator[Item]:
        for path in self.paths():
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if raw.get("is_meaningful") is False:
                    continue
                yield item_from_raw(raw, raw_ref=f"{path.name}#{lineno}")


def item_from_raw(raw: dict, raw_ref: str = "") -> Item:
    """把一条 X-Reader 原始记录变成 `Item`。测试与薄壳都走这里。"""
    return Item.from_xreader(raw, raw_ref=raw_ref)


def load_raw(items_dir: str | Path) -> list[dict]:
    """兼容旧接口：返回原始 dict 列表（`_load_items` 的语义）。"""
    return [it.raw for it in XReaderAdapter(items_dir).iter_items()]
