"""M3 工作区路径（`out/<期号>/`）。

M2 的产物是扁平的两个文件：`out/<期号>.briefing.txt` 与 `out/<期号>.generate.json`。
M3 要在旁边长出一整个目录（题、答、正本、历史、缓存），所以集中在这里定义，
别让 `prompt.py` / `apply.py` / `confirm.py` 各写一份 `out / id / "answer"`。
"""
from __future__ import annotations

from pathlib import Path


def workspace(out_dir: str | Path, issue_id: str) -> Path:
    return Path(out_dir) / issue_id


def prompts(ws: Path) -> Path:
    return ws / "prompt"


def answers(ws: Path) -> Path:
    return ws / "answer"


def report(ws: Path) -> Path:
    return ws / "report.json"


def history(ws: Path) -> Path:
    return ws / "history"


def cache(ws: Path) -> Path:
    return ws / "cache.json"


def ensure(ws: Path) -> Path:
    for path in (prompts(ws), answers(ws), history(ws)):
        path.mkdir(parents=True, exist_ok=True)
    return ws
