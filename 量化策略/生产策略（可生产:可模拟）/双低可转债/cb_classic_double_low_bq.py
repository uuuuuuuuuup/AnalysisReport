# -*- coding: utf-8 -*-
# ============================================================
# Engine 2: 可转债经典双低轮动 (Classic Double-Low, 月频)
# 平台: BigQuant BigTrader  |  市场: Market.CN_CBOND
# ============================================================
# ⚠️ 三引擎合并: 本脚本独立运行在 Market.CN_CBOND,
#   用 merge_three_engine.py 与 unified_etf_engine_bq.py 合并净值。
#   合并公式: 合并NAV = ETF_NAV + 0.35 × CB_NAV - 35,000
#
# 设计依据: 训练集 2019-01 ~ 2022-12 共48个月
#   经典双低: 年化 15.32%  夏普 1.05  最大回撤 -14.9%  月胜率 64.6%
#   BigQuant回测(2019-01~2024-09): 年化 15.02% 夏普 0.77 回撤 -31.4%
#   回撤恶化因2023-2024可转债首次违约(搜特/蓝盾), 实盘须按-31%做心理准备
#
# 逻辑:
#   1. 每月调仓(约22个交易日)
#   2. 双低打分: 0.5×z(close) + 0.5×z(cb_over_rate), 值越低越好
#   3. 选前20只, 等权
#   4. 缓冲带: 前25名中已在仓的保留, 补足到20只
#   5. 信用过滤: close<80且cb_over_rate>100 → 剔除
#   6. 池子过滤: 距maturity_date>12月 / 上市满30天
# ============================================================

from bigquant import bigtrader
import dai
import pandas as pd
import numpy as np

# ---- 冻结参数 ----
N_HOLD = 20
BUFFER_N = 25
W_PRICE = 0.50
W_PREMIUM = 0.50
MIN_LIST_DAYS = 30
MIN_TERM_MONTHS = 12
REBALANCE_DAYS = 22
CREDIT_PRICE_FLOOR = 80
CREDIT_PREMIUM_CEILING = 100


def initialize(context: bigtrader.IContext):
    """策略初始化。加载可转债全量数据, 设置费率。"""
    # 账户费率: 免印花税, 佣金万0.85 免5
    context.set_commission(bigtrader.PerOrder(
        buy_cost=0.000085,
        sell_cost=0.000085,
        min_cost=0,
        tax_ratio=0
    ))

    # 百分比滑点 0.05%
    context.set_slippage_value(slippage_type=2, slippage_value=0.0005)

    # 加载可转债全量数据
    # ⚠️ 2023年起 cn_cbond_bar1d_te.cb_over_rate 数据异常,
    #    改用 cn_cbond_bar1d(行情) + cn_cbond_analyze_metric(转股溢价率) 联表
    sql = """
    SELECT
        a.date, a.instrument, a.close,
        m.conversion_premium_rate AS premium_rate,
        b.maturity_date, b.list_date,
        b.name AS bond_name
    FROM cn_cbond_bar1d a
    INNER JOIN cn_cbond_basic_info b
        ON a.instrument = b.instrument
    INNER JOIN cn_cbond_analyze_metric m
        ON a.instrument = m.instrument AND a.date = m.date
    WHERE
        a.close > 0
        AND b.maturity_date IS NOT NULL
    ORDER BY a.date, a.instrument
    """
    # cn_cbond_bar1d 为分区表, 须指定 filters 分区范围(对齐回测起止日期)
    df = dai.query(sql, filters={"date": ["2019-01-01", "2026-07-29"]}).df()
    df['date'] = pd.to_datetime(df['date'])
    df['maturity_date'] = pd.to_datetime(df['maturity_date'])
    df['list_date'] = pd.to_datetime(df['list_date'])

    context.cb_data = df
    context.day_count = 0

    context.logger.info('可转债数据: %d 行, %d 标的, %s ~ %s'
                        % (len(df), df['instrument'].nunique(),
                           df['date'].min().strftime('%Y-%m-%d'),
                           df['date'].max().strftime('%Y-%m-%d')))


def handle_data(context: bigtrader.IContext, data: bigtrader.IBarData):
    """每日K线回调。调仓日执行选股+交易。"""
    context.day_count += 1
    if context.day_count % REBALANCE_DAYS != 0:
        return

    today = data.current_dt.strftime('%Y-%m-%d')
    today_dt = data.current_dt

    # ---- 当天数据 ----
    cur = context.cb_data[context.cb_data['date'] == today].copy()
    if len(cur) < BUFFER_N:
        context.logger.warning('%s: 仅%d条数据, 跳过' % (today, len(cur)))
        return

    # ---- 过滤 ----
    cur['days_listed'] = (today_dt - cur['list_date']).dt.days
    cur['months_to_mat'] = (cur['maturity_date'] - today_dt).dt.days / 30.0
    cur = cur[(cur['days_listed'] >= MIN_LIST_DAYS) &
              (cur['months_to_mat'] >= MIN_TERM_MONTHS)].copy()

    if len(cur) < BUFFER_N:
        context.logger.warning('%s: 过滤后仅%d只, 跳过' % (today, len(cur)))
        return

    # ---- 信用过滤 ----
    cur['risky'] = ((cur['close'] < CREDIT_PRICE_FLOOR) &
                    (cur['premium_rate'] > CREDIT_PREMIUM_CEILING))
    cur = cur[~cur['risky']]

    if len(cur) < BUFFER_N:
        context.logger.warning('%s: 过滤后仅%d只, 跳过' % (today, len(cur)))
        return

    # ---- 双低打分 (z-score, 值越低→得分越高) ----
    for col in ['close', 'premium_rate']:
        s = cur[col]
        mean, std = s.mean(), s.std()
        cur[col + '_z'] = -(s - mean) / std if std > 0 else 0.0

    cur['score'] = W_PRICE * cur['close_z'] + W_PREMIUM * cur['premium_rate_z']
    cur = cur.sort_values('score', ascending=False)

    # ---- 缓冲带 ----
    held = set(context.portfolio.positions.keys())
    top_pool = cur.head(BUFFER_N)['instrument'].tolist()

    keep = [s for s in top_pool if s in held]
    fresh = [s for s in top_pool if s not in held]
    selected = keep[:N_HOLD] + fresh[:max(0, N_HOLD - len(keep))]

    if len(selected) < N_HOLD * 0.7:
        context.logger.warning('%s: 缓冲带后仅%d只, 跳过' % (today, len(selected)))
        return

    # ---- 调仓 ----
    target_set = set(selected)

    # 卖出
    for s in list(held):
        if s not in target_set:
            context.order_target_percent(s, 0)

    # 等权买入
    w = 1.0 / len(selected)
    for s in selected:
        context.order_target_percent(s, w)

    # 日志
    context.logger.info('%s: 选%d只 | 资产%.0f | 持仓%d'
                        % (today, len(selected),
                           context.get_portfolio_value(),
                           len(context.portfolio.positions)))


# ============================================================
# 回测入口
# ============================================================
performance = bigtrader.run(
    market=bigtrader.Market.CN_CBOND,
    frequency=bigtrader.Frequency.DAILY,
    start_date='2019-01-01',
    end_date='2026-07-29',
    capital_base=100000,
    benchmark='000852.SH',
    initialize=initialize,
    handle_data=handle_data,
    order_price_field_buy='close',
    order_price_field_sell='close',
    volume_limit=0.1,
)
