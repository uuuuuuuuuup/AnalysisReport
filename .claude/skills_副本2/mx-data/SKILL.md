---
name: mx-data
description: >
  基于东方财富数据库，输出结构化数据文件（Excel、CSV、Markdown）。
  当用户意图为查数据、导数据、做量化筛选、获取宏观指标、可比公司分析时使用本技能：
  - 金融数据查数（--data-type finance）：个股/基金/债券/宏观等多实体指标查询，输出 xlsx + md
  - 宏观数据（--data-type macro）：GDP、CPI、货币等宏观数据，输出按频率分组的 csv + txt
  - 股票基金筛选（--data-type screener）：A股/港股/美股/基金/ETF/可转债/板块筛选，输出 csv + txt
  - 可比公司分析（--data-type comparable）：同业对比数据，输出 xlsx/csv
  触发词如「查一下」「导出数据」「选股」「筛选」「宏观数据」「可比公司」等。
  普通问答请使用 mx-assistant；生成完整报告请使用 mx-report。
---

# 结构化数据查询 (mx-data)

## 触发规则

- 用户要求查询金融数据并输出表格：「查一下贵州茅台、五粮液的营收」
- 用户要求筛选股票/基金/板块：「股价大于1000元的股票」「新能源板块」「白酒主题基金」
- 用户要求宏观数据：「中国近五年GDP」「CPI走势」
- 用户要求可比公司分析：「贵州茅台与五粮液的可比分析」

## 命令行

```bash
# 金融数据查数（多实体时必填 --indicators）
python3 {baseDir}/scripts/query_data.py --query "贵州茅台、五粮液近一年营收" --data-type finance --indicators "近一年营收"

# 宏观数据
python3 {baseDir}/scripts/query_data.py --query "中国近五年GDP" --data-type macro

# 股票基金筛选
python3 {baseDir}/scripts/query_data.py --query "股价大于1000元的股票" --data-type screener --select-type A股

# 可比公司分析
python3 {baseDir}/scripts/query_data.py --query "贵州茅台与五粮液的可比分析" --data-type comparable
```

## 参数说明

| 参数 | 必填 | 说明 |
|---|---|---|
| `--query` | 是 | 自然语言查询 |
| `--data-type` | 是 | `finance`、`macro`、`screener`、`comparable` |
| `--indicators` | finance 多实体时必填 | 从 query 提取的指标，不含实体名称 |
| `--select-type` | screener 必填 | `A股`、`港股`、`美股`、`基金`、`ETF`、`可转债`、`板块` |
| `--output-dir` | 否 | 输出目录覆盖 |

## 输出格式

脚本向 stdout 输出单一 JSON 对象：

```json
{
  "ok": true,
  "data_type": "finance|macro|screener|comparable",
  "query": "...",
  "files": ["..."],
  "row_count": 42,
  "csv_path": "...",
  "md_path": "...",
  "description_path": "...",
  "recognized_entity_count": 5,
  "returned_entity_count": 5,
  "completeness_warning": "..."
}
```

失败时：

```json
{
  "ok": false,
  "error_code": "MISSING_INDICATORS|API_ERROR|...",
  "message": "..."
}
```

## 输出文件

- `finance`: `miaoxiang/mx-data/mx_data_finance_<id>.xlsx` 与 `.md`
- `macro`: `miaoxiang/mx-data/mx_data_macro_<id>_<frequency>.csv` 与 `_description.txt`
- `screener`: `miaoxiang/mx-data/mx_data_screener_<id>.csv` 与 `_description.txt`
- `comparable`: `miaoxiang/mx-data/mx_data_comparable_<id>.xlsx` 与 `.csv`
