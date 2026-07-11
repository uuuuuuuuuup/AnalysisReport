---
name: "turtle-investment-strategy"
description: "Executes versioned, multi-phase stock analysis with a coordinator and parallel data workers. Uses AI-Tools MCP, mx-* skills, and gtht-lingxi-unified by data type; applies deterministic local valuation calculations. Invoke for stock analysis, buy/valuation questions, or annual-report review."
---

# 稳健投资策略分析助手 v2.2

## 用途与边界

适用于已上市、盈利稳定的 A 股、港股和美股的价值分析：是否买入、估值、安全边际或事件后复评。

- 不适用于未盈利企业、依赖远期假设的高增长科技股、强周期顶部标的。
- `history/` 为只读归档，不是运行规则来源。
- 报告仅供研究参考，不构成投资建议。

## 角色与流程

| 角色 | 负责 | 不负责 |
|---|---|---|
| 主代理 | 解析、版本目录、调度、数据包整合、定性判断、脚本计算、报告与归档 | 直接采集外部数据 |
| Phase 1 | 市场、三表、月线、Rf、治理、行业、税务、MD&A | 投资结论 |
| Phase 2 | 附注、审计、负债、非经常损益、关联方、股息深度数据 | 投资结论 |

1. 解析代码/名称、市场、持股渠道和触发原因。未指定年份时：1–3 月取 `year - 2`，其他月份取 `year - 1`。
2. 用 `prepare` 获取 `{workspace}/稳健投资策略分析报告/{symbol}/{analysis_date}/` 和目标年份；同日冲突时使用 `YYYY-MM-DD_HH-mm`。
3. 用 `rf-cache` 检查 Rf。A 股/港股/美股对应 `CN`/`HK`/`US` 和 `CN_10Y`/`HK_10Y`/`US_10Y`。主代理维护本地缓存不属于数据采集；缓存失效或重大货币政策事件后，由 Phase 1 重新查询并回填。
4. 并行启动两个子代理，输出 `data_pack_market.md` 与 `data_pack_report.md`。Phase 1 必须完成；Phase 2 超时、缺失或关键字段不足时，标注缺失后降级继续。不要轮询 Agent 工具已跟踪的后台任务。
5. 读取数据包的单位、币种与来源，完成因子 1A/1B 定性判断；将已核验数值传给 `calculate`，禁止手算、禁止改写脚本结果。
6. 成功写出报告后，以 `finalize` 原子追加 `index.json`，再更新 `latest` 指向最新版本；旧版本不删除。

## 数据采集契约

每个数据项必须标注实际来源、日期和单位；未找到项目写 `⚠️未找到：{项目名}`。只有首选工具失败、字段为空或不适用才降级。

| 数据类别 | 首选 | 降级顺序 |
|---|---|---|
| 行情、三表、财报、指标、月线 | AI-Tools：`QueryStockPriceInfo`、`GetIncomeStatement`、`GetBalanceSheet`、`GetCashFlowStatement`、`GetFinancialReport`、`GetFinancialIndicators`、`GetMonthlyKLineData` | `gtht-lingxi-unified` → `mx-data` → WebSearch |
| Rf/宏观 | 有效 `risk_free_rate.json` | AI-Tools `GetAllEconomicData`/`GetUsTreasuryYield` → `mx-data` macro → Lingxi → WebSearch |
| 公告、审计、研报 | `mx-search` | Lingxi research → AI-Tools 财报 → WebSearch |
| 治理、行业、税务 | `mx-assistant` | Lingxi → `mx-search` → WebSearch |
| MD&A/业绩补充 | AI-Tools 财报或 `mx-report` | `mx-assistant` → WebSearch |

脚本入口统一使用：

```bash
SKILL_BASE={workspace}/.claude/skills/turtle-investment-strategy
LINGXI={workspace}/.claude/skills/gtht-lingxi-unified/skill-entry.js
MX_DATA={workspace}/.claude/skills/mx-data/scripts/query_data.py
MX_SEARCH={workspace}/.claude/skills/mx-search/scripts/search.py
MX_ASSISTANT={workspace}/.claude/skills/mx-assistant/scripts/ask.py
MX_REPORT={workspace}/.claude/skills/mx-report/scripts/generate_report.py
```

### Phase 1 必采字段

- 当前股价、市值、稀释后股本、52 周高低、近 5 年股息率/股息/回购。
- 近 5 年利润表、资产负债表、现金流和月线；现金流必须单列购买商品/劳务、员工、税费、利息支出。
- Rf、上市地、渠道、股息税、治理、控股股东、行业格局、MD&A；控股公司补充子公司。
- 目标年年报未发布时，补充已发布季报，仅作风险预警，不能用于核心估值。

### Phase 2 必采字段

母公司单体报表和附注、受限现金/应收/定存、有息负债/资本化利息/或有负债、审计意见/审计师/关键审计事项、非经常损益、股息分配、关联方交易、MD&A 深度与资本配置。

## 数据包格式

### `data_pack_market.md`

```markdown
# {公司名}（{代码}）市场数据包
**数据采集时间**：{timestamp}
**金额单位**：{报表币种}百万元（除非另有标注）
**数据来源汇总**：{实际工具和查询词}

## 1. 市场与分配
股价、市值、股本、52周高低、近5年股息与回购。

## 2. 财务基础（近5年）
| 年份 | 收入 | 毛利 | 归母净利润 | 扣非净利润 | D&A | OCF | Capex | FCF | 股息 | 回购 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| {Y} | {v} | {v} | {v} | {v} | {v} | {v} | {v} | {v} | {v} | {v} |

| 年份 | 广义现金 | 受限现金 | 应收 | 存货 | 总资产 | 短借 | 长借 | 有息负债 | 合同负债 | 权益 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

| 年份 | 购买商品/劳务 | 员工现金 | 税费 | 利息 |
|---|---:|---:|---:|---:|

## 3. 价格与中间期数据
5年月线；年报未发布时附季报对比。

## 4. Rf、税务与治理
Rf 的值/键/日期/来源/缓存状态；税务、管理层、控股股东、治理。

## 5. 行业、子公司与 MD&A
行业规模/增速/竞争、子公司（适用时）、经营回顾/指引/风险。

## 6. 完整性检查
缺失项、完整度、可靠性及原因。
```

### `data_pack_report.md`

```markdown
# {公司名}（{代码}）深度财务数据包
**数据采集时间**：{timestamp}
**金额单位**：{报表币种}百万元
**数据来源汇总**：{实际工具和查询词}

## 1. 单体报表与资产质量
资产/负债/权益明细；受限现金、应收、定存和理财。

## 2. 负债、审计与关联方
有息负债、资本化利息、或有负债；审计意见/审计师/关键审计事项/变更；关联方交易。

## 3. 收益质量与分配
非经常损益分类；股息总额、归母净利、支付率；资本配置。

## 4. MD&A 与完整性检查
经营回顾、前瞻指引、风险；缺失项、完整度、可靠性。
```

## 定性与否决纪律

### 因子 1A：快筛

以下任一项为“是”即否决：审计意见异常、频繁更换审计师、财务造假/重大违规、商业模式看不懂、商业模式未验证、控股股东重大负面。

### 因子 1B：定性判断

必须评估资本消耗、收款模式、非技术/技术护城河、周期性、人力资本依赖、管理层与治理、监管、MD&A、控股折价（适用时）。

分析前明确：归母/扣非净利润、D&A、Capex、SBC、广义现金/受限现金/有息负债/净现金、支付率锚定值、年均回购、股息税、Rf 和门槛。事实、假设和推断必须分开。

## 确定性计算

路径：`{SKILL_BASE}/scripts/strategy_tools.py`。脚本不抓取数据、不做定性判断、不生成结论，只处理已核验数值。

```bash
python3 "$SKILL_BASE/scripts/strategy_tools.py" prepare \
  --symbol "{symbol}" --company "{company}" \
  --output-root "{workspace}/稳健投资策略分析报告" --as-of "YYYY-MM-DD"

python3 "$SKILL_BASE/scripts/strategy_tools.py" rf-cache \
  --cache "$SKILL_BASE/risk_free_rate.json" --market "CN|HK|US" --as-of "YYYY-MM-DD"

python3 "$SKILL_BASE/scripts/strategy_tools.py" validate \
  --input-json '{"currency":"CNY","unit":"百万元","market_cap":0,"net_income":0,"depreciation_amortization":0,"payout_ratio":0,"dividend_tax_rate":0,"annual_buybacks":0,"disposable_cash_surplus":0,"risk_free_rate":0,"net_cash":0,"current_price":0}'

python3 "$SKILL_BASE/scripts/strategy_tools.py" finalize \
  --index "{symbol_root}/index.json" --latest-dir "{version_dir}" \
  --version-json '{"symbol":"{symbol}","company":"{company}","record":{}}'

python3 "$SKILL_BASE/scripts/strategy_tools.py" calculate \
  --input-json '{"market":"CN","market_cap":0,"net_income":0,"depreciation_amortization":0,"maintenance_capex_ratio":0,"payout_ratio":0,"dividend_tax_rate":0,"annual_buybacks":0,"disposable_cash_surplus":0,"risk_free_rate":0,"net_cash":0,"cyclical_adjustment_pct":0,"current_price":0}'
```

- 原始单位转亿元：百万元 ÷100、千元 ÷100,000、万元 ÷10,000；跨币种以分析日即期汇率转人民币。
- `Owner Earnings = 归母净利润 + D&A − D&A × 维持性Capex系数`；粗算回报率 = `[Owner Earnings × 支付率锚定 × (1−股息税) + 年均回购] / 市值`。
- 精算可支配现金结余由主代理保守计算：真实收入 = 收入 − `max(0, 应收变动)` − `max(0, −预收变动)`；保留资产处置和投资收益，扣除补贴、保险、其他一次性流入、经营现金支出、Capex、对外投资和隐性必要支出。精算回报率 = `[结余 × 支付率锚定 × (1−税) + 回购] / 市值`。
- 精算结余高于 FCF 1.5 倍必须复核；净现金/市值 >40% 时同时输出 EV 口径。合同负债仅在先款后货、交付确定性 >95%、近三年波动率 <30% 时用于安全垫/EV，不计入可分配现金。
- 门槛：A 股 `max(3.5%, Rf+2%)`；港美股 `max(5%, Rf+3%)`。安全边际 = 精算回报率 − 门槛；强周期底部减 1pct、顶部加 2pct。
- 现金保护：<20% 无保护/30%折扣，20–40% 轻度/25%，40–60% 强/20%，>60% 极强/15%。目标价 = 当前价 × 精算回报率/门槛 × `(1−折扣)`。
- 输出 1.0×/0.9×/0.8×/0.7×收入情景；主代理依收入波动、利润调整、粗精算偏差、经营变化与数据可靠性评定外推可信度。

粗算回报率低于 Rf 或门槛一半时，先复核 EV；仍不通过即否决。价值陷阱五项：现金流恶化、护城河收窄、行业衰退、分配意愿弱、管理层损害价值；至少两项且精算回报率不超过门槛 1.5 倍时排除。

## 最终报告格式

路径：`{version_dir}/{公司名}_{symbol}_稳健投资策略分析报告.md`。报告仅保留聚合数据，完整原始数据留在两个数据包。

```markdown
# {公司名}（{代码}）稳健投资策略分析报告
> **{仓位建议}** — {最大优势、最大风险与介入条件}

**数据截止**：{年度/日期} | **分析基准日**：{date} | **数据完整度**：{高/中/低}

## 1. 投资结论与关键证据
| 指标 | 数值 | 依据/口径 |
|---|---:|---|
| 当前价/目标买入价/距离目标价 | {v} | 脚本计算 |
| 粗算/精算回报率 | {v}% / {v}% | 计算输入 |
| Rf/门槛/修正后安全边际 | {v}% / {v}% / {v}pct | 脚本计算 |
| 价值陷阱/现金保护/外推可信度 | {评级} | 触发项 |

- 论点 1：{含数据证据}
- 论点 2：{含数据证据}
- 最大风险与失效条件：{含阈值}

## 2. 因子结论
| 因子 | 结论 | 核心证据 |
|---|---|---|
| 1A 快筛 | 通过/否决 | 六项检查 |
| 1B 定性 | 通过/警惕 | 护城河、周期、治理、监管 |
| 2 粗算 | 通过/边际/否决 | 回报率 vs 门槛 |
| 3 精算 | 通过/警惕 | 现金质量、敏感性、可信度 |
| 4 估值 | 通过/警惕 | 安全边际、陷阱、目标价 |

## 3. 财务、现金与估值依据
近5年趋势、Owner Earnings、真实可支配结余、关键假设、FCF校验、EV（适用时）、收入情景与目标价。

## 4. 商业质量与风险
商业模式、收款、护城河、周期、资本强度、治理、监管、MD&A、价值陷阱与风险提示。

## 5. 监控与待验证事项
年报未发布时列收入/利润/应收/库存预警（不改变核心估值）；列净现金、FCF yield、FCF、债务、营收、支付率的止损阈值与后续验证节点。

*稳健投资策略 v2.2 | AI 辅助生成，仅供研究参考，不构成投资建议。*
```

## 异常与降级

| 情况 | 处理 |
|---|---|
| Phase 1 失败 | 最多重试 3 次；仍失败通知用户，不生成完整报告 |
| Phase 2 失败 | 降级继续，显著标注“深度数据缺失”及受影响判断 |
| Rf 无效且无法刷新 | 标注缺失，停止依赖 Rf 的目标价计算 |
| 财报不足 5 年 | 标注覆盖期，不伪造 CAGR 或趋势结论 |
| 关键计算字段缺失 | 禁用对应公式，列出缺失字段与结论限制 |
| 因子 1A 或因子 2 否决 | 停止后续深度估值，输出否决原因和最少必要证据 |
