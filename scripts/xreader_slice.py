#!/usr/bin/env python3
r"""把 X-Reader 的全量库切成「按 JST 日一片」，写进 `data/xreader/`。

## 为什么要切，而不是把整份库搬进来

X-Reader 的库是 **append-only**：`data/items/x.jsonl` 从 2016 年一直写到现在，
14 MB 且每天都在长；`data-galgame/items/x.jsonl` 5.3 MB。直接把两份 jsonl
提交进站点仓库，等于让 git 每天存一份**全新的整文件**——一天 20 MB，一年 7 GB，
仓库会被撑爆。

按日切片把「整文件重写」变成「每天新增一个不可变的小文件」：

    一天  ≈ 550 KB（700 条上下）        → 一年 git 里约 55 MB（zlib 后）
    滚存 40 天 ≈ 21 MB 工作区          → 克隆时不会觉得重

代价是只留最近 `--keep` 天。日报只需要「昨天」，但周报/月报要覆盖最长 35 天的窗口，
所以默认留 40 天；要看更早的，`.xreader/` 那份全量库还在。

## 为什么不进公开网址

`data/` 在仓库根，**不在 `public/` 里**，Astro 只把 `public/` 和路由生成的页面
放进 `dist/`——`dist/data/` 从来不存在（`data/daily/` 是 content collection，
构建时读、不复制）。所以这里的东西不会出现在 epsilongg.io 上。

## 用法

    python scripts/xreader_slice.py                  # 两版都切，滚存 40 天
    python scripts/xreader_slice.py --kind galgame
    python scripts/xreader_slice.py --keep 30        # 留一个月
    python scripts/xreader_slice.py --date 2026-10-31 # 只补这一天
    python scripts/xreader_slice.py --dry-run        # 只看会写什么

`daily_prepare.py` 在 `git pull` 之后会自动调用它（`--no-slice` 可关掉），
所以正常出日报时**不需要单独跑**。手动跑的场合是：重出旧期、或想改保留天数。

## 退出码

    0  切完（或本来就没有可切的）
    2  抓取侧还没有这个库（`data/items` / `data-galgame/items` 都不存在）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_prepare import KINDS, default_xreader  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

# 切片的落脚点。目录名是 kind，文件名是 JST 自然日：`voice/2026-10-31.jsonl`。
DEST = REPO_ROOT / "data" / "xreader"

# 默认滚存天数。
# 日报只用昨天，重出一期最多回看两周；但周报窗口 7 天、月报窗口最长 35 天，
# 统一内容层要能从版本化切片里取到完整的 35 天（外加边界余量），所以留 40 天。
# 2026-11-04 经用户授权从 14 改到 40（见 docs/architecture/unified-content-audit.md §0.1）。
# 注意：这只改变切片的保留范围，不改变日报读哪份库、也不改变日报输出。
KEEP_DAYS = 40

JST = timezone(timedelta(hours=9))


def _moment(raw: str) -> datetime | None:
    """把 `published_at` 解析成带时区的时刻；解析不了返回 None。"""
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def collect(items_dir: Path) -> dict[date, dict[str, tuple[str, str]]]:
    """按 JST 自然日分组，返回 `{day: {去重键: (published_at, 原始行)}}`。

    存**原始行**而不是反序列化后的对象：X-Reader 那边字段顺序、浮点写法都可能变，
    重新 `json.dumps` 会让切片和正本逐字节对不上，白白制造 diff。

    去重键优先 `identity_key`（X-Reader 自己的口径，`x:<id>`），退回 `item_id`。
    同一轮抓取重复落同一条是常态（nitter 的 RSS 窗口会重叠），切片里不该出现两份。
    """
    days: dict[date, dict[str, tuple[str, str]]] = {}
    for path in sorted(items_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.rstrip("\r\n")
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw = record.get("published_at") or ""
                moment = _moment(raw)
                if moment is None:
                    continue
                day = moment.astimezone(JST).date()
                key = str(record.get("identity_key") or record.get("item_id") or line[:120])
                days.setdefault(day, {})[key] = (raw, line)
    return days


def write_day(dest_dir: Path, day: date, bucket: dict[str, tuple[str, str]], *, dry_run: bool) -> tuple[int, int]:
    """写一片，返回 (条数, 字节数)。按 `published_at` 升序，同一时刻按去重键排。"""
    ordered = sorted(bucket.items(), key=lambda kv: (kv[1][0], kv[0]))
    # 用 bytes 写，绕开本机 `core.autocrlf=true`：切片必须是 LF，否则每次 checkout
    # 都变成一次「全文件改动」，git 历史里全是噪音（`.gitattributes` 里也钉了 eol=lf）。
    payload = "".join(line + "\n" for _key, (_at, line) in ordered).encode("utf-8")
    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / f"{day.isoformat()}.jsonl").write_bytes(payload)
    return len(ordered), len(payload)


def prune(dest_dir: Path, keep_from: date, keep_to: date, *, dry_run: bool) -> list[str]:
    """删掉窗口外的旧片。返回被删的文件名（`--dry-run` 时是「将要删」）。"""
    removed: list[str] = []
    if not dest_dir.exists():
        return removed
    for path in sorted(dest_dir.glob("*.jsonl")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if keep_from <= day <= keep_to:
            continue
        removed.append(path.name)
        if not dry_run:
            path.unlink()
    return removed


def refresh(
    kind: str,
    xreader: Path,
    *,
    keep: int = KEEP_DAYS,
    only_day: date | None = None,
    dest: Path = DEST,
    dry_run: bool = False,
    quiet: bool = False,
) -> int:
    """切一版。返回 0 表示切了（或无事可做），2 表示抓取侧还没有这个库。"""
    _suffix, data_name, label = KINDS[kind]
    items_dir = xreader / data_name / "items"
    if not items_dir.exists():
        if not quiet:
            print(f"{label}: 没有 {items_dir}，跳过", file=sys.stderr)
        return 2

    days = collect(items_dir)
    if not days:
        if not quiet:
            print(f"{label}: {items_dir} 里没有可用的条目，跳过", file=sys.stderr)
        return 0

    dest_dir = dest / kind
    if only_day is not None:
        # `--date` 是「补这一天」，不是「只留这一天」——所以这个分支**不剪枝**。
        window = [only_day] if only_day in days else []
        keep_from = keep_to = only_day
    else:
        keep_to = max(days)
        keep_from = keep_to - timedelta(days=max(keep, 1) - 1)
        window = [day for day in sorted(days) if keep_from <= day <= keep_to]

    if not window:
        if not quiet:
            print(f"{label}: {only_day} 没有条目，什么都没写", file=sys.stderr)
        return 0

    total_items = total_bytes = 0
    for day in window:
        count, size = write_day(dest_dir, day, days[day], dry_run=dry_run)
        total_items += count
        total_bytes += size
        if not quiet:
            print(f"  {day.isoformat()}  {count:>4d} 条  {size / 1024:>7.0f} KB")

    removed = [] if only_day is not None else prune(dest_dir, keep_from, keep_to, dry_run=dry_run)
    if removed and not quiet:
        verb = "将删除" if dry_run else "已删除"
        print(f"  {verb}窗口外旧片 {len(removed)} 个：{', '.join(removed[:3])}"
              f"{' …' if len(removed) > 3 else ''}")

    if not quiet:
        scope = f"{window[0].isoformat()} ~ {window[-1].isoformat()}" if len(window) > 1 else window[0].isoformat()
        prefix = "（dry-run，未落盘）" if dry_run else ""
        print(f"{label}: {scope} 共 {total_items} 条 / {total_bytes / 1024 / 1024:.1f} MB "
              f"→ {dest_dir}{prefix}")
    return 0


def refresh_quiet(kind: str, xreader: Path, **kwargs) -> int:
    """给 `daily_prepare.py` 用的薄包装：不刷屏，只在出错时说一句。"""
    try:
        return refresh(kind, xreader, quiet=True, **kwargs)
    except OSError as exc:
        print(f"（切片跳过：{exc}）", file=sys.stderr)
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 X-Reader 的库切成 data/xreader/ 的按日切片")
    parser.add_argument("--kind", choices=["voice", "galgame", "both"], default="both")
    parser.add_argument("--xreader", type=Path,
                        default=Path(default_xreader()),
                        help="X-Reader 的 checkout 路径（默认 .xreader/）")
    parser.add_argument("--dest", type=Path, default=DEST, help="切片写到哪（默认 data/xreader/）")
    parser.add_argument("--keep", type=int, default=KEEP_DAYS, help=f"滚存天数（默认 {KEEP_DAYS}）")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="只切这一天（JST）")
    parser.add_argument("--dry-run", action="store_true", help="只看会写什么，不落盘")
    args = parser.parse_args(argv)

    if not (args.xreader / ".git").exists():
        print(f"{args.xreader} 不像 X-Reader 的 checkout（没有 .git）——"
              "先按 docs/daily-report-guide.md 建一个", file=sys.stderr)
        return 2

    kinds = ["voice", "galgame"] if args.kind == "both" else [args.kind]
    worst = 0
    for kind in kinds:
        code = refresh(
            kind, args.xreader, keep=args.keep, only_day=args.date,
            dest=args.dest, dry_run=args.dry_run,
        )
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
