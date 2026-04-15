# turtle-investment-strategy SKILL.md v2.0 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `SKILL.md` 从"主代理做所有事"升级为"主代理只调度 + 子代理并行采集数据 + 按数据类型使用东方财富 mx-* skills"

**Architecture:** 主代理只做输入解析、目录创建、子代理调度、因子分析和报告输出。两个子代理并行运行（Phase 1 市场数据、Phase 2 深度财务），各自调用对应数据源写出 data_pack 文件。东方财富 mx-* skills 按数据类型分工：mx-macro-data 取无风险利率、mx-finance-search 取公告/研报、mx-financial-assistant 取定性信息、mx-finance-data 取实时行情/股息。

**Tech Stack:** Markdown（skill 文件）、AI-Tools MCP、东方财富 mx-* Skill 工具（mx-finance-data / mx-finance-search / mx-financial-assistant / mx-macro-data）

---

## 文件映射

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改（完整重写） | `skills/turtle-investment-strategy/SKILL.md` | 主文件 |
| 参考（只读） | `skills/turtle-investment-strategy/V1.3.md` | 已有子代理架构，因子分析内容来源 |
| 参考（只读） | `skills/mx-finance-data/SKILL.md` | 调用语法参考 |
| 参考（只读） | `skills/mx-finance-search/SKILL.md` | 调用语法参考 |
| 参考（只读） | `skills/mx-financial-assistant/SKILL.md` | 调用语法参考 |
| 参考（只读） | `skills/mx-macro-data/SKILL.md` | 调用语法参考 |

---

## Task 1：备份当前 SKILL.md

**Files:**
- Read: `skills/turtle-investment-strategy/SKILL.md`（先读取）
- Create: `skills/turtle-investment-strategy/V1.4-legacy.md`（备份）

- [ ] **Step 1：读取当前 SKILL.md**

  使用 Read 工具读取：`/Users/apple/Documents/分析报告/.trae/skills/turtle-investment-strategy/SKILL.md`

- [ ] **Step 2：将当前内容复制为 V1.4-legacy.md**

  使用 Write 工具将 SKILL.md 完整内容写入：`/Users/apple/Documents/分析报告/.trae/skills/turtle-investment-strategy/V1.4-legacy.md`

  文件头加一行注释：
  ```markdown
  <!-- 备份：SKILL.md 升级为 v2.0 之前的版本，保存于 2026-04-15 -->
  ```

---

## Task 2：写新 SKILL.md 第一部分（frontmatter + 架构 + 主代理流程）

**Files:**
- Modify（重写）: `skills/turtle-investment-strategy/SKILL.md`

- [ ] **Step 1：使用 Write 工具写入 SKILL.md（第一部分）**

  写入以下内容到 `SKILL.md`，**完全覆盖原文件**：

  ````markdown
  ---
  name: "turtle-investment-strategy"
  description: "Executes multi-phase stock analysis using Turtle Investment Strategy v2.0. Sub-agent architecture: main agent orchestrates only, Phase 1 & Phase 2 worker agents collect data in parallel. Integrates East Finance mx-* skills by data type. Invoke when user requests stock analysis, asks to evaluate a company, or uploads annual report PDF with stock name/code."
  ---

  # 龟龟投资策略分析助手 v2.0

  ## 技能描述

  本技能实现龟龟投资策略框架，通过**主代理+子代理**的多代理架构对股票进行深度价值分析，并按数据类型接入东方财富 mx-* skills。适用于：
  - 用户请求分析某只股票
  - 用户询问是否应该买入某只股票
  - 用户需要估值分析和安全边际评估

  ---

  ## 架构设计

  ### 角色分工

  **主代理（Coordinator）**
  - 输入解析与任务调度
  - 创建输出目录
  - 并行启动子代理（使用 Agent 工具）
  - 等待子代理写出数据包文件后汇聚结果
  - 执行因子分析（Phase 3）
  - 生成最终报告

  ⚠️ **主代理不直接调用任何数据采集工具，所有数据采集由子代理完成**

  **子代理 1（Phase 1 Worker）**
  - 采集市场数据：股价、三大报表、股息历史、K 线、无风险利率、管理层信息、行业竞争格局
  - 输出：`data_pack_market.md`

  **子代理 2（Phase 2 Worker）**
  - 采集深度财务数据：报表附注、审计报告、关联方交易、非经常损益、研报
  - 输出：`data_pack_report.md`

  ### 工作流程图

  ```
  用户请求
      ↓
  主代理：输入解析 + 目标年份确定
      ↓
  主代理：mkdir 创建输出目录
      ↓
  主代理：Agent 工具（并行启动两个子代理）
      ├─→ 子代理 1（Phase 1）→ data_pack_market.md
      └─→ 子代理 2（Phase 2）→ data_pack_report.md
      ↓
  主代理：Read 工具轮询，等待两个文件生成
      ↓
  主代理：读取数据包，验证完整性
      ↓
  主代理：执行因子分析（1A → 1B → 2 → 3 → 4）
      ↓
  主代理：写出最终报告
  ```

  ---

  ## 触发条件

  当用户输入包含以下任一情况时，立即调用本技能：
  1. 股票代码或名称（如"分析平安银行"、"000001"、"长和"）
  2. 询问估值、安全边际、是否值得买入等问题
  3. 提到"龟龟投资策略"或"turtle strategy"

  ---

  ## 主代理执行流程

  ### 第一阶段：输入解析

  从用户消息中提取：
  1. **股票代码/名称**：识别目标股票
  2. **持股渠道**：港股通/直接持有/美股券商（未指定则用默认值）
  3. **目标年份**：
     - 当前月份 ≤ 3 月 → target_year = 当前年份 - 2
     - 当前月份 ≥ 4 月 → target_year = 当前年份 - 1

  ### 第二阶段：创建输出目录

  ```bash
  mkdir -p {workspace}/龟龟投资策略分析报告/{symbol}/
  ```

  ### 第三阶段：并行启动子代理

  使用 Agent 工具并行启动两个子代理（设置 run_in_background=true 可同时运行）。

  **子代理 1 完整 prompt**：

  ```
  你是龟龟投资策略的 Phase 1 市场数据采集子代理。请严格按照以下规范采集数据，写出标准化 markdown 文件。

  ═══ 输入参数 ═══
  股票代码：{symbol}
  公司名称：{company_name}
  持股渠道：{holding_channel}
  目标年份：{target_year}
  输出路径：{workspace}/龟龟投资策略分析报告/{symbol}/data_pack_market.md

  ═══ 数据来源（按数据类型分工）═══

  1. 无风险利率（十年期国债收益率）
     → 第一来源：mx_macro_data Skill（查询："[对应市场] 十年期国债收益率"）
     → 备用：WebSearch 搜索"中国十年期国债收益率 最新"

  2. 实时股价/市值/股息率/股息历史/回购历史
     → 第一来源：mx_finance_data Skill（自然语言查询）
     → 备用：AI-Tools MCP QueryStockPriceInfo + GetFinancialIndicators

  3. 三大报表近5年（利润表/资产负债表/现金流量表）+ 财务比率
     → 第一来源：AI-Tools MCP
       * GetIncomeStatement（利润表）
       * GetBalanceSheet（资产负债表）
       * GetCashFlowStatement（现金流量表）
       * GetFinancialIndicators（财务比率）
     → 备用：mx_finance_data Skill

  4. 历史月线价格（近5年）
     → 第一来源：AI-Tools MCP GetMonthlyKLineData（period='5y', interval='1mo'）
     → 备用：mx_finance_data Skill

  5. 管理层与治理信息（CEO/CFO/董事长/控股股东/股权结构）
     → 第一来源：mx_financial_assistant Skill
       查询1："[公司名] 管理层 CEO CFO 董事长 任期 持股比例"
       查询2："[公司名] 控股股东 持股比例 股权结构"
     → 备用：WebSearch

  6. 行业与竞争格局（行业规模/增速/主要竞争对手/市场份额）
     → 第一来源：mx_financial_assistant Skill
       查询："[公司名] 行业地位 市场份额 主要竞争对手 护城河"
     → 备用：mx_finance_search Skill 搜索行业研报

  7. MD&A 摘要（经营回顾/前瞻指引/风险因素）
     → 第一来源：AI-Tools MCP GetFinancialReport
     → 备用：mx_financial_assistant Skill 查询"[公司名] [target_year] 年报 MD&A 经营回顾"

  8. 上市结构与税务信息
     → 第一来源：mx_financial_assistant Skill
       查询："[公司名] 上市地点 [持股渠道] 股息税率 代扣代缴"
     → 备用：WebSearch

  9. 子公司数据（仅控股公司）
     → 第一来源：mx_finance_data Skill
     → 备用：AI-Tools MCP GetFinancialReport

  ═══ 输出文件规范 ═══

  文件头部必须包含：
  - 数据采集时间（时间戳）
  - 金额单位：报表币种百万元（除非另有标注）
  - 数据来源标注（每个数据项标注实际使用的工具）

  缺失项标注格式：⚠️未找到：{项目名}

  文件结构：
  ## 一、基础市场数据（股价/市值/股息/回购）
  ## 二、财务报表数据（利润表/资产负债/现金流，近5年）
  ## 三、历史价格数据（月线）
  ## 四、无风险利率
  ## 五、上市结构与税务
  ## 六、管理层与治理信息
  ## 七、行业与竞争格局
  ## 八、子公司数据（控股公司适用，否则跳过）
  ## 九、MD&A 摘要
  ## 十、数据完整性检查（缺失项列表 + 完整度评估）
  ```

  **子代理 2 完整 prompt**：

  ```
  你是龟龟投资策略的 Phase 2 深度财务数据采集子代理。请严格按照以下规范采集数据，写出标准化 markdown 文件。

  ═══ 输入参数 ═══
  股票代码：{symbol}
  公司名称：{company_name}
  目标年份：{target_year}
  输出路径：{workspace}/龟龟投资策略分析报告/{symbol}/data_pack_report.md

  ═══ 数据来源（按数据类型分工）═══

  1. 母公司单体报表/报表附注（资产明细/负债明细/权益明细）
     → 第一来源：AI-Tools MCP
       * GetBalanceSheet（含单体报表）
       * GetCashFlowStatement（详细版）
       * GetFinancialIndicators（受限现金/应收账款周转/坏账计提/关联方交易/定期存款）
     → 备用：mx_finance_data Skill

  2. 审计报告（审计意见类型/审计师名称/关键审计事项/审计师更换历史）
     → 第一来源：mx_finance_search Skill
       搜索1："[公司名] [target_year] 审计报告 审计意见"
       搜索2："[公司名] [target_year] 年报公告"
     → 备用：AI-Tools MCP GetFinancialReport

  3. 券商研报（用于验证数据和补充定性分析）
     → 第一来源：mx_finance_search Skill
       搜索："[公司名] [target_year] 年报点评 业绩 研报"
     → 备用：search_reports MCP（keywords="{公司名}"）

  4. MD&A 深度（经营回顾/前瞻指引/资本配置意图/风险因素）
     → 第一来源：AI-Tools MCP GetFinancialReport
     → 备用：mx_financial_assistant Skill 查询"[公司名] [target_year] 年报 前瞻指引 资本配置"

  5. 非经常性损益明细（资产处置/政府补贴/投资收益/公允价值变动）
     → 第一来源：AI-Tools MCP GetFinancialReport + GetIncomeStatement
     → 备用：mx_finance_search Skill 搜索公告

  6. 股息分配历史（历年股息总额/归母净利润/支付率）
     → 第一来源：mx_finance_data Skill（查询"[公司名] 历年股息 分红 支付率"）
     → 备用：AI-Tools MCP GetFinancialReport

  7. 有息负债明细（银行贷款/债券/关联方借款/资本化利息/或有负债）
     → 第一来源：AI-Tools MCP GetBalanceSheet + GetFinancialIndicators
     → 备用：mx_finance_search Skill（搜索公告）

  ═══ 输出文件规范 ═══

  文件头部必须包含：
  - 数据采集时间（时间戳）
  - 金额单位：报表币种百万元
  - 数据来源标注

  缺失项标注格式：⚠️未找到：{项目名}

  文件结构：
  ## 一、母公司单体资产负债表数据
  ## 二、受限现金与应收账款明细
  ## 三、负债详细信息（有息负债/资本化利息/或有负债）
  ## 四、MD&A 深度信息
  ## 五、审计相关信息
  ## 六、非经常性损益明细
  ## 七、股息分配信息
  ## 八、关联方交易信息
  ## 九、定期存款与理财产品
  ## 十、数据完整性检查
  ```

  ### 第四阶段：监控子代理状态

  主代理使用 Read 工具检查输出文件是否生成：
  - 检查 `data_pack_market.md`：存在且非空 → Phase 1 完成
  - 检查 `data_pack_report.md`：存在且非空 → Phase 2 完成
  - 若 data_pack_market.md 缺失超过合理时间 → 通知用户，可选择重试
  - data_pack_report.md 可选，若缺失则使用降级方案继续分析

  ### 第五阶段：数据包整合

  ```
  1. 读取 data_pack_market.md
  2. 检查文件头部单位标注（百万元 / 千元 / 万元）
  3. 读取 data_pack_report.md（若存在）
  4. 汇总缺失项列表
  5. 将数据传递给因子分析
  ```

  ### 第六阶段：执行因子分析（Phase 3）

  见"因子分析框架"章节。

  ---
  ````

- [ ] **Step 2：确认文件写入成功**

  使用 Read 工具读取 `SKILL.md` 前 50 行，确认 frontmatter 和架构图正确写入。

---

## Task 3：追加 Phase 1 子代理规范详细输出格式

**Files:**
- Modify: `skills/turtle-investment-strategy/SKILL.md`（追加内容）

- [ ] **Step 1：追加子代理规范章节到 SKILL.md**

  使用 Edit 工具在 `### 第六阶段：执行因子分析（Phase 3）` 之后、`---` 之前追加以下内容（或 Write 工具追加），形成"子代理规范"独立章节：

  ````markdown
  ## 子代理规范

  ### Phase 1 输出文件详细格式

  ```markdown
  # {公司名}（{代码}）市场数据包

  **数据采集时间**：[时间戳]
  **金额单位**：报表币种百万元（除非另有标注）
  **数据来源汇总**：[AI-Tools / mx-finance-data / mx-macro-data / mx-financial-assistant / WebSearch]

  ---

  ## 一、基础市场数据

  ### 1.1 股价与市值
  - 当前股价：[值] [币种]
  - 总股本（稀释后）：[值] 股
  - 当前市值：[值] 亿元
  - 52周最高/最低：[高] / [低]
  - **数据来源**：mx_finance_data / AI-Tools QueryStockPriceInfo

  ### 1.2 股息与回购
  - 当前股息率：[值]%
  - 过去5年股息率序列：[X%, X%, X%, X%, X%]
  - 过去5年回购金额序列：[X, X, X, X, X] 亿元
  - **数据来源**：mx_finance_data / AI-Tools

  ---

  ## 二、财务报表数据（近5年，百万元）

  ### 2.1 利润表
  | 年份 | 营业收入 | 营业成本 | 毛利润 | 研发费用 | 销售费用 | 管理费用 | 经营利润 | 税前利润 | 所得税 | 归母净利润 | 少数股东损益 | D&A | SBC |
  |------|---------|---------|--------|---------|---------|---------|---------|---------|--------|-----------|-------------|-----|-----|
  | 202X | ... |
  **数据来源**：AI-Tools GetIncomeStatement

  ### 2.2 资产负债表
  | 年份 | 现金及等价物 | 短期投资 | 应收账款 | 存货 | 流动资产 | 长期投资 | 商誉 | 无形资产 | 总资产 | 短期借款 | 长期借款 | 有息负债合计 | 合同负债 | 股东权益 |
  |------|------------|---------|---------|------|---------|---------|------|---------|--------|---------|---------|-------------|---------|---------|
  | 202X | ... |
  **数据来源**：AI-Tools GetBalanceSheet

  ### 2.3 现金流量表
  | 年份 | OCF | Capex | FCF | 股息支付 | 回购金额 |
  |------|-----|-------|-----|---------|---------|
  | 202X | ... |
  **数据来源**：AI-Tools GetCashFlowStatement

  ---

  ## 三、历史价格数据（5年月线）
  [逐年逐月价格数据，含日期和收盘价]
  **数据来源**：AI-Tools GetMonthlyKLineData

  ---

  ## 四、无风险利率
  - 十年期国债收益率：[值]%
  - 对应市场：[中国/美国/香港]
  - **数据来源**：mx_macro_data / WebSearch

  ---

  ## 五、上市结构与税务信息
  - 上市地点：[港股/A股/美股]
  - 持股渠道：[港股通/直接持有/美股券商]
  - 股息税率：[值]%
  - 代扣代缴：[是/否]
  - **数据来源**：mx_financial_assistant / WebSearch

  ---

  ## 六、管理层与治理信息
  - CEO：[姓名]，任期：[时间]
  - CFO：[姓名]，任期：[时间]
  - 董事长：[姓名]，任期：[时间]
  - 控股股东：[名称]，持股：[值]%
  - 独立董事占比：[值]%
  - **数据来源**：mx_financial_assistant

  ---

  ## 七、行业与竞争格局
  - 行业名称：[名称]，规模：[值] 亿元，增速：[值]%
  - 主要竞争对手及市场份额：...
  - **数据来源**：mx_financial_assistant / mx_finance_search

  ---

  ## 八、子公司数据（控股公司适用）
  [若非控股公司则填写：不适用]
  **数据来源**：mx_finance_data / AI-Tools GetFinancialReport

  ---

  ## 九、MD&A 摘要
  - 经营回顾：[摘要]
  - 前瞻性指引：[摘要]
  - 风险因素：[摘要]
  - **数据来源**：AI-Tools GetFinancialReport / mx_financial_assistant

  ---

  ## 十、数据完整性检查
  - ⚠️未找到：[项目名]
  - 完整度：[值]%
  - 可靠性：[高/中/低]
  ```

  ### Phase 2 输出文件详细格式

  ```markdown
  # {公司名}（{代码}）深度财务数据包

  **数据采集时间**：[时间戳]
  **金额单位**：报表币种百万元
  **数据来源汇总**：[AI-Tools / mx-finance-search / mx-financial-assistant / search_reports]

  ---

  ## 一、母公司单体资产负债表数据
  ### 1.1 资产端明细
  ### 1.2 负债端明细
  ### 1.3 股东权益明细
  **数据来源**：AI-Tools GetBalanceSheet / GetFinancialIndicators

  ## 二、受限现金与应收账款明细
  **数据来源**：AI-Tools GetFinancialIndicators

  ## 三、负债详细信息
  ### 3.1 有息负债明细（银行贷款/债券/关联方借款）
  ### 3.2 资本化利息（金额/占比）
  ### 3.3 或有负债（对外担保/未决诉讼/资本承诺）
  **数据来源**：AI-Tools GetBalanceSheet / GetFinancialIndicators

  ## 四、MD&A 深度信息
  ### 4.1 经营回顾与业绩归因
  ### 4.2 前瞻性指引
  ### 4.3 资本配置意图
  ### 4.4 风险因素
  **数据来源**：AI-Tools GetFinancialReport / mx_financial_assistant

  ## 五、审计相关信息
  ### 5.1 审计意见（标准无保留/保留意见/强调事项）
  ### 5.2 审计师名称
  ### 5.3 关键审计事项
  ### 5.4 审计师更换历史
  **数据来源**：mx_finance_search（公告搜索）/ AI-Tools GetFinancialReport

  ## 六、非经常性损益明细
  ### 6.1 资产处置损益
  ### 6.2 政府补贴
  ### 6.3 投资收益（联营分红/理财收益）
  ### 6.4 公允价值变动损益
  **数据来源**：AI-Tools GetFinancialReport / GetIncomeStatement

  ## 七、股息分配信息
  | 年份 | 股息总额 | 归母净利润 | 支付率 |
  **数据来源**：mx_finance_data / AI-Tools GetFinancialReport

  ## 八、关联方交易信息
  **数据来源**：AI-Tools GetFinancialIndicators

  ## 九、定期存款与理财产品
  **数据来源**：AI-Tools GetFinancialIndicators

  ## 十、数据完整性检查
  ```
  ````

- [ ] **Step 2：确认章节写入**

  使用 Glob 工具检查 SKILL.md 文件大小：应明显大于修改前（大于 1000 行）。

---

## Task 4：追加因子分析框架（复制自 V1.3.md）

**Files:**
- Read: `skills/turtle-investment-strategy/V1.3.md`（参考源）
- Modify: `skills/turtle-investment-strategy/SKILL.md`（追加）

- [ ] **Step 1：读取 V1.3.md 的因子分析章节**

  使用 Read 工具读取 `V1.3.md` 第 166 行到末尾（`#### 因子 1A：五分钟快筛` 开始，直到 `## 单位换算规则` 之前的部分）。

  精确范围：`#### 因子 1A` 到 `### 第五阶段：报告生成` 的结束（含报告模板输出格式）。

- [ ] **Step 2：追加因子分析章节**

  在 SKILL.md 当前末尾追加以下章节头，然后追加从 V1.3.md 提取的完整内容（不做修改）：

  ```markdown
  ---

  ## 因子分析框架

  > 本章节由主代理在 Phase 3 执行，基于两个子代理产出的数据包进行分析。

  ```

  然后追加完整的因子 1A/1B/2/3/4 内容（来自 V1.3.md，原样复制）。

  ⚠️ **注意**：因子 1A/1B/2/3/4 内容**完全不做修改**，只在章节头加上上面的 > 引用说明。

- [ ] **Step 3：读取 V1.3.md 报告模板章节**

  追加 V1.3.md 中的 `【最终决策输出】` 格式模板（步骤 5 的决策输出区块）。

---

## Task 5：追加工具清单 + 单位换算 + 注意事项

**Files:**
- Modify: `skills/turtle-investment-strategy/SKILL.md`（追加）

- [ ] **Step 1：追加工具清单章节**

  在 SKILL.md 末尾追加：

  ````markdown
  ---

  ## 可用工具清单

  ### 一、东方财富 mx-* Skills（按数据类型专项使用）

  **`mx_finance_data`（实时行情/股息/市场数据）**
  - 适用场景：实时股价、市值、股息率、股息历史、回购历史、股东信息
  - 调用方式：`Skill(name="mx_finance_data", args="查询内容")`
  - 或 Bash：`python3 {baseDir}/scripts/get_data.py --query "贵州茅台近5年股息率和分红总额"`
  - 输出：xlsx 文件（结构化数据）+ txt 说明文件

  **`mx_macro_data`（宏观数据/国债收益率/无风险利率）**
  - 适用场景：十年期国债收益率（Rf）、GDP、CPI 等宏观指标
  - 调用方式：`Skill(name="mx_macro_data", args="查询内容")`
  - 或 Bash：`python3 {baseDir}/scripts/get_data.py --query "中国十年期国债收益率"`
  - 注意：查询必须包含具体指标名称
  - 输出：csv 文件 + txt 说明文件

  **`mx_finance_search`（公告/研报/新闻搜索）**
  - 适用场景：公司公告（审计报告、分红公告）、券商研报、财经新闻
  - 调用方式：`Skill(name="mx_finance_search", args="查询内容")`
  - 或 Bash：`python3 {baseDir}/scripts/get_data.py "格力电器 2024 年报审计意见"`
  - 输出：txt 文件（资讯正文）

  **`mx_financial_assistant`（综合金融问答）**
  - 适用场景：管理层信息、行业竞争格局、商业模式解读、综合定性分析
  - 调用方式：`Skill(name="mx_financial_assistant", args="查询内容")`
  - 或 Bash：`python3 {baseDir}/scripts/generate_answer.py --query "平安银行管理层构成和持股"`
  - 深度思考模式：添加 `--deep-think` 参数
  - 输出：Markdown 格式回答

  ---

  ### 二、AI-Tools MCP 工具（结构化财务数据，第一优先级用于三大报表）

  **股票基础信息**：
  - `StockSearch`：搜索股票代码和名称
  - `QueryStockPriceInfo`：查询实时股价信息

  **财务报表数据**：
  - `GetIncomeStatement`：利润表（Markdown）
  - `GetBalanceSheet`：资产负债表（Markdown）
  - `GetCashFlowStatement`：现金流量表（Markdown）
  - `GetFinancialReport`：完整财务报告（含 MD&A）
  - `GetFinancialIndicators`：财务指标（含受限现金/关联方/应收账款详情）

  **JSON 原始数据**（用于精确数字提取）：
  - `GetIncomeStatementJson`、`GetBalanceSheetJson`、`GetCashFlowStatementJson`
  - `GetFinancialIndicatorsJson`、`GetFinancialReportJson`

  **K 线数据**：
  - `GetMonthlyKLineData`：月线数据（历史价格，主要来源）
  - `GetKLineData`：任意周期 K 线
  - `GetDailyKLineData`：日线数据

  **调用方式**：
  ```
  mcp_AI_Tools_invoke_tool({
    "toolName": "工具名称",
    "parameters": { ... }
  })
  ```

  ---

  ### 三、WebSearch（补充数据）

  - 适用场景：mx-* skill 和 AI-Tools 均无法获取时的补充
  - 优先来源：巨潮资讯、港交所披露易、公司官网投资者关系

  ---

  ### 四、发现报告 MCP（`search_reports`，研报备用）

  - 适用场景：mx_finance_search 无法获取研报时
  - 参数：keywords, start_time/end_time, page_size（10-20）

  ---

  ### 五、文件操作工具

  - `Read`：读取数据包和策略规则文件
  - `Write`：写入数据包和分析报告
  - `Glob`：查找文件
  - `Bash`：执行 mx-* skill Python 脚本、创建目录

  ````

- [ ] **Step 2：追加单位换算规则**

  追加（来自 V1.3.md，原样复制单位换算章节）：

  ````markdown
  ---

  ## 单位换算规则

  **Phase 3 必须先读取各 data_pack 文件头的单位标注**：

  | 原始单位 | → 亿元 | 示例 |
  |---------|--------|------|
  | 百万元 | ÷ 100 | 9,890.67 百万 → 98.91 亿 |
  | 千元 | ÷ 100,000 | 9,082,254 千元 → 90.82 亿 |
  | 万元 | ÷ 10,000 | 908,225 万 → 90.82 亿 |

  **币种换算**：使用分析日即期汇率，先换算为人民币再转为亿元

  ````

- [ ] **Step 3：追加注意事项**

  追加：

  ````markdown
  ---

  ## 注意事项

  1. **职责边界**：主代理只做调度和分析，不调用数据采集工具；数据采集完全由子代理完成
  2. **工具分工**：严格按数据类型选用工具（见可用工具清单中的适用场景）
  3. **数据优先级**：
     - 无风险利率 → mx_macro_data 优先
     - 公告/研报 → mx_finance_search 优先
     - 定性信息/管理层/竞争格局 → mx_financial_assistant 优先
     - 实时行情/股息 → mx_finance_data 优先
     - 三大报表/K线 → AI-Tools MCP 优先
  4. **并行执行**：Phase 1 和 Phase 2 子代理可以并行执行，主代理等待两个文件都生成后再继续
  5. **数据标注**：所有数据必须标注来源（工具名称/搜索关键词）
  6. **单位统一**：报告输出使用人民币亿元，子代理数据包使用报表原始币种百万元
  7. **否决纪律**：因子 1A 或因子 2 触发否决 → 立即停止后续分析
  8. **策略目录只读**：不得修改 V1.x.md 历史版本文件
  9. **框架边界**：不适用于 Pre-profit 企业、高增长科技股、周期顶部的强周期股

  ---

  ## 关键变量索引

  （与 V1.3.md 相同，原样保留）

  ### 因子 2 变量
  A=集团净利润, B=少数股东损益, C=归母净利润, D=折旧摊销, E=资本开支,
  G=维持性资本开支系数, H=D×G（维持性资本开支粗估）, I=C+D-H（Owner Earnings）,
  M=支付率锚定值, O=年均回购金额, Q=综合股息税率, R=粗算穿透回报率

  ### 因子 3 变量
  S=营业收入, T=应收账款净变动, U=预收款/合同负债净变动,
  V1=资产处置收入（保留项）, V_deduct=应扣除非经常性流入,
  W=经营性现金支出, Y=总扣除额, AA=真实可支配现金结余基准值,
  BB=广义现金合计, FF=可自由支配现金, GG=精算穿透回报率, HH=R-GG（粗算偏差）

  ### 因子 4 变量
  GG=精算穿透回报率, II=门槛值, JJ=GG-II（安全边际）, KK=修正后安全边际,
  NN=历史价格数据点数量, OO=5年最低价, PP=5年最高价

  ---

  ## 特殊规则

  ### 合同负债计入类现金

  适用条件（须同时满足）：
  - 业务模式为"先款后货"或"预收制"
  - 合同负债对应交付确定性极高（>95%）
  - 合同负债近3年波动率 < 30%

  计入逻辑：
  - 用于：安全垫评估、EV 口径计算、派息可持续年限
  - 不用于：可自由分配现金 FF 的计算

  ### EV 口径双轨制

  触发条件：广义净现金/市值 > 40%

  计算：
  - EV = 市值 - 广义净现金
  - R_EV = [C × M × (1-Q%) + O] / EV
  - GG_EV = [AA × M × (1-Q%) + O] / EV

  通过条件：R_EV ≥ II **且** 通过"现金分配意愿检验"

  ### 现金保护等级

  | 等级 | 广义净现金/市值 | 安全边际折扣 |
  |------|--------------|------------|
  | 无保护 | < 20% | 标准 30% |
  | 轻度保护 | 20-40% | 25% |
  | 强保护 | 40-60% | 20% |
  | 极强保护 | > 60% | 15% |

  ---

  ## 异常处理

  | 异常情况 | 处理方式 |
  |---------|---------|
  | Phase 1 子代理超时 | 主代理重新启动，最多3次；仍失败则通知用户 |
  | mx-* skill 调用失败 | 降级至对应备用工具（见工具清单） |
  | AI-Tools 财报数据不足5年 | 使用 mx_finance_data 补充，标注实际覆盖年份 |
  | data_pack_report.md 缺失 | 使用降级方案（data_pack_market.md 单独分析），标注"深度数据缺失" |
  | 因子 1A/1B 触发否决 | 停止后续分析，输出否决报告 |
  | 因子 2 粗算否决 | 不进入因子 3，直接输出否决结论 |

  ````

- [ ] **Step 4：确认文件完整性**

  使用 Bash 检查 SKILL.md 总行数：
  ```bash
  wc -l "/Users/apple/Documents/分析报告/.trae/skills/turtle-investment-strategy/SKILL.md"
  ```
  预期：应大于 800 行（原文件约 919 行，新文件加入了子代理 prompt 应更长）。

---

## Task 6：验证并提交

**Files:**
- Read: `skills/turtle-investment-strategy/SKILL.md`（验证）

- [ ] **Step 1：验证关键章节存在**

  使用 Grep 工具检查以下关键字符串均在 SKILL.md 中存在：
  - `"主代理不直接调用任何数据采集工具"`
  - `"mx_macro_data"`
  - `"mx_finance_search"`
  - `"mx_financial_assistant"`
  - `"mx_finance_data"`
  - `"Phase 1 子代理"`
  - `"Phase 2 子代理"`
  - `"因子 1A：五分钟快筛"`
  - `"因子 4：估值与安全边际"`

- [ ] **Step 2：读取 SKILL.md 前100行**

  使用 Read 工具验证 frontmatter、架构图、主代理流程描述正确无误。

- [ ] **Step 3：读取 SKILL.md 子代理规范章节**

  搜索"子代理规范"章节，确认 Phase 1 和 Phase 2 的数据来源表格和 prompt 模板都存在。

- [ ] **Step 4：向用户报告完成**

  汇报：
  - SKILL.md 总行数
  - 关键章节清单（全部存在）
  - 主要变更摘要：子代理架构 + 东方财富 skill 分工

  **无需提交 git commit**（由用户决定何时提交）。

---

## 自检清单

- [x] **Spec 覆盖**：子代理架构 ✓，主代理只调度 ✓，mx-* 按类型分工 ✓，因子分析完整保留 ✓
- [x] **无占位符**：所有 prompt 模板均为完整内容，无 TBD
- [x] **工具名称一致**：mx_macro_data / mx_finance_data / mx_finance_search / mx_financial_assistant（与 skill 名称一致）
- [x] **文件路径准确**：所有路径使用绝对路径或 {workspace} 变量
