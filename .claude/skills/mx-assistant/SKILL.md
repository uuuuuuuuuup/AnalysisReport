---
name: mx-assistant
description: >
  基于东方财富权威金融数据库的智能问答服务，覆盖数据、资讯、知识、分析、决策全链条。
  当用户提出自然语言问题并希望获得即时回答时使用此技能，例如查数据、问行情、求解释、做总结、选股票/基金、问宏观、问政策等。
  支持标准模式和深度思考模式（--deep-think）。
  不适用需要生成完整报告、保存附件或输出结构化文件的场景；那些场景请使用 mx-report / mx-data / mx-diagnosis / mx-search。
---

# 金融问答 (mx-assistant)

## 触发规则

当用户提出以下任一类型问题时触发本技能：

- 查询具体金融数据、行情、估值、财务指标。
- 询问个股/基金/债券/宏观/行业基本情况或走势。
- 请求解释概念、政策、术语、交易规则。
- 请求总结资讯、公告、研报要点。
- 自然语言选股、选基、筛选板块。
- 询问"XX怎么样"、"分析一下"、"帮我查一下"、"解释一下"。

**不触发本技能的场景：**

- 要求生成行业/主题/首次覆盖/跟踪/业绩点评等完整报告（使用 `mx-report`）。
- 要求输出 Excel/CSV/结构化数据文件（使用 `mx-data`）。
- 要求诊断单只股票/基金/市场热点（使用 `mx-diagnosis`）。
- 要求财经资讯搜索（使用 `mx-search`）。

## 命令行

```bash
python3 {baseDir}/scripts/ask.py --query "用户问题"
python3 {baseDir}/scripts/ask.py --query "用户问题" --deep-think
```

## 输出格式

脚本向 stdout 输出单一 JSON 对象：

```json
{
  "ok": true,
  "tool": "金融问答",
  "question": "用户问题",
  "deep_think": false,
  "answer": "Markdown 格式回答",
  "references": [
    {"refId": 1, "type": "查数", "referenceType": "CITED_REFERENCE", "markdown": "..."},
    {"refId": 2, "type": "资讯", "referenceType": "CITED_REFERENCE", "title": "...", "jumpUrl": "...", "source": "..."}
  ]
}
```

失败时：

```json
{
  "ok": false,
  "error_code": "API_ERROR|TIMEOUT|...",
  "message": "金融问答服务暂时不可用，请稍后重试。"
}
```

## 引用展示规范

- 不要在条目前添加 `[1]`、`[2]` 等 refId 编号前缀。
- 查数/选股数据直接展示 `markdown` 表格内容。
- 资讯/公告/研报按 `{title}`（`{source}`）或 `[{title}]({jumpUrl})` 展示。
