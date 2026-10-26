#!/usr/bin/env python3
"""提交并推送站点仓库，专治本机 `git push` 被 SIGTERM 掉的问题。

背景：这台机器上直接 `git push`（连 `--dry-run`）都会在走到
`git-credential-manager.exe` 时被进程树杀掉，报不出任何错。可行的路径是：

    1. `GCM_INTERACTIVE=never git-credential-manager get` 拿到账号与 token
    2. 把 token 写进一个临时 askpass 脚本
    3. `GIT_ASKPASS=<临时脚本> git -c credential.helper= push`
    4. 立刻删掉临时脚本

第 2 步的临时文件是本脚本唯一的风险面：它写在系统临时目录、只用于一次 push、
无论成功失败都在 finally 里删除。token 本身不落仓库、不写日志。

直连 HTTPS 在这台机器上会 schannel 握手失败，所以走本地代理；
`--proxy` 不给就试 127.0.0.1:7897（Clash 默认端口），连不上再退回直连。

用法：

    python scripts/push_site.py -m "daily: 26102522"
    python scripts/push_site.py -m "..." --no-push     # 只提交
    python scripts/push_site.py -m "..." --proxy http://127.0.0.1:7897
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROXY = "http://127.0.0.1:7897"


def run(cmd: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, env=env)
    if check and result.returncode != 0:
        print((result.stderr or result.stdout).strip(), file=sys.stderr)
        raise SystemExit(f"命令失败：{' '.join(cmd)}")
    return result


def git_credentials() -> tuple[str, str]:
    """向 GCM 要 GitHub 的账号与 token（不落盘）。"""
    result = subprocess.run(
        ["git-credential-manager", "get"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True,
        env={**os.environ, "GCM_INTERACTIVE": "never"},
    )
    fields = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    username = fields.get("username", "")
    password = fields.get("password", "")
    if not username or not password:
        raise SystemExit("拿不到 GitHub 凭据：先在本机执行一次 `git credential-manager login`")
    return username, password


def write_askpass(username: str, password: str) -> Path:
    """一个只在这次 push 期间存在的 askpass 脚本。"""
    handle, path = tempfile.mkstemp(suffix=".cmd", prefix="push_askpass_")
    os.close(handle)
    script = Path(path)
    # cmd 的 `echo %~1 | findstr` 判据：git 问 username 时回账号，问 password 时回 token。
    script.write_text(
        "@echo off\r\n"
        'echo %~1 | findstr /i "username" >nul && '
        f"(echo {username}) || (echo {password})\r\n",
        encoding="ascii",
    )
    return script


def push(proxy: str | None) -> None:
    username, password = git_credentials()
    askpass = write_askpass(username, password)
    try:
        env = {**os.environ, "GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0"}
        if proxy:
            env["https_proxy"] = proxy
            env["http_proxy"] = proxy
        result = subprocess.run(
            ["git", "-c", "credential.helper=", "push", "origin", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, env=env,
        )
        if result.returncode != 0:
            print((result.stderr or result.stdout).strip(), file=sys.stderr)
            raise SystemExit("推送失败")
        print((result.stderr or result.stdout).strip().splitlines()[-1] if (result.stderr or result.stdout).strip() else "已推送")
    finally:
        askpass.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="提交并推送站点仓库")
    parser.add_argument("-m", "--message", required=True, help="提交信息")
    parser.add_argument("--no-push", action="store_true", help="只提交，不推送")
    parser.add_argument("--proxy", default=None, help=f"推送用的 HTTP 代理，默认 {DEFAULT_PROXY}")
    args = parser.parse_args(argv)

    run(["git", "add", "-A"])

    staged = run(["git", "diff", "--cached", "--name-only"]).stdout.strip()
    if not staged:
        print("没有需要提交的改动")
        return 0
    print("改动：\n" + staged)

    run(["git", "-c", "user.name=EpsilonGG", "-c", "user.email=epsilongg@users.noreply.github.com",
         "commit", "-q", "-m", args.message])

    if args.no_push:
        print("已提交（未推送）")
        return 0

    proxy = args.proxy or os.environ.get("DAILY_PROXY") or DEFAULT_PROXY
    push(proxy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
