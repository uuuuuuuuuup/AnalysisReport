# -*- coding: utf-8 -*-
"""
================================================================================
米筐研究环境：高频散户行为反向因子探索脚本（v3 - 低内存版）
================================================================================
针对 8GB 内存优化：
  1. 按月分块拉取，每月约 120MB 原始数据
  2. 月内逐日 pivot 成小宽表计算，算完即释放
  3. 日因子结果增量写入 CSV，不堆积在内存
  4. 每月结束 del 原始数据 + gc.collect()
  5. 保留 numpy 向量化计算，不过度牺牲 CPU 效率

运行环境：ricequant.com 在线研究环境（Notebook）
数据接口：get_price(frequency='1m') / get_price(frequency='1d')
================================================================================
"""

import gc
import os
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    from rqdatac import get_price, index_components
except ImportError:
    try:
        from rqalpha_plus.apis import get_price, index_components
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
    'output_prefix': 'factor_discovery_rq_v3',
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


def month_chunks(start_date, end_date):
    """把日期范围按月切分，返回 [(month_start, month_end), ...]。"""
    start = pd.Timestamp(start_date).to_period('M')
    end = pd.Timestamp(end_date).to_period('M')
    chunks = []
    current = start
    while current <= end:
        chunks.append((current.start_time.strftime('%Y-%m-%d'),
                       current.end_time.strftime('%Y-%m-%d')))
        current += 1
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
            # 立即降精度减少内存
            for col in df.columns:
                if df[col].dtype == np.float64:
                    df[col] = df[col].astype(np.float32)
            all_dfs.append(df)
            print(f'  拉取 {i+1}-{min(i+batch_size, n)}/{n} 完成, shape={df.shape}, mem={df.memory_usage(deep=True).sum()/1e6:.1f}MB')
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
    """给分钟数据添加 date 列，并把 order_book_id 从索引转为列。"""
    df = df.copy().reset_index()
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
    elif 'date' in df.columns:
        df['datetime'] = pd.to_datetime(df['date'])
    else:
        df['datetime'] = pd.to_datetime(df.index)
    df['date'] = df['datetime'].dt.date.astype(str)
    return df


# ============================================================
# 向量化因子计算（单日的 numpy 数组）
# 输入 arr 形状均为 (n_stocks, n_minutes)
# 输出 shape (n_stocks,)
# ============================================================
def compute_pullback_intensity(open_arr, high_arr, low_arr, close_arr, volume_arr, amount_arr):
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

    count = np.sum(extreme_mask, axis=1)
    std_dev = np.nanstd(dev_masked, axis=1)
    return np.where(count >= 3, std_dev, np.nan)


def compute_volume_burst_continuation(open_arr, high_arr, low_arr, close_arr, volume_arr, amount_arr):
    n_stocks, n_minutes = volume_arr.shape
    # 使用 nanpercentile 处理停牌股票导致的 NaN
    threshold = np.nanpercentile(volume_arr, 90, axis=1, keepdims=True)
    burst_mask = volume_arr >= threshold

    post_ret = np.empty_like(close_arr, dtype=float)
    post_ret[:] = np.nan
    post_ret[:, :-5] = (close_arr[:, 5:] - close_arr[:, :-5]) / (close_arr[:, :-5] + 1e-12)

    valid = burst_mask.copy()
    valid[:, -5:] = False
    valid &= ~np.isnan(post_ret)

    count = valid.sum(axis=1)
    weighted = np.where(valid, post_ret, 0.0).sum(axis=1)
    return np.where(count > 0, weighted / count, np.nan)


FACTOR_CONFIG = [
    {'name': 'pullback_intensity', 'func': compute_pullback_intensity, 'direction_hypo': -1},
    {'name': 'down_up_concentration', 'func': compute_down_up_concentration, 'direction_hypo': -1},
    {'name': 'post_decline_recovery', 'func': compute_post_decline_recovery, 'direction_hypo': None},
    {'name': 'extreme_comovement_deviation', 'func': compute_extreme_comovement_deviation, 'direction_hypo': None},
    {'name': 'volume_burst_continuation', 'func': compute_volume_burst_continuation, 'direction_hypo': 1},
]


# ============================================================
# 按月处理：逐日计算并增量写 CSV
# ============================================================
def process_month(month_start, month_end, stocks, index_code, lookback_days, output_csv):
    """
    处理一个月的数据，逐日计算因子，结果追加写入 output_csv。
    """
    # 多取 lookback_days*3 天，用于月初几天的 lookback
    data_start = (pd.Timestamp(month_start) - pd.Timedelta(days=lookback_days * 3)).strftime('%Y-%m-%d')
    data_end = month_end

    print(f'\n拉取 {month_start} ~ {month_end} 分钟数据...')
    minute_df = get_minute_data_batched(stocks, data_start, data_end, CONFIG['stock_batch_size'])
    if minute_df.empty:
        print('无分钟数据')
        return 0

    index_minute_df = get_minute_data_batched([index_code], data_start, data_end, 1)
    if index_minute_df.empty:
        print('无指数分钟数据')
        del minute_df
        gc.collect()
        return 0

    minute_df = add_date_column(minute_df)
    index_minute_df = add_date_column(index_minute_df)

    # 字段别名
    for old, new in {'total_turnover': 'amount'}.items():
        if old in minute_df.columns and new not in minute_df.columns:
            minute_df[new] = minute_df[old]
        if old in index_minute_df.columns and new not in index_minute_df.columns:
            index_minute_df[new] = index_minute_df[old]

    # 只处理本月交易日
    target_dates = sorted([d for d in minute_df['date'].unique()
                           if pd.Timestamp(month_start) <= pd.Timestamp(d) <= pd.Timestamp(month_end)])

    n_written = 0
    for date in target_dates:
        day_df = minute_df[minute_df['date'] == date]
        idx_day = index_minute_df[index_minute_df['date'] == date]

        if len(day_df) < 100 or len(idx_day) < 100:
            continue

        try:
            # pivot 单日数据
            close_wide = day_df.pivot(index='datetime', columns='order_book_id', values='close')
            open_wide = day_df.pivot(index='datetime', columns='order_book_id', values='open')
            high_wide = day_df.pivot(index='datetime', columns='order_book_id', values='high')
            low_wide = day_df.pivot(index='datetime', columns='order_book_id', values='low')
            vol_wide = day_df.pivot(index='datetime', columns='order_book_id', values='volume')
            amt_wide = day_df.pivot(index='datetime', columns='order_book_id', values='amount')
        except Exception as e:
            print(f'  {date} pivot 失败: {e}')
            continue

        # reindex 到目标股票列表
        close_wide = close_wide.reindex(columns=stocks)
        open_wide = open_wide.reindex(columns=stocks)
        high_wide = high_wide.reindex(columns=stocks)
        low_wide = low_wide.reindex(columns=stocks)
        vol_wide = vol_wide.reindex(columns=stocks)
        amt_wide = amt_wide.reindex(columns=stocks)

        # 转置为 (n_stocks, n_minutes)，float32 转 float64 计算（percentile 需要）
        open_arr = open_wide.values.T.astype(np.float64)
        high_arr = high_wide.values.T.astype(np.float64)
        low_arr = low_wide.values.T.astype(np.float64)
        close_arr = close_wide.values.T.astype(np.float64)
        vol_arr = vol_wide.values.T.astype(np.float64)
        amt_arr = amt_wide.values.T.astype(np.float64)

        valid_mask = np.sum(~np.isnan(close_arr), axis=1) >= CONFIG['min_minutes_per_day']
        if valid_mask.sum() == 0:
            continue

        valid_stocks = close_wide.columns[valid_mask].tolist()
        sub_open = open_arr[valid_mask]
        sub_high = high_arr[valid_mask]
        sub_low = low_arr[valid_mask]
        sub_close = close_arr[valid_mask]
        sub_vol = vol_arr[valid_mask]
        sub_amt = amt_arr[valid_mask]

        idx_close = idx_day.sort_values('datetime')['close'].values.astype(np.float64)

        rows = []
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
                rows.append({'date': date, 'stock': stock, 'factor': cfg['name'], 'value': v})

        if rows:
            pd.DataFrame(rows).to_csv(output_csv, mode='a', header=not os.path.exists(output_csv),
                                      index=False, encoding='utf-8-sig')
            n_written += len(rows)

        # 释放单日大数组
        del (open_arr, high_arr, low_arr, close_arr, vol_arr, amt_arr,
             open_wide, high_wide, low_wide, close_wide, vol_wide, amt_wide,
             sub_open, sub_high, sub_low, sub_close, sub_vol, sub_amt)

    print(f'  {month_start} ~ {month_end} 写入 {n_written} 条记录')

    del minute_df, index_minute_df
    gc.collect()
    return n_written


# ============================================================
# IC 分析
# ============================================================
def analyze_factors(daily_factor_csv, start_date, end_date):
    """
    从增量 CSV 读取日因子，做 lookback 聚合，然后计算 IC。
    """
    print(f'\n读取日因子数据: {daily_factor_csv}')
    daily_factor_df = pd.read_csv(daily_factor_csv, parse_dates=['date'])
    print(f'总记录数: {len(daily_factor_df)}')

    lookback_days = CONFIG['lookback_days']

    # lookback 滚动平均
    daily_factor_df = daily_factor_df.sort_values(['stock', 'factor', 'date'])

    def rolling_agg(group):
        group = group.sort_values('date')
        group['value_agg'] = group['value'].shift(1).rolling(lookback_days, min_periods=1).mean()
        return group

    daily_factor_df = daily_factor_df.groupby(['stock', 'factor']).apply(rolling_agg)
    daily_factor_df = daily_factor_df.reset_index(drop=True)
    daily_factor_df = daily_factor_df[daily_factor_df['date'] >= pd.Timestamp(start_date)]

    # 转宽表
    factor_wide = daily_factor_df.pivot(index=['date', 'stock'], columns='factor', values='value_agg').reset_index()

    # 拉取日收盘价
    all_stocks = factor_wide['stock'].unique().tolist()
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

    # 合并
    close_long = daily_close_wide.reset_index().melt(id_vars='date', var_name='stock', value_name='close')
    close_long['date'] = pd.to_datetime(close_long['date'])
    merged = factor_wide.merge(close_long, on=['date', 'stock'], how='inner')
    merged = merged.sort_values(['stock', 'date'])
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
    return ic_report, corr, merged, daily_factor_df


# ============================================================
# 主流程
# ============================================================
def main():
    start_date = CONFIG['start_date']
    end_date = CONFIG['end_date']
    lookback_days = CONFIG['lookback_days']

    date_str = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
    daily_csv = f'{CONFIG["output_prefix"]}_daily_{date_str}.csv'

    chunks = month_chunks(start_date, end_date)
    print(f'共分为 {len(chunks)} 个月')

    # 预删除旧文件
    if os.path.exists(daily_csv):
        os.remove(daily_csv)

    for idx, (month_start, month_end) in enumerate(chunks):
        print(f'\n===== 第 {idx+1}/{len(chunks)} 个月 =====')
        stocks = load_universe(CONFIG['universe_index'], month_end, CONFIG['sample_n'])
        print(f'标的池: {len(stocks)} 只')
        process_month(month_start, month_end, stocks, CONFIG['universe_index'], lookback_days, daily_csv)

    # 分析
    ic_report, corr, merged, daily_factor_df = analyze_factors(daily_csv, start_date, end_date)

    # 保存
    ic_file = f'{CONFIG["output_prefix"]}_ic_{date_str}.csv'
    corr_file = f'{CONFIG["output_prefix"]}_corr_{date_str}.csv'
    merged_file = f'{CONFIG["output_prefix"]}_data_{date_str}.csv'

    ic_report.to_csv(ic_file, index=False, encoding='utf-8-sig')
    corr.to_csv(corr_file, encoding='utf-8-sig')
    merged.to_csv(merged_file, index=False, encoding='utf-8-sig')

    print('\n========== 因子 IC 汇总 (lag=0) ==========')
    print(ic_report[ic_report['lag'] == 0].to_string(index=False))
    print(f'\n日因子: {daily_csv}')
    print(f'IC 报告: {ic_file}')
    print(f'相关性矩阵: {corr_file}')
    print(f'合并数据: {merged_file}')


if __name__ == '__main__':
    main()
