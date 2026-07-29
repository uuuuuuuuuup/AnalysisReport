# 聚宽（JoinQuant）策略 API 笔记

> 来源：https://www.joinquant.com/help/api/help#api:%E7%AD%96%E7%95%A5API%E4%BB%8B%E7%BB%8D
> 整理日期：2026-07-26

---

## 目录

- [一、策略程序架构](#一策略程序架构)
- [二、策略设置函数](#二策略设置函数)
- [三、数据获取函数](#三数据获取函数)
- [四、jqlib 因子库](#四jqlib-因子库)
- [五、数据处理函数](#五数据处理函数)
- [六、组合优化函数 portfolio_optimizer](#六组合优化函数-portfolio_optimizer)
- [七、交易函数](#七交易函数)
- [八、核心对象](#八核心对象)
- [九、其他辅助函数](#九其他辅助函数)
- [十、策略组合操作](#十策略组合操作)
- [十一、Tick 级策略专用函数](#十一tick-级策略专用函数)
- [十二、融资融券专用函数](#十二融资融券专用函数)
- [十三、期货策略专用函数](#十三期货策略专用函数)
- [十四、归因分析说明](#十四归因分析说明)
- [十五、常用策略示例](#十五常用策略示例)

---

## 一、策略程序架构

> ♠ 回测/模拟专用

### 1. initialize(context)

初始化函数，整个回测/模拟最开始执行一次。

```python
def initialize(context):
    g.security = "000001.XSHE"
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
```

### 2. 定时运行函数

#### run_daily(func, time='9:30', reference_security)

#### run_weekly(func, weekday, time='9:30', reference_security, force=False)

#### run_monthly(func, monthday, time='9:30', reference_security, force=False)

**time 参数支持：**
- 具体时间：`"10:00"`
- 每根 bar：`"every_bar"`
- 相对开盘：`"open+5m"` 形式

> **建议使用 run_daily 系列，不要同时使用 handle_data**

### 3. handle_data(context, data)

每个单位时间调用一次（tick 频率不支持）。

### 4. before_trading_start(context)

每天开盘前调用（9:00）。

### 5. after_trading_end(context)

每天收盘后调用（15:30）。

### 6. on_strategy_end(context)

策略正常结束时调用。

### 7. process_initialize(context)

每次进程重启时执行，用于初始化不能持久化的内容。

### 8. after_code_changed(context)

模拟交易更换代码后运行。

### 9. unschedule_all()

取消所有定时运行。

### 10. on_event(context, event)

事件回调函数（分红送股、强平等事件）。

---

## 二、策略设置函数

### 1. set_benchmark(security)

设置基准，支持单标的或 dict 组合。

```python
set_benchmark('000300.XSHG')
```

### 2. set_order_cost(cost, type, ref=None)

设置佣金/印花税。

**OrderCost 参数：**
- `open_tax`：买入印花税
- `close_tax`：卖出印花税
- `open_commission`：买入佣金
- `close_commission`：卖出佣金
- `close_today_commission`：平今仓佣金（期货）
- `min_commission`：最低佣金

**type：** `'stock'` / `'fund'` / `'index_futures'` / `'futures'` 等

```python
set_order_cost(OrderCost(
    close_tax=0.001,
    open_commission=0.0003,
    close_commission=0.0003,
    min_commission=5
), type='stock')
```

### 3. set_slippage(object, type=None, ref=None)

设置滑点。

- `FixedSlippage(0.02)`：固定值滑点
- `PriceRelatedSlippage(0.00246)`：百分比滑点（**默认**）
- `StepRelatedSlippage(2)`：跳数滑点（期货专用）

### 4. set_option('use_real_price', True) ⭐

开启动态复权（真实价格）模式，**强烈建议开启**，避免前复权带来的未来函数问题。

### 5. set_option('order_volume_ratio', 0.25)

设置成交量比例限制。

### 6. set_option('match_with_order_book', True)

开启盘口撮合（仅模拟盘）。

### 7. set_option('avoid_future_data', True)

开启避免未来数据模式。

### 8. set_universe(security_list)

设定股票池（history 专用）。

### 9. disable_cache()

关闭缓存（内存占用大时使用）。

---

## 三、数据获取函数

### 1. get_price

```python
get_price(security, start_date=None, end_date=None, frequency='daily',
          fields=None, skip_paused=False, fq='pre', count=None)
```

获取历史行情，返回 DataFrame / Panel。

### 2. history ♠

```python
history(count, unit='1d', field='avg', security_list=None,
        df=True, skip_paused=False, fq='pre')
```

获取历史行情，多标的单字段。

### 3. attribute_history ♠

```python
attribute_history(security, count, unit='1d',
                  fields=('open', 'close', 'high', 'low', 'volume', 'money'),
                  df=True, skip_paused=True, fq='pre')
```

获取单标的多字段历史数据，**默认跳过停牌**。

### 4. get_bars

```python
get_bars(security, count, unit='1d',
         fields=('date', 'open', 'high', 'low', 'close', 'volume'),
         include_now=False, end_dt=None, fq_ref_date=None, df=False)
```

获取各种周期 bar 数据。

### 5. get_current_tick ♠

```python
get_current_tick(security)
```

获取最新 tick 数据。

### 6. get_ticks

```python
get_ticks(security, end_dt, start_dt=None, count=None,
          fields=['current', 'volume', 'money'])
```

获取 tick 历史数据，支持五档盘口。

### 7. get_current_data ♠

```python
get_current_data()
```

获取当前涨跌停价、是否停牌、当天开盘价等。返回 dict，key 为标的代码。

**常用属性：**
- `high_limit`：涨停价
- `low_limit`：跌停价
- `paused`：是否停牌
- `day_open`：当日开盘价
- `last_price`：最新价

### 8. get_extras

```python
get_extras(info, security_list, start_date=None, end_date=None, df=True, count=None)
```

获取 ST 状态、期货结算价等。

**info 可选：** `'is_st'` / `'acc_net_value'` / `'unit_net_value'` / `'futures_sett_price'` / `'futures_positions'`

### 9. get_fundamentals

```python
get_fundamentals(query_object, date=None, statDate=None)
```

查询财务数据（SQLAlchemy Query 风格）。

```python
from jqdata import *
q = query(valuation).filter(valuation.code == '000001.XSHE')
df = get_fundamentals(q)
```

### 10. get_fundamentals_continuously

```python
get_fundamentals_continuously(query_object, end_date=None, count=1)
```

查询多日财务数据。

### 11. finance.run_query

```python
finance.run_query(query_object)
```

查询沪深港通、股东信息等。**每次最多返回 4000 行**。

### 12. macro.run_query

```python
macro.run_query(query_object)
```

查询宏观经济数据。

### 13. get_billboard_list

```python
get_billboard_list(stock_list, start_date=None, end_date=None, count=None)
```

获取龙虎榜数据。

### 14. get_index_stocks

```python
get_index_stocks(index_symbol, date=None)
```

获取指数成分股列表。

### 15. get_index_weights

```python
get_index_weights(index_id, date=None)
```

获取指数成分股权重（每月更新一次）。

### 16. get_industry_stocks

```python
get_industry_stocks(industry_code, date=None)
```

获取行业成分股。

### 17. get_concept_stocks

```python
get_concept_stocks(concept_code, date=None)
```

获取概念板块成分股。

### 18. get_industries

```python
get_industries(name, date=None)
```

获取行业列表。

**name 可选：** `'sw_l1'` / `'sw_l2'` / `'sw_l3'` / `'jq_l1'` / `'jq_l2'` / `'zjw'`

### 19. get_concepts

```python
get_concepts()
```

获取所有概念板块列表。

### 20. get_all_securities

```python
get_all_securities(types=[], date=None)
```

获取所有标的信息。

**types 可选：** `'stock'`, `'fund'`, `'index'`, `'futures'`, `'options'`, `'etf'`, `'lof'` 等

> **types 为空时返回所有股票，不包括基金、指数和期货**

### 21. get_security_info

```python
get_security_info(code, date=None)
```

获取单个标的信息。

**属性：** `display_name`, `name`, `start_date`, `end_date`, `type`, `parent`

### 22. get_industry

```python
get_industry(security, date=None)
```

查询股票所属行业。返回嵌套 dict，包含 jq_l1/jq_l2/sw_l1/sw_l2/sw_l3/zjw 各分类。

### 23. get_concept

```python
get_concept(security, date=None)
```

获取股票所属概念板块。

### 24. get_all_trade_days

```python
get_all_trade_days()
```

获取所有交易日（numpy.ndarray，元素为 datetime.date）。

### 25. get_trade_days

```python
get_trade_days(start_date=None, end_date=None, count=None)
```

获取指定范围交易日。

### 26. get_money_flow

```python
get_money_flow(security_list, start_date=None, end_date=None, fields=None, count=None)
```

获取资金流信息（主力、超大单、大单、中单、小单）。

### 27. get_call_auction

```python
get_call_auction(security, start_date=None, end_date=None, fields=None)
```

获取集合竞价 tick 数据（09:25）。

### 28. get_trade_day

```python
get_trade_day(security, query_dt)
```

根据标的获取指定时刻对应的交易日。

### 29. get_history_fundamentals

```python
get_history_fundamentals(security, fields, watch_date=None, stat_date=None,
                         count=1, interval='1q', stat_by_year=False)
```

获取多个季度/年度的历史财务数据。

### 30. get_valuation

```python
get_valuation(security, start_date=None, end_date=None, fields=None, count=None)
```

获取市值表数据（PE、PB、市值、换手率等）。

### 31. 因子库相关

- `get_all_factors()`：获取所有因子列表
- `get_factor_values(securities, factors, ...)`：获取因子库因子数据
- `get_factor_kanban_values(...)`：获取因子看板数据

---

## 四、jqlib 因子库

### 1. alpha101

WorldQuant 的 101 个 Alpha 因子。

```python
from jqlib.alpha101 import *
a = alpha_001('2017-03-10', '000300.XSHG')
```

### 2. alpha191

国泰君安 191 个短周期阿尔法因子。

```python
from jqlib.alpha191 import *
a = alpha_007(code_list, end_date='2017-04-04')
```

### 3. technical_analysis

技术分析指标库（GDX 等）。

```python
from jqlib.technical_analysis import *
gdx_jax, gdx_ylx, gdx_zcx = GDX(security_list, check_date='2017-01-04', N=30, M=9)
```

---

## 五、数据处理函数

> 导入：`from jqfactor import ...`

### 1. neutralize - 中性化

```python
neutralize(series, how=None, date=None, axis=1, fillna=None, add_constant=False)
```

**how 默认：** `['jq_l1', 'market_cap']`（行业+市值中性化）

支持行业分类：`'jq_l1'`, `'jq_l2'`, `'sw_l1'`, `'sw_l2'`, `'sw_l3'`

支持财务因子：`'market_cap'`, `'ln_market_cap'`, `'net_profit'` 等

### 2. winsorize - 去极值

```python
winsorize(series, scale=None, range=None, qrange=None,
          inclusive=True, inf2nan=True, axis=1)
```

**三种模式三选一：**
- `scale`：标准差倍数，[μ - scale×σ, μ + scale×σ]
- `range`：上下边界列表
- `qrange`：分位数边界，如 `[0.05, 0.95]`

### 3. winsorize_med - 中位数去极值

```python
winsorize_med(series, scale=1, inclusive=True, inf2nan=True, axis=1)
```

基于中位数和 MAD 的去极值。

### 4. standardlize - 标准化 (z-score)

```python
standardlize(series, inf2nan=True, axis=1)
```

---

## 六、组合优化函数 portfolio_optimizer

> 导入：`from jqlib.optimizer import *`

```python
portfolio_optimizer(date, securities, target, constraints,
                    bounds=[Bound(0.0, 1.0)],
                    default_port_weight_range=[0.0, 1.0],
                    ftol=1e-9, return_none_if_fail=True)
```

### 目标函数 (target) - 只能选一个

| 函数 | 说明 |
|------|------|
| `MinVariance(count=250)` | 组合风险最小化（最小方差） |
| `MaxProfit(count=250)` | 组合收益最大化 |
| `MaxSharpeRatio(rf=0.0, weight_sum_equal=1.0, count=250)` | 夏普比率最大化 |
| `MinTrackingError(benchmark, count=250)` | 追踪误差最小化 |
| `RiskParity(count=250, risk_budget=None)` | 风险平价 |
| `MaxScore(scores)` | 打分最大化 |
| `MinScore(scores)` | 打分最小化 |
| `MaxFactorValue(factor, count=1)` | 因子值最大化（仅股票） |
| `MinFactorValue(factor, count=1)` | 因子值最小化（仅股票） |

### 约束函数 (constraints) - 可多个

| 函数 | 说明 |
|------|------|
| `WeightConstraint(low, high)` | 组合总权重范围限制 |
| `WeightEqualConstraint(limit=1.0)` | 组合总权重和固定 |
| `AnnualStdConstraint(limit, count=250)` | 年化波动率上限 |
| `AnnualProfitConstraint(limit, count=250)` | 年化收益下限 |
| `IndustryConstraint(industry_code, low, high)` | 单一行业权重限制 |
| `IndustriesConstraint(industry_code, low, high)` | 行业分类权重限制 |
| `MarketConstraint(market_type, low, high)` | 市场类型权重限制 |
| `ExposureConstraint(factor, low, high, count=1)` | 因子暴露限制 |
| `BarraConstraint(...)` | Barra 风险因子暴露限制 |
| `IndustryDeviationConstraint(industry_code, benchmark, limit)` | 行业偏离度限制 |
| `IndustriesDeviationConstraint(industry_code, benchmark, limit)` | 行业分类偏离度限制 |
| `TrackingErrorConstraint(benchmark, limit, count=250)` | 追踪误差限制 |
| `TurnoverConstraint(limit, current_portfolio=None)` | 换手率限制 |
| `RatioConstraint(ratio, low, high, ...)` | 比率限制（sharpe/var/cvar等） |
| `MaxDrawdownConstraint(limit, count=250)` | 最大回撤限制 |

### 边界函数 (bounds) - 单标的权重限制

| 函数 | 说明 |
|------|------|
| `Bound(low=0.0, high=1.0)` | 每只标的权重上下限 |
| `IndustryBound(industry_code, low, high)` | 某行业单股权重限制 |
| `LiquidityBound(limit, capital, count=1, subset=None)` | 流动性限制（成交量占比） |
| `CapBound(limit, capital, count=1, subset=None)` | 市值限制 |

---

## 七、交易函数

> ♠ 回测/模拟专用
> 所有下单函数可在 handle_data 及定时函数（time='every_bar' 或具体时间点）中使用

### 1. order - 按股数下单

```python
order(security, amount, style=None, side='long', pindex=0, close_today=False)
```

- **amount**：正数买入，负数卖出
- **style**：`None`=市价单 / `MarketOrderStyle()` / `LimitOrderStyle(price)`
- **side**：`'long'` 多单 / `'short'` 空单（股票不支持空单）
- **pindex**：子账户索引，默认 0
- **返回**：Order 对象或 None

```python
order('000001.XSHE', 100)                          # 市价买入100股
order('000001.XSHE', 100, LimitOrderStyle(10.0))  # 限价10元买入
order('688001.XSHG', 100, MarketOrderStyle(10))   # 科创板保护价
```

### 2. order_target - 目标股数下单

```python
order_target(security, amount, style=None, side='long', pindex=0, close_today=False)
```

调整到目标股数。**若有未完成订单，会先取消。**

```python
order_target('000001.XSHE', 0)    # 清仓
order_target('000001.XSHE', 100)  # 调到100股
```

### 3. order_value - 按价值下单

```python
order_value(security, value, style=None, side='long', pindex=0, close_today=False)
```

买卖指定价值的标的。value 为正买入，为负卖出。

### 4. order_target_value - 目标价值下单

```python
order_target_value(security, value, style=None, side='long', pindex=0, close_today=False)
```

调整到目标价值。

```python
order_target_value('000001.XSHE', 0)        # 清仓
order_target_value('000001.XSHE', 10000)    # 调到1万元
```

### 5. cancel_order - 撤单

```python
cancel_order(order)  # Order对象或order_id
```

### 6. get_open_orders - 获取未完成订单

```python
get_open_orders()
```

返回 dict，key 为 order_id，value 为 Order 对象。

### 7. get_orders - 获取订单信息

```python
get_orders(order_id=None, security=None, status=None)
```

获取当天所有订单，可按 order_id / 标的 / 状态筛选。

### 8. get_trades - 获取成交信息

```python
get_trades()
```

获取当天所有成交记录（一个订单可能分多次成交）。

### 9. inout_cash - 账户出入金

```python
inout_cash(cash, pindex=0)
```

正为入金，负为出金。当日出入金从当日开始记入成本。

### 10. batch_submit_orders - 篮子下单

```python
batch_submit_orders(orders)
```

批量委托，任一校验失败则全部失败。

```python
orders = [
    {"security": "000001.XSHE", "amount": 100},
    {"security": "600660.XSHG", "amount": 100},
]
batch_submit_orders(orders)
```

### 11. batch_cancel_orders - 批量撤单

```python
batch_cancel_orders(orders)  # 订单对象或ID列表
```

### 订单失败常见原因

1. 股票停牌
2. 标的代码错误、已退市、未上市
3. 账户类型错误
4. 调整后下单数量为0
5. 股票下空单
6. 科创板市价单未指定保护价

### A股交易规则

- 每次交易数量为 **100股整数倍**
- 卖光所有股票时不受100股限制
- 科创板：200股起，可交易200以上零散股
- 每日结束自动取消所有未完成订单
- 每日下单最大数量：**10000笔**

---

## 八、核心对象

### 1. g - 全局变量对象

```python
def initialize(context):
    g.security = "000001.XSHE"
    g.count = 1
```

- 模拟盘每天重启，g 中变量会被 pickle 序列化保存到磁盘
- **以 `__` 开头的变量不被序列化**（用于不可序列化对象）
- 保存大小上限 **30M**
- 不可序列化对象在 `process_initialize` 中初始化

```python
def process_initialize(context):
    g.__q = query(valuation)  # 双下划线开头，不持久化
```

### 2. Context - 策略上下文

**核心属性：**
- `subportfolios`：子账户数组（SubPortfolio 对象）
- `portfolio`：总账户信息（Portfolio 对象，单仓位时等于 subportfolios[0]）
- `current_dt`：当前单位时间开始时间（datetime）
- `previous_date`：前一个交易日（date）
- `universe`：set_universe 设定的股票池
- `run_params`：运行参数（start_date, end_date, type, frequency）

> context 也支持添加自定义变量，与 g 类似，但**推荐使用 g**

### 3. SubPortfolio - 子账户信息

| 属性 | 说明 |
|------|------|
| `inout_cash` | 累计出入金 |
| `available_cash` | 可用资金 |
| `transferable_cash` | 可取资金 |
| `locked_cash` | 挂单锁住资金 |
| `type` | 账户类型 |
| `long_positions` | 多单持仓 dict |
| `short_positions` | 空单持仓 dict |
| `positions_value` | 持仓价值 |
| `total_value` | 总资产 |
| `total_liability` | 总负债 |
| `net_value` | 净资产 |
| `cash_liability` | 融资负债 |
| `sec_liability` | 融券负债 |
| `interest` | 利息总负债 |
| `maintenance_margin_rate` | 维持担保比例 |
| `available_margin` | 融资融券可用保证金 |
| `margin` | 保证金 |

### 4. Portfolio - 总账户信息

所有子账户的汇总，属性与 SubPortfolio 类似，另含：
- `returns`：累计收益
- `starting_cash`：初始资金（等于 inout_cash）
- `positions`：等同于 long_positions

### 5. Position - 持仓标的信息

| 属性 | 说明 |
|------|------|
| `security` | 标的代码 |
| `price` | 最新行情价格 |
| `acc_avg_cost` | 累计持仓成本（清仓/减仓时更新） |
| `avg_cost` | 当前持仓成本（仅加仓时更新，用于浮盈计算） |
| `hold_cost` | 当日持仓成本 |
| `init_time` | 建仓时间 |
| `transact_time` | 最后交易时间 |
| `locked_amount` | 挂单冻结仓位 |
| `total_amount` | 总仓位（不含挂单冻结） |
| `closeable_amount` | 可卖出仓位 |
| `today_amount` | 今日开仓量 |
| `value` | 标的价值 |
| `side` | 多/空方向 |
| `pindex` | 仓位索引 |

### 6. SecurityUnitData - 单标的单位时间数据

**基本属性：** `open`, `close`, `high`, `low`, `volume`, `money`, `factor`, `high_limit`, `low_limit`, `avg`, `pre_close`, `paused`

**方法：**
- `mavg(days, field='close')`：移动平均
- `vwap(days)`：成交量加权平均价
- `stddev(days)`：标准差
- `isnan()`：数据是否有效

> 为了向前兼容保留，**由于效率问题不推荐使用**，建议用 history/attribute_history/get_price

### 7. tick 对象

| 属性 | 说明 |
|------|------|
| `code` | 标的代码 |
| `datetime` | tick 时间 |
| `current` | 最新价 |
| `open` / `high` / `low` | 当日开/高/低 |
| `volume` / `money` | 累计成交量/额 |
| `position` | 持仓量（期货） |
| `a1_v~a5_v` / `a1_p~a5_p` | 卖一到卖五量/价 |
| `b1_v~b5_v` / `b1_p~b5_p` | 买一到买五量/价 |

### 8. Trade - 成交对象

- `time`：交易时间
- `security`：标的代码
- `amount`：交易数量
- `price`：交易价格
- `trade_id`：成交记录 ID
- `order_id`：对应订单 ID

### 9. Order - 订单对象

| 属性 | 说明 |
|------|------|
| `status` | 订单状态（OrderStatus） |
| `add_time` | 添加时间 |
| `is_buy` | 买/卖 |
| `amount` | 下单数量 |
| `filled` | 已成交数量 |
| `security` | 标的代码 |
| `order_id` | 订单 ID |
| `price` | 平均成交价格 |
| `avg_cost` | 持仓成本（卖）/ 买入均价（买） |
| `side` | 多/空 |
| `action` | 开/平 |
| `commission` | 交易费用 |

> **不可以在策略中保存当天的订单信息到之后的交易日使用**

### 10. OrderStatus - 订单状态

```python
class OrderStatus(Enum):
    new = 8        # 新创建未委托（盘前/隔夜单）
    open = 0       # 未完成，无成交
    filled = 1     # 未完成，部分成交
    canceled = 2   # 已撤销（可能有成交）
    rejected = 3   # 交易所拒绝（可能有成交）
    held = 4       # 全部成交
```

> 判断时需转为 str：`str(order.status) == 'held'`

### 11. OrderStyle - 下单方式

**市价单：**
```python
MarketOrderStyle(limit_price=None)
# limit_price 为科创板市价单保护价
```

**限价单：**
```python
LimitOrderStyle(limit_price)
```

**停止单：**
```python
StopMarketOrderStyle(mode, stop_price)
StopLimitOrderStyle(mode, stop_price, limit_price)
# mode: 'stop_loss' 止损 / 'take_profit' 止盈
```

### 12. Event - 事件对象

**DividendsEvent（分红送股）：**
- `name`, `pindex`, `security`, `side`, `dividends`

**ForcedLiquidationEvent（强行平仓）：**
- `name`, `pindex`, `security`, `side`, `amount`

---

## 九、其他辅助函数

### 1. record ♠ - 画图函数

```python
record(**kwargs)
```

在回测图表上绘制额外曲线。**必须从回测开始调用，不支持中间开始。**

```python
record(price=d.price, open=d.open, close=d.close)
```

### 2. send_message ♠ - 发送自定义消息

```python
send_message(message, channel='weixin')
```

仅聚宽官网实时运行模拟交易可用。每天最多 **5 条**，单条不超过 200 字符。

### 3. log - 日志

```python
log.error(content)
log.warn(content)
log.info(content)
log.debug(content)
print(content)  # 等同于 log.info
```

**设置日志级别：**
```python
log.set_level(name, level)
# name: 'order' / 'history' / 'strategy' / 'system'
# level: 'debug' < 'info' < 'warning' < 'error'
```

### 4. write_file - 写入研究文件

```python
write_file(path, content, append=False)
```

将回测/模拟数据写入投资研究文件。

### 5. read_file - 读取研究文件

```python
read_file(path)
```

读取研究中的私有文件，返回原始内容。

### 6. normalize_code - 股票代码格式转换

```python
normalize_code(code)
```

将其他形式代码转为聚宽格式。

```python
normalize_code(('000001', 'SZ000001', '000001.sz'))
# ['000001.XSHE', '000001.XSHE', '000001.XSHE']
```

### 7. enable_profile ♠ - 性能分析

```python
enable_profile()
```

开启性能分析，**必须放在所有代码最上方**。仅回测可用。

### 8. create_backtest - 研究中创建回测

```python
create_backtest(algorithm_id, start_date, end_date, frequency="day",
                initial_cash=10000, initial_positions=None, extras=None,
                name=None, code="", benchmark=None, use_credit=False)
```

仅研究环境可用，返回 backtest_id。

### 9. get_backtest - 获取回测信息

```python
gt = get_backtest(backtest_id)
```

**方法：**
- `gt.get_status()` - 回测状态
- `gt.get_params()` - 回测参数
- `gt.get_results()` - 收益曲线
- `gt.get_positions()` - 持仓详情
- `gt.get_orders()` - 交易详情
- `gt.get_records()` - record 记录
- `gt.get_risk()` - 总风险指标
- `gt.get_period_risks()` - 分月风险指标
- `gt.get_balances()` - 每日市值

---

## 十、策略组合操作

### 1. set_subportfolios - 初始化子账户

```python
set_subportfolios([SubPortfolioConfig(cash, type), ...])
```

**只能在 initialize 中调用。**

**type 可选：**
- `'stock'`：股票+基金
- `'index_futures'`：金融期货
- `'futures'`：股指期货+商品期货
- `'stock_margin'`：融资融券

```python
# 三分账户示例
init_cash = context.portfolio.starting_cash / 3
set_subportfolios([
    SubPortfolioConfig(cash=init_cash, type='stock'),
    SubPortfolioConfig(cash=init_cash, type='futures'),
    SubPortfolioConfig(cash=init_cash, type='stock_margin'),
])
```

### 2. transfer_cash - 账户间转移资金

```python
transfer_cash(from_pindex, to_pindex, cash)
```

及时到账。

---

## 十一、Tick 级策略专用函数

> 需要会员权限开通，必须使用真实价格模式

### 1. handle_tick

```python
def handle_tick(context, tick):
    ...
```

订阅标的产生 tick 事件时调用。**handle_data 不会在 tick 频率策略中调用。**

### 2. subscribe / unsubscribe

```python
subscribe(security, frequency='tick')
unsubscribe(security, frequency='tick')
unsubscribe_all()
```

- 模拟交易最多同时订阅 **100 个**标的
- 股票 tick 数据：2017-01-01 至今，每3秒一次快照，五档盘口
- 期货 tick 数据：2010-01-01 至今，每0.5秒一次快照，一档盘口

---

## 十二、融资融券专用函数

### 初始化融资融券账户

```python
def initialize(context):
    set_subportfolios([SubPortfolioConfig(
        cash=context.portfolio.starting_cash,
        type='stock_margin'
    )])
```

### 利率与保证金设置

```python
set_option('margincash_interest_rate', 0.08)      # 融资利率，默认8%
set_option('margincash_margin_rate', 1.5)         # 融资保证金比率，默认100%
set_option('marginsec_interest_rate', 0.10)       # 融券利率，默认10%
set_option('marginsec_margin_rate', 1.5)          # 融券保证金比率，默认100%
```

### 融资操作

| 函数 | 说明 |
|------|------|
| `margincash_open(security, amount, style, pindex)` | 融资买入 |
| `margincash_close(security, amount, style, pindex)` | 卖券还款 |
| `margincash_direct_refund(value, pindex)` | 直接还款 |

### 融券操作

| 函数 | 说明 |
|------|------|
| `marginsec_open(security, amount, style, pindex)` | 融券卖出 |
| `marginsec_close(security, amount, style, pindex)` | 买券还券 |
| `marginsec_direct_refund(security, amount, pindex)` | 直接还券 |

### 标的查询

```python
get_margincash_stocks(date=None)   # 融资标的列表
get_marginsec_stocks(date=None)   # 融券标的列表
```

### 融资融券数据

```python
from jqdata import *
get_mtss(security_list, start_date=None, end_date=None, fields=None, count=None)
```

字段：`fin_value`(融资余额), `fin_buy_value`(融资买入额), `sec_value`(融券余量), `sec_sell_value`(融券卖出量), `fin_sec_value`(融资融券余额) 等

---

## 十三、期货策略专用函数

### 初始化期货账户

```python
def initialize(context):
    set_subportfolios([SubPortfolioConfig(
        cash=context.portfolio.starting_cash,
        type='futures'
    )])
```

### 合约相关

**主力连续合约：** 品种代码 + `9999` + 交易所后缀（如 `AG9999.XSGE`）
- 基于持仓量拼接，**不可直接下单**

**品种指数：** 品种代码 + `8888` + 交易所后缀（如 `AG8888.XSGE`）
- 持仓量加权平均，**不可直接下单**

```python
get_dominant_future('IF')           # 获取主力合约代码
get_future_contracts('IF')          # 获取可交易合约列表
```

### 保证金设置

```python
set_option('futures_margin_rate', 0.15)          # 全局设置
set_option('futures_margin_rate.IF', 0.15)       # 按品种设置
set_option('futures_margin_rate.AU1709', 0.08)   # 按合约设置
```

**默认值：** 股指期货 0.15，商品期货各品种不同（0.04~0.2）

### 保证金预警

```python
context.subportfolios[i].is_dangerous(margin_rate)
```

低于指定比例返回 True。

### 期货下单

与股票共用 order 系列函数，需指定 `side='long'/'short'` 和 `close_today` 参数。

**平今字段（仅上期所、能源中心、中金所生效）：**
- `close_today=True`：只平今仓，不足则废单
- `close_today=False`：优先平昨仓，不足平今仓

### 期货行情数据

get_price / history / get_bars 等均可使用，新增字段 `open_interest`（持仓量）。

### 期货注意事项

- 有夜盘品种的交易日从前一天 21:00 开始
- 每日 16:00 结算，使用结算价结算
- 持仓到交割日自动以结算价平仓，无手续费
- 股指期货平今手续费默认万分之六点九

---

## 十四、归因分析说明

### 收益分析指标

累计收益、对数轴累计收益、日内收益、滑点影响、年度/月度收益、月度热力图等。

### 风险指标

滚动 Beta（6/12个月）、滚动夏普（6个月）、前五大回撤区间。

### Brinson 归因

- **总超额收益** = 主动配置收益 + 标的选择收益 + 互动收益
- **主动配置收益**：行业择时能力
- **标的选择收益**：个股选择能力
- **互动收益**：配置与选择的交叉效应

### Fama-French 五因子模型

| 因子 | 符号 | 说明 |
|------|------|------|
| 市场因子 | RM | 市场组合超额收益 |
| 规模因子 | SMB | 小市值 - 大市值 |
| 估值因子 | HML | 高账面市值比 - 低账面市值比 |
| 盈利因子 | RMW | 高盈利 - 低盈利 |
| 投资因子 | CMA | 低投资率 - 高投资率 |

### Barra 十大风险因子

市值、非线性市值、杠杆、账面市值比、成长、动量、盈利能力、贝塔、残差波动率、流动性。

---

## 十五、常用策略示例

### 1. 均线策略

```python
import jqdata

def initialize(context):
    g.security = '000001.XSHE'
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

def handle_data(context, data):
    security = g.security
    close_data = attribute_history(security, 5, '1d', ['close'])
    MA5 = close_data['close'].mean()
    current_price = close_data['close'][-1]
    cash = context.portfolio.available_cash

    if current_price > 1.05 * MA5 and cash > 0:
        order_value(security, cash)
        log.info("Buying %s" % security)
    elif current_price < 0.95 * MA5 and context.portfolio.positions[security].closeable_amount > 0:
        order_target(security, 0)
        log.info("Selling %s" % security)
    record(stock_price=current_price)
```

### 2. 多股票持仓

```python
def initialize(context):
    g.stocks = ['000001.XSHE', '000002.XSHE', '000004.XSHE', '000005.XSHE']
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

def handle_data(context, data):
    for security in g.stocks:
        vwap = data[security].vwap(3)
        price = data[security].close
        cash = context.portfolio.available_cash

        if price < vwap * 0.995 and context.portfolio.positions[security].closeable_amount > 0:
            order(security, -100)
        elif price > vwap * 1.005 and cash > 0:
            order(security, 100)
```

### 3. 多股票追涨策略（分钟级）

```python
def initialize(context):
    set_option('use_real_price', True)
    g.daily_buy_count = 5
    g.stocks = set(get_industry_stocks('I64') + get_industry_stocks('I65'))
    run_daily(morning_sell_all, '09:30')

def morning_sell_all(context):
    for security in context.portfolio.positions:
        order_target(security, 0)

def before_trading_start(context):
    g.today_bought_stocks = set()
    g.last_df = history(1, '1d', 'close', g.stocks)

def handle_data(context, data):
    if context.current_dt.hour < 13:
        return
    if len(g.today_bought_stocks) >= g.daily_buy_count:
        return

    for security in (g.stocks - g.today_bought_stocks):
        price = data[security].close
        last_close = g.last_df[security][0]

        if (price / last_close > 1.095 and
            price / last_close < 1.099 and
            data[security].high_limit - last_close >= 1.0):

            need_count = g.daily_buy_count - len(g.today_bought_stocks)
            buy_cash = context.portfolio.available_cash / need_count
            order_value(security, buy_cash)
            g.today_bought_stocks.add(security)

            if len(g.today_bought_stocks) >= g.daily_buy_count:
                break
```

### 4. 万圣节效应策略

```python
def initialize(context):
    set_option('use_real_price', True)
    g.stocks = ['000001.XSHE', '600000.XSHG', '600036.XSHG', '600519.XSHG']

def handle_data(context, data):
    cash = context.portfolio.available_cash / len(g.stocks)
    hist = history(1, '1d', 'close', g.stocks)
    today = context.current_dt

    for security in g.stocks:
        current_price = hist[security][0]
        # 10月15日后买入
        if (today.month == 10 and today.day > 15 and
            cash > current_price and
            context.portfolio.positions[security].closeable_amount == 0):
            order_value(security, cash)
        # 5月15日后卖出
        elif (today.month == 5 and today.day > 15 and
              context.portfolio.positions[security].closeable_amount > 0):
            order_target(security, 0)
```

---

## 重要注意事项汇总

1. ⭐ **强烈建议开启动态复权**：`set_option('use_real_price', True)`，避免前复权的未来函数问题
2. **run_daily 优先于 handle_data**：建议使用定时运行函数
3. **模拟盘 g 对象持久化**：不可序列化变量以 `__` 开头，在 `process_initialize` 中初始化
4. **复权价格不要跨日期缓存**：真实价格模式下，不同日期 history 返回价格可能不同
5. **每日最大下单数**：10000 笔
6. **A股交易单位**：100 股整数倍，清仓不受限
7. **风险指标更新频率**：每天 17:00 左右更新，基于每日收盘收益
8. **订单不可跨日保存**：当天订单对象不要存到之后交易日使用
9. **财务数据避免未来函数**：回测中无法获取当天数据
10. **Tick 级必须用真实价格模式**：且需开通会员权限
