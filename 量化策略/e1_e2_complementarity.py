# -*- coding: utf-8 -*-
# ============================================================
# E1-E2 信号互补性验证 (BigQuant Notebook)
# ============================================================
# ETF 数据源: cn_fund_bar1d (不是 cn_stock_bar1d!)
# CB  数据源: cn_cbond_bar1d_te
# ============================================================

import dai
import pandas as pd
import numpy as np

ETF_LIST = ['510300.SH', '510500.SH', '159915.SZ',
            '510880.SH', '513100.SH', '518880.SH']
ETF_SAFE = '511010.SH'
ETF_K = 6
ETF_M = 2

START = '2015-10-01'
END   = '2026-07-29'


# ============================================================
# 1. 拉取 ETF 日线 — cn_fund_bar1d, 分批查询
# ============================================================
print('拉取 ETF 数据...')
# 半年一批 (180天查询已验证可行)
etf_parts = []
for year in range(2015, 2027):
    for half, (m1, m2) in enumerate([(1, 6), (7, 12)]):
        d1 = '%d-%02d-01' % (year, m1)
        d2 = '%d-%02d-01' % (year + (1 if m2 == 12 else 0),
                             1 if m2 == 12 else m2 + 1)
        # end date 不能超过 END
        if d2 > END:
            d2 = END
        if d1 >= d2 or d1 > END:
            continue

        try:
            part = dai.query("""
                SELECT date, instrument, close
                FROM cn_fund_bar1d
                ORDER BY date
            """, filters={"date": [d1, d2]}).df()

            if len(part) > 0:
                part = part[part['instrument'].isin(ETF_LIST + [ETF_SAFE])]
                if len(part) > 0:
                    etf_parts.append(part)
        except Exception as e:
            print('  [跳过] %s~%s: %s' % (d1, d2, str(e)[:60]))

if not etf_parts:
    raise RuntimeError('cn_fund_bar1d 无数据!')

etf_df = pd.concat(etf_parts, ignore_index=True)
etf_df['date'] = pd.to_datetime(etf_df['date'])
etf_df = etf_df.sort_values(['date', 'instrument']).reset_index(drop=True)
print('ETF: %d 行, %d 标的, %s ~ %s' % (len(etf_df),
      etf_df['instrument'].nunique(),
      etf_df['date'].min().strftime('%Y-%m-%d'),
      etf_df['date'].max().strftime('%Y-%m-%d')))

# 标的上市日期
for s in ETF_LIST + [ETF_SAFE]:
    sub = etf_df[etf_df['instrument'] == s]
    if len(sub) > 0:
        print('  %s: %s ~ %s (%d行)' % (s,
              sub['date'].min().strftime('%Y-%m-%d'),
              sub['date'].max().strftime('%Y-%m-%d'), len(sub)))


# ============================================================
# 2. 拉取可转债日线
# ============================================================
print('\n拉取可转债数据...')
cb_df = dai.query("""
    SELECT a.date, a.instrument, a.close, a.cb_over_rate AS premium_rate,
           b.maturity_date, b.list_date
    FROM cn_cbond_bar1d_te a
    INNER JOIN cn_cbond_basic_info b ON a.instrument = b.instrument
    WHERE a.date >= '%s' AND a.date <= '%s'
      AND a.close > 0 AND b.maturity_date IS NOT NULL
    ORDER BY a.date, a.instrument
""" % (START, END)).df()
cb_df['date'] = pd.to_datetime(cb_df['date'])
cb_df['maturity_date'] = pd.to_datetime(cb_df['maturity_date'])
cb_df['list_date'] = pd.to_datetime(cb_df['list_date'])
print('CB: %d 行, %d 标的, %s ~ %s' % (len(cb_df),
      cb_df['instrument'].nunique(),
      cb_df['date'].min().strftime('%Y-%m-%d'),
      cb_df['date'].max().strftime('%Y-%m-%d')))


# ============================================================
# 3. 月度调仓日
# ============================================================
all_dates = sorted(set(etf_df['date'].unique()) | set(cb_df['date'].unique()))
all_dates = pd.to_datetime(all_dates)

months = pd.Series(all_dates).dt.to_period('M').unique()
month_ends = sorted([max(all_dates[pd.Series(all_dates).dt.to_period('M') == m])
                      for m in months])

monthly = pd.DataFrame({'date': month_ends})
print('\n月度区间: %s ~ %s (%d 个月)'
      % (monthly['date'].iloc[0].strftime('%Y-%m'),
         monthly['date'].iloc[-1].strftime('%Y-%m'), len(monthly)))


# ============================================================
# 4. ETF 月末价格映射 (用于动量)
# ============================================================
etf_df['ym'] = etf_df['date'].dt.strftime('%Y-%m')
etf_me = etf_df.groupby(['ym', 'instrument'])['close'].last().reset_index()

etf_monthly = {}
for s in ETF_LIST:
    me = etf_me[etf_me['instrument'] == s].set_index('ym')['close']
    etf_monthly[s] = me.sort_index()


# ============================================================
# 5. E1 动量广度 + E1 持仓收益
# ============================================================
print('计算 E1 动量广度 & 收益...')

def e1_analysis(target_date):
    """返回 (动量广度, E1组合下月收益)。"""
    today_ym = target_date.strftime('%Y-%m')

    mom = {}
    for s in ETF_LIST:
        mask = (etf_df['instrument'] == s) & (etf_df['date'] == target_date)
        cur = etf_df[mask]
        if len(cur) == 0:
            continue
        px = cur['close'].iloc[0]
        if px <= 0:
            continue
        me = etf_monthly.get(s)
        if me is None:
            continue
        prior = me[me.index < today_ym]
        if len(prior) < ETF_K:
            continue
        base = prior.iloc[-ETF_K]
        if pd.isna(base) or base <= 0:
            continue
        mom[s] = px / base - 1

    breadth = sum(1 for v in mom.values() if v > 0)

    if len(mom) < 2:
        return breadth, None

    ranked = sorted(mom.items(), key=lambda kv: kv[1], reverse=True)
    picks = [s for s, m in ranked[:ETF_M] if m > 0]

    if not picks:
        return breadth, 0.02 / 12  # 全避险

    later = [d for d in month_ends if d > target_date]
    if not later:
        return breadth, None
    next_date = later[0]

    rets = []
    for s in picks:
        m0 = (etf_df['instrument'] == s) & (etf_df['date'] == target_date)
        m1 = (etf_df['instrument'] == s) & (etf_df['date'] == next_date)
        if m0.any() and m1.any():
            rets.append(etf_df[m1]['close'].iloc[0] / etf_df[m0]['close'].iloc[0] - 1)

    return breadth, (np.mean(rets) if rets else None)


results = {}
for _, row in monthly.iterrows():
    b, r = e1_analysis(row['date'])
    results[row['date']] = (b, r)

monthly['e1_breadth'] = monthly['date'].apply(lambda d: results.get(d, (None, None))[0])
monthly['e1_ret']     = monthly['date'].apply(lambda d: results.get(d, (None, None))[1])


# ============================================================
# 6. E2 双低组合收益
# ============================================================
print('计算 E2 月度收益...')

N_HOLD = 20

def calc_e2_return(target_date):
    cur = cb_df[cb_df['date'] == target_date].copy()
    if len(cur) < N_HOLD:
        return None
    cur['days_listed'] = (target_date - cur['list_date']).dt.days
    cur['months_to_mat'] = (cur['maturity_date'] - target_date).dt.days / 30.0
    cur = cur[(cur['days_listed'] >= 30) & (cur['months_to_mat'] >= 12)]
    if len(cur) < N_HOLD:
        return None
    cur = cur[~((cur['close'] < 80) & (cur['premium_rate'] > 100))]
    if len(cur) < N_HOLD:
        return None
    for col in ['close', 'premium_rate']:
        s = cur[col]
        m, std = s.mean(), s.std()
        cur[col + '_z'] = -(s - m) / std if std > 0 else 0
    cur['score'] = 0.5 * cur['close_z'] + 0.5 * cur['premium_rate_z']
    selected = cur.sort_values('score', ascending=False).head(N_HOLD)['instrument'].tolist()

    later = [d for d in month_ends if d > target_date]
    if not later:
        return None
    next_date = later[0]

    rets = []
    for inst in selected:
        m0 = (cb_df['instrument'] == inst) & (cb_df['date'] == target_date)
        m1 = (cb_df['instrument'] == inst) & (cb_df['date'] == next_date)
        if m0.any() and m1.any():
            p0, p1 = cb_df[m0]['close'].iloc[0], cb_df[m1]['close'].iloc[0]
            if p0 > 0:
                rets.append(p1 / p0 - 1)
    return np.mean(rets) if len(rets) >= N_HOLD * 0.5 else None

e2_rets = {}
for _, row in monthly.iterrows():
    r = calc_e2_return(row['date'])
    if r is not None:
        e2_rets[row['date']] = r
monthly['e2_ret'] = monthly['date'].map(e2_rets)


# ============================================================
# 7. 分析
# ============================================================
valid = monthly.dropna(subset=['e1_breadth', 'e1_ret', 'e2_ret']).copy()
print('\n有效月份: %d (两引擎均有数据)' % len(valid))

# --- 动量广度分布 ---
print('\n' + '=' * 60)
print('E1 动量广度分布 (%d 个月)' % len(valid))
print('=' * 60)
bc = valid['e1_breadth'].value_counts().sort_index()
for b, c in bc.items():
    print('  广度=%d: %d 个月 (%.0f%%)' % (b, c, c / len(valid) * 100))

# --- 核心: E2 按 E1 状态分组 ---
off = valid[valid['e1_breadth'] <= 1]
on  = valid[valid['e1_breadth'] >= 2]

print('\n' + '=' * 60)
print('★★★ 核心: E2 收益按 E1 状态分组 ★★★')
print('=' * 60)
for label, sub in [('E1 熄火 (广度≤1)', off), ('E1 活跃 (广度≥2)', on)]:
    if len(sub) == 0:
        print('\n%s: 0 个月' % label)
        continue
    print('\n%s: %d 个月 (%.0f%%)' % (label, len(sub), len(sub) / len(valid) * 100))
    for eng, col in [('E2(可转债)', 'e2_ret'), ('E1(ETF动量)', 'e1_ret')]:
        m = sub[col].mean()
        a = (1 + m) ** 12 - 1
        w = (sub[col] > 0).mean()
        v = sub[col].std()
        print('  %s: 月均 %+.2f%%  年化 %+.1f%%  胜率 %.0f%%  月波 %.1f%%'
              % (eng, m * 100, a * 100, w * 100, v * 100))

if len(off) > 0 and len(on) > 0:
    diff_e2 = off['e2_ret'].mean() - on['e2_ret'].mean()
    diff_e1 = off['e1_ret'].mean() - on['e1_ret'].mean()
    print('\n★ 熄火期 - 活跃期差异:')
    print('  E2: %+.2f%%/月 (%+.1f%%/年)' % (diff_e2 * 100, diff_e2 * 12 * 100))
    print('  E1: %+.2f%%/月 (%+.1f%%/年)' % (diff_e1 * 100, diff_e1 * 12 * 100))

# --- 相关性 ---
print('\n' + '=' * 60)
print('相关性矩阵')
print('=' * 60)
print(valid[['e1_breadth', 'e1_ret', 'e2_ret']].corr().round(3).to_string())

# --- 信号切换 ---
print('\n' + '=' * 60)
print('信号切换统计')
print('=' * 60)
valid['regime'] = valid['e1_breadth'].apply(lambda x: 'OFF' if x <= 1 else 'ON')
n_switches = (valid['regime'] != valid['regime'].shift()).sum()
print('ON  %d月 (%.0f%%), OFF %d月 (%.0f%%), 切换 %d次'
      % ((valid['regime'] == 'ON').sum(),
         (valid['regime'] == 'ON').mean() * 100,
         (valid['regime'] == 'OFF').sum(),
         (valid['regime'] == 'OFF').mean() * 100,
         n_switches))

# 连续OFF长度
streaks, cur = [], 0
for _, row in valid.iterrows():
    if row['regime'] == 'OFF': cur += 1
    else:
        if cur > 0: streaks.append(cur)
        cur = 0
if cur > 0: streaks.append(cur)
if streaks:
    print('OFF连续: 最短%d月  最长%d月  均值%.1f月' % (min(streaks), max(streaks), np.mean(streaks)))

# --- 策略对比 ---
print('\n' + '=' * 60)
print('策略模拟: 固定 35/35/30 vs 切换 (E1 OFF → E2 70%%)')
print('=' * 60)

e3_m = 0.05 / 12  # E3 年化~5%

valid['fixed']  = 0.35 * valid['e1_ret'] + 0.35 * valid['e2_ret'] + 0.30 * e3_m
valid['switch'] = 0.30 * e3_m
for i, row in valid.iterrows():
    valid.at[i, 'switch'] += 0.70 * row['e2_ret'] if row['regime'] == 'OFF' \
                         else 0.35 * row['e1_ret'] + 0.35 * row['e2_ret']

def metrics(rets, label):
    cum  = (1 + pd.Series(rets)).cumprod()
    tot  = cum.iloc[-1] - 1
    ann  = (1 + tot) ** (12 / len(rets)) - 1
    vol  = np.std(rets) * np.sqrt(12)
    sr   = np.mean(rets) / np.std(rets) * np.sqrt(12) if np.std(rets) > 0 else 0
    dd   = (cum / cum.cummax() - 1).min()
    print('%s: 累计%+.1f%%  年化%+.1f%%  波动%.1f%%  夏普%.2f  回撤%.1f%%'
          % (label, tot * 100, ann * 100, vol * 100, sr, dd * 100))

metrics(valid['fixed'].values,  '固定 35/35/30')
metrics(valid['switch'].values, '切换 E1OFF→E2')

print('\n===== 完成 =====')
