# -*- coding: utf-8 -*-
# %% [markdown]
# # 多资产 ETF 动量轮动 — 【训练集】研究
#
# # ⛔ 数据边界声明 —— 修改 TRAIN_END 即销毁测试集
#
# ```
# 训练集  2014-07 ~ 2022-12  (102个月)   ← 本 notebook 只取这段，可反复试
# ────────────────── 数据墙 ──────────────────
# 测试集  2023-01 ~ 2026-07  ( 43个月)   ← 物理上不取，冻结参数后只看一次
# ```
#
# **本 notebook 的 `TRAIN_END = '2022-12-31'` 是硬边界。**
# 把它改成更晚的日期 = 测试集永久作废。
# 「约定不看」是无效纪律——数据一旦取进来就一定会被看到，所以物理上不取。
#
# 测试集在另一个 notebook (`etf_rotation_holdout.ipynb`) 里跑，
# 该文件在训练结束、参数写入冻结规格之后才创建。
#
# ---
#
# ## 测试集能检测什么（先算清，防止事后过度解读）
#
# 夏普标准误 ≈ √[(1+S²/2)/T]，T 以年计：
#
# ```
# 43个月 = 3.6年 → 夏普标准误 ≈ 0.59
# 若真实夏普 0.7，观测值 95% 区间约 -0.5 ~ +1.9
# ```
#
# **43 个月无法确认夏普 0.7 非零，只能检测灾难性失败。**
# 定位：烟雾测试。真正的验证是前向模拟盘。
#
# ---
#
# ## 标的池的选择偏差（日期划分无法解决）
#
# 标的池是用后见之明挑的——纳指、黄金在 2013-2026 是明星资产。
# 这个偏差污染的是**标的池本身**，切日期救不了。两条并用：
#
# 1. 每个标的用**事前**资产配置逻辑辩护，不用表现：
#    A股宽基(300/500/创业板) + 防御风格(红利) + 海外分散(纳指)
#    + 实物资产(黄金) + 避险(国债)。这是 2013 年就说得出的标准菜单。
# 2. **同时跑「只含A股」变体**，量化超额里多少来自纳指/黄金。
#    若主要来自这两个 → 策略真实含义是「过去十年该买美股和黄金」。
#
# ---
#
# ## 为什么不设三段（训练/验证/测试）
#
# 有效数据仅约 145 个月，三分会让每段都太薄。
# 且已实测：**参数优化在此类问题上有害**
# （股票因子 IS/OOS 排序相关性 -0.815；walk-forward IR -0.04 输给先验固定 +0.26）。
# 既然不靠数据挑参数，就不需要「验证集」这个中间层。
#
# 本 notebook 的用途是**理解策略特性**，不是搜索最优参数。
# 最终配置用先验值（K=6, M=2），网格只用来看敏感性与稳健性。

# %%
from jqdata import *
import numpy as np
import pandas as pd
import pickle, os
from collections import OrderedDict
from datetime import date
import matplotlib
import matplotlib.pyplot as plt
%matplotlib inline

pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 60)

# ==================== 数据边界 ====================
FETCH_START = '2013-06-01'      # 含动量回看所需的前置数据
TRAIN_END   = '2022-12-31'      # ⛔ 硬边界。改晚 = 测试集作废
# =================================================

CACHE = 'etf_cache_train'       # 训练集独立缓存, 与测试集物理隔离
if not os.path.exists(CACHE):
    os.makedirs(CACHE)

assert TRAIN_END == '2022-12-31', \
    '数据边界被修改。若确实要越界, 必须先在冻结规格中登记测试集作废。'

def cache(name, fn):
    p = os.path.join(CACHE, name + '.pkl')
    if os.path.exists(p):
        with open(p, 'rb') as f:
            print('[cache hit ] %s' % name); return pickle.load(f)
    o = fn()
    with open(p, 'wb') as f: pickle.dump(o, f)
    print('[cache save] %s' % name); return o

# 标的池: 每个都有事前的资产配置理由(见上方声明)
UNIVERSE = OrderedDict([
    ('510300.XSHG', '沪深300'),     # A股大盘
    ('510500.XSHG', '中证500'),     # A股中盘
    ('159915.XSHE', '创业板'),      # A股成长
    ('510880.XSHG', '红利'),        # 防御风格
    ('513100.XSHG', '纳指'),        # 海外分散
    ('518880.XSHG', '黄金'),        # 实物资产
])
ASHARE_ONLY = ['510300.XSHG', '510500.XSHG', '159915.XSHE', '510880.XSHG']
SAFE  = '511010.XSHG'           # 国债ETF: 绝对动量为负时的避险仓
BENCH = '000852.XSHG'           # 对照基准: 中证1000

COST_RT = 0.0016                # ETF往返: 佣金万0.85×2 + 无印花税 + 价差约0.05%×2


# %% [markdown]
# ## 1. 取数（只到 TRAIN_END）

# %%
def fetch():
    out = {}
    for c in list(UNIVERSE.keys()) + [SAFE]:
        s = get_price(c, start_date=FETCH_START, end_date=TRAIN_END,
                      frequency='daily', fields=['close'], fq='pre')['close'].dropna()
        s.index = pd.to_datetime(s.index)
        out[c] = s
        print('  %-16s %-8s %s ~ %s  (%d bars)'
              % (c, UNIVERSE.get(c, '国债'), s.index[0].date(), s.index[-1].date(), len(s)))
    b = get_price(BENCH, start_date=FETCH_START, end_date=TRAIN_END,
                  frequency='daily', fields=['close'], fq='pre')['close'].dropna()
    b.index = pd.to_datetime(b.index)
    out['__bench__'] = b
    return out

px = cache('prices_train', fetch)
bench_px = px.pop('__bench__')
prices = pd.DataFrame(px).sort_index()

# 起点受三个约束, 取最晚者:
#   1) 全部ETF都有数据(黄金ETF 518880 于2013-07上市)
#   2) 基准中证1000指数有数据(该指数2014-10-17才发布, 聚宽无更早数据)
#   3) 后续动量回看还要再往后推 K 个月
etf_from = prices.dropna().index[0]
bench_from = bench_px.index[0]
valid_from = max(etf_from, bench_from)
print('\n起点约束: ETF齐备 %s | 基准可用 %s | 采用 %s'
      % (etf_from.date(), bench_from.date(), valid_from.date()))

prices = prices.loc[valid_from:]
bench_px = bench_px.loc[valid_from:]

# 只保留 ETF 与基准都有的交易日, 避免后续按日期取值时 KeyError
both = prices.index.intersection(bench_px.index)
prices = prices.loc[both]
bench_px = bench_px.loc[both]

ym = pd.Series(prices.index).dt.strftime('%Y-%m')
rebal = pd.Series(prices.index).groupby(ym).max().sort_values().tolist()
print('共同交易日 %d  末点 %s' % (len(both), prices.index[-1].date()))
print('调仓期数 %d' % len(rebal))
assert prices.index[-1] <= pd.Timestamp(TRAIN_END), '越界!'


# %% [markdown]
# ## 2. 策略引擎
#
# - 动量 = 过去 K 个月收益率
# - 横截面：选动量最高的 M 只，等权
# - **绝对动量过滤**：选中标的自身动量 < 0 时，该仓位换成国债ETF
# - 成本：单边换手比例 × 往返成本

# %%
MAX_K = 12      # 网格中最大回看月数。所有配置统一从第 MAX_K 期开始评估,
                # 否则 K=1 会多吃到早期月份(含2015股灾)而 K=12 吃不到, 网格数字不可比。

def run(K, M, risk_assets=None, abs_filter=True, cost_rt=COST_RT):
    assert K <= MAX_K, 'K 超过 MAX_K, 会破坏配置间可比性'
    risk = risk_assets if risk_assets else list(UNIVERSE.keys())
    rets, turns, hist = {}, {}, {}
    held = set()
    for i in range(MAX_K, len(rebal) - 1):
        t0, t1, tb = rebal[i], rebal[i + 1], rebal[i - K]
        mom = (prices.loc[t0, risk] / prices.loc[tb, risk] - 1).dropna()
        if len(mom) < M:
            continue
        sel = list(mom.sort_values(ascending=False).index[:M])
        if abs_filter:
            sel = [s if mom[s] > 0 else SAFE for s in sel]
        new = set(sel)
        turn = len(new - held) / float(len(sel))
        w = pd.Series(1.0 / len(sel), index=sel).groupby(level=0).sum()
        r = prices.loc[t1, w.index] / prices.loc[t0, w.index] - 1
        rets[t0.date()] = float((r * w).sum()) - turn * cost_rt
        turns[t0.date()] = turn
        hist[t0.date()] = sel
        held = new
    return pd.Series(rets).sort_index(), pd.Series(turns).sort_index(), hist


# 基准与买入持有也统一到同一评估窗口
bench_r = pd.Series({rebal[i].date(): float(bench_px.loc[rebal[i+1]] / bench_px.loc[rebal[i]] - 1)
                     for i in range(MAX_K, len(rebal) - 1)}).sort_index()
print('统一评估窗口: %s ~ %s (%d个月)'
      % (bench_r.index[0], bench_r.index[-1], len(bench_r)))

def maxdd(nav): return float((nav / nav.cummax() - 1).min())

def perf(r, label):
    b = bench_r.reindex(r.index).fillna(0)
    n = len(r); nav = (1 + r).cumprod(); ex = r - b
    return OrderedDict([
        ('strategy', label), ('n_m', n),
        ('ann_ret', round(nav.iloc[-1] ** (12.0 / n) - 1, 4)),
        ('bench_ann', round((1 + b).cumprod().iloc[-1] ** (12.0 / n) - 1, 4)),
        ('excess_ann', round((1 + ex).cumprod().iloc[-1] ** (12.0 / n) - 1, 4)),
        ('vol', round(r.std() * np.sqrt(12), 4)),
        ('sharpe', round(r.mean() / r.std() * np.sqrt(12), 2) if r.std() else np.nan),
        ('maxdd', round(maxdd(nav), 4)),
        ('IR', round(ex.mean() / ex.std() * np.sqrt(12), 2) if ex.std() else np.nan),
        ('win_m', round((r > 0).mean(), 3)),
    ])

def sub(r, lo, hi):
    return r[[d for d in r.index if (lo is None or d >= lo) and (hi is None or d < hi)]]


# %% [markdown]
# ## 3. 参数敏感性（全表，不挑峰值）
#
# 训练集内再分两段做稳健性检查——这不是样本外，只是看结论是否依赖单一时期。

# %%
SPLIT = date(2019, 1, 1)
GRID_K, GRID_M = [1, 3, 6, 9, 12], [1, 2, 3]

rows, store = [], {}
for K in GRID_K:
    for M in GRID_M:
        r, tn, _ = run(K, M)
        if len(r) < 36: continue
        store[(K, M)] = r
        pa, p1, p2 = perf(r, ''), perf(sub(r, None, SPLIT), ''), perf(sub(r, SPLIT, None), '')
        rows.append(OrderedDict([
            ('config', 'K=%d,M=%d' % (K, M)),
            ('ann', pa['ann_ret']), ('sharpe', pa['sharpe']), ('maxdd', pa['maxdd']),
            ('前段sharpe', p1['sharpe']), ('后段sharpe', p2['sharpe']),
            ('excess', pa['excess_ann']), ('IR', pa['IR']),
            ('turnover', round(tn.mean() * 12, 2)),
        ]))
grid = pd.DataFrame(rows)
print('=' * 122)
print('参数敏感性 [训练集 %s ~ %s]  前段<2019, 后段>=2019' % (rebal[0].date(), rebal[-1].date()))
print('=' * 122)
print(grid.sort_values('sharpe', ascending=False).to_string(index=False))
print('\n夏普为正的配置 %d/%d   中位夏普 %.2f' % ((grid['sharpe'] > 0).sum(), len(grid), grid['sharpe'].median()))
print('前后两段夏普排序相关性 %.3f' % grid['前段sharpe'].corr(grid['后段sharpe'], method='spearman'))
print('  (接近0或为负 → 参数选择在训练集内部就不稳定, 更应坚持先验固定值)')


# %% [markdown]
# ## 4. 先验固定参数 K=6,M=2 + 标的池偏差检验

# %%
PRIOR = (6, 2)
r_p,  tn_p,  hist_p = run(*PRIOR)
r_a,  tn_a,  _      = run(*PRIOR, risk_assets=ASHARE_ONLY)
r_nf, _, _          = run(*PRIOR, abs_filter=False)
r_fr, _, _          = run(*PRIOR, cost_rt=0.0)

def bh(code):
    return pd.Series({rebal[i].date(): float(prices.loc[rebal[i+1], code] / prices.loc[rebal[i], code] - 1)
                      for i in range(MAX_K, len(rebal) - 1)}).sort_index().reindex(r_p.index).fillna(0)

rows = [perf(r_p, '轮动 K=6,M=2 全标的池'),
        perf(r_a, '轮动 K=6,M=2 【仅A股】'),
        perf(r_nf, '轮动 无绝对动量过滤'),
        perf(r_fr, '轮动 零成本'),
        perf(bh('510300.XSHG'), '买入持有 沪深300'),
        perf(bh('510500.XSHG'), '买入持有 中证500'),
        perf(bench_r.reindex(r_p.index).fillna(0), '买入持有 中证1000')]
print('=' * 125)
print('先验固定参数 + 变体对照 [训练集]')
print('=' * 125)
print(pd.DataFrame(rows).to_string(index=False))

pf, pa_ = perf(r_p, ''), perf(r_a, '')
print('\n>>> 标的池偏差: 全池年化 %.2f%% vs 仅A股 %.2f%%, 差 %.2f 个点'
      % (pf['ann_ret'] * 100, pa_['ann_ret'] * 100, (pf['ann_ret'] - pa_['ann_ret']) * 100))
print('    若差距很大 → 策略主要价值来自「持有纳指/黄金」这个资产配置决定,')
print('    而非「动量轮动」这个信号。这是后见之明选池造成的, 无法用日期划分修正。')
print('\n年化单边换手 %.0f%%  成本拖累 %.2f%%/年  国债避险月份占比 %.1f%%'
      % (tn_p.mean() * 1200, tn_p.mean() * 12 * COST_RT * 100,
         100.0 * sum(1 for v in hist_p.values() if SAFE in v) / len(hist_p)))

cnt = pd.Series([s for v in hist_p.values() for s in v]).value_counts()
print('\n各标的被持有月数:')
for c, n in cnt.items():
    print('  %-16s %-8s %d 个月 (%.0f%%)' % (c, UNIVERSE.get(c, '国债'), n, 100.0 * n / len(hist_p)))


# %% [markdown]
# ## 5. 分年度

# %%
yr = pd.DataFrame({
    'strategy': r_p.groupby(pd.Series(r_p.index).apply(lambda x: x.year).values).apply(lambda s: (1+s).prod()-1),
    'A股Only':  r_a.groupby(pd.Series(r_a.index).apply(lambda x: x.year).values).apply(lambda s: (1+s).prod()-1),
    'CSI1000': bench_r.reindex(r_p.index).fillna(0)
                 .groupby(pd.Series(r_p.index).apply(lambda x: x.year).values).apply(lambda s: (1+s).prod()-1),
})
yr['excess'] = yr['strategy'] - yr['CSI1000']
print('---- 分年度 (%) 训练集 ----')
print((yr * 100).round(1).to_string())
print('\n策略为正 %d/%d   超额为正 %d/%d'
      % ((yr['strategy'] > 0).sum(), len(yr), (yr['excess'] > 0).sum(), len(yr)))


# %% [markdown]
# ## 6. 图 + 训练集小结

# %%
fig, axes = plt.subplots(2, 2, figsize=(16, 9))
ax = axes[0][0]
for r, l in [(r_p, 'Rotation full'), (r_a, 'Rotation A-share only'),
             (bench_r.reindex(r_p.index).fillna(0), 'CSI1000')]:
    ax.plot(r.index, (1 + r).cumprod().values, label=l, lw=2 if 'full' in l else 1.2)
ax.set_yscale('log'); ax.set_title('NAV (train)'); ax.legend(fontsize=8); ax.grid(alpha=.3)

ax = axes[0][1]
for (K, M), r in sorted(store.items()):
    if M == 2: ax.plot(r.index, (1 + r).cumprod().values, label='K=%d' % K)
ax.set_yscale('log'); ax.set_title('Lookback sensitivity (M=2)'); ax.legend(fontsize=8); ax.grid(alpha=.3)

ax = axes[1][0]
nav = (1 + r_p).cumprod()
ax.fill_between(nav.index, (nav / nav.cummax() - 1).values * 100, 0, color='r', alpha=.4)
ax.set_title('Drawdown %'); ax.grid(alpha=.3)

ax = axes[1][1]
x = np.arange(len(yr))
ax.bar(x - .2, yr['strategy'].values * 100, .4, label='strategy')
ax.bar(x + .2, yr['CSI1000'].values * 100, .4, label='CSI1000')
ax.set_xticks(x); ax.set_xticklabels(yr.index, rotation=45); ax.axhline(0, color='k', lw=.8)
ax.set_title('Yearly %'); ax.legend(); ax.grid(alpha=.3)
plt.tight_layout(); plt.savefig('etf_train.png', dpi=110)
grid.to_csv('etf_grid_train.csv', index=False, encoding='utf-8-sig')
print('已导出 etf_train.png / etf_grid_train.csv'); plt.show()

print('\n' + '=' * 74)
print('训练集小结 (先验 K=6,M=2)  —— 这不是验证结果')
print('=' * 74)
print('年化 %.2f%%  夏普 %.2f  回撤 %.2f%%  超额 %+.2f%%  IR %.2f  换手 %.0f%%'
      % (pf['ann_ret']*100, pf['sharpe'], pf['maxdd']*100,
         pf['excess_ann']*100, pf['IR'], tn_p.mean()*1200))
print('网格夏普为正 %d/%d, 中位 %.2f' % ((grid['sharpe'] > 0).sum(), len(grid), grid['sharpe'].median()))
print('\n下一步: 把参数写入冻结规格, 然后才创建 holdout notebook 跑 2023-01~2026-07。')
print('        测试集只能看一次, 且只能检测灾难性失败(夏普标准误约0.59)。')
