"""源适配器接口（M1.3）。

换数据源只加一个文件，不改主流程。每个适配器都要过同一套契约测试
（`tests/test_daily_adapters.py`），契约只有三条：

  * `name`          稳定的源名，进 `Item.key` 的前缀
  * `fingerprint()` 输入指纹，用来判断「这批数据变没变」
  * `iter_items()`  产出 `Item`，顺序稳定（同一份输入两次跑出同一个顺序）

适配器**不做筛选**：`is_meaningful: false` 这种过滤属于「这条算不算内容」，
由适配器自己决定并在文档里写清楚（X-Reader 适配器沿用现有行为：跳过）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from ..model import Item


class SourceAdapter(ABC):
    """所有源的统一入口。"""

    name: str = "base"

    @abstractmethod
    def fingerprint(self) -> str:
        """输入指纹（sha256 前缀即可）。同一份输入必须给出同一个值。"""

    @abstractmethod
    def iter_items(self) -> Iterator[Item]:
        """按稳定顺序产出条目。"""
