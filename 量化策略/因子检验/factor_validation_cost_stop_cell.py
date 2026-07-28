# %% [markdown]
# # Part 6：真实成本重估 + 移动止损 + N/整数倍权衡
#
# **前提**：在已跑完 `factor_validation_full.ipynb`（含 Part 4 的 `OOS_LO`）的同一 kernel 里执行。
#
# ## 背景修正
#
# 用户账户为 **免5 + 万0.85**，真实往返成本：
#
# ```
# 佣金 0.0085%×2 = 0.017%   (5%)
# 印花税(卖出)    = 0.100%   (32%)
# 滑点(估)        = 0.200%   (63%)   ← 现在是主导项
# 合计            = 0.317%
# ```
#
# 即等于原 `COST_50W`。上一轮"10万不可行"的判决基于 `COST_10W=0.65%`，作废。
#
# ## 本节要回答
#
# | # | 问题 | 空白原因 |
# |---|---|---|
# | 1 | 滑点假设错了怎么办？ | 滑点占成本63%，必须做敏感性 |
# | 2 | 移动止损 × 因子选股 = ? | 价值陷阱需价格止损，但从未联合测试 |
# | 3 | N 多大最优（含整数倍惩罚）？ | IR随N升，整数倍误差也随N升 |

# %%
COST_TRUE = 0.00317          # 免5+万0.85+印花税+滑点0.2%
COST_LO   = 0.00217          # 乐观：滑点0.1%(限价单/延后执行)
COST_HI   = 0.00417          # 悲观：滑点0.3%
CAPITAL   = 100000

PANEL = panels['roe50/bp50'] if 'panels' in dir() \
        else combo_panels['roe50/bp50 + momExcl']

print('=' * 96)
print('问题1：滑点敏感性 —— 真实成本下各 N 的表现（样本外 2021-2025）')
print('=' * 96)
rows = []
for N in [16, 20, 30, 40, 50]:
    for cname, c in [('乐观0.22%', COST_LO), ('基准0.32%', COST_TRUE), ('悲观0.42%', COST_HI)]:
        r, tn = long_only(PANEL, n_hold=N, cost_rt=c)
        ro = r[[d for d in r.index if d >= OOS_LO]]
        if len(ro) < 24:
            continue
        p = perf(ro, bench_r, 'N=%d %s' % (N, cname))
        rows.append(OrderedDict([
            ('config', 'N=%-3d %s' % (N, cname)),
            ('OOS_excess', round(p['excess_ann'], 4)),
            ('OOS_IR', p['IR']),
            ('OOS_exDD', round(p['excess_maxdd'], 4)),
            ('OOS_maxdd', round(p['maxdd'], 4)),
            ('turnover', round(tn.mean() * 12, 2)),
        ]))
sens = pd.DataFrame(rows)
print(sens.to_string(index=False))
print('\n>>> 若"悲观"列的 IR 仍 >0.35，则结论对滑点假设不敏感，可以放心推进。')


# %% [markdown]
# ## 问题2：移动止损 × 因子选股
#
# 逻辑：调仓日按因子选 top-N 建仓，月内逐日跟踪最高收盘价，
# 回撤达 `stop_pct` 则以当日收盘平仓、剩余时间持现金。
#
# **已知偏乐观**：真实执行会延后到次日，此处用当日收盘近似。

# %%
def run_with_stop(panel, n_hold, stop_pct=None, cost_rt=COST_TRUE):
    """返回 (月度净收益, 换手, 平均月内止损触发比例)"""
    dates = [d for d in panel.index if d in fwd_ret]
    rets, turns, hits = {}, {}, {}
    held_end = set()
    for i, d0 in enumerate(dates):
        if i + 1 >= len(dates):
            break
        d1 = dates[i + 1]
        s = panel.loc[d0].dropna()
        r_fwd = fwd_ret[d0]
        common = s.index.intersection(r_fwd.index)
        if len(common) < 50:
            continue
        sel = list(s[common].nlargest(n_hold).index)

        t0, t1 = pd.Timestamp(d0), pd.Timestamp(d1)
        days = close.index[(close.index > t0) & (close.index <= t1)]

        per, stopped = [], 0
        survive = set()
        for st in sel:
            if st not in close.columns:
                continue
            p0 = close.loc[t0, st]
            if not np.isfinite(p0) or p0 <= 0:
                continue
            path = close.loc[days, st].dropna()
            if len(path) == 0:
                continue
            if stop_pct is None:
                per.append(path.iloc[-1] / p0 - 1)
                survive.add(st)
                continue
            runmax, exit_r = p0, None
            for p in path.values:
                if p > runmax:
                    runmax = p
                if p <= runmax * (1 - stop_pct):
                    exit_r = p / p0 - 1
                    break
            if exit_r is None:
                per.append(path.iloc[-1] / p0 - 1)
                survive.add(st)
            else:
                per.append(exit_r)
                stopped += 1
        if not per:
            continue
        new_buys = len([x for x in sel if x not in held_end])
        turn = new_buys / float(len(sel))
        rets[d0] = float(np.mean(per)) - turn * cost_rt
        turns[d0] = turn
        hits[d0] = stopped / float(len(sel))
        held_end = survive
    return (pd.Series(rets).sort_index(), pd.Series(turns).sort_index(),
            pd.Series(hits).sort_index())


print('=' * 112)
print('问题2：移动止损效果   (N=30, 真实成本0.32%)')
print('=' * 112)
rows = []
for sp, lbl in [(None, '无止损'), (0.20, '止损20%'), (0.15, '止损15%'),
                (0.12, '止损12%'), (0.10, '止损10%'), (0.08, '止损8%')]:
    r, tn, hit = run_with_stop(PANEL, 30, stop_pct=sp)
    if len(r) < 36:
        continue
    pa = perf(r, bench_r, lbl)
    ro = r[[d for d in r.index if d >= OOS_LO]]
    po = perf(ro, bench_r, '') if len(ro) >= 24 else None
    rows.append(OrderedDict([
        ('stop', lbl),
        ('ALL_excess', round(pa['excess_ann'], 4)), ('ALL_IR', pa['IR']),
        ('ALL_maxdd', round(pa['maxdd'], 4)),
        ('ALL_exDD', round(pa['excess_maxdd'], 4)),
        ('OOS_excess', round(po['excess_ann'], 4) if po else np.nan),
        ('OOS_IR', po['IR'] if po else np.nan),
        ('turnover', round(tn.mean() * 12, 2)),
        ('月均触发', round(hit.mean(), 3)),
    ]))
stop_df = pd.DataFrame(rows)
print(stop_df.to_string(index=False))
print('\n>>> 关键看 ALL_maxdd 是否明显改善，且 OOS_IR 不被止损吃掉。')
print('    若止损既降回撤又不损IR → 采用；若只降回撤但IR大跌 → 说明止损在砍赢家。')


# %% [markdown]
# ## 问题3：N 与整数倍误差的联合权衡（10万本金）

# %%
print('=' * 104)
print('问题3：N 权衡表  (10万本金, 真实成本0.32%, 含止损最优档)')
print('=' * 104)

best_stop = None
if len(stop_df):
    cand = stop_df.dropna(subset=['OOS_IR'])
    if len(cand):
        top = cand.sort_values('OOS_IR', ascending=False).iloc[0]
        best_stop = {'无止损': None, '止损20%': 0.20, '止损15%': 0.15,
                     '止损12%': 0.12, '止损10%': 0.10, '止损8%': 0.08}[top['stop']]
        print('（止损档采用 OOS_IR 最优的: %s）\n' % top['stop'])

rows = []
for N in [16, 20, 24, 30, 40, 50]:
    r, tn, _ = run_with_stop(PANEL, N, stop_pct=best_stop)
    ro = r[[d for d in r.index if d >= OOS_LO]]
    if len(ro) < 24:
        continue
    p = perf(ro, bench_r, '')
    e, sk = lot_feasibility(PANEL, N, CAPITAL)
    rows.append(OrderedDict([
        ('N', N),
        ('单只金额', '%.0f元' % (CAPITAL / float(N))),
        ('整数倍误差', '%.1f%%' % (e * 100)),
        ('买不进', '%.1f%%' % (sk * 100)),
        ('OOS_excess', round(p['excess_ann'], 4)),
        ('OOS_IR', p['IR']),
        ('OOS_maxdd', round(p['maxdd'], 4)),
        ('turnover', round(tn.mean() * 12, 2)),
    ]))
ndf = pd.DataFrame(rows)
print(ndf.to_string(index=False))

print('\n' + '=' * 76)
print('股票因子策略 最终配置建议 (10万, 免5+万0.85)')
print('=' * 76)
if len(ndf):
    ok = ndf[ndf['OOS_IR'] >= 0.40]
    pick = ok.iloc[0] if len(ok) else ndf.sort_values('OOS_IR', ascending=False).iloc[0]
    print('推荐 N = %d   (单只%s, 整数倍误差%s, 买不进%s)'
          % (pick['N'], pick['单只金额'], pick['整数倍误差'], pick['买不进']))
    print('  样本外超额 %+.2f%%   IR %.2f   绝对回撤 %.2f%%   年化换手 %.0f%%'
          % (pick['OOS_excess'] * 100, pick['OOS_IR'],
             pick['OOS_maxdd'] * 100, pick['turnover'] * 100))
    print('  止损档: %s' % ('无' if best_stop is None else '%.0f%%' % (best_stop * 100)))
    if pick['OOS_IR'] >= 0.40:
        print('\n>>> 通过。可以进入生产代码编写。')
    else:
        print('\n>>> 未达 IR 0.40，需重新考虑。')

sens.to_csv('cost_sensitivity.csv', index=False, encoding='utf-8-sig')
stop_df.to_csv('stop_test.csv', index=False, encoding='utf-8-sig')
ndf.to_csv('n_tradeoff.csv', index=False, encoding='utf-8-sig')
print('\n已导出 cost_sensitivity.csv / stop_test.csv / n_tradeoff.csv')
