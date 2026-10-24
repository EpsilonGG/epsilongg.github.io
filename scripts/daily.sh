#!/usr/bin/env bash
# 本地一键生成「日报草稿」：组装 + 产出待填 AI 摘要的 Markdown。
# 注意：LLM 摘要这一步由本地 WorkBuddy 完成（脚本只做无 LLM 的确定性组装）。
#
# 用法：
#   ./scripts/daily.sh [DATE] [X-READER_ITEMS_DIR]
#
# 示例：
#   ./scripts/daily.sh                       # 今天，使用仓库内样例数据
#   ./scripts/daily.sh 2026-10-24             # 指定日期
#   ./scripts/daily.sh 2026-10-24 /c/.../X-Reader/data/items   # 指定真实数据
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATE="${1:-$(date +%F)}"
ITEMS_DIR="${2:-}"

# Windows / Git Bash 上的 Python 可能叫 python、py 或带完整路径；按需修改下面这行。
PY="${PYTHON:-python3}"

echo "=== 步骤 1（可选）：运行 X-Reader 抓取 ==="
echo "X-Reader 的 GitHub Actions 已每日自动抓取并提交 data/；本地通常可跳过此步。"

echo "=== 步骤 2：组装日报 Markdown（含 AI 摘要占位）==="
if [ -n "$ITEMS_DIR" ]; then
  "$PY" "$SCRIPT_DIR/daily_digest.py" --items-dir "$ITEMS_DIR" --date "$DATE"
else
  echo "未提供 X-Reader 的 items 目录，使用仓库内样例数据预览："
  "$PY" "$SCRIPT_DIR/daily_digest.py" --items-dir "$SCRIPT_DIR/sample_items" --date "$DATE"
fi

echo
echo "=== 步骤 3：让本地 WorkBuddy 填写 AI 摘要 ==="
echo "对 WorkBuddy 说：\"填写今天的日报 AI 摘要\"，它会读取 briefing 并把"
echo "  $REPO_ROOT/src/content/daily/$DATE.md  里的 <!--AI_SUMMARY--> 替换为中文摘要。"
echo
echo "=== 步骤 4：提交并推送 ==="
echo "  git add src/content/daily/$DATE.md && git commit -m \"daily: $DATE\" && git push"
