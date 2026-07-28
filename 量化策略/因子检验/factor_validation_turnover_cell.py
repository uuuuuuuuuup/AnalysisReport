# %% [markdown]
# # Part 5：换手抑制 + 10万本金可行性判决
#
# **前提**：在已跑完 `factor_validation_full.ipynb` 的**同一个 kernel** 里新增 cell 执行。
#
# ## 背景
#
# 用户选定：纯多头指增（接受 25-30% 回撤）、本金 10 万。
# 在此约束下，成本拖累 = 换手率 × 成本率。成本率被本金锁死(0.65%往返)，
# **换手率是唯一可动的变量**，且当前 490%/年 远高于同类因子的正常水平(150-250%)。
#
# ## 两个机制
#
# 1. **缓冲带**：进入前 `buy_pct` 才买，跌出前 `sell_pct` 才卖（业界标准防抖手法）
# 2. **降频**：每 N 期才调仓一次
#
# ## 同时量化整数倍可行性
#
# 10 万本金下单只仓位极小，100股整数倍会造成系统性偏差，必须量化。

# %%
def long_only_buffer(panel, n_hold, buy_pct=0.20, sell_pct=0.50,
                     every=1, cost_rt=0.0):
    """带缓冲带与降频的多头组合。
    buy_pct : 仅从排名前 buy_pct 比例中补仓
    sell_pct: 持仓跌出前 sell_pct 比例才卖出
    every   : 每 every 期调仓一次（1=每期）
    """
    held, rets, turns = set(), {}, {}
    dates = [d for d in panel.index if d in fwd_ret]
    for i, d in enumerate(dates):
        s = panel.loc[d].dropna()
        r = fwd_ret[d]
        common = s.index.intersection(r.index)
        if len(common) < 50:
            continue
        s = s[common]
        rk = s.rank(ascending=False, pct=True)      # 0~1, 越小越好

        if i % every == 0:
            keep = set(x for x in held if x in rk.index and rk[x] <= sell_pct)
            slots = n_hold - len(keep)
            if slots > 0:
                pool = rk[rk <= buy_pct].sort_values().index
                cand = [x for x in pool if x not in keep]
                keep.update(cand[:slots])
            new = keep if keep else set(rk.sort_values().index[:n_hold])
        else:
            new = set(held)

        cur = [x for x in new if x in r.index]
        if not cur:
            held = new
            continue
        turn = len(new - held) / float(len(new)) if new else 0.0
        rets[d] = r[cur].mean() - turn * cost_rt
        turns[d] = turn
        held = new
    return pd.Series(rets).sort_index(), pd.Series(turns).sort_index()


PANEL = panels['roe50/bp50'] if 'panels' in dir() else \
        combo_panels['roe50/bp50 + momExcl']

# %% [markdown]
# ## 测试 1：缓冲带 + 降频 的换手与净超额（10万成本）

# %%
CFG = [
    ('基准 硬TopN 每期',        dict(buy_pct=1.0,  sell_pct=0.0,  every=1)),
    ('缓冲20/50 每期',          dict(buy_pct=0.20, sell_pct=0.50, every=1)),
    ('缓冲20/60 每期',          dict(buy_pct=0.20, sell_pct=0.60, every=1)),
    ('缓冲10/50 每期',          dict(buy_pct=0.10, sell_pct=0.50, every=1)),
    ('缓冲20/50 每2期',         dict(buy_pct=0.20, sell_pct=0.50, every=2)),
    ('缓冲20/50 每3期(季度)',   dict(buy_pct=0.20, sell_pct=0.50, every=3)),
    ('缓冲20/60 每3期(季度)',   dict(buy_pct=0.20, sell_pct=0.60, every=3)),
    ('缓冲20/70 每3期(季度)',   dict(buy_pct=0.20, sell_pct=0.70, every=3)),
]

for N in [16, 20]:
    rows = []
    for name, kw in CFG:
        if kw['buy_pct'] >= 1.0:
            r, tn = long_only(PANEL, n_hold=N, cost_rt=COST_10W)
        else:
            r, tn = long_only_buffer(PANEL, n_hold=N, cost_rt=COST_10W, **kw)
        if len(r) < 24:
            continue
        p = perf(r, bench_r, name)
        p['turnover_ann'] = round(tn.mean() * 12, 2)
        p['cost_drag'] = round(tn.mean() * 12 * COST_10W, 4)
        # 样本外单独看
        ro = r[[d for d in r.index if d >= OOS_LO]]
        po = perf(ro, bench_r, '') if len(ro) >= 24 else None
        p['OOS_excess'] = round(po['excess_ann'], 4) if po else np.nan
        p['OOS_IR'] = po['IR'] if po else np.nan
        rows.append(p)
    df = pd.DataFrame(rows)[['portfolio', 'turnover_ann', 'cost_drag',
                             'excess_ann', 'IR', 'OOS_excess', 'OOS_IR',
                             'excess_maxdd', 'maxdd']]
    print('=' * 118)
    print('N=%d   10万成本(0.65%%往返)   全区间2015-2025 + 样本外2021-2025' % N)
    print('=' * 118)
    print(df.to_string(index=False))
    print()


# %% [markdown]
# ## 测试 2：100股整数倍可行性（10万本金）

# %%
def lot_feasibility(panel, n_hold, capital):
    target = capital / float(n_hold)
    errs, skipped, tot = [], 0, 0
    for d in panel.index:
        if d not in fwd_ret:
            continue
        ts = pd.Timestamp(d)
        if ts not in close.index:
            continue
        sel = panel.loc[d].dropna().nlargest(n_hold).index
        px = close.loc[ts].reindex(sel).dropna()
        for p in px.values:
            tot += 1
            lot = p * 100
            if lot > target * 1.4:          # 一手就超目标40% → 实质买不了
                skipped += 1
                continue
            k = max(1, int(round(target / lot)))
            errs.append(abs(k * lot / target - 1))
    return (np.mean(errs) if errs else np.nan,
            skipped / float(tot) if tot else np.nan)


print('=' * 78)
print('100股整数倍误差   (target = 本金 / N)')
print('=' * 78)
print('%-10s %-10s %-14s %-16s' % ('本金', 'N', '单只目标', '平均|误差|  买不进占比'))
for cap in [100000, 500000]:
    for N in [16, 20, 30, 40]:
        e, sk = lot_feasibility(PANEL, N, cap)
        print('%-10s %-10d %-14s %.1f%%        %.1f%%'
              % ('%d万' % (cap / 10000), N, '%.0f元' % (cap / float(N)),
                 e * 100, sk * 100))


# %% [markdown]
# ## 判决：10万本金到底做不做

# %%
best_name, best_kw = ('缓冲20/60 每3期(季度)',
                      dict(buy_pct=0.20, sell_pct=0.60, every=3))
r_base, tn_base = long_only(PANEL, n_hold=16, cost_rt=COST_10W)
r_best, tn_best = long_only_buffer(PANEL, n_hold=16, cost_rt=COST_10W, **best_kw)

ro_base = r_base[[d for d in r_base.index if d >= OOS_LO]]
ro_best = r_best[[d for d in r_best.index if d >= OOS_LO]]
pb, pB = perf(ro_base, bench_r, ''), perf(ro_best, bench_r, '')

print('=' * 80)
print('10万本金 N=16 样本外(2021-2025) 对比')
print('=' * 80)
print('原始硬TopN每期:  换手%.0f%%  超额%+.2f%%  IR%.2f'
      % (tn_base.mean() * 1200, pb['excess_ann'] * 100, pb['IR']))
print('%s:  换手%.0f%%  超额%+.2f%%  IR%.2f'
      % (best_name, tn_best.mean() * 1200, pB['excess_ann'] * 100, pB['IR']))
print('改善: 超额 %+.2fpt,  IR %+.2f'
      % ((pB['excess_ann'] - pb['excess_ann']) * 100, pB['IR'] - pb['IR']))
print()
if pB['excess_ann'] < 0.02 or pB['IR'] < 0.3:
    print('>>> 判决: 10万本金不值得跑这个策略。')
    print('    换手抑制救不回来。建议直接买中证1000 ETF，')
    print('    或把本金提到50万以上再启用策略。')
else:
    print('>>> 判决: 换手抑制使10万本金变得可行。')
    print('    进入实盘工程化(风控/执行/死亡条件)。')
