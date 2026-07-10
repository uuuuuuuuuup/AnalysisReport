---
name: mx-search
description: >
  基于东方财富数据库，搜索全网财经资讯、公告、研报、新闻、政策等。
  当用户明确要求搜索资讯、公告、研报、新闻，或需要最新市场动态时使用此技能。
  触发词如「搜索」「查找」「最新资讯」「公告」「研报」「新闻」「政策」等。
  普通问答请使用 mx-assistant；结构化查数请使用 mx-data。
---

# 金融资讯搜索 (mx-search)

## 触发规则

- 用户要求搜索财经资讯：「搜索贵州茅台最新公告」「查找新能源行业研报」
- 用户要求最新市场动态：「最近有什么财经新闻」「最新政策」
- 用户要求查找特定事件报道：「XX事件相关资讯」

## 命令行

```bash
python3 {baseDir}/scripts/search.py --query "贵州茅台最新公告"
```

## 输出格式

脚本向 stdout 输出单一 JSON 对象：

```json
{
  "ok": true,
  "query": "...",
  "content": "搜索到的文本内容",
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

## 输出文件

默认保存到 `miaoxiang/mx-search/mx_search_<id>.txt`。

## 注意事项

- 返回内容来自 `searchNews` 接口的 `llmSearchResponse` / `searchResponse` / `content` / `answer` / `summary` 字段。
- 不要尝试解析或补充未返回的内容。
