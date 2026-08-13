# -*- coding: utf-8 -*-
"""
================================================================================
高频微观结构因子库 - 多因子组合策略（BigQuant BigTrader 版本）
================================================================================

策略说明：
    基于分钟级 K 线数据，将头部私募"捂着不公开"的高频微观结构因子做近似还原，
    搭建可扩展的因子库 + 多因子组合策略框架。

平台        : BigQuant BigTrader
标的池      : 中证 1000 (000852.SH)
数据频率    : 回测日频触发，因子计算用前一交易日分钟K线（240根/日）
调仓频率    : 日频
持仓方式    : 多头 Top20 等权
滑点/佣金   : 万1 / 万2.5

因子库 (6 个，全部来自公开但小众的卖方研报，且分钟数据可还原)：
    1. price_peak        价峰因子          来源: 开源证券《市场微观结构研究系列(33)》
    2. vol_entropy       成交量分布熵值    来源: 方正证券《"暗流涌动"因子》
    3. avg_amt_skew      分钟单笔金额偏度  来源: 开源证券《市场微观结构研究系列(15)》
    4. big_order_push    大单推动涨幅      来源: 海通证券《选股因子系列研究(69)》
    5. tail_vol_ratio    尾盘成交占比      来源: 海通证券《选股因子系列研究(69)》
    6. modified_reversal 改进反转          来源: 海通证券《选股因子系列研究(69)》

扩展方式：
    新增因子只需：
      1) 继承 Factor 基类
      2) 实现 compute() 方法
      3) 用 @register_factor 装饰器注册
      4) 在 CONFIG['factor_names'] 中启用

性能提示：
    每个调仓日会查询 ~1000 只股票 × 240 根分钟K线 ≈ 24万行数据。
    如回测过慢，可将 rebalance_freq 改为 5（周频）减少查询次数。

风险提示：
    - 分钟级 K 线无法还原真正的 Tick / 订单簿数据，本策略为降级近似版本
    - 历史回测不代表未来收益，实盘需考虑滑点扩大、停牌、流动性等风险
================================================================================
"""

from collections import OrderedDict
from bigquant import bigtrader
import dai
import pandas as pd
import numpy as np


# ============================================================
# 配置层
# ============================================================
CONFIG = {
    # 基础设置
    'benchmark':           '000852.SH',       # 基准指数：中证1000
    'universe_index':      '000852.SH',       # 标的池：中证1000成分股
    'rebalance_freq':      1,                  # 调仓频率（交易日）
    'top_n':               20,                 # 多头持仓数

    # 交易成本
    'slippage':            0.0001,             # 滑点：万1
    'commission_buy':      0.00025,            # 佣金：万2.5
    'commission_sell':     0.00025,            # 佣金：万2.5
    'min_cost':            5.0,                # 最小佣金
    'tax_ratio':           0.0005,             # 印花税：千0.5（卖出）

    # 因子启用清单
    'factor_names': [
        'price_peak',         # 价峰因子
        'vol_entropy',        # 成交量分布熵值
        'avg_amt_skew',       # 分钟单笔金额偏度
        'big_order_push',     # 大单推动涨幅
        'tail_vol_ratio',     # 尾盘成交占比
        'modified_reversal',  # 改进反转
    ],

    # 因子方向：1 = 正向（值越大越买），-1 = 负向（值越小越买）
    'factor_directions': {
        'price_peak':         1,   # 价峰越多，未来表现越好
        'vol_entropy':       -1,   # 熵值越小（成交越集中），未来越好
        'avg_amt_skew':      -1,   # 单笔金额右偏越强（大单主导），未来越好
        'big_order_push':    -1,   # 大单推动涨幅越大，未来反转越强
        'tail_vol_ratio':    -1,   # 尾盘成交占比越高，未来越差
        'modified_reversal': -1,   # 日内反转效应：剔除开盘后反转更稳定
    },

    # 因子权重：None=等权，或传入 dict
    'factor_weights': None,

    # 分钟K线参数
    'minute_count': 240,    # 一天240根1分钟K线
    'tail_minutes': 30,     # 尾盘定义为最后30分钟（14:30之后）
    'opening_skip': 30,     # 改进反转剔除开盘30分钟
}


# ============================================================
# 因子基类与注册表
# ============================================================
class Factor:
    """
    因子基类：所有因子继承此类，实现 compute() 方法。
    扩展框架时只需继承 + 装饰器注册即可，无需改动主流程。
    """
    name = 'base'

    def compute(self, context, securities, minute_data):
        """
        计算因子值。

        参数
        ----
        context    : BigTrader 上下文
        securities : list, 股票代码列表
        minute_data: dict, key=股票代码, value=分钟K线 DataFrame
                     DataFrame 字段: open/high/low/close/volume/amount

        返回
        ----
        pd.Series, index=股票代码, value=因子值（NaN 会被自动剔除）
        """
        raise NotImplementedError


# 因子注册表：因子名 -> 因子实例
FACTOR_REGISTRY = OrderedDict()


def register_factor(cls):
    """因子注册装饰器：被装饰的类会被实例化并加入注册表"""
    FACTOR_REGISTRY[cls.name] = cls()
    return cls


# ============================================================
# 因子 1：价峰因子
# 来源：开源证券《高频价格跳跃的峰、岭、谷信息》(2026)
# 逻辑：以分钟振幅代理价格跳跃。统计"无缺口+非情绪高涨"的孤立跳跃点数。
#       此类跳跃代表信息驱动但未被情绪放大，预示未来正向 alpha。
# 实证：价峰分钟数因子多空年化 16.4%，IR 2.1
# ============================================================
@register_factor
class PricePeakFactor(Factor):
    name = 'price_peak'

    def compute(self, context, securities, minute_data):
        values = {}
        for sec in securities:
            df = minute_data.get(sec)
            if df is None or len(df) < 30:
                continue

            high, low, close = df['high'], df['low'], df['close']
            # 用前一根收盘价归一化振幅
            prev_close = close.shift(1).fillna(close.iloc[0])
            amplitude = (high - low) / prev_close.replace(0, np.nan)
            amplitude = amplitude.dropna()
            if len(amplitude) < 10:
                continue

            std = amplitude.std()
            if std == 0 or np.isnan(std):
                continue

            # 阈值：1 倍标准差
            is_jump = amplitude > std

            # 价峰定义：跳跃点 + 前后非跳跃（非情绪高涨）+ 无价格缺口
            peak_count = 0
            for i in range(1, len(df) - 1):
                if is_jump.iloc[i] and not is_jump.iloc[i + 1] and not is_jump.iloc[i - 1]:
                    # 无缺口：下一根最低不高于当前最高，下一根最高不低于当前最低
                    has_gap = (low.iloc[i + 1] > high.iloc[i]) or (high.iloc[i + 1] < low.iloc[i])
                    if not has_gap:
                        peak_count += 1

            values[sec] = peak_count / len(df)

        return pd.Series(values)


# ============================================================
# 因子 2：成交量分布熵值
# 来源：方正证券《"暗流涌动"因子》(2025)
# 逻辑：用香农熵刻画个股日内相对成交量分布。
#       熵值越小 → 成交越集中 → 越可能由信息/主力驱动 → 未来表现越好。
# 实证：Rank IC -5.72%, ICIR -3.54, 多空年化 23.14%, IR 2.74
# ============================================================
@register_factor
class VolumeEntropyFactor(Factor):
    name = 'vol_entropy'

    def compute(self, context, securities, minute_data):
        # 第一步：聚合全市场每分钟总成交量，用于计算"相对成交量"
        market_vol_by_minute = {}
        for sec, df in minute_data.items():
            if df is None:
                continue
            vol_arr = df['volume'].values
            for i, v in enumerate(vol_arr):
                market_vol_by_minute[i] = market_vol_by_minute.get(i, 0) + v

        # 第二步：逐股计算相对成交量的香农熵
        n_bins = 48  # 240 / 5 = 48 个 5 分钟区间
        values = {}
        for sec in securities:
            df = minute_data.get(sec)
            if df is None or len(df) < 240:
                continue

            vol = df['volume'].values
            market = np.array([market_vol_by_minute.get(i, 1) for i in range(len(vol))])
            rel_vol = vol / np.where(market == 0, 1, market)

            bin_size = len(rel_vol) // n_bins
            if bin_size == 0:
                continue
            bin_sums = np.array([rel_vol[i * bin_size:(i + 1) * bin_size].sum()
                                 for i in range(n_bins)])
            total = bin_sums.sum()
            if total <= 0:
                continue

            p = bin_sums / total
            p = p[p > 0]
            entropy = -np.sum(p * np.log(p))
            values[sec] = entropy

        return pd.Series(values)


# ============================================================
# 因子 3：分钟单笔金额偏度
# 来源：开源证券《分钟单笔金额序列中的主力行为刻画》(2022)
# 逻辑：分钟成交额 / 分钟成交量 = 分钟内单笔平均金额（近似逐笔）
#       分布右偏越强（少数大单主导）→ 主力关注 → 未来表现越好。
# 实证：Rank IC -0.072, ICIR 3.57, 多头年化 24.69%, IR 3.59
# ============================================================
@register_factor
class AvgAmtSkewFactor(Factor):
    name = 'avg_amt_skew'

    def compute(self, context, securities, minute_data):
        values = {}
        for sec in securities:
            df = minute_data.get(sec)
            if df is None or len(df) < 30:
                continue

            vol = df['volume'].replace(0, np.nan)
            amount = df['amount']
            # 分钟内单笔平均成交金额近似
            avg_amt = (amount / vol).dropna()
            if len(avg_amt) < 10:
                continue

            skew = avg_amt.skew()
            if np.isnan(skew):
                continue
            values[sec] = skew

        return pd.Series(values)


# ============================================================
# 因子 4：大单推动涨幅
# 来源：海通证券《选股因子系列研究(69) - 高频因子的现实与幻想》
# 逻辑：将分钟按成交额排序，超过均值的 1.5 倍视为"大单分钟"，
#       累加这些分钟的收益率 = 大单推动涨幅。
#       大单推动涨幅越大 → 越短期超买 → 未来反转越强（负向因子）。
# 实证：Rank IC 3.71%, ICIR 3.79%
# ============================================================
@register_factor
class BigOrderPushFactor(Factor):
    name = 'big_order_push'

    def compute(self, context, securities, minute_data):
        values = {}
        for sec in securities:
            df = minute_data.get(sec)
            if df is None or len(df) < 30:
                continue

            amount = df['amount']
            close = df['close']
            rets = close.pct_change().fillna(0)

            threshold = amount.mean() * 1.5
            big_mask = amount > threshold
            if big_mask.sum() == 0:
                continue

            big_rets = rets[big_mask].sum()
            values[sec] = big_rets

        return pd.Series(values)


# ============================================================
# 因子 5：尾盘成交占比
# 来源：海通证券《选股因子系列研究(69)》
# 逻辑：尾盘（14:30 之后）成交额占全天比例。
#       尾盘成交过旺 → 投机性强 / 散户主导 → 未来表现差（负向因子）。
# 实证：Rank IC 4.86%, ICIR 3.59%（海通研报中表现最优的分钟因子）
# ============================================================
@register_factor
class TailVolumeRatioFactor(Factor):
    name = 'tail_vol_ratio'

    def compute(self, context, securities, minute_data):
        tail_n = CONFIG['tail_minutes']
        values = {}
        for sec in securities:
            df = minute_data.get(sec)
            if df is None or len(df) < tail_n:
                continue

            total_amount = df['amount'].sum()
            if total_amount <= 0:
                continue
            tail_amount = df['amount'].iloc[-tail_n:].sum()
            values[sec] = tail_amount / total_amount

        return pd.Series(values)


# ============================================================
# 因子 6：改进反转
# 来源：海通证券《选股因子系列研究(69)》
# 逻辑：剔除隔夜跳空 + 开盘 30 分钟情绪段后的日内反转。
#       A 股日内反转效应显著，剔除噪声段后 IC 更稳定。
# 实证：Rank IC 4.33%, ICIR 3.74%
# ============================================================
@register_factor
class ModifiedReversalFactor(Factor):
    name = 'modified_reversal'

    def compute(self, context, securities, minute_data):
        skip = CONFIG['opening_skip']
        values = {}
        for sec in securities:
            df = minute_data.get(sec)
            if df is None or len(df) < skip + 10:
                continue

            intraday = df.iloc[skip:]
            open_price = intraday['close'].iloc[0]
            close_price = intraday['close'].iloc[-1]
            if open_price == 0 or np.isnan(open_price):
                continue
            ret = (close_price - open_price) / open_price
            values[sec] = ret

        return pd.Series(values)


# ============================================================
# 多因子合成器
# ============================================================
def synthesize_factors(factor_values_dict, directions, weights=None):
    """
    截面标准化 + 方向调整 + 加权合成。

    参数
    ----
    factor_values_dict : {因子名: pd.Series}
    directions         : {因子名: ±1}
    weights            : {因子名: float} 或 None（等权）

    返回
    ----
    pd.Series, 综合得分（越大越值得买）
    """
    standardized = {}
    for name, series in factor_values_dict.items():
        s = series.dropna()
        if len(s) < 10:
            continue

        # 1) 中位数法去极值（MAD）
        med = s.median()
        mad = (s - med).abs().median()
        if mad > 0:
            s = s.clip(lower=med - 3 * 1.4826 * mad,
                       upper=med + 3 * 1.4826 * mad)

        # 2) Z-Score 标准化
        std = s.std()
        if std > 0:
            s = (s - s.mean()) / std

        # 3) 方向调整
        s = s * directions.get(name, 1)
        standardized[name] = s

    if not standardized:
        return pd.Series()

    df = pd.DataFrame(standardized)

    # 4) 加权合成
    if weights is None:
        score = df.mean(axis=1)
    else:
        for name in df.columns:
            df[name] = df[name] * weights.get(name, 0)
        score = df.sum(axis=1)

    return score


# ============================================================
# BigTrader 策略入口
# ============================================================
def initialize(context: bigtrader.IContext):
    """策略初始化"""
    # 费率：股票佣金万2.5 + 印花税千0.5（卖出）
    context.set_commission(bigtrader.PerOrder(
        buy_cost=CONFIG['commission_buy'],
        sell_cost=CONFIG['commission_sell'],
        min_cost=CONFIG['min_cost'],
        tax_ratio=CONFIG['tax_ratio'],
    ))

    # 滑点：万1（百分比滑点）
    context.set_slippage_value(slippage_type=2, slippage_value=CONFIG['slippage'])

    # ---- 预加载中证1000成分股历史 ----
    # 表 cn_stock_index_component 字段:
    #   instrument  = 指数代码 (如 '000852.SH')
    #   member_code = 成分股代码
    #   date        = 日期
    # 建立 date(YYYY-MM-DD) -> [member_code] 的映射，用于每个交易日动态获取标的池
    index_code = CONFIG['universe_index']
    start = '2020-01-01'  # 成分股历史预加载起始日
    end = '2026-12-31'
    try:
        comp_df = dai.query(
            "SELECT date, member_code FROM cn_stock_index_component "
            "WHERE instrument = '%s' ORDER BY date" % index_code,
            filters={"date": [start, end]},
        ).df()
        comp_df['date'] = pd.to_datetime(comp_df['date'])
        # 先把 date 转成字符串列，再 groupby，key 直接就是字符串
        comp_df['date_str'] = comp_df['date'].dt.strftime('%Y-%m-%d')
        context.index_components = {
            d: g['member_code'].tolist()
            for d, g in comp_df.groupby('date_str')
        }
        context.logger.info('中证1000成分股加载: %d 个交易日, 样本 %s ~ %s' % (
            len(context.index_components),
            comp_df['date'].min().strftime('%Y-%m-%d'),
            comp_df['date'].max().strftime('%Y-%m-%d'),
        ))
    except Exception as e:
        context.logger.error('成分股加载失败: %s' % str(e))
        context.index_components = {}

    # ---- 预加载日K线（用于停牌/ST过滤）----
    try:
        daily_df = dai.query(
            "SELECT date, instrument, close, volume, name "
            "FROM cn_stock_bar1d ORDER BY date",
            filters={"date": [start, end]},
        ).df()
        daily_df['date'] = pd.to_datetime(daily_df['date'])
        context.daily_df = daily_df
        context.logger.info('日K线加载: %d 行, %s ~ %s' % (
            len(daily_df),
            daily_df['date'].min().strftime('%Y-%m-%d'),
            daily_df['date'].max().strftime('%Y-%m-%d'),
        ))
    except Exception as e:
        context.logger.error('日K线加载失败: %s' % str(e))
        context.daily_df = pd.DataFrame()

    # ---- 状态 ----
    context.last_rebalance_date = None   # 上次调仓日期字符串
    context.nav_peak = 0.0               # 净值峰值（用于回撤监控）
    context.day_count = 0                # 交易日计数器（用于调仓频率控制）

    context.logger.info('=' * 60)
    context.logger.info('高频微观结构多因子组合策略 (BigQuant版) 启动')
    context.logger.info('标的池=%s | 调仓=%d日 | TopN=%d | 滑点=%.4f | 佣金=%.4f' % (
        CONFIG['universe_index'], CONFIG['rebalance_freq'],
        CONFIG['top_n'], CONFIG['slippage'], CONFIG['commission_buy']))
    context.logger.info('启用因子: %s' % ' | '.join(CONFIG['factor_names']))
    context.logger.info('=' * 60)


def handle_data(context: bigtrader.IContext, data: bigtrader.IBarData):
    """日频回调：每个交易日触发一次"""
    today = pd.Timestamp(data.current_dt.strftime('%Y-%m-%d'))
    total = context.get_portfolio_value()
    context.nav_peak = max(context.nav_peak, total)

    # ---- 调仓频率控制：每 rebalance_freq 个交易日调仓一次 ----
    context.day_count += 1
    if context.day_count % CONFIG['rebalance_freq'] != 0:
        return

    context.last_rebalance_date = today.strftime('%Y-%m-%d')

    # ---- 1) 获取标的池 ----
    securities = _get_universe(context, today)
    if len(securities) < 50:
        context.logger.warning('调仓日 %s | 标的池不足 50 只 (%d)，跳过' % (
            today.strftime('%Y-%m-%d'), len(securities)))
        return

    # ---- 2) 获取前一交易日分钟数据 ----
    minute_data = _fetch_minute_data(context, securities, today)
    if len(minute_data) < 50:
        context.logger.warning('分钟数据样本不足 (%d)，跳过本次调仓' % len(minute_data))
        return

    context.logger.info('-' * 50)
    context.logger.info('调仓日 %s | 标的池 %d 只 | 分钟数据 %d 只' % (
        today.strftime('%Y-%m-%d'), len(securities), len(minute_data)))

    # ---- 3) 计算各因子 ----
    factor_values = {}
    for fname in CONFIG['factor_names']:
        if fname not in FACTOR_REGISTRY:
            context.logger.warning('因子 %s 未注册，跳过' % fname)
            continue
        try:
            values = FACTOR_REGISTRY[fname].compute(context, securities, minute_data)
            if len(values) > 0:
                factor_values[fname] = values
                context.logger.info('因子 %s: %d 个值 | 均值=%.4f | 标准差=%.4f' % (
                    fname, len(values), values.mean(), values.std()))
        except Exception as e:
            context.logger.error('因子 %s 计算失败: %s' % (fname, str(e)))

    if len(factor_values) < 2:
        context.logger.warning('有效因子数 < 2，跳过本次调仓')
        return

    # ---- 4) 多因子合成 ----
    score = synthesize_factors(factor_values,
                               CONFIG['factor_directions'],
                               CONFIG['factor_weights'])
    if len(score) < 50:
        context.logger.warning('合成得分样本不足: %d' % len(score))
        return

    # ---- 5) 选股 TopN ----
    top_n = CONFIG['top_n']
    target_stocks = score.nlargest(top_n).index.tolist()
    context.logger.info('目标持仓 %d 只 | 前5得分: %s' % (
        len(target_stocks),
        {s: round(score[s], 3) for s in target_stocks[:5]}
    ))

    # ---- 6) 调仓：先卖后买 ----
    _rebalance(context, target_stocks, total)

    # ---- 7) 绩效记录 ----
    _record_performance(context, today, score, factor_values)


# ============================================================
# 标的池获取
# ============================================================
def _get_universe(context, today):
    """
    获取中证1000成分股，过滤停牌和 ST。
    用预加载的成分股映射 + 日K线数据做过滤。
    """
    today_str = today.strftime('%Y-%m-%d')

    # 找到 <= today 的最近一个成分股日期
    securities = []
    if context.index_components:
        # 成分股日期可能不是每天更新，找最近的
        available_dates = sorted([d for d in context.index_components.keys() if d <= today_str],
                                 reverse=True)
        if available_dates:
            securities = context.index_components[available_dates[0]]

    if not securities:
        return []

    # 用日K线过滤停牌（volume == 0）和 ST（name 含 ST）
    if context.daily_df is not None and len(context.daily_df) > 0:
        daily = context.daily_df
        # 找 <= today 的最近交易日
        prev_daily = daily[daily['date'] <= today]
        if len(prev_daily) > 0:
            prev_date = prev_daily['date'].max()
            day_data = prev_daily[prev_daily['date'] == prev_date]
            day_data = day_data[day_data['instrument'].isin(securities)]

            # 过滤停牌：volume == 0
            traded = day_data[day_data['volume'] > 0]['instrument'].tolist()
            # 过滤 ST：name 含 'ST'（如果 name 字段可用）
            if 'name' in day_data.columns:
                st_filter = day_data[day_data['name'].astype(str).str.contains('ST', na=False)]
                st_set = set(st_filter['instrument'].tolist())
                traded = [s for s in traded if s not in st_set]

            securities = traded

    return securities


# ============================================================
# 分钟数据获取
# ============================================================
def _fetch_minute_data(context, securities, today):
    """
    查询前一交易日的全天分钟K线。
    用 dai 查 cn_stock_bar1m 表，按日期和标的过滤。
    """
    # 找前一交易日
    if context.daily_df is None or len(context.daily_df) == 0:
        return {}

    daily = context.daily_df
    prev_daily = daily[daily['date'] < today]
    if len(prev_daily) == 0:
        return {}
    prev_date = prev_daily['date'].max()

    # 查询前一交易日的分钟K线
    try:
        minute_df = dai.query(
            "SELECT date, instrument, open, high, low, close, volume, amount "
            "FROM cn_stock_bar1m ORDER BY date",
            filters={
                "date": [prev_date.strftime('%Y-%m-%d'),
                         prev_date.strftime('%Y-%m-%d')],
                "instrument": securities,
            },
        ).df()
    except Exception as e:
        context.logger.error('分钟数据查询失败: %s' % str(e))
        return {}

    if len(minute_df) == 0:
        return {}

    # 转成 dict[instrument] -> DataFrame
    minute_data = {}
    for sec, grp in minute_df.groupby('instrument'):
        df = grp.sort_values('date').reset_index(drop=True)
        if len(df) >= 30:
            minute_data[sec] = df

    return minute_data


# ============================================================
# 调仓执行
# ============================================================
def _rebalance(context, target_stocks, total):
    """
    调仓：先卖后买，等权分配。
    用 order_target_percent 下单，多轮放大消除整数倍欠配。
    """
    target_set = set(target_stocks)

    # ---- 先卖：不在目标中的持仓清零 ----
    positions = context.get_positions()
    for sec in list(positions.keys()):
        if sec not in target_set:
            context.order_target_percent(sec, 0)

    # ---- 后买：多轮放大消除整数倍欠配 ----
    if len(target_stocks) == 0:
        return

    weight = 1.0 / len(target_stocks)
    scale = 1.0
    for _ in range(4):
        for sec in target_stocks:
            context.order_target_percent(sec, weight * scale)
        idle = context.get_available_cash() / total if total else 0
        if idle < 0.015:
            break
        scale += idle * 0.95

    # ---- 日志 ----
    positions = context.get_positions()
    holding = ' | '.join(
        '%s %.1f%%' % (s, p.market_value / total * 100)
        for s, p in sorted(positions.items()) if p.market_value > 0
    )
    context.logger.info('调仓完成 | %s | 闲置现金 %.1f%% | 放大系数 %.3f' % (
        holding,
        context.get_available_cash() / total * 100,
        scale,
    ))


# ============================================================
# 绩效记录与监控
# ============================================================
def _record_performance(context, today, score, factor_values):
    """记录每日绩效与持仓信息"""
    total = context.get_portfolio_value()
    cash = context.get_available_cash()
    drawdown = total / context.nav_peak - 1 if context.nav_peak > 0 else 0
    positions = context.get_positions()
    n_positions = len([p for p in positions.values() if p.market_value > 0])

    context.logger.info('账户净值: %.2f | 现金: %.2f | 回撤: %.1f%% | 持仓数: %d' % (
        total, cash, drawdown * 100, n_positions))

    # 死亡条件告警：回撤超过 30%
    if drawdown < -0.30:
        context.logger.warning(
            '[死亡条件-告警] 回撤 %.1f%% 已超 -30%%, 风险特征异常, 请人工复核' % (drawdown * 100))


# ============================================================
# 预查所有历史成分股 + 构造 basic_info 绕过权限表
# ============================================================
# 背景：bigtrader.run 内部会自动查 cn_stock_index_info 表获取合约基本信息，
#       但该表需旗舰版权限。解决方案：用 user_data={'basic_info': df} 传入
#       自定义合约信息，绕过内部查询。
#       basic_info 用免费的 cn_stock_instruments 表构造（字段: instrument, name）。
#
# 表字段说明:
#   cn_stock_index_component: instrument=指数代码, member_code=成分股代码, date
#   cn_stock_instruments:     instrument=股票代码, name=简称, date
#                             (查询时必须用 filters 指定 date 分区范围)
# ------------------------------------------------------------
_all_instruments = [CONFIG['benchmark']]
_basic_info_df = pd.DataFrame(columns=['instrument', 'name'])

try:
    # 1) 查所有历史成分股（用于 instruments 列表）
    #    字段: instrument=指数代码, member_code=成分股代码
    _comp_all = dai.query(
        "SELECT DISTINCT member_code FROM cn_stock_index_component "
        "WHERE instrument = '%s'" % CONFIG['universe_index'],
        filters={"date": ['2020-01-01', '2026-12-31']},
    ).df()
    if len(_comp_all) > 0:
        _all_instruments = list(set(_comp_all['member_code'].tolist()))
    print('成分股预查: %d 只' % len(_all_instruments))
except Exception as _e:
    print('成分股预查失败，退化用基准指数: %s' % str(_e))

try:
    # 2) 查股票名称信息（用于 basic_info，替代 cn_stock_index_info）
    #    cn_stock_instruments 必须用 filters 指定 date 分区范围
    _inst_df = dai.query(
        "SELECT instrument, name FROM cn_stock_instruments",
        filters={"date": ['2020-01-01', '2026-12-31'],
                 "instrument": _all_instruments},
    ).df()
    # 去重：每只股票取最新一条
    if len(_inst_df) > 0:
        _basic_info_df = _inst_df.drop_duplicates(subset=['instrument'], keep='last').reset_index(drop=True)
    print('basic_info 构造: %d 条' % len(_basic_info_df))
except Exception as _e:
    print('basic_info 构造失败（cn_stock_instruments 查询异常）: %s' % str(_e))
    # 退化：用空 name 构造 basic_info，至少能让 bigtrader.run 跳过内部查询
    _basic_info_df = pd.DataFrame({
        'instrument': _all_instruments,
        'name': [''] * len(_all_instruments),
    })


# ============================================================
# 回测入口
# ============================================================
performance = bigtrader.run(
    market=bigtrader.Market.CN_STOCK,
    frequency=bigtrader.Frequency.DAILY,
    start_date='2021-01-01',
    end_date='2026-07-29',
    capital_base=1000000,
    instruments=_all_instruments,    # 所有历史成分股，确保下单不被拒
    benchmark=CONFIG['benchmark'],
    initialize=initialize,
    handle_data=handle_data,
    order_price_field_buy='close',   # 按收盘价撮合
    order_price_field_sell='close',
    volume_limit=0.1,                # 单笔最大成交比例 10%
    # 关键：用 user_data 传入 basic_info，绕过 bigtrader 内部对
    #       cn_stock_index_info 旗舰版权限表的查询
    user_data={'basic_info': _basic_info_df},
)
