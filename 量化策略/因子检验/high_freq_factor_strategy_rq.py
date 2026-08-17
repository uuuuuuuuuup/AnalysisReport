# -*- coding: utf-8 -*-
# ============================================================
# 高频微观结构多因子组合策略 (米筐 RiceQuant 版)
# 平台: ricequant.com 在线回测  |  频率: 分钟级 (1m)
# ============================================================
#
# 因子来源 (来自6篇卖方研报,均为小众但实测有效的微观结构因子):
#   1. price_peak          价峰因子        (开源证券《微观结构(33) - 峰岭谷》)
#   2. vol_entropy         成交量分布熵值   (方正证券《暗流涌动因子》)
#   3. avg_amt_skew        分钟单笔金额偏度 (开源证券《微观结构(15)》)
#   4. big_order_push      大单推动涨幅     (海通证券《选股因子(69)》)
#   5. tail_vol_ratio      尾盘成交占比     (海通证券《选股因子(69)》)
#   6. modified_reversal   改进反转         (海通证券《选股因子(69)》)
#
# 数据要求:
#   - 分钟K线: history_bars(stock, N, '1m', ['open','high','low','close','volume','total_turnover'])
#   - 米筐在线平台免费版支持分钟级回测 (开源RQAlpha只有日线,在线平台有分钟数据)
#   - 股票代码格式: 000001.XSHE / 600519.XSHG (与聚宽一致)
#
# 回测建议:
#   - 标的池: 中证1000 (000852.XSHG) - 小盘股高频效应更显著
#   - 调仓频率: 日频 (可改周频降低换手)
#   - 回测区间: 2021-01-01 ~ 2026-07-29
#   - 初始资金: 100万
#   - 在 ricequant.com 网页上选 "多因子选股" 模板, 把本文件代码贴进去
#   - 频率选择 "1m" (分钟级)
# ============================================================

import numpy as np
import pandas as pd
from scipy.stats import entropy, skew
from rqalpha.api import (
    history_bars, order_target_percent, get_position,
    index_components, update_universe, order_shares,
    get_trading_dates, instruments, all_instruments,
    logger,
)


# ============================================================
# 配置
# ============================================================
CONFIG = {
    'universe_index': '000852.XSHG',  # 中证1000
    'benchmark': '000852.XSHG',
    'top_n': 20,                       # 选股数量
    'rebalance_freq': 1,               # 调仓频率(天), 1=日频, 5=周频
    'min_stocks': 50,                  # 标的池最小数量
    'lookback_days': 10,               # 因子计算回看天数
    'min_listed_days': 60,             # 最小上市天数(过滤次新)
    'slippage': 0.0001,                # 滑点 0.01%
    'commission_buy': 0.0003,          # 买入佣金万3
    'commission_sell': 0.0013,         # 卖出佣金万3+印花税千1
    'factor_names': [
        'price_peak', 'vol_entropy', 'avg_amt_skew',
        'big_order_push', 'tail_vol_ratio', 'modified_reversal'
    ],
    'factor_directions': {             # +1=因子值越大越看好, -1=越小越看好
        'price_peak': +1,
        'vol_entropy': -1,
        'avg_amt_skew': -1,
        'big_order_push': -1,
        'tail_vol_ratio': -1,
        'modified_reversal': -1,
    },
    # 大单阈值(单位:元,成交额超过此值视为大单)
    'big_order_threshold': 200000,
    # 尾盘时段(分钟索引, 9:30=0, 14:55=230)
    'tail_start_idx': 210,             # 14:00 开始
    'tail_end_idx': 240,               # 15:00 收盘
    # 反转提纯: 排除开盘30分钟(开盘跳跃), 用剩余时段计算反转
    'reversal_exclude_open': 30,
}


# ============================================================
# 因子基类与注册
# ============================================================
_FACTOR_REGISTRY = {}


def register_factor(name):
    """因子注册装饰器"""
    def decorator(cls):
        _FACTOR_REGISTRY[name] = cls
        return cls
    return decorator


class Factor:
    """因子基类"""
    name = 'base'
    direction = +1  # +1=正向, -1=反向

    def compute(self, bars_1m):
        """
        计算因子值
        :param bars_1m: np.ndarray, 分钟K线数据 (fields: datetime/open/high/low/close/volume/total_turnover)
        :return: float, 因子值 (NaN表示无效)
        """
        raise NotImplementedError


    # ---- 辅助方法 ----
    @staticmethod
    def safe_div(a, b):
        if b is None or b == 0 or np.isnan(b):
            return np.nan
        return a / b


# ============================================================
# 因子1: 价峰因子 (开源证券《微观结构(33)》)
# ============================================================
@register_factor('price_peak')
class PricePeakFactor(Factor):
    """
    价峰因子: 过去N天内, 日内最高价-开盘价跳变幅度 > X% 的次数占比
    逻辑: 价格跳跃是主力资金进场的信号, 跳跃次数多=主力活跃
    方向: +1 (跳跃越多越看好)
    """
    name = 'price_peak'
    direction = +1

    # 跳跃阈值: 日内 (high-open)/open > 1%
    PEAK_THRESHOLD = 0.01

    def compute(self, bars_1m):
        if len(bars_1m) == 0:
            return np.nan
        open_px = bars_1m['open'][0]
        high_px = bars_1m['high'].max()
        if open_px <= 0:
            return np.nan
        peak_pct = (high_px - open_px) / open_px
        # 当日是否发生跳跃 (二元变量)
        return 1.0 if peak_pct > self.PEAK_THRESHOLD else 0.0


# ============================================================
# 因子2: 成交量分布熵值 (方正证券《暗流涌动因子》)
# ============================================================
@register_factor('vol_entropy')
class VolEntropyFactor(Factor):
    """
    成交量熵值: 分钟成交量的信息熵
    逻辑: 熵值低=成交量集中在某些分钟(有资金主动选择时段)
          熵值高=成交量均匀分散(随机交易,无主力)
    方向: -1 (熵值低越看好)
    """
    name = 'vol_entropy'
    direction = -1

    def compute(self, bars_1m):
        vol = bars_1m['volume'].astype(float)
        vol = vol[vol > 0]  # 去除0成交量
        if len(vol) < 5:
            return np.nan
        # 归一化为概率分布
        p = vol / vol.sum()
        # 计算熵 (以e为底)
        return entropy(p)


# ============================================================
# 因子3: 分钟单笔金额偏度 (开源证券《微观结构(15)》)
# ============================================================
@register_factor('avg_amt_skew')
class AvgAmtSkewFactor(Factor):
    """
    单笔成交金额偏度: 当日所有分钟成交金额的偏度
    逻辑: 偏度<0 = 左偏 = 多数分钟成交额小,少数分钟成交额大 = 主力大单进场
          偏度>0 = 右偏 = 成交额分布均匀,无主力
    方向: -1 (偏度越小越看好)
    """
    name = 'avg_amt_skew'
    direction = -1

    def compute(self, bars_1m):
        amt = bars_1m['total_turnover'].astype(float)
        amt = amt[amt > 0]
        if len(amt) < 5:
            return np.nan
        return skew(amt)


# ============================================================
# 因子4: 大单推动涨幅 (海通证券《选股因子(69)》)
# ============================================================
@register_factor('big_order_push')
class BigOrderPushFactor(Factor):
    """
    大单推动涨幅: 大单成交额占比 * 涨幅
    逻辑: 大单占比高 + 涨幅高 = 主力主动拉升
          大单占比高 + 涨幅低 = 主力洗盘
          大单占比低 = 散户行情
    我们取: -1 * 大单占比 * 涨幅 (反向, 因为主力拉升后短期反转概率高)
    方向: -1
    """
    name = 'big_order_push'
    direction = -1

    def compute(self, bars_1m):
        amt = bars_1m['total_turnover'].astype(float)
        if len(amt) == 0:
            return np.nan
        total_amt = amt.sum()
        if total_amt <= 0:
            return np.nan
        # 大单占比
        big_ratio = (amt[amt > CONFIG['big_order_threshold']].sum() / total_amt)
        # 涨幅
        open_px = bars_1m['open'][0]
        close_px = bars_1m['close'][-1]
        if open_px <= 0:
            return np.nan
        ret = (close_px - open_px) / open_px
        return big_ratio * ret


# ============================================================
# 因子5: 尾盘成交占比 (海通证券《选股因子(69)》)
# ============================================================
@register_factor('tail_vol_ratio')
class TailVolRatioFactor(Factor):
    """
    尾盘成交占比: 14:00-15:00 成交额 / 全天成交额
    逻辑: 尾盘集中成交 = 主力做收盘价 (粉饰报表或布局次日)
    方向: -1 (尾盘成交占比高, 次日反转概率高, 反向)
    """
    name = 'tail_vol_ratio'
    direction = -1

    def compute(self, bars_1m):
        amt = bars_1m['total_turnover'].astype(float)
        total_amt = amt.sum()
        if total_amt <= 0:
            return np.nan
        tail_amt = amt[CONFIG['tail_start_idx']:CONFIG['tail_end_idx']].sum()
        return self.safe_div(tail_amt, total_amt)


# ============================================================
# 因子6: 改进反转 (海通证券《选股因子(69)》)
# ============================================================
@register_factor('modified_reversal')
class ModifiedReversalFactor(Factor):
    """
    改进反转: 排除开盘30分钟后的日内涨幅反转
    逻辑: 传统反转因子被开盘跳空噪声污染, 排除开盘后反转效应更稳定
    方向: -1 (涨幅高反向)
    """
    name = 'modified_reversal'
    direction = -1

    def compute(self, bars_1m):
        if len(bars_1m) < CONFIG['reversal_exclude_open'] + 5:
            return np.nan
        # 排除开盘N分钟, 用第N分钟开盘价作为基准
        base_idx = CONFIG['reversal_exclude_open']
        base_px = bars_1m['open'][base_idx]
        close_px = bars_1m['close'][-1]
        if base_px <= 0:
            return np.nan
        return (close_px - base_px) / base_px


# ============================================================
# 因子合成 (MAD去极值 + Z-Score标准化 + 方向调整 + 等权合成)
# ============================================================
def synthesize_factors(factor_df, factor_names, directions):
    """
    因子合成
    :param factor_df: DataFrame, index=stock, columns=factor_names
    :param factor_names: list, 因子名列表
    :param directions: dict, 因子方向
    :return: Series, 合成因子值 (越大越看好)
    """
    if factor_df.empty:
        return pd.Series(dtype=float)

    df = factor_df[factor_names].copy()

    # 1) MAD去极值
    for col in df.columns:
        s = df[col]
        med = s.median()
        mad = (s - med).abs().median()
        if mad > 0:
            df[col] = s.clip(lower=med - 3 * 1.4826 * mad,
                             upper=med + 3 * 1.4826 * mad)

    # 2) Z-Score标准化
    df = (df - df.mean()) / df.std()

    # 3) 方向调整 (方向=-1的因子取负)
    for col in df.columns:
        if directions.get(col, +1) == -1:
            df[col] = -df[col]

    # 4) 等权合成
    return df.mean(axis=1)


# ============================================================
# 米筐策略入口
# ============================================================
def init(context):
    """
    策略初始化 (米筐约定函数)
    """
    # ---- 设置佣金和滑点 ----
    # 米筐用 context.config 设置, 或在网页配置
    context.universe_index = CONFIG['universe_index']
    context.benchmark = CONFIG['benchmark']
    context.top_n = CONFIG['top_n']
    context.rebalance_freq = CONFIG['rebalance_freq']
    context.lookback_days = CONFIG['lookback_days']
    context.factor_names = CONFIG['factor_names']
    context.factor_directions = CONFIG['factor_directions']

    # ---- 状态 ----
    context.day_count = 0
    context.initialized = False
    context.nav_peak = 0.0
    context.nav_hist = []  # 月末净值序列 [(date, total)]
    context.last_rebalance_date = None  # 上次调仓日期(避免同日重复触发)
    context.debug_logged = False  # 诊断日志只打印一次

    # ---- 预加载因子实例 ----
    context.factors = {name: _FACTOR_REGISTRY[name]() for name in context.factor_names}

    logger.info('=' * 60)
    logger.info('高频微观结构多因子组合策略 (米筐版) 启动')
    logger.info('标的池=%s | 调仓=%d日 | TopN=%d | 滑点=%.4f | 佣金=%.4f' % (
        context.universe_index, context.rebalance_freq, context.top_n,
        CONFIG['slippage'], CONFIG['commission_buy']
    ))
    logger.info('启用因子: %s' % ' | '.join(context.factor_names))
    logger.info('=' * 60)


def handle_bar(context, bar_dict):
    """
    策略主循环 (米筐约定函数, 每个bar触发一次)

    日频回测: context.now 时间为 15:00 (收盘), 每日触发1次
    分钟回测: context.now 每分钟触发, 用 last_rebalance_date 防止同日重复
    """
    # 防止同日重复调仓 (兼容日频和分钟频)
    today_str = context.now.strftime('%Y-%m-%d')
    if context.last_rebalance_date == today_str:
        return
    context.last_rebalance_date = today_str

    _daily_rebalance(context, bar_dict)


def _daily_rebalance(context, bar_dict):
    """
    每日调仓逻辑
    """
    context.day_count += 1
    if context.day_count % context.rebalance_freq != 0:
        return

    # ---- 1. 获取标的池 ----
    today = context.now.date()
    try:
        universe = index_components(context.universe_index, date=today)
    except Exception as e:
        logger.warning('成分股查询失败: %s' % str(e))
        return

    if len(universe) < CONFIG['min_stocks']:
        logger.warning('调仓日 %s | 标的池不足 %d 只 (%d), 跳过' % (
            today, CONFIG['min_stocks'], len(universe)))
        return

    # ---- 2. 过滤次新股 ----
    universe = [
        s for s in universe
        if _is_listed_long_enough(s, CONFIG['min_listed_days'])
    ]

    # ---- 3. 计算因子 ----
    factor_values = {}
    fail_reasons = {}  # 诊断: 记录失败原因
    for stock in universe:
        try:
            bars_1m = _get_minute_bars(context, stock, context.lookback_days)
            if bars_1m is None:
                fail_reasons['data_none'] = fail_reasons.get('data_none', 0) + 1
                continue
            if len(bars_1m) < 60:  # 至少1小时数据
                fail_reasons['data_too_short'] = fail_reasons.get('data_too_short', 0) + 1
                continue
            # 计算该股票所有因子
            fv = {}
            for name, factor in context.factors.items():
                try:
                    v = factor.compute(bars_1m)
                    if not np.isnan(v):
                        fv[name] = v
                    else:
                        fail_reasons['factor_nan_%s' % name] = fail_reasons.get('factor_nan_%s' % name, 0) + 1
                except Exception as fe:
                    fail_reasons['factor_err_%s' % name] = fail_reasons.get('factor_err_%s' % name, 0) + 1
                    # 第一次出错时打印详细错误, 便于定位问题
                    if not context.debug_logged:
                        logger.error('[诊断] 因子 %s 在 %s 上计算失败: %s' % (name, stock, str(fe)))
            # 至少要有3个因子值才参与选股
            if len(fv) >= 3:
                factor_values[stock] = fv
            else:
                fail_reasons['not_enough_factors'] = fail_reasons.get('not_enough_factors', 0) + 1
        except Exception as e:
            fail_reasons['outer_exception'] = fail_reasons.get('outer_exception', 0) + 1
            if not context.debug_logged:
                logger.error('[诊断] 股票 %s 处理失败: %s' % (stock, str(e)))

    # 首次调仓打印一次诊断信息 (字段名/数据形状)
    if not context.debug_logged:
        context.debug_logged = True
        try:
            sample_stock = universe[0]
            sample_bars = _get_minute_bars(context, sample_stock, 1)
            if sample_bars is not None and len(sample_bars) > 0:
                logger.info('[诊断] 样本股票 %s 分钟数据: %d 行, 字段=%s, 首行=%s' % (
                    sample_stock, len(sample_bars), sample_bars.dtype.names, sample_bars[0]
                ))
            else:
                logger.warning('[诊断] 样本股票 %s 分钟数据为空! 可能是权限问题' % sample_stock)
        except Exception as de:
            logger.error('[诊断] 获取样本数据失败: %s' % str(de))
        logger.info('[诊断] 失败原因汇总: %s' % str(fail_reasons))

    if len(factor_values) < 10:
        logger.warning('调仓日 %s | 有效因子值不足 (%d), 跳过' % (
            today, len(factor_values)))
        return

    # ---- 4. 因子合成 ----
    factor_df = pd.DataFrame.from_dict(factor_values, orient='index')
    composite = synthesize_factors(factor_df, context.factor_names, context.factor_directions)
    if composite.empty:
        return

    # ---- 5. 选股 TopN ----
    ranked = composite.sort_values(ascending=False)
    picks = ranked.head(context.top_n).index.tolist()

    # ---- 6. 调仓 ----
    _rebalance(context, picks)

    # ---- 7. 月报 ----
    _monthly_report(context, today)

    logger.info('调仓日 %s | 池=%d | 因子覆盖=%d | 持仓=%d' % (
        today, len(universe), len(factor_values), len(picks)))


# ============================================================
# 辅助函数
# ============================================================
def _get_minute_bars(context, stock, days):
    """
    获取分钟K线数据 (米筐 history_bars)
    :param stock: 股票代码
    :param days: 回看天数
    :return: np.ndarray, 字段=datetime/open/high/low/close/volume/total_turnover
    """
    try:
        # 米筐 history_bars: bar_count, frequency, fields
        # 每天约240根1分钟K线, 取 days * 240 + 缓冲
        bar_count = days * 240 + 20
        bars = history_bars(
            stock, bar_count, '1m',
            fields=['datetime', 'open', 'high', 'low', 'close', 'volume', 'total_turnover']
        )
        return bars
    except Exception as e:
        return None


def _is_listed_long_enough(stock, min_days):
    """检查股票上市天数是否足够"""
    try:
        inst = instruments(stock)
        if inst is None:
            return False
        days_listed = inst.days_from_listed()
        return days_listed >= min_days
    except Exception:
        return False


def _rebalance(context, picks):
    """
    调仓: 先卖后买, 等权配置
    :param picks: list, 选中的股票代码
    """
    target_weight = 1.0 / len(picks) if picks else 0.0

    # ---- 1. 卖出不在目标中的持仓 ----
    positions = context.portfolio.positions
    for stock in list(positions.keys()):
        if stock not in picks:
            try:
                order_target_percent(stock, 0)
            except Exception:
                pass

    # ---- 2. 买入目标股票 (等权) ----
    for stock in picks:
        try:
            order_target_percent(stock, target_weight)
        except Exception:
            pass


def _monthly_report(context, today):
    """
    月报: 净值、回撤、死亡条件检查
    """
    total = context.portfolio.total_value
    context.nav_peak = max(context.nav_peak, total)
    context.nav_hist.append((today, total))

    drawdown = total / context.nav_peak - 1 if context.nav_peak > 0 else 0
    cash = context.portfolio.cash

    logger.info('月报 | 总资产 %.0f | 现金 %.0f | 回撤 %.1f%%' % (
        total, cash, drawdown * 100))

    # 死亡条件1: 滚动绝对收益跑不过现金 (2%无风险)
    risk_free = 0.02
    for months, level in [(24, '告警'), (36, '建议停用')]:
        if len(context.nav_hist) > months:
            n0 = context.nav_hist[-months - 1][1]
            ret = total / n0 - 1
            cash_ret = (1 + risk_free) ** (months / 12.0) - 1
            if ret < cash_ret:
                logger.warning('[死亡条件-%s] 滚动%d个月绝对收益 %.2f%% < 现金 %.2f%%' % (
                    level, months, ret * 100, cash_ret * 100))

    # 死亡条件2: 回撤超阈值
    if drawdown < -0.30:
        logger.warning('[死亡条件-告警] 回撤 %.1f%% 超阈值, 请人工复核' % (drawdown * 100))


# ============================================================
# 在米筐在线平台运行时, 以下配置由网页端设置, 不需要在代码里写
# 网页端配置:
#   - 回测起止日期: 2021-01-01 ~ 2026-07-29
#   - 频率: 分钟级 (1m)
#   - 初始资金: 1,000,000
#   - 基准: 000852.XSHG (中证1000)
# ============================================================
