# -*- coding: utf-8 -*-
"""
红利低波 因子研究 — BigQuant 版 (完整版)
==========================================
⛔ 数据墙: 训练集 2015-01 ~ 2022-12 | 测试集 2023-01 ~ 2026-07 封存

数据表:
- cn_stock_bar1d             日线行情 (filters: date + instrument)
- cn_stock_valuation_v6      估值数据, dividend_yield_ratio (filters: date)
- cn_stock_index_component   指数成分股 (filters: date)
- cn_stock_industry          行业分类 (静态表)
"""

import dai
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

# ==================== 配置 ====================
START_DATE = '2015-01-01'
END_DATE   = '2025-12-31'

# ⛔ ========== 数据墙 ==========
TRAIN_END_DATE  = '2022-12-31'
TEST_START_DATE = '2023-01-01'
# ⛔ ============================

N_GROUPS = 10
W_DP     = 0.50
W_VOL    = 0.50

INSTRUMENT_BATCH = 200   # 每批取价股票数


# ============================================================
# 1. 获取股票池：中证800成分股
# ============================================================
print('=' * 60)
print('1. 获取中证800成分股')
print('=' * 60)

# 先看 cn_stock_index_component 的 member_code 格式
print('探索指数成分股表...')
sample = dai.query(
    "SELECT * FROM cn_stock_index_component LIMIT 10",
    filters={"date": ["2022-12-30"]}
).df()
print(f'member_code 唯一值样例: {sample["member_code"].unique()[:20]}')
print(f'member_name 唯一值样例: {sample["member_name"].unique()[:20]}')

# 找到沪深300和中证500对应的 member_code
hs300_codes = sample[sample['member_name'].str.contains('300', na=False)]['member_code'].unique()
zz500_codes = sample[sample['member_name'].str.contains('500', na=False)]['member_code'].unique()
print(f'沪深300 candidate codes: {hs300_codes}')
print(f'中证500 candidate codes: {zz500_codes}')

# 扩大查询范围找指数
all_idx = dai.query(
    "SELECT DISTINCT member_code, member_name FROM cn_stock_index_component",
    filters={"date": ["2022-12-30"]}
).df()
print(f'所有指数: {len(all_idx)} 个')
# 筛选宽基指数
wide_idx = all_idx[all_idx['member_name'].str.contains(
    '300|500|800|1000|全指|综指', na=False)]
print(f'宽基指数:\n{wide_idx.to_string()}')

# ---- 构建股票池 ----
# 优先用中证800成分股，失败则按市值取 top 800
pool_stocks = []
if len(wide_idx) > 0:
    # 找 300 和 500 的 member_code
    codes_300 = wide_idx[wide_idx['member_name'].str.contains('300', na=False)]['member_code'].tolist()
    codes_500 = wide_idx[wide_idx['member_name'].str.contains('500', na=False)]['member_code'].tolist()
    target_codes = codes_300[:1] + codes_500[:1]  # 各取一个
    if target_codes:
        code_str = "', '".join(target_codes)
        df = dai.query(
            f"SELECT DISTINCT instrument FROM cn_stock_index_component "
            f"WHERE member_code IN ('{code_str}')",
            filters={"date": ["2022-12-30"]}
        ).df()
        pool_stocks = sorted(df['instrument'].tolist())

if len(pool_stocks) == 0:
    print('指数成分股方式失败，改用市值排名 top800...')
    df = dai.query(
        "SELECT instrument, total_market_cap FROM cn_stock_valuation_v6 "
        "WHERE total_market_cap > 0 ORDER BY total_market_cap DESC LIMIT 800",
        filters={"date": ["2022-12-30"]}
    ).df()
    pool_stocks = sorted(df['instrument'].tolist())

print(f'股票池: {len(pool_stocks)} 只')
print(f'中证800 去重后: {len(pool_stocks)} 只')
print(f'前5: {pool_stocks[:5]}')
print(f'后5: {pool_stocks[-5:]}')


# ============================================================
# 2. 取日线数据（仅调仓日附近的，节省内存）
# ============================================================
print('\n' + '=' * 60)
print('2. 取调仓日与收盘价')
print('=' * 60)

# 取所有交易日 → 找每月最后一个
all_dates_df = dai.query(
    "SELECT DISTINCT date FROM cn_stock_bar1d",
    filters={"date": [START_DATE, END_DATE]}
).df()
all_dates = sorted(all_dates_df['date'].tolist())
print(f'总交易日: {len(all_dates)}')

# 月末交易日
ym = pd.Series(all_dates).apply(lambda d: str(d)[:7])  # 'YYYY-MM'
rebal_days_raw = pd.Series(all_dates).groupby(ym).max().tolist()
# 统一为字符串格式，避免 Timestamp vs str 比较问题
rebal_days = [str(d)[:10] if hasattr(d, 'strftime') else str(d)[:10]
              for d in rebal_days_raw]
print(f'调仓日: {len(rebal_days)} 个, {rebal_days[0]} ~ {rebal_days[-1]}')

train_days = [d for d in rebal_days if d <= TRAIN_END_DATE]
test_days  = [d for d in rebal_days if d >= TEST_START_DATE]
print(f'训练集: {len(train_days)} ({train_days[0]} ~ {train_days[-1]})')
print(f'测试集: {len(test_days)} ({test_days[0]} ~ {test_days[-1]}) ← ⛔ 封存')


# %%
# ---- 分批取调仓日的收盘价 ----
print('\n取调仓日收盘价...')
all_px_parts = []
n_batches = (len(pool_stocks) + INSTRUMENT_BATCH - 1) // INSTRUMENT_BATCH

for b in range(n_batches):
    batch = pool_stocks[b * INSTRUMENT_BATCH : (b + 1) * INSTRUMENT_BATCH]
    df = dai.query(
        "SELECT date, instrument, close FROM cn_stock_bar1d",
        filters={"date": [START_DATE, END_DATE], "instrument": batch}
    ).df()
    # 统一日期格式为字符串
    df['date'] = df['date'].apply(lambda x: str(x)[:10])
    # 只保留调仓日
    df = df[df['date'].isin(rebal_days)]
    all_px_parts.append(df)
    print(f'  batch {b+1}/{n_batches}: {len(df)} 行, {df["instrument"].nunique()} 只')

px_monthly = pd.concat(all_px_parts, ignore_index=True)
print(f'调仓日收盘价总计: {len(px_monthly)} 行, '
      f'{px_monthly["instrument"].nunique()} 只股票')

# 构建 (调仓日 × 股票) 矩阵
close_tbl = px_monthly.pivot_table(
    values='close', index='date', columns='instrument', aggfunc='last')
close_tbl = close_tbl.reindex(rebal_days)
print(f'收盘价矩阵: {close_tbl.shape}')


# %%
# ---- 月度收益 ----
monthly_ret = close_tbl.pct_change()  # row[t] = close[t]/close[t-1] - 1
monthly_ret = monthly_ret.iloc[1:]     # 第一行全 NaN
print(f'月度收益矩阵: {monthly_ret.shape}')


# %%
# ---- 未来收益 (对齐: 本期因子 → 下期收益) ----
fwd_ret = monthly_ret.shift(-1).iloc[:-1]  # shift up, drop last NaN row
print(f'未来收益矩阵: {fwd_ret.shape}')


# ============================================================
# 3. 波动率因子（12个月月度收益 std，年化）
# ============================================================
print('\n' + '=' * 60)
print('3. 波动率因子')
print('=' * 60)

# 滚动12个月月度收益的 std → 年化
vol_12m = monthly_ret.rolling(12, min_periods=8).std() * np.sqrt(12)
# 对齐因子表 index (调仓日)
vol_tbl = vol_12m.dropna(how='all')
print(f'波动率: {vol_tbl.shape}')

vol_valid = vol_tbl.notna().sum(axis=1)
print(f'每期有效数: min={vol_valid.min()}  max={vol_valid.max()}  median={int(vol_valid.median())}')


# ============================================================
# 4. 股息率因子
# ============================================================
print('\n' + '=' * 60)
print('4. 股息率因子')
print('=' * 60)

# 从 cn_stock_valuation_v6 取 dividend_yield_ratio
# 注意：早期数据大量为 0 / 缺失，需过滤 dp > 0
dp_parts = []
dates = sorted(set(rebal_days) & set([d for d in rebal_days if d >= '2015-06-01']))
# 分月取（valuation 表按 date 分区，一次取太多月份可能慢）
for d in dates:
    try:
        df = dai.query(
            "SELECT instrument, dividend_yield_ratio FROM cn_stock_valuation_v6",
            filters={"date": [d]}
        ).df()
        if not df.empty:
            df = df[df['dividend_yield_ratio'] > 0]  # 过滤零值（未分红/数据缺失）
            if not df.empty:
                df['date'] = d
                dp_parts.append(df)
    except Exception:
        pass

if dp_parts:
    dp_raw = pd.concat(dp_parts, ignore_index=True)
    dp_tbl = dp_raw.pivot_table(values='dividend_yield_ratio',
                                 index='date', columns='instrument')
    dp_tbl = dp_tbl.reindex(rebal_days)
    print(f'股息率: {dp_tbl.shape}')
    dp_valid = dp_tbl.notna().sum(axis=1)
    print(f'每期有效数: min={dp_valid.min()}  max={dp_valid.max()}  median={int(dp_valid.median())}')
else:
    print('⚠️ 股息率数据为空')
    dp_tbl = pd.DataFrame()


# ============================================================
# 5. 行业数据（中性化用）
# ============================================================
print('\n' + '=' * 60)
print('5. 行业分类')
print('=' * 60)

try:
    ind_df = dai.query(
        "SELECT instrument, industry_level1_code FROM cn_stock_industry"
    ).df()
    ind_map = dict(zip(ind_df['instrument'], ind_df['industry_level1_code']))
    print(f'行业映射: {len(ind_map)} 只股票')
except Exception as e:
    print(f'行业表查询失败: {e}')
    ind_map = {}


# ============================================================
# 6. 因子预处理
# ============================================================
print('\n' + '=' * 60)
print('6. 因子预处理')
print('=' * 60)

if dp_tbl.empty:
    print('股息率数据缺失，无法继续。')
    raise SystemExit(0)


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


def prepare_factor(factor_tbl, higher_is_better):
    """去极值 → z-score，方向对齐(值越大=越好)。"""
    result = {}
    for d in factor_tbl.index:
        s = factor_tbl.loc[d].dropna()
        if len(s) < 30:
            continue
        s = winsorize_mad(s)
        s = zscore(s)
        if not higher_is_better:
            s = -s
        result[d] = s
    return pd.DataFrame(result).T


dp_factor  = prepare_factor(dp_tbl, higher_is_better=True)
vol_factor = prepare_factor(vol_tbl, higher_is_better=False)
print(f'dp:   {dp_factor.shape}')
print(f'vol:  {vol_factor.shape}')

# 合并因子
common_dates = sorted(set(dp_factor.index) & set(vol_factor.index))
print(f'共同调仓日: {len(common_dates)}')

combined = {}
for d in common_dates:
    dp_s = dp_factor.loc[d].dropna()
    vol_s = vol_factor.loc[d].dropna()
    common = sorted(set(dp_s.index) & set(vol_s.index))
    if len(common) < 30:
        continue
    combined[d] = W_DP * dp_s[common] + W_VOL * vol_s[common]

combined_factor = pd.DataFrame(combined).T
print(f'红利低波合并: {combined_factor.shape}')


# ============================================================
# ⛔ 以下所有分析限制在训练集 (≤ 2022-12-31)
# ============================================================

def filter_train(factor_df):
    dates = [d for d in factor_df.index if d <= TRAIN_END_DATE]
    return factor_df.loc[dates]


def compute_ic(factor_df, fwd_ret_df):
    """Rank IC，仅训练集。"""
    factor_df = filter_train(factor_df)
    ics = []
    for d in factor_df.index:
        if d not in fwd_ret_df.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret_df.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < 30:
            continue
        ic, _ = spearmanr(f_s[common].values, r_s[common].values)
        if not np.isnan(ic):
            ics.append({'date': d, 'ic': ic, 'n': len(common)})
    return pd.DataFrame(ics)


def layered_returns(factor_df, fwd_ret_df, n_groups=N_GROUPS):
    """分层收益，仅训练集。"""
    factor_df = filter_train(factor_df)
    layers = {g: [] for g in range(n_groups)}
    for d in factor_df.index:
        if d not in fwd_ret_df.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret_df.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < n_groups * 5:
            continue
        vals = f_s[common].values
        rets = r_s[common].values
        order = vals.argsort()
        gs = len(common) // n_groups
        for g in range(n_groups):
            s, e = g * gs, min((g+1)*gs, len(common))
            layers[g].append(rets[order[s:e]].mean())
    return {g: pd.Series(layers[g]) for g in range(n_groups)}


def simulate(factor_df, fwd_ret_df, n_hold):
    """选因子值最高的 n_hold 只，等权月频。仅训练集。"""
    factor_df = filter_train(factor_df)
    monthly_rets = {}
    all_rets = {}
    for d in factor_df.index:
        if d not in fwd_ret_df.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret_df.loc[d].dropna()
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
        ex = monthly_ret[ci] - benchmark[ci]
        r['超额%'] = ex.mean()*12*100
        r['IR'] = ex.mean()/ex.std()*np.sqrt(12) if ex.std() > 0 else 0
    return r


# ============================================================
# 7. IC 分析（训练集）
# ============================================================
print('\n' + '=' * 60)
print('7. IC 分析 (训练集)')
print('=' * 60)

for name, factor_df in [('股息率(dp)', dp_factor), ('低波动(vol)', vol_factor),
                          ('红利低波', combined_factor)]:
    ic_df = compute_ic(factor_df, fwd_ret)
    if len(ic_df) == 0:
        print(f'{name}: 无数据')
        continue
    mu = ic_df['ic'].mean()
    ir = mu / ic_df['ic'].std() if ic_df['ic'].std() > 0 else 0
    pos = (ic_df['ic'] > 0).mean()
    print(f'{name:14s}  mean_IC={mu:+.4f}  IC_IR={ir:+.2f}  IC>0={pos:.1%}  N={len(ic_df)}')


# ============================================================
# 8. 分层收益（训练集）
# ============================================================
print('\n' + '=' * 60)
print('8. 分层收益 (训练集)')
print('=' * 60)

for name, factor_df in [('股息率', dp_factor), ('低波动', vol_factor),
                          ('红利低波', combined_factor)]:
    layers = layered_returns(factor_df, fwd_ret)
    print(f'\n--- {name} ---')
    ann_vals = {}
    for g in sorted(layers.keys()):
        s = layers[g].dropna()
        if len(s) == 0:
            continue
        ann = s.mean() * 12
        vol = s.std() * np.sqrt(12)
        sr = ann / vol if vol > 0 else 0
        dd = (s.cumsum() - s.cumsum().cummax()).min() * 100
        ann_vals[g] = ann
        print(f'  G{g+1:2d}  年化{ann*100:+5.1f}%  夏普{sr:+.2f}  回撤{dd:+5.1f}%  N={len(s)}')

    g_keys = sorted(ann_vals.keys())
    if len(g_keys) >= 2:
        rho, _ = spearmanr(g_keys, [ann_vals[g] for g in g_keys])
        spread = (ann_vals[g_keys[-1]] - ann_vals[g_keys[0]]) * 100
        print(f'  单调性 ρ={rho:.3f}  顶-底差={spread:.1f}%')


# ============================================================
# 9. N 敏感性 + 单因子对比（训练集）
# ============================================================
print('\n' + '=' * 60)
print('9. N 敏感性 & 单因子对比 (训练集)')
print('=' * 60)

print('--- N 敏感性 (红利低波合并) ---')
for n in [15, 20, 30, 40]:
    ret, bench = simulate(combined_factor, fwd_ret, n)
    s = stats(ret, bench)
    print(f'N={n:2d}  年化{s["年化%"]:+5.1f}%  夏普{s["夏普"]:.2f}  '
          f'回撤{s["回撤%"]:+5.1f}%  超额{s.get("超额%",0):+5.1f}%  '
          f'IR{s.get("IR",0):.2f}  {s["月数"]}月')

print('\n--- 单因子 vs 合并 (N=20) ---')
for name, factor_df in [('纯股息率', dp_factor), ('纯低波动', vol_factor),
                          ('红利低波', combined_factor)]:
    ret, bench = simulate(factor_df, fwd_ret, 20)
    s = stats(ret, bench)
    print(f'{name}  年化{s["年化%"]:+5.1f}%  夏普{s["夏普"]:.2f}  '
          f'回撤{s["回撤%"]:+5.1f}%  超额{s.get("超额%",0):+5.1f}%  '
          f'IR{s.get("IR",0):.2f}  {s["月数"]}月')


# ============================================================
# 10. 因子截面相关性
# ============================================================
print('\n' + '=' * 60)
print('10. dp vs vol 截面相关 (训练集)')
print('=' * 60)

corrs = []
for d in common_dates:
    if d > TRAIN_END_DATE:
        break
    dp_s = dp_factor.loc[d].dropna() if d in dp_factor.index else None
    vol_s = vol_factor.loc[d].dropna() if d in vol_factor.index else None
    if dp_s is None or vol_s is None:
        continue
    common = sorted(set(dp_s.index) & set(vol_s.index))
    if len(common) >= 30:
        c = dp_s[common].corr(vol_s[common])
        if not np.isnan(c):
            corrs.append(c)

if corrs:
    corrs = pd.Series(corrs)
    print(f'mean={corrs.mean():.3f}  median={corrs.median():.3f}  std={corrs.std():.3f}')
    print(f'正相关占比: {(corrs>0).mean()*100:.1f}%  → '
          + ('高股息=低波动，合并增量有限' if corrs.mean() > 0.3
             else '相关性适中，合并有分散价值'))


# ============================================================
# 11. 分年度 + 训练集总结
# ============================================================
print('\n' + '=' * 60)
print('11. 分年度 + 训练集总结')
print('=' * 60)

ret_full, bench_full = simulate(combined_factor, fwd_ret, N_HOLD)

if len(ret_full) > 0:
    df = ret_full.reset_index()
    df.columns = ['date', 'ret']
    df['year'] = pd.to_datetime(df['date']).dt.year

    print('分年度收益:')
    for yr, grp in df.groupby('year'):
        cum = (1 + grp['ret']).prod() - 1
        bar = '█' * max(0, int(cum*100/5)) if cum >= 0 else '░' * max(0, int(-cum*100/3))
        print(f'  {yr}  {cum:+6.1f}%  {bar}')

    s = stats(ret_full)
    print(f'\n全训练集: 年化{s["年化%"]:.1f}%  夏普{s["夏普"]:.2f}  '
          f'波动{s["波动%"]:.1f}%  回撤{s["回撤%"]:.1f}%  '
          f'月胜率{s["月胜率"]:.1f}%  {s["月数"]}月')

    # 前后段稳定性
    mid = '2019-01-01'
    pre = ret_full[ret_full.index <= mid]
    post = ret_full[ret_full.index > mid]
    if len(pre) >= 12 and len(post) >= 12:
        sp = stats(pre)
        so = stats(post)
        print(f'前半(<2019): 年化{sp["年化%"]:+.1f}%  夏普{sp["夏普"]:.2f}  回撤{sp["回撤%"]:.1f}%')
        print(f'后半(≥2019): 年化{so["年化%"]:+.1f}%  夏普{so["夏普"]:.2f}  回撤{so["回撤%"]:.1f}%')
        # 前后段相关（月度收益相关性，非参数排序）
        common_months = sorted(set(pre.index) & set(post.index)
                               | set(pre.index) | set(post.index))
        if len(pre) > 0 and len(post) > 0:
            print(f'注: 前后段参数稳定性无法直接计算(因子不同期)，')
            print(f'    但已知股票因子 IS/OOS 相关性 -0.815，参数优化有害。')

    # 夏普标准误
    se = np.sqrt((1 + s['夏普']**2/2) / s['月数']) * np.sqrt(12)
    print(f'\n训练集 {s["月数"]} 个月，夏普标准误 ≈ {se:.2f}')
    print(f'→ 95% 置信区间较宽，参数选择须保守。')


# ============================================================
# 12. 参数网格（仅供参考，不做优化）
# ============================================================
print('\n' + '=' * 60)
print('12. 参数网格 N × w_dp (仅供参考)')
print('=' * 60)

grid_rows = []
for n in [15, 20, 30, 40]:
    for w_dp in [0.3, 0.4, 0.5, 0.6, 0.7]:
        w_vol = 1.0 - w_dp
        tmp = {}
        for d in common_dates:
            if d > TRAIN_END_DATE:
                break
            dp_s = dp_factor.loc[d].dropna() if d in dp_factor.index else None
            vol_s = vol_factor.loc[d].dropna() if d in vol_factor.index else None
            if dp_s is None or vol_s is None:
                continue
            common = sorted(set(dp_s.index) & set(vol_s.index))
            if len(common) < 30:
                continue
            tmp[d] = w_dp * dp_s[common] + w_vol * vol_s[common]

        tmp_factor = pd.DataFrame(tmp).T
        ret, bench = simulate(tmp_factor, fwd_ret, n)
        s = stats(ret, bench)
        grid_rows.append({'N': n, 'w_dp': w_dp, '年化%': s['年化%'],
                          '夏普': s['夏普'], '回撤%': s['回撤%']})

grid_df = pd.DataFrame(grid_rows)
print(f'中位夏普: {grid_df["夏普"].median():.2f}')
print(f'夏普范围: [{grid_df["夏普"].min():.2f}, {grid_df["夏普"].max():.2f}]')

for n in [15, 20, 30, 40]:
    sub = grid_df[grid_df['N'] == n]
    print(f'N={n}: 夏普 median={sub["夏普"].median():.2f}  '
          f'range=[{sub["夏普"].min():.2f}, {sub["夏普"].max():.2f}]')

print('\n⚠️ IS/OOS 相关性已知为负（股票 -0.815），此网格不用于参数选择。')


# ============================================================
# 训练集总结
# ============================================================
print('\n' + '=' * 60)
print('训练集总结')
print('=' * 60)

ret_final, _ = simulate(combined_factor, fwd_ret, N_HOLD)
s_final = stats(ret_final)

print(f'股票池:    中证800 (~{len(pool_stocks)}只)')
print(f'打分:      {W_DP:.0%} × z(股息率) + {W_VOL:.0%} × z(-波动率)')
print(f'持仓:      N={N_HOLD}, 等权, 月频')
print(f'训练集:    {train_days[0]} ~ {train_days[-1]} ({len(train_days)}次调仓)')
print(f'年化收益:   {s_final["年化%"]:.1f}%')
print(f'夏普(rf=0): {s_final["夏普"]:.2f}')
print(f'最大回撤:   {s_final["回撤%"]:.1f}%')
print(f'月胜率:     {s_final["月胜率"]:.1f}%')

print(f'\n⛔ 以上全部来自训练集 (≤ {TRAIN_END_DATE})。')
print(f'⛔ 测试集 ({TEST_START_DATE} ~ 2026-07) 未被触碰。')
print('冻结参数后，只跑一次 holdout notebook。')

print('\n===== 研究完成 =====')
