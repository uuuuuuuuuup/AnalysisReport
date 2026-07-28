# -*- coding: utf-8 -*-
# %% [markdown]
# # Part 2：因子相关性 / 组合因子 / 多头净超额 / 换手成本
#
# **运行方式**：接在 `factor_validation.ipynb` 之后，在**同一个 kernel** 里跑。
# 若已重启 kernel，先重跑原 notebook 的 Cell 1~7（缓存全部命中，约 1 分钟）。
#
# **要回答的四个问题**
#
# | # | 问题 | 为什么决定性 |
# |---|---|---|
# | 1 | `roe_report` 和 `bp` 的信息是否重复？ | 若高度相关，加权=单因子加倍，权重讨论无意义 |
# | 2 | 组合因子 IR 是否高于单用 `roe_report`(0.494)？ | 若不高，就只用一个因子，别拼 |
# | 3 | **多头** top-N 相对中证1000 的超额是多少？ | 策略是纯多头，做不了空，LS 不可投资 |
# | 4 | 月频调仓的换手成本拖累多少？ | **若吃掉全部超额，B 应放弃而非重构** |

# %%
# 依赖检查：确认前置变量在 kernel 中
for _v in ['neu_f', 'raw_f', 'fwd_ret', 'detail', 'factors', 'close',
           'rebal_days', 'END_DATE', 'FACTOR_LIST', 'N_GROUPS', 'INDEX_CODE',
           'zscore', 'evaluate', 'max_drawdown']:
    if _v not in dir():
        raise NameError('缺少 %s —— 请先运行 factor_validation.ipynb 的 Cell 1~7' % _v)
print('前置变量齐全，继续。')


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
