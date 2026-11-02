"""M4.1 长图：`data/daily/<期号>/report.json` → `public/images/daily/<期号>.webp`。

`publish` 写完正本后调这里，站点页把这张图插在「作品动态」后面。
渲染器是 `scripts/daily-image/render.mjs`（HTML + 本机 Edge 截图，1080 宽 ×2，
截图拿到 PNG 缓冲后压成 WebP q92：同尺寸约 660KB，直出 PNG 要 1.6–1.8MB）。

为什么不放进 `publish.py` 里直接画：那一步是「搬文件」，画图要起浏览器、要 node，
失败原因和搬运完全不同。分开之后 `publish` 能决定「图挂了还要不要继续发」。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "daily-image" / "render.mjs"
DEFAULT_DEST = REPO_ROOT / "public" / "images" / "daily"


class ImageError(RuntimeError):
    pass


def _node() -> str | None:
    """优先 PATH，其次 Windows 的默认安装位置。

    自动化里不一定继承了交互式 shell 的 PATH，直接写死 `node` 会在最需要它的
    那一次失败。
    """
    found = shutil.which("node")
    if found:
        return found
    for candidate in (
        Path(r"C:\Program Files\nodejs\node.exe"),
        Path(r"C:\Program Files (x86)\nodejs\node.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def image_path(issue_id: str, *, dest_root: str | Path = DEFAULT_DEST) -> Path:
    return Path(dest_root) / f"{issue_id}.webp"


def render(issue_id: str, *, dest_root: str | Path = DEFAULT_DEST) -> Path:
    """出图，返回落盘路径。失败抛 `ImageError`。"""
    node = _node()
    if node is None:
        raise ImageError("找不到 node。装 Node 或把 node 加进 PATH 后重跑。")

    dest = image_path(issue_id, dest_root=dest_root)
    dest.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [node, str(SCRIPT), issue_id, "--final", f"--out={dest}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or not dest.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ImageError(detail.splitlines()[-1] if detail else f"渲染失败（exit {proc.returncode}）")
    return dest
