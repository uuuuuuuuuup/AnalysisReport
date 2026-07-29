# -*- coding: utf-8 -*-
# %% [markdown]
# # 可转债经典双低 — 【测试集】验证
#
# # ⛔ 本 notebook 只能用一次
#
# ```
# 训练集  2019-01 ~ 2022-12  ( 48个月)   ← 训练 notebook: cb_multifactor.py
# ────────────────── 数据墙 ──────────────────
# 测试集  2023-01 ~ 2026-07  ( 43个月)   ← 本 notebook
# ```
#
# **冻结规格**: `cb_freeze_spec.md`
#
# 本 notebook 设计约束：
# - 只跑冻结配置（经典双低 N=20）
# - 额外跑纯 premium 作为对照记录（非决策依据）
# - 不跑参数网格、不探索变体
# - 跑完即冻结测试集消耗记录
#
# ---
#
# ## 预先承诺的判定规则（来自冻结规格）
#
# | 观测夏普 (rf=0) | 解读 | 动作 |
# |---|---|---|
# | > -0.50 | 落在预期分布内，不构成任何证据 | 照常进入实盘 |
# | < -0.50 | 超出 95% 区间下沿 | 停止，重新审查 |
#
# | 观测最大回撤 | 解读 |
# |---|---|
# | 优于 -30%（训练集2倍） | 正常 |
# | 差于 -30% | 红旗 |
#
# | 观测信用事件 | 解读 |
# |---|---|
# | 持仓中出现违约/退市 | 信用过滤失败 |
# | 无违约 | 过滤有效 |
#

# %%
from jqdata import *
import numpy as np
import pandas as pd
import pickle, os, warnings
from datetime import date
from collections import OrderedDict
import matplotlib
import matplotlib.pyplot as plt
%matplotlib inline

warnings.filterwarnings('ignore')
pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 60)

# ==================== 数据边界 ====================
TEST_START = '2023-01-01'
TEST_END   = '2026-07-29'
FETCH_START = '2022-07-01'     # 为动量/缓冲带提供前置数据
# =================================================

CACHE = 'cb_cache_test'
if not os.path.exists(CACHE):
    os.makedirs(CACHE)

def cache(name, fn):
    p = os.path.join(CACHE, name + '.pkl')
    if os.path.exists(p):
        with open(p, 'rb') as f:
            print('[cache hit ] %s' % name); return pickle.load(f)
    o = fn()
    with open(p, 'wb') as f: pickle.dump(o, f)
    print('[cache save] %s' % name); return o

# ---- 冻结参数 ----
PRIOR_N = 20
BUFFER_N = 25      # 缓冲带: 前25名中已在仓的保留
COST_RT = 0.0017   # 往返成本

# ---- 信用过滤 ----
CREDIT_PRICE_THRESHOLD = 80     # 转债价格低于此触发检查
CREDIT_PREMIUM_THRESHOLD = 100  # 转股溢价率高于此 + 低价 = 疑似违约定价


# %% [markdown]
# ## 1. 取数

# %%
# 可转债基本信息
def fetch_cb_info():
    from jqdata import bond
    df = bond.run_query(query(
        bond.CONBOND_BASIC_INFO.code,
        bond.CONBOND_BASIC_INFO.short_name,
        bond.CONBOND_BASIC_INFO.company_code,
        bond.CONBOND_BASIC_INFO.list_date,
        bond.CONBOND_BASIC_INFO.maturity_date,
        bond.CONBOND_BASIC_INFO.actual_raise_fund,
        bond.CONBOND_BASIC_INFO.exchange_code,
    ))
    xchg_map = {705001: 'XSHG', 705002: 'XSHE', 705003: 'XSHE',
                705004: 'XSHE', 705005: 'XSHG', 705006: 'XSHE'}
    df['suffix'] = df['exchange_code'].map(xchg_map).fillna('XSHE')
    df['cb_code'] = df['code'].astype(str) + '.' + df['suffix']
    df = df[df['company_code'].notna() & df['list_date'].notna() & df['maturity_date'].notna()]
    df['list_date'] = pd.to_datetime(df['list_date'])
    df['maturity_date'] = pd.to_datetime(df['maturity_date'])
    print('可转债: %d 只' % len(df))
    return df

cb_info = cache('cb_basic_info_test', fetch_cb_info)


# %%
# 可转债日行情（用 bond.run_query）
def fetch_cb_prices():
    from jqdata import bond
    all_dates = sorted(set(get_trade_days(start_date=FETCH_START, end_date=TEST_END)))
    all_dates = pd.to_datetime(all_dates)
    print('交易日: %d' % len(all_dates))

    batch_days = 10
    frames = []
    for i in range(0, len(all_dates), batch_days):
        batch = all_dates[i:i + batch_days]
        d0 = batch[0].strftime('%Y-%m-%d')
        d1 = batch[-1].strftime('%Y-%m-%d')
        try:
            df = bond.run_query(query(
                bond.CONBOND_DAILY_PRICE.date,
                bond.CONBOND_DAILY_PRICE.code,
                bond.CONBOND_DAILY_PRICE.close,
            ).filter(
                bond.CONBOND_DAILY_PRICE.date >= d0,
                bond.CONBOND_DAILY_PRICE.date <= d1,
            ))
            if df is not None and len(df) > 0:
                frames.append(df)
        except Exception as e:
            pass

    raw = pd.concat(frames, ignore_index=True)
    raw['date'] = pd.to_datetime(raw['date'])
    code_to_suffix = cb_info.set_index('code')['suffix'].to_dict()
    raw['cb_code'] = raw['code'].astype(str).map(
        lambda c: str(c) + '.' + code_to_suffix.get(str(c), 'XSHE'))
    prices = raw.pivot_table(values='close', index='date', columns='cb_code', aggfunc='last')
    prices = prices.sort_index()
    print('价格面板: %d 交易日 x %d CB' % (len(prices), len(prices.columns)))
    return prices

prices = cache('cb_prices_test', fetch_cb_prices)

# 只看测试段
test_prices = prices[prices.index >= TEST_START]
print('测试段: %s ~ %s  (%d 天)'
      % (test_prices.index[0].date(), test_prices.index[-1].date(), len(test_prices)))


# %%
# 转股溢价率
def fetch_convert_stats():
    from jqdata import bond
    all_dates = sorted(set(get_trade_days(start_date=FETCH_START, end_date=TEST_END)))
    all_dates = pd.to_datetime(all_dates)

    # 只取每月最后3个交易日
    ym = pd.Series(all_dates).dt.strftime('%Y-%m')
    month_ends_list = []
    for _ym, grp in pd.Series(all_dates).groupby(ym):
        month_ends_list.extend(grp.iloc[-3:].tolist())
    month_ends = sorted(set(month_ends_list))
    month_ends = pd.to_datetime(month_ends)

    date_batches = [month_ends[i:i+5] for i in range(0, len(month_ends), 5)]
    frames = []
    for batch_dates in date_batches:
        d0 = batch_dates[0].strftime('%Y-%m-%d')
        d1 = batch_dates[-1].strftime('%Y-%m-%d')
        try:
            df = bond.run_query(query(
                bond.CONBOND_DAILY_CONVERT.date,
                bond.CONBOND_DAILY_CONVERT.code,
                bond.CONBOND_DAILY_CONVERT.convert_premium_rate,
                bond.CONBOND_DAILY_CONVERT.convert_price,
            ).filter(
                bond.CONBOND_DAILY_CONVERT.date >= d0,
                bond.CONBOND_DAILY_CONVERT.date <= d1,
            ))
            if df is not None and len(df) > 0:
                frames.append(df)
        except Exception as e:
            pass

    df = pd.concat(frames, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'])
    code_to_suffix = cb_info.set_index('code')['suffix'].to_dict()
    df['cb_code'] = df['code'].astype(str).map(
        lambda c: str(c) + '.' + code_to_suffix.get(str(c), 'XSHE'))
    print('转股统计: %d 行' % len(df))
    return df

convert_stats = cache('cb_convert_stats_test', fetch_convert_stats)


# %%
# 正股 ST 状态（用于信用过滤）
def fetch_st_status():
    """获取所有正股的ST状态历史。"""
    stock_codes = sorted(cb_info['company_code'].dropna().unique().tolist())
    # 用 get_extras 获取ST状态
    try:
        st_df = get_extras('is_st', stock_codes,
                          start_date=FETCH_START, end_date=TEST_END, df=True)
        print('ST状态: %d 天 x %d 股票' % (len(st_df), len(st_df.columns)))
        return st_df
    except Exception as e:
        print('get_extras 失败: %s, 将跳过ST过滤' % str(e)[:80])
        return None

st_status = cache('st_status_test', fetch_st_status)


# %% [markdown]
# ## 2. 策略引擎（冻结配置）

# %%
# 调仓日期
ym_series = pd.Series(test_prices.index).dt.strftime('%Y-%m')
rebal_dates = pd.Series(test_prices.index).groupby(ym_series).last().sort_values().tolist()
rebal_dates = pd.to_datetime(rebal_dates)
rebal = rebal_dates[1:]  # 第一个月用于动量参考
print('测试段调仓: %d 期  (%s ~ %s)'
      % (len(rebal), rebal[0].date(), rebal[-1].date()))

# 构建每期池子: 已上市 + 距到期>12月
cb_info_idx = cb_info.set_index('cb_code')
code_to_stock = cb_info.set_index('cb_code')['company_code'].to_dict()

def build_pool(dt):
    """返回当天合格的可转债列表（不含信用过滤，那在打分时做）。"""
    valid = []
    for cb in prices.columns:
        if cb not in cb_info_idx.index:
            continue
        info = cb_info_idx.loc[cb]
        if pd.isna(info['list_date']) or pd.isna(info['maturity_date']):
            continue
        if info['list_date'] > dt:
            continue
        if info['maturity_date'] <= dt + pd.DateOffset(months=12):
            continue
        if dt not in prices.index or pd.isna(prices.loc[dt, cb]) or prices.loc[dt, cb] <= 0:
            continue
        valid.append(cb)
    return valid


def is_credit_risky(cb_code, dt, price, premium_rate):
    """信用风险过滤: ST正股 或 低价+超高溢价(市场已定价违约)。"""
    # 检查ST
    stk = code_to_stock.get(cb_code)
    if stk and st_status is not None:
        try:
            # 查最近20个交易日内是否有ST
            st_dates = st_status.index[st_status.index <= dt]
            if len(st_dates) > 0:
                recent_st = st_status.loc[st_dates[-20:], stk] if stk in st_status.columns else pd.Series()
                if len(recent_st) > 0 and recent_st.any():
                    return True
        except (KeyError, IndexError):
            pass

    # 检查低价+高溢价（疑似违约定价）
    if price < CREDIT_PRICE_THRESHOLD and premium_rate > CREDIT_PREMIUM_THRESHOLD:
        return True

    return False


def score_candidates_classic(dt):
    """经典双低打分: 0.5*z(price低) + 0.5*z(premium低)。含信用过滤。"""
    candidates = build_pool(dt)
    if len(candidates) < BUFFER_N:
        return None

    # 当天价格
    cb_close = prices.loc[dt, candidates].dropna()

    # 当天溢价率
    day_conv = convert_stats[convert_stats['date'] == dt].set_index('cb_code')
    premium = day_conv['convert_premium_rate'].reindex(cb_close.index)

    # 合并
    valid = pd.DataFrame({'price': cb_close, 'premium': premium}).dropna()
    if len(valid) < BUFFER_N:
        return None

    # 信用过滤
    risky = []
    for cb in valid.index:
        if is_credit_risky(cb, dt, valid.loc[cb, 'price'], valid.loc[cb, 'premium']):
            risky.append(cb)
    if risky:
        valid = valid.drop(risky)

    if len(valid) < BUFFER_N:
        return None

    # z-score + 等权
    for col in ['price', 'premium']:
        s = valid[col]
        sd = s.std()
        if not sd or sd == 0:
            valid[col + '_z'] = 0.0
        else:
            valid[col + '_z'] = (s - s.mean()) / sd

    # price越低越好(premium也一样), 所以取负
    valid['score'] = 0.5 * (-valid['price_z']) + 0.5 * (-valid['premium_z'])
    return valid['score'].dropna().sort_values(ascending=False)


def score_candidates_premium_only(dt):
    """纯premium对照(非决策依据)。"""
    candidates = build_pool(dt)
    if len(candidates) < BUFFER_N:
        return None
    cb_close = prices.loc[dt, candidates].dropna()
    day_conv = convert_stats[convert_stats['date'] == dt].set_index('cb_code')
    premium = day_conv['convert_premium_rate'].reindex(cb_close.index)
    valid = pd.DataFrame({'price': cb_close, 'premium': premium}).dropna()
    if len(valid) < BUFFER_N:
        return None
    # 信用过滤
    risky = []
    for cb in valid.index:
        if is_credit_risky(cb, dt, valid.loc[cb, 'price'], valid.loc[cb, 'premium']):
            risky.append(cb)
    if risky:
        valid = valid.drop(risky)
    if len(valid) < BUFFER_N:
        return None
    s = valid['premium']
    sd = s.std()
    if not sd or sd == 0:
        valid['score'] = 0.0
    else:
        valid['score'] = -(s - s.mean()) / sd
    return valid['score'].dropna().sort_values(ascending=False)


def select_with_buffer(scores, held):
    """缓冲带选股: 前 BUFFER_N 名中已在仓的保留，其余按排名补足 N。"""
    candidates = list(scores.index[:BUFFER_N])

    # 已在仓且在候选池中 → 优先保留
    keep = [s for s in candidates if s in held]
    # 候选池中不在仓的 → 候补
    fresh = [s for s in candidates if s not in held]

    # 保留在仓的 + 候补补足
    selected = keep[:PRIOR_N]  # 在仓的太多则截断
    needed = PRIOR_N - len(selected)
    if needed > 0:
        selected.extend(fresh[:needed])

    return selected


def run_strategy(score_fn, label=''):
    rets, turns, hist, credit_hits = {}, {}, {}, {}
    held = set()

    for i in range(len(rebal) - 1):
        t0, t1 = rebal[i], rebal[i + 1]
        scores = score_fn(t0)
        if scores is None or len(scores) < PRIOR_N:
            continue

        picks = select_with_buffer(scores, held)
        if len(picks) < PRIOR_N * 0.8:
            continue

        new_set = set(picks)
        turnover = len(new_set - held) / float(PRIOR_N)

        # 等权收益
        w = 1.0 / PRIOR_N
        r_sum = 0.0
        valid_n = 0
        for cb in picks:
            try:
                if cb in prices.columns and t0 in prices.index and t1 in prices.index:
                    p0 = prices.loc[t0, cb]
                    p1 = prices.loc[t1, cb]
                    if not pd.isna(p0) and not pd.isna(p1) and p0 > 0:
                        r_sum += (p1 / p0 - 1) * w
                        valid_n += 1
            except (KeyError, IndexError):
                pass

        if valid_n < PRIOR_N * 0.5:
            continue

        rets[t0.date()] = r_sum - turnover * COST_RT
        turns[t0.date()] = turnover
        hist[t0.date()] = picks
        held = new_set

        # 记录信用过滤命中
        credit_hits[t0.date()] = len([s for s in picks
                                      if is_credit_risky(s, t0,
                                          prices.loc[t0, s] if t0 in prices.index and s in prices.columns else 999,
                                          999)])

    return pd.Series(rets).sort_index(), pd.Series(turns).sort_index(), hist, credit_hits


# %% [markdown]
# ## 3. 跑测试

# %%
# 经典双低
r_cb, tn_cb, hist_cb, credit_cb = run_strategy(score_candidates_classic, '经典双低')

# 纯premium对照
r_pm, tn_pm, hist_pm, credit_pm = run_strategy(score_candidates_premium_only, '纯premium')

# 买入持有基准: 可转债等权指数代理(取所有活跃转债平均)
bench_ret = {}
for i in range(len(rebal) - 1):
    t0, t1 = rebal[i], rebal[i + 1]
    pool = build_pool(t0)
    if len(pool) < 10:
        continue
    r_avg = 0.0
    n_valid = 0
    for cb in pool:
        try:
            if t0 in prices.index and t1 in prices.index:
                p0 = prices.loc[t0, cb]
                p1 = prices.loc[t1, cb]
                if not pd.isna(p0) and not pd.isna(p1) and p0 > 0:
                    r_avg += (p1 / p0 - 1)
                    n_valid += 1
        except (KeyError, IndexError):
            pass
    if n_valid > 0:
        bench_ret[t0.date()] = r_avg / n_valid
bench_r = pd.Series(bench_ret).sort_index()


# %% [markdown]
# ## 4. 评估

# %%
def maxdd(nav):
    return float((nav / nav.cummax() - 1).min())

def perf(r, label=''):
    n = len(r)
    if n < 6:
        return None
    nav = (1 + r).cumprod()
    return OrderedDict([
        ('strategy', label), ('n_m', n),
        ('ann_ret', round(nav.iloc[-1] ** (12.0 / n) - 1, 4)),
        ('vol', round(r.std() * np.sqrt(12), 4)),
        ('sharpe', round(r.mean() / r.std() * np.sqrt(12), 2) if r.std() else np.nan),
        ('maxdd', round(maxdd(nav), 4)),
        ('win_m', round((r > 0).mean(), 3)),
        ('worst_m', round(r.min(), 4)),
    ])

# 对齐基准
bench_aligned = bench_r.reindex(r_cb.index).fillna(0)

rows = []
for r, name in [(r_cb, '经典双低 N=20 (冻结)'),
                (r_pm, '纯premium N=20 (对照)')]:
    if r is not None and len(r) >= 6:
        p = perf(r, name)
        ex = r - bench_aligned.reindex(r.index).fillna(0)
        p['excess_ann'] = round((1 + ex).cumprod().iloc[-1] ** (12.0 / len(ex)) - 1, 4)
        p['IR'] = round(ex.mean() / ex.std() * np.sqrt(12), 2) if ex.std() else np.nan
        rows.append(p)

if len(bench_r) >= 6:
    p_b = perf(bench_aligned.reindex(r_cb.index).fillna(0), 'CB等权基准')
    rows.append(p_b)

print('=' * 95)
print('测试集  %s ~ %s  (%d个月)'
      % (r_cb.index[0], r_cb.index[-1], len(r_cb)))
print('=' * 95)
print(pd.DataFrame(rows).to_string(index=False))

# 换手率
print('\n年化单边换手: 双低 %.0f%%  premium %.0f%%'
      % (tn_cb.mean() * 1200, tn_pm.mean() * 1200))

# 信用过滤命中
credit_total = sum(credit_cb.values())
print('信用过滤命中: %d 次 (共 %d 个调仓期)' % (credit_total, len(credit_cb)))


# %% [markdown]
# ## 5. 按预先承诺规则判定

# %%
p_cb = perf(r_cb, '')
sharpe_test = p_cb['sharpe']
dd_test = p_cb['maxdd']

print('=' * 60)
print('预先承诺规则判定')
print('=' * 60)
print('夏普(rf=0): %.2f  阈值: > -0.50' % sharpe_test)
print('最大回撤:  %.1f%%  阈值: 优于 -30%%' % (dd_test * 100))
print()

if sharpe_test > -0.50:
    print('✅ 夏普通过 — 落在预期分布内，不构成任何证据')
else:
    print('❌ 夏普未通过 — 超出95%%区间下沿，停止并重新审查')

if dd_test > -0.30:
    print('✅ 回撤通过 — 优于训练集2倍阈值')
else:
    print('❌ 回撤未通过 — 风险特征与训练集不符')

if sum(credit_cb.values()) == 0:
    print('✅ 无信用事件 — 过滤有效')
else:
    print('⚠ 信用过滤命中 %d 次 — 过滤在发挥作用，但需检查是否有漏网之鱼'
          % sum(credit_cb.values()))

print()
print('结论: ', end='')
if sharpe_test > -0.50 and dd_test > -0.30:
    print('照常进入实盘/模拟盘。')
else:
    print('停止，需人工复核。')
print()
print('⚠ 即使通过，43个月在统计上无法确认策略有效。')
print('  真正的验证是前向实盘记录。')


# %% [markdown]
# ## 6. 分年度 + 持仓分析

# %%
# 分年度
yr = r_cb.groupby(pd.Series(r_cb.index).apply(lambda x: x.year).values).apply(
    lambda s: (1 + s).prod() - 1)
print('---- 分年度(%) 测试集 ----')
print((yr * 100).round(1).to_string())

# 被选中最多的标的
cnt = pd.Series([cb for v in hist_cb.values() for cb in v]).value_counts()
print('\n被选中次数最多的10只可转债:')
for cb_code, n in cnt.head(10).items():
    name = cb_info_idx.loc[cb_code, 'short_name'] if cb_code in cb_info_idx.index else '?'
    print('  %-16s %-12s %d 次 (%.0f%%)' % (cb_code, name, n, 100.0 * n / len(hist_cb)))

# 信用过滤触发记录
if sum(credit_cb.values()) > 0:
    print('\n信用过滤触发详情（被排除的标的）:')
    # 后面在图表cell里展开


# %% [markdown]
# ## 7. 图表

# %%
fig, axes = plt.subplots(2, 2, figsize=(16, 9))

# NAV
ax = axes[0][0]
nav_cb = (1 + r_cb).cumprod()
ax.plot(nav_cb.index, nav_cb.values, label='经典双低 N=20 (冻结)', lw=2, color='steelblue')
nav_pm = (1 + r_pm).cumprod()
ax.plot(nav_pm.index, nav_pm.values, label='纯premium (对照)', lw=1.2, color='coral', ls='--')
nav_b = (1 + bench_aligned.reindex(r_cb.index).fillna(0)).cumprod()
ax.plot(nav_b.index, nav_b.values, label='CB等权基准', lw=1, color='gray', alpha=0.6)
ax.set_yscale('log')
ax.set_title('NAV (测试集)')
ax.legend(fontsize=8)
ax.grid(alpha=.3)

# 回撤
ax = axes[1][0]
dd = (nav_cb / nav_cb.cummax() - 1) * 100
ax.fill_between(dd.index, dd.values, 0, color='r', alpha=.4)
ax.set_title('回撤 % (经典双低)')
ax.grid(alpha=.3)

# 分年度
ax = axes[1][1]
x = np.arange(len(yr))
colors = ['steelblue' if v > 0 else 'tomato' for v in yr.values]
ax.bar(x, yr.values * 100, color=colors)
ax.set_xticks(x)
ax.set_xticklabels(yr.index, rotation=45)
ax.axhline(0, color='k', lw=.8)
ax.set_title('年度收益 %')
ax.grid(alpha=.3)

# 换手
ax = axes[0][1]
ax.plot(tn_cb.index, tn_cb.values * 100, 'o-', markersize=3, color='steelblue', label='双低')
ax.plot(tn_pm.index, tn_pm.values * 100, 's-', markersize=3, color='coral', label='premium')
ax.axhline(tn_cb.mean() * 100, color='steelblue', ls='--', lw=0.8)
ax.axhline(tn_pm.mean() * 100, color='coral', ls='--', lw=0.8)
ax.set_title('换手率 % (缓冲带后)')
ax.legend(fontsize=8)
ax.grid(alpha=.3)

plt.tight_layout()
plt.savefig('cb_holdout_test.png', dpi=110)
print('已导出 cb_holdout_test.png')
plt.show()


# %% [markdown]
# ## 测试集小结

print('\n' + '=' * 70)
print('测试集小结 — 可转债经典双低')
print('=' * 70)
print('测试段: %s ~ %s  (%d个月)' % (r_cb.index[0], r_cb.index[-1], len(r_cb)))
print()
print('经典双低:  年化 %.2f%%  夏普 %.2f  回撤 %.1f%%  月胜率 %.1f%%'
      % (p_cb['ann_ret'] * 100, p_cb['sharpe'], p_cb['maxdd'] * 100, p_cb['win_m'] * 100))
print('纯premium:  年化 %.2f%%  夏普 %.2f  回撤 %.1f%%'
      % (perf(r_pm, '')['ann_ret'] * 100, perf(r_pm, '')['sharpe'], perf(r_pm, '')['maxdd'] * 100))
print('CB等权基准: 年化 %.2f%%' % (perf(bench_aligned.reindex(r_cb.index).fillna(0), '')['ann_ret'] * 100))
print()
print('换手(缓冲带后): 双低 %.0f%%/年  premium %.0f%%/年'
      % (tn_cb.mean() * 1200, tn_pm.mean() * 1200))
print('信用过滤命中: %d 次' % sum(credit_cb.values()))
print()
print('训练集 vs 测试集:')
print('  年化:  15.32%% → %.2f%%' % (p_cb['ann_ret'] * 100))
print('  夏普:  1.05  → %.2f' % p_cb['sharpe'])
print('  回撤: -14.9%% → %.1f%%' % (p_cb['maxdd'] * 100))
print()
print('测试集已消耗。自此，唯一干净的验证途径是前向实盘/模拟盘。')
print('参数冻结于 cb_freeze_spec.md，禁止基于本测试集结果调参。')
