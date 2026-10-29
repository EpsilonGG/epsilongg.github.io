"""M4.1 迁移：`src/content/daily/<期号>.md` → `data/daily/<期号>/report.json`。

> **这个工具已经冻结**。它只认 M4 之前的八位期号（`26102322`），而现在的期号是
> `YYMMDD`（`261023`，同日第二期 `261023-2`）——再跑它会产出不合规的期号。
> 归档在 M4 就迁完了，留着是为了「当年怎么迁的」有据可查，不是给现在用的。

M4 之前站点读 Markdown frontmatter，M4 之后读 JSON。这个脚本是那次换血的一次性工具，
但它要满足两个长期要求，所以没有写成「读一遍、打一份」的临时脚本：

* **`--check` 只读**。同一份 Markdown 跑两次必须得到同一份 JSON（连 `generated_at`
  都取发布时刻而不是当前时间），否则「迁移有没有改内容」就说不清，金文件比对也失去意义。
* **`--write` 才落盘**。先跑 `--check` 看差异，确认无误再写。

字段映射（只搬，不改写）：

    description          → description
    highlights: [str]    → highlights: [{text, sources: []}]
    works: str           → works
    interactions: [str]  → interactions: [{text, sources: []}]
    people: [{handle, summary, via}]
                         → people: [{handle, summary, via, category: "", sources: []}]
    accounts: [str]      → accounts（保留：正文里的 @提及 靠它变成链接）
    source: ai           → 丢弃（整栏都是 AI，页面固定挂「AI 整理」标记）

`title` / `pubDate` 本来就不在 frontmatter 里，由期号推导；这里把推导结果写进
`issue.published_at`，让 JSON 自身能说清「这是哪一刻的一期」。

**为什么 `generated_at` 取发布时刻**：`--check` 要比对整份 JSON，任何「当前时间」
都会让每次比对都有差异。取发布时刻是唯一的确定值，也让 provenance 至少有个时间锚点。

用法：

    cd scripts && python -m daily migrate --check
    cd scripts && python -m daily migrate --write
    cd scripts && python -m daily migrate --write --id 26102322

依赖 PyYAML（只在解析 frontmatter 时用到）。系统 Python 没装就换
`C:/Users/lenovo/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe`。
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .issue import JST
from .window import IssueWindow

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "src" / "content" / "daily"
DEFAULT_DEST = REPO_ROOT / "data" / "daily"


class MigrateError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# frontmatter
# --------------------------------------------------------------------------
def split_frontmatter(text: str) -> str:
    """取出两行 `---` 之间的 YAML。没有 frontmatter 直接报错——日报不可能没有。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise MigrateError("文件开头不是 `---`，没有 frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index])
    raise MigrateError("frontmatter 没有闭合的 `---`")


def load_meta(path: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415  —— 只有这个工具需要，别让全包依赖它
    except ModuleNotFoundError:  # pragma: no cover - 环境问题，不是逻辑分支
        raise MigrateError(
            "需要 PyYAML。系统 Python 里没装，换用 "
            "C:/Users/lenovo/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe"
        ) from None

    meta = yaml.safe_load(split_frontmatter(path.read_text(encoding="utf-8"))) or {}
    if not isinstance(meta, dict):
        raise MigrateError(f"{path.name} 的 frontmatter 不是映射")
    return meta


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------
def _issue_moment(issue_id: str):
    """`26102322` → 2026-10-23 22:00+09:00。非法期号直接报错，别猜。"""
    from datetime import datetime  # noqa: PLC0415

    if len(issue_id) != 8 or not issue_id.isdigit():
        raise MigrateError(f"期号 {issue_id!r} 不是 YYMMDDHH")
    try:
        return datetime.strptime(issue_id, "%y%m%d%H").replace(tzinfo=JST)
    except ValueError:
        raise MigrateError(f"期号 {issue_id!r} 不是一个真实存在的时刻") from None


def _claim(value) -> dict:
    """字符串 → `{text, sources: []}`；已经是字典就补齐两个键。"""
    if isinstance(value, str):
        return {"text": value.strip(), "sources": []}
    if isinstance(value, dict):
        text = str(value.get("text") or "").strip()
        sources = [str(s) for s in (value.get("sources") or [])]
        return {"text": text, "sources": sources}
    raise MigrateError(f"claims 里出现了 {type(value).__name__}，只认字符串或 {{text, sources}}")


def _claims(value) -> list[dict]:
    return [_claim(item) for item in (value or [])]


def _works(value) -> list[str]:
    """老简报里的 `works` 是一段话，正本要的是「一条一个作品」。

    按句末标点切开（确定性切法，`--check` 才能逐字节比），数组原样收。
    """
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    parts = [p.strip() for p in re.split(r"(?<=[。！？])", str(value).strip())]
    return [p for p in parts if p]


def _people(value) -> list[dict]:
    people: list[dict] = []
    for entry in value or []:
        if not isinstance(entry, dict):
            raise MigrateError(f"people 里出现了 {type(entry).__name__}，只认映射")
        handle = str(entry.get("handle") or "").strip()
        if not handle:
            continue
        via = [str(v).strip() for v in (entry.get("via") or []) if str(v).strip()]
        people.append(
            {
                "handle": handle,
                "category": str(entry.get("category") or ""),
                "summary": str(entry.get("summary") or "").strip(),
                "via": via,
                "sources": [str(s) for s in (entry.get("sources") or [])],
            }
        )
    return people


def report_from_meta(meta: dict, issue_id: str) -> dict:
    """把一份 frontmatter 映射成 `report.json`。纯函数，不碰磁盘。"""
    moment = _issue_moment(issue_id)
    window = IssueWindow.for_day(date(moment.year, moment.month, moment.day))
    published_at = moment.isoformat()

    accounts = [str(a).strip() for a in (meta.get("accounts") or []) if str(a).strip()]
    description = str(meta.get("description") or "").strip()

    return {
        "schema_version": 1,
        "issue": {
            "id": issue_id,
            "published_at": published_at,
            "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
            # 迁移的对象都是**已经上线**的期：定稿状态照实写，不然 `publish` 会拒绝它们
            "status": "confirmed",
            "confirmed_at": published_at,
        },
        "counts": {
            # 迁移期没有条目库（briefing 早被清掉了），条数一律记 0，不编。
            # 站点不显示这四个数字，它们只在 M2/M3 的产物里有意义。
            # 四个键都写出来（而不是靠 Zod 默认补），是为了让
            # `/daily/<期号>.json` 与磁盘上的 `report.json` 逐字节相同。
            "items": 0,
            "accounts": len(accounts),
            "late": 0,
            "skipped_duplicate": 0,
        },
        "description": description,
        "highlights": _claims(meta.get("highlights")),
        "insights": _claims(meta.get("insights")),
        "interactions": _claims(meta.get("interactions")),
        "works": _works(meta.get("works")),
        "categories": [],
        "accounts": accounts,
        "people": _people(meta.get("people")),
        "provenance": {
            "generator": "daily.migrate",
            "prompt_version": 1,
            "cache_key": "",
            # 取发布时刻，不取 now()：`--check` 要比整份文件
            "generated_at": published_at,
        },
    }


# --------------------------------------------------------------------------
# 读写
# --------------------------------------------------------------------------
def dump(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


@dataclass
class Result:
    issue_id: str
    action: str  # created | updated | identical | missing
    path: Path


def _compare(existing: dict, fresh: dict) -> bool:
    return json.loads(json.dumps(existing)) == json.loads(json.dumps(fresh))


def migrate_one(md: Path, dest_root: Path, *, write: bool) -> Result:
    issue_id = md.stem
    report = report_from_meta(load_meta(md), issue_id)
    target = dest_root / issue_id / "report.json"

    if not target.exists():
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(dump(report), encoding="utf-8", newline="\n")
        return Result(issue_id, "created", target)

    existing = json.loads(target.read_text(encoding="utf-8"))
    if _compare(existing, report):
        return Result(issue_id, "identical", target)
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dump(report), encoding="utf-8", newline="\n")
    return Result(issue_id, "updated", target)


def migrate(
    src: Path = DEFAULT_SRC,
    dest: Path = DEFAULT_DEST,
    *,
    ids: list[str] | None = None,
    write: bool = False,
) -> list[Result]:
    files = sorted(src.glob("*.md"))
    if ids:
        wanted = set(ids)
        files = [f for f in files if f.stem in wanted]
        missing = wanted - {f.stem for f in files}
        if missing:
            raise MigrateError(f"找不到这些期号的 Markdown：{', '.join(sorted(missing))}")
    return [migrate_one(f, dest, write=write) for f in files]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Markdown 日报 → report.json（M4.1）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="只读比对，有差异退出 1")
    mode.add_argument("--write", action="store_true", help="落盘")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="Markdown 目录")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="report.json 根目录")
    parser.add_argument("--id", action="append", dest="ids", help="只处理这些期号（可重复）")
    args = parser.parse_args(argv)

    try:
        results = migrate(args.src, args.dest, ids=args.ids, write=args.write)
    except MigrateError as exc:
        print(f"迁移失败：{exc}")
        return 2

    if not results:
        print(f"{args.src} 里没有 Markdown 了（已经迁移完毕）")
        return 0

    labels = {"created": "新建", "updated": "更新", "identical": "一致", "missing": "缺失"}
    for item in results:
        print(f"  {item.issue_id}  {labels[item.action]:<2}  {item.path}")

    drift = [r for r in results if r.action in {"created", "updated"}]
    if args.check:
        if drift:
            print(f"\n{len(drift)} 期与磁盘上的 report.json 不一致（--write 才会落盘）")
            return 1
        print(f"\n{len(results)} 期全部一致")
    return 0
