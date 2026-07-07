#!/bin/zsh
# 将 /tmp/notes_drafts/ 中的 11 篇读书笔记上传到思源笔记

set -e

SRC_DIR="/tmp/notes_drafts"
TARGET_DIR="/投资研究/02_知识库/投资经典/读书笔记/聪明的投资者读书笔记"

files=(
  "00_导览与核心箴言.md"
  "01_投资与投机：定义与预期收益.md"
  "02_通货膨胀、利率与长期回报.md"
  "03_股市历史、周期与估值水平.md"
  "04_防御型投资者：组合与股债配置.md"
  "05_防御型投资者：普通股选股原则.md"
  "06_积极型投资者：策略与方法.md"
  "07_市场波动、市场先生与心理纪律.md"
  "08_投资顾问、基金与投资者行为.md"
  "09_证券分析与财报陷阱.md"
  "10_安全边际、股息与股东关系.md"
)

for file in "${files[@]}"; do
  title="${file%.md}"
  path="${TARGET_DIR}/${title}"
  echo "Creating: ${path}"
  siyuan-sisyphus fs write --path "${path}" --markdown "$(cat "${SRC_DIR}/${file}")"
  echo "✅ Created: ${title}"
done

echo ""
echo "All 11 notes uploaded."
