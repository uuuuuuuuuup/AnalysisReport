# ST Stock Strategy Skill Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the existing `st-stock-strategy` skill so future agents can analyze ST/*ST stocks using the user's ST strategy note, AI-Tools, 东方财富 skills, and WebSearch.

**Architecture:** This is a documentation/process skill update, not application code. Replace the existing single-file skill with a more complete workflow: ST type classification, market regime check, one-vote vetoes, restructuring stage analysis, tool matrix, output template, and rationalization guards. Validate by running the same pressure scenario before and after the update.

**Tech Stack:** Markdown skill file under `.claude/skills`, Claude Code Skill tool, AI-Tools MCP, WebSearch, subagent pressure tests.

---

## File Structure

- Modify: `.claude/skills/st-stock-strategy/SKILL.md` — the canonical skill file loaded by Claude Code.
- Do not modify: `.claude/skills/st-stock-strategy/skill.md` — this path appeared in a Read attempt but does not exist on disk; `SKILL.md` is the actual file.
- Optional read-only reference: `/Users/apple/Documents/字幕/学习笔记/02_ST策略详解.md` — source note for the strategy logic.

---

### Task 1: Write the updated skill content

**Files:**
- Modify: `.claude/skills/st-stock-strategy/SKILL.md`

- [ ] **Step 1: Read the current skill**

Run no shell command for this step. Use the Read tool on `.claude/skills/st-stock-strategy/SKILL.md` and confirm it contains the current event-driven ST strategy skill.

Expected: file starts with frontmatter `name: "st-stock-strategy"`.

- [ ] **Step 2: Replace the skill with the new version**

Use Write tool to replace `.claude/skills/st-stock-strategy/SKILL.md` with this exact content:

```markdown
---
name: "st-stock-strategy"
description: "Use when 用户寻找ST/*ST股票机会、分析某只ST股是否值得参与、评估摘帽/重整/保壳/假ST反包交易、制定ST买卖点和风控方案、或需要结合AI-Tools、东方财富skills、WebSearch生成ST板块分析报告时。"
---

# ST股分析与重整博弈策略

## 核心原则

ST策略不是普通价值投资,而是高风险事件驱动与壳价值博弈。先判断"会不会死",再判断"值不值得赌"。

必须按顺序分析:
1. **退市排雷**:任何退市红线优先于收益想象。
2. **ST类型分类**:不同戴帽原因决定完全不同的操作方式。
3. **市场环境开关**:流动性、政策、微盘股/ST指数环境不对时,再好的个股也要降仓或放弃。
4. **事件阶段定价**:暗线埋伏有赔率,明线公布后多半见光死。
5. **仓位先行**:单只ST建议不超过总资金5%,ST总仓位不超过15%,且持仓市值不得超过该股近日日均成交额10%。

## ST类型分类

| 类型 | 触发原因 | 操作结论 | 关键核查 |
|---|---|---|---|
| 财务型ST | 营收不足、净利润为负、净资产问题 | 主要标的,但必须确认保壳路径 | 营收能否过线、扣非是否改善、资产注入是否真实 |
| 规则型ST | 信息披露、资金占用、治理违规等明确规则问题 | 可关注,路径清晰时赔率较好 | 违规是否已纠正、处罚是否落地、整改期限 |
| 审计型ST | 无法表示意见、否定意见、审计问题 | 普通投资者原则回避 | 审计意见是否改善、是否换小所、财务真实性 |
| 重大违法型ST | 财务造假、重大安全事故、重大违法退市风险 | 坚决回避 | 处罚告知书、行政处罚决定、是否触发重大违法退市 |
| 假ST | 历史轻微违规或不会导致退市的戴帽 | 只做短线反包,不长持 | 跌停板数、退市概率、违规性质是否轻微 |

先分类再选股。不要把假ST当重整股,不要把审计型ST当财务型ST,不要把重大违法型ST当困境反转。

## 一票否决

命中任一项,结论必须是"回避/退出",除非用户明确要求只做案例复盘:

- 证监会立案未出结果,行政处罚告知书或处罚决定未明确前无法排除重大违法退市。
- 已触发或高度接近面值退市、退市整理期、终止上市事先告知。
- 年报审计意见为否定意见,或无法表示意见且没有明确改善证据。
- 重大违法、安全事故、财务造假方向明确。
- 山海关外ST原则一票否决,东北地区退市比例高,除非有极强国资/资产注入证据。
- 独立董事、财务总监、审计负责人异常辞职。
- 到10月重整路条仍未批,年报前极限保壳窗口关闭。
- 大存大贷、资金占用、违规担保无法解释。
- 纯粹书困型重整且市值偏大、没有新资产注入或主营改善。

## 市场环境开关

买入前先判断ST策略是否处在可做环境:

| 环境项 | 正面 | 负面 | 操作 |
|---|---|---|---|
| 市场流动性 | 成交活跃、微盘股走强 | 科技/主线虹吸资金,小票失血 | 负面时只观察或降仓 |
| 微盘股指数 + ST指数 | 双红企稳 | 双双下行 | 双红再做壳价值套利 |
| 政策环境 | 重整、重组、保壳政策宽松 | 监管处罚趋严、退市加速 | 趋严时提高排雷标准 |
| 事件反馈 | 利好公告后有持续承接 | 利好只涨一点或反跌停 | 反馈弱时抢跑,不等兑现 |

注意:ST指数有幸存者偏差,退市股会被剔除,指数表现可能好于真实持仓体验。

## 重整流程与阶段策略

```text
预重整/签投资人 -> 法院裁定重整 -> 重整路条 -> 资本公积转增 -> 填权 -> 摘帽
```

| 阶段 | 含义 | 操作 |
|---|---|---|
| 预重整/签投资人 | 前端准备,信息不透明,赔率最大 | 只在排雷后小仓暗线埋伏 |
| 法院裁定重整 | 面试通过,但未完全确定 | 可继续跟踪,不追高 |
| 重整路条 | 基本等同重整成功 | 已接近明牌,考虑减仓 |
| 资本公积转增 | 投资人成本、转增比例公开 | 明牌阶段,不把公布当买点 |
| 填权 | 好公司可能填到原价前不开板 | 未持有者不追,持有者分批兑现 |
| 摘帽 | 利好兑现,恢复普通股票属性 | 摘帽当天或次日减仓至少一半 |

关键原则:应在资本公积转增前参与,填权后再参与性价比差。方案公布、路条明牌、摘帽复牌都更偏卖点而非买点。

## 暗线与明线

| 模式 | 特征 | 优点 | 风险 | 结论 |
|---|---|---|---|---|
| 主观型暗线埋伏 | 有预重整、签约投资人、股权变化、高管变化、资产线索,但草案未公布 | 赔率最高 | 信息不对称大 | 只小仓,见光后减仓 |
| 客观型明线套利 | 草案公布,产投/财投成本可算 | 确定性更高 | 容易见光死 | 只在折价足够且流动性允许时做 |
| 假ST反包 | 戴帽原因轻微,连续跌停后恐慌释放 | 短线弹性 | 不适合长持 | 反包做完就走 |

2026环境修正:事件驱动反馈变弱,书困型重整基本失效,产投成本锚定可能被击穿。除非注入商业航天、AI等强热门资产,否则方案公布后优先抢跑,至少先出成本或减半。

## 壳价值与价格区间

- 总市值10亿-15亿是典型壳价值观察区间。
- 低于6亿可能基本面太烂或退市风险过高;高于30亿壳价值吸引力下降。
- 股价1.5元-2.5元较理想;低于1元有面值退市风险,高于3元性价比下降。
- 主板优先。创业板/科创板ST流动性和交易机制不同,普通投资者谨慎。

壳价值只提供底部想象,不能替代退市排雷和资产质量核查。

## 工具工作流

优先用AI-Tools获取结构化数据,用东方财富skills补公告和交易所信息,用WebSearch查最新舆情、处罚、重整进展。

| 任务 | 首选工具 | 交叉验证 |
|---|---|---|
| 搜索ST标的 | `StockSearch`, `ChoiceStockByIndicators`, `GetHotStockRank` | 东方财富行情/板块页 |
| 实时价格与市值 | `QueryStockPriceInfo`, `GetDailyKLineData` | 东方财富个股页 |
| 公告排雷 | `GetStockNotice`, `GetStockNoticeByType` | 东方财富公告、交易所公告、WebSearch |
| 财务与审计 | `GetFinancialReport`, `GetFinancialIndicators`, `GetIncomeStatement`, `GetBalanceSheet`, `GetCashFlowStatement` | 年报、审计意见公告 |
| 重整/处罚/诉讼 | `GetStockRelatedNews`, `GetStockResearchReport`, `GetNoticeDetail` | WebSearch + 东方财富公告 |
| 资金与筹码 | `GetStockMoneyTrend`, `GetStockMoneyFlowDetail`, `GetChipDistribution`, `GetCostAnalysis`, `GetLongTigerRank` | 龙虎榜、成交额 |
| 板块环境 | `GetAStockIndexes`, `GetIndustryMoneyRank`, `GetMarketHotNews`, `GetCapitalTideReport` | WebSearch市场新闻 |

不要只看单一来源。ST公司信息质量差,公告、财务、新闻至少两类来源交叉验证。

## 分析输出模板

每次分析ST股,必须按以下结构输出:

```markdown
## 结论先行
- 评级: 可跟踪 / 小仓试错 / 只做反包 / 回避
- 核心理由: [一句话]
- 最大风险: [一句话]

## 1. ST类型与退市排雷
- ST类型: 财务型 / 规则型 / 审计型 / 重大违法型 / 假ST
- 戴帽原因:
- 一票否决检查:
- 退市风险判断:

## 2. 市场环境
- 微盘股/ST板块状态:
- 流动性状态:
- 当前是否适合做ST策略:

## 3. 重整/摘帽/保壳路径
- 所处阶段:
- 下一关键节点:
- 产业投资人/财务投资人成本:
- 是否属于书困型或换头型:

## 4. 赔率与买卖点
- 赔率来源: 壳价值 / 暗线重整 / 明线套利 / 假ST反包 / 摘帽预期
- 参考买入区间:
- 目标兑现点:
- 失效条件:

## 5. 仓位与风控
- 单票仓位上限:
- ST总仓位上限:
- 流动性可承载仓位:
- 必须立即退出的触发器:

## 6. 跟踪清单
- 后续公告:
- 财报/年报日期:
- 重整节点:
- 监管/处罚进展:
```

如果数据不足,不要给买入建议。输出"信息不足,只能列入观察"并说明缺哪几项数据。

## 买入纪律

可以买入或跟踪的典型情况:
- 财务型或规则型ST,退市红线已排除,有明确保壳/重整/资产注入动作。
- 市值接近壳价值,股价远离面值退市线,成交额足够。
- 暗线阶段已有真实线索,但方案未完全明牌。
- 财投/产投成本经除权后计算仍明显高于当前价格,且不是纯财务套利盘。
- 假ST连续跌停后恐慌充分释放,仅做短线反包。

禁止买入:
- 摘帽申请后追涨。
- 资本公积转增、路条、方案公布后把明牌利好当新买点。
- 只因"跌得多"抄底。
- 没算除权后的投资人成本。
- 没有可执行退出路径。

## 卖出与退出纪律

- 摘帽当天或次日减仓至少一半。
- 重整方案公布后优先减仓,尤其市场环境弱时。
- 事件兑现但股价不涨或高开低走,视为反馈弱,减仓。
- 重整方案被否、预重整延期、投资人退出、处罚加重,立即退出。
- 独董/财务负责人/审计负责人辞职,立即降低仓位或退出。
- 到10月路条未批,退出极限保壳博弈。
- 股价接近1元,退出面值退市风险。
- 一字跌停无法卖出时,每日最早委托挂跌停价,不要幻想反弹。

## 常见错误

| 错误 | 正确做法 |
|---|---|
| 把所有ST当一类 | 先分财务型、规则型、审计型、重大违法型、假ST |
| 只看净利润转正 | 看扣非、现金流、营收质量、审计意见 |
| 迷信产投成本 | 按除权后成本计算,并承认极端环境可跌破 |
| 把书困型当换头型 | 区分只化债与注入新资产/改善主营 |
| 等公告确认再买 | 明线容易见光死,公告更多是卖点 |
| 用ST指数代表真实体验 | 记住幸存者偏差,退市股会被剔除 |
| 忽视地域和治理信号 | 山海关外、独董辞职、财务负责人离职都要高权重 |
| 认为止损一定能执行 | ST一字跌停时流动性消失,预防优先于止损 |

## 最终提醒

ST策略高赔率但高难度,不适合重仓。没有排雷、没有阶段判断、没有流动性测算时,默认结论是回避。任何输出都必须包含风险提示:本分析不构成投资建议,ST股票存在连续跌停、停牌和本金全损风险。
```

- [ ] **Step 3: Verify the frontmatter**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path('.claude/skills/st-stock-strategy/SKILL.md')
text = p.read_text()
assert text.startswith('---\nname: "st-stock-strategy"')
assert 'description: "Use when' in text
assert text.split('---', 2)[1].count('description:') == 1
print('frontmatter ok')
PY
```

Expected: `frontmatter ok`.

- [ ] **Step 4: Verify key strategy coverage**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
text = Path('.claude/skills/st-stock-strategy/SKILL.md').read_text()
required = [
    '财务型ST', '规则型ST', '审计型ST', '重大违法型ST', '假ST',
    '山海关外', '独立董事', '10月重整路条', '大存大贷',
    '预重整/签投资人', '法院裁定重整', '重整路条', '资本公积转增', '填权', '摘帽',
    '暗线', '明线', '书困型', '换头型', '双红', '幸存者偏差',
    'AI-Tools', '东方财富', 'WebSearch', 'GetStockNotice', 'GetFinancialIndicators'
]
missing = [s for s in required if s not in text]
if missing:
    raise SystemExit('missing: ' + ', '.join(missing))
print('coverage ok')
PY
```

Expected: `coverage ok`.

---

### Task 2: Validate the skill with the pressure scenario

**Files:**
- Read-only: `.claude/skills/st-stock-strategy/SKILL.md`

- [ ] **Step 1: Run a skill-aware subagent scenario**

Dispatch a subagent with this prompt:

```text
请阅读并遵循 .claude/skills/st-stock-strategy/SKILL.md。用户要求: 帮我找 1-3 只 ST/*ST 股票机会，并给买卖点和风控。你不需要真的给具体股票，但要输出你会如何分析、必须调用哪些工具、哪些情况一票否决、如何判断重整阶段、如何处理暗线/明线、如何设置仓位和退出。重点展示流程是否完整。
```

Expected: subagent mentions ST type classification, one-vote vetoes, market environment/double-red, restructuring stages, dark-line vs public-line logic, tool matrix, and output template.

- [ ] **Step 2: Compare against baseline failures**

Confirm the skill-aware answer fixes these baseline gaps:

```text
- Does not treat all ST stocks as one category.
- Mentions fake ST反包 as short-term only.
- Mentions 山海关外/立案未结/独董辞职/10月路条未批 as veto or exit signals.
- Distinguishes 预重整、法院裁定、路条、转增、填权、摘帽.
- Treats方案公布/摘帽 as sell or reduce events, not fresh buy signals.
- Warns that 2026 event feedback is weak, book-debt-only restructuring is less effective, and investor cost can be broken.
- Requires AI-Tools + 东方财富 + WebSearch cross-validation.
```

Expected: every item is satisfied. If any item is missing, edit `SKILL.md` to add explicit wording and rerun Step 1.

- [ ] **Step 3: Check git diff**

Run:

```bash
git diff -- .claude/skills/st-stock-strategy/SKILL.md
```

Expected: diff only changes the ST skill file. Do not revert unrelated dirty files.

---

### Task 3: Report completion

**Files:**
- No file changes.

- [ ] **Step 1: Summarize changed areas**

Report these points to the user:

```text
已更新 .claude/skills/st-stock-strategy/SKILL.md。
主要增强: ST类型分类、一票否决、市场环境开关、重整阶段、暗线/明线、工具矩阵、输出模板、常见错误。
```

- [ ] **Step 2: Mention validation**

Report whether the coverage scripts and pressure scenario passed. If the subagent found a missing item and it was fixed, mention the fix.

- [ ] **Step 3: Do not commit unless user asks**

The user's global instruction says only commit when explicitly instructed, and commit messages must not include `Co-Authored-By`. Do not commit this change unless the user asks.

---

## Self-Review

- Spec coverage: The plan covers the user request to understand the ST note and write a complete ST stock analysis skill using AI-Tools, 东方财富 skills, and WebSearch.
- Placeholder scan: No TBD/TODO placeholders remain; all verification commands and expected results are explicit.
- Type consistency: File paths consistently use `.claude/skills/st-stock-strategy/SKILL.md` as the only modified file.
