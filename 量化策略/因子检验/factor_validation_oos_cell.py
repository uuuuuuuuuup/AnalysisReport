# %% [markdown]
# # Part 4：样本外检验 + MA60择时冲突验证
#
# **前提**：在已跑完 `factor_validation_full.ipynb` 的**同一个 kernel** 里新增 cell 粘贴执行。
#
# ## 要回答的三个问题
#
# | # | 问题 | 判定含义 |
# |---|---|---|
# | 1 | 样本内挑的最优参数，样本外还成立吗？ | 若不成立 → 前面所有 IR 数字作废 |
# | 2 | 样本内 IR 能否预测样本外 IR？ | **若排序相关性≈0 → 整个挑参数的动作只是在挑噪音** |
# | 3 | MA60 择时是帮忙还是打架？ | 直接检验"择时层与 alpha 反向"的猜想 |
#
# 问题 2 是最关键的诊断：它检验的不是"某个参数好不好"，
# 而是"用历史表现挑参数"这件事本身有没有意义。

# %%
from datetime import date

IS_LO,  IS_HI  = date(2015, 1, 1), date(2021, 1, 1)   # 样本内 72个月
OOS_LO, OOS_HI = date(2021, 1, 1), date(2026, 1, 1)   # 样本外 59个月

WEIGHTS = [(0.7, 0.3, 'roe70/bp30'), (0.5, 0.5, 'roe50/bp50'),
           (0.3, 0.7, 'roe30/bp70'), (0.2, 0.8, 'roe20/bp80'),
           (0.0, 1.0, 'bp100')]
NS = [16, 24, 30, 40, 50]

# 构建面板（每个权重一个，N 不影响面板）
panels = {}
for wr, wb, wn in WEIGHTS:
    key = wn + ' + momExcl'
    panels[wn] = combo_panels.get(key) if key in combo_panels \
                 else build_combo(wr, wb, exclude_mom_top=0.20)

# 全区间收益序列（换手连续性保留，之后再切片）
series = {}
for wr, wb, wn in WEIGHTS:
    for n in NS:
        r, _ = long_only(panels[wn], n_hold=n, cost_rt=COST_50W)
        series[(wn, n)] = r
print('已生成 %d 个配置的收益序列' % len(series))


def slice_perf(r, lo, hi, label):
    rr = r[[d for d in r.index if lo <= d < hi]]
    if len(rr) < 12:
        return None
    return perf(rr, bench_r, label)


# %% [markdown]
# ## 问题 1 & 2：样本内 vs 样本外

# %%
rows = []
for (wn, n), r in series.items():
    pi = slice_perf(r, IS_LO, IS_HI, '')
    po = slice_perf(r, OOS_LO, OOS_HI, '')
    if pi is None or po is None:
        continue
    rows.append(OrderedDict([
        ('config', '%s|N=%d' % (wn, n)),
        ('IS_excess', round(pi['excess_ann'], 4)),
        ('IS_IR', pi['IR']),
        ('OOS_excess', round(po['excess_ann'], 4)),
        ('OOS_IR', po['IR']),
        ('OOS_exDD', round(po['excess_maxdd'], 4)),
    ]))
oos_df = pd.DataFrame(rows).sort_values('IS_IR', ascending=False)

print('=' * 100)
print('样本内(2015-2020, 72m)  vs  样本外(2021-2025, 59m)   按样本内IR排序')
print('=' * 100)
print(oos_df.to_string(index=False))

# 关键诊断：IS 排序能否预测 OOS 排序
rank_corr = oos_df['IS_IR'].corr(oos_df['OOS_IR'], method='spearman')
pear = oos_df['IS_IR'].corr(oos_df['OOS_IR'])
print('\n>>> IS_IR 与 OOS_IR 的排序相关性 (spearman) = %.3f' % rank_corr)
print('>>> IS_IR 与 OOS_IR 的线性相关性 (pearson)  = %.3f' % pear)
if abs(rank_corr) < 0.3:
    print('    ==> 样本内表现几乎不能预测样本外表现。')
    print('        挑参数这件事在这个问题上没有信息量，应改用先验固定参数。')
elif rank_corr < 0:
    print('    ==> 负相关：样本内越好，样本外越差。典型过拟合特征。')
else:
    print('    ==> 存在正向预测力，挑参数有一定意义。')

# 样本内最优 → 样本外实际表现
best_is = oos_df.iloc[0]
print('\n样本内最优配置: %s  (IS_IR=%.2f, IS超额=%.2f%%)'
      % (best_is['config'], best_is['IS_IR'], best_is['IS_excess'] * 100))
print('  它的样本外表现: OOS_IR=%.2f, OOS超额=%.2f%%, OOS超额回撤=%.2f%%'
      % (best_is['OOS_IR'], best_is['OOS_excess'] * 100, best_is['OOS_exDD'] * 100))
print('  样本外全部配置的中位 IR = %.2f' % oos_df['OOS_IR'].median())
print('  样本外为正的配置数 = %d / %d'
      % ((oos_df['OOS_excess'] > 0).sum(), len(oos_df)))


# %% [markdown]
# ## Walk-forward：滚动挑参数 vs 先验固定参数
#
# 每年初用**过去48个月**挑 IR 最高的配置，用于**下一年**，逐年滚动。
# 对照组是一个不做任何拟合的先验固定配置。
#
# **若滚动挑参数打不过先验固定，则证明参数优化只是在放大噪音。**

# %%
FIXED = ('roe50/bp50', 40)      # 先验固定：等权拼两因子，N取中段，未经优化

wf_chunks, wf_picks = [], []
for y in range(2019, 2026):
    tr_lo, tr_hi = date(y - 4, 1, 1), date(y, 1, 1)
    te_lo, te_hi = date(y, 1, 1), date(y + 1, 1, 1)
    best, best_ir = None, -99
    for cfg, r in series.items():
        p = slice_perf(r, tr_lo, tr_hi, '')
        if p is None or p['IR'] is None or np.isnan(p['IR']):
            continue
        if p['IR'] > best_ir:
            best, best_ir = cfg, p['IR']
    if best is None:
        continue
    te = series[best][[d for d in series[best].index if te_lo <= d < te_hi]]
    if len(te) == 0:
        continue
    wf_chunks.append(te)
    wf_picks.append((y, '%s|N=%d' % best, round(best_ir, 2)))

print('逐年挑中的配置:')
for y, c, ir in wf_picks:
    print('  %d  ->  %-22s (前48月IR=%.2f)' % (y, c, ir))

wf = pd.concat(wf_chunks).sort_index()
fx = series[FIXED][[d for d in series[FIXED].index if date(2019, 1, 1) <= d]]

print('\n' + '=' * 100)
print('Walk-forward(滚动挑参数)  vs  先验固定参数   [2019-2025 共同区间]')
print('=' * 100)
cmp_rows = [perf(wf, bench_r, 'walk-forward 滚动挑参数'),
            perf(fx, bench_r, '先验固定 %s|N=%d' % FIXED)]
print(pd.DataFrame(cmp_rows).to_string(index=False))


# %% [markdown]
# ## 问题 3：MA60 择时与 alpha 是否打架
#
# 用 rebalance 日（含当日）之前的数据判断指数是否在 MA60 上方，
# 与因子组合的**下一期**超额收益对照——检验
# "MA60 说强势时，正是因子最不灵的时候" 这个猜想。

# %%
_idx = get_price(INDEX_CODE, start_date='2014-06-01', end_date=END_DATE,
                 frequency='daily', fields=['close'])['close']
_idx.index = pd.to_datetime(_idx.index)

above = {}
for d in rebal_days:
    t = pd.Timestamp(d)
    hist = _idx.loc[:t]
    if len(hist) < 60:
        continue
    above[d] = bool(hist.iloc[-1] > hist.iloc[-60:].mean())
above_s = pd.Series(above)
print('MA60上方月份 %d / 下方 %d' % (above_s.sum(), (~above_s).sum()))

r_base = series[FIXED]
ex = r_base - bench_r.reindex(r_base.index).fillna(0)

up = ex[[d for d in ex.index if above_s.get(d, False)]]
dn = ex[[d for d in ex.index if d in above_s.index and not above_s[d]]]

print('\n---- 因子组合超额收益 按MA60状态拆分 (%s|N=%d) ----' % FIXED)
print('MA60上方(择时说加仓): 月均超额 %+.3f%%  年化 %+.2f%%  月数 %d  胜率 %.1f%%'
      % (up.mean() * 100, ((1 + up.mean()) ** 12 - 1) * 100, len(up), (up > 0).mean() * 100))
print('MA60下方(择时说减仓): 月均超额 %+.3f%%  年化 %+.2f%%  月数 %d  胜率 %.1f%%'
      % (dn.mean() * 100, ((1 + dn.mean()) ** 12 - 1) * 100, len(dn), (dn > 0).mean() * 100))
gap = (up.mean() - dn.mean()) * 100
print('差异: %+.3f%%/月' % gap)
if gap < -0.2:
    print('  ==> 证实冲突: MA60看多时因子明显更差，择时层与选股层反向。')
elif gap > 0.2:
    print('  ==> 未证实: MA60看多时因子反而更好，择时与选股同向，猜想被推翻。')
else:
    print('  ==> 无显著差异，MA60状态与因子有效性基本无关(择时未帮忙也未打架)。')

print('\n---- 三种择时方案对比 (绝对收益口径) ----')
gated = r_base.copy()
gated[[d for d in gated.index if not above_s.get(d, False)]] = 0.0    # 仅MA60上方持仓
inv = r_base.copy()
inv[[d for d in inv.index if above_s.get(d, True)]] = 0.0             # 仅MA60下方持仓
tim_rows = [perf(r_base, bench_r, '始终满仓(无择时)'),
            perf(gated, bench_r, 'MA60上方才持仓'),
            perf(inv, bench_r, 'MA60下方才持仓')]
print(pd.DataFrame(tim_rows).to_string(index=False))
print('\n注: 择时方案持仓月份更少(空仓记0收益)，绝对收益天然偏低，')
print('    重点比 sharpe / maxdd，而非 ann_ret。')

oos_df.to_csv('oos_validation.csv', index=False, encoding='utf-8-sig')
print('\n已导出: oos_validation.csv')
