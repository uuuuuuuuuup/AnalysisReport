# -*- coding: utf-8 -*-
"""
================================================================================
米筐研究环境：高频散户行为反向因子探索脚本（v2 - 空间换时间版）
================================================================================
优化目标：在 8GB 内存、CPU 核数少的环境下，用空间换时间，减少 API 调用和 Python 循环。

核心改进：
  1. 按年/半年分块拉取分钟数据，减少 get_price 调用次数
  2. 每天把所有股票 pivot 成 (n_stocks, n_minutes) 的 numpy 数组
  3. 因子计算全部向量化（numpy），避免逐只逐日循环
  4. 日因子先缓存，最后统一做 lookback 滚动平均
  5. 500 只股票一批拉取，超时自动降级到 200 只

运行环境：ricequant.com 在线研究环境（Notebook）
数据接口：get_price(frequency='1m') / get_price(frequency='1d')
================================================================================
"""

import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    from rqdatac import get_price, index_components, all_instruments
except ImportError:
    try:
        from rqalpha_plus.apis import get_price, index_components, all_instruments
    except ImportError:
        raise ImportError('无法导入米筐数据接口，请确认运行在研究环境。')


# ============================================================
# 配置
# ============================================================
CONFIG = {
    'universe_index': '000852.XSHG',
    'start_date': '2021-01-01',
    'end_date': '2023-12-31',
    'lookback_days': 5,
    'sample_n': None,          # None=全部成分股
    'min_minutes_per_day': 200,
    'output_prefix': 'factor_discovery_rq_v2',
    'chunk_unit': 'Y',         # 'Y'=按年, 'H'=按半年
    'stock_batch_size': 500,   # 每次拉取股票数
    'fallback_batch_size': 200,
}


# ============================================================
# 工具函数
# ============================================================
def get_trading_dates(start_date, end_date):
    """获取交易日历，统一返回 'YYYY-MM-DD' 字符串列表。"""
    try:
        from rqdatac import get_trading_dates as _get_trading_dates
        dates = _get_trading_dates(start_date, end_date)
    except Exception:
        dates = pd.date_range(start_date, end_date, freq='B')
    return [pd.Timestamp(d).strftime('%Y-%m-%d') for d in dates]


def split_date_range(start_date, end_date, unit='Y'):
    """把日期范围按年或半年切分。"""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    chunks = []
    current = start
    while current <= end:
        if unit == 'Y':
            chunk_end = pd.Timestamp(current.year, 12, 31)
        else:  # 'H'
            if current.month <= 6:
                chunk_end = pd.Timestamp(current.year, 6, 30)
            else:
                chunk_end = pd.Timestamp(current.year, 12, 31)
        chunk_end = min(chunk_end, end)
        chunks.append((current.strftime('%Y-%m-%d'), chunk_end.strftime('%Y-%m-%d')))
        current = chunk_end + pd.Timedelta(days=1)
    return chunks


def load_universe(index_code, date, sample_n=None):
    """加载指数成分股。"""
    try:
        stocks = index_components(index_code, date=date)
    except Exception as e:
        print(f'index_components 失败: {e}')
        stocks = []
    stocks = sorted(list(set(stocks)))
    if sample_n is not None and len(stocks) > sample_n:
        stocks = stocks[:sample_n]
    return stocks


def get_minute_data_batched(stocks, start_date, end_date, batch_size=500):
    """分批拉取分钟数据，自动处理大容量请求。"""
    all_dfs = []
    n = len(stocks)
    for i in range(0, n, batch_size):
        batch = stocks[i:i+batch_size]
        try:
            df = get_price(
                order_book_ids=batch,
                start_date=start_date,
                end_date=end_date,
                frequency='1m',
                fields=['open', 'high', 'low', 'close', 'volume', 'total_turnover'],
                expect_df=True,
                skip_suspended=False,
            )
            all_dfs.append(df)
            print(f'  拉取 {i+1}-{min(i+batch_size, n)}/{n} 完成, shape={df.shape}')
        except Exception as e:
            print(f'  拉取 {i+1}-{min(i+batch_size, n)} 失败: {e}')
            if batch_size > CONFIG['fallback_batch_size']:
                print(f'  降级到每批 {CONFIG["fallback_batch_size"]} 只重试')
                sub_dfs = get_minute_data_batched(batch, start_date, end_date,
                                                   CONFIG['fallback_batch_size'])
                all_dfs.extend(sub_dfs)
            else:
                print(f'  跳过该批')
    if not all_dfs:
        return pd.DataFrame()
    return pd.concat(all_dfs, sort=False)


def add_date_column(df):
    """给分钟数据添加 date 列。"""
    df = df.copy()
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
    elif isinstance(df.index, pd.MultiIndex):
        df['datetime'] = pd.to_datetime(df.index.get_level_values(1))
    else:
        df['datetime'] = pd.to_datetime(df.index)
    df['date'] = df['datetime'].dt.date.astype(str)
    return df


# ============================================================
# 向量化因子计算
# 输入 arr 形状均为 (n_stocks, n_minutes)
# 输出 shape (n_stocks,)
# ============================================================
def compute_pullback_intensity(open_arr, high_arr, low_arr, close_arr, volume_arr, amount_arr):
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


def compute_down_up_concentration(open_arr, high_arr, low_arr, close_arr, volume_arr, amount_arr):
    """下跌成交集中度相对上涨集中度。方向 -1（若数据反了可改）。"""
    up_mask = close_arr > open_arr
    down_mask = close_arr < open_arr

    up_amount_nan = np.where(up_mask, amount_arr, np.nan)
    down_amount_nan = np.where(down_mask, amount_arr, np.nan)

    up_q90 = np.nanpercentile(up_amount_nan, 90, axis=1)
    down_q90 = np.nanpercentile(down_amount_nan, 90, axis=1)
    up_sum = np.nansum(up_amount_nan, axis=1)
    down_sum = np.nansum(down_amount_nan, axis=1)

    up_conc = up_q90 / (up_sum + 1e-12)
    down_conc = down_q90 / (down_sum + 1e-12)
    factor = down_conc / (up_conc + 1e-12)
    return np.where((up_sum > 0) & (down_sum > 0), factor, np.nan)


def compute_post_decline_recovery(open_arr, high_arr, low_arr, close_arr, volume_arr, amount_arr):
    """跌后恢复效率。方向由数据确定。"""
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


def compute_extreme_comovement_deviation(open_arr, high_arr, low_arr, close_arr, volume_arr, amount_arr, index_close):
    """个股—市场极端同步偏离。方向由数据确定。"""
    n_stocks, n_minutes = close_arr.shape
    stock_ret = np.empty_like(close_arr, dtype=float)
    stock_ret[:] = np.nan
    stock_ret[:, 1:] = (close_arr[:, 1:] - close_arr[:, :-1]) / (close_arr[:, :-1] + 1e-12)

    index_ret = np.empty_like(index_close, dtype=float)
    index_ret[:] = np.nan
    index_ret[1:] = (index_close[1:] - index_close[:-1]) / (index_close[:-1] + 1e-12)

    threshold = np.nanpercentile(stock_ret, 90, axis=1, keepdims=True)
    extreme_mask = stock_ret >= threshold

    dev = stock_ret - index_ret  # broadcasting
    dev_masked = np.where(extreme_mask, dev, np.nan)

    mean_dev = np.nanmean(dev_masked, axis=1)
    std_dev = np.nanstd(dev_masked, axis=1)
    return np.where(extreme_mask.sum(axis=1) >= 3, std_dev, np.nan)


def compute_volume_burst_continuation(open_arr, high_arr, low_arr, close_arr, volume_arr, amount_arr):
    """成交量爆发后的价格延续（简化版，原效率衰减因子的替代）。方向 +1。"""
    n_stocks, n_minutes = volume_arr.shape
    threshold = np.percentile(volume_arr, 90, axis=1, keepdims=True)
    burst_mask = volume_arr >= threshold

    # 爆发后 5 分钟收益率
    post_ret = np.empty_like(close_arr, dtype=float)
    post_ret[:] = np.nan
    post_ret[:, :-5] = (close_arr[:, 5:] - close_arr[:, :-5]) / (close_arr[:, :-5] + 1e-12)

    valid = burst_mask.copy()
    valid[:, -5:] = False

    count = valid.sum(axis=1)
    return np.where(count > 0, (post_ret * valid).sum(axis=1) / count, np.nan)


# 因子注册表
FACTOR_CONFIG = [
    {'name': 'pullback_intensity', 'func': compute_pullback_intensity, 'direction_hypo': -1},
    {'name': 'down_up_concentration', 'func': compute_down_up_concentration, 'direction_hypo': -1},
    {'name': 'post_decline_recovery', 'func': compute_post_decline_recovery, 'direction_hypo': None},
    {'name': 'extreme_comovement_deviation', 'func': compute_extreme_comovement_deviation, 'direction_hypo': None},
    {'name': 'volume_burst_continuation', 'func': compute_volume_burst_continuation, 'direction_hypo': 1},
]


# ============================================================
# 按日批量计算因子
# ============================================================
def compute_factors_for_chunk(minute_df, index_minute_df, stocks):
    """
    对一个时间块的分钟数据，按日计算所有因子。
    返回 DataFrame: date, stock, factor1, factor2, ...
    """
    if minute_df.empty:
        return pd.DataFrame()

    minute_df = add_date_column(minute_df)
    index_minute_df = add_date_column(index_minute_df)

    # 字段别名统一
    field_map = {'total_turnover': 'amount'}
    for old, new in field_map.items():
        if old in minute_df.columns and new not in minute_df.columns:
            minute_df[new] = minute_df[old]
        if old in index_minute_df.columns and new not in index_minute_df.columns:
            index_minute_df[new] = index_minute_df[old]

    dates = sorted(minute_df['date'].unique())
    records = []

    for date in dates:
        day_df = minute_df[minute_df['date'] == date]
        idx_day = index_minute_df[index_minute_df['date'] == date]

        if len(day_df) < 100 or len(idx_day) < 100:
            continue

        # pivot 成 (datetime, stock) 宽表
        try:
            close_wide = day_df.pivot(index='datetime', columns='order_book_id', values='close')
            open_wide = day_df.pivot(index='datetime', columns='order_book_id', values='open')
            high_wide = day_df.pivot(index='datetime', columns='order_book_id', values='high')
            low_wide = day_df.pivot(index='datetime', columns='order_book_id', values='low')
            vol_wide = day_df.pivot(index='datetime', columns='order_book_id', values='volume')
            amt_wide = day_df.pivot(index='datetime', columns='order_book_id', values='amount')
        except Exception as e:
            print(f'  {date} pivot 失败: {e}')
            continue

        # 只保留目标股票，并按股票代码排序
        close_wide = close_wide.reindex(columns=stocks)
        open_wide = open_wide.reindex(columns=stocks)
        high_wide = high_wide.reindex(columns=stocks)
        low_wide = low_wide.reindex(columns=stocks)
        vol_wide = vol_wide.reindex(columns=stocks)
        amt_wide = amt_wide.reindex(columns=stocks)

        # 转置为 (n_stocks, n_minutes)
        open_arr = open_wide.values.T.astype(float)
        high_arr = high_wide.values.T.astype(float)
        low_arr = low_wide.values.T.astype(float)
        close_arr = close_wide.values.T.astype(float)
        vol_arr = vol_wide.values.T.astype(float)
        amt_arr = amt_wide.values.T.astype(float)

        # 过滤有效股票（当日数据足够）
        valid_mask = np.sum(~np.isnan(close_arr), axis=1) >= CONFIG['min_minutes_per_day']
        if valid_mask.sum() == 0:
            continue

        # 对有效股票计算因子
        valid_stocks = close_wide.columns[valid_mask].tolist()
        sub_open = open_arr[valid_mask]
        sub_high = high_arr[valid_mask]
        sub_low = low_arr[valid_mask]
        sub_close = close_arr[valid_mask]
        sub_vol = vol_arr[valid_mask]
        sub_amt = amt_arr[valid_mask]

        # 指数收益率
        idx_close = idx_day.sort_values('datetime')['close'].values.astype(float)

        row = {'date': date}
        for cfg in FACTOR_CONFIG:
            try:
                if cfg['name'] == 'extreme_comovement_deviation':
                    vals = cfg['func'](sub_open, sub_high, sub_low, sub_close, sub_vol, sub_amt, idx_close)
                else:
                    vals = cfg['func'](sub_open, sub_high, sub_low, sub_close, sub_vol, sub_amt)
            except Exception as e:
                print(f'  {date} 因子 {cfg["name"]} 计算失败: {e}')
                vals = np.full(len(valid_stocks), np.nan)

            for stock, v in zip(valid_stocks, vals):
                records.append({
                    'date': date,
                    'stock': stock,
                    'factor': cfg['name'],
                    'value': v,
                })

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)


# ============================================================
# IC 分析
# ============================================================
def analyze_factors(daily_factor_df, daily_close_wide):
    """
    daily_factor_df: long format, columns=[date, stock, factor, value]
    daily_close_wide: index=date_str, columns=stock
    """
    # 转宽表
    factor_wide = daily_factor_df.pivot(index=['date', 'stock'], columns='factor', values='value').reset_index()
    factor_wide['date'] = pd.to_datetime(factor_wide['date'])

    # 合并日收盘价
    close_long = daily_close_wide.reset_index().melt(id_vars='date', var_name='stock', value_name='close')
    close_long['date'] = pd.to_datetime(close_long['date'])
    merged = factor_wide.merge(close_long, on=['date', 'stock'], how='inner')
    merged = merged.sort_values(['stock', 'date'])

    # 计算次日收益
    merged['next_ret'] = merged.groupby('stock')['close'].shift(-1) / merged['close'] - 1
    merged = merged.dropna(subset=['next_ret'])

    factor_names = [cfg['name'] for cfg in FACTOR_CONFIG]
    reports = []

    for lag in range(0, 6):
        for name in factor_names:
            sub = merged[['date', 'stock', name, 'next_ret']].dropna().copy()
            if len(sub) < 30:
                continue
            if lag > 0:
                sub[name] = sub.groupby('stock')[name].shift(lag)
                sub = sub.dropna()
                if len(sub) < 30:
                    continue

            ic_series = sub.groupby('date').apply(lambda g: g[name].corr(g['next_ret'], method='spearman'))
            reports.append({
                'factor': name,
                'lag': lag,
                'n_obs': len(sub),
                'n_days': sub['date'].nunique(),
                'ic_mean': ic_series.mean(),
                'ic_std': ic_series.std(),
                'icir': ic_series.mean() / ic_series.std() if ic_series.std() > 0 else np.nan,
                'ic_positive_ratio': (ic_series > 0).mean(),
            })

    ic_report = pd.DataFrame(reports)
    corr = merged[factor_names].corr()
    return ic_report, corr, merged


# ============================================================
# 主流程
# ============================================================
def main():
    start_date = CONFIG['start_date']
    end_date = CONFIG['end_date']
    lookback_days = CONFIG['lookback_days']

    chunks = split_date_range(start_date, end_date, CONFIG['chunk_unit'])
    print(f'共分为 {len(chunks)} 个时间块: {chunks}')

    all_daily_factors = []

    for chunk_idx, (chunk_start, chunk_end) in enumerate(chunks):
        print(f'\n===== 处理第 {chunk_idx+1}/{len(chunks)} 块: {chunk_start} ~ {chunk_end} =====')

        # 成分股以该块结束日为基准
        stocks = load_universe(CONFIG['universe_index'], chunk_end, CONFIG['sample_n'])
        print(f'标的池数量: {len(stocks)}')

        # 拉取分钟数据，多取 lookback_days*2 天用于 lookback
        data_start = (pd.Timestamp(chunk_start) - pd.Timedelta(days=lookback_days * 3)).strftime('%Y-%m-%d')
        data_end = chunk_end

        minute_df = get_minute_data_batched(stocks, data_start, data_end, CONFIG['stock_batch_size'])
        if minute_df.empty:
            print('该块无分钟数据，跳过')
            continue

        # 拉取指数分钟数据
        index_minute_df = get_minute_data_batched([CONFIG['universe_index']], data_start, data_end, 1)

        # 计算该块日因子
        chunk_factors = compute_factors_for_chunk(minute_df, index_minute_df, stocks)
        print(f'该块生成日因子记录: {len(chunk_factors)}')

        if len(chunk_factors) > 0:
            all_daily_factors.append(chunk_factors)

    if not all_daily_factors:
        print('未生成任何因子数据')
        return

    daily_factor_df = pd.concat(all_daily_factors, ignore_index=True)
    print(f'\n总日因子记录数: {len(daily_factor_df)}')

    # lookback 滚动平均：对每只股票，按日期排序后取前 lookback_days 日均值
    daily_factor_df['date'] = pd.to_datetime(daily_factor_df['date'])
    daily_factor_df = daily_factor_df.sort_values(['stock', 'factor', 'date'])

    def rolling_agg(group):
        group = group.sort_values('date')
        group['value_agg'] = group['value'].shift(1).rolling(lookback_days, min_periods=1).mean()
        return group

    daily_factor_df = daily_factor_df.groupby(['stock', 'factor']).apply(rolling_agg)
    daily_factor_df = daily_factor_df.reset_index(drop=True)
    # 只保留 lookback 后的数据
    daily_factor_df = daily_factor_df[daily_factor_df['date'] >= pd.Timestamp(start_date)]

    # 拉取日收盘价
    all_stocks = daily_factor_df['stock'].unique().tolist()
    print(f'拉取 {len(all_stocks)} 只股票的日收盘价...')
    daily_close_wide = get_price(
        order_book_ids=all_stocks,
        start_date=start_date,
        end_date=(pd.Timestamp(end_date) + pd.Timedelta(days=10)).strftime('%Y-%m-%d'),
        frequency='1d',
        fields=['close'],
        expect_df=True,
        skip_suspended=False,
    )
    if isinstance(daily_close_wide.index, pd.MultiIndex):
        daily_close_wide = daily_close_wide['close'].unstack(level=0)
    elif 'order_book_id' in daily_close_wide.columns:
        daily_close_wide = daily_close_wide.pivot(index='date', columns='order_book_id', values='close')
    if isinstance(daily_close_wide.index, pd.DatetimeIndex):
        daily_close_wide.index = daily_close_wide.index.strftime('%Y-%m-%d')

    # 分析
    ic_report, corr, merged = analyze_factors(daily_factor_df, daily_close_wide)

    # 保存
    date_str = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
    ic_file = f'{CONFIG["output_prefix"]}_ic_{date_str}.csv'
    corr_file = f'{CONFIG["output_prefix"]}_corr_{date_str}.csv'
    merged_file = f'{CONFIG["output_prefix"]}_data_{date_str}.csv'
    daily_file = f'{CONFIG["output_prefix"]}_daily_{date_str}.csv'

    ic_report.to_csv(ic_file, index=False, encoding='utf-8-sig')
    corr.to_csv(corr_file, encoding='utf-8-sig')
    merged.to_csv(merged_file, index=False, encoding='utf-8-sig')
    daily_factor_df.to_csv(daily_file, index=False, encoding='utf-8-sig')

    print('\n========== 因子 IC 汇总 (lag=0) ==========')
    print(ic_report[ic_report['lag'] == 0].to_string(index=False))
    print(f'\nIC 报告: {ic_file}')
    print(f'相关性矩阵: {corr_file}')
    print(f'合并数据: {merged_file}')
    print(f'日因子: {daily_file}')


if __name__ == '__main__':
    main()
