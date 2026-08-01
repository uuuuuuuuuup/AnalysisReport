# -*- coding: utf-8 -*-
# ============================================================
# 小盘股反转因子研究（BigQuant AI Studio）
# ============================================================
# 目的：系统性测试不同反转周期、不同市值域的因子有效性
#
# 测试内容：
#   1. 单因子IC测试：反转1周/2周/1月/3月 + 市值/波动/换手
#   2. 分组收益测试：5分组多空收益
#   3. 小市值域内反转增强：小盘×反转 vs 全市场反转
#   4. 复合因子预研：反转+波动+换手
#
# 输出：IC均值/ICIR、分组收益、多空收益对比表
# ============================================================

import dai
import pandas as pd
import numpy as np
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 参数
# ============================================================
# 数据划分（训练集/测试集，严格隔离）
# 训练集：用于因子研究和参数确定，可反复试
# 测试集：冻结后只看一次，禁止调参数
TRAIN_START = '2019-01-01'
TRAIN_END   = '2023-12-31'   # 训练集 5年
# ────────────────── 数据墙 ──────────────────
TEST_START  = '2024-01-01'   # 测试集 2.5年
TEST_END    = '2026-07-29'

# 当前阶段：因子研究 → 使用训练集
START_DATE = TRAIN_START
END_DATE   = TRAIN_END
N_GROUPS = 5           # 分组数
REBALANCE_FREQ = 'W'   # 调仓频率: W=周, 2W=双周, M=月

# 反转回看周期（交易日）
REVERSAL_PERIODS = [5, 10, 20, 60]
REVERSAL_LABELS = ['1周', '2周', '1月', '3月']


# ============================================================
# 数据加载（SQL层面过滤，避免加载全量prefactors）
# ============================================================
def load_stock_data():
    """加载A股日线数据 + 市值数据，SQL层面完成过滤"""
    print('加载数据（SQL层面过滤）...')

    # 一次查询：行情 + 市值 + 基本过滤条件，全部在SQL中完成
    # cn_stock_prefactors 提供 st_status / suspended / list_days / list_sector
    # cn_stock_valuation 提供 total_market_cap / float_market_cap
    sql = """
    SELECT
        p.date, p.instrument, p.close, p.volume,
        p.turn AS turnover_ratio, p.open, p.high, p.low,
        v.total_market_cap AS market_cap,
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
        AND f.list_days >= 60
        AND f.list_sector NOT IN (3, 4)
    ORDER BY p.date, p.instrument
    """

    df = dai.query(sql, filters={"date": [START_DATE, END_DATE]}).df()
    df['date'] = pd.to_datetime(df['date'])
    print('加载完成: %d 行, %d 标的' % (len(df), df['instrument'].nunique()))

    return df


# ============================================================
# 因子计算
# ============================================================
def compute_factors(df, reversal_period):
    """
    计算单日截面因子

    参数：
        df: 日线数据（需含 close, volume, turnover_ratio, circulating_market_cap）
        reversal_period: 反转回看天数

    返回：
        每日因子DataFrame
    """
    # 按标的分组计算
    grouped = df.groupby('instrument')

    # ---- 反转因子：过去N日收益率（负值=跌得多=反转信号强）----
    df['ret_backward'] = grouped['close'].transform(
        lambda x: x / x.shift(reversal_period) - 1
    )

    # ---- 波动因子：过去20日日收益标准差 ----
    df['daily_ret'] = grouped['close'].transform(
        lambda x: x.pct_change()
    )
    df['volatility_20d'] = grouped['daily_ret'].transform(
        lambda x: x.rolling(20, min_periods=10).std()
    )

    # ---- 换手率因子：过去20日平均换手率 ----
    df['turnover_20d'] = grouped['turnover_ratio'].transform(
        lambda x: x.rolling(20, min_periods=10).mean()
    )

    # ---- 市值因子 ----
    # circulating_market_cap 已在 df 中

    return df


# ============================================================
# IC 计算
# ============================================================
def compute_ic(df, factor_col, return_col='forward_ret_5d'):
    """
    计算因子IC（Spearman秩相关系数）

    参数：
        df: 含因子值和前向收益的DataFrame
        factor_col: 因子列名
        return_col: 前向收益列名

    返回：
        ic_series: 每日IC序列
    """
    dates = df['date'].unique()
    ic_list = []

    for date in dates:
        day_data = df[df['date'] == date][[factor_col, return_col]].dropna()

        if len(day_data) < 30:
            continue

        ic, _ = stats.spearmanr(day_data[factor_col], day_data[return_col])
        ic_list.append({'date': date, 'IC': ic})

    ic_series = pd.DataFrame(ic_list)
    return ic_series


# ============================================================
# 分组收益测试
# ============================================================
def compute_group_returns(df, factor_col, n_groups=N_GROUPS, return_col='forward_ret_5d'):
    """
    按因子值分组，计算各组平均收益

    参数：
        df: 含因子值和前向收益的DataFrame
        factor_col: 因子列名
        n_groups: 分组数
        return_col: 前向收益列名

    返回：
        group_stats: 各组统计指标
    """
    dates = df['date'].unique()
    all_groups = []

    for date in dates:
        day_data = df[df['date'] == date][[factor_col, return_col]].dropna()

        if len(day_data) < n_groups * 10:
            continue

        # 按因子值分组
        day_data['group'] = pd.qcut(day_data[factor_col], n_groups, labels=False, duplicates='drop')

        for g in range(n_groups):
            group_ret = day_data[day_data['group'] == g][return_col]
            if len(group_ret) > 0:
                all_groups.append({
                    'date': date,
                    'group': g,
                    'return': group_ret.mean()
                })

    group_df = pd.DataFrame(all_groups)

    if len(group_df) == 0:
        return None

    # 计算各组平均收益
    group_stats = group_df.groupby('group')['return'].agg(['mean', 'std', 'count'])
    group_stats.columns = ['平均收益', '收益标准差', '样本数']
    group_stats['年化收益'] = group_stats['平均收益'] * 252 / 5  # 假设5日持有期

    return group_stats


# ============================================================
# 主研究函数
# ============================================================
def run_factor_research():
    """运行因子研究"""

    # 加载数据（已含过滤：ST/停牌/次新/北交所/科创板）
    df = load_stock_data()

    print('过滤后: %d 行, %d 标的' % (len(df), df['instrument'].nunique()))

    # ---- 计算前向收益（5日、10日、20日）----
    print('计算前向收益...')
    grouped = df.groupby('instrument')
    df['forward_ret_5d'] = grouped['close'].transform(lambda x: x.shift(-5) / x - 1)
    df['forward_ret_10d'] = grouped['close'].transform(lambda x: x.shift(-10) / x - 1)
    df['forward_ret_20d'] = grouped['close'].transform(lambda x: x.shift(-20) / x - 1)

    # ---- 标记小市值域（每日市值排名后30%）----
    print('标记市值域...')
    df['cap_rank'] = df.groupby('date')['circulating_market_cap'].transform(
        lambda x: x.rank(pct=True)
    )
    df['is_small_cap'] = df['cap_rank'] <= 0.3  # 小市值：后30%

    # ============================================================
    # 测试 1: 单因子IC（反转不同周期）
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 1: 反转因子IC（不同回看周期）')
    print('=' * 60)

    ic_results = []

    for period, label in zip(REVERSAL_PERIODS, REVERSAL_LABELS):
        print('计算反转因子: %s (%d日)...' % (label, period))

        # 计算反转因子
        factor_col = 'reversal_%dd' % period
        df[factor_col] = df.groupby('instrument')['close'].transform(
            lambda x: -(x / x.shift(period) - 1)  # 负号：跌得多→因子值大
        )

        # 全市场IC
        ic_all = compute_ic(df, factor_col, 'forward_ret_5d')
        if len(ic_all) > 0:
            ic_mean = ic_all['IC'].mean()
            ic_std = ic_all['IC'].std()
            icir = ic_mean / ic_std if ic_std > 0 else 0
            ic_hit_rate = (ic_all['IC'] > 0).mean()
        else:
            ic_mean, icir, ic_hit_rate = 0, 0, 0

        # 小市值域IC
        df_small = df[df['is_small_cap']].copy()
        ic_small = compute_ic(df_small, factor_col, 'forward_ret_5d')
        if len(ic_small) > 0:
            ic_small_mean = ic_small['IC'].mean()
            ic_small_std = ic_small['IC'].std()
            icir_small = ic_small_mean / ic_small_std if ic_small_std > 0 else 0
        else:
            ic_small_mean, icir_small = 0, 0

        ic_results.append({
            '因子': '反转_%s' % label,
            '回看天数': period,
            '全市场IC均值': f'{ic_mean:.4f}',
            '全市场ICIR': f'{icir:.2f}',
            '全市场IC>0占比': f'{ic_hit_rate:.1%}',
            '小市值IC均值': f'{ic_small_mean:.4f}',
            '小市值ICIR': f'{icir_small:.2f}',
        })

    # ============================================================
    # 测试 2: 辅助因子IC（市值/波动/换手）
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 2: 辅助因子IC')
    print('=' * 60)

    # 计算辅助因子
    print('计算波动因子...')
    df['volatility_20d'] = df.groupby('instrument')['close'].transform(
        lambda x: x.pct_change().rolling(20, min_periods=10).std()
    )

    print('计算换手率因子...')
    df['turnover_20d'] = df.groupby('instrument')['turnover_ratio'].transform(
        lambda x: x.rolling(20, min_periods=10).mean()
    )

    print('计算市值因子...')
    df['log_cap'] = np.log(df['circulating_market_cap'])

    # 辅助因子IC
    aux_factors = {
        '小市值': ('log_cap', False),   # 负向：市值越小越好
        '高波动': ('volatility_20d', True),  # 正向：波动越大越好
        '低换手': ('turnover_20d', False),   # 负向：换手越低越好
    }

    for factor_label, (factor_col, is_positive) in aux_factors.items():
        # 如果是负向因子，取负
        if not is_positive:
            test_col = f'neg_{factor_col}'
            df[test_col] = -df[factor_col]
        else:
            test_col = factor_col

        ic_all = compute_ic(df, test_col, 'forward_ret_5d')
        if len(ic_all) > 0:
            ic_mean = ic_all['IC'].mean()
            ic_std = ic_all['IC'].std()
            icir = ic_mean / ic_std if ic_std > 0 else 0
            ic_hit_rate = (ic_all['IC'] > 0).mean()
        else:
            ic_mean, icir, ic_hit_rate = 0, 0, 0

        ic_results.append({
            '因子': factor_label,
            '回看天数': '-',
            '全市场IC均值': f'{ic_mean:.4f}',
            '全市场ICIR': f'{icir:.2f}',
            '全市场IC>0占比': f'{ic_hit_rate:.1%}',
            '小市值IC均值': '-',
            '小市值ICIR': '-',
        })

    # ============================================================
    # 测试 3: 分组收益（反转因子，5分组）
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 3: 反转因子分组收益（5分组）')
    print('=' * 60)

    group_results = []

    for period, label in zip(REVERSAL_PERIODS, REVERSAL_LABELS):
        factor_col = 'reversal_%dd' % period
        print('分组测试: 反转_%s ...' % label)

        # 全市场分组
        group_stats = compute_group_returns(df, factor_col, N_GROUPS, 'forward_ret_5d')
        if group_stats is not None and len(group_stats) == N_GROUPS:
            long_ret = group_stats.loc[N_GROUPS - 1, '年化收益']
            short_ret = group_stats.loc[0, '年化收益']
            ls_ret = long_ret - short_ret

            group_results.append({
                '因子': '反转_%s' % label,
                '域': '全市场',
                'G1(空)': f'{group_stats.loc[0, "年化收益"]:.1%}',
                'G2': f'{group_stats.loc[1, "年化收益"]:.1%}',
                'G3': f'{group_stats.loc[2, "年化收益"]:.1%}',
                'G4': f'{group_stats.loc[3, "年化收益"]:.1%}',
                'G5(多)': f'{group_stats.loc[4, "年化收益"]:.1%}',
                '多空': f'{ls_ret:.1%}',
            })

        # 小市值域分组
        df_small = df[df['is_small_cap']].copy()
        group_stats_small = compute_group_returns(df_small, factor_col, N_GROUPS, 'forward_ret_5d')
        if group_stats_small is not None and len(group_stats_small) == N_GROUPS:
            long_ret = group_stats_small.loc[N_GROUPS - 1, '年化收益']
            short_ret = group_stats_small.loc[0, '年化收益']
            ls_ret = long_ret - short_ret

            group_results.append({
                '因子': '反转_%s' % label,
                '域': '小市值',
                'G1(空)': f'{group_stats_small.loc[0, "年化收益"]:.1%}',
                'G2': f'{group_stats_small.loc[1, "年化收益"]:.1%}',
                'G3': f'{group_stats_small.loc[2, "年化收益"]:.1%}',
                'G4': f'{group_stats_small.loc[3, "年化收益"]:.1%}',
                'G5(多)': f'{group_stats_small.loc[4, "年化收益"]:.1%}',
                '多空': f'{ls_ret:.1%}',
            })

    # ============================================================
    # 测试 4: 复合因子预研
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 4: 复合因子预研')
    print('=' * 60)

    composite_results = []

    # 找到IC最高的反转周期
    best_reversal = 'reversal_10d'  # 默认2周
    # 也可以根据IC结果动态选择

    # 复合因子1: 反转 + 小市值
    print('复合因子: 反转 + 小市值...')
    df['composite_rev_cap'] = (
        df[best_reversal].rank(pct=True) +
        (-df['log_cap']).rank(pct=True)
    ) / 2

    ic_comp = compute_ic(df, 'composite_rev_cap', 'forward_ret_5d')
    if len(ic_comp) > 0:
        ic_mean = ic_comp['IC'].mean()
        icir = ic_mean / ic_comp['IC'].std() if ic_comp['IC'].std() > 0 else 0
    else:
        ic_mean, icir = 0, 0

    composite_results.append({
        '复合因子': '反转2周 + 小市值',
        'IC均值': f'{ic_mean:.4f}',
        'ICIR': f'{icir:.2f}',
    })

    # 复合因子2: 反转 + 高波动
    print('复合因子: 反转 + 高波动...')
    df['composite_rev_vol'] = (
        df[best_reversal].rank(pct=True) +
        df['volatility_20d'].rank(pct=True)
    ) / 2

    ic_comp = compute_ic(df, 'composite_rev_vol', 'forward_ret_5d')
    if len(ic_comp) > 0:
        ic_mean = ic_comp['IC'].mean()
        icir = ic_mean / ic_comp['IC'].std() if ic_comp['IC'].std() > 0 else 0
    else:
        ic_mean, icir = 0, 0

    composite_results.append({
        '复合因子': '反转2周 + 高波动',
        'IC均值': f'{ic_mean:.4f}',
        'ICIR': f'{icir:.2f}',
    })

    # 复合因子3: 反转 + 小市值 + 高波动
    print('复合因子: 反转 + 小市值 + 高波动...')
    df['composite_rev_cap_vol'] = (
        df[best_reversal].rank(pct=True) +
        (-df['log_cap']).rank(pct=True) +
        df['volatility_20d'].rank(pct=True)
    ) / 3

    ic_comp = compute_ic(df, 'composite_rev_cap_vol', 'forward_ret_5d')
    if len(ic_comp) > 0:
        ic_mean = ic_comp['IC'].mean()
        icir = ic_mean / ic_comp['IC'].std() if ic_comp['IC'].std() > 0 else 0
    else:
        ic_mean, icir = 0, 0

    composite_results.append({
        '复合因子': '反转2周 + 小市值 + 高波动',
        'IC均值': f'{ic_mean:.4f}',
        'ICIR': f'{icir:.2f}',
    })

    # 复合因子4: 反转 + 小市值 + 高波动 + 低换手
    print('复合因子: 反转 + 小市值 + 高波动 + 低换手...')
    df['composite_all'] = (
        df[best_reversal].rank(pct=True) +
        (-df['log_cap']).rank(pct=True) +
        df['volatility_20d'].rank(pct=True) +
        (-df['turnover_20d']).rank(pct=True)
    ) / 4

    ic_comp = compute_ic(df, 'composite_all', 'forward_ret_5d')
    if len(ic_comp) > 0:
        ic_mean = ic_comp['IC'].mean()
        icir = ic_mean / ic_comp['IC'].std() if ic_comp['IC'].std() > 0 else 0
    else:
        ic_mean, icir = 0, 0

    composite_results.append({
        '复合因子': '反转2周 + 小市值 + 高波动 + 低换手',
        'IC均值': f'{ic_mean:.4f}',
        'ICIR': f'{icir:.2f}',
    })

    # ============================================================
    # 输出所有结果
    # ============================================================
    print('\n' + '=' * 80)
    print('因子研究结果汇总')
    print('=' * 80)

    # IC结果
    ic_df = pd.DataFrame(ic_results)
    print('\n【单因子IC】')
    print(ic_df.to_string(index=False))

    # 分组收益
    if group_results:
        group_df = pd.DataFrame(group_results)
        print('\n【分组收益（5分组，年化）】')
        print(group_df.to_string(index=False))

    # 复合因子
    comp_df = pd.DataFrame(composite_results)
    print('\n【复合因子IC】')
    print(comp_df.to_string(index=False))

    # 保存
    ic_df.to_csv('smallcap_reversal_ic_results.csv', index=False, encoding='utf-8-sig')
    if group_results:
        group_df.to_csv('smallcap_reversal_group_results.csv', index=False, encoding='utf-8-sig')
    comp_df.to_csv('smallcap_reversal_composite_results.csv', index=False, encoding='utf-8-sig')

    print('\n结果已保存到:')
    print('  smallcap_reversal_ic_results.csv')
    print('  smallcap_reversal_group_results.csv')
    print('  smallcap_reversal_composite_results.csv')

    return ic_df, group_results, comp_df


# ============================================================
# 主程序
# ============================================================
if __name__ == '__main__':
    results = run_factor_research()