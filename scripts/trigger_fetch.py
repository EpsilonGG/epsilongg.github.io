#!/usr/bin/env python3
"""按一下就让 CI 立刻抓一轮（`workflow_dispatch`），并等数据真正落地。

## 为什么需要这个脚本

GitHub 的 `schedule` 是 **best-effort**：cron 写了 03:00 / 15:00 UTC，实际
`created_at` 却是 09:26 / 19:11 UTC —— 2026-10-26 到 10-31 的 12 次定时运行，
**每一次都晚 4.2–6.9 小时**（见 `--report` 的表）。而 job 本身只要 3–19 分钟。

也就是说：慢的不是抓取，是排队。等「15:00 那轮」等于等一个不确定的时刻，
而日报出稿卡在这个时刻上——261031 就是这样只覆盖到 JST 18:30 的。

`workflow_dispatch` 触发的 run 是**立刻创建**的。本地 00:05 按一下，5–15 分钟后
数据就落地，不用赌 scheduler。

## 用法

    # fine-grained PAT：Actions = Read and write，Contents = Read（只这一个仓库）
    export XREADER_TOKEN=github_pat_xxx

    python scripts/trigger_fetch.py                      # 两版都抓，等完成，再 git pull
    python scripts/trigger_fetch.py --kind voice         # 只抓声优版
    python scripts/trigger_fetch.py --no-wait            # 按一下就返回
    python scripts/trigger_fetch.py --report             # 只看最近的调度延迟，不触发
    python scripts/trigger_fetch.py --verify-only --date 2026-10-31
                                                        # 只查本地数据覆盖到几点

## 退出码

    0  跑完，数据已拉到本地（`--no-wait` 时只代表「已触发」）
    2  没有 token（或 token 无效）
    4  run 失败 / 超时
    5  数据落地了，但目标日的覆盖不全（最后一小时没有条目）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from daily_prepare import DEFAULT_XREADER, KINDS, pull, scan_day  # noqa: E402

JST = timezone(timedelta(hours=9))
OWNER = "EpsilonGG"
REPO = "X-Reader"
API = "https://api.github.com"

# kind → workflow 文件名。两版各一条 workflow，各自写自己的 data_dir。
WORKFLOWS = {
    "voice": "update.yml",
    "galgame": "update-galgame.yml",
}

# 目标日最后一条距 24:00 超过这个时长，就当「没覆盖完整」。
COVERAGE_SLACK = timedelta(hours=2)


def _api(method: str, path: str, token: str, payload: dict | None = None) -> tuple[int, dict | list | None]:
    """打一次 GitHub REST。返回 (状态码, 解析后的 JSON)。不抛网络异常以外的错。"""
    url = path if path.startswith("http") else API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    # 公开仓库读 run 列表不需要 token（60 次/小时的匿名额度够看 `--report`）；
    # dispatch 一定要，缺了会在调用处先被拦下。
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"message": body[:300]}


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def dispatch(kind: str, token: str) -> datetime:
    """触发一条 workflow，返回触发时刻（UTC）。"""
    workflow = WORKFLOWS[kind]
    status, body = _api(
        "POST", f"/repos/{OWNER}/{REPO}/actions/workflows/{workflow}/dispatches",
        token, {"ref": "main"},
    )
    if status not in (204, 201):
        raise SystemExit(
            f"触发 {workflow} 失败（HTTP {status}）：{body}\n"
            "token 需要这个仓库的 Actions: write 权限。"
        )
    return datetime.now(timezone.utc)


def latest_run(kind: str, token: str) -> dict | None:
    """最近一次 workflow_dispatch 触发的 run。"""
    workflow = WORKFLOWS[kind]
    status, body = _api(
        "GET",
        f"/repos/{OWNER}/{REPO}/actions/workflows/{workflow}/runs?event=workflow_dispatch&per_page=5",
        token,
    )
    if status != 200 or not isinstance(body, dict):
        return None
    runs = body.get("workflow_runs") or []
    return runs[0] if runs else None


def wait_for(kind: str, since: datetime, token: str, timeout_min: int) -> dict:
    """等这一次 dispatch 跑完。`since` 之前创建的 run 不算（避免抓到旧 run）。"""
    deadline = time.monotonic() + timeout_min * 60
    last = ""
    while time.monotonic() < deadline:
        run = latest_run(kind, token)
        if run:
            created = _parse(run.get("created_at"))
            # 允许 90 秒时钟偏差：dispatch 返回后 run 才被创建
            if created and created >= since - timedelta(seconds=90):
                state = f"{run.get('status')}/{run.get('conclusion') or '-'}"
                if state != last:
                    print(f"  {WORKFLOWS[kind]}: {state}")
                    last = state
                if run.get("status") == "completed":
                    return run
        time.sleep(15)
    raise SystemExit(f"等 {WORKFLOWS[kind]} 超时（{timeout_min} 分钟）——去 Actions 页面看看")


def report(token: str, pages: int = 1) -> None:
    """打印定时运行的「计划时刻 → 实际创建」延迟，用来复核这条结论还成不成立。"""
    rows = []
    for page in range(1, pages + 1):
        status, body = _api("GET", f"/repos/{OWNER}/{REPO}/actions/runs?per_page=100&page={page}", token)
        if status != 200 or not isinstance(body, dict):
            raise SystemExit(f"读 run 列表失败（HTTP {status}）")
        for run in body.get("workflow_runs") or []:
            if run.get("event") != "schedule":
                continue
            created = _parse(run.get("created_at"))
            updated = _parse(run.get("updated_at"))
            if not created or not updated:
                continue
            slots = [
                datetime(d.year, d.month, d.day, h, 0, tzinfo=timezone.utc)
                for d in (created.date() - timedelta(days=1), created.date(), created.date() + timedelta(days=1))
                for h in (3, 15)
            ]
            slot = max(s for s in slots if s <= created)
            rows.append((run["name"][:24], created, (created - slot).total_seconds() / 3600,
                         (updated - created).total_seconds() / 60, run.get("conclusion")))
    if not rows:
        print("没有定时运行的记录。")
        return
    print(f"{'workflow':26s} {'实际创建(UTC)':16s} {'晚于计划':>8s} {'耗时':>7s}  结论")
    for name, created, delay, took, conclusion in rows[:20]:
        print(f"{name:26s} {created.strftime('%m-%d %H:%M'):16s} {delay:7.1f}h {took:6.1f}m  {conclusion}")


def verify(xreader: Path, day: date, kinds: list[str]) -> int:
    """检查本地数据对 `day` 的覆盖：条数 + 最后一条的时间。覆盖不全返回 5。"""
    worst = 0
    for kind in kinds:
        _, data_name, label = KINDS[kind]
        items_dir = xreader / data_name / "items"
        if not items_dir.exists():
            print(f"{label}: 没有 {items_dir}")
            worst = max(worst, 5)
            continue
        inside, total, latest = scan_day(items_dir, day)
        if inside == 0 or latest is None:
            print(f"{label}: {day} 一条都没有（全部 {total} 条）")
            worst = max(worst, 5)
            continue
        end = datetime.combine(day, datetime.min.time(), tzinfo=JST) + timedelta(days=1)
        gap = end - latest
        flag = "OK" if gap <= COVERAGE_SLACK else "覆盖不全"
        print(
            f"{label}: {day} 共 {inside} 条，最后一条 {latest.astimezone(JST).strftime('%H:%M')} JST"
            f"（距 24:00 还差 {gap.total_seconds() / 3600:.1f} 小时）→ {flag}"
        )
        if gap > COVERAGE_SLACK:
            worst = max(worst, 5)
    return worst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="立刻触发 X-Reader 抓取并等它落地")
    parser.add_argument("--kind", choices=["voice", "galgame", "both"], default="both")
    parser.add_argument("--token-env", default="XREADER_TOKEN",
                        help="从哪个环境变量读 token（默认 XREADER_TOKEN，退回 GITHUB_TOKEN）")
    parser.add_argument("--timeout", type=int, default=25, help="等多久算超时（分钟）")
    parser.add_argument("--no-wait", action="store_true", help="触发后立刻返回，不等完成")
    parser.add_argument("--no-pull", action="store_true", help="跑完不 git pull")
    parser.add_argument("--xreader", type=Path,
                        default=Path(os.environ.get("XREADER_DIR") or DEFAULT_XREADER))
    parser.add_argument("--report", action="store_true", help="只打印最近的调度延迟，不触发")
    parser.add_argument("--verify-only", action="store_true", help="只检查本地数据覆盖，不触发")
    parser.add_argument("--date", type=date.fromisoformat, default=None,
                        help="验证哪一天（JST），默认昨天")
    args = parser.parse_args(argv)

    kinds = ["voice", "galgame"] if args.kind == "both" else [args.kind]
    day = args.date or (datetime.now(JST).date() - timedelta(days=1))

    token = os.environ.get(args.token_env) or os.environ.get("GITHUB_TOKEN") or ""

    # --verify-only 只读本地文件；--report 只读公开的 run 列表——两条都不需要 token，
    # 所以放在 token 检查之前。
    if args.verify_only:
        return verify(args.xreader, day, kinds)

    if args.report:
        report(token)
        return 0

    if not token:
        print(
            f"没有 token：设 {args.token_env} 或 GITHUB_TOKEN。\n"
            "建一个 fine-grained PAT（只选 X-Reader 仓库）：\n"
            "  Actions      → Read and write\n"
            "  Contents     → Read（要顺带 pull 的话）\n"
            "  Metadata     → Read（自动带上）\n"
            "地址：https://github.com/settings/personal-access-tokens/new",
            file=sys.stderr,
        )
        return 2

    print(f"触发：{'、'.join(WORKFLOWS[k] for k in kinds)}（ref=main）")
    stamps = {kind: dispatch(kind, token) for kind in kinds}

    if args.no_wait:
        print("已触发，不等结果。稍后自己跑 `--verify-only` 检查覆盖。")
        return 0

    failed = []
    for kind in kinds:
        run = wait_for(kind, stamps[kind], token, args.timeout)
        if run.get("conclusion") != "success":
            failed.append((WORKFLOWS[kind], run.get("conclusion"), run.get("html_url")))
    if failed:
        for name, conclusion, url in failed:
            print(f"{name} 没成功（{conclusion}）：{url}", file=sys.stderr)
        return 4

    if not args.no_pull:
        code = pull(args.xreader)
        if code:
            return code

    return verify(args.xreader, day, kinds)


if __name__ == "__main__":
    raise SystemExit(main())
