#!/usr/bin/env bash
# 本地一键生成「日报草稿」：组装 + 产出待填内容的 Markdown。
# 注意：写摘要这一步由本地 WorkBuddy 完成（脚本只做无 LLM 的确定性组装）。
#
# 期号 = 被覆盖的那一天，格式 YYMMDD（日本时间）。
# 例：2026-10-31 那一期 → 261031，正本 out/261031/report.json。
# 期号里没有小时：一天的数据要到 JST 24:00 才闭合，真实出稿在次日凌晨，
# 所以真实发布时刻另存 issue.published_at（--at），不写进期号。
# 同一天要出第二期时加 --new，排成 261031-2。
#
# 用法：
#   ./scripts/daily.sh [DATE] [X-READER_ITEMS_DIR]
#
# 环境变量：
#   AT="2026-10-31 22:00"  写进 issue.published_at 的真实发布时间（JST），默认取当前时刻
#   PYTHON=/path/to/python 指定解释器
#
# 示例：
#   ./scripts/daily.sh                       # 今天，使用仓库内样例数据
#   ./scripts/daily.sh 2026-10-24             # 汇总 10-24 的数据，期号 261024
#   AT="2026-10-24 21:00" ./scripts/daily.sh 2026-10-24   # 同一期，只是把发布时间写成 21:00
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATE="${1:-$(date +%F)}"
ITEMS_DIR="${2:-}"
AT="${AT:-}"

# Windows / Git Bash 上的 Python 可能叫 python、py 或带完整路径；按需修改下面这行。
PY="${PYTHON:-python3}"

# 期号与 daily_digest.py 用同一套规则（JST），两处必须一致：期号就是 DATE 那一天
ISSUE_ID="$(TZ=Asia/Tokyo date -d "$DATE" +%y%m%d)"
if [ -n "$AT" ]; then
  AT_ARGS=(--at "$AT")
else
  AT_ARGS=()
fi

echo "=== 步骤 1（可选）：运行 X-Reader 抓取 ==="
echo "X-Reader 的 GitHub Actions 已每日自动抓取并提交 data/；本地通常可跳过此步。"

echo "=== 步骤 2：组装日报骨架（期号 $ISSUE_ID）==="
if [ -n "$ITEMS_DIR" ]; then
  "$PY" "$SCRIPT_DIR/daily_digest.py" --items-dir "$ITEMS_DIR" --date "$DATE" ${AT_ARGS[@]+"${AT_ARGS[@]}"}
else
  echo "未提供 X-Reader 的 items 目录，使用仓库内样例数据预览："
  "$PY" "$SCRIPT_DIR/daily_digest.py" --items-dir "$SCRIPT_DIR/sample_items" --date "$DATE" ${AT_ARGS[@]+"${AT_ARGS[@]}"}
fi

echo
echo "=== 步骤 3：出题 → 答题 → 判卷合并（M3.9 起）==="
echo "  python scripts/daily_digest.py prompt --issue $ISSUE_ID --flat"
echo "     → 题面 out/$ISSUE_ID/prompts/all.md（每条材料带来源 key）"
echo "  python scripts/daily_digest.py apply --issue $ISSUE_ID --answer out/$ISSUE_ID/answer/all.json"
echo "     → 回答不合格会逐条列出，改完再跑；通过才写进 out/$ISSUE_ID/report.json"
echo "回答里要写四个地方："
echo "    summary           今日看点的简报（≤60 字，会当页面副标题）"
echo "    works             作品动态（一段话，不带来源链接）"
echo "    interactions      名单内多人互动（没有就留空数组）"
echo "    people[].summary  每人一句话（留空 = 当日无活动，不渲染）"
echo
echo "=== 步骤 4：定稿、发布、提交 ==="
echo "  python scripts/daily_digest.py confirm --issue $ISSUE_ID   # 定稿前会再判一次卷"
echo "  python scripts/daily_digest.py publish --issue $ISSUE_ID   # 搬到 data/daily/，站点才读得到"
echo "  python scripts/push_site.py -m \"daily: $ISSUE_ID\" --path data/daily/"
echo "  （不要直接 git push：本机走到 credential-manager 会被 SIGTERM 掉；"
echo "    带 --path 是为了只提交这一期，别把工作区里其它改动卷进来）"
echo
echo "网址：/daily/$ISSUE_ID/    归档：/daily/    订阅：/daily/rss.xml"
