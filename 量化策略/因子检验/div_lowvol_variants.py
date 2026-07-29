# -*- coding: utf-8 -*-
"""
Engine 3 替代方案验证: 纯高股息 + 质量过滤
============================================
基于前面已取的数据（close_tbl, monthly_ret, fwd_ret），
新增 ROE 过滤，对比多种变体。

⛔ 仅训练集 (≤ 2022-12-31)
"""

import dai
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

# 复用前面的变量（从已运行的 notebook cell 继承）
# close_tbl, monthly_ret, fwd_ret, rebal_days, pool_stocks
# dp_factor, vol_factor, combined_factor

TRAIN_END_DATE = '2022-12-31'
W_DP = 0.50
W_VOL = 0.50

# ============================================================
# 1. 获取 ROE 数据
# ============================================================
print('=' * 60)
print('1. 获取 ROE')
print('=' * 60)

# 方法: 从 cn_stock_valuation_v6 取 PB 和 PE_ttm → ROE ≈ PB / PE_ttm
# 优点: 同一张表，已有 filters 模式；缺点: 会计科目不完全匹配，做质量过滤够用
print('从 PB/PE_ttm 反推 ROE ...')

roe_data = {}
dates_for_roe = sorted(set(rebal_days) & set([d for d in rebal_days if d >= '2015-06-01']))

for i, d in enumerate(dates_for_roe):
    try:
        df = dai.query(
            "SELECT instrument, pb, pe_ttm FROM cn_stock_valuation_v6",
            filters={"date": [d]}
        ).df()
        if df.empty:
            continue
        # ROE ≈ PB / PE_ttm (PE_ttm > 0 才有意义)
        df = df[(df['pb'] > 0) & (df['pe_ttm'] > 0)]
        df['roe_est'] = df['pb'] / df['pe_ttm']
        # 过滤极端值
        df = df[(df['roe_est'] > 0) & (df['roe_est'] < 1.0)]
        if not df.empty:
            df['date'] = d
            roe_data[d] = df[['date', 'instrument', 'roe_est']].set_index('instrument')
    except Exception:
        pass
    if i % 24 == 0:
        print(f'  roe {d}: {len(roe_data.get(d, pd.DataFrame()))} 条 (已取{i+1}期)')

if roe_data:
    roe_tbl = pd.DataFrame({d: roe_data[d]['roe_est'] for d in roe_data}).T
    print(f'ROE 估算: {roe_tbl.shape}')
    roe_valid = roe_tbl.notna().sum(axis=1)
    print(f'每期有效数: min={roe_valid.min()}  max={roe_valid.max()}  median={int(roe_valid.median())}')
    print(f'ROE 分布: mean={roe_tbl.stack().mean():.3f}  median={roe_tbl.stack().median():.3f}')
else:
    print('⚠️ ROE 数据为空')
    roe_tbl = pd.DataFrame()


# ============================================================
# 2. 构建各变体因子
# ============================================================
print('\n' + '=' * 60)
print('2. 构建变体因子')
print('=' * 60)


def winsorize_mad(s, n_mad=5):
    med = s.median()
    mad = (s - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return s
    return s.clip(med - n_mad * 1.4826 * mad, med + n_mad * 1.4826 * mad)


def zscore(s):
    sd = s.std()
    if not sd or np.isnan(sd):
        return s * 0.0
    return (s - s.mean()) / sd


# ---- 变体1: 纯高股息 (dp-only) ----
# 已有 dp_factor

# ---- 变体2: 高股息 + ROE>0 (排除亏损股) ----
dp_roe_positive = {}
for d in dp_factor.index:
    if d > TRAIN_END_DATE:
        break
    dp_s = dp_factor.loc[d].dropna()
    if d in roe_tbl.index:
        roe_s = roe_tbl.loc[d].dropna()
        valid_codes = roe_s[roe_s > 0].index  # ROE > 0
        dp_s = dp_s[dp_s.index.isin(valid_codes)]
    if len(dp_s) >= 30:
        dp_roe_positive[d] = dp_s
dp_roe_positive = pd.DataFrame(dp_roe_positive).T
print(f'变体2 (dp + ROE>0): {dp_roe_positive.shape}')

# ---- 变体3: 高股息 + 高ROE (ROE > 截面中位数) ----
dp_roe_high = {}
for d in dp_factor.index:
    if d > TRAIN_END_DATE:
        break
    dp_s = dp_factor.loc[d].dropna()
    if d in roe_tbl.index:
        roe_s = roe_tbl.loc[d].dropna()
        median_roe = roe_s.median()
        high_roe = roe_s[roe_s > median_roe].index
        dp_s = dp_s[dp_s.index.isin(high_roe)]
    if len(dp_s) >= 30:
        dp_roe_high[d] = dp_s
dp_roe_high = pd.DataFrame(dp_roe_high).T
print(f'变体3 (dp + ROE>中位): {dp_roe_high.shape}')

# ---- 变体4: 高股息 + 剔除ROE最差的20%（软过滤） ----
dp_roe_soft = {}
for d in dp_factor.index:
    if d > TRAIN_END_DATE:
        break
    dp_s = dp_factor.loc[d].dropna()
    if d in roe_tbl.index:
        roe_s = roe_tbl.loc[d].dropna()
        bottom_cutoff = roe_s.quantile(0.20)
        keep = roe_s[roe_s >= bottom_cutoff].index
        dp_s = dp_s[dp_s.index.isin(keep)]
    if len(dp_s) >= 30:
        dp_roe_soft[d] = dp_s
dp_roe_soft = pd.DataFrame(dp_roe_soft).T
print(f'变体4 (dp + 剔除ROE末20%): {dp_roe_soft.shape}')

# ---- 对照: dp + vol (原方案) ----
# 已有 combined_factor

# ---- 对照: 等权全池 ----
# 已有 monthly_ret


# ============================================================
# 3. 统一评估
# ============================================================
print('\n' + '=' * 60)
print('3. 变体对比 (训练集, N=20)')
print('=' * 60)


def filter_train(factor_df):
    dates = [d for d in factor_df.index if d <= TRAIN_END_DATE]
    return factor_df.loc[dates]


def simulate(factor_df, n_hold):
    factor_df = filter_train(factor_df)
    monthly_rets = {}
    all_rets = {}
    for d in factor_df.index:
        if d not in fwd_ret.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < n_hold * 2:
            continue
        top_n = f_s[common].nlargest(n_hold).index
        rets = r_s[top_n].dropna()
        if len(rets) >= n_hold * 0.5:
            monthly_rets[d] = rets.mean()
        all_rets[d] = r_s.mean()
    return pd.Series(monthly_rets), pd.Series(all_rets)


def stats(monthly_ret, benchmark=None):
    if len(monthly_ret) < 6:
        return {}
    ann = monthly_ret.mean() * 12
    vol = monthly_ret.std() * np.sqrt(12)
    s = ann / vol if vol > 0 else 0
    dd = (monthly_ret.cumsum() - monthly_ret.cumsum().cummax()).min()
    wr = (monthly_ret > 0).mean()
    r = {'年化%': ann*100, '夏普': s, '波动%': vol*100, '回撤%': dd*100,
         '月胜率': wr*100, '月数': len(monthly_ret)}
    if benchmark is not None and len(benchmark) > 0:
        ci = monthly_ret.index.intersection(benchmark.index)
        if len(ci) > 0:
            ex = monthly_ret[ci] - benchmark[ci]
            r['超额%'] = ex.mean()*12*100
            r['IR'] = ex.mean()/ex.std()*np.sqrt(12) if ex.std() > 0 else 0
    return r


# 等权基准
bench_ret = monthly_ret.mean(axis=1)
bench_ret = bench_ret[bench_ret.index <= TRAIN_END_DATE]

variants = [
    ('纯高股息(dp-only)',    dp_factor),
    ('dp + ROE>0',           dp_roe_positive),
    ('dp + ROE>中位',         dp_roe_high),
    ('dp + 剔ROE末20%',       dp_roe_soft),
    ('dp+vol(原方案对照)',     combined_factor),
]

results = []
for name, factor_df in variants:
    # 尝试 N=20 和 N=30
    for n in [20, 30]:
        ret, _ = simulate(factor_df, n)
        s = stats(ret, bench_ret)
        s['变体'] = name
        s['N'] = n
        results.append(s)

result_df = pd.DataFrame(results)
print(result_df[['变体', 'N', '年化%', '夏普', '回撤%', '月胜率', '月数']].to_string(index=False))


# ============================================================
# 4. 最佳变体的深入分析
# ============================================================
print('\n' + '=' * 60)
print('4. 最优变体深入分析')
print('=' * 60)

# 找到夏普最高的变体
best_sharpe = -999
best_config = None
for r in results:
    if r['夏普'] > best_sharpe:
        best_sharpe = r['夏普']
        best_config = (r['变体'], r['N'])

best_name, best_n = best_config
print(f'夏普最高: {best_name}, N={best_n}')

# 跑分年度
best_factor = dict(variants)[best_name]
ret_best, _ = simulate(best_factor, best_n)
df = ret_best.reset_index()
df.columns = ['date', 'ret']
df['year'] = pd.to_datetime(df['date']).dt.year

print('\n分年度:')
for yr, grp in df.groupby('year'):
    cum = (1 + grp['ret']).prod() - 1
    bar = '█' * max(0, int(cum*100/5)) if cum >= 0 else '░' * max(0, int(-cum*100/3))
    print(f'  {yr}  {cum:+6.1f}%  {bar}')

s = stats(ret_best, bench_ret)
print(f'\n训练集: 年化{s["年化%"]:.1f}%  夏普{s["夏普"]:.2f}  '
      f'波动{s["波动%"]:.1f}%  回撤{s["回撤%"]:.1f}%'
      f'  月胜率{s["月胜率"]:.1f}%  {s["月数"]}月')

# 前后段
mid = '2019-01-01'
pre = ret_best[ret_best.index <= mid]
post = ret_best[ret_best.index > mid]
if len(pre) >= 12 and len(post) >= 12:
    sp = stats(pre)
    so = stats(post)
    print(f'前半(<2019): 年化{sp["年化%"]:+.1f}%  夏普{sp["夏普"]:.2f}  回撤{sp["回撤%"]:.1f}%')
    print(f'后半(≥2019): 年化{so["年化%"]:+.1f}%  夏普{so["夏普"]:.2f}  回撤{so["回撤%"]:.1f}%')
    # 夏普差
    delta_sharpe = so['夏普'] - sp['夏普']
    print(f'前后夏普差: {delta_sharpe:+.2f}')


# ============================================================
# 5. 与三引擎的相关性预判
# ============================================================
print('\n' + '=' * 60)
print('5. 三引擎相关性预判')
print('=' * 60)

print(f'''
{best_name} (N={best_n}):
  年化 {s["年化%"]:.1f}%  夏普 {s["夏普"]:.2f}  回撤 {s["回撤%"]:.1f}%

与其他引擎的预期相关性:
  vs ETF双动量:     低 (趋势跟踪 vs 价值防守)
  vs 可转债双低:     低 (转债定价 vs 股票股息)
  vs 中证1000增强:  中 (同属A股，但因子/池子完全不同)

{best_name} 赚的是"公司愿意分红、现金流真实"的钱，
亏钱场景: A股大牛市中跑输(股息股涨得慢)、利率上行期承压。
与 ETF 动量(牛市发力)和转债(利率敏感)的亏钱时间大概率错开。
''')

print('⛔ 以上全部来自训练集。测试集未被触碰。')
print('===== 验证完成 =====')
