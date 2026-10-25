"""命令行入口。

    cd scripts
    python -m daily build --items-dir sample_items --date 2026-10-23 --at "2026-10-23 22:00"
    python -m daily build ... --check-reproducible
    python -m daily state info --path ../data/daily/state.json
    python -m daily version

`scripts/daily_digest.py` 是它的薄壳：老的命令行参数一个都没变。

`build` 一条链路做四件事，顺序不能换：

    window 切窗 → classify 五态判定 → dedupe 合并同一条内容 → order 排序 → export 出结构

先判态再合并：账本按 `key` 记，同一条内容的多条记录必须**各自**判一次，
否则「第二次运行 skipped_duplicate 是 28 还是 27」会随去重实现漂移。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path

from . import SCHEMA_VERSION, __version__
from .adapters.xreader import XReaderAdapter
from .build import build_briefing, build_markdown
from .dedupe import merge
from .export import build as build_export
from .incremental import Classification, classify, commit
from .issue import JST, issue_id_for, parse_at
from .model import Item
from .order import sort_accounts, sort_items
from .roster import Roster
from .state import State
from .window import IssueWindow

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = REPO_ROOT / "data" / "daily" / "state.json"


def _select(items: list[Item], date_text: str | None, at_text: str | None):
    """定窗口（哪一天）与期号（哪一小时）。分天一律按 JST 自然日。"""
    if date_text:
        report_date = date_cls.fromisoformat(date_text)
    else:
        known = [d for d in (it.date() for it in items) if d]
        report_date = max(known) if known else date_cls.today()

    window = IssueWindow.for_day(report_date)
    moment = parse_at(at_text) if at_text else datetime.now(JST)
    return window, issue_id_for(moment), moment


def _render(
    classification: Classification,
    merged: list[Item],
    accounts: list[str],
    issue_id: str,
    roster: Roster,
    published_at: str,
) -> dict[str, bytes]:
    """三个产物一起出。generate.json 也是可复现对象，所以放进同一份比对。"""
    export = build_export(issue_id, classification, merged, roster, published_at)
    return {
        f"{issue_id}.briefing.txt": build_briefing(
            merged, classification.window.day, accounts
        ).encode("utf-8"),
        f"{issue_id}.md": build_markdown(merged, issue_id, accounts).encode("utf-8"),
        f"{issue_id}.generate.json": (
            json.dumps(export, ensure_ascii=False, indent=1) + "\n"
        ).encode("utf-8"),
    }


def _pipeline(
    raw: list[Item], window: IssueWindow, roster: Roster, seen: dict
) -> tuple[Classification, list[Item], list[str]]:
    selection = window.select(raw)
    if selection.unsure:
        print(
            f"注意：{len(selection.unsure)} 条只有日期精度（precision=day），"
            f"无法判定属于哪一天，已按 {window.day.isoformat()} 窗内处理，请人工确认。",
            file=sys.stderr,
        )
    if selection.undated:
        print(
            f"注意：{len(selection.undated)} 条没有可解析的发布时间，未计入任何一期。",
            file=sys.stderr,
        )

    classification = classify(raw, window, seen)
    merged = sort_items(merge(classification.items))
    accounts = sort_accounts({i.account for i in merged}, roster)
    roster.warn_unknown(accounts)
    return classification, merged, accounts


def _cmd_build(args: argparse.Namespace) -> int:
    adapter = XReaderAdapter(Path(args.items_dir))
    raw = list(adapter.iter_items())
    if not raw:
        print(
            "未找到任何条目。请先运行 X-Reader（CI 或本地），或检查 --items-dir。",
            file=sys.stderr,
        )
        return 2

    window, issue_id, moment = _select(raw, args.date, args.at)
    published_at = moment.isoformat()
    roster = Roster.load(args.roster)

    if args.backfill:
        # 补录历史：只关心窗口内的条目。不这么筛的话，同一批数据里
        # 其他日子的条目会全部落进 late / future，counts 全是噪音。
        raw = [
            it
            for it in raw
            if (it.published_dt() is not None and window.start <= it.published_dt() < window.end)
        ]

    if args.check_reproducible:
        # 纯函数检查：不读也不写账本，否则第二次运行会因为「都见过了」而不同
        first_c, first_items, first_acc = _pipeline(raw, window, roster, {})
        first = _render(first_c, first_items, first_acc, issue_id, roster, published_at)
        second_c, second_items, second_acc = _pipeline(raw, window, roster, {})
        second = _render(second_c, second_items, second_acc, issue_id, roster, published_at)
        if first != second:
            for name in sorted(set(first) | set(second)):
                if first.get(name) != second.get(name):
                    print(f"不可复现：{name} 两次输出不同", file=sys.stderr)
            return 4
        total = sum(len(v) for v in first.values())
        print(f"可复现：{len(first)} 个文件、{total} 字节，两次运行完全相同（{issue_id}）")
        return 0

    state = State() if (args.no_state or args.backfill) else State.load(args.state)
    classification, merged, accounts = _pipeline(raw, window, roster, state.seen)

    md_out = (
        Path(args.md_out)
        if args.md_out
        else REPO_ROOT / "src" / "content" / "daily" / f"{issue_id}.md"
    )
    # 存档保护：同一声明时间只允许有一期，重跑必须先 --force，避免手滑覆盖
    if md_out.exists() and not args.force:
        print(
            f"已存在 {md_out}，拒绝覆盖（这一期已经在存档里了）。\n"
            f"换一个小时（--at）或者加 --force 明确覆盖。",
            file=sys.stderr,
        )
        return 3

    files = _render(classification, merged, accounts, issue_id, roster, published_at)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, blob in files.items():
        (out / name).write_bytes(blob)

    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_bytes(files[f"{issue_id}.md"])

    counts = classification.counts(accounts=len(accounts))
    print(
        f"{window.label} 窗口：{len(merged)} 条（去重后，原始 {len(classification.items)}）· "
        f"{counts['accounts']} 位账号 · 跳过重复 {counts['skipped_duplicate']} · "
        f"迟到 {counts['late']} · 晚于窗口 {len(classification.future)}"
    )
    print(f"Wrote {out / issue_id}.briefing.txt")
    print(f"Wrote {out / issue_id}.generate.json")
    print(f"Wrote Markdown -> {md_out}  (期号 {issue_id}，网址 /daily/{issue_id}/)")

    if not args.no_state and not args.backfill:
        commit(state, classification, issue_id, published_at)
        state.save(args.state)
        print(f"State -> {args.state}（seen {len(state.seen)} 条）")

    if not counts["items"]:
        print(
            "注意：这一期没有任何新条目。如果是历史补录，检查 --date；"
            "如果是重跑，重复条目已经全部跳过了。",
            file=sys.stderr,
        )

    print(
        "下一步：让本地 WorkBuddy 读 briefing 与 generate.json，填写该 .md 里的 "
        "highlights（今日看点）/ interactions（互动）/ people[].summary（每人一句）三段。"
    )
    return 0


def _cmd_state(args: argparse.Namespace) -> int:
    state = State.load(args.path)
    if args.state_cmd == "info":
        print(
            f"schema_version {state.schema_version} | issues {len(state.issues)} | "
            f"seen {len(state.seen)} | {args.path}"
        )
        return 0
    if args.state_cmd == "prune":
        dropped = state.prune(days=args.days)
        state.save(args.path)
        print(f"pruned {dropped} entries older than {args.days} days -> {args.path}")
        return 0
    if args.state_cmd == "rebuild":
        count = state.rebuild()
        state.save(args.path)
        print(f"rebuilt {count} seen keys from {len(state.issues)} issues -> {args.path}")
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily", description="日报数据层（M2）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="切窗、判态、去重、排序，出 briefing 与骨架")
    build.add_argument("--items-dir", required=True, help="X-Reader data/items 目录")
    build.add_argument("--date", help="汇总哪一天的数据 YYYY-MM-DD（JST 自然日；默认：数据里最新的一天）")
    build.add_argument(
        "--at", default=None, help="发布时间（JST），决定期号，如 '2026-10-31 22:00'；默认当前时间"
    )
    build.add_argument("--out", default="out", help="briefing / generate.json 的输出目录")
    build.add_argument("--md-out", default=None, help="日报 Markdown 输出路径")
    build.add_argument("--state", default=str(DEFAULT_STATE), help="增量状态文件")
    build.add_argument("--no-state", action="store_true", help="不读也不写账本（历史补录用）")
    build.add_argument(
        "--backfill",
        action="store_true",
        help="补录历史：只取窗口内的条目，不读不写账本（late / future 恒为 0）",
    )
    build.add_argument("--roster", default=None, help="名单文件，默认 src/config/daily-roster.json")
    build.add_argument("--force", action="store_true", help="允许覆盖已存在的期号")
    build.add_argument(
        "--check-reproducible",
        action="store_true",
        help="同一份输入跑两次，逐字节比对（不落盘、不读账本）",
    )
    build.set_defaults(func=_cmd_build)

    state = sub.add_parser("state", help="增量状态的查看与维护")
    state_sub = state.add_subparsers(dest="state_cmd", required=True)
    for name, help_text in (
        ("info", "看条数"),
        ("prune", "裁掉 90 天前的 seen"),
        ("rebuild", "从 issues 重建 seen"),
    ):
        sp = state_sub.add_parser(name, help=help_text)
        sp.add_argument("--path", default=str(DEFAULT_STATE))
        if name == "prune":
            sp.add_argument("--days", type=int, default=90)
        sp.set_defaults(func=_cmd_state)

    version = sub.add_parser("version", help="打印版本")
    version.set_defaults(func=lambda _a: print(f"daily {__version__} | schema {SCHEMA_VERSION}") or 0)

    args = parser.parse_args(argv)
    return args.func(args)
