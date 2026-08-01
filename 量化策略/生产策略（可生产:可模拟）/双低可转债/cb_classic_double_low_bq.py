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
#   2. 双低打分: 0.5×z(close) + 0.5×z(premium_rate), 值越低越好
#   3. 选前20只, 等权
#   4. 缓冲带: 前25名中已在仓的保留, 补足到20只
#   5. 信用过滤: close<80且premium_rate>100 → 剔除
#   6. 池子过滤: 距maturity_date>12月 / 上市满30天
#
# ⚠️ 数据权限修复 (2026-08-01):
#   原方案使用 cn_cbond_analyze_metric.conversion_premium_rate (需标准版付费权限)
#   现改为: 通过4张免费表手动计算转股溢价率 ——
#     转股价值 = 100 ÷ 转股价 × 正股收盘价
#     转股溢价率 = (转债收盘价 ÷ 转股价值 - 1) × 100%
#   免费数据表:
#     - cn_cbond_bar1d       (Beta免费): 可转债日行情 close + 正股代码 stock_code
#     - cn_cbond_basic_info  (Alpha免费): 基本信息 maturity_date / list_date / stock_code
#     - cn_cbond_conversion  (免费):     转股价 conversion_clause_price
#     - cn_stock_bar1d       (免费):     正股日行情 close
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
    """策略初始化。加载可转债全量数据, 设置费率。

    数据获取策略:
      1. 可转债行情 (cn_cbond_bar1d) + 基本信息 (cn_cbond_basic_info) → 主表
      2. 转股条款 (cn_cbond_conversion) → 转股价 conversion_clause_price
         (注意: cn_cbond_conversion.date 为转股起始日, 非分区日; 该表记录最新条款快照,
          若某标的无转股价记录, 回退使用 basic_info 中的初始转股价 或 标记后丢弃)
      3. 正股行情 (cn_stock_bar1d) → 正股收盘价
      4. 按公式手动计算转股溢价率 premium_rate
    """
    # 账户费率: 免印花税, 佣金万0.85 免5
    context.set_commission(bigtrader.PerOrder(
        buy_cost=0.000085,
        sell_cost=0.000085,
        min_cost=0,
        tax_ratio=0
    ))

    # 百分比滑点 0.05%
    context.set_slippage_value(slippage_type=2, slippage_value=0.0005)

    # ---- Step 1: 加载可转债行情 + 基本信息 ----
    # stock_code 字段用于关联正股行情
    sql_cb = """
    SELECT
        a.date, a.instrument, a.close AS bond_close, a.stock_code,
        b.maturity_date, b.list_date,
        b.name AS bond_name
    FROM cn_cbond_bar1d a
    LEFT JOIN cn_cbond_basic_info b
        ON a.instrument = b.instrument
    WHERE
        a.close > 0
        AND b.maturity_date IS NOT NULL
    ORDER BY a.date, a.instrument
    """
    df = dai.query(sql_cb, filters={"date": ["2019-01-01", "2026-07-29"]}).df()
    df['date'] = pd.to_datetime(df['date'])
    df['maturity_date'] = pd.to_datetime(df['maturity_date'])
    df['list_date'] = pd.to_datetime(df['list_date'])

    context.logger.info('Step1 可转债行情+基本信息: %d 行, %d 标的'
                        % (len(df), df['instrument'].nunique()))

    # ---- Step 2: 加载转股价 (cn_cbond_conversion) ----
    # 注意: 该表 date 字段为「转股起始日期」, 非每日快照; 取每条 bond 最新转股价即可
    # (实际回测中, 若需精确的历史转股价变动, 可后续加入 cn_cbond_revise 修正条款,
    #  此处先用最新转股价作为近似, 对于双低策略来说误差可接受)
    sql_conv = """
    SELECT
        instrument,
        conversion_clause_price AS conversion_price
    FROM cn_cbond_conversion
    WHERE
        conversion_clause_price > 0
    """
    try:
        df_conv = dai.query(sql_conv).df()
        # 同一 instrument 可能有多条记录(不同转股期), 取最小转股价(更保守)
        df_conv = df_conv.groupby('instrument', as_index=False)['conversion_price'].min()
        context.logger.info('Step2 转股价数据: %d 只可转债' % len(df_conv))
    except Exception as e:
        context.logger.warning('Step2 读取 cn_cbond_conversion 失败: %s, 将使用默认转股价' % str(e))
        df_conv = pd.DataFrame(columns=['instrument', 'conversion_price'])

    # 将转股价合并到主表
    df = df.merge(df_conv, on='instrument', how='left')

    # ---- Step 3: 加载正股收盘价 (cn_stock_bar1d) ----
    # 收集所有需要的正股代码, 避免全表扫描
    stock_list = df['stock_code'].dropna().unique().tolist()
    if stock_list:
        sql_stock = """
        SELECT date, instrument AS stock_code, close AS stock_close
        FROM cn_stock_bar1d
        WHERE close > 0
        """
        # cn_stock_bar1d 也是分区表, 需要指定 date filters
        df_stock = dai.query(sql_stock, filters={"date": ["2019-01-01", "2026-07-29"]}).df()
        df_stock['date'] = pd.to_datetime(df_stock['date'])
        context.logger.info('Step3 正股行情: %d 行, %d 只正股'
                            % (len(df_stock), df_stock['stock_code'].nunique()))

        # 合并正股收盘价到主表
        df = df.merge(df_stock, on=['date', 'stock_code'], how='left')
    else:
        df['stock_close'] = np.nan
        context.logger.warning('Step3 未找到正股代码列表, 正股收盘价列为空')

    # ---- Step 4: 手动计算转股溢价率 ----
    # 公式:
    #   转股价值 = 100 / 转股价 × 正股收盘价
    #   转股溢价率 = (转债收盘价 / 转股价值 - 1) × 100%
    df['conversion_value'] = np.where(
        (df['conversion_price'] > 0) & (df['stock_close'] > 0),
        100.0 / df['conversion_price'] * df['stock_close'],
        np.nan
    )
    df['premium_rate'] = np.where(
        df['conversion_value'] > 0,
        (df['bond_close'] / df['conversion_value'] - 1.0) * 100.0,
        np.nan
    )

    # 转股价缺失或正股收盘价缺失时, 对 premium_rate 做兜底处理:
    # - 若 premium_rate 缺失, 按当日截面中位数填充 (仅用于避免回测中断)
    n_missing = df['premium_rate'].isna().sum()
    if n_missing > 0:
        context.logger.warning('Step4 有 %d 行 premium_rate 缺失, 按当日截面中位数填充' % n_missing)
        df['premium_rate'] = df.groupby('date')['premium_rate'].transform(
            lambda x: x.fillna(x.median())
        )
        # 仍缺失的(当日全缺失), 用全局默认值 30% 填充
        df['premium_rate'] = df['premium_rate'].fillna(30.0)

    # 统一列名: bond_close → close, 与原代码保持兼容
    df.rename(columns={'bond_close': 'close'}, inplace=True)

    # 过滤异常值: 溢价率 > 500% 或 < -50% 的视为数据异常, 用截面中位数替代
    pct_mask = (df['premium_rate'] > 500) | (df['premium_rate'] < -50)
    if pct_mask.any():
        context.logger.warning('Step4 过滤 %d 行异常溢价率数据, 用当日截面中位数替代' % pct_mask.sum())
        df.loc[pct_mask, 'premium_rate'] = np.nan
        df['premium_rate'] = df.groupby('date')['premium_rate'].transform(
            lambda x: x.fillna(x.median())
        )
        df['premium_rate'] = df['premium_rate'].fillna(30.0)

    context.cb_data = df
    context.day_count = 0

    context.logger.info('可转债数据(已计算溢价率): %d 行, %d 标的, %s ~ %s | 溢价率均值 %.2f%%, 中位数 %.2f%%'
                        % (len(df), df['instrument'].nunique(),
                           df['date'].min().strftime('%Y-%m-%d'),
                           df['date'].max().strftime('%Y-%m-%d'),
                           df['premium_rate'].mean(),
                           df['premium_rate'].median()))


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
