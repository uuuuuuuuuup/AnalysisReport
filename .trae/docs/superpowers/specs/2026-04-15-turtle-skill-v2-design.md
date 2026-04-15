# turtle-investment-strategy SKILL.md 升级设计文档

**日期**：2026-04-15  
**版本**：SKILL.md v2.0  
**背景**：将旧版（主代理做所有事）升级为子代理架构 + 按数据类型接入东方财富 mx-* skills

---

## 目标

1. **子代理架构**：主代理只负责调度，Phase 1（市场数据）和 Phase 2（深度财务数据）分别由独立子代理并行执行
2. **东方财富 skill 接入**：按数据类型将 mx-macro-data / mx-finance-search / mx-financial-assistant / mx-finance-data 插入到各自擅长的数据采集环节

---

## 架构设计

### 角色分工

```
主代理（Coordinator）
  ├── 职责：输入解析、目录创建、子代理调度、等待汇聚、因子分析、写报告
  └── 不直接调用任何数据采集工具

子代理 1（Phase 1 Worker）
  └── 职责：采集市场数据（股价、三大报表、股息、K线、无风险利率、管理层、竞争格局）
      输出：data_pack_market.md

子代理 2（Phase 2 Worker）
  └── 职责：采集深度财务数据（报表附注、审计报告、关联方、非经常损益等）
      输出：data_pack_report.md
```

### 工作流

```
用户请求
  → 主代理解析 + 创建目录
  → 并行 Agent(子代理1) + Agent(子代理2)
  → 等待两个 data_pack 文件生成
  → 读取数据包 → 执行因子分析（1A/1B/2/3/4）
  → 写出最终报告
```

---

## 数据来源分工（East Finance Skills）

| 数据类型 | 第一来源 | 备用来源 |
|---------|---------|---------|
| 无风险利率（十年期国债收益率） | `mx-macro-data` | WebSearch |
| 公司公告（审计报告/分红公告） | `mx-finance-search` | AI-Tools GetFinancialReport |
| 券商研报 | `mx-finance-search` | search_reports MCP |
| 管理层/行业竞争/商业模式解读 | `mx-financial-assistant` | WebSearch |
| 实时股价/市值/股息率/股息历史 | `mx-finance-data` | AI-Tools QueryStockPriceInfo |
| 三大报表（利润表/资产负债/现金流） | AI-Tools MCP | `mx-finance-data` |
| 财务指标/关联方/受限现金详情 | AI-Tools GetFinancialIndicators | `mx-finance-data` |
| 历史月线 K 线 | AI-Tools GetMonthlyKLineData | `mx-finance-data` |
| MD&A 深度文本 | AI-Tools GetFinancialReport | `mx-financial-assistant` |

---

## 子代理 prompt 规范

子代理 prompt 需包含：
- 任务类型（Phase 1 or Phase 2）
- 输入参数（symbol, company_name, target_year, holding_channel, output_path）
- 详细采集清单（指明每个数据类型用哪个工具）
- 输出格式（标准化 markdown 文件）
- 数据来源标注要求

子代理完成后通过写文件与主代理通信（主代理轮询 Read 工具检查文件存在性）。

---

## 可用工具清单更新

现有：AI-Tools MCP（GetIncomeStatement 等），WebSearch，search_reports，文件操作工具

新增：
- `mx-macro-data`：宏观经济数据，用于无风险利率
- `mx-finance-search`：公告/研报/新闻搜索
- `mx-financial-assistant`：综合金融问答，用于定性信息
- `mx-finance-data`：结构化金融数据，用于行情/股息等

---

## 不变的部分

因子分析框架（1A/1B/2/3/4）内容完整保留，逻辑不变。  
输出报告格式、单位换算规则、变量索引等保持不变。

---

## 实现边界

- 修改文件：`skills/turtle-investment-strategy/SKILL.md`
- 不修改：V1.0.md / V1.1.md / V1.2.md / V1.3.md（历史版本保留）
- 策略规则目录只读原则：写 SKILL.md 本身除外
