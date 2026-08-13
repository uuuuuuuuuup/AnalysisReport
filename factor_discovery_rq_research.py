# -*- coding: utf-8 -*-
"""
================================================================================
米筐研究环境：高频散户行为反向因子探索脚本
================================================================================
运行环境: ricequant.com 在线研究环境 (Research / Notebook)
数据接口: get_price(frequency='1m')  或  get_price(frequency='1d')
目标    : 基于中证1000 分钟 OHLCV，计算候选因子并统计 IC/ICIR/衰减/相关性

使用方式:
  1. 在 ricequant.com 创建一个新的 Notebook
  2. 把本文件内容全部贴入一个 cell
  3. 修改 CONFIG 里的日期、股票数量等参数
  4. 运行
  5. 在当前工作目录查看生成的 CSV 报告

注意:
  - 本脚本只做因子分析，不产生交易信号
  - 中证1000 全成分股 × 多年分钟数据量很大，建议先用 sample_n=50 测试
  - 若 get_price 返回格式与下面假设不同，请根据报错调整字段解析
================================================================================
"""

import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 如果米筐研究环境已经自动初始化，可以注释掉下面两行
# import rqdatac as rq
# rq.init()

# 从研究环境导入数据接口（米筐在线 Notebook 通常已自动注入）
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
    # 标的池
    'universe_index': '000852.XSHG',  # 中证1000
    # 分析区间（建议使用训练/验证分段运行）
    'start_date': '2023-01-01',
    'end_date': '2023-06-30',
    # 因子计算回看交易日数
    'lookback_days': 5,
    # 最大分析股票数（设为 None 则取全部成分股；测试阶段建议 50-100）
    'sample_n': 50,
    # 每日至少需要多少根有效分钟线
    'min_minutes_per_day': 200,
    # 输出文件名
    'output_prefix': 'factor_discovery_rq',
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
        # 降级：生成所有日期后粗略过滤周末
        dates = pd.date_range(start_date, end_date, freq='B')

    return [pd.Timestamp(d).strftime('%Y-%m-%d') for d in dates]


def align_minute_to_day(minute_df):
    """
    把分钟级 DataFrame 按交易日分组。
    返回 dict: date_str -> DataFrame(按时间排序)
    """
    if minute_df is None or len(minute_df) == 0:
        return {}
    minute_df = minute_df.copy()

    if 'datetime' in minute_df.columns:
        minute_df['datetime'] = pd.to_datetime(minute_df['datetime'])
        minute_df['date'] = minute_df['datetime'].dt.date
    elif isinstance(minute_df.index, pd.MultiIndex):
        # 假设 level 0 是 order_book_id, level 1 是 datetime
        minute_df['datetime'] = pd.to_datetime(minute_df.index.get_level_values(1))
        minute_df['date'] = minute_df['datetime'].dt.date
    else:
        # 可能是 DatetimeIndex，也可能是字符串索引
        minute_df['datetime'] = pd.to_datetime(minute_df.index)
        minute_df['date'] = minute_df['datetime'].dt.date

    # 消除 'datetime' 同时是索引名和列名的歧义
    minute_df = minute_df.reset_index(drop=True)

    result = {}
    for d, grp in minute_df.groupby('date'):
        result[str(d)] = grp.sort_values('datetime')
    return result


def ensure_fields(df, required_fields):
    """确保 DataFrame 包含必要字段，尝试常见别名转换。"""
    df = df.copy()
    field_map = {
        'total_turnover': 'amount',
        'turnover': 'amount',
        'vol': 'volume',
        'money': 'amount',
    }
    for old, new in field_map.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    missing = [f for f in required_fields if f not in df.columns]
    if missing:
        raise ValueError(f'缺少字段: {missing}，现有字段: {list(df.columns)}')
    return df


# ============================================================
# 候选因子计算（每个因子接收单日分钟 DataFrame）
# ============================================================
def factor_pullback_intensity(df):
    """
    冲高回落强度
    因子 = （高点后成交额占比） * （高点到收盘回撤幅度）
    方向：-1
    """
    if len(df) < 30:
        return np.nan
    df = ensure_fields(df, ['high', 'close', 'amount'])
    high_idx = df['high'].idxmax()
    high_price = df['high'].max()
    close_price = df['close'].iloc[-1]
    total_amount = df['amount'].sum()
    if total_amount <= 0 or high_price <= 0:
        return np.nan
    amt_after_peak = df.loc[high_idx:, 'amount'].sum()
    pullback = (high_price - close_price) / high_price
    return (amt_after_peak / total_amount) * pullback


def factor_up_move_discontinuity(df):
    """
    上涨路径断裂率
    因子 = 上涨分钟后紧跟下跌分钟的次数 / 总分钟数
    方向：-1
    """
    if len(df) < 30:
        return np.nan
    df = ensure_fields(df, ['close'])
    ret = df['close'].pct_change().dropna()
    if len(ret) < 5:
        return np.nan
    up = ret > 0
    transitions = ((up.shift(1) == True) & (up == False)).sum()
    return transitions / len(ret)


def factor_down_up_concentration(df):
    """
    下跌成交集中度相对上涨集中度
    因子 = （下跌分钟 top10% 成交额 / 下跌总成交额） / （上涨分钟 top10% 成交额 / 上涨总成交额 + eps）
    方向：-1
    """
    if len(df) < 30:
        return np.nan
    df = ensure_fields(df, ['open', 'close', 'amount'])
    up_mask = df['close'] > df['open']
    down_mask = df['close'] < df['open']

    up_amt = df.loc[up_mask, 'amount']
    down_amt = df.loc[down_mask, 'amount']

    if len(up_amt) == 0 or len(down_amt) == 0 or up_amt.sum() <= 0 or down_amt.sum() <= 0:
        return np.nan

    up_conc = up_amt.quantile(0.9) / up_amt.sum()
    down_conc = down_amt.quantile(0.9) / down_amt.sum()
    return down_conc / (up_conc + 1e-12)


def factor_post_decline_recovery(df):
    """
    跌后恢复效率
    因子 = 大跌后 10 分钟内恢复到跌前价位的比例均值
    方向：训练区间确定，不预设
    """
    if len(df) < 30:
        return np.nan
    df = ensure_fields(df, ['close'])
    ret = df['close'].pct_change()
    if len(ret) < 10:
        return np.nan
    threshold = ret.quantile(0.1)
    big_down_idx = ret[ret <= threshold].index
    if len(big_down_idx) == 0:
        return np.nan

    recoveries = []
    for idx in big_down_idx:
        pos = df.index.get_loc(idx)
        if pos < 1 or pos + 10 >= len(df):
            continue
        pre_price = df['close'].iloc[pos - 1]
        post_price = df['close'].iloc[pos + 10]
        recoveries.append(1.0 if post_price >= pre_price else 0.0)

    return np.mean(recoveries) if recoveries else np.nan


def factor_extreme_comovement_deviation(df, index_df):
    """
    个股—市场极端同步偏离
    因子 = 个股涨幅 top10% 分钟里，个股收益相对指数收益的标准差
    方向：训练区间确定，不预设（偏离大=独立信息；偏离小=羊群）
    """
    if len(df) < 30 or index_df is None or len(index_df) < 30:
        return np.nan
    df = ensure_fields(df, ['close'])
    index_df = ensure_fields(index_df, ['close'])

    # 对齐时间
    df = df.copy()
    df['stock_ret'] = df['close'].pct_change()

    # 把指数收益合并到个股
    idx_ret = index_df['close'].pct_change().rename('index_ret')
    merged = df[['stock_ret']].merge(idx_ret, left_index=True, right_index=True, how='inner')
    if len(merged) < 10:
        return np.nan

    extreme = merged['stock_ret'] >= merged['stock_ret'].quantile(0.9)
    if extreme.sum() < 3:
        return np.nan
    dev = (merged.loc[extreme, 'stock_ret'] - merged.loc[extreme, 'index_ret']).std()
    return dev if not np.isnan(dev) else np.nan


def factor_volume_burst_efficiency_decay(df):
    """
    成交爆发后的路径效率衰减
    因子 = 爆发后5分钟路径效率 / 爆发前5分钟路径效率 的均值
    方向：-1
    """
    if len(df) < 30:
        return np.nan
    df = ensure_fields(df, ['open', 'high', 'low', 'close', 'volume'])

    burst_mask = df['volume'] >= df['volume'].quantile(0.9)
    burst_idx = df[burst_mask].index
    if len(burst_idx) == 0:
        return np.nan

    ratios = []
    for idx in burst_idx:
        pos = df.index.get_loc(idx)
        if pos < 5 or pos + 6 >= len(df):
            continue
        pre = df.iloc[pos - 5:pos]
        post = df.iloc[pos + 1:pos + 6]

        pre_net = abs(pre['close'].iloc[-1] - pre['close'].iloc[0])
        pre_range = pre['high'].max() - pre['low'].min()
        post_net = abs(post['close'].iloc[-1] - post['close'].iloc[0])
        post_range = post['high'].max() - post['low'].min()

        if pre_range > 0 and post_range > 0:
            ratios.append((post_net / post_range) / (pre_net / pre_range + 1e-12))

    return np.mean(ratios) if ratios else np.nan


# 因子注册表
FACTORS = {
    'pullback_intensity': {
        'func': factor_pullback_intensity,
        'hypothesis_direction': -1,  # 越大越差
        'needs_index': False,
    },
    'up_move_discontinuity': {
        'func': factor_up_move_discontinuity,
        'hypothesis_direction': -1,
        'needs_index': False,
    },
    'down_up_concentration': {
        'func': factor_down_up_concentration,
        'hypothesis_direction': -1,
        'needs_index': False,
    },
    'post_decline_recovery': {
        'func': factor_post_decline_recovery,
        'hypothesis_direction': None,  # 训练确定
        'needs_index': False,
    },
    'extreme_comovement_deviation': {
        'func': factor_extreme_comovement_deviation,
        'hypothesis_direction': None,
        'needs_index': True,
    },
    'volume_burst_efficiency_decay': {
        'func': factor_volume_burst_efficiency_decay,
        'hypothesis_direction': -1,
        'needs_index': False,
    },
}


# ============================================================
# 主流程
# ============================================================
def load_universe(index_code, end_date, sample_n=None):
    """加载指数成分股。"""
    try:
        stocks = index_components(index_code, date=end_date)
    except Exception as e:
        print(f'index_components 失败: {e}，尝试用 all_instruments')
        stocks = []

    if sample_n is not None and len(stocks) > sample_n:
        # 按股票代码排序取前 sample_n，保证可重复
        stocks = sorted(stocks)[:sample_n]
    return sorted(stocks)


def get_minute_data(stocks, start_date, end_date):
    """
    批量获取分钟数据。
    米筐 get_price 返回格式可能是长表 DataFrame（含 order_book_id 列）或多索引。
    """
    print(f'开始拉取 {len(stocks)} 只股票 {start_date} ~ {end_date} 的分钟数据...')
    try:
        df = get_price(
            order_book_ids=stocks,
            start_date=start_date,
            end_date=end_date,
            frequency='1m',
            fields=['open', 'high', 'low', 'close', 'volume', 'total_turnover'],
            expect_df=True,
            skip_suspended=False,
        )
    except Exception as e:
        print(f'get_price(expect_df=True) 失败，尝试默认返回: {e}')
        df = get_price(
            order_book_ids=stocks,
            start_date=start_date,
            end_date=end_date,
            frequency='1m',
            fields=['open', 'high', 'low', 'close', 'volume', 'total_turnover'],
            skip_suspended=False,
        )

    print(f'分钟数据 shape={df.shape}, columns={list(df.columns)}, index={df.index[:3]}')
    return df


def parse_minute_data(df):
    """
    把 get_price 返回的统一 DataFrame 解析为 {stock: {date: DataFrame}}。
    """
    result = defaultdict(dict)

    # 判断格式
    if isinstance(df.index, pd.MultiIndex):
        # level 0 通常是 order_book_id，level 1 是 datetime
        stock_col = df.index.get_level_values(0)
        for stock in df.index.get_level_values(0).unique():
            sub = df.xs(stock, level=0)
            result[stock] = align_minute_to_day(sub)
    elif 'order_book_id' in df.columns:
        for stock in df['order_book_id'].unique():
            sub = df[df['order_book_id'] == stock].copy()
            result[stock] = align_minute_to_day(sub)
    else:
        # 单只股票
        result[df.columns[0] if 'order_book_id' in df.columns else 'unknown'] = align_minute_to_day(df)

    return result


def get_daily_close(stocks, start_date, end_date):
    """获取日收盘价用于计算次日收益，返回 wide DataFrame: index=date_str, columns=stock。"""
    print(f'拉取日K线 {start_date} ~ {end_date} ...')
    df = get_price(
        order_book_ids=stocks,
        start_date=start_date,
        end_date=end_date,
        frequency='1d',
        fields=['close'],
        expect_df=True,
        skip_suspended=False,
    )
    # 统一格式为 wide: index=date_str, columns=stock
    if isinstance(df.index, pd.MultiIndex):
        # level 0: order_book_id, level 1: date
        wide = df['close'].unstack(level=0)
    elif 'order_book_id' in df.columns:
        # 长表
        if 'date' not in df.columns:
            df['date'] = pd.to_datetime(df.index).strftime('%Y-%m-%d')
        wide = df.pivot(index='date', columns='order_book_id', values='close')
    else:
        # 单只股票，index 可能是 date
        if isinstance(df.index, pd.DatetimeIndex):
            wide = df[['close']].copy()
            wide.index = wide.index.strftime('%Y-%m-%d')
        else:
            wide = df[['close']].copy()

    # 把索引统一为字符串
    if isinstance(wide.index, pd.DatetimeIndex):
        wide.index = wide.index.strftime('%Y-%m-%d')
    return wide


def compute_stock_factors(stock, daily_dict, index_daily_dict, lookback_days, trading_dates):
    """
    对单只股票，每个交易日计算过去 lookback_days 的聚合因子值。
    返回 DataFrame: index=date, columns=factor_names
    """
    available_dates = sorted(daily_dict.keys())
    records = []

    for i, date_str in enumerate(available_dates):
        # 找到该日期前 lookback_days 个交易日
        try:
            pos = trading_dates.index(date_str)
        except ValueError:
            continue
        start_pos = max(0, pos - lookback_days)
        hist_dates = [d for d in trading_dates[start_pos:pos] if d in daily_dict]
        if len(hist_dates) == 0:
            continue

        factor_vals = defaultdict(list)
        for d in hist_dates:
            day_df = daily_dict[d]
            if len(day_df) < CONFIG['min_minutes_per_day']:
                continue
            index_day_df = index_daily_dict.get(d)
            for name, cfg in FACTORS.items():
                try:
                    if cfg['needs_index']:
                        v = cfg['func'](day_df, index_day_df)
                    else:
                        v = cfg['func'](day_df)
                    if not np.isnan(v):
                        factor_vals[name].append(v)
                except Exception as e:
                    pass

        row = {'date': date_str, 'stock': stock}
        for name in FACTORS.keys():
            vals = factor_vals.get(name, [])
            row[name] = np.mean(vals) if vals else np.nan
        records.append(row)

    return pd.DataFrame(records)


def analyze_factors(factor_df, daily_close_wide):
    """
    计算每个因子的 IC、ICIR、方向一致性、滞后衰减、相关性矩阵。
    factor_df columns: date, stock, factor1, factor2, ...
    daily_close_wide: index=date, columns=stock
    """
    factor_df = factor_df.copy()
    factor_df['date'] = pd.to_datetime(factor_df['date'])
    factor_df = factor_df.sort_values(['stock', 'date'])

    # 计算次日收益率
    def calc_fwd_ret(group):
        group = group.sort_values('date')
        group['next_ret'] = group['close'].shift(-1) / group['close'] - 1
        return group

    # 先把日收盘价合并进来
    close_long = daily_close_wide.reset_index().melt(id_vars='date', var_name='stock', value_name='close')
    close_long['date'] = pd.to_datetime(close_long['date'])
    merged = factor_df.merge(close_long, on=['date', 'stock'], how='inner')
    merged = merged.groupby('stock').apply(calc_fwd_ret)
    merged = merged.reset_index(drop=True)

    # 去掉有 forward return 为空的行
    merged = merged.dropna(subset=['next_ret'])

    reports = []
    factor_names = [n for n in factor_df.columns if n not in ['date', 'stock']]

    for lag in range(0, 6):
        for name in factor_names:
            sub = merged[['date', 'stock', name, 'next_ret']].dropna().copy()
            if len(sub) < 30:
                continue

            if lag > 0:
                sub = sub.sort_values(['stock', 'date'])
                sub[name] = sub.groupby('stock')[name].shift(lag)
                sub = sub.dropna()
                if len(sub) < 30:
                    continue

            # Rank IC
            def _rank_ic(g):
                return g[name].corr(g['next_ret'], method='spearman')

            ics = sub.groupby('date').apply(_rank_ic)
            ic_mean = ics.mean()
            ic_std = ics.std()
            icir = ic_mean / ic_std if ic_std > 0 else np.nan
            ic_positive_ratio = (ics > 0).mean()

            reports.append({
                'factor': name,
                'lag': lag,
                'n_obs': len(sub),
                'n_days': sub['date'].nunique(),
                'ic_mean': ic_mean,
                'ic_std': ic_std,
                'icir': icir,
                'ic_positive_ratio': ic_positive_ratio,
            })

    ic_report = pd.DataFrame(reports)

    # 因子相关性矩阵（使用最新一个lag=0的截面）
    corr = merged[factor_names].corr()

    return ic_report, corr, merged


def main():
    start_date = CONFIG['start_date']
    end_date = CONFIG['end_date']
    lookback_days = CONFIG['lookback_days']
    sample_n = CONFIG['sample_n']

    # 1. 交易日历
    trading_dates = get_trading_dates(start_date, end_date)
    print(f'交易日数: {len(trading_dates)}')

    # 2. 标的池
    stocks = load_universe(CONFIG['universe_index'], end_date, sample_n)
    print(f'标的池数量: {len(stocks)}')

    # 3. 拉取分钟数据
    # 为了有足够回看，向前多取 lookback_days 交易日
    data_start = (pd.Timestamp(start_date) - pd.Timedelta(days=lookback_days * 2)).strftime('%Y-%m-%d')
    minute_df = get_minute_data(stocks, data_start, end_date)
    parsed_minute = parse_minute_data(minute_df)

    # 4. 拉取指数分钟数据（用于 extreme_comovement_deviation）
    index_minute_df = get_minute_data([CONFIG['universe_index']], data_start, end_date)
    parsed_index = parse_minute_data(index_minute_df)
    index_daily_dict = parsed_index.get(CONFIG['universe_index'], {})

    # 调试用：打印第一只股票的解析结果
    if stocks and stocks[0] in parsed_minute:
        sample_stock = stocks[0]
        sample_dict = parsed_minute[sample_stock]
        sample_keys = sorted(sample_dict.keys())[:3]
        print(f'样本 {sample_stock} 解析出 {len(sample_dict)} 个交易日，前3天: {sample_keys}')
        for k in sample_keys:
            print(f'  {k}: shape={sample_dict[k].shape}, cols={list(sample_dict[k].columns)[:5]}')

    # 5. 逐只股票计算因子
    all_factor_frames = []
    for stock in stocks:
        if stock not in parsed_minute:
            continue
        daily_dict = parsed_minute[stock]
        ff = compute_stock_factors(stock, daily_dict, index_daily_dict, lookback_days, trading_dates)
        if len(ff) > 0:
            all_factor_frames.append(ff)
        print(f'完成 {stock}: {len(ff)} 条记录')

    if not all_factor_frames:
        print('没有生成任何因子数据，请检查数据拉取是否成功。')
        return

    factor_df = pd.concat(all_factor_frames, ignore_index=True)
    print(f'因子数据 shape={factor_df.shape}')

    # 6. 拉取日收盘价
    daily_close_wide = get_daily_close(stocks, start_date, end_date)

    # 7. 分析
    ic_report, corr, merged = analyze_factors(factor_df, daily_close_wide)

    # 8. 保存
    date_str = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
    ic_file = f'{CONFIG["output_prefix"]}_ic_{date_str}.csv'
    corr_file = f'{CONFIG["output_prefix"]}_corr_{date_str}.csv'
    merged_file = f'{CONFIG["output_prefix"]}_data_{date_str}.csv'

    ic_report.to_csv(ic_file, index=False, encoding='utf-8-sig')
    corr.to_csv(corr_file, encoding='utf-8-sig')
    merged.to_csv(merged_file, index=False, encoding='utf-8-sig')

    print('\n========== 因子 IC 汇总 (lag=0) ==========')
    print(ic_report[ic_report['lag'] == 0].to_string(index=False))
    print(f'\nIC 报告已保存: {ic_file}')
    print(f'相关性矩阵已保存: {corr_file}')
    print(f'原始数据已保存: {merged_file}')


if __name__ == '__main__':
    main()
