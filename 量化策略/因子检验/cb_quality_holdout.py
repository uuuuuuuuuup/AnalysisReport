# -*- coding: utf-8 -*-
# ============================================================
# 质量增强可转债双低轮动 — 测试集一次性 Holdout (BigQuant Notebook)
# ============================================================
# 🚫 只能跑一次。跑完即作废。
#
# 本脚本使用训练集(2019-2022)冻结的参数，
# 在测试集(2023-01 ~ 2026-07)上跑一次完整回测，
# 输出全部绩效指标并与训练集对比。
#
# 先算清它能说明什么：
#   43个月测试集，年化波动 ~15%
#   预期夏普标准误 ≈ sqrt((1 + 1.0^2/2) / 43) * sqrt(12) ≈ 0.50
#   95% 置信区间较宽，43个月在统计上仍无法精确确认夏普。
#   解释结果时应保持警惕。
#
# 判定规则：
#   测试集夏普 > 0.8 → 通过，进入模拟盘
#   测试集夏普 0.5~0.8 → 边缘，进入模拟盘但标注"证据不足"
#   测试集夏普 < 0.5 → 不通过，退回纯双低
# ============================================================

import dai
import pandas as pd
import numpy as np
import pickle
import os


# ==================== 🔒 冻结参数 ====================
# ⚠️ 以下参数来自训练集研究，禁止基于测试集结果修改

W_PRICE    = 0.40
W_PREMIUM  = 0.30
W_QUALITY  = 0.30
N_HOLD     = 20

MIN_LIST_DAYS      = 30
MIN_TERM_MONTHS    = 12
CREDIT_PRICE_FLOOR = 80
CREDIT_PREMIUM_CEILING = 100
MOM_LOOKBACK       = 40
MOM_EXCLUDE_PCT    = 0.20

START_DATE = '2023-01-01'
END_DATE   = '2026-07-29'

CACHE_DIR = 'cb_quality_holdout_cache'

# ==================== 工具函数 ====================

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


# ============================================================
# 1. 拉取数据 (测试集全区间)
# ============================================================
print('=' * 60)
print('1. 拉取测试集数据')
print('=' * 60)


def fetch_all_data():
    """拉取 CB + 正股估值 + 正股价格（测试集全区间）。"""
    # --- CB 基本信息 ---
    info = dai.query("""
        SELECT instrument, stock_code, maturity_date, list_date
        FROM cn_cbond_basic_info
        WHERE maturity_date IS NOT NULL
    """).df()
    info['maturity_date'] = pd.to_datetime(info['maturity_date'])
    info['list_date'] = pd.to_datetime(info['list_date'])

    # --- CB 日线 ---
    cb_parts = []
    for year in [2023, 2024, 2025, 2026]:
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
                    cb_parts.append(part)
            except Exception as e:
                print('  [跳过] %s~%s: %s' % (d1, d2, str(e)[:60]))

    cb_df = pd.concat(cb_parts, ignore_index=True)
    cb_df['date'] = pd.to_datetime(cb_df['date'])
    cb_df = cb_df.sort_values(['date', 'instrument']).reset_index(drop=True)

    info_map = info.set_index('instrument')
    cb_df['stock_code'] = cb_df['instrument'].map(info_map['stock_code'])
    cb_df['maturity_date'] = cb_df['instrument'].map(info_map['maturity_date'])
    cb_df['list_date'] = cb_df['instrument'].map(info_map['list_date'])

    print('CB日线: %d 行, %d 标的' % (len(cb_df), cb_df['instrument'].nunique()))

    all_stocks = sorted(cb_df['stock_code'].dropna().unique())

    # --- 正股价 (动量计算) ---
    stock_parts = []
    for year in [2022, 2023, 2024, 2025, 2026]:
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
                    SELECT date, instrument, close
                    FROM cn_stock_bar1d
                    ORDER BY date
                """, filters={"date": [d1, d2]}).df()
                if len(part) > 0:
                    stock_parts.append(part)
            except Exception:
                pass

    stock_df = pd.concat(stock_parts, ignore_index=True) if stock_parts else pd.DataFrame()
    if not stock_df.empty:
        stock_df['date'] = pd.to_datetime(stock_df['date'])
        stock_df = stock_df.sort_values(['date', 'instrument']).reset_index(drop=True)

    print('正股日线: %d 行, %d 标的' % (len(stock_df),
          stock_df['instrument'].nunique() if not stock_df.empty else 0))

    # --- 正股估值 (ROE) ---
    roe_data = {}
    for d in cb_df['date'].unique():
        d_str = pd.Timestamp(d).strftime('%Y-%m-%d')
        try:
            df = dai.query("""
                SELECT instrument, pb, pe_ttm
                FROM cn_stock_valuation_v6
            """, filters={"date": [d_str]}).df()
            if not df.empty:
                df = df[(df['pb'] > 0) & (df['pe_ttm'] > 0)]
                df['roe_est'] = df['pb'] / df['pe_ttm']
                df = df[(df['roe_est'] > 0) & (df['roe_est'] < 1.0)]
                df = df.set_index('instrument')
                roe_data[d] = df['roe_est']
        except Exception:
            pass

    roe_tbl = pd.DataFrame(roe_data).T
    print('ROE估算: %d 期 × %d 股票' % roe_tbl.shape)

    # --- 财务数据 (尝试) ---
    gross_margin_tbl = pd.DataFrame()
    debt_tbl = pd.DataFrame()
    cashflow_tbl = pd.DataFrame()
    try:
        all_fin = dai.query("""
            SELECT instrument, end_date,
                   gross_profit_margin,
                   debt_to_assets,
                   operating_cash_flow_to_revenue
            FROM cn_stock_financial_v6
            WHERE end_date >= '2022-01-01' AND end_date <= '%s'
            ORDER BY instrument, end_date
        """ % END_DATE.split('-')[0] + '-12-31').df()

        if len(all_fin) > 0:
            all_fin['end_date'] = pd.to_datetime(all_fin['end_date'])
            all_fin = all_fin.sort_values(['instrument', 'end_date'])

            fin_data = {}
            all_dates_list = sorted(cb_df['date'].unique())
            for d in all_dates_list:
                cutoff = pd.Timestamp(d)
                latest = all_fin[all_fin['end_date'] <= cutoff] \
                    .groupby('instrument').last().reset_index()
                if not latest.empty:
                    fin_data[d] = latest.set_index('instrument')

            if fin_data:
                gross_margin_tbl = pd.DataFrame({
                    d: fin_data[d]['gross_profit_margin']
                    for d in fin_data if 'gross_profit_margin' in fin_data[d].columns
                }).T
                debt_tbl = pd.DataFrame({
                    d: fin_data[d]['debt_to_assets']
                    for d in fin_data if 'debt_to_assets' in fin_data[d].columns
                }).T
                cashflow_tbl = pd.DataFrame({
                    d: fin_data[d]['operating_cash_flow_to_revenue']
                    for d in fin_data if 'operating_cash_flow_to_revenue' in fin_data[d].columns
                }).T
    except Exception as e:
        print('⚠ 财务数据拉取失败: %s' % str(e)[:100])

    print('毛利率: %s | 资产负债率: %s | 经营现金流: %s'
          % (('✓' if len(gross_margin_tbl) > 0 else '✗'),
             ('✓' if len(debt_tbl) > 0 else '✗'),
             ('✓' if len(cashflow_tbl) > 0 else '✗')))

    return cb_df, stock_df, roe_tbl, gross_margin_tbl, debt_tbl, cashflow_tbl


cb_df, stock_df, roe_tbl, gross_margin_tbl, debt_tbl, cashflow_tbl = \
    cache('holdout_data', fetch_all_data)

has_gross_margin = len(gross_margin_tbl) > 0
has_debt = len(debt_tbl) > 0
has_cashflow = len(cashflow_tbl) > 0
QUALITY_SUB_COUNT = 1 + has_gross_margin + has_debt + has_cashflow


# ============================================================
# 2. 构建调仓日
# ============================================================
all_dates = sorted(cb_df['date'].unique())
all_dates = pd.to_datetime(all_dates)
months = pd.Series(all_dates).dt.to_period('M').unique()
rebal_days = sorted([max(all_dates[pd.Series(all_dates).dt.to_period('M') == m])
                      for m in months])
rebal_days = [d.date() for d in rebal_days]
print('\n测试集调仓日: %d 个, %s ~ %s'
      % (len(rebal_days), rebal_days[0], rebal_days[-1]))

# ---- 预计算 40 日动量矩阵 ----
print('预计算正股动量...')
_momentum_cache_ho = {}
if not stock_df.empty:
    _sp = stock_df.pivot_table(
        values='close', index='date', columns='instrument', aggfunc='last')
    _sp = _sp.sort_index()
    for d in rebal_days:
        d_ts = pd.Timestamp(d)
        if d_ts not in _sp.index:
            avail = _sp.index[_sp.index <= d_ts]
            if len(avail) == 0:
                continue
            d_ts = avail[-1]
        idx_pos = _sp.index.get_loc(d_ts)
        lookback_pos = max(0, idx_pos - MOM_LOOKBACK)
        if lookback_pos == idx_pos:
            continue
        recent = _sp.iloc[idx_pos]
        base = _sp.iloc[lookback_pos]
        mom = (recent / base - 1).dropna()
        mom = mom[(mom > -1) & (mom < 10)]
        if len(mom) > 0:
            _momentum_cache_ho[d] = mom
    print('  动量缓存: %d 期 (共 %d 条)' % (len(_momentum_cache_ho),
          sum(len(v) for v in _momentum_cache_ho.values())))


# ============================================================
# 3. 构建因子 (每调仓日截面)
# ============================================================
print('\n' + '=' * 60)
print('2. 构建因子 (测试集)')
print('=' * 60)

inst_to_stock = dict(zip(
    cb_df[['instrument', 'stock_code']].drop_duplicates()['instrument'],
    cb_df[['instrument', 'stock_code']].drop_duplicates()['stock_code']))


def build_factor_single_date(d, col_name, higher_is_better, factor_type='cb'):
    """构建单期因子截面。factor_type: 'cb'=从cb_df取, 'roe'=从roe_tbl取, 'fin'=从财务tbl取。"""
    if factor_type == 'cb':
        sub = cb_df[cb_df['date'] == pd.Timestamp(d)]
        if len(sub) < 20:
            return None
        s = sub.set_index('instrument')[col_name].dropna()
        if len(s) < 20:
            return None
        s = winsorize_mad(s)
        s = zscore(s)
        if not higher_is_better:
            s = -s
        return s

    elif factor_type == 'roe':
        if d not in roe_tbl.index:
            return None
        s = roe_tbl.loc[d].dropna()
        if len(s) < 20:
            return None
        s = winsorize_mad(s)
        s = zscore(s)
        mapped = {}
        for inst, stk in inst_to_stock.items():
            if stk in s.index:
                mapped[inst] = s[stk]
        return pd.Series(mapped) if len(mapped) >= 20 else None

    elif factor_type == 'fin':
        tbl = {'gross_margin': gross_margin_tbl,
               'debt': debt_tbl,
               'cashflow': cashflow_tbl}[col_name]
        if len(tbl) == 0 or d not in tbl.index:
            return None
        s = tbl.loc[d].dropna()
        if len(s) < 20:
            return None
        s = winsorize_mad(s)
        s = zscore(s)
        if not higher_is_better:
            s = -s
        mapped = {}
        for inst, stk in inst_to_stock.items():
            if stk in s.index:
                mapped[inst] = s[stk]
        return pd.Series(mapped) if len(mapped) >= 20 else None

    return None


# 逐期构建因子
price_factors = {}
premium_factors = {}
roe_factors = {}
gross_margin_factors = {}
debt_factors = {}
cashflow_factors = {}

for i, d in enumerate(rebal_days):
    pf = build_factor_single_date(d, 'close', False, 'cb')
    if pf is not None:
        price_factors[d] = pf

    prf = build_factor_single_date(d, 'premium_rate', False, 'cb')
    if prf is not None:
        premium_factors[d] = prf

    rf = build_factor_single_date(d, 'roe_est', True, 'roe')
    if rf is not None:
        roe_factors[d] = rf

    if has_gross_margin:
        gf = build_factor_single_date(d, 'gross_margin', True, 'fin')
        if gf is not None:
            gross_margin_factors[d] = gf

    if has_debt:
        df_ = build_factor_single_date(d, 'debt', False, 'fin')
        if df_ is not None:
            debt_factors[d] = df_

    if has_cashflow:
        cf = build_factor_single_date(d, 'cashflow', True, 'fin')
        if cf is not None:
            cashflow_factors[d] = cf

    if i % 12 == 0:
        print('  %s: price=%d prem=%d roe=%d' % (d,
              len(price_factors), len(premium_factors), len(roe_factors)))

print('因子构建完成: price=%d prem=%d roe=%d'
      % (len(price_factors), len(premium_factors), len(roe_factors)))


# ============================================================
# 4. 构建最终打分 & 纯双低对照
# ============================================================
print('\n' + '=' * 60)
print('3. 构建最终打分')
print('=' * 60)

# 取共同日期
common_dates = sorted(set(price_factors.keys())
                      & set(premium_factors.keys())
                      & set(roe_factors.keys()))
print('共同日期: %d' % len(common_dates))


def compute_quality_score(d):
    """计算质量合并分。缺失≥2 → 退回中性(0)。"""
    sub_factors = [roe_factors.get(d)]
    if has_gross_margin:
        sub_factors.append(gross_margin_factors.get(d))
    if has_debt:
        sub_factors.append(debt_factors.get(d))
    if has_cashflow:
        sub_factors.append(cashflow_factors.get(d))

    valid_factors = [f for f in sub_factors if f is not None]
    if not valid_factors:
        return None

    combined = None
    for f in valid_factors:
        s = f.dropna()
        if combined is None:
            combined = pd.DataFrame({'val': s, 'cnt': 1})
        else:
            common_idx = combined.index.intersection(s.index)
            combined = combined.loc[common_idx]
            combined['val'] = combined['val'] + s[common_idx]
            combined['cnt'] = combined['cnt'] + 1

    if combined is None or len(combined) < 20:
        return None

    min_needed = max(1, QUALITY_SUB_COUNT - 1)
    combined['avg'] = combined['val'] / combined['cnt']
    combined.loc[combined['cnt'] < min_needed, 'avg'] = 0.0
    return combined['avg']


final_scores = {}
pure_dl_scores = {}

for d in common_dates:
    p = price_factors[d]
    pr = premium_factors[d]
    q = compute_quality_score(d)

    if q is None:
        continue

    common = sorted(set(p.index) & set(pr.index) & set(q.index))
    if len(common) < N_HOLD * 2:
        continue

    final_scores[d] = W_PRICE * p[common] + W_PREMIUM * pr[common] + W_QUALITY * q[common]
    pure_dl_scores[d] = 0.5 * p[common] + 0.5 * pr[common]

print('final_score: %d 期  |  pure_double_low: %d 期'
      % (len(final_scores), len(pure_dl_scores)))


# ============================================================
# 5. 未来收益矩阵
# ============================================================
print('\n' + '=' * 60)
print('4. 构建未来收益')
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
# 6. 动量过滤 (使用预计算缓存)
# ============================================================
def momentum_filter(d, eligible, cur_info):
    """排除正股 40 日动量最差 MOM_EXCLUDE_PCT。使用预计算缓存 O(N)。"""
    if d not in _momentum_cache_ho:
        return eligible

    mom_all = _momentum_cache_ho[d]
    if len(mom_all) < 20:
        return eligible

    inst_to_stk = dict(zip(
        cb_df[cb_df['date'] == pd.Timestamp(d)]['instrument'],
        cb_df[cb_df['date'] == pd.Timestamp(d)]['stock_code']))
    inst_to_stk = {k: v for k, v in inst_to_stk.items() if pd.notna(v)}

    inst_mom = {}
    for inst in eligible:
        stk = inst_to_stk.get(inst)
        if stk is not None and stk in mom_all.index:
            inst_mom[inst] = mom_all[stk]

    if len(inst_mom) < 20:
        return eligible
    cutoff_val = pd.Series(inst_mom).quantile(MOM_EXCLUDE_PCT)
    return {inst for inst, mom in inst_mom.items() if mom >= cutoff_val}


# ============================================================
# 7. 跑回测
# ============================================================
print('\n' + '=' * 60)
print('5. 🚫 测试集一次性回测')
print('=' * 60)


def run_backtest(score_dict, label):
    """遍历调仓日，模拟月频等权轮动。"""
    dates_sorted = sorted(score_dict.keys())
    monthly_rets = []

    for i, d in enumerate(dates_sorted[:-1]):
        next_d = dates_sorted[i + 1]

        f_s = score_dict[d].dropna()
        if d not in fwd_ret.index:
            continue
        r_s = fwd_ret.loc[d].dropna()

        # 基础过滤
        cur = cb_df[cb_df['date'] == pd.Timestamp(d)]
        if len(cur) == 0:
            continue
        cur_info = cur.set_index('instrument')
        eligible = set(f_s.index) & set(r_s.index)

        for inst in list(eligible):
            if inst not in cur_info.index:
                eligible.discard(inst)
                continue
            info = cur_info.loc[inst]

            mature = info['maturity_date']
            if pd.notna(mature):
                ml = (pd.Timestamp(mature) - pd.Timestamp(d)).days / 30.0
                if ml < MIN_TERM_MONTHS:
                    eligible.discard(inst)
                    continue

            list_d = info['list_date']
            if pd.notna(list_d):
                dl = (pd.Timestamp(d) - pd.Timestamp(list_d)).days
                if dl < MIN_LIST_DAYS:
                    eligible.discard(inst)
                    continue

            px = info['close'] if 'close' in info.index else np.nan
            prem = info['premium_rate'] if 'premium_rate' in info.index else np.nan
            if (pd.notna(px) and pd.notna(prem)
                    and px < CREDIT_PRICE_FLOOR
                    and prem > CREDIT_PREMIUM_CEILING):
                eligible.discard(inst)
                continue

        if len(eligible) < N_HOLD * 2:
            continue

        # 动量硬排除
        eligible = momentum_filter(d, eligible, cur_info)
        if len(eligible) < N_HOLD * 2:
            continue

        eligible_list = sorted(eligible)
        f_vals = f_s[eligible_list]
        r_vals = r_s[eligible_list]

        top_n = f_vals.nlargest(min(N_HOLD, len(f_vals))).index
        rets = r_vals[top_n].dropna()
        if len(rets) >= N_HOLD * 0.5:
            monthly_rets.append({
                'date': d,
                'ret': rets.mean(),
                'n_selected': len(rets),
                'n_eligible': len(eligible)
            })

    result = pd.DataFrame(monthly_rets)
    if len(result) == 0:
        print('%s: 无有效回测结果!' % label)
        return None

    ann_ret = result['ret'].mean() * 12
    ann_vol = result['ret'].std() * np.sqrt(12)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    cumsum_ret = result['ret'].cumsum()
    maxdd = (cumsum_ret - cumsum_ret.cummax()).min()
    calmar = ann_ret / abs(maxdd) if maxdd < 0 else np.inf
    win_rate = (result['ret'] > 0).mean()

    # 等权全池基准
    bench_rets = []
    for _, row in result.iterrows():
        d = row['date'].date() if hasattr(row['date'], 'date') else row['date']
        if d in fwd_ret.index:
            bench_rets.append(fwd_ret.loc[d].mean())
    bench_series = pd.Series(bench_rets, index=result['date'])
    common_bench = result['ret'].index.intersection(bench_series.index)
    if len(common_bench) > 6:
        excess = result.set_index('date')['ret'].loc[common_bench] - bench_series[common_bench]
        ir = excess.mean() / excess.std() * np.sqrt(12) if excess.std() > 0 else 0
        excess_ann = excess.mean() * 12 * 100
    else:
        ir = np.nan
        excess_ann = np.nan

    print('\n' + '=' * 50)
    print('  %s  测试集绩效' % label)
    print('=' * 50)
    print('  区间:       %s ~ %s' % (result['date'].iloc[0], result['date'].iloc[-1]))
    print('  月数:       %d' % len(result))
    print('  年化收益:    %+.1f%%' % (ann_ret * 100))
    print('  年化波动:    %.1f%%' % (ann_vol * 100))
    print('  夏普(rf=0):  %.2f' % sharpe)
    print('  卡玛:       %.2f' % calmar)
    print('  最大回撤:    %.1f%%' % (maxdd * 100))
    print('  月胜率:     %.0f%%' % (win_rate * 100))
    print('  超额(vs全池): %+.1f%%/年' % excess_ann)
    print('  IR:         %.2f' % ir)
    print('  每期平均候选: %.0f只 → 选%d只' % (result['n_eligible'].mean(), N_HOLD))

    # 分年度
    result['year'] = pd.to_datetime(result['date']).dt.year
    print('\n  分年度:')
    for yr, grp in result.groupby('year'):
        cum = (1 + grp['ret']).prod() - 1
        print('    %d  %+6.1f%%  (%d月)' % (yr, cum * 100, len(grp)))

    return {
        'label': label,
        'ann_ret': ann_ret, 'ann_vol': ann_vol, 'sharpe': sharpe,
        'calmar': calmar, 'maxdd': maxdd, 'win_rate': win_rate,
        'ir': ir, 'excess_ann': excess_ann,
        'n_months': len(result),
        'monthly_rets': result['ret'].values
    }


# 跑质量增强
result_enhanced = run_backtest(final_scores, '质量增强双低')
# 跑纯双低对照
result_pure = run_backtest(pure_dl_scores, '纯双低(对照)')


# ============================================================
# 8. 训练集 vs 测试集 对比
# ============================================================
print('\n' + '=' * 60)
print('6. 训练集 vs 测试集 对比')
print('=' * 60)

# 训练集基准值(从 cb_quality_factor_research.py 冻结，需手动填入)
# 注意：这些值应在冻结参数后从研究脚本输出中复制过来
TRAIN_SHARPE = None   # TODO: 从研究脚本输出填入
TRAIN_CALMAR = None   # TODO: 从研究脚本输出填入
TRAIN_WIN_RATE = None # TODO: 从研究脚本输出填入
TRAIN_MAXDD = None    # TODO: 从研究脚本输出填入

if result_enhanced:
    print('\n指标对比 (质量增强双低):')
    print('%-16s %10s %10s %10s' % ('指标', '训练集', '测试集', '差异'))
    for metric, train_val in [('夏普', TRAIN_SHARPE), ('卡玛', TRAIN_CALMAR),
                                ('月胜率', TRAIN_WIN_RATE), ('回撤%', TRAIN_MAXDD)]:
        test_val = {'夏普': result_enhanced['sharpe'],
                    '卡玛': result_enhanced['calmar'],
                    '月胜率': result_enhanced['win_rate'] * 100,
                    '回撤%': result_enhanced['maxdd'] * 100}[metric]
        if train_val is not None:
            diff = test_val - train_val
            print('%-16s %9.2f %9.2f %+9.2f' % (metric, train_val, test_val, diff))
        else:
            print('%-16s %9s %9.2f %9s' % (metric, '(待填入)', test_val, '-'))


# ============================================================
# 9. 判定
# ============================================================
print('\n' + '=' * 60)
print('7. 最终判定')
print('=' * 60)

if result_enhanced is None:
    print('✗ 回测失败，无法判定')
elif result_enhanced['sharpe'] > 0.8 and result_enhanced['win_rate'] > 0.55:
    print('✓ 通过 — 测试集夏普 %.2f > 0.8, 月胜率 %.0f%% > 55%%'
          % (result_enhanced['sharpe'], result_enhanced['win_rate'] * 100))
    print('  建议：进入模拟盘验证')
elif result_enhanced['sharpe'] > 0.5:
    print('△ 边缘 — 测试集夏普 %.2f 在 0.5~0.8 之间' % result_enhanced['sharpe'])
    print('  建议：进入模拟盘，但标注"证据不足"')
else:
    print('✗ 不通过 — 测试集夏普 %.2f < 0.5' % result_enhanced['sharpe'])
    print('  建议：退回纯双低策略')

# 与纯双低对比
if result_enhanced and result_pure:
    sharpe_diff = result_enhanced['sharpe'] - result_pure['sharpe']
    print()
    if sharpe_diff > 0.05:
        print('vs 纯双低: 质量增强夏普高 %.2f → 质量因子在测试集上有正向贡献'
              % sharpe_diff)
    elif sharpe_diff > -0.05:
        print('vs 纯双低: 质量增强夏普差 %.2f → 质量因子在测试集上接近中性'
              % sharpe_diff)
    else:
        print('vs 纯双低: 质量增强夏普低 %.2f → 质量因子在测试集上为负贡献，应退回纯双低'
              % abs(sharpe_diff))

print()
print('🚫 本次 holdout 已使用。该测试区间不可再次用于验证。')
print('   后续验证只能通过前向模拟盘积累新的未污染数据。')

print('\n===== Holdout 完成 =====')
