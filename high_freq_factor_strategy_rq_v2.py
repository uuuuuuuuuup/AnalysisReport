# -*- coding: utf-8 -*-
# ============================================================
# 高频散户行为反向多因子策略 (米筐 RiceQuant 版 v2)
# ============================================================
# 策略逻辑：基于中证1000小盘股散户行为偏差，构建3个高频反向因子：
#   1. extreme_comovement_deviation  极端同步偏离   (方向 -1)
#   2. pullback_intensity            冲高回落强度   (方向 -1)
#   3. post_decline_recovery         跌后恢复效率   (方向 +1)
#
# 数据来源：分钟K线 (open/high/low/close/volume/total_turnover)
# 调仓频率：日频，每天 09:31 开盘后调仓
# 持仓数量：Top 20 等权
# 标的池：中证1000 (000852.XSHG)
# ============================================================

import numpy as np
import pandas as pd
from collections import defaultdict
from rqalpha.api import (
    history_bars, order_target_percent, get_position,
    index_components, update_universe, get_trading_dates,
    instruments, logger,
)


# ============================================================
# 配置
# ============================================================
CONFIG = {
    'universe_index': '000852.XSHG',
    'benchmark': '000852.XSHG',
    'top_n': 20,
    'lookback_days': 5,          # 因子回看交易日数
    'min_minutes_per_day': 200,  # 单日有效分钟数
    'min_listed_days': 60,       # 过滤次新股
    'slippage': 0.0001,          # 万1滑点
    'commission_buy': 0.0003,    # 买入佣金万3
    'commission_sell': 0.0013,   # 卖出佣金万3 + 印花税千1
    'factor_directions': {
        'extreme_comovement_deviation': -1,
        'pullback_intensity': -1,
        'post_decline_recovery': +1,
    },
}


# ============================================================
# 工具函数
# ============================================================
def safe_div(a, b, default=np.nan):
    """安全除法，避免除0。"""
    return np.where(np.abs(b) > 1e-12, a / b, default)


def parse_datetime(dt_values):
    """
    兼容处理 history_bars 返回的不同 datetime 格式：
    datetime64 / YYYYMMDDHHMMSS 整数 / 秒级时间戳 / 毫秒时间戳 / 字符串
    """
    s = pd.Series(dt_values)

    # 已经是 datetime 类型
    if np.issubdtype(s.dtype, np.datetime64):
        return pd.to_datetime(s)

    # 数值型：先判断是不是 YYYYMMDDHHMMSS 格式
    if np.issubdtype(s.dtype, np.number):
        min_val = s.min()
        max_val = s.max()
        # 14 位整数，例如 20201218093200
        if 1e13 <= max_val < 1e15 and min_val >= 1e13:
            return pd.to_datetime(s.astype(str), format='%Y%m%d%H%M%S')

        # 否则按 Unix 时间戳处理
        if max_val > 1e18:
            return pd.to_datetime(s, unit='ns')
        elif max_val > 1e12:
            return pd.to_datetime(s, unit='ms')
        elif max_val > 1e9:
            return pd.to_datetime(s, unit='s')
        else:
            return pd.to_datetime(s, unit='ns')

    # 字符串
    return pd.to_datetime(s, errors='coerce')


def extract_complete_days(bars):
    """
    从 history_bars 返回的分钟数据中，提取完整的交易日。
    返回：{date_str -> DataFrame(按时间排序)}，只包含至少 min_minutes 根的交易日。
    """
    if bars is None or len(bars) == 0:
        return {}

    # 米筐返回的是 np.recarray，字段名通过 dtype.names 访问
    df = pd.DataFrame({
        'datetime': bars['datetime'],
        'open': bars['open'],
        'high': bars['high'],
        'low': bars['low'],
        'close': bars['close'],
        'volume': bars['volume'],
        'amount': bars['total_turnover'],
    })
    df['datetime'] = parse_datetime(df['datetime'])
    df['date'] = df['datetime'].dt.strftime('%Y-%m-%d')
    df = df.sort_values('datetime')

    result = {}
    for date, grp in df.groupby('date'):
        if len(grp) >= CONFIG['min_minutes_per_day']:
            result[date] = grp.reset_index(drop=True)
    return result


def compute_extreme_comovement_deviation(open_arr, high_arr, low_arr, close_arr, amount_arr, index_close):
    """个股—市场极端同步偏离。方向 -1。"""
    n_stocks, n_minutes = close_arr.shape
    stock_ret = np.empty_like(close_arr, dtype=float)
    stock_ret[:] = np.nan
    stock_ret[:, 1:] = (close_arr[:, 1:] - close_arr[:, :-1]) / (close_arr[:, :-1] + 1e-12)

    index_ret = np.empty_like(index_close, dtype=float)
    index_ret[:] = np.nan
    index_ret[1:] = (index_close[1:] - index_close[:-1]) / (index_close[:-1] + 1e-12)

    threshold = np.nanpercentile(stock_ret, 90, axis=1, keepdims=True)
    extreme_mask = stock_ret >= threshold
    dev = stock_ret - index_ret
    dev_masked = np.where(extreme_mask, dev, np.nan)

    count = np.nansum(extreme_mask, axis=1)
    std_dev = np.nanstd(dev_masked, axis=1)
    return np.where(count >= 3, std_dev, np.nan)


def compute_pullback_intensity(open_arr, high_arr, low_arr, close_arr, amount_arr):
    """冲高回落强度。方向 -1。"""
    n_stocks, n_minutes = high_arr.shape
    high_idx = np.argmax(high_arr, axis=1)
    high_price = np.max(high_arr, axis=1)
    close_price = close_arr[:, -1]
    total_amount = np.nansum(amount_arr, axis=1)

    col_idx = np.arange(n_minutes)
    mask_after_peak = col_idx >= high_idx[:, None]
    amt_after_peak = np.nansum(amount_arr * mask_after_peak, axis=1)

    pullback = (high_price - close_price) / (high_price + 1e-12)
    factor = (amt_after_peak / (total_amount + 1e-12)) * pullback
    return np.where(total_amount > 0, factor, np.nan)


def compute_post_decline_recovery(open_arr, high_arr, low_arr, close_arr, amount_arr):
    """跌后恢复效率。方向 +1。"""
    n_stocks, n_minutes = close_arr.shape
    ret = np.empty_like(close_arr, dtype=float)
    ret[:] = np.nan
    ret[:, 1:] = (close_arr[:, 1:] - close_arr[:, :-1]) / (close_arr[:, :-1] + 1e-12)

    threshold = np.nanpercentile(ret, 10, axis=1, keepdims=True)
    big_down_mask = ret <= threshold

    pre_price = np.roll(close_arr, 1, axis=1)
    post_price = np.roll(close_arr, -10, axis=1)
    recovered = (post_price >= pre_price).astype(float)

    valid = big_down_mask.copy()
    valid[:, :1] = False
    valid[:, -10:] = False
    valid &= ~np.isnan(ret)

    count = valid.sum(axis=1)
    return np.where(count > 0, (recovered * valid).sum(axis=1) / count, np.nan)


FACTOR_FUNCS = {
    'extreme_comovement_deviation': compute_extreme_comovement_deviation,
    'pullback_intensity': compute_pullback_intensity,
    'post_decline_recovery': compute_post_decline_recovery,
}


# ============================================================
# 核心计算：从分钟数据提取 lookback 天因子并聚合
# ============================================================
def compute_stock_factor(context, stock, lookback_days, index_daily_dict):
    """
    计算单只股票过去 lookback_days 个交易日的聚合因子值。
    index_daily_dict: {date_str: index_close_array}
    返回 dict: {factor_name -> value}，value 为 NaN 表示无效。
    """
    bar_count = (lookback_days + 3) * 240
    try:
        bars = history_bars(
            stock, bar_count, '1m',
            fields=['datetime', 'open', 'high', 'low', 'close', 'volume', 'total_turnover']
        )
    except Exception as e:
        logger.warning(f'{stock} history_bars 失败: {e}')
        return {}

    daily_dict = extract_complete_days(bars)
    if len(daily_dict) < lookback_days:
        return {}

    dates = sorted(daily_dict.keys())
    today_str = context.now.strftime('%Y-%m-%d')
    if dates[-1] == today_str:
        dates = dates[:-1]
    use_dates = dates[-lookback_days:]
    if len(use_dates) < lookback_days:
        return {}

    daily_values = defaultdict(list)
    for d in use_dates:
        df = daily_dict[d]
        open_arr = df['open'].values.astype(float)[None, :]
        high_arr = df['high'].values.astype(float)[None, :]
        low_arr = df['low'].values.astype(float)[None, :]
        close_arr = df['close'].values.astype(float)[None, :]
        amount_arr = df['amount'].values.astype(float)[None, :]

        # 从预加载的指数数据里取当天
        index_close = index_daily_dict.get(d)

        for name, func in FACTOR_FUNCS.items():
            try:
                if name == 'extreme_comovement_deviation':
                    if index_close is None or len(index_close) < CONFIG['min_minutes_per_day']:
                        continue
                    v = func(open_arr, high_arr, low_arr, close_arr, amount_arr, index_close)[0]
                else:
                    v = func(open_arr, high_arr, low_arr, close_arr, amount_arr)[0]
                if not np.isnan(v):
                    daily_values[name].append(v)
            except Exception as e:
                logger.warning(f'{stock} {name} 计算失败: {e}')

    result = {}
    for name in FACTOR_FUNCS.keys():
        vals = daily_values.get(name, [])
        if len(vals) >= lookback_days - 1:
            result[name] = np.mean(vals)
    return result


def load_index_daily_dict(context, lookback_days):
    """
    每天调仓前加载指数最近 lookback_days+3 个完整交易日的分钟收盘价。
    返回 {date_str: close_array}
    """
    bar_count = (lookback_days + 5) * 240
    try:
        bars = history_bars(
            CONFIG['universe_index'], bar_count, '1m',
            fields=['datetime', 'close']
        )
    except Exception as e:
        logger.warning(f'指数 history_bars 失败: {e}')
        return {}

    df = pd.DataFrame({
        'datetime': parse_datetime(bars['datetime']),
        'close': bars['close'].astype(float),
    })
    df['date'] = df['datetime'].dt.strftime('%Y-%m-%d')
    df = df.sort_values('datetime')

    result = {}
    for date, grp in df.groupby('date'):
        if len(grp) >= CONFIG['min_minutes_per_day']:
            result[date] = grp['close'].values.astype(float)

    # 去掉今天（如果包含今天部分数据）
    today_str = context.now.strftime('%Y-%m-%d')
    if today_str in result:
        del result[today_str]

    logger.info(f'指数数据覆盖 {len(result)} 个完整交易日: {sorted(result.keys())[-lookback_days:]}')
    return result


# ============================================================
# 因子合成
# ============================================================
def synthesize_factors(factor_df, directions):
    """MAD去极值 + Z-Score标准化 + 方向调整 + 等权合成。"""
    if factor_df.empty:
        return pd.Series(dtype=float)

    df = factor_df.copy()

    # MAD 去极值
    for col in df.columns:
        s = df[col]
        med = s.median()
        mad = (s - med).abs().median()
        if mad > 0:
            df[col] = s.clip(lower=med - 3 * 1.4826 * mad,
                             upper=med + 3 * 1.4826 * mad)

    # Z-Score
    df = (df - df.mean()) / df.std()

    # 方向调整
    for col in df.columns:
        df[col] = df[col] * directions.get(col, 1)

    return df.mean(axis=1)


# ============================================================
# 策略入口
# ============================================================
def init(context):
    context.universe_index = CONFIG['universe_index']
    context.benchmark = CONFIG['benchmark']
    context.top_n = CONFIG['top_n']
    context.lookback_days = CONFIG['lookback_days']
    context.factor_directions = CONFIG['factor_directions']
    context.last_rebalance_date = None

    logger.info('=' * 60)
    logger.info('高频散户行为反向因子策略 v2 启动')
    logger.info(f'标的池={context.universe_index} | TopN={context.top_n} | 回看={context.lookback_days}')
    logger.info(f'启用因子: {list(context.factor_directions.keys())}')
    logger.info('=' * 60)


def handle_bar(context, bar_dict):
    """每天 09:31 开盘后调仓一次。"""
    now_time = context.now.strftime('%H:%M')
    if now_time != '09:31':
        return

    today_str = context.now.strftime('%Y-%m-%d')
    if context.last_rebalance_date == today_str:
        return
    context.last_rebalance_date = today_str

    _daily_rebalance(context, bar_dict)


def _daily_rebalance(context, bar_dict):
    today = context.now.date()
    logger.info(f'\n{"="*50}')
    logger.info(f'调仓日 {today}')

    # 1. 获取标的池
    try:
        universe = index_components(context.universe_index, date=today)
    except Exception as e:
        logger.warning(f'成分股查询失败: {e}')
        return

    universe = [s for s in universe if _is_listed_long_enough(s, CONFIG['min_listed_days'])]
    logger.info(f'标的池: {len(universe)} 只')
    if len(universe) < 50:
        logger.warning('标的池不足 50 只，跳过')
        return

    # 2. 预加载指数分钟数据；不能在每只股票里重复请求
    index_daily_dict = load_index_daily_dict(context, context.lookback_days)
    if len(index_daily_dict) < context.lookback_days:
        logger.warning(f'指数完整日数据不足 {context.lookback_days} 天，跳过')
        return

    # 3. 计算因子
    factor_values = {}
    fail_count = 0
    debug_logged = False
    for stock in universe:
        try:
            fv = compute_stock_factor(context, stock, context.lookback_days, index_daily_dict)
            if len(fv) >= len(context.factor_directions):
                factor_values[stock] = fv
            elif not debug_logged:
                debug_logged = True
                logger.info(f'[调试] {stock} 有效因子不足: {fv}')
        except Exception as e:
            fail_count += 1
            if fail_count <= 5:
                logger.warning(f'{stock} 因子计算异常: {e}')

    if len(factor_values) < 50:
        logger.warning(f'有效因子覆盖 {len(factor_values)} 只，不足 50，跳过')
        return

    factor_df = pd.DataFrame.from_dict(factor_values, orient='index')
    logger.info(f'因子覆盖: {len(factor_df)} 只股票')

    # 3. 合成
    composite = synthesize_factors(factor_df, context.factor_directions)
    if composite.empty:
        logger.warning('合成因子为空')
        return

    # 4. 选股 TopN
    picks = composite.nlargest(context.top_n).index.tolist()
    logger.info(f'选中 {len(picks)} 只: {picks[:5]}')

    # 5. 调仓
    _rebalance(context, picks)


def _is_listed_long_enough(stock, min_days):
    """检查上市天数。"""
    try:
        inst = instruments(stock)
        if inst is None:
            return False
        return inst.days_from_listed() >= min_days
    except Exception:
        return False


def _rebalance(context, picks):
    """先卖后买，等权配置。"""
    target_weight = 1.0 / len(picks) if picks else 0.0

    for stock in list(context.portfolio.positions.keys()):
        if stock not in picks:
            try:
                order_target_percent(stock, 0)
            except Exception:
                pass

    for stock in picks:
        try:
            order_target_percent(stock, target_weight)
        except Exception:
            pass


# ============================================================
# 米筐网页端配置建议
# ============================================================
# - 回测起止日期: 2021-01-01 ~ 2026-07-29
# - 频率: 分钟级 (1m)
# - 初始资金: 1,000,000
# - 基准: 000852.XSHG
# - 滑点/佣金在代码中已设置，也可在网页端配置
# ============================================================
