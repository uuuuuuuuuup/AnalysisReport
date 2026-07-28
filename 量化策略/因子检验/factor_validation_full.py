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


# %% [markdown]
# ============================================================
# Part 2（合并版）：因子相关性 / 组合因子 / 多头净超额 / 换手成本
# ============================================================
#
# 无需重新取数：universe/prices/fundamentals/industry/is_st/list_date/factors
# 全部命中 factor_cache/，本节只新增 bench_monthly() 对指数的一次轻量取数。
#
# **要回答的四个问题**
#
# | # | 问题 | 为什么决定性 |
# |---|---|---|
# | 1 | `roe_report` 和 `bp` 的信息是否重复？ | 若高度相关，加权=单因子加倍，权重讨论无意义 |
# | 2 | 组合因子 IR 是否高于单用 `roe_report`(0.494)？ | 若不高，就只用一个因子，别拼 |
# | 3 | **多头** top-N 相对中证1000 的超额是多少？ | 策略是纯多头，做不了空，LS 不可投资 |
# | 4 | 月频调仓的换手成本拖累多少？ | **若吃掉全部超额，B 应放弃而非重构** |

# %% [markdown]
# ## 测量 1：因子信息重复度
#
# 两个角度都看：
# - **IC 时序相关**：两个因子的"何时有效"是否同步（决定组合能否分散风险）
# - **截面值相关**：两个因子给股票的打分是否雷同（决定组合能否分散选股）


# %%
ic_tbl = {}
for f in FACTOR_LIST:
    if ('neutral', f) in detail:
        ic_tbl[f] = detail[('neutral', f)][2]
ic_df = pd.DataFrame(ic_tbl).sort_index()

print('---- IC 时序相关性 (neutral, spearman) ----')
print(ic_df.corr(method='spearman').round(2).to_string())

cs_corr = {}
for f1 in FACTOR_LIST:
    row = {}
    for f2 in FACTOR_LIST:
        vals = []
        for d in neu_f[f1].index:
            if d not in neu_f[f2].index:
                continue
            a, b = neu_f[f1].loc[d].dropna(), neu_f[f2].loc[d].dropna()
            common = a.index.intersection(b.index)
            if len(common) > 50:
                vals.append(a[common].corr(b[common], method='spearman'))
        row[f2] = np.mean(vals) if vals else np.nan
    cs_corr[f1] = row

print('\n---- 因子值截面相关性均值 (neutral, spearman) ----')
print(pd.DataFrame(cs_corr).round(2).to_string())



# %% [markdown]
# ## 测量 2：组合因子分层检验
#
# `mom_40d` 按 Part 1 的结论用作**硬排除**（剔除动量最高的 20%），不参与打分。


# %%
def build_combo(w_roe, w_bp, exclude_mom_top=0.20):
    """组合因子面板。w 作用在已中性化+z-score 的残差上。"""
    panel = {}
    base = neu_f['roe_report']
    for d in base.index:
        if d not in neu_f['bp'].index:
            continue
        a, b = base.loc[d].dropna(), neu_f['bp'].loc[d].dropna()
        common = a.index.intersection(b.index)
        if len(common) < 100:
            continue
        s = w_roe * zscore(a[common]) + w_bp * zscore(b[common])

        if exclude_mom_top and d in raw_f['mom_40d'].index:
            m = raw_f['mom_40d'].loc[d].dropna()
            keep = m[m.rank(pct=True) <= (1.0 - exclude_mom_top)].index
            s = s.reindex(s.index.intersection(keep))
        panel[d] = s.dropna()
    return pd.DataFrame(panel).T.sort_index()


SPECS = [
    ('roe only',              1.0, 0.0, 0.0),
    ('roe only + momExcl',    1.0, 0.0, 0.2),
    ('bp only + momExcl',     0.0, 1.0, 0.2),
    ('roe70/bp30 + momExcl',  0.7, 0.3, 0.2),
    ('roe50/bp50 + momExcl',  0.5, 0.5, 0.2),
    ('roe30/bp70 + momExcl',  0.3, 0.7, 0.2),
    ('roe50/bp50 no excl',    0.5, 0.5, 0.0),
]

combo_panels, combo_rows = {}, []
for name, wr, wb, ex in SPECS:
    p = build_combo(wr, wb, ex)
    combo_panels[name] = p
    summ, grp_ann, ls, ic = evaluate(p, name)
    if summ is None:
        print('!! %s 期数不足' % name)
        continue
    combo_rows.append(summ)
    detail[('combo', name)] = (grp_ann, ls, ic)

combo_res = pd.DataFrame(combo_rows)[
    ['factor', 'n_periods', 'IC_mean', 'IC_IR', 'IC_t', 'monotonic',
     'LS_ann', 'LS_sharpe', 'LS_maxdd', 'yr_consist']]
print('---- 组合因子 vs 单因子 ----')
print('基准: roe_report 单因子 neutral IR = 0.494, LS年化 12.67%\n')
print(combo_res.to_string(index=False))

print('\n---- 组合因子分层年化 %% ----')
rows = {}
for name, _, _, _ in SPECS:
    if ('combo', name) in detail:
        rows[name] = (detail[('combo', name)][0] * 100).round(2)
print(pd.DataFrame(rows).T.to_string())



# %% [markdown]
# ## 测量 3 + 4：多头绝对收益、超额、换手、扣费净超额
#
# **成本假设**（来自策略日志实测）
#
# | 本金 | 佣金 | 印花税 | 滑点 | 往返合计 |
# |---|---|---|---|---|
# | 10 万（当前）| 单边 0.167%（触发 5 元下限）| 卖出 0.1% | 0.2% | **0.65%** |
# | 50 万以上 | 单边 0.03%（名义费率）| 卖出 0.1% | 0.15% | **0.31%** |
#
# 换手成本 = 单边换手比例 × 往返成本（卖旧 + 买新）。


# %%
def bench_monthly():
    dates = [d for d in sorted(fwd_ret.keys())]
    bc = get_price(INDEX_CODE, start_date=str(dates[0]), end_date=END_DATE,
                   frequency='daily', fields=['close'])['close']
    bc.index = pd.to_datetime(bc.index)
    out = {}
    ds = sorted(set(list(fwd_ret.keys()) + [rebal_days[-1]]))
    for i in range(len(ds) - 1):
        t0, t1 = pd.Timestamp(ds[i]), pd.Timestamp(ds[i + 1])
        if t0 in bc.index and t1 in bc.index:
            out[ds[i]] = bc.loc[t1] / bc.loc[t0] - 1
    return pd.Series(out).sort_index()


bench_r = bench_monthly()
print('中证1000 月度收益期数: %d' % len(bench_r))


def long_only(panel, n_hold=None, top_pct=None, cost_rt=0.0):
    """纯多头等权组合。返回 (月度净收益 Series, 单边换手 Series)"""
    prev, rets, turns = set(), {}, {}
    for d in panel.index:
        if d not in fwd_ret:
            continue
        s, r = panel.loc[d].dropna(), fwd_ret[d]
        common = s.index.intersection(r.index)
        if len(common) < 50:
            continue
        s = s[common]
        k = n_hold if n_hold else max(1, int(len(s) * top_pct))
        sel = s.nlargest(k).index
        cur = set(sel)
        turn = len(cur - prev) / float(len(cur)) if cur else 0.0
        rets[d] = r[sel].mean() - turn * cost_rt
        turns[d] = turn
        prev = cur
    return pd.Series(rets).sort_index(), pd.Series(turns).sort_index()


def perf(r, bench, label):
    b = bench.reindex(r.index).fillna(0)
    n = len(r)
    nav, bnav = (1 + r).cumprod(), (1 + b).cumprod()
    ann = nav.iloc[-1] ** (12.0 / n) - 1
    bann = bnav.iloc[-1] ** (12.0 / n) - 1
    ex = r - b
    ex_nav = (1 + ex).cumprod()
    ex_ann = ex_nav.iloc[-1] ** (12.0 / n) - 1
    return OrderedDict([
        ('portfolio', label),
        ('n_months', n),
        ('ann_ret', round(ann, 4)),
        ('bench_ann', round(bann, 4)),
        ('excess_ann', round(ex_ann, 4)),
        ('ann_vol', round(r.std() * np.sqrt(12), 4)),
        ('sharpe', round(r.mean() / r.std() * np.sqrt(12), 2) if r.std() else np.nan),
        ('maxdd', round(max_drawdown(nav), 4)),
        ('excess_maxdd', round(max_drawdown(ex_nav), 4)),
        ('IR', round(ex.mean() / ex.std() * np.sqrt(12), 2) if ex.std() else np.nan),
        ('win_month', round((ex > 0).mean(), 3)),
    ])


BEST = 'roe50/bp50 + momExcl'
COST_10W, COST_50W = 0.0065, 0.0031

# 先看换手水平
_, tn = long_only(combo_panels[BEST], n_hold=16)
print('\n持仓16只，月度单边换手率: 均值 %.1f%%  中位 %.1f%%  年化单边 %.0f%%'
      % (tn.mean() * 100, tn.median() * 100, tn.mean() * 12 * 100))
print('→ 年化成本拖累:  10万本金 %.2f%%   50万本金 %.2f%%'
      % (tn.mean() * 12 * COST_10W * 100, tn.mean() * 12 * COST_50W * 100))

rows = []
for label, kw in [
    ('top20% (~180只) 零成本', dict(top_pct=0.20, cost_rt=0.0)),
    ('top20% (~180只) 50万成本', dict(top_pct=0.20, cost_rt=COST_50W)),
    ('16只 零成本', dict(n_hold=16, cost_rt=0.0)),
    ('16只 50万成本', dict(n_hold=16, cost_rt=COST_50W)),
    ('16只 10万成本', dict(n_hold=16, cost_rt=COST_10W)),
    ('8只 50万成本', dict(n_hold=8, cost_rt=COST_50W)),
    ('30只 50万成本', dict(n_hold=30, cost_rt=COST_50W)),
]:
    r, _ = long_only(combo_panels[BEST], **kw)
    rows.append(perf(r, bench_r, label))

print('\n' + '=' * 125)
print('纯多头表现  组合因子 = %s' % BEST)
print('=' * 125)
print(pd.DataFrame(rows).to_string(index=False))



# %% [markdown]
# ## 各权重方案的多头净超额横向对比（16只 / 50万成本）


# %%
rows = []
for name, _, _, _ in SPECS:
    if name not in combo_panels:
        continue
    r, _ = long_only(combo_panels[name], n_hold=16, cost_rt=COST_50W)
    if len(r) < 12:
        continue
    rows.append(perf(r, bench_r, name))
print(pd.DataFrame(rows).to_string(index=False))



# %% [markdown]
# ## 16只组合的分年度超额（不要被平滑的年化数字骗）
#
# 持仓只有 16 只时，年度离散度远大于分层检验的 180 只。


# %%
r16, _ = long_only(combo_panels[BEST], n_hold=16, cost_rt=COST_50W)
b16 = bench_r.reindex(r16.index).fillna(0)
yr = pd.DataFrame({
    'strategy': r16.groupby(pd.Series(r16.index).apply(lambda x: x.year).values).apply(
        lambda s: (1 + s).prod() - 1),
    'bench': b16.groupby(pd.Series(b16.index).apply(lambda x: x.year).values).apply(
        lambda s: (1 + s).prod() - 1),
})
yr['excess'] = yr['strategy'] - yr['bench']
print('---- 16只组合 分年度 (%%)，已扣 50万本金成本 ----')
print((yr * 100).round(1).to_string())
print('\n超额为正的年份: %d / %d' % ((yr['excess'] > 0).sum(), len(yr)))



# %% [markdown]
# ## 图表


# %%
fig, axes = plt.subplots(2, 2, figsize=(16, 10))

ax = axes[0][0]
for name in ['roe only', BEST, 'bp only + momExcl']:
    if ('combo', name) in detail:
        ga = detail[('combo', name)][0]
        ax.plot(ga.index, ga.values * 100, marker='o', label=name)
ax.axhline(0, color='k', lw=0.8)
ax.set_title('Combo factor: group annualized return')
ax.set_xlabel('quantile group')
ax.set_ylabel('annualized %')
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

ax = axes[0][1]
for lbl, kw in [('16 stocks, no cost', dict(n_hold=16, cost_rt=0.0)),
                ('16 stocks, 500k cost', dict(n_hold=16, cost_rt=COST_50W)),
                ('16 stocks, 100k cost', dict(n_hold=16, cost_rt=COST_10W))]:
    r, _ = long_only(combo_panels[BEST], **kw)
    ax.plot(r.index, (1 + r).cumprod().values, label=lbl)
ax.plot(bench_r.index, (1 + bench_r).cumprod().values, 'k--', label='CSI1000')
ax.set_title('Long-only NAV: cost impact')
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

ax = axes[1][0]
ex = r16 - b16
ax.plot(ex.index, (1 + ex).cumprod().values, 'r-', lw=2)
ax.axhline(1, color='k', lw=0.8)
ax.set_title('Excess NAV vs CSI1000 (16 stocks, 500k cost)')
ax.grid(alpha=0.3)

ax = axes[1][1]
_, tn16 = long_only(combo_panels[BEST], n_hold=16)
ax.plot(tn16.index, tn16.values * 100)
ax.axhline(tn16.mean() * 100, color='r', ls='--',
           label='mean %.0f%%' % (tn16.mean() * 100))
ax.set_title('Monthly one-way turnover (16 stocks)')
ax.set_ylabel('%')
ax.legend()
ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('factor_part2.png', dpi=110)
print('图已保存: factor_part2.png')
plt.show()



# %% [markdown]
# ## 判决


# %%
combo_res.to_csv('combo_summary.csv', index=False, encoding='utf-8-sig')

r_free, _ = long_only(combo_panels[BEST], n_hold=16, cost_rt=0.0)
r_50w, _ = long_only(combo_panels[BEST], n_hold=16, cost_rt=COST_50W)
r_10w, _ = long_only(combo_panels[BEST], n_hold=16, cost_rt=COST_10W)
p_free = perf(r_free, bench_r, 'free')
p_50w = perf(r_50w, bench_r, '50w')
p_10w = perf(r_10w, bench_r, '10w')

print('=' * 80)
print('B 策略生死判决  (16只持仓, 月频调仓, %s)' % BEST)
print('=' * 80)
print('毛超额年化      %+.2f%%' % (p_free['excess_ann'] * 100))
print('扣50万成本      %+.2f%%   (成本吃掉 %.2f 个点)'
      % (p_50w['excess_ann'] * 100,
         (p_free['excess_ann'] - p_50w['excess_ann']) * 100))
print('扣10万成本      %+.2f%%   (成本吃掉 %.2f 个点)'
      % (p_10w['excess_ann'] * 100,
         (p_free['excess_ann'] - p_10w['excess_ann']) * 100))
print('超额最大回撤    %.2f%%  (50万口径)' % (p_50w['excess_maxdd'] * 100))
print('信息比率        %.2f    (50万口径)' % p_50w['IR'])
print('月度胜率        %.1f%%' % (p_50w['win_month'] * 100))
print('超额为正年份    %d / %d' % ((yr['excess'] > 0).sum(), len(yr)))
print()
if p_50w['excess_ann'] <= 0:
    print('>>> 判决: 放弃 B。50万本金下净超额已为负，重构无意义。')
elif p_50w['excess_ann'] < 0.03:
    print('>>> 判决: B 边际可行但不值得。净超额 < 3%%，扣掉实盘偏差后归零。')
elif p_50w['IR'] < 0.5:
    print('>>> 判决: B 有超额但不稳定 (IR<0.5)，需先解决稳定性再谈上线。')
else:
    print('>>> 判决: B 可重构。进入分体制样本外检验(阶段2)。')
