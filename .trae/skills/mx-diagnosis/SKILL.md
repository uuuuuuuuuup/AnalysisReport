---
name: mx-diagnosis
description: >
  基于东方财富数据库，对单只股票、单只基金或市场热点进行诊断式分析。
  当用户意图为"诊断""分析"某只股票/基金，或发现/解读市场热点时触发本技能：
  - 股票诊断（--asset-type stock）：个股技术面、基本面、消息面诊断
  - 基金诊断（--asset-type fund）：单只基金业绩、持仓、风险诊断
  - 市场热点发现（--asset-type hotspot）：市场热点挖掘与解读
  触发词如「诊断」「个股分析」「基金分析」「市场热点」「热点解读」等。
  普通问答请使用 mx-assistant；生成完整报告请使用 mx-report。
---

# 诊断分析 (mx-diagnosis)

## 触发规则

- 用户点名具体股票并要求分析/诊断：「诊断贵州茅台」「分析一下比亚迪」
- 用户点名具体基金并要求分析/诊断：「诊断易方达蓝筹」「这只基金怎么样」
- 用户要求发现/解读市场热点：「最近市场热点是什么」「解读一下AI板块热点」

## 命令行

```bash
python3 {baseDir}/scripts/diagnose.py --query "贵州茅台" --asset-type stock
python3 {baseDir}/scripts/diagnose.py --query "易方达蓝筹" --asset-type fund
python3 {baseDir}/scripts/diagnose.py --query "近期市场热点" --asset-type hotspot
```

## 输出格式

脚本向 stdout 输出单一 JSON 对象，`content` 字段为 Markdown 诊断内容：

```json
{
  "ok": true,
  "asset_type": "stock|fund|hotspot",
  "question": "...",
  "content": "Markdown 诊断内容",
  "output_path": "..."
}
```

失败时：

```json
{
  "ok": false,
  "error_code": "API_ERROR|...",
  "message": "..."
}
```
