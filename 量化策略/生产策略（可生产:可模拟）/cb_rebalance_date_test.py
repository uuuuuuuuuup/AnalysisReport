# -*- coding: utf-8 -*-
# ============================================================
# 调仓日期敏感性测试
# ============================================================
# 目的：测试不同调仓日期对策略收益的影响
#
# 测试维度：
#   1. 固定日历日：每月1号、5号、10号、15号、20号、25号、最后一个交易日
#   2. 固定交易日间隔：每15/20/22/25/30个交易日
#   3. 随机调仓日：验证是否存在特定日期效应
#
# 输出：不同调仓日期的收益对比表
# ============================================================

import dai
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 固定参数
# ============================================================
N_HOLD = 20
W_PRICE = 0.50
W_PREMIUM = 0.50
MIN_LIST_DAYS = 30
MIN_TERM_MONTHS = 12
CREDIT_PRICE_FLOOR = 80
CREDIT_PREMIUM_CEILING = 100
BUFFER_RATIO = 1.25

START_DATE = '2019-01-01'
END_DATE = '2026-07-29'


# ============================================================
# 数据加载
# ============================================================
def load_cbond_data():
    """加载可转债全量数据"""
    print('加载可转债数据...')

    sql = """
    SELECT
        a.date, a.instrument, a.close,
        m.conversion_premium_rate AS premium_rate,
        b.maturity_date, b.list_date,
        b.name AS bond_name
    FROM cn_cbond_bar1d a
    INNER JOIN cn_cbond_basic_info b
        ON a.instrument = b.instrument
    INNER JOIN cn_cbond_analyze_metric m
        ON a.instrument = m.instrument AND a.date = m.date
    WHERE
        a.close > 0
        AND b.maturity_date IS NOT NULL
    ORDER BY a.date, a.instrument
    """

    df = dai.query(sql, filters={"date": [START_DATE, END_DATE]}).df()
    df['date'] = pd.to_datetime(df['date'])
    df['maturity_date'] = pd.to_datetime(df['maturity_date'])
    df['list_date'] = pd.to_datetime(df['list_date'])

    print('数据加载完成: %d 行, %d 标的'
          % (len(df), df['instrument'].nunique()))

    return df


# ============================================================
# 策略核心逻辑（修改版：支持固定日历日调仓）
# ============================================================
def run_strategy_calendar_days(df, rebalance_day_of_month):
    """
    固定日历日调仓策略

    参数：
        df: 可转债全量数据
        rebalance_day_of_month: 每月几号调仓（如 1, 5, 10, 15, 20, 25, -1表示最后一个交易日）
    """
    buffer_n = int(N_HOLD * BUFFER_RATIO)

    # 构建价格矩阵
    price_matrix = df.pivot(index='date', columns='instrument', values='close')
    all_dates = price_matrix.index.sort_values()

    nav = [1.0]
    nav_dates = [all_dates[0]]
    holdings = {}
    monthly_returns = []
    last_nav = 1.0
    last_month = None

    # 获取交易日历
    trading_days = pd.DatetimeIndex(all_dates)

    # 计算每月调仓日
    monthly_rebalance_dates = []
    for year_month in trading_days.strftime('%Y-%m').unique():
        month_dates = trading_days[trading_days.strftime('%Y-%m') == year_month]

        if rebalance_day_of_month == -1:
            # 最后一个交易日
            rebalance_date = month_dates[-1]
        else:
            # 找到第一个>=指定日期的交易日
            target_day = rebalance_day_of_month
            rebalance_date = None
            for d in month_dates:
                if d.day >= target_day:
                    rebalance_date = d
                    break
            # 如果没找到（如2月没有30号），用最后一个交易日
            if rebalance_date is None:
                rebalance_date = month_dates[-1]

        monthly_rebalance_dates.append(rebalance_date)

    monthly_rebalance_dates = pd.DatetimeIndex(monthly_rebalance_dates)

    # 遍历每个交易日
    for i, date in enumerate(all_dates):
        # 获取当天数据用于过滤
        cur = df[df['date'] == date].copy()

        if len(cur) < buffer_n:
            nav.append(nav[-1] if nav else 1.0)
            nav_dates.append(date)
            continue

        # 过滤逻辑
        cur['days_listed'] = (date - cur['list_date']).dt.days
        cur['months_to_mat'] = (cur['maturity_date'] - date).dt.days / 30.0
        cur = cur[(cur['days_listed'] >= MIN_LIST_DAYS) &
                  (cur['months_to_mat'] >= MIN_TERM_MONTHS)].copy()

        if len(cur) < buffer_n:
            nav.append(nav[-1] if nav else 1.0)
            nav_dates.append(date)
            continue

        # 信用过滤
        cur['risky'] = ((cur['close'] < CREDIT_PRICE_FLOOR) &
                        (cur['premium_rate'] > CREDIT_PREMIUM_CEILING))
        cur = cur[~cur['risky']]

        if len(cur) < buffer_n:
            nav.append(nav[-1] if nav else 1.0)
            nav_dates.append(date)
            continue

        # 判断是否为调仓日
        should_rebalance = (date in monthly_rebalance_dates)

        if should_rebalance:
            # 双低打分
            for col in ['close', 'premium_rate']:
                s = cur[col]
                mean, std = s.mean(), s.std()
                cur[col + '_z'] = -(s - mean) / std if std > 0 else 0.0

            cur['score'] = W_PRICE * cur['close_z'] + W_PREMIUM * cur['premium_rate_z']
            cur = cur.sort_values('score', ascending=False)

            # 缓冲带选股
            top_pool = cur.head(buffer_n)['instrument'].tolist()
            held_set = set(holdings.keys())
            keep = [s for s in top_pool if s in held_set]
            fresh = [s for s in top_pool if s not in held_set]
            selected = keep[:N_HOLD] + fresh[:max(0, N_HOLD - len(keep))]

            if len(selected) >= N_HOLD * 0.7:
                w = 1.0 / len(selected)
                holdings = {s: w for s in selected}

        # 计算当日收益
        if holdings and i > 0:
            prev_date = all_dates[i - 1]
            cur_prices = price_matrix.loc[date]
            prev_prices = price_matrix.loc[prev_date]

            daily_return = 0.0
            valid_count = 0

            for inst, weight in holdings.items():
                if inst in cur_prices.index and inst in prev_prices.index:
                    cur_p = cur_prices[inst]
                    prev_p = prev_prices[inst]
                    if not pd.isna(cur_p) and not pd.isna(prev_p) and prev_p > 0:
                        stock_return = (cur_p / prev_p - 1)
                        daily_return += stock_return * weight
                        valid_count += 1

            if valid_count >= len(holdings) * 0.5:
                nav.append(nav[-1] * (1 + daily_return))
            else:
                nav.append(nav[-1])
        else:
            nav.append(nav[-1] if nav else 1.0)

        nav_dates.append(date)

        # 记录月度收益
        current_month = pd.Timestamp(date).strftime('%Y-%m')
        if last_month is not None and current_month != last_month:
            monthly_return = (nav[-2] / last_nav - 1) if len(nav) >= 2 and last_nav > 0 else 0
            monthly_returns.append(monthly_return)
            last_nav = nav[-1]
        elif last_month is None:
            last_nav = nav[-1]
        last_month = current_month

    # 转为 Series
    nav_series = pd.Series(nav, index=pd.DatetimeIndex(nav_dates))

    # 计算统计指标
    total_days = len(nav_series)
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    annual_return = (1 + total_return) ** (252 / total_days) - 1 if total_days > 0 else 0

    daily_returns = nav_series.pct_change().dropna()
    annual_volatility = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0
    sharpe = (annual_return - 0.03) / annual_volatility if annual_volatility > 0 else 0

    cummax = nav_series.cummax()
    drawdown = (nav_series - cummax) / cummax
    max_drawdown = drawdown.min()

    monthly_returns = pd.Series(monthly_returns)
    win_rate = (monthly_returns > 0).sum() / len(monthly_returns) if len(monthly_returns) > 0 else 0

    stats = {
        'annual_return': annual_return,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate
    }

    return nav_series, stats


# ============================================================
# 主测试函数
# ============================================================
def run_rebalance_date_test():
    """运行调仓日期敏感性测试"""

    df = load_cbond_data()

    results = []

    # ============================================================
    # 测试 1: 固定日历日调仓
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 1: 固定日历日调仓')
    print('=' * 60)

    calendar_days = [1, 5, 10, 15, 20, 25, -1]  # -1表示最后一个交易日
    calendar_labels = {
        1: '每月1号',
        5: '每月5号',
        10: '每月10号',
        15: '每月15号',
        20: '每月20号',
        25: '每月25号',
        -1: '月末最后交易日'
    }

    for day in calendar_days:
        label = calendar_labels[day]
        print('测试 %s ...' % label)

        _, stats = run_strategy_calendar_days(df, day)

        results.append({
            '测试维度': '固定日历日',
            '参数': label,
            '年化收益': f'{stats["annual_return"]:.2%}',
            '夏普': f'{stats["sharpe"]:.2f}',
            '最大回撤': f'{stats["max_drawdown"]:.2%}',
            '月胜率': f'{stats["win_rate"]:.1%}'
        })

    # ============================================================
    # 输出结果
    # ============================================================
    results_df = pd.DataFrame(results)

    print('\n' + '=' * 80)
    print('调仓日期敏感性测试结果')
    print('=' * 80)
    print(results_df.to_string(index=False))

    # 保存
    output_file = 'cb_rebalance_date_results.csv'
    results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print('\n结果已保存到: %s' % output_file)

    # ============================================================
    # 分析结论
    # ============================================================
    print('\n' + '=' * 80)
    print('分析结论')
    print('=' * 80)

    # 计算收益波动范围
    returns = [float(r['年化收益'].replace('%', '')) for r in results]
    max_return = max(returns)
    min_return = min(returns)
    volatility = max_return - min_return

    print('\n【调仓日期影响】')
    print('  年化收益范围: %.2f%% ~ %.2f%%' % (min_return, max_return))
    print('  收益波动幅度: %.2f%%' % volatility)

    if volatility < 3:
        print('  ✅ 调仓日期对收益影响较小，策略稳健性良好')
    elif volatility < 5:
        print('  ⚠️ 调仓日期对收益有一定影响，但可接受')
    else:
        print('  ❌ 调仓日期对收益影响较大，存在特定日期效应')

    # 找出最优调仓日
    best_idx = returns.index(max(returns))
    best_day = results[best_idx]['参数']
    print('\n【最优调仓日】')
    print('  %s: 年化收益 %.2f%%' % (best_day, max_return))

    return results_df


# ============================================================
# 主程序
# ============================================================
if __name__ == '__main__':
    results = run_rebalance_date_test()