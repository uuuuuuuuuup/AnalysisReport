# -*- coding: utf-8 -*-
# ============================================================
# 小盘股反转策略 - 测试集诊断
# ============================================================
# 目的: 不调参数, 只看数据, 理解策略在测试集发生了什么
#   1. 因子IC在测试集是否衰减?
#   2. 2024年微盘踩踏期间策略具体怎么亏的?
#   3. 动量确认在测试集过滤了多少标的?
#   4. 市场择时在测试集触发了多少次?
#   5. 分年度/分月度收益分解
# ============================================================

import dai
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# 参数（与策略一致）
REVERSAL_PERIOD = 20
MOMENTUM_PERIOD = 5
VOLATILITY_PERIOD = 20
TURNOVER_PERIOD = 20
MIN_LIST_DAYS = 60
CAP_PERCENTILE = 0.30

MARKET_WEAK_THRESHOLD = -0.05
MARKET_CRASH_THRESHOLD = -0.10
MARKET_LOOKBACK = 20

TRAIN_START = '2019-01-01'
TRAIN_END = '2023-12-31'
TEST_START = '2024-01-01'
TEST_END = '2026-07-29'


# ============================================================
# 加载数据
# ============================================================
print('加载数据...')
sql = """
SELECT
    p.date, p.instrument, p.close, p.volume,
    p.turn AS turnover_ratio,
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
    AND f.list_days >= %d
    AND f.list_sector NOT IN (3, 4)
ORDER BY p.date, p.instrument
""" % MIN_LIST_DAYS

df = dai.query(sql, filters={"date": [TEST_START, TEST_END]}).df()
df['date'] = pd.to_datetime(df['date'])
print('数据: %d 行, %d 标的' % (len(df), df['instrument'].nunique()))


# ============================================================
# 因子计算
# ============================================================
print('计算因子...')
grouped = df.groupby('instrument')

df['reversal'] = grouped['close'].transform(
    lambda x: -(x / x.shift(REVERSAL_PERIOD) - 1)
)
df['momentum'] = grouped['close'].transform(
    lambda x: x / x.shift(MOMENTUM_PERIOD) - 1
)
df['daily_ret'] = grouped['close'].transform(lambda x: x.pct_change())
df['volatility'] = grouped['daily_ret'].transform(
    lambda x: -x.rolling(VOLATILITY_PERIOD, min_periods=10).std()
)
df['turnover'] = grouped['turnover_ratio'].transform(
    lambda x: -x.rolling(TURNOVER_PERIOD, min_periods=10).mean()
)
df['forward_ret_5d'] = grouped['close'].transform(lambda x: x.shift(-5) / x - 1)
df['cap_rank'] = df.groupby('date')['circulating_market_cap'].transform(
    lambda x: x.rank(pct=True, na_option='keep')
)


# ============================================================
# 诊断1: 因子IC在测试集的衰减
# ============================================================
print('\n' + '=' * 70)
print('诊断1: 因子IC衰减（训练集 vs 测试集）')
print('=' * 70)

from scipy.stats import spearmanr

dates = sorted(df['date'].unique())
# 每月取一个截面
monthly_dates = pd.Series(dates).groupby(
    pd.Series(dates).apply(lambda x: x.strftime('%Y-%m'))
).last().tolist()

factors = ['reversal', 'turnover', 'volatility']

for factor in factors:
    ic_list = []
    for d in monthly_dates:
        cur = df[(df['date'] == d) & (df['cap_rank'] <= CAP_PERCENTILE)]
        cur = cur.dropna(subset=[factor, 'forward_ret_5d'])
        if len(cur) < 50:
            continue
        ic, _ = spearmanr(cur[factor], cur['forward_ret_5d'])
        ic_list.append(ic)

    avg_ic = np.mean(ic_list)
    icir = np.mean(ic_list) / np.std(ic_list) if np.std(ic_list) > 0 else 0
    ic_pos = np.mean([1 for x in ic_list if x > 0])

    print('  %-12s  IC均值 %+.4f  ICIR %+.2f  IC>0占比 %.0f%%'
          % (factor, avg_ic, icir, ic_pos * 100))

# 分年度IC
print('\n  分年度IC:')
for year in [2024, 2025, 2026]:
    year_dates = [d for d in monthly_dates if d.year == year]
    if not year_dates:
        continue
    for factor in factors:
        ic_list = []
        for d in year_dates:
            cur = df[(df['date'] == d) & (df['cap_rank'] <= CAP_PERCENTILE)]
            cur = cur.dropna(subset=[factor, 'forward_ret_5d'])
            if len(cur) < 50:
                continue
            ic, _ = spearmanr(cur[factor], cur['forward_ret_5d'])
            ic_list.append(ic)
        avg_ic = np.mean(ic_list) if ic_list else 0
        print('    %d  %-12s  IC %+.4f  (n=%d)' % (year, factor, avg_ic, len(ic_list)))


# ============================================================
# 诊断2: 动量确认过滤效果
# ============================================================
print('\n' + '=' * 70)
print('诊断2: 动量确认过滤了多少标的?')
print('=' * 70)

# 每月统计
for year in [2024, 2025, 2026]:
    year_dates = [d for d in monthly_dates if d.year == year]
    if not year_dates:
        continue
    total_before = 0
    total_after = 0
    for d in year_dates:
        cur = df[(df['date'] == d) & (df['cap_rank'] <= CAP_PERCENTILE)]
        cur = cur.dropna(subset=['reversal', 'momentum'])
        before = len(cur)
        after = len(cur[cur['momentum'] > 0])
        total_before += before
        total_after += after
    avg_before = total_before / len(year_dates)
    avg_after = total_after / len(year_dates)
    filter_pct = 1 - avg_after / avg_before if avg_before > 0 else 0
    print('  %d: 小市值池平均 %.0f 只 → 动量确认后 %.0f 只 (过滤 %.0f%%)'
          % (year, avg_before, avg_after, filter_pct * 100))


# ============================================================
# 诊断3: 市场择时触发统计
# ============================================================
print('\n' + '=' * 70)
print('诊断3: 市场择时触发情况')
print('=' * 70)

daily_market_ret = df.groupby('date')['daily_ret'].mean()
market_cumret = (1 + daily_market_ret).cumprod()
market_dates_arr = market_cumret.index.tolist()

trigger_events = []
for i, d in enumerate(market_dates_arr):
    if i < MARKET_LOOKBACK:
        continue
    bm_ret = market_cumret.iloc[i] / market_cumret.iloc[i - MARKET_LOOKBACK] - 1
    if bm_ret < MARKET_CRASH_THRESHOLD:
        trigger_events.append((d, 'crash', bm_ret))
    elif bm_ret < MARKET_WEAK_THRESHOLD:
        trigger_events.append((d, 'weak', bm_ret))

print('  弱市触发(20日收益<-5%%): %d 次' % len([e for e in trigger_events if e[1] == 'weak']))
print('  崩盘触发(20日收益<-10%%): %d 次' % len([e for e in trigger_events if e[1] == 'crash']))

if trigger_events:
    print('\n  触发时间线:')
    for d, regime, ret in trigger_events[:20]:
        print('    %s  %s  20日收益 %+.1f%%' % (d.strftime('%Y-%m-%d'), regime, ret * 100))
    if len(trigger_events) > 20:
        print('    ... 共%d次' % len(trigger_events))


# ============================================================
# 诊断4: 2024年1-3月详细分解
# ============================================================
print('\n' + '=' * 70)
print('诊断4: 2024年1-3月逐周收益分解')
print('=' * 70)

# 模拟策略在2024年1-3月的逐日收益
price_matrix = df.pivot(index='date', columns='instrument', values='close')
all_dates_2024 = [d for d in sorted(price_matrix.index) if d >= pd.Timestamp('2024-01-01') and d <= pd.Timestamp('2024-03-31')]

if all_dates_2024:
    nav = 1.0
    holdings = {}
    day_count = 0

    for i, date in enumerate(all_dates_2024):
        day_count += 1
        should_rebalance = (day_count % 10 == 0)  # 双周

        if should_rebalance:
            cur = df[df['date'] == date].copy()
            cur = cur[cur['cap_rank'] <= CAP_PERCENTILE]
            cur = cur[cur['momentum'] > 0]
            cur = cur.dropna(subset=['reversal', 'volatility', 'turnover'])

            if len(cur) >= 20:
                for col in ['reversal', 'volatility', 'turnover']:
                    s = cur[col]
                    mean, std = s.mean(), s.std()
                    cur[col + '_z'] = (s - mean) / std if std > 0 else 0.0
                cur['score'] = 0.5 * cur['reversal_z'] + 0.25 * cur['turnover_z'] + 0.25 * cur['volatility_z']
                cur = cur.sort_values('score', ascending=False)
                selected = cur.head(20)['instrument'].tolist()
                holdings = {s: 1.0/20 for s in selected}

        # 计算日收益
        if holdings and i > 0:
            prev_date = all_dates_2024[i - 1]
            daily_ret = 0
            for inst, w in holdings.items():
                if inst in price_matrix.columns:
                    cp = price_matrix.loc[date, inst] if date in price_matrix.index else np.nan
                    pp = price_matrix.loc[prev_date, inst] if prev_date in price_matrix.index else np.nan
                    if not pd.isna(cp) and not pd.isna(pp) and pp > 0:
                        daily_ret += (cp / pp - 1) * w
            nav *= (1 + daily_ret)

        # 每周五打印
        if date.weekday() == 4:
            print('  %s  NAV %.4f  持仓%d只' % (date.strftime('%Y-%m-%d'), nav, len(holdings)))

    print('\n  2024Q1期末NAV: %.4f (收益 %+.1f%%)' % (nav, (nav - 1) * 100))


# ============================================================
# 诊断5: 反转选出的标的在测试集的实际表现
# ============================================================
print('\n' + '=' * 70)
print('诊断5: 反转选股的实际5日收益分布')
print('=' * 70)

# 每月选股, 看实际5日收益
for year in [2024, 2025, 2026]:
    year_dates = [d for d in monthly_dates if d.year == year]
    if not year_dates:
        continue

    selected_returns = []
    for d in year_dates:
        cur = df[(df['date'] == d) & (df['cap_rank'] <= CAP_PERCENTILE)]
        cur = cur[cur['momentum'] > 0]
        cur = cur.dropna(subset=['reversal', 'volatility', 'turnover', 'forward_ret_5d'])
        if len(cur) < 20:
            continue
        for col in ['reversal', 'volatility', 'turnover']:
            s = cur[col]
            mean, std = s.mean(), s.std()
            cur[col + '_z'] = (s - mean) / std if std > 0 else 0.0
        cur['score'] = 0.5 * cur['reversal_z'] + 0.25 * cur['turnover_z'] + 0.25 * cur['volatility_z']
        cur = cur.sort_values('score', ascending=False)
        top20 = cur.head(20)
        selected_returns.extend(top20['forward_ret_5d'].tolist())

    if selected_returns:
        avg_ret = np.mean(selected_returns)
        win = np.mean([1 for r in selected_returns if r > 0])
        print('  %d: 选股5日平均收益 %+.2f%%  胜率 %.0f%%  (n=%d)'
              % (year, avg_ret * 100, win * 100, len(selected_returns)))


# ============================================================
# 诊断6: 与训练集对比
# ============================================================
print('\n' + '=' * 70)
print('诊断6: 训练集 vs 测试集 关键指标对比')
print('=' * 70)

# 训练集IC（简要）
print('  加载训练集数据计算IC...')
df_train = dai.query(sql, filters={"date": [TRAIN_START, TRAIN_END]}).df()
df_train['date'] = pd.to_datetime(df_train['date'])

grouped_t = df_train.groupby('instrument')
df_train['reversal'] = grouped_t['close'].transform(lambda x: -(x / x.shift(REVERSAL_PERIOD) - 1))
df_train['daily_ret'] = grouped_t['close'].transform(lambda x: x.pct_change())
df_train['volatility'] = grouped_t['daily_ret'].transform(lambda x: -x.rolling(VOLATILITY_PERIOD, min_periods=10).std())
df_train['turnover'] = grouped_t['turnover_ratio'].transform(lambda x: -x.rolling(TURNOVER_PERIOD, min_periods=10).mean())
df_train['forward_ret_5d'] = grouped_t['close'].transform(lambda x: x.shift(-5) / x - 1)
df_train['cap_rank'] = df_train.groupby('date')['circulating_market_cap'].transform(lambda x: x.rank(pct=True, na_option='keep'))

train_dates = sorted(df_train['date'].unique())
train_monthly = pd.Series(train_dates).groupby(
    pd.Series(train_dates).apply(lambda x: x.strftime('%Y-%m'))
).last().tolist()

print('\n  因子IC对比:')
print('  %-12s  %12s  %12s' % ('因子', '训练集IC', '测试集IC'))
for factor in factors:
    # 训练集IC
    ic_train = []
    for d in train_monthly:
        cur = df_train[(df_train['date'] == d) & (df_train['cap_rank'] <= CAP_PERCENTILE)]
        cur = cur.dropna(subset=[factor, 'forward_ret_5d'])
        if len(cur) < 50:
            continue
        ic, _ = spearmanr(cur[factor], cur['forward_ret_5d'])
        ic_train.append(ic)

    # 测试集IC
    ic_test = []
    for d in monthly_dates:
        cur = df[(df['date'] == d) & (df['cap_rank'] <= CAP_PERCENTILE)]
        cur = cur.dropna(subset=[factor, 'forward_ret_5d'])
        if len(cur) < 50:
            continue
        ic, _ = spearmanr(cur[factor], cur['forward_ret_5d'])
        ic_test.append(ic)

    avg_train = np.mean(ic_train) if ic_train else 0
    avg_test = np.mean(ic_test) if ic_test else 0
    decay_pct = (avg_test - avg_train) / abs(avg_train) * 100 if avg_train != 0 else 0

    print('  %-12s  %+12.4f  %+12.4f  (衰减 %+.0f%%)' % (factor, avg_train, avg_test, decay_pct))


print('\n诊断完成。')
