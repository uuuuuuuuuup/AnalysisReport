---
name: mx-report
description: >
  依托东方财富数据库，生成深度研究报告类内容并保存 PDF/DOCX 附件。
  当用户明确要求生成报告、点评、跟踪研究时使用此技能：
  - 行业研究 / 产业报告（--report-type industry）
  - 主题研究 / 概念研究（--report-type topic）
  - 首次覆盖 / 深度研究（--report-type coverage）
  - 行业/个股跟踪报告（--report-type tracker）
  - 上市公司业绩点评 / 财报点评（--report-type earnings）
  触发词如「行业研究」「主题报告」「首次覆盖」「深度研究」「跟踪报告」「业绩点评」「财报点评」等。
  普通问答请使用 mx-assistant；仅查数/结构化文件请使用 mx-data。
---

# 研究报告生成 (mx-report)

## 触发规则

当用户意图为生成以下类型报告时触发：

- 行业/产业研究报告：「半导体行业研究」「新能源汽车产业报告」
- 主题/概念研究报告：「AI芯片主题研究」「低空经济研究报告」
- 首次覆盖/深度研究：「深度研究贵州茅台」「首次覆盖宁德时代」
- 行业/个股跟踪报告：「跟踪半导体行业」「跟踪个股表现」
- 业绩点评/财报点评：「贵州茅台业绩点评」「XX公司年报点评」

## 命令行

```bash
python3 {baseDir}/scripts/generate_report.py --query "行业/主题/个股" --report-type industry
python3 {baseDir}/scripts/generate_report.py --query "低空经济" --report-type topic
python3 {baseDir}/scripts/generate_report.py --query "贵州茅台" --report-type coverage
python3 {baseDir}/scripts/generate_report.py --query "半导体行业" --report-type tracker
python3 {baseDir}/scripts/generate_report.py --query "贵州茅台 2025年报" --report-type earnings
```

## 输出格式

脚本向 stdout 输出单一 JSON 对象：

```json
{
  "ok": true,
  "report_type": "industry|topic|coverage|tracker|earnings",
  "query": "...",
  "title": "报告标题",
  "content": "Markdown 正文或总结",
  "share_url": "...",
  "article_id": "...",
  "entity_type": "...",
  "attachments": [
    {"type": "PDF", "path": "..."},
    {"type": "DOCX", "path": "..."}
  ]
}
```

失败时：

```json
{
  "ok": false,
  "error_code": "ERROR_ENTITY|API_ERROR|...",
  "message": "..."
}
```

## 注意事项

- `earnings` 类型会先进行实体识别与报告期匹配，默认取最新可用报告期。
- 禁止后台异步执行；脚本在当前会话同步完成。
- 附件路径为本地绝对路径，不可作为网络 URL 直接访问。
