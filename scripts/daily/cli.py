"""命令行入口。

    cd scripts
    python -m daily build --items-dir sample_items --date 2026-10-23
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
from . import confirm as confirm_mod
from . import migrate as migrate_mod
from . import paths as path_mod
from . import prompt as prompt_mod
from . import publish as publish_mod
from .adapters.xreader import XReaderAdapter
from .apply import ApplyError, apply
from .audit import audit_report, has_errors, summarize
from .build import build_briefing, build_report
from .dedupe import merge
from .export import build as build_export
from .filter import apply_rules
from .incremental import Classification, classify, commit
from .issue import JST, issue_id_for, parse_at
from .model import Item
from .order import sort_accounts, sort_items
from .roster import Roster
from .state import State
from .validate import ValidationError, validate_answer
from .window import IssueWindow

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = REPO_ROOT / "data" / "daily" / "state.json"


def _taken_issues(out_dir: str, dest_root: Path) -> set[str]:
    """工作区与已发布目录里已经存在的期号。分配新期号时避开它们。"""
    taken = {p.parent.name for p in Path(out_dir).glob("*/report.json")}
    taken |= {p.parent.name for p in Path(dest_root).glob("*/report.json")}
    return taken


def _select(
    items: list[Item],
    date_text: str | None,
    at_text: str | None,
    *,
    new: bool = False,
    out_dir: str = "out",
    dest_root: Path = publish_mod.DEFAULT_DEST,
):
    """定窗口（哪一天）、期号（那一天的哪一期）与发布时间。

    期号只到天：`261027`，同一天的第二期是 `261027-2`。`--at` **不再决定期号**，
    它只是 `issue.published_at`——也就是页面「发布于」和 RSS `pubDate` 用的真实时间。
    """
    if date_text:
        report_date = date_cls.fromisoformat(date_text)
    else:
        known = [d for d in (it.date() for it in items) if d]
        report_date = max(known) if known else date_cls.today()

    window = IssueWindow.for_day(report_date)
    moment = parse_at(at_text) if at_text else datetime.now(JST)

    # 默认就用当天第 1 期；已存在的话由 build 的存档保护拦下（不静默改成 -2）。
    # 明确要出第二期时才往后找空位。
    taken = _taken_issues(out_dir, dest_root)
    seq = 1
    if new:
        while issue_id_for(report_date, seq) in taken:
            seq += 1
    return window, issue_id_for(report_date, seq), moment


def _render(
    classification: Classification,
    merged: list[Item],
    accounts: list[str],
    issue_id: str,
    roster: Roster,
    published_at: str,
    per_account: int | None = None,
    dropped: list[dict] | None = None,
) -> dict[str, bytes]:
    """三个产物一起出。generate.json 与 report.json 也是可复现对象，所以放进同一份比对。"""
    export = build_export(issue_id, classification, merged, roster, published_at, dropped=dropped)
    report = build_report(
        merged,
        issue_id,
        accounts=accounts,
        roster=roster,
        published_at=published_at,
        window=classification.window,
        counts=classification.counts(accounts=len(accounts)),
    )
    return {
        f"{issue_id}.briefing.txt": build_briefing(
            merged, classification.window.day, accounts, per_account
        ).encode("utf-8"),
        f"{issue_id}.report.json": (
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
        f"{issue_id}.generate.json": (
            json.dumps(export, ensure_ascii=False, indent=1) + "\n"
        ).encode("utf-8"),
    }


def _pipeline(
    raw: list[Item], window: IssueWindow, roster: Roster, seen: dict
) -> tuple[Classification, list[Item], list[str], list[dict]]:
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

    # 名单里 active=false 的账号（目前是全部社团号）先不进日报：
    # 跳过的是**条目**，不是「当成未知账号」——它们在名单里，只是暂时不消化。
    # 静默跳过会让「昨天还在的人今天不见了」无从查起，所以打一行日志。
    idle = sorted({i.account for i in merged if not roster.is_active(i.account)})
    if idle:
        print(
            f"注意：{len(idle)} 个账号标了 active=false，条目已跳过：" + "、".join(idle),
            file=sys.stderr,
        )
        merged = [i for i in merged if roster.is_active(i.account)]

    # 账号级降噪（`filter.py`）：情报站与官号的抽奖、促销、周年回顾在这里被挡掉。
    # 挡在 merge 之后、accounts 之前——一个号如果当天只剩这类条目，
    # 它就不该出现在 people 表里（页面上会出现一个没有内容的人）。
    merged, dropped = apply_rules(merged, roster.filters)
    if dropped:
        per_account: dict[str, int] = {}
        for row in dropped:
            per_account[row["account"]] = per_account.get(row["account"], 0) + 1
        summary = "、".join(f"{h} {n} 条" for h, n in sorted(per_account.items()))
        print(f"注意：{len(dropped)} 条被账号规则筛掉（{summary}）", file=sys.stderr)

    # 名单外的 handle 不进**页面**（`accounts` → frontmatter 的 people 行）。
    # 条目本身留在 `merged` 里：briefing 与 export 照旧能看到，出问题才查得到。
    # 名单外的人在页面上拿不到 `name`，只能渲染成裸 @handle，等于把品牌号当声优列出来。
    accounts = sort_accounts({i.account for i in merged}, roster)
    unknown = roster.warn_unknown(accounts)
    if unknown:
        accounts = [a for a in accounts if roster.is_known(a)]
    return classification, merged, accounts, dropped


def _cmd_build(args: argparse.Namespace) -> int:
    adapter = XReaderAdapter(Path(args.items_dir))
    raw = list(adapter.iter_items())
    if adapter.malformed:
        # 坏行不会让构建失败（一天的抓取里偶发一行截断是常态），但**必须报出来**：
        # 静默跳过等于「那几条推文从来不存在」，而日报是转述，少一条没人看得出来。
        shown = "、".join(adapter.malformed[:5])
        if len(adapter.malformed) > 5:
            shown += f" 等 {len(adapter.malformed)} 处"
        print(f"注意：{len(adapter.malformed)} 行不是合法 JSON，已跳过（{shown}）", file=sys.stderr)
    if not raw:
        print(
            "未找到任何条目。请先运行 X-Reader（CI 或本地），或检查 --items-dir。",
            file=sys.stderr,
        )
        return 2

    window, issue_id, moment = _select(
        raw, args.date, args.at, new=args.new, out_dir=args.out
    )
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
        first_c, first_items, first_acc, first_drop = _pipeline(raw, window, roster, {})
        first = _render(first_c, first_items, first_acc, issue_id, roster, published_at,
                        args.per_account, first_drop)
        second_c, second_items, second_acc, second_drop = _pipeline(raw, window, roster, {})
        second = _render(second_c, second_items, second_acc, issue_id, roster, published_at,
                         args.per_account, second_drop)
        if first != second:
            for name in sorted(set(first) | set(second)):
                if first.get(name) != second.get(name):
                    print(f"不可复现：{name} 两次输出不同", file=sys.stderr)
            return 4
        total = sum(len(v) for v in first.values())
        print(f"可复现：{len(first)} 个文件、{total} 字节，两次运行完全相同（{issue_id}）")
        return 0

    state = State() if (args.no_state or args.backfill) else State.load(args.state)
    classification, merged, accounts, dropped = _pipeline(raw, window, roster, state.seen)

    # 正本落在工作区 `out/<期号>/report.json`——`apply` / `confirm` / `publish` 都读它。
    # 站点读的是 `data/daily/<期号>/report.json`，两者靠 `publish` 连接：
    # 「编辑中的一期」和「已经发布的一期」在磁盘上必须是两个位置。
    report_out = (
        Path(args.report_out)
        if args.report_out
        else path_mod.report(path_mod.workspace(args.out, issue_id))
    )
    # 存档保护：同一期只允许有一份草稿，重跑必须先 --force，避免手滑覆盖已写好的内容
    if report_out.exists() and not args.force:
        print(
            f"已存在 {report_out}，拒绝覆盖（这一期已经在工作区里了）。\n"
            f"改内容加 --force；确实要出第二期就加 --new（会排成 {issue_id_for(window.day, 2)}）。",
            file=sys.stderr,
        )
        return 3

    files = _render(
        classification, merged, accounts, issue_id, roster, published_at, args.per_account, dropped
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, blob in files.items():
        if name.endswith(".report.json"):
            continue  # 正本走下面的目录结构，不进扁平的 out/
        (out / name).write_bytes(blob)

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_bytes(files[f"{issue_id}.report.json"])

    counts = classification.counts(accounts=len(accounts))
    print(
        f"{window.label} 窗口：{len(merged)} 条（去重后，原始 {len(classification.items)}）· "
        f"{counts['accounts']} 位账号 · 跳过重复 {counts['skipped_duplicate']} · "
        f"迟到 {counts['late']} · 晚于窗口 {len(classification.future)}"
    )
    print(f"Wrote {out / issue_id}.briefing.txt")
    print(f"Wrote {out / issue_id}.generate.json")
    print(f"Wrote 正本 -> {report_out}  (期号 {issue_id}，网址 /daily/{issue_id}/)")

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
        f"下一步：让本地 WorkBuddy 读 briefing 与 generate.json，填写 {report_out} 里的 "
        "highlights（今日看点）/ works（作品动态）/ interactions（互动）/ people[].summary（每人一句）。"
        "写完 `daily confirm` 定稿，再 `daily publish` 搬到站点。"
    )
    return 0


def _load_generate(out_dir: str, issue_id: str) -> dict:
    path = Path(out_dir) / f"{issue_id}.generate.json"
    if not path.exists():
        raise SystemExit(f"找不到 {path}，先跑 `daily build`。")
    return json.loads(path.read_text(encoding="utf-8"))


def _known(generate: dict) -> tuple[set[str], dict[str, set[str]]]:
    """本期的合法来源 key，以及每个分类各自的 handles。"""
    keys: set[str] = set()
    handles: dict[str, set[str]] = {}
    for category in generate.get("categories") or []:
        cid = str(category.get("id") or "")
        handles[cid] = {str(h) for h in category.get("handles") or []}
        for item in category.get("items") or []:
            keys.add(str(item.get("key") or ""))
    return keys, handles


def _all_handles(handles: dict[str, set[str]]) -> set[str]:
    """整期题（category=all）的合法 handle 集合：本期出过条目的所有账号。"""
    out: set[str] = set()
    for group in handles.values():
        out |= group
    return out


def _cmd_prompt(args: argparse.Namespace) -> int:
    generate = _load_generate(args.out, args.issue)
    if args.flat and args.reduce:
        raise SystemExit("--flat 与 --reduce 只能选一个：前者是整期一份题，后者是分类答完之后的汇总题。")
    if args.reduce:
        answer_dir = path_mod.answers(path_mod.workspace(args.out, args.issue))
        answers = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(answer_dir.glob("*.json"))]
        if not answers:
            raise SystemExit(f"{answer_dir} 里没有回答，先答分类题。")
        prompt = prompt_mod.build_reduce(args.issue, answers, args.out, force=args.force)
        print(f"{'跳过（输入未变）' if prompt.cached else '已写出'} {prompt.md_path}")
        return 0

    if args.flat:
        prompt = prompt_mod.build_flat(args.issue, generate, args.out, force=args.force)
        flag = "跳过（输入未变）" if prompt.cached else "已写出"
        print(f"{flag} {prompt.md_path}  （{prompt.items} 条）")
        print(f"下一步：把回答存成 {path_mod.answers(path_mod.workspace(args.out, args.issue)) / 'all.json'}，再 `daily apply`。")
        return 0

    prompts = prompt_mod.build(args.issue, generate, args.out, force=args.force)
    for prompt in prompts:
        flag = "跳过（输入未变）" if prompt.cached else "已写出"
        print(f"{flag} {prompt.md_path}  （{prompt.items} 条）")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    generate = _load_generate(args.out, args.issue)
    roster = Roster.load(args.roster)
    keys, handles = _known(generate)

    if args.answer:
        files = [Path(p) for p in args.answer]
    else:
        files = sorted(path_mod.answers(path_mod.workspace(args.out, args.issue)).glob("*.json"))
    if not files:
        raise SystemExit("没有可合并的回答。先跑 `daily prompt`，把回答放进 answer/。")

    answers = []
    failed = 0
    for path in files:
        try:
            answer = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"{path.name}: 不是合法 JSON（{exc}）", file=sys.stderr)
            failed += 1
            continue
        cid = str(answer.get("category") or path.stem)
        try:
            validate_answer(
                answer,
                roster=roster,
                known_keys=keys,
                # 整期题的合法 handle = 本期所有出过条目的账号。
                # 以前这里传 None（只查名单），等于允许把「名单里有但今天没说话的人」写进 people。
                handles=_all_handles(handles) if cid == "all" else handles.get(cid),
                category=None if cid == "all" else cid,
            )
        except ValidationError as exc:
            print(f"{path.name} 判卷失败\n{exc}", file=sys.stderr)
            failed += 1
            continue
        answers.append(answer)

    if failed:
        print(f"{failed} 份回答不合格，未合并任何内容。", file=sys.stderr)
        return 1

    try:
        report = apply(
            args.issue, answers, roster=roster, generate=generate, out_dir=args.out, force=args.force
        )
    except ApplyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    filled = sum(1 for p in report["people"] if p.get("summary"))
    print(
        f"已合并 {len(answers)} 份回答 → {path_mod.report(path_mod.workspace(args.out, args.issue))}"
        f"（{filled}/{len(report['people'])} 人有摘要，状态 {report['issue']['status']}）"
    )
    return 0


def _report_path_for_audit(issue_id: str, out_dir: str, *, published: bool = False) -> Path:
    if published:
        return Path(publish_mod.DEFAULT_DEST) / issue_id / "report.json"
    workspace = path_mod.report(path_mod.workspace(out_dir, issue_id))
    if workspace.exists():
        return workspace
    return Path(publish_mod.DEFAULT_DEST) / issue_id / "report.json"


def _audit(
    issue_id: str,
    out_dir: str,
    roster: Roster,
    *,
    published: bool = False,
    strict: bool | None = None,
) -> tuple[Path, list, bool]:
    """对一份**已经写好的**正本判卷。返回 `(路径, findings, 是否核对了来源)`。

    严格度默认按正本来路定：迁移来的旧正本没有 `sources`，不能因为补了个校验
    就把已上线的内容判死；新写的正本（`generator` 不是 `daily.migrate`）必须带来源。
    """
    path = _report_path_for_audit(issue_id, out_dir, published=published)
    if not path.exists():
        raise SystemExit(f"找不到正本：{path}")
    report = json.loads(path.read_text(encoding="utf-8"))

    generate_path = Path(out_dir) / f"{issue_id}.generate.json"
    known_keys: set[str] | None = None
    accounts: set[str] | None = None
    if generate_path.exists():
        keys, handles = _known(json.loads(generate_path.read_text(encoding="utf-8")))
        known_keys = keys
        accounts = _all_handles(handles)

    if strict is None:
        generator = str((report.get("provenance") or {}).get("generator") or "")
        strict = generator != "daily.migrate"

    findings = audit_report(
        report, roster=roster, known_keys=known_keys, accounts=accounts, strict=strict
    )
    return path, findings, known_keys is not None


def _cmd_audit(args: argparse.Namespace) -> int:
    strict = True if args.strict else False if args.lenient else None
    path, findings, had_material = _audit(
        args.issue, args.out, Roster.load(args.roster), published=args.published, strict=strict
    )
    print(f"判卷对象：{path}")
    if not had_material:
        print("  ! 没有找到本期的 generate.json，只核了归属，**没核来源**")
    print(summarize(findings))
    return 1 if has_errors(findings) else 0


def _cmd_confirm(args: argparse.Namespace) -> int:
    if not args.no_audit and not args.reopen:
        _, findings, had_material = _audit(args.issue, args.out, Roster.load(args.roster))
        if has_errors(findings):
            print("定稿前判卷没过，先改正本：", file=sys.stderr)
            print(summarize(findings), file=sys.stderr)
            return 1
        if not had_material:
            print("注意：没有 generate.json，定稿只核了归属，没核来源。", file=sys.stderr)

    try:
        if args.reopen:
            report, saved = confirm_mod.reopen(args.issue, args.out)
            print(f"已退回草稿；旧版存到 {saved}")
        else:
            report, saved = confirm_mod.confirm(args.issue, args.out)
            print(f"已定稿（{report['issue']['confirmed_at']}）；旧版存到 {saved}")
    except confirm_mod.ConfirmError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    """M4.1：Markdown 日报 → report.json（一次性）。参数转给 `daily.migrate`。"""
    argv = ["--check" if args.check else "--write", "--src", str(args.src), "--dest", str(args.dest)]
    for issue_id in args.ids or []:
        argv += ["--id", issue_id]
    return migrate_mod.main(argv)


def _cmd_publish(args: argparse.Namespace) -> int:
    """M4：把定稿的正本从 out/ 搬到站点读的 data/daily/。"""
    try:
        result = publish_mod.publish(
            args.issue, out_dir=args.out, dest_root=args.dest, force=args.force
        )
    except publish_mod.PublishError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    verb = "已覆盖" if result.replaced else "已发布"
    print(f"{verb}：{result.path}")
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
        "--at",
        default=None,
        help="真实发布时间（JST），只影响 issue.published_at / RSS pubDate / 页面「发布于」；"
        "不决定期号（期号是 --date 那一天）。默认当前时间",
    )
    build.add_argument(
        "--new",
        action="store_true",
        help="当天第 1 期已存在时，另起一期（排成 261027-2）",
    )
    build.add_argument("--out", default="out", help="briefing / generate.json 的输出目录")
    build.add_argument(
        "--report-out", default=None, help="正本输出路径，默认 out/<期号>/report.json"
    )
    build.add_argument("--state", default=str(DEFAULT_STATE), help="增量状态文件")
    build.add_argument("--no-state", action="store_true", help="不读也不写账本（历史补录用）")
    build.add_argument(
        "--backfill",
        action="store_true",
        help="补录历史：只取窗口内的条目，不读不写账本（late / future 恒为 0）",
    )
    build.add_argument("--roster", default=None, help="名单文件，默认 src/config/daily-roster.json")
    build.add_argument(
        "--per-account",
        type=int,
        default=None,
        help="briefing 里每个账号最多写几条（默认全部）。给了数就按（互动, 时间）从高到低截断",
    )
    build.add_argument("--force", action="store_true", help="允许覆盖已存在的期号")
    build.add_argument(
        "--check-reproducible",
        action="store_true",
        help="同一份输入跑两次，逐字节比对（不落盘、不读账本）",
    )
    build.set_defaults(func=_cmd_build)

    prompt_cmd = sub.add_parser("prompt", help="M3.1 出题：按分类各写一份题面（.md 给人贴、.json 算指纹）")
    prompt_cmd.add_argument("--issue", required=True, help="期号，如 261027（同日第二期 261027-2）")
    prompt_cmd.add_argument("--out", default="out", help="工作目录（默认 out）")
    prompt_cmd.add_argument("--reduce", action="store_true", help="出全局题（材料是已写好的分类回答）")
    prompt_cmd.add_argument(
        "--flat", action="store_true", help="出整期题：一份题装下本期全部条目，产出 category=all 的回答"
    )
    prompt_cmd.add_argument("--force", action="store_true", help="忽略缓存，强制重写题面")
    prompt_cmd.set_defaults(func=_cmd_prompt)

    apply_cmd = sub.add_parser("apply", help="M3.2–M3.4 判卷并合并进 report.json")
    apply_cmd.add_argument("--issue", required=True)
    apply_cmd.add_argument("--out", default="out")
    apply_cmd.add_argument(
        "--answer", action="append", default=None, help="回答文件（可重复）；默认取 answer/ 下全部"
    )
    apply_cmd.add_argument("--roster", default=None, help="名单文件，默认 src/config/daily-roster.json")
    apply_cmd.add_argument("--force", action="store_true", help="已定稿也强行合并（正常流程请先 reopen）")
    apply_cmd.set_defaults(func=_cmd_apply)

    confirm_cmd = sub.add_parser("confirm", help="M3.5 定稿 / 退回草稿，旧版本进 history/")
    confirm_cmd.add_argument("--issue", required=True)
    confirm_cmd.add_argument("--out", default="out")
    confirm_cmd.add_argument("--reopen", action="store_true", help="退回草稿（旧版进 history/）")
    confirm_cmd.add_argument("--roster", default=None, help="名单文件，默认 src/config/daily-roster.json")
    confirm_cmd.add_argument(
        "--no-audit", action="store_true", help="跳过定稿前的判卷（只在明知正本缺来源时用）"
    )
    confirm_cmd.set_defaults(func=_cmd_confirm)

    audit_cmd = sub.add_parser("audit", help="M3.9 对已写好的正本判卷：来源能不能对上、人是不是本期的")
    audit_cmd.add_argument("--issue", required=True)
    audit_cmd.add_argument("--out", default="out")
    audit_cmd.add_argument("--roster", default=None, help="名单文件，默认 src/config/daily-roster.json")
    audit_cmd.add_argument(
        "--published", action="store_true", help="查已发布的那份（data/daily/）而不是工作区"
    )
    level = audit_cmd.add_mutually_exclusive_group()
    level.add_argument("--strict", action="store_true", help="每条 claim 都必须有来源")
    level.add_argument("--lenient", action="store_true", help="没有来源只提醒，来源写错仍然算错")
    audit_cmd.set_defaults(func=_cmd_audit)

    publish_cmd = sub.add_parser("publish", help="M4 把定稿的正本发到 data/daily/（站点读它）")
    publish_cmd.add_argument("--issue", required=True)
    publish_cmd.add_argument("--out", default="out")
    publish_cmd.add_argument(
        "--dest", default=str(publish_mod.DEFAULT_DEST), help="发布根目录（默认 data/daily）"
    )
    publish_cmd.add_argument("--force", action="store_true", help="已发布过的期号也覆盖")
    publish_cmd.set_defaults(func=_cmd_publish)

    migrate_cmd = sub.add_parser("migrate", help="M4.1 Markdown 日报迁成 report.json（一次性）")
    migrate_mode = migrate_cmd.add_mutually_exclusive_group(required=True)
    migrate_mode.add_argument("--check", action="store_true", help="只读比对，有差异退出 1")
    migrate_mode.add_argument("--write", action="store_true", help="落盘")
    migrate_cmd.add_argument("--src", default=str(migrate_mod.DEFAULT_SRC), help="Markdown 目录")
    migrate_cmd.add_argument("--dest", default=str(migrate_mod.DEFAULT_DEST), help="report.json 根目录")
    migrate_cmd.add_argument("--id", action="append", dest="ids", help="只处理这些期号（可重复）")
    migrate_cmd.set_defaults(func=_cmd_migrate)

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
