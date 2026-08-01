# -*- coding: utf-8 -*-
# ============================================================
# 小盘股反转轮动策略 v2 (Small-Cap Reversal + Momentum Confirmation)
# 平台: BigQuant BigTrader  |  市场: Market.CN_STOCK
# ============================================================
# 逻辑:
#   1. 股票池: 剔除ST/停牌/次新(<60天)/北交所/科创板
#   2. 市值域: 流通市值排名后40%（兼顾小盘特征与流动性）
#   3. 反转因子: 过去20日收益率取负（跌得多→得分高）
#   4. 动量确认: 过去5日收益>-2%才买入（反弹初期允许微负）
#   5. 辅助因子: 低换手率(25%) + 低波动(25%)
#   6. 复合打分: z(反转)×0.5 + z(低换手)×0.25 + z(低波动)×0.25
#   7. 选前20只, 等权
#   8. 缓冲带: 前25名中已在仓的保留, 补足到20只
#   9. 市场择时: 全A 10日收益<-5%半仓, <-10%清仓（快速响应暴跌）
#  10. 个股止损: 持仓跌幅>20%强制卖出（小盘波动大，避免误杀）
#  11. 7日调仓(每7个交易日，折中周频/双周)
#
# 训练集(2019-01~2023-12): 年化28.59% 夏普1.22 回撤-30.53%
# ============================================================

from bigquant import bigtrader
import dai
import pandas as pd
import numpy as np

# ---- 冻结参数 ----
N_HOLD = 20
BUFFER_N = 25
REBALANCE_DAYS = 7       # 调仓频率: 7个交易日（反转信号衰减快，折中周频/双周）
REVERSAL_PERIOD = 20
MOMENTUM_PERIOD = 5
MOMENTUM_THRESHOLD = -0.02   # 动量确认阈值: 5日收益>-2%即可（反弹初期可能仍微负）
VOLATILITY_PERIOD = 20
TURNOVER_PERIOD = 20
MIN_LIST_DAYS = 60
CAP_PERCENTILE = 0.40    # 小市值域: 后40%（后30%流动性太差，后40%仍具小盘特征）
STOP_LOSS = -0.20        # 止损: -20%（小盘股波动大，-15%易误杀）

# 复合因子权重
W_REVERSAL = 0.50
W_TURNOVER = 0.25
W_VOLATILITY = 0.25

# 市场择时
MARKET_WEAK_THRESHOLD = -0.05
MARKET_CRASH_THRESHOLD = -0.10
MARKET_LOOKBACK = 10     # 回看10天（暴跌极快，20天来不及反应）

# 数据划分
TRAIN_START = '2019-01-01'
TRAIN_END   = '2023-12-31'   # 训练集5年（因子研究+参数确定，已用尽）
# ────────────────── 数据墙 ──────────────────
TEST_START  = '2024-01-01'   # 测试集2.5年（冻结后只看一次，禁止调参数）
TEST_END    = '2026-07-29'

# 当前：样本外验证 → 使用测试集
START_DATE = TEST_START
END_DATE   = TEST_END


def initialize(context: bigtrader.IContext):
    """策略初始化。加载全量数据, 设置费率。"""
    # 账户费率: 佣金万3 + 印花税千1(卖出)
    context.set_commission(bigtrader.PerOrder(
        buy_cost=0.0003,
        sell_cost=0.0013,
        min_cost=5,
        tax_ratio=0.001
    ))

    # 百分比滑点 0.1%
    context.set_slippage_value(slippage_type=2, slippage_value=0.001)

    # ---- 加载股票日线+估值+基本面 ----
    # 只需测试集+前置缓冲(60个交易日≈3个月), 避免内存溢出
    data_start = '2023-10-01'
    data_end = TEST_END
    print('加载数据 %s ~ %s (回测区间 %s ~ %s)...' % (data_start, data_end, START_DATE, END_DATE))

    sql = """
    SELECT
        p.date, p.instrument, p.close, p.volume,
        p.turn AS turnover_ratio,
        v.float_market_cap AS circulating_market_cap
    FROM cn_stock_bar1d p
    INNER JOIN cn_stock_valuation v
        ON p.date = v.date AND p.instrument = v.instrument
    INNER JOIN cn_stock_prefactors f
        ON p.date = f.date AND p.instrument = f.instrument
    WHERE
        p.close > 0
        AND p.volume > 0
        AND f.st_status = 0
        AND f.suspended = 0
        AND f.list_days >= %d
        AND f.list_sector NOT IN (3, 4)
    ORDER BY p.date, p.instrument
    """ % MIN_LIST_DAYS

    df = dai.query(sql, filters={"date": [data_start, data_end]}).df()
    df['date'] = pd.to_datetime(df['date'])

    context.logger.info('股票数据: %d 行, %d 标的, %s ~ %s'
                        % (len(df), df['instrument'].nunique(),
                           df['date'].min().strftime('%Y-%m-%d'),
                           df['date'].max().strftime('%Y-%m-%d')))

    # ---- 计算因子 ----
    context.logger.info('计算因子...')
    grouped = df.groupby('instrument')

    # 反转因子: 过去20日收益率取负
    df['reversal'] = grouped['close'].transform(
        lambda x: -(x / x.shift(REVERSAL_PERIOD) - 1)
    )

    # 动量确认: 过去5日收益率
    df['momentum'] = grouped['close'].transform(
        lambda x: x / x.shift(MOMENTUM_PERIOD) - 1
    )

    # 波动率因子: 取负=低波动得分高
    df['daily_ret'] = grouped['close'].transform(lambda x: x.pct_change())
    df['volatility'] = grouped['daily_ret'].transform(
        lambda x: -x.rolling(VOLATILITY_PERIOD, min_periods=10).std()
    )

    # 换手率因子: 取负=低换手得分高
    df['turnover'] = grouped['turnover_ratio'].transform(
        lambda x: -x.rolling(TURNOVER_PERIOD, min_periods=10).mean()
    )

    # 市值排名（每日截面）
    df['cap_rank'] = df.groupby('date')['circulating_market_cap'].transform(
        lambda x: x.rank(pct=True, na_option='keep')
    )

    # 预建日期索引（字符串key，加速截面查询）
    df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
    context.stock_data = df
    context.day_count = 0

    # ---- 计算市场基准（全A等权日收益）----
    context.logger.info('计算市场基准...')
    daily_market_ret = df.groupby('date')['daily_ret'].mean()
    context.market_cumret = (1 + daily_market_ret).cumprod()
    # 市场日期也用字符串索引
    context.market_cumret.index = context.market_cumret.index.strftime('%Y-%m-%d')

    context.logger.info('初始化完成')


def handle_data(context: bigtrader.IContext, data: bigtrader.IBarData):
    """每日K线回调。执行止损+择时+调仓。"""
    context.day_count += 1
    today = data.current_dt.strftime('%Y-%m-%d')
    today_dt = data.current_dt

    # ---- 个股止损检查 ----
    held = set(context.portfolio.positions.keys())
    for inst in list(held):
        pos = context.portfolio.positions[inst]
        if pos.amount == 0:
            continue
        # 持仓盈亏比例
        cost = pos.cost_basis if hasattr(pos, 'cost_basis') else pos.avg_cost
        if cost > 0:
            cur_price = data.current(inst, 'close')
            if cur_price > 0 and (cur_price / cost - 1) < STOP_LOSS:
                context.order_target_percent(inst, 0)
                context.logger.info('%s: 止损 %s (成本%.2f 现价%.2f 亏损%.1f%%)'
                                    % (today, inst, cost, cur_price,
                                       (cur_price / cost - 1) * 100))

    # ---- 市场择时判断 ----
    market_regime = 'normal'
    if today in context.market_cumret.index:
        bm_loc = context.market_cumret.index.get_loc(today)
        if bm_loc >= MARKET_LOOKBACK:
            bm_ret = (context.market_cumret.iloc[bm_loc] /
                      context.market_cumret.iloc[bm_loc - MARKET_LOOKBACK] - 1)
            if bm_ret < MARKET_CRASH_THRESHOLD:
                market_regime = 'crash'
            elif bm_ret < MARKET_WEAK_THRESHOLD:
                market_regime = 'weak'

    # crash时强制清仓
    if market_regime == 'crash':
        for inst in list(context.portfolio.positions.keys()):
            if context.portfolio.positions[inst].amount > 0:
                context.order_target_percent(inst, 0)
        context.logger.warning('%s: 市场崩盘, 全部清仓' % today)
        return

    # ---- 调仓日判断 ----
    if context.day_count % REBALANCE_DAYS != 0:
        return

    # ---- 当天截面数据 ----
    cur = context.stock_data[context.stock_data['date_str'] == today].copy()
    if len(cur) < N_HOLD:
        context.logger.warning('%s: 截面数据仅%d只, 跳过' % (today, len(cur)))
        return

    # ---- 小市值域 ----
    cur = cur[cur['cap_rank'] <= CAP_PERCENTILE]

    # ---- 动量确认: 只保留已在反弹或企稳的股票 ----
    cur = cur[cur['momentum'] > MOMENTUM_THRESHOLD]

    if len(cur) < N_HOLD:
        context.logger.info('%s: 动量确认后仅%d只(需%d只), 保持持仓' % (today, len(cur), N_HOLD))
        return

    # ---- 去除因子缺失 ----
    cur = cur.dropna(subset=['reversal', 'volatility', 'turnover'])

    if len(cur) < N_HOLD:
        return

    # ---- Z-score 标准化 ----
    for col in ['reversal', 'volatility', 'turnover']:
        s = cur[col]
        mean, std = s.mean(), s.std()
        cur[col + '_z'] = (s - mean) / std if std > 0 else 0.0

    # ---- 复合打分 ----
    cur['score'] = (W_REVERSAL * cur['reversal_z'] +
                   W_TURNOVER * cur['turnover_z'] +
                   W_VOLATILITY * cur['volatility_z'])

    cur = cur.sort_values('score', ascending=False)

    # ---- 缓冲带选股 ----
    held = set(context.portfolio.positions.keys())
    top_pool = cur.head(BUFFER_N)['instrument'].tolist()

    keep = [s for s in top_pool if s in held]
    fresh = [s for s in top_pool if s not in held]

    # 市场择时调整持仓数
    if market_regime == 'weak':
        target_n = int(N_HOLD * 0.5)
    else:
        target_n = N_HOLD

    if target_n < 5:
        for inst in list(held):
            if context.portfolio.positions[inst].amount > 0:
                context.order_target_percent(inst, 0)
        return

    selected = keep[:target_n] + fresh[:max(0, target_n - len(keep))]

    if len(selected) < target_n * 0.7:
        context.logger.warning('%s: 缓冲带后仅%d只, 跳过' % (today, len(selected)))
        return

    # ---- 调仓 ----
    target_set = set(selected)

    # 卖出
    for inst in list(held):
        if inst not in target_set:
            context.order_target_percent(inst, 0)

    # 等权买入
    w = 1.0 / len(selected)
    for inst in selected:
        context.order_target_percent(inst, w)

    # 日志
    regime_flag = ' [弱市半仓]' if market_regime == 'weak' else ''
    context.logger.info('%s: 选%d只 | 资产%.0f | 持仓%d%s'
                        % (today, len(selected),
                           context.get_portfolio_value(),
                           len(context.portfolio.positions), regime_flag))


# ============================================================
# 回测入口
# ============================================================
performance = bigtrader.run(
    market=bigtrader.Market.CN_STOCK,
    frequency=bigtrader.Frequency.DAILY,
    start_date=TEST_START,
    end_date=TEST_END,
    capital_base=100000,
    benchmark='000852.SH',
    initialize=initialize,
    handle_data=handle_data,
    order_price_field_buy='close',
    order_price_field_sell='close',
    volume_limit=0.1,
)
