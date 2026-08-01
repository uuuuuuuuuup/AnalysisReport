# -*- coding: utf-8 -*-
# ============================================================
# 事件驱动策略: 业绩超预期 + 增持回购 (BigTrader回测)
# 平台: BigQuant BigTrader  |  市场: Market.CN_STOCK
# ============================================================
# 设计依据:
#   1. PEAD(盈余后动量漂移): 业绩超预期后股价短期反应不足,
#      后续有显著正向漂移, A股效应强于美股(散户主导市场)
#   2. 内部人交易信号: 大股东增持/公司回购是强看涨信号,
#      A股统计显示增持后30日超额收益3-5%
#   3. 两类事件相关性低, 可叠加
#
# 逻辑:
#   1. 每N个交易日扫描事件窗口(过去30天)
#   2. 业绩超预期: 净利润预告同比>30% 且 超上年同期
#   3. 增持/回购: 过去30天有增持/回购公告 且 金额占比>0.5%
#   4. 事件打分 + 小市值偏好 + 流动性过滤
#   5. 选Top15, 等权, 持有15天后事件衰减→调仓
#   6. 缓冲带: Top20中已在仓的保留
#
# 数据表字段:
#   astock_forecast: security_code, ann_date, profit_yoy_min/max, forecast_type
#   astock_financial_brief: security_code, ann_date, net_profit_yoy
#   astock_holder_trade: security_code, ann_date, trade_direction, trade_amount
#   astock_repurchase: security_code, ann_date, complete_amount
# ============================================================

from bigquant import bigtrader
import dai
import pandas as pd
import numpy as np

# ---- 冻结参数 ----
N_HOLD = 15               # 持仓数
BUFFER_N = 20              # 缓冲带候选数
REBALANCE_DAYS = 15        # 持有15个交易日(事件效应约15-20天)
EVENT_WINDOW = 30          # 事件窗口: 扫描过去30天的事件
MIN_LIST_DAYS = 60         # 次新过滤

# 业绩超预期阈值
EARNINGS_YOY_MIN = 0.30    # 净利润同比最低30%
EARNINGS_SCORE_WEIGHT = 0.60

# 增持回购阈值
BUYBACK_RATIO_MIN = 0.005  # 增持金额占市值>0.5%
BUYBACK_SCORE_WEIGHT = 0.40

# 市值过滤: 剔除超大盘(前10%)和微盘(后10%)
CAP_LOWER = 0.10
CAP_UPPER = 0.90

# 日均成交额过滤: >500万(散户可执行)
MIN_AVG_AMOUNT = 5_000_000


def _map_code_to_inst(df, code_col='security_code', code_map=None):
    """将 security_code 映射为 instrument 格式 (600519 → 600519.SH)"""
    if code_map is None:
        return df
    df['instrument'] = df[code_col].map(code_map)
    return df[df['instrument'].notna()].copy()


def initialize(context: bigtrader.IContext):
    """策略初始化。加载事件数据+行情数据。"""
    # 费率: 佣金万2.5 + 印花税千1(卖出)
    context.set_commission(bigtrader.PerOrder(
        buy_cost=0.00025,
        sell_cost=0.00025,
        min_cost=5,
        tax_ratio=0.001
    ))

    # 百分比滑点 0.1%
    context.set_slippage_value(slippage_type=2, slippage_value=0.001)

    data_start = '2023-10-01'
    data_end = '2026-07-29'

    # ---- 1. 加载行情+市值数据 ----
    print('加载行情+市值数据 %s ~ %s ...' % (data_start, data_end))
    sql_price = """
    SELECT
        a.date, a.instrument, a.close, a.volume,
        a.amount, a.turn AS turnover_ratio,
        v.float_market_cap AS circulating_market_cap
    FROM cn_stock_bar1d a
    INNER JOIN cn_stock_valuation v
        ON a.instrument = v.instrument AND a.date = v.date
    INNER JOIN cn_stock_prefactors p
        ON a.instrument = p.instrument AND a.date = p.date
    WHERE
        a.close > 0
        AND p.suspended = 0
        AND p.st_status = 0
        AND p.list_days >= %d
        AND p.list_sector NOT IN (3, 4)
    ORDER BY a.date, a.instrument
    """ % MIN_LIST_DAYS

    df = dai.query(sql_price, filters={"date": [data_start, data_end]}).df()
    df['date'] = pd.to_datetime(df['date'])
    df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
    context.stock_data = df
    print('行情: %d 行, %d 标的' % (len(df), df['instrument'].nunique()))

    # 构建 security_code → instrument 映射
    inst_set = set(df['instrument'].unique())
    code_map = {}
    for inst in inst_set:
        code = inst.split('.')[0]
        code_map[code] = inst
    context.code_map = code_map

    # ---- 2. 加载业绩预告数据 ----
    print('加载业绩预告数据...')
    try:
        sql_forecast = """
        SELECT security_code, ann_date,
               profit_yoy_min, profit_yoy_max, forecast_type
        FROM astock_forecast
        WHERE profit_yoy_min IS NOT NULL
        ORDER BY ann_date, security_code
        """
        df_forecast = dai.query(sql_forecast, filters={"ann_date": [data_start, data_end]}).df()
        df_forecast['ann_date'] = pd.to_datetime(df_forecast['ann_date'])
        df_forecast = _map_code_to_inst(df_forecast, code_map=code_map)
        context.forecast_data = df_forecast
        print('业绩预告: %d 条 (映射后)' % len(df_forecast))
    except Exception as e:
        print('⚠️ 业绩预告表查询失败: %s' % str(e)[:80])
        context.forecast_data = pd.DataFrame()

    # ---- 3. 加载业绩快报数据 ----
    print('加载业绩快报数据...')
    try:
        sql_brief = """
        SELECT security_code, ann_date, net_profit_yoy
        FROM astock_financial_brief
        WHERE net_profit_yoy IS NOT NULL
        ORDER BY ann_date, security_code
        """
        df_brief = dai.query(sql_brief, filters={"ann_date": [data_start, data_end]}).df()
        df_brief['ann_date'] = pd.to_datetime(df_brief['ann_date'])
        df_brief = _map_code_to_inst(df_brief, code_map=code_map)
        context.brief_data = df_brief
        print('业绩快报: %d 条 (映射后)' % len(df_brief))
    except Exception as e:
        print('⚠️ 业绩快报表查询失败: %s' % str(e)[:80])
        context.brief_data = pd.DataFrame()

    # ---- 4. 加载增持数据 ----
    print('加载增持数据...')
    try:
        sql_holder = """
        SELECT security_code, ann_date,
               trade_direction, trade_amount, trade_volume
        FROM astock_holder_trade
        WHERE trade_direction = 'BUY'
          AND trade_volume > 0
        ORDER BY ann_date, security_code
        """
        df_holder = dai.query(sql_holder, filters={"ann_date": [data_start, data_end]}).df()
        df_holder['ann_date'] = pd.to_datetime(df_holder['ann_date'])
        df_holder = _map_code_to_inst(df_holder, code_map=code_map)
        context.holder_data = df_holder
        print('增持: %d 条 (映射后)' % len(df_holder))
    except Exception as e:
        print('⚠️ 增持表查询失败: %s' % str(e)[:80])
        context.holder_data = pd.DataFrame()

    # ---- 5. 加载回购数据 ----
    print('加载回购数据...')
    try:
        sql_repo = """
        SELECT security_code, ann_date, complete_amount
        FROM astock_repurchase
        WHERE complete_amount IS NOT NULL
          AND complete_amount > 0
        ORDER BY ann_date, security_code
        """
        df_repo = dai.query(sql_repo, filters={"ann_date": [data_start, data_end]}).df()
        df_repo['ann_date'] = pd.to_datetime(df_repo['ann_date'])
        df_repo = _map_code_to_inst(df_repo, code_map=code_map)
        context.repo_data = df_repo
        print('回购: %d 条 (映射后)' % len(df_repo))
    except Exception as e:
        print('⚠️ 回购表查询失败: %s' % str(e)[:80])
        context.repo_data = pd.DataFrame()

    context.day_count = 0
    context.logger.info('事件驱动策略初始化完成')


def handle_data(context: bigtrader.IContext, data: bigtrader.IBarData):
    """每日K线回调。调仓日执行事件扫描+选股+交易。"""
    context.day_count += 1
    if context.day_count % REBALANCE_DAYS != 0:
        return

    today = data.current_dt.strftime('%Y-%m-%d')
    today_dt = data.current_dt

    # ---- 当天行情截面 ----
    cur = context.stock_data[context.stock_data['date_str'] == today].copy()
    if len(cur) < BUFFER_N:
        return

    # ---- 市值过滤: 去掉超大和微盘 ----
    cap_q = cur['circulating_market_cap'].quantile([CAP_LOWER, CAP_UPPER])
    cur = cur[(cur['circulating_market_cap'] >= cap_q[CAP_LOWER]) &
              (cur['circulating_market_cap'] <= cap_q[CAP_UPPER])].copy()
    if len(cur) < BUFFER_N:
        return

    # ---- 流动性过滤: 近5日均成交额 > 500万 ----
    recent = context.stock_data[
        (context.stock_data['date_str'] <= today) &
        (context.stock_data['date_str'] >= (today_dt - pd.Timedelta(days=10)).strftime('%Y-%m-%d'))
    ]
    avg_amount = recent.groupby('instrument')['amount'].mean()
    cur = cur[cur['instrument'].map(avg_amount) > MIN_AVG_AMOUNT].copy()
    if len(cur) < N_HOLD:
        context.logger.warning('%s: 流动性过滤后仅%d只' % (today, len(cur)))
        return

    instruments_set = set(cur['instrument'].tolist())

    # ============================================================
    # 事件1: 业绩超预期
    # ============================================================
    earnings_score = pd.Series(0.0, index=cur['instrument'])

    window_start = (today_dt - pd.Timedelta(days=EVENT_WINDOW)).strftime('%Y-%m-%d')

    # 业绩预告 (字段: profit_yoy_min, ann_date)
    if len(context.forecast_data) > 0:
        fc = context.forecast_data[
            (context.forecast_data['ann_date'] >= window_start) &
            (context.forecast_data['ann_date'] <= today_dt)
        ]
        fc = fc[fc['profit_yoy_min'] > EARNINGS_YOY_MIN]
        if len(fc) > 0:
            best_fc = fc.groupby('instrument')['profit_yoy_min'].max()
            for inst, yoy in best_fc.items():
                if inst in instruments_set:
                    earnings_score[inst] = min(yoy / 1.0, 1.0)

    # 业绩快报(补充) (字段: net_profit_yoy, ann_date)
    if len(context.brief_data) > 0:
        bf = context.brief_data[
            (context.brief_data['ann_date'] >= window_start) &
            (context.brief_data['ann_date'] <= today_dt)
        ]
        bf = bf[bf['net_profit_yoy'] > EARNINGS_YOY_MIN]
        if len(bf) > 0:
            best_bf = bf.groupby('instrument')['net_profit_yoy'].max()
            for inst, yoy in best_bf.items():
                if inst in instruments_set:
                    score = min(yoy / 1.0, 1.0)
                    earnings_score[inst] = max(earnings_score.get(inst, 0), score)

    # ============================================================
    # 事件2: 增持/回购
    # ============================================================
    buyback_score = pd.Series(0.0, index=cur['instrument'])

    # 增持 (字段: trade_amount, ann_date, trade_direction='BUY')
    if len(context.holder_data) > 0:
        hd = context.holder_data[
            (context.holder_data['ann_date'] >= window_start) &
            (context.holder_data['ann_date'] <= today_dt)
        ]
        if len(hd) > 0:
            hd_sum = hd.groupby('instrument')['trade_amount'].sum()
            cap_map = cur.set_index('instrument')['circulating_market_cap']
            for inst, amt in hd_sum.items():
                if inst in instruments_set and inst in cap_map.index:
                    cap_val = cap_map[inst]
                    if cap_val > 0:
                        ratio = amt / cap_val
                        if ratio > BUYBACK_RATIO_MIN:
                            buyback_score[inst] = min(ratio / 0.02, 1.0)

    # 回购(补充) (字段: complete_amount, ann_date)
    if len(context.repo_data) > 0:
        rp = context.repo_data[
            (context.repo_data['ann_date'] >= window_start) &
            (context.repo_data['ann_date'] <= today_dt)
        ]
        if len(rp) > 0:
            rp_sum = rp.groupby('instrument')['complete_amount'].sum()
            cap_map = cur.set_index('instrument')['circulating_market_cap']
            for inst, amt in rp_sum.items():
                if inst in instruments_set and inst in cap_map.index:
                    cap_val = cap_map[inst]
                    if cap_val > 0:
                        ratio = amt / cap_val
                        if ratio > BUYBACK_RATIO_MIN:
                            score = min(ratio / 0.02, 1.0)
                            buyback_score[inst] = max(buyback_score.get(inst, 0), score)

    # ============================================================
    # 复合打分
    # ============================================================
    has_signal = (earnings_score > 0) | (buyback_score > 0)
    if has_signal.sum() < N_HOLD * 0.5:
        context.logger.warning('%s: 事件信号不足(%d只), 跳过' % (today, has_signal.sum()))
        return

    candidates = cur[cur['instrument'].isin(has_signal[has_signal].index)].copy()

    candidates['earnings_s'] = candidates['instrument'].map(earnings_score)
    candidates['buyback_s'] = candidates['instrument'].map(buyback_score)
    candidates['score'] = (EARNINGS_SCORE_WEIGHT * candidates['earnings_s'] +
                           BUYBACK_SCORE_WEIGHT * candidates['buyback_s'])

    # 叠加小市值偏好(30%权重)
    cap_rank = candidates['circulating_market_cap'].rank(pct=True)
    candidates['cap_pref'] = 1.0 - cap_rank
    candidates['score'] = 0.70 * candidates['score'] + 0.30 * candidates['cap_pref']

    candidates = candidates.sort_values('score', ascending=False)

    # ---- 缓冲带 ----
    held = set(context.portfolio.positions.keys())
    top_pool = candidates.head(BUFFER_N)['instrument'].tolist()

    keep = [s for s in top_pool if s in held]
    fresh = [s for s in top_pool if s not in held]
    selected = keep[:N_HOLD] + fresh[:max(0, N_HOLD - len(keep))]

    if len(selected) < N_HOLD * 0.5:
        context.logger.warning('%s: 缓冲带后仅%d只, 跳过' % (today, len(selected)))
        return

    # ---- 调仓 ----
    target_set = set(selected)

    for s in list(held):
        if s not in target_set:
            context.order_target_percent(s, 0)

    w = 1.0 / len(selected)
    for s in selected:
        context.order_target_percent(s, w)

    n_earn = (candidates.head(N_HOLD)['earnings_s'] > 0).sum()
    n_buy = (candidates.head(N_HOLD)['buyback_s'] > 0).sum()
    context.logger.info('%s: 选%d只 | 业绩%d 增持%d | 资产%.0f'
                        % (today, len(selected), n_earn, n_buy,
                           context.get_portfolio_value()))


# ============================================================
# 回测入口
# ============================================================
performance = bigtrader.run(
    market=bigtrader.Market.CN_STOCK,
    frequency=bigtrader.Frequency.DAILY,
    start_date='2024-01-01',
    end_date='2026-07-29',
    capital_base=100000,
    benchmark='000852.SH',
    initialize=initialize,
    handle_data=handle_data,
    order_price_field_buy='close',
    order_price_field_sell='close',
    volume_limit=0.1,
)
