#!/usr/bin/env python3
"""日报自动化第一步：拉抓取数据 → 校验新鲜度 → 生成骨架与 briefing。

这一步是**确定性**的，不碰模型。把它单独抽出来，是因为「今天到底有没有数据」
必须由脚本回答：如果让模型去判断，它会在没有数据的时候编出一期看起来正常的日报。

一天出**两份**，每份跑一次本脚本（`--kind` 选哪一版）：

    voice    声优版（声优 + 音声社团）    期号 YYMMDD    库 data/items
    galgame  Galgame 版（制造商 + 信息号）期号 YYMMDD-g  库 data-galgame/items

分工：

    本脚本（无 LLM）  拉数据 / 切 JST 窗口 / 数条数 / 生成骨架
    WorkBuddy（LLM）  `daily prompt --flat` 出题 → 写 answer/all.json → `daily apply` 判卷合并
                      （声优版还要多一道：`daily ja` 出 Ci-en 版）
    push_site.py      提交并推送

用法：

    python scripts/daily_prepare.py                 # 昨天的 JST 数据，声优版
    python scripts/daily_prepare.py --kind galgame  # 同一天的 Galgame 版
    python scripts/daily_prepare.py --date 2026-10-25
    python scripts/daily_prepare.py --no-pull       # 已经拉过，跳过 git

退出码：

    0  骨架已生成，可以填内容
    2  目标日在数据里没有任何条目 —— 抓取侧没跑或失败了，**不要**写这一期
       （Galgame 版第一次跑 `update-galgame.yml` 之前 `data-galgame/` 还不存在，
        也走这个码：跳过这一版，不要写空稿）
    3  抓取仓库拉取失败
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XREADER = REPO_ROOT.parent / "X-rss-workspace" / "X-Reader"
JST = timezone(timedelta(hours=9))

# kind → (期号后缀, 抓取仓库里的数据目录, 人话名字)
# 两版各有一份 JSONL 库：update.yml 写 data/，update-galgame.yml 写 data-galgame/。
# 目录名和期号后缀必须跟 `daily.issue` 保持一致，否则期号会和库对不上。
KINDS: dict[str, tuple[str, str, str]] = {
    "voice": ("", "data", "声优版"),
    "galgame": ("-g", "data-galgame", "Galgame 版"),
}

# 目标日只有 1-2 条时几乎肯定抓取失败（不是「大家都没发推」），提示一句。
SUSPICIOUSLY_FEW = 3


def jst_yesterday() -> date:
    return (datetime.now(JST).date() - timedelta(days=1))


def count_items(items_dir: Path, day: date) -> tuple[int, int]:
    """返回 (窗口内条数, 全部条数)。窗口是 JST 自然日 [00:00, 次日 00:00)。"""
    start = datetime.combine(day, datetime.min.time(), tzinfo=JST)
    end = start + timedelta(days=1)
    inside = total = 0
    for path in sorted(items_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw = record.get("published_at") or ""
                if not raw:
                    continue
                try:
                    moment = datetime.fromisoformat(raw)
                except ValueError:
                    continue
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                if start <= moment < end:
                    inside += 1
    return inside, total


def pull(xreader: Path) -> int:
    """`git pull --ff-only`。CI 每 12 小时提交一次 data/，本地必须先拉。"""
    if not (xreader / ".git").exists():
        print(f"{xreader} 不是 git 仓库，无法拉取（见 docs/daily-report-guide.md）", file=sys.stderr)
        return 3
    env = dict(os.environ)
    # 本机直连 GitHub 会 schannel 握手失败，走本地代理；CI 里没有这个变量就跳过。
    proxy = os.environ.get("DAILY_PROXY")
    if proxy:
        env.setdefault("https_proxy", proxy)
        env.setdefault("http_proxy", proxy)
    result = subprocess.run(
        ["git", "-C", str(xreader), "pull", "--ff-only", "--quiet"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print("git pull 失败：\n" + (result.stderr or result.stdout), file=sys.stderr)
        return 3
    print(f"已拉取 {xreader.name}：{(result.stdout or 'up to date').strip()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="日报自动化第一步：拉数据 + 出骨架")
    parser.add_argument(
        "--kind",
        choices=list(KINDS),
        default="voice",
        help="哪一版：voice=声优版（声优 + 音声社团，期号 YYMMDD）/ "
        "galgame=Galgame 版（制造商 + 信息号，期号 YYMMDD-g）。一天两版各跑一次",
    )
    parser.add_argument("--date", type=date.fromisoformat, default=None,
                        help="汇总哪一天（JST 自然日），默认昨天")
    parser.add_argument("--xreader", type=Path,
                        default=Path(os.environ.get("XREADER_DIR") or DEFAULT_XREADER),
                        help="X-Reader 的 checkout 路径")
    parser.add_argument("--no-pull", action="store_true", help="跳过 git pull")
    parser.add_argument("--force", action="store_true", help="允许覆盖已存在的期号")
    parser.add_argument("--new", action="store_true", help="同一天再出一期：排成 -2、-3")
    args = parser.parse_args(argv)

    suffix, data_name, label = KINDS[args.kind]
    day = args.date or jst_yesterday()
    xreader: Path = args.xreader
    items_dir = xreader / data_name / "items"

    if not args.no_pull:
        code = pull(xreader)
        if code:
            return code

    if not items_dir.exists():
        print(f"找不到 {items_dir}：{label}还没有任何抓取数据", file=sys.stderr)
        if args.kind == "galgame":
            print(
                "Galgame 版由 update-galgame.yml 抓（03:10 / 15:10 UTC，写 data-galgame/）。"
                "它第一次跑完之前这个目录不存在——跳过这一版，不要写空稿。",
                file=sys.stderr,
            )
        return 2

    inside, total = count_items(items_dir, day)
    print(f"{label} · {day} (JST) 窗口内 {inside} 条 / 全部 {total} 条")
    if inside == 0:
        print(
            f"\n{day} 没有任何条目，不生成这一期（{label}）。\n"
            "先确认抓取任务跑了：https://github.com/EpsilonGG/X-Reader/actions",
            file=sys.stderr,
        )
        return 2
    if inside < SUSPICIOUSLY_FEW:
        print(f"注意：只有 {inside} 条，可能抓取不完整，建议看一眼 briefing 再决定", file=sys.stderr)

    # 不再传 `--at`：期号只到天，`issue.published_at` 取真实运行时刻
    # （旧做法是钉一个名义 22:00，比真实出稿早约 3.5 小时）
    cmd = [
        sys.executable, str(REPO_ROOT / "scripts" / "daily_digest.py"),
        "--kind", args.kind,
        "--items-dir", str(items_dir),
        "--date", day.isoformat(),
    ]
    if args.force:
        cmd.append("--force")
    if args.new:
        cmd.append("--new")

    print("运行：" + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        return result.returncode

    issue_id = day.strftime("%y%m%d") + suffix
    note = f"（--new 时目录是 {issue_id}-2）" if args.new else ""
    print(f"\n骨架：out/{issue_id}/report.json{note}（定稿后 publish 到 data/daily/）")
    print(f"简报：out/{issue_id}.briefing.txt")
    print(f"下一步：python scripts/daily_digest.py prompt --issue {issue_id} --flat")
    print(f"        → 写 out/{issue_id}/answer/all.json")
    print(f"        → python scripts/daily_digest.py apply --issue {issue_id} --answer out/{issue_id}/answer/all.json")
    if args.kind == "voice":
        print(f"        → python scripts/daily_digest.py ja --issue {issue_id}   # Ci-en 版（声优版才有）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
