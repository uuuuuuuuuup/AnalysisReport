# -*- coding: utf-8 -*-
# ============================================================
# 三引擎合并脚本
# ============================================================
# 用法:
#   1. 在 BigQuant 分别跑:
#      unified_etf_engine_bq.py  → 导出 daily_nav_etf.csv  (净值+日期)
#      cb_classic_double_low_bq.py → 导出 daily_nav_cb.csv
#
#   2. 在 BigQuant 的 "绩效分析" → "收益曲线" → 导出CSV,
#      或从 bigtrader.run() 返回的 performance 对象中提取 daily_nav。
#
#   3. 运行本脚本: python merge_three_engine.py
#
# 合并公式推导:
#   ETF 账户: 100,000 本金, 65% 配置 (35%动量+30%红利), 35% 闲置现金
#   CB  账户: 100,000 本金, ~100% 配置可转债
#
#   设 ETF_inv 为 ETF 账户中投资部分的收益率:
#     ETF_NAV = 100,000 + 65,000 × ETF_inv  →  ETF_inv = (ETF_NAV - 100k) / 65k
#
#   三引擎合并 NAV (若在同一账户):
#     100,000 + 35,000×ETF_mom + 35,000×CB + 30,000×ETF_div
#   ≈ 100,000 + 65,000×ETF_inv + 35,000×CB_ret       (假定动量+红利收益率接近)
#   = 100,000 + (ETF_NAV - 100,000) + 35,000×(CB_NAV/100,000 - 1)
#   = ETF_NAV + 0.35 × CB_NAV - 35,000
#
# 验证 (零收益情形): 100,000 + 0.35×100,000 - 35,000 = 100,000 ✓
# ============================================================

import pandas as pd
import numpy as np
import sys


def load_nav(filepath, date_col='date', nav_col='nav'):
    """加载 BigQuant 导出的净值 CSV。"""
    df = pd.read_csv(filepath, parse_dates=[date_col])
    df = df.rename(columns={date_col: 'date', nav_col: 'nav'})
    df = df.sort_values('date').reset_index(drop=True)
    return df


def merge(etf_nav: pd.DataFrame, cb_nav: pd.DataFrame):
    """
    合并两条净值曲线。

    参数:
      etf_nav: ETF 账户净值 (unified_etf_engine_bq.py 输出)
      cb_nav:  CB 账户净值 (cb_classic_double_low_bq.py 输出)

    返回:
      DataFrame with columns: date, combined_nav, etf_nav, cb_nav
    """
    merged = pd.merge(etf_nav, cb_nav, on='date', how='inner', suffixes=('_etf', '_cb'))
    merged = merged.sort_values('date').reset_index(drop=True)

    # 合并公式: ETF_NAV + 0.35 × CB_NAV - 35,000
    merged['combined_nav'] = merged['nav_etf'] + 0.35 * merged['nav_cb'] - 35000.0

    print('合并区间: %s ~ %s (%d 个交易日)'
          % (merged['date'].min().strftime('%Y-%m-%d'),
             merged['date'].max().strftime('%Y-%m-%d'),
             len(merged)))

    return merged


def report(merged: pd.DataFrame):
    """计算合并后的绩效指标。"""
    nav = merged['combined_nav'].values
    initial = nav[0]
    final   = nav[-1]
    n_years = (merged['date'].iloc[-1] - merged['date'].iloc[0]).days / 365.25

    total_ret = final / initial - 1
    annual_ret = (final / initial) ** (1 / max(n_years, 0.01)) - 1

    # 日收益
    daily_ret = np.diff(nav) / nav[:-1]
    annual_vol = np.std(daily_ret) * np.sqrt(252)

    # 夏普 (rf=0)
    sharpe = np.mean(daily_ret) / np.std(daily_ret) * np.sqrt(252) if np.std(daily_ret) > 0 else 0

    # 最大回撤
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1
    max_dd = np.min(dd)

    print('=' * 60)
    print('三引擎合并绩效')
    print('=' * 60)
    print('区间:       %s ~ %s (%.1f 年)'
          % (merged['date'].iloc[0].strftime('%Y-%m-%d'),
             merged['date'].iloc[-1].strftime('%Y-%m-%d'), n_years))
    print('累计收益:    %.2f%%' % (total_ret * 100))
    print('年化收益:    %.2f%%' % (annual_ret * 100))
    print('年化波动:    %.2f%%' % (annual_vol * 100))
    print('夏普 (rf=0): %.3f' % sharpe)
    print('最大回撤:    %.2f%%' % (max_dd * 100))

    # 分引擎
    for label, col in [('ETF账户 (Engine 1+3)', 'nav_etf'), ('可转债账户 (Engine 2)', 'nav_cb')]:
        n = merged[col].values
        r = n[-1] / n[0] - 1
        ann = (n[-1] / n[0]) ** (1 / n_years) - 1
        print('  %s: 累计 %.2f%%  年化 %.2f%%' % (label, r * 100, ann * 100))

    print('=' * 60)
    return merged


if __name__ == '__main__':
    if len(sys.argv) >= 3:
        etf_file = sys.argv[1]
        cb_file  = sys.argv[2]
    else:
        etf_file = 'daily_nav_etf.csv'
        cb_file  = 'daily_nav_cb.csv'
        print('使用默认文件名: %s, %s' % (etf_file, cb_file))
        print('可指定: python merge_three_engine.py <etf_csv> <cb_csv>')

    etf = load_nav(etf_file)
    cb  = load_nav(cb_file)
    merged = merge(etf, cb)
    merged = report(merged)

    output = 'combined_three_engine_nav.csv'
    merged.to_csv(output, index=False)
    print('合并净值已写入: %s' % output)
