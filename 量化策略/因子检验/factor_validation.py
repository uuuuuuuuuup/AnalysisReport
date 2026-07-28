# -*- coding: utf-8 -*-
# %% [markdown]
# # 中证1000 因子有效性分层检验
#
# 目的：在动任何权重之前，先回答"这三个因子方向对不对"。
#
# **待检验因子**
#
# | 因子 | 定义 | 角色 |
# |---|---|---|
# | `mom_40d`  | 40日收益率 | **策略当前在用（权重50%）** |
# | `mom_20d`  | 20日收益率 | 短期反转对照 |
# | `mom_12_1` | 250日收益剔除最近20日 | 学术标准动量对照 |
# | `roe_report` | `indicator.roe`（报告期累计、未年化） | **策略当前在用（权重30%）** |
# | `roe_ttm`  | `pb_ratio / pe_ratio` 恒等式反推 | 正确实现对照 |
# | `ep`       | `1 / pe_ratio` | **策略当前在用（权重20%），越大越便宜** |
# | `bp`       | `1 / pb_ratio` | 对照 |
#
# **口径**
# - 股票池：每期动态取中证1000成分股（规避幸存者偏差）
# - 频率：月频（自然月最后一个交易日）
# - 收益：close(T+1末) / close(T末) - 1，等权
# - 剔除：停牌、ST、上市不足120日、当期涨停（买不进）
# - 双版本：裸因子 / 行业(sw_l1)+ln市值 中性化残差
#
# **通过标准**
#
# | 指标 | 门槛 |
# |---|---|
# | \|IC均值\| | > 0.02 |
# | \|IC_IR\| | > 0.3 |
# | 分层单调性 | \|spearman(组号, 组年化)\| > 0.7 |
# | 分年度方向一致率 | > 60% |

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
START_DATE = '2015-01-01'
END_DATE   = '2025-12-31'
INDEX_CODE = '000852.XSHG'      # 中证1000
N_GROUPS   = 10                 # 分层组数
MIN_LIST_DAYS = 120             # 上市满N个自然日才纳入
PRICE_BATCH = 300               # get_price 分批只数
CACHE_DIR  = 'factor_cache'     # 缓存目录(研究环境当前路径下)

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


def cache(name, builder):
    """磁盘缓存：取数很慢，避免重跑。删除 factor_cache/ 即可强制重取。"""
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

    # 每个自然月的最后一个交易日
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


rebal_days, pool = cache('universe', build_universe)
all_codes = sorted(set(c for v in pool.values() for c in v))
print('\n调仓期数: %d  (%s ~ %s)' % (len(rebal_days), rebal_days[0], rebal_days[-1]))
print('历史成分股并集: %d 只' % len(all_codes))


# %% [markdown]
# ## 2. 价格数据（分批取全区间日线）
#
# 需要 `close` 算因子与收益，`paused` / `high_limit` 做可交易过滤。
# 用 `fq='pre'` 前复权，避免除权造成的假跌幅。

# %%
def _fetch_batch(batch, start, end, fields):
    """兼容新旧聚宽 get_price：新版 panel=False 返回长表，旧版返回 Panel。
    统一返回 {field: DataFrame(index=date, columns=code)}"""
    try:
        long = get_price(batch, start_date=start, end_date=end, frequency='daily',
                         fields=fields, skip_paused=False, fq='pre', panel=False)
        tcol = 'time' if 'time' in long.columns else long.columns[0]
        long[tcol] = pd.to_datetime(long[tcol])
        return {f: long.pivot(index=tcol, columns='code', values=f) for f in fields}
    except TypeError:
        p = get_price(batch, start_date=start, end_date=end, frequency='daily',
                      fields=fields, skip_paused=False, fq='pre')
        return {f: p[f] for f in fields}


def fetch_prices():
    # 动量要回看250日，起点前推约400自然日
    fetch_start = (pd.Timestamp(START_DATE) - pd.Timedelta(days=400)).strftime('%Y-%m-%d')
    fields = ['close', 'paused', 'high_limit']
    acc = {f: [] for f in fields}
    n_batch = (len(all_codes) - 1) // PRICE_BATCH + 1
    for bi in range(n_batch):
        batch = all_codes[bi * PRICE_BATCH:(bi + 1) * PRICE_BATCH]
        d = _fetch_batch(batch, fetch_start, END_DATE, fields)
        for f in fields:
            acc[f].append(d[f])
        print('  batch %d/%d  cols=%d' % (bi + 1, n_batch, d['close'].shape[1]))
    out = {}
    for f in fields:
        m = pd.concat(acc[f], axis=1).sort_index()
        m.index = pd.to_datetime(m.index)
        out[f] = m
    return out


px = cache('prices', fetch_prices)
close, paused, high_limit = px['close'], px['paused'], px['high_limit']
print('\n价格面板: %s ~ %s, shape=%s' % (close.index[0].date(), close.index[-1].date(), close.shape))


# %% [markdown]
# ## 3. 基本面与行业
#
# `get_fundamentals(date=d)` 返回 d 日**已公告可见**的最新财报，聚宽已处理公告日，无未来函数。

# %%
def fetch_fundamentals():
    out = {}
    for i, d in enumerate(rebal_days):
        stocks = pool[d]
        q = query(valuation.code,
                  valuation.pe_ratio,
                  valuation.pb_ratio,
                  valuation.market_cap,
                  indicator.roe).filter(valuation.code.in_(stocks))
        df = get_fundamentals(q, date=d)
        out[d] = df.set_index('code') if df is not None and not df.empty else pd.DataFrame()
        if i % 12 == 0:
            print('  %s  财务 %d 行' % (d, len(out[d])))
    return out


def fetch_industry():
    out = {}
    for i, d in enumerate(rebal_days):
        info = get_industry(pool[d], date=d)
        out[d] = pd.Series({c: v.get('sw_l1', {}).get('industry_code', 'NA')
                            for c, v in info.items()})
        if i % 12 == 0:
            print('  %s  行业 %d 只' % (d, len(out[d])))
    return out


fund = cache('fundamentals', fetch_fundamentals)
indu = cache('industry', fetch_industry)


# %% [markdown]
# ## 4. 可交易过滤 + 因子计算
#
# **过滤规则**（在 T 期末施加，模拟"这只票 T 期末真能买入"）
# - `paused == 1` 停牌 → 剔除
# - `close >= high_limit` 涨停 → 剔除（封板买不进）
# - 上市不足 `MIN_LIST_DAYS` → 剔除
# - ST → 剔除（`get_extras('is_st')`）

# %%
def fetch_st():
    frames = []
    n_batch = (len(all_codes) - 1) // PRICE_BATCH + 1
    for bi in range(n_batch):
        batch = all_codes[bi * PRICE_BATCH:(bi + 1) * PRICE_BATCH]
        df = get_extras('is_st', batch, start_date=START_DATE, end_date=END_DATE, df=True)
        frames.append(df)
        print('  st batch %d/%d' % (bi + 1, n_batch))
    st = pd.concat(frames, axis=1)
    st.index = pd.to_datetime(st.index)
    return st


is_st = cache('is_st', fetch_st)

list_date = cache('list_date', lambda: pd.Series(
    {c: get_security_info(c).start_date for c in all_codes}))


def ret_over(d, n):
    """截至 d（含）的 n 个交易日收益率。d 必须在 close.index 中。"""
    idx = close.index.get_loc(pd.Timestamp(d))
    if idx < n:
        return None
    cur = close.iloc[idx]
    prev = close.iloc[idx - n]
    return cur / prev - 1


def build_factors():
    """返回 {date: DataFrame(index=code, columns=[factors..., lnmc, industry])}"""
    recs = OrderedDict()
    for i, d in enumerate(rebal_days):
        ts = pd.Timestamp(d)
        if ts not in close.index:
            continue
        stocks = [c for c in pool[d] if c in close.columns]

        f = pd.DataFrame(index=stocks)

        # ---- 动量族 ----
        r20  = ret_over(d, 20)
        r40  = ret_over(d, 40)
        r250 = ret_over(d, 250)
        if r40 is None:
            continue
        f['mom_20d'] = r20.reindex(stocks) if r20 is not None else np.nan
        f['mom_40d'] = r40.reindex(stocks)
        if r250 is not None and r20 is not None:
            # 12-1 动量: (1+r250)/(1+r20) - 1，剔除最近1个月
            f['mom_12_1'] = ((1 + r250.reindex(stocks)) / (1 + r20.reindex(stocks))) - 1
        else:
            f['mom_12_1'] = np.nan

        # ---- 基本面族 ----
        fd = fund.get(d, pd.DataFrame())
        if not fd.empty:
            fd = fd.reindex(stocks)
            pe = fd['pe_ratio'].where(fd['pe_ratio'] > 0)
            pb = fd['pb_ratio'].where(fd['pb_ratio'] > 0)
            f['roe_report'] = fd['roe']
            f['roe_ttm'] = pb / pe          # 恒等式: PB/PE = ROE_TTM
            f['ep'] = 1.0 / pe
            f['bp'] = 1.0 / pb
            mc = fd['market_cap'].where(fd['market_cap'] > 0)
            f['lnmc'] = np.log(mc)
        else:
            for col in ['roe_report', 'roe_ttm', 'ep', 'bp', 'lnmc']:
                f[col] = np.nan

        f['industry'] = indu.get(d, pd.Series(dtype=object)).reindex(stocks)

        # ---- 可交易过滤 ----
        tradable = pd.Series(True, index=stocks)
        if ts in paused.index:
            tradable &= (paused.loc[ts].reindex(stocks).fillna(1) == 0)
        if ts in high_limit.index:
            hl = high_limit.loc[ts].reindex(stocks)
            cl = close.loc[ts].reindex(stocks)
            tradable &= ~(cl >= hl * 0.999)          # 涨停封板
        if ts in is_st.index:
            tradable &= (is_st.loc[ts].reindex(stocks).fillna(False) == False)
        age = pd.Series({c: (ts.date() - list_date[c]).days
                         for c in stocks if c in list_date.index})
        tradable &= (age.reindex(stocks).fillna(0) >= MIN_LIST_DAYS)
        tradable &= close.loc[ts].reindex(stocks).notna()

        recs[d] = f[tradable.fillna(False)]
        if i % 12 == 0:
            print('  %s  可用 %d / %d 只' % (d, len(recs[d]), len(stocks)))
    return recs


factors = cache('factors', build_factors)

FACTOR_LIST = ['mom_20d', 'mom_40d', 'mom_12_1', 'roe_report', 'roe_ttm', 'ep', 'bp']
IN_USE = {'mom_40d', 'roe_report', 'ep'}     # 策略当前实际使用的三个

cov = pd.DataFrame(
    {f: {d: factors[d][f].notna().mean() for d in factors} for f in FACTOR_LIST})
print('\n各因子平均覆盖率:')
print((cov.mean() * 100).round(1).to_string())


# %% [markdown]
# ## 5. 前瞻收益

# %%
def build_forward_returns():
    dates = list(factors.keys())
    fwd = {}
    for i in range(len(dates) - 1):
        d0, d1 = pd.Timestamp(dates[i]), pd.Timestamp(dates[i + 1])
        if d0 not in close.index or d1 not in close.index:
            continue
        r = close.loc[d1] / close.loc[d0] - 1
        # 期间停牌退市的按 -100% 处理过于激进，这里剔除（并在报告中注明）
        fwd[dates[i]] = r.dropna()
    return fwd


fwd_ret = build_forward_returns()
print('前瞻收益期数: %d' % len(fwd_ret))


# %% [markdown]
# ## 6. 预处理：MAD去极值 → 行业+ln市值中性化 → 标准化
#
# 中性化用 numpy 最小二乘手动实现（行业哑变量 + ln市值 + 常数项），
# 不依赖 `jqfactor`，避免权限与版本差异。

# %%
def mad_winsorize(s, n=5):
    med = s.median()
    mad = (s - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return s
    lo, hi = med - n * 1.4826 * mad, med + n * 1.4826 * mad
    return s.clip(lo, hi)


def zscore(s):
    sd = s.std()
    return (s - s.mean()) / sd if sd and not np.isnan(sd) else s * 0.0


def neutralize_cs(s, industry, lnmc):
    """截面回归取残差：s ~ 行业哑变量 + ln市值"""
    df = pd.concat([s.rename('y'), industry.rename('ind'), lnmc.rename('mc')], axis=1).dropna()
    if len(df) < 30 or df['ind'].nunique() < 2:
        return pd.Series(np.nan, index=s.index)
    D = pd.get_dummies(df['ind'], drop_first=True).astype(float)
    X = np.column_stack([np.ones(len(df)), df['mc'].values, D.values])
    y = df['y'].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X.dot(beta)
    return pd.Series(resid, index=df.index).reindex(s.index)


def prepare(neutral):
    """返回 {factor: DataFrame(index=date, columns=code)}"""
    out = {f: {} for f in FACTOR_LIST}
    for d, F in factors.items():
        for f in FACTOR_LIST:
            s = F[f].dropna()
            if len(s) < 50:
                continue
            s = zscore(mad_winsorize(s))
            if neutral:
                s = neutralize_cs(s, F['industry'], F['lnmc']).dropna()
                if len(s) < 50:
                    continue
                s = zscore(s)
            out[f][d] = s
    return {f: pd.DataFrame(v).T.sort_index() for f, v in out.items()}


raw_f = prepare(neutral=False)
neu_f = prepare(neutral=True)
print('预处理完成。裸因子/中性化 各 %d 个' % len(raw_f))


# %% [markdown]
# ## 7. IC 检验 + 分层回测

# %%
def max_drawdown(nav):
    return float((nav / nav.cummax() - 1).min())


def evaluate(fac_panel, name):
    """返回 (summary dict, 分层年化 Series, 多空月度收益 Series, IC 时序 Series)"""
    ics, ls_rets, grp_rets = {}, {}, {g: {} for g in range(N_GROUPS)}

    for d in fac_panel.index:
        if d not in fwd_ret:
            continue
        s = fac_panel.loc[d].dropna()
        r = fwd_ret[d]
        common = s.index.intersection(r.index)
        if len(common) < N_GROUPS * 5:
            continue
        s, r = s[common], r[common]

        ics[d] = s.corr(r, method='spearman')

        try:
            lab = pd.qcut(s.rank(method='first'), N_GROUPS, labels=False)
        except ValueError:
            continue
        gm = r.groupby(lab).mean()
        for g in range(N_GROUPS):
            if g in gm.index:
                grp_rets[g][d] = gm[g]
        if 0 in gm.index and N_GROUPS - 1 in gm.index:
            ls_rets[d] = gm[N_GROUPS - 1] - gm[0]     # 高分位 - 低分位

    ic = pd.Series(ics).sort_index()
    ls = pd.Series(ls_rets).sort_index()
    n = len(ic)
    if n < 12:
        return None, None, None, None

    ic_mean, ic_std = ic.mean(), ic.std()
    ic_ir = ic_mean / ic_std if ic_std else np.nan

    grp_ann = {}
    for g in range(N_GROUPS):
        gr = pd.Series(grp_rets[g]).sort_index()
        if len(gr) < 12:
            continue
        nav = (1 + gr).cumprod()
        grp_ann[g + 1] = nav.iloc[-1] ** (12.0 / len(gr)) - 1
    grp_ann = pd.Series(grp_ann)

    mono = (pd.Series(grp_ann.index, index=grp_ann.index)
            .corr(grp_ann, method='spearman')) if len(grp_ann) > 2 else np.nan

    ls_nav = (1 + ls).cumprod()
    ls_ann = ls_nav.iloc[-1] ** (12.0 / len(ls)) - 1
    ls_sharpe = ls.mean() / ls.std() * np.sqrt(12) if ls.std() else np.nan

    yearly_ls = ls.groupby(pd.Series(ls.index).apply(lambda x: x.year).values).sum()
    consist = (np.sign(yearly_ls) == np.sign(ls_ann)).mean()

    summary = OrderedDict([
        ('factor', name),
        ('n_periods', n),
        ('IC_mean', round(ic_mean, 4)),
        ('IC_std', round(ic_std, 4)),
        ('IC_IR', round(ic_ir, 3)),
        ('IC_t', round(ic_ir * np.sqrt(n), 2)),
        ('IC>0_pct', round((ic > 0).mean(), 3)),
        ('monotonic', round(mono, 3) if not np.isnan(mono) else np.nan),
        ('LS_ann', round(ls_ann, 4)),
        ('LS_sharpe', round(ls_sharpe, 2)),
        ('LS_maxdd', round(max_drawdown(ls_nav), 4)),
        ('yr_consist', round(consist, 3)),
    ])
    return summary, grp_ann, ls, ic


results, detail = [], {}
for tag, panel_set in [('raw', raw_f), ('neutral', neu_f)]:
    for f in FACTOR_LIST:
        if f not in panel_set or panel_set[f].empty:
            continue
        summ, grp_ann, ls, ic = evaluate(panel_set[f], f)
        if summ is None:
            continue
        summ['version'] = tag
        summ['in_use'] = 'YES' if f in IN_USE else ''
        results.append(summ)
        detail[(tag, f)] = (grp_ann, ls, ic)

res = pd.DataFrame(results)
cols = ['version', 'factor', 'in_use', 'n_periods', 'IC_mean', 'IC_IR', 'IC_t',
        'IC>0_pct', 'monotonic', 'LS_ann', 'LS_sharpe', 'LS_maxdd', 'yr_consist']
res = res[cols]


def verdict(r):
    if abs(r['IC_mean']) < 0.02 or abs(r['IC_IR']) < 0.3:
        return 'INVALID(too weak)'
    if r['IC_mean'] < 0:
        return '*** REVERSED ***'
    if abs(r['monotonic']) < 0.7:
        return 'NON-MONOTONIC'
    if r['yr_consist'] < 0.6:
        return 'UNSTABLE'
    return 'VALID'


res['verdict'] = res.apply(verdict, axis=1)

print('\n' + '=' * 130)
print('因子有效性汇总  (in_use=YES 为策略当前实际使用)')
print('=' * 130)
for tag in ['raw', 'neutral']:
    print('\n---- %s ----' % tag)
    print(res[res['version'] == tag].drop(columns=['version']).to_string(index=False))


# %% [markdown]
# ## 8. 分层年化收益矩阵
#
# 若因子有效，Q1→Q10 应单调递增。**若 Q1 显著高于 Q10，说明因子方向反了。**

# %%
for tag in ['raw', 'neutral']:
    rows = {}
    for f in FACTOR_LIST:
        if (tag, f) in detail:
            rows[f + (' *' if f in IN_USE else '')] = (detail[(tag, f)][0] * 100).round(2)
    if rows:
        print('\n---- 分层年化收益 %% (%s) ----' % tag)
        print(pd.DataFrame(rows).T.to_string())


# %% [markdown]
# ## 9. 分年度稳定性（多空组合年收益 %）

# %%
for tag in ['raw', 'neutral']:
    rows = {}
    for f in FACTOR_LIST:
        if (tag, f) in detail:
            ls = detail[(tag, f)][1]
            yr = ls.groupby(pd.Series(ls.index).apply(lambda x: x.year).values).sum()
            rows[f + (' *' if f in IN_USE else '')] = (yr * 100).round(1)
    if rows:
        print('\n---- 多空组合分年度收益 %% (%s) ----' % tag)
        print(pd.DataFrame(rows).T.to_string())


# %% [markdown]
# ## 10. 图表

# %%
fig, axes = plt.subplots(2, 2, figsize=(16, 10))

# 分层年化柱状图（裸因子，仅在用的三因子）
ax = axes[0][0]
w, offs = 0.25, [-0.25, 0, 0.25]
for k, f in enumerate(sorted(IN_USE)):
    if ('raw', f) in detail:
        ga = detail[('raw', f)][0]
        ax.bar(np.array(ga.index) + offs[k], ga.values * 100, width=w, label=f)
ax.axhline(0, color='k', lw=0.8)
ax.set_title('Group annualized return - factors IN USE (raw)')
ax.set_xlabel('quantile group (1=lowest factor value)')
ax.set_ylabel('annualized %')
ax.legend()
ax.grid(alpha=0.3)

# 动量族对比
ax = axes[0][1]
for f in ['mom_20d', 'mom_40d', 'mom_12_1']:
    if ('raw', f) in detail:
        ga = detail[('raw', f)][0]
        ax.plot(ga.index, ga.values * 100, marker='o', label=f)
ax.axhline(0, color='k', lw=0.8)
ax.set_title('Momentum family: 20d vs 40d vs 12-1')
ax.set_xlabel('quantile group')
ax.set_ylabel('annualized %')
ax.legend()
ax.grid(alpha=0.3)

# 多空净值
ax = axes[1][0]
for f in FACTOR_LIST:
    if ('raw', f) in detail:
        ls = detail[('raw', f)][1]
        ax.plot(ls.index, (1 + ls).cumprod().values,
                label=f + (' *' if f in IN_USE else ''),
                lw=2.0 if f in IN_USE else 1.0)
ax.axhline(1, color='k', lw=0.8)
ax.set_title('Long-short (Q10 - Q1) cumulative NAV, raw')
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

# IC 滚动12期均值
ax = axes[1][1]
for f in sorted(IN_USE):
    if ('raw', f) in detail:
        ic = detail[('raw', f)][2]
        ax.plot(ic.index, ic.rolling(12).mean().values, label=f)
ax.axhline(0, color='k', lw=0.8)
ax.axhline(0.02, color='g', ls='--', lw=0.8)
ax.axhline(-0.02, color='r', ls='--', lw=0.8)
ax.set_title('Rolling 12M mean IC - factors IN USE')
ax.legend()
ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('factor_validation.png', dpi=110)
print('图已保存: factor_validation.png')
plt.show()


# %% [markdown]
# ## 11. 导出 + 结论

# %%
res.to_csv('factor_summary.csv', index=False, encoding='utf-8-sig')

grp_out = {}
for (tag, f), (ga, ls, ic) in detail.items():
    grp_out['%s|%s' % (tag, f)] = ga
pd.DataFrame(grp_out).to_csv('factor_group_returns.csv', encoding='utf-8-sig')

print('已导出: factor_summary.csv / factor_group_returns.csv / factor_validation.png\n')

print('=' * 90)
print('对策略当前三因子的判决')
print('=' * 90)
name_map = {'mom_40d': '动量(权重50%)', 'roe_report': '质量(权重30%)', 'ep': '估值(权重20%)'}
for f in ['mom_40d', 'roe_report', 'ep']:
    for tag in ['raw', 'neutral']:
        row = res[(res['factor'] == f) & (res['version'] == tag)]
        if row.empty:
            continue
        r = row.iloc[0]
        print('%-22s [%-7s] IC=%+.4f IR=%+.3f t=%+.2f 单调=%+.3f 多空年化=%+.2f%% -> %s'
              % (name_map[f], tag, r['IC_mean'], r['IC_IR'], r['IC_t'],
                 r['monotonic'], r['LS_ann'] * 100, r['verdict']))

print('\n--- 对照组：正确实现 / 学术标准 ---')
for f in ['mom_20d', 'mom_12_1', 'roe_ttm', 'bp']:
    for tag in ['raw', 'neutral']:
        row = res[(res['factor'] == f) & (res['version'] == tag)]
        if row.empty:
            continue
        r = row.iloc[0]
        print('%-22s [%-7s] IC=%+.4f IR=%+.3f t=%+.2f 单调=%+.3f 多空年化=%+.2f%% -> %s'
              % (f, tag, r['IC_mean'], r['IC_IR'], r['IC_t'],
                 r['monotonic'], r['LS_ann'] * 100, r['verdict']))
