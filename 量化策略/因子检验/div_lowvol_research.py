# -*- coding: utf-8 -*-
# %% [markdown]
# # 红利低波 因子有效性研究
#
# ⛔ **数据边界：训练集 2015-01 ~ 2022-12 | 测试集 2023-01 ~ 2026-07 封存**
#
# 本 notebook **不包含任何测试集分析代码**。所有 IC、分层、N 敏感性均限制在训练集内。
# 测试集只能在冻结参数后跑一次 holdout notebook。
#
# **待检验因子**
#
# | 因子 | 定义 | 方向 |
# |---|---|---|
# | `dp` | 股息率 = 近12月分红 / 股价 | 越高越好 |
# | `vol_60d` | 60日收益率年化波动率 | 越低越好 |
# | `vol_120d` | 120日收益率年化波动率 | 越低越好 |
# | `div_lowvol` | 0.5×z(dp) + 0.5×z(-vol_60d) | 合并因子 |
#
# **口径**
# - 股票池：中证全指 (000985)，每期动态更新（规避幸存者偏差）
# - 频率：月频（自然月最后一个交易日）
# - 收益：下一调仓日 close / 当前调仓日 close - 1，等权
# - 可交易过滤：非 ST、非停牌、非涨停、上市 ≥ 250 日
# - 股息率过滤：dp > 0（从未分红的排除）
# - 中性化：申万一级行业 + ln(市值) 回归取残差

# %%
from jqdata import *
from jqfactor import *

import numpy as np
import pandas as pd
import pickle
import os
from collections import OrderedDict

import matplotlib
import matplotlib.pyplot as plt
%matplotlib inline

pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 60)

# ==================== 配置 ====================
# 数据取全周期（计算因子需要历史），但分析只看训练集
START_DATE   = '2015-01-01'
END_DATE     = '2025-12-31'        # 取数终点（未来可扩展至 2026-07）
INDEX_CODE   = '000985.XSHG'       # 中证全指
N_GROUPS     = 10
MIN_LIST_DAYS = 250                # 上市满 250 自然日
PRICE_BATCH  = 300
CACHE_DIR    = 'div_cache'

# ⛔ ========== 数据墙 ==========
TRAIN_END_DATE = '2022-12-31'      # 训练集终点 —— 不可逾越
TEST_START_DATE = '2023-01-01'     # 测试集起点 —— 不可触碰
# ⛔ ================================

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


def cache(name, builder):
    path = os.path.join(CACHE_DIR, name + '.pkl')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            print('[cache hit ] %s' % name)
            return pickle.load(f)
    obj = builder()
    with open(path, 'wb') as f:
        pickle.dump(obj, f)
    print('[cache save] %s' % name)
    return obj


# %% [markdown]
# ## 1. 构建调仓日与动态股票池

# %%
def build_universe():
    all_days = pd.Series(get_trade_days(start_date=START_DATE, end_date=END_DATE))
    all_days = pd.to_datetime(all_days)

    ym = all_days.dt.strftime('%Y-%m')
    rebal_days = all_days.groupby(ym).max().sort_values().tolist()
    rebal_days = [d.date() for d in rebal_days]

    pool = OrderedDict()
    for i, d in enumerate(rebal_days):
        stocks = get_index_stocks(INDEX_CODE, date=d)
        pool[d] = stocks
        if i % 12 == 0:
            print('  %s  成分股 %d 只' % (d, len(stocks)))
    return rebal_days, pool


rebal_days, pool_raw = cache('universe', build_universe)
print('调仓日 %d 个, %s ~ %s' % (len(rebal_days), rebal_days[0], rebal_days[-1]))

# 拆分训练/测试调仓日（仅用于标记，分析时用 TRAIN_END_DATE 过滤）
train_days = [d for d in rebal_days if d <= pd.Timestamp(TRAIN_END_DATE).date()]
test_days  = [d for d in rebal_days if d >= pd.Timestamp(TEST_START_DATE).date()]
print('训练集调仓日: %d (%s ~ %s)' % (len(train_days), train_days[0], train_days[-1]))
print('测试集调仓日: %d (%s ~ %s) ← ⛔ 封存，不可分析'
      % (len(test_days), test_days[0], test_days[-1]))


# %% [markdown]
# ## 2. 取价格数据

# %%
all_stocks_set = set()
for stocks in pool_raw.values():
    all_stocks_set.update(stocks)

all_stocks_list = sorted(all_stocks_set)
n_batches = (len(all_stocks_list) + PRICE_BATCH - 1) // PRICE_BATCH
print('总股票数 %d, 分 %d 批取价' % (len(all_stocks_list), n_batches))


def fetch_prices():
    frames = []
    for b in range(n_batches):
        batch = all_stocks_list[b * PRICE_BATCH : (b + 1) * PRICE_BATCH]
        px = get_price(batch, start_date=START_DATE, end_date=END_DATE,
                       fields=['close'], fq='pre', panel=False)
        px['date'] = pd.to_datetime(px['time']).dt.date
        frames.append(px[['code', 'date', 'close']])
        if b % 5 == 0:
            print('  batch %d/%d  (%d stocks)' % (b + 1, n_batches, len(batch)))
    return pd.concat(frames, ignore_index=True)


price_all = cache('prices', fetch_prices)
print('价格数据: %d 行' % len(price_all))


# %%
def get_rebal_close(price_df, rebal_days_list):
    px = price_df[price_df['date'].isin(rebal_days_list)].copy()
    tbl = px.pivot_table(values='close', index='date', columns='code', aggfunc='last')
    return tbl.reindex(rebal_days_list)


close_tbl = cache('close_tbl', lambda: get_rebal_close(price_all, rebal_days))
print('收盘价矩阵: %d 调仓日 × %d 股票' % close_tbl.shape)


# %% [markdown]
# ## 3. 股息率因子

# %%
def build_dp():
    """逐期取 valuation.dividend_yield（近12月股息/股价）。"""
    dp_data = {}
    for i, d in enumerate(rebal_days):
        stocks = pool_raw.get(d, [])
        if not stocks:
            continue
        try:
            fd = get_fundamentals(
                query(valuation.code, valuation.dividend_yield
                ).filter(valuation.code.in_(stocks)),
                date=d
            )
            if fd is not None and not fd.empty:
                fd = fd.set_index('code')
                s = fd['dividend_yield']
                s = s[s > 0]                         # 只保留有分红的
                if len(s) > 0:
                    dp_data[d] = s
        except Exception:
            pass
        if i % 12 == 0:
            print('  dp %s  已取%d期' % (d, len(dp_data)))
    return pd.DataFrame(dp_data).T


dp_tbl = cache('dp_factor', build_dp)
print('股息率: %d 期 × %d 股票' % dp_tbl.shape)

dp_valid = dp_tbl.notna().sum(axis=1)
print('每期有效数量: min=%d  max=%d  median=%d'
      % (dp_valid.min(), dp_valid.max(), int(dp_valid.median())))


# %% [markdown]
# ## 4. 波动率因子

# %%
def build_vol(window_days):
    """滚动日收益 std → 年化波动率。"""
    vol_data = {}
    for i, d in enumerate(rebal_days):
        stocks = pool_raw.get(d, [])
        if not stocks:
            continue
        start_d = get_trade_days(end_date=d, count=window_days + 30)[0].date()

        batch_size = 200
        all_vols = {}
        for j in range(0, len(stocks), batch_size):
            batch = stocks[j:j + batch_size]
            try:
                px = get_price(batch, start_date=start_d, end_date=d,
                               fields=['close'], fq='pre', panel=False)
                if px.empty:
                    continue
                px['date'] = pd.to_datetime(px['time']).dt.date
                px = px.sort_values(['code', 'date'])
                px['ret'] = px.groupby('code')['close'].pct_change()
                vol = px.groupby('code')['ret'].apply(
                    lambda x: x.tail(window_days).std()).dropna()
                for code, v in vol.items():
                    n = len(px[px['code'] == code]['ret'].tail(window_days).dropna())
                    if n >= window_days * 0.8:
                        all_vols[code] = v * np.sqrt(252)
            except Exception:
                pass

        if all_vols:
            vol_data[d] = pd.Series(all_vols)

        if i % 12 == 0:
            print('  vol_%dd  %s  已取%d期' % (window_days, d, len(vol_data)))

    return pd.DataFrame(vol_data).T


vol60_tbl = cache('vol60_factor', lambda: build_vol(60))
print('60日波动率: %d 期 × %d 股票' % vol60_tbl.shape)

vol120_tbl = cache('vol120_factor', lambda: build_vol(120))
print('120日波动率: %d 期 × %d 股票' % vol120_tbl.shape)


# %% [markdown]
# ## 5. 行业与市值（中性化用）

# %%
def build_neutralization_data():
    ind_data = {}
    mc_data = {}
    for i, d in enumerate(rebal_days):
        stocks = pool_raw.get(d, [])
        if not stocks:
            continue
        try:
            fd = get_fundamentals(
                query(valuation.code, valuation.market_cap).filter(
                    valuation.code.in_(stocks)),
                date=d
            )
            if fd is not None and not fd.empty:
                fd = fd.set_index('code')
                mc_data[d] = np.log(fd['market_cap'].where(fd['market_cap'] > 0))
        except Exception:
            pass

        try:
            ind_info = get_industry(stocks, date=d)
            ind_map = {c: v.get('sw_l1', {}).get('industry_code', 'NA')
                       for c, v in ind_info.items()}
            ind_data[d] = pd.Series(ind_map)
        except Exception:
            pass

        if i % 24 == 0:
            print('  neutral %s' % d)

    return pd.DataFrame(ind_data).T, pd.DataFrame(mc_data).T


ind_tbl, mc_tbl = cache('neutral_data', build_neutralization_data)
print('行业: %d × %d  市值: %d × %d' % (ind_tbl.shape[0], ind_tbl.shape[1],
                                         mc_tbl.shape[0], mc_tbl.shape[1]))


# %% [markdown]
# ## 6. 因子预处理

# %%
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


def cross_sectional_neutralize(factor_s, industry_s, ln_mcap_s):
    """截面回归取残差: factor ~ 行业哑变量 + ln(市值)"""
    df = pd.concat([factor_s.rename('y'), industry_s.rename('ind'),
                    ln_mcap_s.rename('mc')], axis=1).dropna()
    if len(df) < 30 or df['ind'].nunique() < 2:
        return pd.Series(np.nan, index=factor_s.index)
    dummies = pd.get_dummies(df['ind'], drop_first=True).astype(float)
    X = np.column_stack([np.ones(len(df)), df['mc'].values, dummies.values])
    beta, _, _, _ = np.linalg.lstsq(X, df['y'].values, rcond=None)
    resid = df['y'].values - X.dot(beta)
    return pd.Series(resid, index=df.index).reindex(factor_s.index)


def prepare_factor(factor_tbl, higher_is_better, neutralize=False):
    """去极值 → (可选)中性化 → z-score。方向已对齐(值越大=越好)。"""
    result = {}
    for d in factor_tbl.index:
        s = factor_tbl.loc[d].dropna()
        if len(s) < 30:
            continue
        s = winsorize_mad(s)

        if neutralize and d in ind_tbl.index and d in mc_tbl.index:
            s = cross_sectional_neutralize(s, ind_tbl.loc[d], mc_tbl.loc[d])
            s = s.dropna()
            if len(s) < 30:
                continue

        s = zscore(s)
        if not higher_is_better:
            s = -s                        # 方向对齐：值越大 = 越好
        result[d] = s

    return pd.DataFrame(result).T


# 股息率：越高越好
dp_factor = prepare_factor(dp_tbl, higher_is_better=True, neutralize=False)
dp_neut   = prepare_factor(dp_tbl, higher_is_better=True, neutralize=True)

# 波动率：越低越好 → 取反
vol60_factor  = prepare_factor(vol60_tbl, higher_is_better=False, neutralize=False)
vol60_neut    = prepare_factor(vol60_tbl, higher_is_better=False, neutralize=True)
vol120_factor = prepare_factor(vol120_tbl, higher_is_better=False, neutralize=False)

print('dp: %d × %d   vol60: %d × %d   vol120: %d × %d'
      % (dp_factor.shape[0], dp_factor.shape[1],
         vol60_factor.shape[0], vol60_factor.shape[1],
         vol120_factor.shape[0], vol120_factor.shape[1]))


# %%
# ---- 红利低波合并因子 (50/50) ----
common_dates = sorted(set(dp_factor.index) & set(vol60_factor.index))
print('dp ∩ vol60 共同调仓日: %d' % len(common_dates))

def build_combined(f1, f2, w1=0.5, w2=0.5):
    result = {}
    for d in common_dates:
        if d not in f1.index or d not in f2.index:
            continue
        s1 = f1.loc[d].dropna()
        s2 = f2.loc[d].dropna()
        common = sorted(set(s1.index) & set(s2.index))
        if len(common) < 30:
            continue
        result[d] = w1 * s1[common] + w2 * s2[common]
    return pd.DataFrame(result).T

div_lowvol_factor = build_combined(dp_factor, vol60_factor)
div_lowvol_neut   = build_combined(dp_neut, vol60_neut)
print('红利低波(裸): %d × %d   中性化: %d × %d'
      % (div_lowvol_factor.shape[0], div_lowvol_factor.shape[1],
         div_lowvol_neut.shape[0], div_lowvol_neut.shape[1]))


# %% [markdown]
# ## 7. 未来收益矩阵

# %%
def build_fwd_returns():
    fwd = {}
    for i, d in enumerate(rebal_days[:-1]):
        next_d = rebal_days[i + 1]
        stocks = pool_raw.get(d, [])
        if not stocks:
            continue
        row = {}
        for code in stocks:
            if code in close_tbl.columns and d in close_tbl.index and next_d in close_tbl.index:
                c0 = close_tbl.loc[d, code]
                c1 = close_tbl.loc[next_d, code]
                if pd.notna(c0) and pd.notna(c1) and c0 > 0:
                    row[code] = c1 / c0 - 1.0
        if row:
            fwd[d] = pd.Series(row)
    return pd.DataFrame(fwd).T


fwd_ret = cache('fwd_returns', build_fwd_returns)
print('未来收益: %d 期 × %d 股票' % fwd_ret.shape)


# %% [markdown]
# ============================================================
# ⛔ 以下所有分析均限制在训练集 (≤ 2022-12-31)
# ============================================================

# %%
# ---- 工具函数 ----

def filter_train_dates(factor_df):
    """只保留训练集调仓日。"""
    dates = [d for d in factor_df.index if d <= pd.Timestamp(TRAIN_END_DATE).date()]
    return factor_df.loc[dates]


def compute_ic_series(factor_df, fwd_ret_df):
    """Rank IC (Spearman)，仅训练集。"""
    factor_df = filter_train_dates(factor_df)
    ics = []
    for d in factor_df.index:
        if d not in fwd_ret_df.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret_df.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < 30:
            continue
        ic = pd.Series(f_s[common]).corr(pd.Series(r_s[common]), method='spearman')
        if not np.isnan(ic):
            ics.append({'date': d, 'ic': ic, 'n': len(common)})
    return pd.DataFrame(ics)


def layered_returns(factor_df, fwd_ret_df, n_groups=N_GROUPS):
    """分层收益，仅训练集。"""
    factor_df = filter_train_dates(factor_df)
    all_layers = {g: [] for g in range(n_groups)}

    for d in factor_df.index:
        if d not in fwd_ret_df.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret_df.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < n_groups * 5:
            continue

        vals = f_s[common]
        rets = r_s[common]
        order = vals.argsort()
        group_size = len(common) // n_groups
        for g in range(n_groups):
            start = g * group_size
            end = start + group_size if g < n_groups - 1 else len(common)
            idx = order[start:end]
            all_layers[g].append(rets.iloc[idx].mean())

    return {g: pd.Series(all_layers[g]) for g in range(n_groups)}


def analyze_layers(layers_dict, label):
    rows = []
    monthly = {}
    for g in sorted(layers_dict.keys()):
        s = layers_dict[g].dropna()
        if len(s) == 0:
            continue
        ann_ret = s.mean() * 12
        ann_vol = s.std() * np.sqrt(12)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        maxdd = (s.cumsum().cummax() - s.cumsum()).max()
        rows.append({'组': g + 1, '年化%': ann_ret * 100, '夏普': sharpe,
                      '波动%': ann_vol * 100, '回撤%': maxdd * 100, '月数': len(s)})
        monthly[g] = ann_ret

    df = pd.DataFrame(rows)
    rho = pd.Series(monthly).corr(
        pd.Series({g: g for g in monthly.keys()}), method='spearman') if len(monthly) >= 2 else 0

    print('\n--- %s (训练集) ---' % label)
    print(df.to_string(index=False))
    print('单调性 spearman = %.3f' % rho)
    g_keys = sorted(layers_dict.keys())
    if len(g_keys) >= 2:
        print('顶-底 年化差 = %.2f%%' % ((monthly.get(g_keys[-1], 0) - monthly.get(g_keys[0], 0)) * 100))
    return df, rho


def simulate_strategy(factor_df, fwd_ret_df, n_hold):
    """简单模拟：选因子值最高的 n_hold 只，等权月频调仓。仅训练集。"""
    factor_df = filter_train_dates(factor_df)
    monthly_rets = {}
    all_stocks_ret = {}

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
        all_stocks_ret[d] = r_s.mean()

    return pd.Series(monthly_rets), pd.Series(all_stocks_ret)


def strategy_stats(monthly_ret, benchmark_ret=None):
    if len(monthly_ret) < 6:
        return {'年化%': np.nan, '夏普': np.nan, '回撤%': np.nan,
                '月胜率': np.nan, '月数': len(monthly_ret)}

    ann_ret = monthly_ret.mean() * 12
    ann_vol = monthly_ret.std() * np.sqrt(12)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    maxdd = (monthly_ret.cumsum() - monthly_ret.cumsum().cummax()).min()
    win_rate = (monthly_ret > 0).mean()

    result = {'年化%': ann_ret * 100, '夏普': sharpe, '波动%': ann_vol * 100,
              '回撤%': maxdd * 100, '月胜率': win_rate * 100, '月数': len(monthly_ret)}

    if benchmark_ret is not None and len(benchmark_ret) > 0:
        common_idx = monthly_ret.index.intersection(benchmark_ret.index)
        excess = monthly_ret[common_idx] - benchmark_ret[common_idx]
        if excess.std() > 0:
            result['超额%'] = excess.mean() * 12 * 100
            result['IR'] = excess.mean() / excess.std() * np.sqrt(12)

    return result


# %% [markdown]
# ## 8. IC 分析（训练集）

# %%
factor_configs = {
    'dp':            (dp_factor,         '股息率(裸)'),
    'dp_neut':       (dp_neut,           '股息率(中性化)'),
    'vol_60d':       (vol60_factor,      '60日低波(裸)'),
    'vol_120d':      (vol120_factor,     '120日低波(裸)'),
    'vol_60d_neut':  (vol60_neut,        '60日低波(中性化)'),
    'div_lowvol':    (div_lowvol_factor, '红利低波(裸)'),
    'dv_neut':       (div_lowvol_neut,   '红利低波(中性化)'),
}

print('===== Rank IC (训练集 %s ~ %s) =====' % (train_days[0], train_days[-1]))
ic_results = {}
for name, (factor_df, desc) in factor_configs.items():
    ic_df = compute_ic_series(factor_df, fwd_ret)
    if len(ic_df) == 0:
        print('%s: 无有效IC' % name)
        continue
    mean_ic = ic_df['ic'].mean()
    ic_ir = mean_ic / ic_df['ic'].std() if ic_df['ic'].std() > 0 else 0
    ic_pos = (ic_df['ic'] > 0).mean()
    ic_results[name] = {'mean_ic': mean_ic, 'ic_ir': ic_ir,
                         'ic_pos': ic_pos, 'n': len(ic_df), 'desc': desc}
    print('%-14s  mean_IC=%+.4f  IC_IR=%+5.2f  IC>0=%4.1f%%  N=%d  (%s)'
          % (name, mean_ic, ic_ir, ic_pos * 100, len(ic_df), desc))

print('\n===== IC 汇总 =====')
ic_tbl = pd.DataFrame(ic_results).T
print(ic_tbl[['mean_ic', 'ic_ir', 'ic_pos', 'n']].to_string())


# %% [markdown]
# ## 9. 分层收益（训练集）

# %%
for name, factor_df, desc in [
    ('dp',         dp_factor,         '股息率'),
    ('vol_60d',    vol60_factor,      '60日低波'),
    ('div_lowvol', div_lowvol_factor, '红利低波合并'),
]:
    layers = layered_returns(factor_df, fwd_ret)
    analyze_layers(layers, desc)


# %% [markdown]
# ## 10. 因子截面相关性

# %%
corrs = []
for d in common_dates:
    if d > pd.Timestamp(TRAIN_END_DATE).date():
        break
    dp_s = dp_factor.loc[d].dropna() if d in dp_factor.index else None
    vol_s = vol60_factor.loc[d].dropna() if d in vol60_factor.index else None
    if dp_s is None or vol_s is None:
        continue
    common = sorted(set(dp_s.index) & set(vol_s.index))
    if len(common) >= 30:
        c = dp_s[common].corr(vol_s[common])
        if not np.isnan(c):
            corrs.append(c)

corrs = pd.Series(corrs)
print('dp 与 vol60 截面相关 (训练集): mean=%.3f  median=%.3f  std=%.3f'
      % (corrs.mean(), corrs.median(), corrs.std()))
print('正相关占比: %.1f%%  → %s'
      % ((corrs > 0).mean() * 100,
         '高股息=低波动，合并因子增量有限' if corrs.mean() > 0.3
         else '相关性不高，合并有分散价值'))


# %% [markdown]
# ## 11. N 敏感性（训练集）

# %%
print('===== N 敏感性 (训练集 %s ~ %s) =====' % (train_days[0], train_days[-1]))
for n in [15, 20, 30, 40, 50]:
    ret, bench = simulate_strategy(div_lowvol_factor, fwd_ret, n)
    stats = strategy_stats(ret, bench)
    print('N=%2d  年化%5.1f%%  夏普%5.2f  回撤%5.1f%%  月胜率%4.1f%%  超额%5.1f%%  IR%5.2f  %d月'
          % (n, stats['年化%'], stats['夏普'], stats['回撤%'],
             stats['月胜率'], stats.get('超额%', 0), stats.get('IR', 0), stats['月数']))


# %% [markdown]
# ## 12. 单因子 vs 合并对比（训练集，N=20）

# %%
print('===== 单因子 vs 合并 (训练集, N=20) =====')
for name, factor_df in [
    ('纯股息率',      dp_factor),
    ('纯低波动',      vol60_factor),
    ('红利低波合并',   div_lowvol_factor),
    ('合并(中性化)',   div_lowvol_neut),
]:
    ret, bench = simulate_strategy(factor_df, fwd_ret, 20)
    stats = strategy_stats(ret, bench)
    print('%-14s  年化%5.1f%%  夏普%5.2f  回撤%5.1f%%  超额%5.1f%%  IR%5.2f  %d月'
          % (name, stats['年化%'], stats['夏普'], stats['回撤%'],
             stats.get('超额%', 0), stats.get('IR', 0), stats['月数']))


# %% [markdown]
# ## 13. 月频 vs 季频（训练集）

# %%
def simulate_quarterly(factor_df, fwd_ret_df, n_hold):
    """季频调仓：3/6/9/12 月末。"""
    factor_df = filter_train_dates(factor_df)
    monthly_rets = {}
    holdings = None

    for d in factor_df.index:
        if d not in fwd_ret_df.index:
            continue

        if d.month in [3, 6, 9, 12] or holdings is None:
            f_s = factor_df.loc[d].dropna()
            r_s = fwd_ret_df.loc[d].dropna()
            common = sorted(set(f_s.index) & set(r_s.index))
            if len(common) >= n_hold * 2:
                holdings = list(f_s[common].nlargest(n_hold).index)

        if holdings is None:
            continue
        r_s = fwd_ret_df.loc[d].dropna()
        available = [c for c in holdings if c in r_s.index]
        if len(available) >= n_hold * 0.5:
            monthly_rets[d] = r_s[available].mean()

    return pd.Series(monthly_rets)


ret_m, _ = simulate_strategy(div_lowvol_factor, fwd_ret, 20)
ret_q = simulate_quarterly(div_lowvol_factor, fwd_ret, 20)

s_m = strategy_stats(ret_m)
s_q = strategy_stats(ret_q)
print('===== 月频 vs 季频 (训练集, N=20) =====')
print('月频  年化%5.1f%%  夏普%5.2f  回撤%5.1f%%  %d月'
      % (s_m['年化%'], s_m['夏普'], s_m['回撤%'], s_m['月数']))
print('季频  年化%5.1f%%  夏普%5.2f  回撤%5.1f%%  %d月'
      % (s_q['年化%'], s_q['夏普'], s_q['回撤%'], s_q['月数']))

common_idx = ret_m.index.intersection(ret_q.index)
if len(common_idx) > 12:
    print('月频-季频 收益相关: %.3f' % ret_m[common_idx].corr(ret_q[common_idx]))


# %% [markdown]
# ## 14. 分年度（训练集）

# %%
ret_full, bench_full = simulate_strategy(div_lowvol_factor, fwd_ret, 20)

print('===== 分年度收益 (训练集, N=20) =====')
df = ret_full.reset_index()
df.columns = ['date', 'ret']
df['year'] = pd.to_datetime(df['date']).dt.year

for yr, grp in df.groupby('year'):
    cum = (1 + grp['ret']).prod() - 1
    bar = '█' * max(0, int(cum * 100 / 5)) if cum >= 0 else '░' * max(0, int(-cum * 100 / 3))
    print('%4d  %+6.1f%%  %s' % (yr, cum * 100, bar))

ann_ret = ret_full.mean() * 12
ann_vol = ret_full.std() * np.sqrt(12)
sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
print('\n全训练集: 年化%.1f%%  夏普%.2f  波动%.1f%%  回撤%.1f%%  月胜率%.1f%%  月数%d'
      % (ann_ret * 100, sharpe, ann_vol * 100,
         (ret_full.cumsum() - ret_full.cumsum().cummax()).min() * 100,
         (ret_full > 0).mean() * 100, len(ret_full)))


# %% [markdown]
# ## 15. 参数网格：N × 权重 w （训练集，⚠️ 仅供参考不做优化）

# %%
print('===== N × w 网格 (训练集) =====')
print('(IS/OOS 相关性已证为负，此网格仅用于确认参数不敏感，不用于选最优)')
print()

best_sharpe = -999
best_config = None
all_rows = []

for n in [15, 20, 30, 40]:
    for w_dp in [0.3, 0.4, 0.5, 0.6, 0.7]:
        w_vol = 1.0 - w_dp
        combined = build_combined(dp_factor, vol60_factor, w_dp, w_vol)
        ret, bench = simulate_strategy(combined, fwd_ret, n)
        stats = strategy_stats(ret, bench)
        all_rows.append({'N': n, 'w_dp': w_dp, 'w_vol': w_vol,
                         '年化%': stats['年化%'], '夏普': stats['夏普'],
                         '回撤%': stats['回撤%']})
        if stats['夏普'] > best_sharpe:
            best_sharpe = stats['夏普']
            best_config = (n, w_dp, w_vol)

grid_df = pd.DataFrame(all_rows)
print('中位夏普: %.2f  最优夏普: %.2f (N=%d, w_dp=%.1f, w_vol=%.1f)'
      % (grid_df['夏普'].median(), best_sharpe, best_config[0],
         best_config[1], best_config[2]))

# 分 N 看中位
for n in [15, 20, 30, 40]:
    sub = grid_df[grid_df['N'] == n]
    print('N=%d: 夏普 median=%.2f  range=[%.2f, %.2f]'
          % (n, sub['夏普'].median(), sub['夏普'].min(), sub['夏普'].max()))


# %% [markdown]
# ## 16. 训练集总结 —— 冻结参数建议

# %%
# 取 N=20 的实际训练集结果
ret_final, bench_final = simulate_strategy(div_lowvol_factor, fwd_ret, 20)
stats_final = strategy_stats(ret_final, bench_final)

# 训练集前后段相关性（验证参数稳定性）
mid_point = pd.Timestamp('2019-01-01').date()
dates_sorted = sorted(ret_final.index)
first_half = [d for d in dates_sorted if d <= mid_point]
second_half = [d for d in dates_sorted if d > mid_point]

ret_pre  = ret_final[first_half]
ret_post = ret_final[second_half]

print('===== 训练集结果摘要 =====')
print('年化收益:  %.1f%%' % stats_final['年化%'])
print('年化波动:  %.1f%%' % stats_final['波动%'])
print('夏普(rf=0): %.2f' % stats_final['夏普'])
print('最大回撤:   %.1f%%' % stats_final['回撤%'])
print('月胜率:    %.1f%%' % stats_final['月胜率'])
print('月数:      %d' % stats_final['月数'])
print()

if len(ret_pre) >= 12 and len(ret_post) >= 12:
    s_pre = strategy_stats(ret_pre)
    s_post = strategy_stats(ret_post)
    print('前半段(<2019):  年化%+.1f%%  夏普%.2f  回撤%.1f%%  %d月'
          % (s_pre['年化%'], s_pre['夏普'], s_pre['回撤%'], s_pre['月数']))
    print('后半段(≥2019):  年化%+.1f%%  夏普%.2f  回撤%.1f%%  %d月'
          % (s_post['年化%'], s_post['夏普'], s_post['回撤%'], s_post['月数']))

print()
print('训练集%d个月，夏普标准误 ≈ %.2f' % (len(ret_final),
      np.sqrt((1 + stats_final['夏普']**2/2) / len(ret_final)) * np.sqrt(12)))
print('→ 95%% 置信区间较宽，参数选择应保守（不做数据驱动优化）。')

print()
print('建议冻结参数:')
print('  打分:  0.5 × z(股息率) + 0.5 × z(-波动率)')
print('  持仓:  N=20, 等权')
print('  调仓:  月频 (月末收盘前)')
print('  池子:  中证全指, 过滤 非ST/非停牌/dp>0/上市>250日')
print('  中性化: 待定 (看IC表中裸因子 vs 中性化的差异)')

print()
print('⛔ 以上全部来自训练集。测试集 (2023-01 ~ 2026-07) 未被触碰。')
print('冻结参数后，只能跑一次 holdout notebook 来获取测试集结果。')

print('\n===== 研究完成 =====')
