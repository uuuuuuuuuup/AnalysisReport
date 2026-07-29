# -*- coding: utf-8 -*-
# ============================================================
# 统一 ETF 策略 — Engine 1 (双动量) + Engine 3 (红利持有)
# 平台: BigQuant BigTrader  |  市场: Market.CN_STOCK
# ============================================================
# 组合结构 (占总资产 100,000):
#   Engine 1 (35%): ETF 双动量 → 月频选2只, 各 17.5%
#   Engine 3 (30%): 515180 红利ETF → 静态持有, 季度再平衡
#   闲置 35% 现金 → 留给 Engine 2 (可转债, 单独 Market.CN_CBOND 运行)
#
# ⚠️ 三引擎合并方法:
#   本脚本跑 ETF 部分 (65% 资金), cb_classic_double_low_bq.py 跑可转债 (35% 资金)。
#   用 merge_three_engine.py 按权重合并两条净值曲线。
#
# 设计依据 (冻结规格):
#   Engine 1: 训练集 2015-10~2022-11, 年化 8.54%/夏普 0.64/回撤 -14.98%
#             测试集 2023-01~2026-07, 夏普 0.285，按协议判定通过
#   Engine 3: 因子验证 dp IC=0.018/vol IC≈0, 承认选股无 alpha, ETF 直投
# ============================================================

from bigquant import bigtrader
import dai
import pandas as pd
import numpy as np


# ============================================================
# 冻结参数 (与各引擎冻结规格完全一致, 禁止修改)
# ============================================================

# -- Engine 1: ETF 双动量 --
ETF_UNIVERSE = [
    '510300.SH',   # 沪深300
    '510500.SH',   # 中证500
    '159915.SZ',   # 创业板
    '510880.SH',   # 红利
    '513100.SH',   # 纳指
    '518880.SH',   # 黄金
]
ETF_SAFE      = '511010.SH'    # 国债ETF (避险仓)
ETF_K         = 6              # 动量回看月数
ETF_M         = 2              # 持仓数
ETF_ABS       = True           # 绝对动量过滤
W1            = 0.35           # Engine 1 占总资产权重

# -- Engine 3: 红利ETF 静态持有 --
DIV_ETF       = '515180.SH'    # 红利ETF易方达
W3            = 0.30           # Engine 3 占总资产权重
DIV_RB_MONTHS = {3, 6, 9, 12}  # 季度再平衡月份

# -- 通用 --
BENCHMARK = '000852.SH'        # 中证1000
RISK_FREE = 0.02               # 死亡条件现金基准

# -- 费率 (实际账户: 佣金万0.85免5, ETF免印花税) --
COMMISSION = bigtrader.PerOrder(
    buy_cost=0.000085, sell_cost=0.000085,
    min_cost=0, tax_ratio=0)

# -- 标的名称映射 (日志用) --
NAMES = {
    '510300.SH': '沪深300', '510500.SH': '中证500',
    '159915.SZ': '创业板',  '510880.SH': '红利',
    '513100.SH': '纳指',    '518880.SH': '黄金',
    '511010.SH': '国债',    '515180.SH': '红利ETF',
}


# ============================================================
# initialize
# ============================================================

def initialize(context: bigtrader.IContext):
    context.set_commission(COMMISSION)
    context.set_slippage_value(slippage_type=2, slippage_value=0.0005)

    # ---- 加载 ETF 历史日线 (cn_fund_bar1d, 不是 cn_stock_bar1d!) ----
    # ETF 在基金表里。filters 必须包含 date 范围 + instrument。
    all_etfs = ETF_UNIVERSE + [ETF_SAFE, DIV_ETF]
    df = dai.query(
        "SELECT date, instrument, close FROM cn_fund_bar1d ORDER BY date",
        filters={"date": ["2014-01-01", "2026-07-29"], "instrument": all_etfs}
    ).df()
    df['date'] = pd.to_datetime(df['date'])

    # 预计算: 按标的+年月分组, 保存月末收盘价便于快速查询
    df['ym'] = df['date'].dt.strftime('%Y-%m')
    month_end = df.groupby(['ym', 'instrument'])['close'].last().reset_index()
    # 为每个标的建立 month→close 映射
    etf_monthly = {}
    for s in all_etfs:
        me = month_end[month_end['instrument'] == s].set_index('ym')['close']
        etf_monthly[s] = me

    context.etf_monthly = etf_monthly
    context.etf_daily = df  # 用于取最新价格

    context.logger.info('ETF 数据加载: %d 标的, %d 行, %s ~ %s'
                        % (len(all_etfs), len(df),
                           df['date'].min().strftime('%Y-%m-%d'),
                           df['date'].max().strftime('%Y-%m-%d')))

    # ---- 状态 ----
    context.initialized   = False   # 首日建仓标志
    context.nav_peak      = 0.0
    context.monthly_nav   = []      # 月末总资产序列
    context.last_ym       = None    # 上次调仓的年月, 避免同月重复

    context.logger.info('统一 ETF 策略 (Engine 1+3) 初始化完成')


# ============================================================
# handle_data
# ============================================================

def handle_data(context: bigtrader.IContext, data: bigtrader.IBarData):
    today    = pd.Timestamp(data.current_dt.strftime('%Y-%m-%d'))
    today_ym = today.strftime('%Y-%m')

    # ============ 首日建仓 ============
    if not context.initialized:
        _first_day_buy(context, today)
        context.initialized = True
        context.last_ym = today_ym
        return

    # ============ 月末调仓 ============
    # 判断条件: 年月变化 (handle_data 在每个交易日触发, 跨月时即为新月首日)
    if today_ym == context.last_ym:
        return

    # 进入了新的月份 → 上个月刚结束, 执行月末调仓
    context.last_ym = today_ym
    _monthly_rebalance(context, today)
    _monthly_report(context)


def _first_day_buy(context, today):
    """首日: 建仓 Engine 3 的红利ETF (Engine 1 等到第一个月末选股)。"""
    total = context.get_portfolio_value()
    target_value = total * W3
    context.order_target_value(DIV_ETF, target_value)
    context.logger.info('首日建仓 %s: %.0f元 (%.0f%%)' % (NAMES[DIV_ETF], target_value, W3 * 100))

    context.nav_peak = total


# ============================================================
# Engine 1: ETF 动量选股
# ============================================================

def _select_etf_momentum(context, today):
    """
    6个月动量排名 → 选 top-M, 绝对动量<0 的切国债。
    返回 {instrument: weight_in_engine}, 或 None (数据不足跳过)。
    """
    today_ym = today.strftime('%Y-%m')
    current_prices = {}

    for s in ETF_UNIVERSE:
        d = context.etf_daily
        cur = d[(d['instrument'] == s) & (d['date'] <= today)]
        if len(cur) > 0:
            current_prices[s] = cur['close'].iloc[-1]

    mom = {}
    for s in ETF_UNIVERSE:
        if s not in current_prices:
            continue
        me = context.etf_monthly.get(s)
        if me is None:
            continue
        # 只用当月之前的月末数据
        me = me[me.index < today_ym].sort_index()
        if len(me) < ETF_K:
            continue
        base = me.iloc[-ETF_K]
        if pd.isna(base) or base <= 0:
            continue
        px = current_prices[s]
        if pd.isna(px) or px <= 0:
            continue
        mom[s] = px / base - 1.0

    if len(mom) < ETF_M:
        context.logger.warning('ETF 动量: 仅 %d 个可用 (需 %d), 跳过本月' % (len(mom), ETF_M))
        return None

    ranked = sorted(mom.items(), key=lambda kv: kv[1], reverse=True)
    picks = []
    for s, m in ranked[:ETF_M]:
        if ETF_ABS and m <= 0:
            picks.append(ETF_SAFE)
        else:
            picks.append(s)

    w = {}
    for s in picks:
        w[s] = w.get(s, 0.0) + 1.0 / ETF_M

    detail = ' | '.join('%s %+.1f%%' % (NAMES.get(s, s), mom.get(s, 0) * 100)
                        for s, _ in ranked[:ETF_M])
    context.logger.info('[Engine1] %d月动量: %s → %s'
                        % (ETF_K, detail,
                           ', '.join(NAMES.get(s, s) for s in picks)))
    return w


# ============================================================
# 月末调仓执行
# ============================================================

def _monthly_rebalance(context, today):
    """合并 Engine 1 选股 + Engine 3 再平衡, 统一调仓。"""
    total = context.get_portfolio_value()
    targets = {}  # {instrument: % of total portfolio}

    # ---- Engine 1: ETF 双动量 ----
    e1 = _select_etf_momentum(context, today)
    if e1 is not None:
        for s, w_in_engine in e1.items():
            targets[s] = w_in_engine * W1  # engine 内权重 → 总资产权重

    # ---- Engine 3: 红利ETF ----
    # 季度再平衡: 只在 3/6/9/12 月调整到目标权重, 其余月份保持不动
    if today.month in DIV_RB_MONTHS:
        targets[DIV_ETF] = W3
    else:
        pos = context.get_position(DIV_ETF)
        if pos is not None and pos.market_value > 0:
            targets[DIV_ETF] = pos.market_value / total

    if not targets:
        return

    # ---- 执行 ----
    _execute(context, targets, total, today)


def _execute(context, targets, total, today):
    """卖出不在目标中的持仓, 按目标权重买入。多轮放大消除 ETF 整数倍欠配。"""
    positions = context.get_positions()

    # 先卖
    for s in list(positions.keys()):
        if s not in targets:
            context.order_target_percent(s, 0)

    # 后买 (多轮放大)
    scale = 1.0
    for _ in range(6):
        for s, w in targets.items():
            if w > 0:
                context.order_target_percent(s, w * scale)
        idle = context.get_available_cash() / total
        if idle < 0.03:
            break
        scale += idle * 0.90

    # 日志
    positions = context.get_positions()
    holding = ' | '.join(
        '%s %.1f%%' % (NAMES.get(s, s), p.market_value / total * 100)
        for s, p in sorted(positions.items()) if p.market_value > 0
    )
    context.logger.info('调仓 | %s | 闲置 %.1f%% | 放大 %.2f'
                        % (holding, context.get_available_cash() / total * 100, scale))


# ============================================================
# 监控与死亡条件 (与各引擎独立版一致)
# ============================================================

def _monthly_report(context):
    """月末报告: 回撤 + 滚动绝对收益 vs 现金。全部为告警, 不做自动清仓。"""
    total = context.get_portfolio_value()
    context.nav_peak = max(context.nav_peak, total)
    dd = total / context.nav_peak - 1 if context.nav_peak else 0
    context.monthly_nav.append(total)

    # 死亡条件 1: 滚动绝对收益 < 现金
    for months, level in [(24, '告警'), (36, '建议停用')]:
        if len(context.monthly_nav) > months:
            ret = total / context.monthly_nav[-months - 1] - 1
            cash = (1 + RISK_FREE) ** (months / 12.0) - 1
            if ret < cash:
                context.logger.warning(
                    '[死亡-%s] 滚动%d月 %.2f%% < 现金 %.2f%%'
                    % (level, months, ret * 100, cash * 100))

    # 死亡条件 2: 回撤超 30%
    if dd < -0.30:
        context.logger.warning('[死亡-告警] 回撤 %.1f%% 超 30%%, 人工复核' % (dd * 100))

    context.logger.info('月报 | 资产 %.0f | 回撤 %.1f%% | 持仓 %d'
                        % (total, dd * 100, len(context.get_positions())))


# ============================================================
# 回测入口
# ============================================================

performance = bigtrader.run(
    market=bigtrader.Market.CN_STOCK,
    frequency=bigtrader.Frequency.DAILY,
    start_date='2015-10-01',
    end_date='2026-07-29',
    capital_base=100000,
    instruments=ETF_UNIVERSE + [ETF_SAFE, DIV_ETF],
    benchmark=BENCHMARK,
    initialize=initialize,
    handle_data=handle_data,
    order_price_field_buy='close',
    order_price_field_sell='close',
    volume_limit=0.1,
)
