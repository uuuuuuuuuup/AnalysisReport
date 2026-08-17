# -*- coding: utf-8 -*-
"""
================================================================================
高频微观结构因子库 - 多因子组合策略（聚宽 JoinQuant 版本）
================================================================================

策略说明：
    基于分钟级 K 线数据，将头部私募"捂着不公开"的高频微观结构因子做近似还原，
    搭建可扩展的因子库 + 多因子组合策略框架。

标的池      : 中证 1000 (000852.XSHG)
数据频率    : 分钟级（240 根 1 分钟 K 线 / 日）
调仓频率    : 日频
持仓方式    : 多头 Top20 等权
滑点/佣金   : 万1 / 万2.5

因子库 (6 个，全部来自公开但小众的卖方研报，且聚宽分钟数据可还原)：
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

风险提示：
    - 分钟级 K 线无法还原真正的 Tick / 订单簿数据，本策略为降级近似版本
    - 历史回测不代表未来收益，实盘需考虑滑点扩大、停牌、流动性等风险
================================================================================
"""

from collections import OrderedDict
import numpy as np
import pandas as pd


# ============================================================
# 配置层
# ============================================================
CONFIG = {
    # 基础设置
    'benchmark':           '000852.XSHG',   # 基准指数：中证1000
    'universe_index':      '000852.XSHG',   # 标的池：中证1000成分股
    'rebalance_freq':      1,                # 调仓频率（交易日）
    'top_n':               20,               # 多头持仓数

    # 交易成本
    'slippage':            0.0001,           # 滑点：万1
    'commission':          0.00025,          # 佣金：万2.5（买卖各收）

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
        context    : 聚宽上下文
        securities : list, 股票代码列表
        minute_data: dict, key=股票代码, value=分钟K线 DataFrame
                     DataFrame 字段: open/high/low/close/volume/money

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
# 逻辑：分钟成交额 / 分钟成交量 = 分钟内单笔平均金额（聚宽拿不到真逐笔，做近似）
#       分布右偏越强（少数大单主导）→ 主力关注 → 未来表现越好。
#       原研报因子方向为负（Rank IC -0.072）
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
            money = df['money']
            # 分钟内单笔平均成交金额近似
            avg_amt = (money / vol).dropna()
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

            money = df['money']
            close = df['close']
            rets = close.pct_change().fillna(0)

            threshold = money.mean() * 1.5
            big_mask = money > threshold
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

            total_money = df['money'].sum()
            if total_money <= 0:
                continue
            tail_money = df['money'].iloc[-tail_n:].sum()
            values[sec] = tail_money / total_money

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
# 聚宽策略入口
# ============================================================
def initialize(context):
    """策略初始化"""
    set_benchmark(CONFIG['benchmark'])
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # 滑点与佣金
    set_slippage(FixedSlippage(CONFIG['slippage']))
    set_commission(PerTrade(buy_cost=CONFIG['commission'],
                            sell_cost=CONFIG['commission'],
                            min_cost=5))

    log.info('=' * 60)
    log.info('高频微观结构多因子组合策略 启动')
    log.info('标的池=%s | 调仓=%d日 | TopN=%d | 滑点=%.4f | 佣金=%.4f' % (
        CONFIG['universe_index'], CONFIG['rebalance_freq'],
        CONFIG['top_n'], CONFIG['slippage'], CONFIG['commission']))
    log.info('启用因子: %s' % ' | '.join(CONFIG['factor_names']))
    log.info('=' * 60)

    # 每个交易日 09:30 调仓
    run_daily(rebalance, time='09:30')


def get_universe(context):
    """获取标的池：中证1000成分，过滤 ST / 停牌"""
    stocks = get_index_stocks(CONFIG['universe_index'], context.previous_date)
    current_data = get_current_data()
    stocks = [s for s in stocks
              if not current_data[s].paused
              and not current_data[s].is_st
              and 'ST' not in current_data[s].name
              and '*ST' not in current_data[s].name]
    return stocks


def fetch_minute_data(context, securities):
    """
    批量获取昨日全天分钟K线。
    优先用 get_price 批量拉取（性能更优），失败时降级为逐只 get_bars。
    """
    end_dt = context.previous_date
    count = CONFIG['minute_count']
    minute_data = {}

    try:
        # 批量获取：panel=False 返回 long format DataFrame
        panel = get_price(securities,
                          end_date=end_dt,
                          count=count,
                          frequency='1m',
                          fields=['open', 'high', 'low', 'close', 'volume', 'money'],
                          panel=False)
        for sec in securities:
            df = panel[panel['code'] == sec].copy().reset_index(drop=True)
            if len(df) >= 30:
                minute_data[sec] = df
    except Exception as e:
        log.warn('批量获取分钟数据失败，降级为逐只获取: %s' % str(e))
        for sec in securities:
            try:
                df = get_bars(sec, count=count, unit='1m', end_dt=end_dt,
                              fields=['open', 'high', 'low', 'close', 'volume', 'money'],
                              df=True)
                if len(df) >= 30:
                    minute_data[sec] = df
            except:
                continue

    return minute_data


def rebalance(context):
    """每日调仓主流程"""
    # 1) 标的池
    securities = get_universe(context)
    log.info('-' * 50)
    log.info('调仓日 %s | 标的池 %d 只' % (str(context.current_dt.date()), len(securities)))
    if len(securities) < 50:
        log.warn('标的池不足 50 只，跳过本次调仓')
        return

    # 2) 拉取分钟数据
    minute_data = fetch_minute_data(context, securities)
    log.info('获取分钟数据成功: %d 只' % len(minute_data))
    if len(minute_data) < 50:
        log.warn('分钟数据样本不足，跳过本次调仓')
        return

    # 3) 计算各因子
    factor_values = {}
    for fname in CONFIG['factor_names']:
        if fname not in FACTOR_REGISTRY:
            log.warn('因子 %s 未注册，跳过' % fname)
            continue
        try:
            values = FACTOR_REGISTRY[fname].compute(context, securities, minute_data)
            if len(values) > 0:
                factor_values[fname] = values
                log.info('因子 %s 计算: %d 个值 | 均值=%.4f | 标准差=%.4f' % (
                    fname, len(values), values.mean(), values.std()))
        except Exception as e:
            log.error('因子 %s 计算失败: %s' % (fname, str(e)))

    if len(factor_values) < 2:
        log.warn('有效因子数 < 2，跳过本次调仓')
        return

    # 4) 多因子合成
    score = synthesize_factors(factor_values,
                               CONFIG['factor_directions'],
                               CONFIG['factor_weights'])
    if len(score) < 50:
        log.warn('合成得分样本不足: %d' % len(score))
        return

    # 5) 选股 TopN
    top_n = CONFIG['top_n']
    target_stocks = score.nlargest(top_n).index.tolist()
    log.info('目标持仓 %d 只 | 前5得分: %s' % (
        len(target_stocks),
        {s: round(score[s], 3) for s in target_stocks[:5]}
    ))

    # 6) 调仓：先卖后买
    current_positions = set(context.portfolio.positions.keys())
    for sec in current_positions - set(target_stocks):
        order_target_value(sec, 0)

    if len(target_stocks) > 0:
        weight = 1.0 / len(target_stocks)
        for sec in target_stocks:
            order_target_value(sec, context.portfolio.total_value * weight)

    # 7) 绩效记录
    record_performance(context, score, target_stocks, factor_values)


def record_performance(context, score, target_stocks, factor_values):
    """记录每日绩效与持仓信息"""
    total_value = context.portfolio.total_value
    positions_value = context.portfolio.positions_value
    returns = context.portfolio.returns

    log.info('账户净值: %.2f | 持仓市值: %.2f | 当日收益: %.4f | 持仓数: %d' % (
        total_value, positions_value, returns, len(context.portfolio.positions)))

    # 记录基准与组合净值（聚宽回测系统会自动生成净值曲线）
    record(total_value=total_value,
           num_positions=len(context.portfolio.positions),
           num_universe=len(score))


# ============================================================
# 入口（聚宽策略环境自动调用 initialize）
# ============================================================
