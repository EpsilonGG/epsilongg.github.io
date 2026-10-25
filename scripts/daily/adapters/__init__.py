"""源适配器。一个源一个文件，加源不改主流程。"""
from __future__ import annotations

from .base import SourceAdapter
from .fixture import FixtureAdapter
from .xreader import XReaderAdapter, item_from_raw, load_raw

__all__ = ["SourceAdapter", "FixtureAdapter", "XReaderAdapter", "item_from_raw", "load_raw"]
