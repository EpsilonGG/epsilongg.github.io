"""M4 发布：`out/<期号>/report.json` → `data/daily/<期号>/report.json`。

M3 的正本在 `out/`（工作区，gitignore），站点读的是 `data/daily/`（要发布的东西）。
中间这一步以前不存在——M3 写完就没人把它搬到站点读的地方，于是「改了摘要但线上没变」
是必然的。这个模块就是那道门。

三条规矩：

* **只发定稿**。`status != confirmed` 直接拒绝。草稿进 `data/daily/` 就等于上线，
  而「上线」这个动作必须是人做过的（`confirm`），不能是流程的副作用。
* **默认不覆盖**。已经发布过的期号再发要显式 `--force`，否则「补一条摘要」会悄悄
  改掉一份可能已经被引用过的 JSON。
* **落盘前先过 schema**。发出去的 JSON 是站点的数据源，字段写错不该等到
  `npm run build` 才炸。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .schema import SchemaError, load_schema, validate

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEST = REPO_ROOT / "data" / "daily"


class PublishError(RuntimeError):
    pass


@dataclass
class Published:
    issue_id: str
    path: Path
    replaced: bool
    ja_path: Path | None = None


def publish(
    issue_id: str,
    *,
    out_dir: str | Path = "out",
    dest_root: str | Path = DEFAULT_DEST,
    force: bool = False,
) -> Published:
    source = paths.report(paths.workspace(out_dir, issue_id))
    if not source.exists():
        raise PublishError(f"还没有正本：{source}。先跑 `daily apply` 再 `daily confirm`。")

    report = json.loads(source.read_text(encoding="utf-8"))

    actual = str((report.get("issue") or {}).get("id") or "")
    if actual != issue_id:
        raise PublishError(f"正本里的期号是 {actual!r}，和 --issue {issue_id!r} 对不上")

    status = str((report.get("issue") or {}).get("status") or "")
    if status != "confirmed":
        raise PublishError(
            f"{issue_id} 还是 {status or '未定稿'} 状态，拒绝发布。定稿用 `daily confirm --issue {issue_id}`。"
        )

    try:
        validate(report, load_schema("report"))
    except SchemaError as exc:
        raise PublishError(f"正本不合法，未发布：{exc}") from None

    target = Path(dest_root) / issue_id / "report.json"
    replaced = target.exists()
    if replaced and not force:
        raise PublishError(f"{target} 已存在。确认要覆盖就加 --force。")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    # Ci-en 版是可选产物，但**有就一起发**：只发正本不发日文版，等于当天悄悄少了
    # 一个出口，而 `data/daily/` 里少一个文件是没人会注意到的。
    ja_source = paths.ja_report(source.parent)
    ja_target: Path | None = None
    if ja_source.exists():
        ja_target = target.parent / "report.ja.json"
        ja_target.write_text(
            ja_source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
        )

    return Published(issue_id, target, replaced, ja_target)
