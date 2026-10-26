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
        # 坏行位置（`文件名#行号`）。**不要静默跳过**——2026-10-26 查出来
        # `splitlines()` 会把 U+2028 当换行，一条合法记录被劈成两半后
        # 两边都解析失败，于是推文从每一期里凭空消失，而构建一声不响。
        self.malformed: list[str] = []

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
        """逐行读。**必须按文件迭代，不能用 `read_text().splitlines()`。**

        `str.splitlines()` 认的换行符不止 `\\n`：U+2028、U+2029、U+0085、U+000B、
        U+000C 都算。而 `json.dumps(ensure_ascii=False)` 不会转义 U+2028——
        于是「正文里带一个行分隔符」的合法记录会被劈成两半，两半都解析失败、
        都被当成坏行跳过。真实数据里 x.jsonl 有 2 条记录共 12 个 U+2028，
        旧读法把它们拆成 12 个碎片、丢掉 2 条（`splitlines()` 2423 行 vs 实际 2411 条）。
        文件迭代用的是 universal newlines（只认 `\\r`、`\\n`、`\\r\\n`），不受影响。
        """
        self.malformed = []
        for path in self.paths():
            with path.open("r", encoding="utf-8") as handle:
                for lineno, line in enumerate(handle, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        self.malformed.append(f"{path.name}#{lineno}")
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
