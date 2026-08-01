---
name: gtht-lingxi-unified
description: 国泰海通灵犀统一金融数据 Skill，整合行情查询、市场榜单、自选股管理、金融数据查询、智能选股、策略回测、研报搜索等功能。触发关键词：股价、涨跌幅、行情、榜单、自选股、选股、回测、研报、财报、财务数据。
allowed-tools: ["node"]
version: 2.0.0
disable: false
---

**Agent 只需读取此文件，无需读取其他源码文件。**

# 国泰海通灵犀 (GTHT Lingxi) 统一 Skill v2.0.0

## 0. 最高优先级

### 0.1 授权先于一切调用

- 任何接口调用之前：必须先确认 `gtht-entry.json` 文件存在且 API Key 有效
- 查找顺序：当前 skill 目录下的 `gtht-entry.json`
- 若不存在或 Key 失效（4xx 错误）：必须先完成授权流程
- 用户可通过两种方式授权：
  1. **API Key 直接授权**（推荐）：`node skill-entry.js auth save <API_KEY>`
  2. **扫码授权**：`node skill-entry.js auth` 生成链接 → 扫码 → `node skill-entry.js auth poll <TOKEN>`

### 0.2 最终回答硬性要求

所有调用本 Skill 的回复末尾必须追加：

> 本Skill仅提供客观数据，调用后生成的内容不构成投资建议。

---

## 1. 概述

本 Skill 整合了国泰海通证券灵犀平台的 7 大核心能力：

| 能力 | 命令 | 说明 |
|------|------|------|
| 实时行情 | `marketdata` | 单只/批量 A股、港股、美股行情查询 |
| 市场榜单 | `ranklist` | 12维度A股全市场排行榜 |
| 自选股管理 | `watchlist` | 查询/添加/删除【我的自选】分组 |
| 金融数据 | `financial` | 自然语言查询财务、估值、技术指标 |
| 智能选股 | `stockselect` | 多指标组合条件选股 |
| 策略回测 | `backtest` | 选股策略历史回测 |
| 研报搜索 | `research` | 国泰海通研究所专业研究报告 |

---

## 2. 授权管理

```bash
# 直接保存 API Key（推荐）
node skill-entry.js auth save <API_KEY>

# 检查授权状态
node skill-entry.js auth check

# 扫码授权（生成链接）
node skill-entry.js auth

# 扫码后轮询
node skill-entry.js auth poll <TOKEN>

# 清除授权
node skill-entry.js auth clear
```

---

## 3. 命令详解

### 3.1 实时行情 (marketdata)

**功能**：查询单只或多只股票的实时行情数据

```bash
# 按代码查询
node skill-entry.js marketdata SH601211

# 按名称查询（自动查表获取代码）
node skill-entry.js marketdata 贵州茅台

# 批量查询
node skill-entry.js marketdata 贵州茅台 宁德时代 SH601211
```

**返回字段**：最新价、开盘价、最高价、最低价、涨跌幅、涨跌额、振幅、量比、成交量、成交额、换手率、当日资金净流入、总市值

---

### 3.2 市场榜单 (ranklist)

**功能**：查询 A 股全市场各类排行榜（固定范围 `BK101003`）

```bash
# 涨幅榜前20（默认）
node skill-entry.js ranklist

# 涨幅榜前10
node skill-entry.js ranklist --order-by=2 --limit=10

# 跌幅榜
node skill-entry.js ranklist --order-by=2 --sort=asc --limit=10

# 成交量榜
node skill-entry.js ranklist --order-by=9 --limit=10

# 成交额榜
node skill-entry.js ranklist --order-by=10 --limit=10

# 资金净流入榜
node skill-entry.js ranklist --order-by=11 --limit=10
```

**order_by 参数**：

| 值 | 维度 | 值 | 维度 |
|----|------|----|------|
| 0 | 最新价 | 6 | 总市值 |
| 1 | 涨跌值 | 7 | 市盈率 |
| 2 | 涨跌幅 | 8 | 量比 |
| 3 | 振幅 | 9 | 成交量 |
| 4 | 5分钟涨幅 | 10 | 成交额 |
| 5 | 换手率 | 11 | 当日资金净流入 |

**sorted_type**：`1`=降序(默认), `2`=升序

---

### 3.3 自选股管理 (watchlist)

**功能**：管理【我的自选】分组中的自选股

```bash
# 查看自选股列表+行情
node skill-entry.js watchlist list

# 添加自选股（支持代码和名称）
node skill-entry.js watchlist add 贵州茅台 SH601211

# 删除自选股
node skill-entry.js watchlist remove SH601211
```

⚠️ **删除操作必须先列出待删除股票，等待用户确认后再执行。**

---

### 3.4 金融数据查询 (financial)

**功能**：自然语言查询 A 股财务数据、估值指标、技术指标等

```bash
# 财务指标
node skill-entry.js financial "科大讯飞营业收入"
node skill-entry.js financial "贵州茅台净利润"
node skill-entry.js financial "比亚迪毛利率"

# 估值指标
node skill-entry.js financial "宁德时代市盈率"
node skill-entry.js financial "招商银行市净率"

# 批量查询
node skill-entry.js financial "查询科大讯飞营业收入和贵州茅台净利润"
```

---

### 3.5 智能选股 (stockselect)

**功能**：多指标组合条件选股

```bash
node skill-entry.js stockselect "涨幅大于5%且换手率大于3%的股票，按涨幅从高到低排序"
node skill-entry.js stockselect "ROE大于15%且市盈率低于20倍的股票"
node skill-entry.js stockselect "市值小于100亿的中小盘股"
```

---

### 3.6 策略回测 (backtest)

**功能**：对选股策略进行历史回测

```bash
# 使用默认参数回测
node skill-entry.js backtest "AI概念板块"

# 自定义参数
node skill-entry.js backtest --query "涨幅超5%的股票" --start-date 20240101 --end-date 20260630 --holding-period 10 --stock-hold 10 --day-buy 5
```

**回测默认参数**：
- 开始时间：三年前
- 结束时间：今天
- 持仓周期：10 天
- 持股上限：10 只
- 单日买入：5 只

---

### 3.7 研报搜索 (research)

**功能**：搜索国泰海通研究所专业研究报告

```bash
# 宏观策略
node skill-entry.js research "最新宏观经济研究报告"

# 行业深度
node skill-entry.js research "新能源汽车行业研究报告"
node skill-entry.js research "人工智能产业链深度分析"

# 策略观点
node skill-entry.js research "下半年A股市场策略观点"
```

---

## 4. 网关接口汇总

| 网关 | 地址 | 工具 |
|------|------|------|
| market | `https://zx.app.gtja.com:8443/mcp/marketdata` | `marketdata-tool` |
| ranklist | `https://zx.app.gtja.com:8443/mcp/hq-20200002` | `ranklist` |
| optionalStock | `https://zx.app.gtja.com:8443/mcp/optionalStock` | `get_optionalStock`, `op_optionalStock` |
| financial | `https://zx.app.gtja.com:8443/mcp/financialsearch/lingxi` | `financial-search` |
| researchReport | `https://zx.app.gtja.com:8443/mcp/researchReport/lingxi` | `search-research-report` |
| stockselect | `https://zx.app.gtja.com:8443/mcp/lingxi/financial` | `financial-search` |
| backtest | `https://zx.app.gtja.com:8443/mcp/lingxi/backtest` | `backtest` |
| mqtt | `https://zx.app.gtja.com:8443/mcp/mqtt` | `get-token` |

---

## 5. 文件结构

```
gtht-lingxi-unified/
├── SKILL.md              # 本文档
├── skill-entry.js        # 统一入口
├── gateway-config.json   # 网关配置
├── stock_code_name.json  # 股票名称→代码映射表
└── gtht-entry.json       # 授权文件（运行时生成）
```

---

## 6. Agent 使用流程 (SOP)

1. **检查授权**：`gtht-entry.json` 是否存在 → 不存在则引导授权
2. **匹配命令**：根据用户意图选择对应命令
3. **执行查询**：使用 `node skill-entry.js <命令> [参数]`
4. **返回结果**：格式化输出 + 固定免责声明

---

## 7. 错误码对照

| 错误码 | 含义 | 解决方案 |
|--------|------|----------|
| 401 | 未授权/Key 过期 | 重新授权 |
| 403 | 禁止访问 | 联系管理员 |
| 400 | 参数错误 | 检查参数格式 |
| 500 | 服务器错误 | 稍后重试 |
| 404 | 工具不存在 | 检查网关配置 |

---

## 8. 免责声明

> 本Skill仅提供客观数据，调用后生成的内容不构成投资建议。