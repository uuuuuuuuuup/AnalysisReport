# -*- coding: utf-8 -*-
# ============================================================
# 可转债双低策略参数敏感性测试（纯脚本计算，无回测引擎）
# ============================================================
# 用途：批量测试不同参数组合，验证策略稳健性，识别过拟合风险
#
# 测试维度：
#   1. 调仓频率 (REBALANCE_DAYS): 15, 20, 22, 25, 30
#   2. 持仓数量 (N_HOLD): 15, 20, 25, 30
#   3. 双低权重 (W_PRICE/W_PREMIUM): (0.3,0.7), (0.4,0.6), (0.5,0.5), (0.6,0.4), (0.7,0.3)
#   4. 信用过滤 (CREDIT_PRICE_FLOOR, CREDIT_PREMIUM_CEILING): (70,80), (80,100), (90,120)
#
# 输出：每个参数组合的年化收益、夏普、最大回撤、月胜率对比表
# ============================================================

import dai
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from itertools import product
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 固定参数（不参与测试）
# ============================================================
MIN_LIST_DAYS = 30
MIN_TERM_MONTHS = 12
BUFFER_RATIO = 1.25  # BUFFER_N = N_HOLD * BUFFER_RATIO

# 回测区间
START_DATE = '2019-01-01'
END_DATE = '2026-07-29'

# ============================================================
# 数据加载（只加载一次）
# ============================================================
def load_cbond_data():
    """加载可转债全量数据（新版数据表）"""
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

    print('数据加载完成: %d 行, %d 标的, %s ~ %s'
          % (len(df), df['instrument'].nunique(),
             df['date'].min().strftime('%Y-%m-%d'),
             df['date'].max().strftime('%Y-%m-%d')))

    return df


# ============================================================
# 策略核心逻辑
# ============================================================
def run_strategy(df, n_hold, w_price, w_premium,
                 credit_price_floor, credit_premium_ceiling,
                 rebalance_days):
    """
    运行策略并返回净值曲线

    参数：
        df: 可转债全量数据
        n_hold: 持仓数量
        w_price: 价格权重
        w_premium: 溢价率权重
        credit_price_floor: 信用过滤价格下限
        credit_premium_ceiling: 信用过滤溢价率上限
        rebalance_days: 调仓频率（交易日）

    返回：
        nav_series: 净值曲线 (日期索引)
        stats: 统计指标字典
    """
    buffer_n = int(n_hold * BUFFER_RATIO)

    # ---- 性能优化：构建价格矩阵（日期 × 标的）----
    # 用 pivot_table 加速价格查询
    price_matrix = df.pivot(index='date', columns='instrument', values='close')
    all_dates = price_matrix.index.sort_values()

    nav = [1.0]  # 初始净值
    nav_dates = [all_dates[0]]

    # 持仓记录
    holdings = {}  # {instrument: weight}
    day_count = 0

    # 月度收益记录（用于计算月胜率）
    monthly_returns = []
    last_nav = 1.0
    last_month = None

    for i, date in enumerate(all_dates):
        # 获取当天基础数据（用于过滤）
        cur = df[df['date'] == date].copy()

        if len(cur) < buffer_n:
            nav.append(nav[-1] if nav else 1.0)
            nav_dates.append(date)
            continue

        # ---- 过滤逻辑 ----
        cur['days_listed'] = (date - cur['list_date']).dt.days
        cur['months_to_mat'] = (cur['maturity_date'] - date).dt.days / 30.0

        cur = cur[(cur['days_listed'] >= MIN_LIST_DAYS) &
                  (cur['months_to_mat'] >= MIN_TERM_MONTHS)].copy()

        if len(cur) < buffer_n:
            nav.append(nav[-1] if nav else 1.0)
            nav_dates.append(date)
            continue

        # 信用过滤
        cur['risky'] = ((cur['close'] < credit_price_floor) &
                        (cur['premium_rate'] > credit_premium_ceiling))
        cur = cur[~cur['risky']]

        if len(cur) < buffer_n:
            nav.append(nav[-1] if nav else 1.0)
            nav_dates.append(date)
            continue

        # ---- 调仓日判断 ----
        day_count += 1
        should_rebalance = (day_count % rebalance_days == 0)

        if should_rebalance:
            # 双低打分
            for col in ['close', 'premium_rate']:
                s = cur[col]
                mean, std = s.mean(), s.std()
                cur[col + '_z'] = -(s - mean) / std if std > 0 else 0.0

            cur['score'] = w_price * cur['close_z'] + w_premium * cur['premium_rate_z']
            cur = cur.sort_values('score', ascending=False)

            # 缓冲带选股
            top_pool = cur.head(buffer_n)['instrument'].tolist()

            held_set = set(holdings.keys())
            keep = [s for s in top_pool if s in held_set]
            fresh = [s for s in top_pool if s not in held_set]
            selected = keep[:n_hold] + fresh[:max(0, n_hold - len(keep))]

            if len(selected) < n_hold * 0.7:
                nav.append(nav[-1] if nav else 1.0)
                nav_dates.append(date)
                continue

            # 更新持仓（等权）
            w = 1.0 / len(selected)
            holdings = {s: w for s in selected}

        # ---- 计算当日收益（用价格矩阵加速）----
        if holdings and i > 0:
            prev_date = all_dates[i - 1]

            # 批量获取当日和前一日价格
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

            # 只有至少一半持仓有效时才计算收益
            if valid_count >= len(holdings) * 0.5:
                nav.append(nav[-1] * (1 + daily_return))
            else:
                nav.append(nav[-1])
        else:
            nav.append(nav[-1] if nav else 1.0)

        nav_dates.append(date)

        # 记录月度收益（月份切换时计算上月收益）
        current_month = pd.Timestamp(date).strftime('%Y-%m')
        if last_month is not None and current_month != last_month:
            # 上个月收益 = 上月末净值 / 上月初净值 - 1
            monthly_return = (nav[-2] / last_nav - 1) if len(nav) >= 2 and last_nav > 0 else 0
            monthly_returns.append(monthly_return)
            last_nav = nav[-1]  # 新月份起始净值
        elif last_month is None:
            last_nav = nav[-1]
        last_month = current_month

    # 转为 Series
    nav_series = pd.Series(nav, index=pd.DatetimeIndex(nav_dates))

    # ---- 计算统计指标 ----
    # 年化收益率
    total_days = len(nav_series)
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    annual_return = (1 + total_return) ** (252 / total_days) - 1 if total_days > 0 else 0

    # 年化波动率（日收益标准差）
    daily_returns = nav_series.pct_change().dropna()
    annual_volatility = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0

    # 夏普比率（假设无风险利率为 3%）
    sharpe = (annual_return - 0.03) / annual_volatility if annual_volatility > 0 else 0

    # 最大回撤
    cummax = nav_series.cummax()
    drawdown = (nav_series - cummax) / cummax
    max_drawdown = drawdown.min()

    # 月胜率
    monthly_returns = pd.Series(monthly_returns)
    win_rate = (monthly_returns > 0).sum() / len(monthly_returns) if len(monthly_returns) > 0 else 0

    stats = {
        'annual_return': annual_return,
        'annual_volatility': annual_volatility,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'total_trades': day_count // rebalance_days if rebalance_days > 0 else 0
    }

    return nav_series, stats


# ============================================================
# 批量测试
# ============================================================
def run_sensitivity_test():
    """运行参数敏感性测试"""

    # 加载数据
    df = load_cbond_data()

    # 定义测试参数组合
    test_configs = {
        '调仓频率': {
            'param': 'rebalance_days',
            'values': [15, 20, 22, 25, 30]
        },
        '持仓数量': {
            'param': 'n_hold',
            'values': [15, 20, 25, 30]
        },
        '价格权重': {
            'param': 'w_price',
            'values': [0.3, 0.4, 0.5, 0.6, 0.7]
        },
        '信用过滤': {
            'param': 'credit_filter',
            'values': [(70, 80), (80, 100), (90, 120)]
        }
    }

    results = []

    # ============================================================
    # 测试 1: 调仓频率
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 1: 调仓频率敏感性')
    print('=' * 60)

    for rebalance_days in [15, 20, 22, 25, 30]:
        print('测试 REBALANCE_DAYS = %d ...' % rebalance_days)

        _, stats = run_strategy(
            df,
            n_hold=20,
            w_price=0.50,
            w_premium=0.50,
            credit_price_floor=80,
            credit_premium_ceiling=100,
            rebalance_days=rebalance_days
        )

        results.append({
            '测试维度': '调仓频率',
            '参数': f'{rebalance_days}天',
            '年化收益': f'{stats["annual_return"]:.2%}',
            '夏普': f'{stats["sharpe"]:.2f}',
            '最大回撤': f'{stats["max_drawdown"]:.2%}',
            '月胜率': f'{stats["win_rate"]:.1%}'
        })

    # ============================================================
    # 测试 2: 持仓数量
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 2: 持仓数量敏感性')
    print('=' * 60)

    for n_hold in [15, 20, 25, 30]:
        print('测试 N_HOLD = %d ...' % n_hold)

        _, stats = run_strategy(
            df,
            n_hold=n_hold,
            w_price=0.50,
            w_premium=0.50,
            credit_price_floor=80,
            credit_premium_ceiling=100,
            rebalance_days=22
        )

        results.append({
            '测试维度': '持仓数量',
            '参数': f'{n_hold}只',
            '年化收益': f'{stats["annual_return"]:.2%}',
            '夏普': f'{stats["sharpe"]:.2f}',
            '最大回撤': f'{stats["max_drawdown"]:.2%}',
            '月胜率': f'{stats["win_rate"]:.1%}'
        })

    # ============================================================
    # 测试 3: 双低权重
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 3: 双低权重敏感性')
    print('=' * 60)

    weight_pairs = [(0.3, 0.7), (0.4, 0.6), (0.5, 0.5), (0.6, 0.4), (0.7, 0.3)]

    for w_price, w_premium in weight_pairs:
        print('测试 W_PRICE = %.1f, W_PREMIUM = %.1f ...' % (w_price, w_premium))

        _, stats = run_strategy(
            df,
            n_hold=20,
            w_price=w_price,
            w_premium=w_premium,
            credit_price_floor=80,
            credit_premium_ceiling=100,
            rebalance_days=22
        )

        results.append({
            '测试维度': '双低权重',
            '参数': f'{w_price:.1f}/{w_premium:.1f}',
            '年化收益': f'{stats["annual_return"]:.2%}',
            '夏普': f'{stats["sharpe"]:.2f}',
            '最大回撤': f'{stats["max_drawdown"]:.2%}',
            '月胜率': f'{stats["win_rate"]:.1%}'
        })

    # ============================================================
    # 测试 4: 信用过滤阈值
    # ============================================================
    print('\n' + '=' * 60)
    print('测试 4: 信用过滤阈值敏感性')
    print('=' * 60)

    credit_filters = [(70, 80), (80, 100), (90, 120), (100, 150)]

    for price_floor, premium_ceiling in credit_filters:
        print('测试 PRICE=%.0f, PREMIUM=%.0f ...' % (price_floor, premium_ceiling))

        _, stats = run_strategy(
            df,
            n_hold=20,
            w_price=0.50,
            w_premium=0.50,
            credit_price_floor=price_floor,
            credit_premium_ceiling=premium_ceiling,
            rebalance_days=22
        )

        results.append({
            '测试维度': '信用过滤',
            '参数': f'价<{price_floor}/溢>{premium_ceiling}',
            '年化收益': f'{stats["annual_return"]:.2%}',
            '夏普': f'{stats["sharpe"]:.2f}',
            '最大回撤': f'{stats["max_drawdown"]:.2%}',
            '月胜率': f'{stats["win_rate"]:.1%}'
        })

    # ============================================================
    # 输出结果表
    # ============================================================
    results_df = pd.DataFrame(results)

    print('\n' + '=' * 80)
    print('参数敏感性测试结果汇总')
    print('=' * 80)
    print(results_df.to_string(index=False))

    # 保存到 CSV（使用当前工作目录，适配云端环境）
    output_file = 'cb_param_sensitivity_results.csv'
    results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print('\n结果已保存到: %s' % output_file)
    print('在 BigQuant 环境中，文件保存在当前工作目录，可在左侧文件列表查看')

    return results_df


# ============================================================
# 主程序
# ============================================================
if __name__ == '__main__':
    results = run_sensitivity_test()

    # 简要分析
    print('\n' + '=' * 80)
    print('敏感性分析结论')
    print('=' * 80)

    # 调仓频率分析
    freq_results = results[results['测试维度'] == '调仓频率']
    print('\n【调仓频率】')
    print('  年化收益范围: %s ~ %s' %
          (freq_results['年化收益'].min(), freq_results['年化收益'].max()))
    print('  建议: 选择夏普比率最高且收益稳定的调仓频率')

    # 持仓数量分析
    hold_results = results[results['测试维度'] == '持仓数量']
    print('\n【持仓数量】')
    print('  年化收益范围: %s ~ %s' %
          (hold_results['年化收益'].min(), hold_results['年化收益'].max()))
    print('  建议: 持仓数量应≥15只，避免集中度过高风险')

    print('\n【整体评估】')
    print('  如果各参数组合的年化收益波动 < 5%，说明策略稳健性良好')
    print('  如果某一参数微调导致收益大幅波动，说明存在过拟合风险')