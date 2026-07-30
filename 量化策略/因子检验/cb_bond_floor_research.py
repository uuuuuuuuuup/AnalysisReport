# -*- coding: utf-8 -*-
# ============================================================
# 债底距离因子 — 可转债策略创新研究 (BigQuant Notebook)
# ============================================================
# ⛔ 数据边界：训练集 2019-01 ~ 2022-12 | 测试集 2023-01 ~ 2026-07 封存
#
# 核心假设：
#   纯双低用"价格低"作为安全边际的代理——但价格低不等于真安全。
#   真正的防御是债底（纯债价值）：如果现价接近/低于债底，最大下行
#   被未来现金流锁死；如果远高于债底，则完全依赖正股上涨。
#
#   新因子 f_floor_dist = (估算债底 - 现价) / 现价
#     > 0: 现价低于债底 → 安全，类似持有到期债券
#     < 0: 现价远高于债底 → 下行风险大，完全依赖股性
#
# 打分公式（先验固定）：
#   score = 0.50 × f_floor_dist + 0.50 × f_premium
#           (安全边际)                (上涨弹性)
#
# 对照基线：纯双低 (0.5×price + 0.5×premium)
# ============================================================

import dai
import pandas as pd
import numpy as np
import pickle
import os

pd.set_option('display.width', 300)
pd.set_option('display.max_columns', 30)

# ==================== 配置 ====================
START_DATE = '2019-01-01'
END_DATE   = '2025-12-31'

N_GROUPS   = 10
N_HOLD     = 20
W_FLOOR    = 0.50
W_PREMIUM  = 0.50

MIN_LIST_DAYS      = 30
MIN_TERM_MONTHS    = 12
CREDIT_PRICE_FLOOR = 80
CREDIT_PREMIUM_CEILING = 100
MOM_LOOKBACK       = 40
MOM_EXCLUDE_PCT    = 0.20

# 债底计算参数
DISCOUNT_RATE = 0.035       # 折现率 (国债+信用利差近似)

CACHE_DIR = 'cb_floor_cache'

# ⛔ ========== 数据墙 ==========
TRAIN_END_DATE  = '2022-12-31'
TEST_START_DATE = '2023-01-01'
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


# ============================================================
# 0. 字段发现：检查 cn_cbond_basic_info 可用列
# ============================================================
print('=' * 60)
print('0. CB 基础信息字段发现')
print('=' * 60)


def discover_cb_fields():
    """检查 cn_cbond_basic_info 表中有哪些可用字段。"""
    try:
        # 不加 SELECT 限制，尝试取几条看列名
        sample = dai.query("""
            SELECT *
            FROM cn_cbond_basic_info
            LIMIT 3
        """).df()
        print('cn_cbond_basic_info 可用列 (%d):' % len(sample.columns))
        for c in sample.columns:
            n_null = sample[c].isna().sum()
            dtype = sample[c].dtype
            vals = sample[c].dropna().head(2).tolist()
            print('  %-35s  %s  null=%d  sample=%s' % (c, str(dtype), n_null, str(vals)[:80]))
        return list(sample.columns)
    except Exception as e:
        print('⚠ 字段发现失败: %s' % str(e)[:100])
        print('  将使用保守字段集。')
        return []


CB_FIELDS = cache('cb_fields', discover_cb_fields)


# ============================================================
# 1. 拉取 CB 全量数据
# ============================================================
print('\n' + '=' * 60)
print('1. 拉取可转债数据')
print('=' * 60)


def fetch_cb_data():
    """拉取 CB 日线 + 带 coupon 的基本信息。"""
    # 直接查询已知可用字段（字段发现已在步骤0确认）
    select_cols = ['instrument', 'stock_code', 'maturity_date', 'list_date',
                   'issue_interest_rate', 'par_value']

    select_str = ', '.join(select_cols)
    print('查询字段: %s' % select_str)

    try:
        info = dai.query("""
            SELECT %s
            FROM cn_cbond_basic_info
            WHERE maturity_date IS NOT NULL
        """ % select_str).df()
    except Exception as e:
        print('⚠ 全字段查询失败: %s' % str(e)[:100])
        # 回退到最小字段集
        info = dai.query("""
            SELECT instrument, stock_code, maturity_date, list_date
            FROM cn_cbond_basic_info
            WHERE maturity_date IS NOT NULL
        """).df()

    info['maturity_date'] = pd.to_datetime(info['maturity_date'])
    info['list_date'] = pd.to_datetime(info['list_date'])
    print('CB基本信息: %d 只, 字段: %s' % (len(info), list(info.columns)))

    # 确认有哪些 coupon 相关字段可用
    coupon_field = None
    for c in ['issue_interest_rate', 'coupon_rate', 'interest_rate', 'coupon', 'rate']:
        if c in info.columns and info[c].notna().sum() > 10:
            coupon_field = c
            break

    if coupon_field:
        print('✓ 票面利率字段: %s (有效值 %d/%d)'
              % (coupon_field, info[coupon_field].notna().sum(), len(info)))
        # 检查利率格式（可能是百分比如 1.5 或小数如 0.015）
        sample_vals = info[coupon_field].dropna().head(5)
        print('  样本值: %s' % sample_vals.tolist())
        # 如果中位数 > 1，可能是百分比格式，需要 /100
        if sample_vals.median() > 1:
            print('  检测到百分比格式，将自动 /100')
            info[coupon_field] = info[coupon_field] / 100.0
    else:
        print('⚠ 无票面利率字段，将使用默认值 2.0%')

    # 日线数据
    parts = []
    for year in range(2019, 2026):
        for m1, m2 in [(1, 6), (7, 12)]:
            d1 = '%d-%02d-01' % (year, m1)
            d2 = '%d-%02d-01' % (year + (1 if m2 == 12 else 0),
                                 1 if m2 == 12 else m2 + 1)
            if d2 > END_DATE:
                d2 = END_DATE
            if d1 >= d2 or d1 > END_DATE:
                continue
            try:
                part = dai.query("""
                    SELECT date, instrument, close, cb_over_rate AS premium_rate
                    FROM cn_cbond_bar1d_te
                    ORDER BY date
                """, filters={"date": [d1, d2]}).df()
                if len(part) > 0:
                    parts.append(part)
            except Exception as e:
                print('  [跳过] %s~%s: %s' % (d1, d2, str(e)[:60]))

    cb_df = pd.concat(parts, ignore_index=True)
    cb_df['date'] = pd.to_datetime(cb_df['date'])
    cb_df = cb_df.sort_values(['date', 'instrument']).reset_index(drop=True)

    # 合并基本信息
    for col in info.columns:
        if col not in cb_df.columns:
            info_map = info.set_index('instrument')
            cb_df[col] = cb_df['instrument'].map(info_map[col])

    print('CB日线: %d 行, %d 标的, %s ~ %s'
          % (len(cb_df), cb_df['instrument'].nunique(),
             cb_df['date'].min().strftime('%Y-%m-%d'),
             cb_df['date'].max().strftime('%Y-%m-%d')))

    return cb_df, info, coupon_field


cb_df, cb_info, COUPON_FIELD = cache('cb_floor_data', fetch_cb_data)


# ============================================================
# 2. 构建调仓日
# ============================================================
print('\n' + '=' * 60)
print('2. 构建调仓日')
print('=' * 60)

all_dates = sorted(cb_df['date'].unique())
all_dates = pd.to_datetime(all_dates)
months = pd.Series(all_dates).dt.to_period('M').unique()
rebal_days = sorted([max(all_dates[pd.Series(all_dates).dt.to_period('M') == m])
                      for m in months])
rebal_days = [d.date() for d in rebal_days]

print('调仓日: %d 个, %s ~ %s' % (len(rebal_days), rebal_days[0], rebal_days[-1]))

train_days = [d for d in rebal_days if d <= pd.Timestamp(TRAIN_END_DATE).date()]
test_days  = [d for d in rebal_days if d >= pd.Timestamp(TEST_START_DATE).date()]
print('训练集: %d 期 (%s ~ %s)' % (len(train_days), train_days[0], train_days[-1]))
print('测试集: %d 期 (%s ~ %s) ← ⛔ 封存' % (len(test_days), test_days[0], test_days[-1]))


# ============================================================
# 3. 工具函数
# ============================================================
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


def compute_bond_floor(coupon_rate, years_to_maturity, discount_rate=DISCOUNT_RATE,
                       par=100.0, payments_per_year=1):
    """
    计算纯债价值（未来现金流的净现值）。

    参数:
      coupon_rate: 票面利率 (如 0.02 = 2%)
      years_to_maturity: 剩余年数
      discount_rate: 折现率
      par: 面值 (通常是100)
      payments_per_year: 每年付息次数

    返回: 纯债价值估算
    """
    if years_to_maturity <= 0:
        return par

    n_payments = int(years_to_maturity * payments_per_year)
    if n_payments <= 0:
        return par

    dt = 1.0 / payments_per_year
    rate_per_period = discount_rate / payments_per_year
    coupon_per_period = coupon_rate * par / payments_per_year

    pv = 0.0
    for i in range(1, n_payments + 1):
        t = i * dt
        pv += coupon_per_period / ((1 + rate_per_period) ** i)

    pv += par / ((1 + rate_per_period) ** n_payments)
    return pv


# ============================================================
# 4. 构建因子
# ============================================================
print('\n' + '=' * 60)
print('4. 构建因子')
print('=' * 60)

# 获取 coupon 映射
if COUPON_FIELD:
    coupon_map = cb_info.set_index('instrument')[COUPON_FIELD].to_dict()
    # 填默认值
    for k in coupon_map:
        if pd.isna(coupon_map[k]):
            coupon_map[k] = 0.02
else:
    coupon_map = {}
print('有效票面利率映射: %d 只' % len(coupon_map))


# --- 4a. 债底距离因子 ---
def build_floor_factor():
    """逐期计算: f_floor_dist = (债底 - 现价) / 现价"""
    result = {}
    for i, d in enumerate(rebal_days):
        sub = cb_df[cb_df['date'] == pd.Timestamp(d)]
        if len(sub) < 20:
            continue

        floor_vals = {}
        for _, row in sub.iterrows():
            inst = row['instrument']
            price = row['close']
            if pd.isna(price) or price <= 0:
                continue

            mature = row.get('maturity_date')
            if pd.isna(mature):
                continue

            years_left = (pd.Timestamp(mature) - pd.Timestamp(d)).days / 365.25
            if years_left <= 0:
                continue

            cp = coupon_map.get(inst, 0.02)
            floor = compute_bond_floor(cp, years_left)

            # 债底距离: 正 = 有安全边际, 负 = 依赖股性
            floor_vals[inst] = (floor - price) / price

        if len(floor_vals) >= 20:
            s = pd.Series(floor_vals)
            s = winsorize_mad(s)
            s = zscore(s)                     # 越大 = 越安全
            result[d] = s

        if i % 12 == 0:
            n_pos = sum(1 for v in floor_vals.values() if v > 0)
            print('  %s: %d只  债底>现价=%d (%.0f%%)  均值=%.1f%%'
                  % (d, len(floor_vals), n_pos,
                     n_pos / len(floor_vals) * 100,
                     np.mean(list(floor_vals.values())) * 100))

    return pd.DataFrame(result).T


floor_factor = cache('factor_floor', build_floor_factor)
print('f_floor_dist: %d 期 × %d 标的' % floor_factor.shape)

# 打印统计
train_floor = floor_factor[floor_factor.index <= pd.Timestamp(TRAIN_END_DATE).date()]
print('训练集内统计: mean=%.4f  std=%.4f' % (train_floor.stack().mean(),
      train_floor.stack().std()))


# --- 4b. 溢价率因子 (复用) ---
premium_factor = {}
for d in rebal_days:
    sub = cb_df[cb_df['date'] == pd.Timestamp(d)]
    if len(sub) < 20:
        continue
    s = sub.set_index('instrument')['premium_rate'].dropna()
    if len(s) < 20:
        continue
    s = winsorize_mad(s)
    s = -zscore(s)            # 越低越好 → 取负
    premium_factor[d] = s
premium_factor = pd.DataFrame(premium_factor).T
print('f_premium: %d 期 × %d 标的' % premium_factor.shape)


# --- 4c. 价格因子 (纯双低用) ---
price_factor = {}
for d in rebal_days:
    sub = cb_df[cb_df['date'] == pd.Timestamp(d)]
    if len(sub) < 20:
        continue
    s = sub.set_index('instrument')['close'].dropna()
    s = s[s > 0]
    if len(s) < 20:
        continue
    s = winsorize_mad(s)
    s = -zscore(s)            # 越低越好 → 取负
    price_factor[d] = s
price_factor = pd.DataFrame(price_factor).T
print('f_price: %d 期 × %d 标的' % price_factor.shape)


# --- 4d. 合并打分 ---
# 债底增强: 50%债底距离 + 50%溢价率
common_dates = sorted(set(floor_factor.index) & set(premium_factor.index))
floor_enhanced = {}
for d in common_dates:
    fl = floor_factor.loc[d].dropna()
    pr = premium_factor.loc[d].dropna()
    common = sorted(set(fl.index) & set(pr.index))
    if len(common) >= 20:
        floor_enhanced[d] = W_FLOOR * fl[common] + W_PREMIUM * pr[common]
floor_enhanced = pd.DataFrame(floor_enhanced).T
print('floor_enhanced: %d 期 × %d 标的' % floor_enhanced.shape)

# 纯双低对照
common_dates2 = sorted(set(price_factor.index) & set(premium_factor.index))
pure_dl = {}
for d in common_dates2:
    p = price_factor.loc[d].dropna()
    pr = premium_factor.loc[d].dropna()
    common = sorted(set(p.index) & set(pr.index))
    if len(common) >= 20:
        pure_dl[d] = 0.5 * p[common] + 0.5 * pr[common]
pure_dl = pd.DataFrame(pure_dl).T
print('pure_dl: %d 期 × %d 标的' % pure_dl.shape)


# ============================================================
# 5. 未来收益矩阵
# ============================================================
print('\n' + '=' * 60)
print('5. 未来收益矩阵')
print('=' * 60)

fwd_ret = {}
for i, d in enumerate(rebal_days[:-1]):
    next_d = rebal_days[i + 1]
    cur = cb_df[cb_df['date'] == pd.Timestamp(d)]
    nxt = cb_df[cb_df['date'] == pd.Timestamp(next_d)]
    if len(cur) == 0 or len(nxt) == 0:
        continue
    cur_px = cur.set_index('instrument')['close']
    nxt_px = nxt.set_index('instrument')['close']
    common = sorted(set(cur_px.index) & set(nxt_px.index))
    row = {}
    for inst in common:
        if cur_px[inst] > 0 and nxt_px[inst] > 0:
            row[inst] = nxt_px[inst] / cur_px[inst] - 1.0
    if row:
        fwd_ret[d] = pd.Series(row)
fwd_ret = pd.DataFrame(fwd_ret).T
print('未来收益: %d 期 × %d 标的' % fwd_ret.shape)


# ============================================================
# ⛔ 以下仅训练集
# ============================================================

def filter_train(factor_df):
    dates = [d for d in factor_df.index
             if d <= pd.Timestamp(TRAIN_END_DATE).date()]
    return factor_df.loc[dates]


def compute_ic_series(factor_df):
    factor_df = filter_train(factor_df)
    ics = []
    for d in factor_df.index:
        if d not in fwd_ret.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < 20:
            continue
        ic = pd.Series(f_s[common]).corr(pd.Series(r_s[common]), method='spearman')
        if not np.isnan(ic):
            ics.append({'date': d, 'ic': ic, 'n': len(common)})
    return pd.DataFrame(ics)


def layered_returns(factor_df):
    factor_df = filter_train(factor_df)
    all_layers = {g: [] for g in range(N_GROUPS)}
    for d in factor_df.index:
        if d not in fwd_ret.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < N_GROUPS * 3:
            continue
        vals = f_s[common]
        rets = r_s[common]
        order = vals.argsort()
        gs = len(common) // N_GROUPS
        for g in range(N_GROUPS):
            s_, e_ = g * gs, (g + 1) * gs if g < N_GROUPS - 1 else len(common)
            all_layers[g].append(rets.iloc[order[s_:e_]].mean())
    return {g: pd.Series(all_layers[g]) for g in range(N_GROUPS)}


def simulate_strategy(factor_df, n_hold):
    """选因子值最高的 n_hold 只，等权月频。"""
    factor_df = filter_train(factor_df)
    monthly_rets = {}
    for d in factor_df.index:
        if d not in fwd_ret.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret.loc[d].dropna()
        cur = cb_df[cb_df['date'] == pd.Timestamp(d)].set_index('instrument')

        eligible = set(f_s.index) & set(r_s.index)
        # 基础过滤
        for inst in list(eligible):
            if inst not in cur.index:
                eligible.discard(inst)
                continue
            mature = cur.loc[inst].get('maturity_date')
            if pd.notna(mature):
                ml = (pd.Timestamp(mature) - pd.Timestamp(d)).days / 30.0
                if ml < MIN_TERM_MONTHS:
                    eligible.discard(inst)
                    continue
            list_d = cur.loc[inst].get('list_date')
            if pd.notna(list_d):
                dl = (pd.Timestamp(d) - pd.Timestamp(list_d)).days
                if dl < MIN_LIST_DAYS:
                    eligible.discard(inst)
                    continue
            px = cur.loc[inst].get('close', np.nan)
            prem = cur.loc[inst].get('premium_rate', np.nan)
            if (pd.notna(px) and pd.notna(prem)
                    and px < CREDIT_PRICE_FLOOR
                    and prem > CREDIT_PREMIUM_CEILING):
                eligible.discard(inst)
                continue

        if len(eligible) < n_hold * 2:
            continue

        eligible_list = sorted(eligible)
        top_n = f_s[eligible_list].nlargest(min(n_hold, len(eligible_list))).index
        rets = r_s[top_n].dropna()
        if len(rets) >= n_hold * 0.5:
            monthly_rets[d] = rets.mean()

    return pd.Series(monthly_rets)


def strategy_stats(monthly_ret):
    if len(monthly_ret) < 6:
        return {}
    ann = monthly_ret.mean() * 12
    vol = monthly_ret.std() * np.sqrt(12)
    sr = ann / vol if vol > 0 else 0
    dd = (monthly_ret.cumsum() - monthly_ret.cumsum().cummax()).min()
    calmar = ann / abs(dd) if dd < 0 else 0
    wr = (monthly_ret > 0).mean()
    return {'年化%': ann * 100, '夏普': sr, '波动%': vol * 100,
            '回撤%': dd * 100, '卡玛': calmar, '月胜率': wr * 100,
            '月数': len(monthly_ret)}


# ============================================================
# 6. 单因子 IC 分析
# ============================================================
print('\n' + '=' * 60)
print('6. 单因子 IC 分析 (训练集)')
print('=' * 60)

for name, f_df, desc in [
    ('f_floor_dist', floor_factor, '债底距离(越大越安全)'),
    ('f_premium',   premium_factor, '低溢价率'),
    ('f_price',     price_factor,   '低价格(双低对照)'),
]:
    ic_df = compute_ic_series(f_df)
    if len(ic_df) == 0:
        print('%-18s: 无有效IC' % name)
        continue
    mean_ic = ic_df['ic'].mean()
    ic_ir = mean_ic / ic_df['ic'].std() if ic_df['ic'].std() > 0 else 0
    ic_pos = (ic_df['ic'] > 0).mean()
    print('%-18s  mean_IC=%+5.4f  IC_IR=%+6.2f  IC>0=%5.1f%%  N=%3d  (%s)'
          % (name, mean_ic, ic_ir, ic_pos * 100, len(ic_df), desc))


# ============================================================
# 7. 因子截面相关性
# ============================================================
print('\n' + '=' * 60)
print('7. 因子截面相关性 (训练集)')
print('=' * 60)

key_factors = {'f_floor_dist': floor_factor,
               'f_premium': premium_factor,
               'f_price': price_factor}
cdates = sorted(set.intersection(
    *[set(f.index) for f in key_factors.values()]))
cdates = [d for d in cdates if d <= pd.Timestamp(TRAIN_END_DATE).date()]

corr_mat = {}
for k1 in key_factors:
    corr_mat[k1] = {}
    for k2 in key_factors:
        corrs = []
        for d in cdates:
            s1 = key_factors[k1].loc[d].dropna()
            s2 = key_factors[k2].loc[d].dropna()
            common = sorted(set(s1.index) & set(s2.index))
            if len(common) >= 20:
                c = s1[common].corr(s2[common])
                if not np.isnan(c):
                    corrs.append(c)
        corr_mat[k1][k2] = np.mean(corrs) if corrs else np.nan

print(pd.DataFrame(corr_mat).round(3).to_string())

# 关键判断
f_fp = corr_mat['f_floor_dist'].get('f_price', 0)
print('\nf_floor_dist × f_price 相关: %.3f' % f_fp)
if abs(f_fp) > 0.7:
    print('→ 债底距离与价格高度同质，无增量价值')
elif abs(f_fp) > 0.4:
    print('→ 中度相关，有部分替代性')
else:
    print('→ 低相关，债底距离提供了独立信息')


# ============================================================
# 8. 分层收益
# ============================================================
print('\n' + '=' * 60)
print('8. 分层收益 (训练集)')
print('=' * 60)

for name, f_df, desc in [
    ('f_floor_dist', floor_factor, '债底距离'),
    ('f_premium',   premium_factor, '低溢价率'),
]:
    layers = layered_returns(f_df)
    print('\n--- %s ---' % desc)
    monthly = {}
    print('%-6s %8s %7s %7s %7s %6s' % ('分组', '年化%', '夏普', '波动%', '回撤%', '月数'))
    for g in sorted(layers.keys()):
        s = layers[g].dropna()
        if len(s) == 0:
            continue
        ann = s.mean() * 12
        vol = s.std() * np.sqrt(12)
        sr = ann / vol if vol > 0 else 0
        dd = (s.cumsum() - s.cumsum().cummax()).min()
        monthly[g] = ann
        print('%2d/%-2d   %+7.1f%% %6.2f %6.1f%% %+6.1f%% %5d'
              % (g + 1, len(layers), ann * 100, sr, vol * 100, dd * 100, len(s)))
    if len(monthly) >= 2:
        rho = pd.Series(monthly).corr(
            pd.Series({g: g for g in monthly}), method='spearman')
        top_bot = monthly[max(monthly.keys())] - monthly[min(monthly.keys())]
        print('单调性 spearman=%.3f  顶-底差=%+.2f%%' % (rho, top_bot * 100))


# ============================================================
# 9. 策略模拟对比
# ============================================================
print('\n' + '=' * 60)
print('9. 策略模拟对比 (训练集, N=%d)' % N_HOLD)
print('=' * 60)

ret_floor = simulate_strategy(floor_enhanced, N_HOLD)
ret_pure  = simulate_strategy(pure_dl, N_HOLD)

for label, rets in [('债底增强', ret_floor), ('纯双低(对照)', ret_pure)]:
    s = strategy_stats(rets)
    print('%s: 年化%+.1f%%  夏普%.2f  卡玛%.2f  波动%.1f%%  回撤%.1f%%  '
          '月胜率%.0f%%  %d月'
          % (label, s['年化%'], s['夏普'], s['卡玛'],
             s['波动%'], s['回撤%'], s['月胜率'], s['月数']))

# 差异分析
common_idx = ret_floor.index.intersection(ret_pure.index)
if len(common_idx) > 12:
    diff = ret_floor[common_idx] - ret_pure[common_idx]
    t_stat = diff.mean() / diff.std() * np.sqrt(len(diff)) if diff.std() > 0 else 0
    print('\n债底增强 vs 纯双低:')
    print('  月差 %+.3f%%  年化差 %+.1f%%  t=%.2f  跑赢%.0f%%'
          % (diff.mean() * 100, diff.mean() * 12 * 100,
             t_stat, (diff > 0).mean() * 100))
    print('  收益相关 %.3f' % ret_floor[common_idx].corr(ret_pure[common_idx]))


# ============================================================
# 10. 前后段一致性
# ============================================================
print('\n' + '=' * 60)
print('10. 前后段一致性')
print('=' * 60)

mid_point = pd.Timestamp('2021-01-01').date()
for label, rets in [('债底增强', ret_floor), ('纯双低', ret_pure)]:
    print('\n%s:' % label)
    for pname, pdates in [('前半(~2020)', [d for d in rets.index if d <= mid_point]),
                            ('后半(2021~)', [d for d in rets.index if d > mid_point])]:
        sub = rets[pdates]
        if len(sub) < 8:
            continue
        ann = sub.mean() * 12
        vol = sub.std() * np.sqrt(12)
        sr = ann / vol if vol > 0 else 0
        dd = (sub.cumsum() - sub.cumsum().cummax()).min()
        wr = (sub > 0).mean()
        print('  %s: 年化%+.1f%%  夏普%.2f  回撤%.1f%%  月胜率%.0f%%  %d月'
              % (pname, ann * 100, sr, dd * 100, wr * 100, len(sub)))

    d1 = [d for d in rets.index if d <= mid_point]
    d2 = [d for d in rets.index if d > mid_point]
    if len(d1) >= 8 and len(d2) >= 8:
        s1 = strategy_stats(rets[d1])
        s2 = strategy_stats(rets[d2])
        ds = s2['夏普'] - s1['夏普']
        print('  → 夏普差 %+.2f  %s' % (ds, '⚠' if abs(ds) > 0.5 else '✓'))


# ============================================================
# 11. 分年度 + 总结
# ============================================================
print('\n' + '=' * 60)
print('11. 分年度 + 总结')
print('=' * 60)

for label, rets in [('债底增强', ret_floor), ('纯双低(对照)', ret_pure)]:
    print('\n%s:' % label)
    df = rets.reset_index()
    df.columns = ['date', 'ret']
    df['year'] = pd.to_datetime(df['date']).dt.year
    for yr, grp in df.groupby('year'):
        cum = (1 + grp['ret']).prod() - 1
        bar = '█' * max(0, int(cum * 100 / 5)) if cum >= 0 else '░' * max(0, int(-cum * 100 / 3))
        print('  %4d  %+6.1f%%  %s' % (yr, cum * 100, bar))

print('\n========== 结论 ==========')
s_floor = strategy_stats(ret_floor)
s_pure  = strategy_stats(ret_pure)
delta_sr = s_floor['夏普'] - s_pure['夏普']

print('纯双低夏普: %.2f  →  债底增强夏普: %.2f' % (s_pure['夏普'], s_floor['夏普']))

if delta_sr > 0.1:
    print('✓ 债底距离因子在训练集上优于纯双低 (夏普提升 +%.2f)' % delta_sr)
    print('  → 建议冻结参数，进入测试集验证')
elif delta_sr > -0.1:
    print('○ 债底距离因子与纯双低接近 (夏普差 %.2f)' % delta_sr)
    if s_floor['回撤%'] > s_pure['回撤%']:  # 回撤绝对值更大
        print('  债底增强回撤更浅 → 防守性更好，仍值得验证')
    else:
        print('  无明显优势，但可并行追踪')
else:
    print('✗ 债底距离因子不及纯双低 (夏普差 %.2f)' % delta_sr)

print()
print('核心疑问已回答: 用"债底距离"替代"低价"，作为安全边际度量')
if COUPON_FIELD:
    print('债底计算用了真实票面利率 (字段: %s)' % COUPON_FIELD)
else:
    print('债底计算使用默认票面利率 2.0%（无真实利率数据）')

print()
print('⛔ 以上全部来自训练集。测试集未被触碰。')

print('\n===== 研究完成 =====')
