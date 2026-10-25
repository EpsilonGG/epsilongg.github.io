"""fixture 适配器（M1.3）：读一份 JSON / JSONL 样例，供测试与离线演练。

它不是「假数据源」——CI 里跑的就是它，所以它必须和真适配器过同一套契约测试。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator

from ..model import Item
from .base import SourceAdapter
from .xreader import item_from_raw


class FixtureAdapter(SourceAdapter):
    name = "fixture"

    def __init__(self, path: str | Path, source: str = "fixture") -> None:
        self.path = Path(path)
        self.source = source

    def _records(self) -> list[dict]:
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8")
        if self.path.suffix == ".jsonl":
            return [json.loads(l) for l in text.splitlines() if l.strip()]
        data = json.loads(text)
        return data if isinstance(data, list) else [data]

    def fingerprint(self) -> str:
        if not self.path.exists():
            return "sha256:" + hashlib.sha256(b"").hexdigest()
        return "sha256:" + hashlib.sha256(self.path.read_bytes()).hexdigest()

    def iter_items(self) -> Iterator[Item]:
        for i, raw in enumerate(self._records(), 1):
            item = item_from_raw(raw, raw_ref=f"{self.path.name}#{i}")
            item.source = self.source
            item.key = f"{self.source}:{item.native_id}"
            yield item
