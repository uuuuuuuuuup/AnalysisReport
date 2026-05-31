#!/bin/bash
# 投资组合周报一键执行脚本

set -e

PROJECT_DIR="/Users/apple/Documents/分析报告"
WATCH_DIR="${PROJECT_DIR}/每周复盘重点关注"
DATE=$(date +%Y-%m-%d)

echo "========================================"
echo "投资组合周报 - ${DATE}"
echo "========================================"
echo ""

# 创建必要目录
mkdir -p "${WATCH_DIR}/_weekly_data"
mkdir -p "${WATCH_DIR}/_summary"

# Step 1: 采集数据
echo "[Step 1/4] 采集最新股价数据..."
cd "${PROJECT_DIR}"
python3 "${WATCH_DIR}/scripts/fetch_weekly_data.py"
echo ""

# Step 2: 生成周报（需要用户在 Claude Code 中手动触发）
echo "[Step 2/4] 生成周报..."
echo "请在 Claude Code 中执行以下命令来生成周报："
echo ""
echo "    /weekly-review"
echo ""
echo "这将读取 latest_data.json 和原始分析报告，"
echo "为每家公司生成周报，并输出汇总报告。"
echo ""
read -p "按 Enter 键继续（生成周报后）..."
echo ""

# Step 3: 发送邮件
echo "[Step 3/4] 发送邮件..."
python3 "${WATCH_DIR}/scripts/send_email.py" "${DATE}"
echo ""

echo "========================================"
echo "周报流程完成: ${DATE}"
echo "========================================"
