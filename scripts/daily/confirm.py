"""M3.5 定稿：`confirm` / `--reopen`，旧版本进 `history/`。

定稿是一个**人**的动作，不是流程的副作用。它的意义只有一个：
从这一刻起，`apply` 不再能改这份正本。所以定稿前先把当前版本存进历史，
定稿后想改必须先 `reopen`——两道门，为的是「重新生成不会覆盖已经确认的版本」。
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import paths


class ConfirmError(RuntimeError):
    pass


def _snapshot(ws: Path, report: dict, reason: str, now: datetime) -> Path:
    paths.history(ws).mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%S")
    status = str((report.get("issue") or {}).get("status") or "draft")
    target = paths.history(ws) / f"report-{stamp}-{status}-{reason}.json"
    shutil.copyfile(paths.report(ws), target)
    return target


def _read(ws: Path) -> dict:
    path = paths.report(ws)
    if not path.exists():
        raise ConfirmError(f"还没有正本：{path}。先跑 `daily apply`。")
    return json.loads(path.read_text(encoding="utf-8"))


def _write(ws: Path, report: dict) -> None:
    paths.report(ws).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def confirm(issue_id: str, out_dir: str | Path = "out", *, now: datetime | None = None) -> tuple[dict, Path]:
    ws = paths.workspace(out_dir, issue_id)
    report = _read(ws)
    moment = now or datetime.now(timezone.utc)

    if (report.get("issue") or {}).get("status") == "confirmed":
        raise ConfirmError("这一期已经定稿了。要改先 `daily confirm --reopen`。")

    saved = _snapshot(ws, report, "confirm", moment)
    report["issue"]["status"] = "confirmed"
    report["issue"]["confirmed_at"] = moment.isoformat(timespec="seconds")
    _write(ws, report)
    return report, saved


def reopen(issue_id: str, out_dir: str | Path = "out", *, now: datetime | None = None) -> tuple[dict, Path]:
    ws = paths.workspace(out_dir, issue_id)
    report = _read(ws)
    moment = now or datetime.now(timezone.utc)

    if (report.get("issue") or {}).get("status") != "confirmed":
        raise ConfirmError("这一期还没定稿，不需要 reopen。")

    saved = _snapshot(ws, report, "reopen", moment)
    report["issue"]["status"] = "draft"
    report["issue"]["confirmed_at"] = None
    _write(ws, report)
    return report, saved
