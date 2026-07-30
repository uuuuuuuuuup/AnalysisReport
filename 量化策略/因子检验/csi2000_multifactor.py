# -*- coding: utf-8 -*-
# ============================================================
# 中证2000 多因子增强策略 (BigQuant Notebook)
# ============================================================
# ⛔ 数据墙：训练集 2015-01 ~ 2022-12 | 测试集 2023-01 ~ 2025-12 封存
#
# 核心逻辑：
#   小微盘股（中证2000）散户主导 → 行为偏差最强 →
#   价值(BP) + 反转(20d) + 低波(60d) + 质量过滤(ROE>0)
#   四因子等权或先验固定权重打分，月频40只等权持有。
#
# 池子：中证2000代理 — 每月按市值排序取后段~2000只
#   (A股全市场 → 过滤ST/新股/停牌 → 市值排序 → 取1800名之后)
#
# 打分公式（先验固定）：
#   score = 0.35 × z(BP_neut) + 0.35 × z(-ret_20d_neut) + 0.30 × z(-vol_60d_neut)
# ============================================================

import dai
import pandas as pd
import numpy as np
import pickle
import os

pd.set_option('display.width', 300)
pd.set_option('display.max_columns', 30)

# ==================== 配置 ====================
START_DATE = '2015-01-01'
END_DATE   = '2025-12-31'

N_HOLD     = 40
W_BP       = 0.35
W_REV      = 0.35
W_VOL      = 0.30

# CSI2000 proxy: 市值排序后取 [rank_start, rank_end)
CSI2000_RANK_START = 1800
CSI2000_POOL_SIZE  = 2000

MIN_LIST_DAYS = 250
MOM_LOOKBACK  = 40
MOM_EXCLUDE   = 0.20

CACHE_DIR = 'csi2000_cache'

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
# 0. 字段发现
# ============================================================
print('=' * 60)
print('0. cn_stock_valuation_v6 字段发现')
print('=' * 60)

try:
    sample_val = dai.query("SELECT * FROM cn_stock_valuation_v6 LIMIT 3").df()
    print('可用列 (%d): %s' % (len(sample_val.columns), list(sample_val.columns)))
    VAL_FIELDS = list(sample_val.columns)
except Exception as e:
    print('⚠ 字段发现失败: %s' % str(e)[:100])
    # 回退：使用已知字段名
    VAL_FIELDS = ['instrument', 'market_cap', 'pb', 'pe_ttm']

# 确定实际字段名
MC_FIELD = None
for c in ['market_cap', 'total_mv', 'mkt_cap', 'circulating_market_cap']:
    if c in VAL_FIELDS:
        MC_FIELD = c
        break

PB_FIELD = 'pb' if 'pb' in VAL_FIELDS else None
PE_FIELD = 'pe_ttm' if 'pe_ttm' in VAL_FIELDS else 'pe_ttm_'
ST_FIELD = 'is_st' if 'is_st' in VAL_FIELDS else None

print('市值字段: %s | PB: %s | PE: %s | ST: %s'
      % (MC_FIELD, PB_FIELD, PE_FIELD, ST_FIELD))

if MC_FIELD is None:
    print('⚠ 无市值字段！将用 cn_stock_valuation_v6 已知字段重试')
    MC_FIELD = 'market_cap'  # 回退默认值


# ============================================================
# 1. 获取调仓日 + 每月全A股市值排名 (CSI2000代理)
# ============================================================
print('\n' + '=' * 60)
print('1. 构建 CSI2000 代理池')
print('=' * 60)


def fetch_trade_calendar():
    """获取交易日历，每月末交易日作为调仓日。"""
    try:
        cal = dai.query("""
            SELECT DISTINCT date
            FROM cn_stock_bar1d
            ORDER BY date
        """, filters={"date": [START_DATE, END_DATE]}).df()
        cal['date'] = pd.to_datetime(cal['date'])
        all_dates = sorted(cal['date'].unique())
    except Exception:
        # 回退：用 pandas 生成日期范围 + 去掉周末
        all_dates = pd.date_range(START_DATE, END_DATE, freq='B')
        all_dates = pd.DatetimeIndex(sorted(all_dates))

    months = pd.Series(all_dates).dt.to_period('M').unique()
    rebal = sorted([max(d for d in all_dates
                        if pd.Timestamp(d).to_period('M') == m)
                    for m in months])
    rebal = [d.date() if hasattr(d, 'date') else pd.Timestamp(d).date()
             for d in rebal]
    print('调仓日: %d, %s ~ %s' % (len(rebal), rebal[0], rebal[-1]))
    return rebal


rebal_days_all = cache('rebal_days', fetch_trade_calendar)

train_days = [d for d in rebal_days_all
              if d <= pd.Timestamp(TRAIN_END_DATE).date()]
test_days  = [d for d in rebal_days_all
              if d >= pd.Timestamp(TEST_START_DATE).date()]
print('训练集: %d 期  测试集: %d 期 ← ⛔' % (len(train_days), len(test_days)))


def fetch_market_caps():
    """每调仓日取全A股 PB + PE_ttm。先取已验证可用的字段。"""
    mc_data = {}
    for i, d in enumerate(rebal_days_all):
        try:
            # 只用 cb_quality_factor_research.py 已验证可行的字段和格式
            df = dai.query("""
                SELECT instrument, pb, pe_ttm
                FROM cn_stock_valuation_v6
            """, filters={"date": [d]}).df()
            if not df.empty:
                df = df[(df['pb'] > 0) & (df['pe_ttm'] > 0)]
                df['market_cap'] = np.nan  # 暂无市值数据，后续补充
                df = df.set_index('instrument')
                mc_data[d] = df
        except Exception as e:
            if i == 0:
                print('  ⚠ 首期查询失败: %s' % str(e)[:80])
        if i % 24 == 0 and len(mc_data) > 0:
            print('  %s: %d 只 (已取%d期)' % (d, len(mc_data.get(d, pd.DataFrame())), len(mc_data)))

    print('估值数据: %d 期' % len(mc_data))

    # 尝试补充市值数据
    try:
        mc_test = dai.query("""
            SELECT instrument, market_cap
            FROM cn_stock_valuation_v6
        """, filters={"date": [rebal_days_all[len(rebal_days_all)//2]]}).df()
        if not mc_test.empty and 'market_cap' in mc_test.columns:
            HAS_MC = True
            print('✓ market_cap 字段可用，补充市值数据...')
            for d in mc_data:
                try:
                    mc_df = dai.query("""
                        SELECT instrument, market_cap
                        FROM cn_stock_valuation_v6
                    """, filters={"date": [d]}).df()
                    if not mc_df.empty:
                        mc_map = mc_df.set_index('instrument')['market_cap']
                        mc_data[d]['market_cap'] = mc_map
                except Exception:
                    pass
        else:
            HAS_MC = False
    except Exception:
        HAS_MC = False

    print('市值数据: %s' % ('✓' if HAS_MC else '✗ (将用PB倒数做代理排名)'))
    return mc_data, HAS_MC


mc_all, HAS_MC = cache('market_caps', fetch_market_caps)

# 如果无市值，用 PB 排名替代（小盘股 PB 通常更低）
if not HAS_MC:
    print('无市值数据，用 PB 倒数排名作为 CSI2000 代理 (低PB≈小市值)')
    for d in mc_all:
        df = mc_all[d]
        # PB 越低 ≈ 市值越小（粗糙代理）
        df['market_cap'] = 1.0 / df['pb'].clip(lower=0.01)
        mc_all[d] = df


def build_csi2000_universe(mc_data):
    """每月按市值排序，取 CSI2000 代理：排名 1801-3800。"""
    universe = {}
    for d, df in mc_data.items():
        df = df.copy()
        df['mcap_rank'] = df['market_cap'].rank(ascending=False)
        start = CSI2000_RANK_START + 1
        end = start + CSI2000_POOL_SIZE
        pool = df[(df['mcap_rank'] >= start) & (df['mcap_rank'] < end)]
        universe[d] = set(pool.index.tolist())
    return universe


csi2000_universe = build_csi2000_universe(mc_all)

# 打印统计
sizes = [len(v) for v in csi2000_universe.values()]
print('CSI2000代理池: 每月 %.0f~%.0f 只 (中位 %.0f)'
      % (min(sizes), max(sizes), np.median(sizes)))

# 所有出现过的股票
all_csi2000_stocks = sorted(set().union(*csi2000_universe.values()))
print('历史出现过的股票总数: %d' % len(all_csi2000_stocks))


# ============================================================
# 2. 拉取日线数据 (仅CSI2000池中出现过的股票)
# ============================================================
print('\n' + '=' * 60)
print('2. 拉取日线数据')
print('=' * 60)

PRICE_BATCH = 300


def fetch_prices():
    """分批拉取日线 close。"""
    stock_list = sorted(all_csi2000_stocks)
    n_batches = (len(stock_list) + PRICE_BATCH - 1) // PRICE_BATCH
    print('%d 只股票, 分 %d 批' % (len(stock_list), n_batches))

    frames = []
    for b in range(n_batches):
        batch = stock_list[b * PRICE_BATCH:(b + 1) * PRICE_BATCH]
        for year in range(2015, 2026):
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
                    """, filters={"date": [d1, d2],
                                  "instrument": batch}).df()
                    if len(part) > 0:
                        frames.append(part)
                except Exception:
                    pass
        if b % 5 == 0:
            print('  batch %d/%d' % (b + 1, n_batches))

    df = pd.concat(frames, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['date', 'instrument']).reset_index(drop=True)
    print('价格数据: %d 行, %d 标的' % (len(df), df['instrument'].nunique()))
    return df


price_df = cache('prices', fetch_prices)


# ============================================================
# 3. 日线预计算 (Pivot → 因子值)
# ============================================================
print('\n' + '=' * 60)
print('3. 预计算因子')
print('=' * 60)

close_pivot = price_df.pivot_table(
    values='close', index='date', columns='instrument', aggfunc='last')
close_pivot = close_pivot.sort_index()
print('close pivot: %d 行 × %d 列' % close_pivot.shape)

# 日收益
daily_ret = close_pivot.pct_change()

# 20日反转因子 (过去20日收益，越低越好 → 取负)
ret_20d = close_pivot.pct_change(20)

# 60日波动率 (越低越好 → 取负)
vol_60d = daily_ret.rolling(60, min_periods=40).std() * np.sqrt(252)

# 40日动量 (用于硬排除)
mom_40d = close_pivot.pct_change(MOM_LOOKBACK)

print('因子预计算完成')


# ============================================================
# 4. 逐期构建 CSI2000 因子截面
# ============================================================
print('\n' + '=' * 60)
print('4. 逐期构建因子截面 + 中性化')
print('=' * 60)


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


def get_industry_map(instruments, date_str):
    """获取申万一级行业分类。"""
    try:
        df = dai.query("""
            SELECT instrument, sw_l1_code
            FROM cn_stock_industry_sw
        """, filters={"date": [date_str]}).df()
        if not df.empty:
            return dict(zip(df['instrument'], df['sw_l1_code']))
    except Exception:
        pass
    return {}


def cross_sectional_neutralize(factor_s, industry_s, ln_mcap_s):
    """截面回归取残差: factor ~ 行业哑变量 + ln(市值)"""
    df = pd.concat([factor_s.rename('y'), industry_s.rename('ind'),
                    ln_mcap_s.rename('mc')], axis=1).dropna()
    if len(df) < 30 or df['ind'].nunique() < 2:
        return pd.Series(np.nan, index=factor_s.index)
    dummies = pd.get_dummies(df['ind'], drop_first=True).astype(float)
    X = np.column_stack([np.ones(len(df)), df['mc'].values, dummies.values])
    beta, _, _, _ = np.linalg.lstsq(X, df['y'].values, rcond=None)
    resid = df['y'].values - X.dot(beta)
    return pd.Series(resid, index=df.index).reindex(factor_s.index)


def build_factors():
    """逐调仓日构建: BP、反转、低波 三因子的中性化 z-score。"""
    bp_factor_raw = {}
    rev_factor_raw = {}
    vol_factor_raw = {}
    mc_factor_raw = {}
    quality_ok = {}       # ROE > 0 的股票集合（质量过滤）

    for i, d in enumerate(rebal_days_all):
        d_ts = pd.Timestamp(d)
        d_str = str(d)

        # CSI2000 池子
        pool = csi2000_universe.get(d, set())
        if len(pool) < 100:
            continue
        pool_list = sorted(pool)

        # --- BP 因子 (1/PB) ---
        if d in mc_all:
            mc_df = mc_all[d]
            common_pool = [s for s in pool_list if s in mc_df.index]
            if len(common_pool) >= 100:
                # BP = 1/PB
                bp_raw = 1.0 / mc_df.loc[common_pool, 'pb'].clip(lower=0.01)
                bp_raw = bp_raw[bp_raw > 0].dropna()
                if len(bp_raw) >= 100:
                    bp_raw = winsorize_mad(bp_raw)
                    bp_factor_raw[d] = bp_raw

                # 市值 (中性化用)
                mc_s = mc_df.loc[common_pool, 'market_cap'].clip(lower=1)
                mc_factor_raw[d] = np.log(mc_s)

                # ROE 估算 (质量过滤)
                pb_pe = mc_df.loc[common_pool, ['pb', 'pe_ttm']].copy()
                pb_pe = pb_pe[(pb_pe['pb'] > 0) & (pb_pe['pe_ttm'] > 0)]
                pb_pe['roe_est'] = pb_pe['pb'] / pb_pe['pe_ttm']
                pb_pe = pb_pe[(pb_pe['roe_est'] > 0) & (pb_pe['roe_est'] < 1.0)]
                quality_ok[d] = set(pb_pe.index.tolist())

        # --- 20日反转 (取负 = 跌得多 → z-score高) ---
        if d_ts in ret_20d.index:
            rev_vals = ret_20d.loc[d_ts].dropna()
            rev_pool = rev_vals[rev_vals.index.isin(pool_list)]
            if len(rev_pool) >= 100:
                rev_pool = winsorize_mad(rev_pool)
                rev_pool = -rev_pool    # 反转：跌得多 → 分高
                rev_factor_raw[d] = rev_pool

        # --- 60日低波 (取负 = 波动低 → z-score高) ---
        if d_ts in vol_60d.index:
            vol_vals = vol_60d.loc[d_ts].dropna()
            vol_pool = vol_vals[vol_vals.index.isin(pool_list)]
            if len(vol_pool) >= 100:
                vol_pool = winsorize_mad(vol_pool)
                vol_pool = -vol_pool    # 低波：波动低 → 分高
                vol_factor_raw[d] = vol_pool

        if i % 12 == 0:
            print('  %s: bp=%d rev=%d vol=%d q=%d'
                  % (d, len(bp_factor_raw.get(d, [])),
                     len(rev_factor_raw.get(d, [])),
                     len(vol_factor_raw.get(d, [])),
                     len(quality_ok.get(d, set()))))

    # --- 中性化 ---
    bp_factor_neut = {}
    rev_factor_neut = {}
    vol_factor_neut = {}

    raw_common = sorted(set(bp_factor_raw.keys())
                         & set(rev_factor_raw.keys())
                         & set(vol_factor_raw.keys())
                         & set(mc_factor_raw.keys()))
    print('  原始因子共同日期: bp=%d rev=%d vol=%d mc=%d → 共同=%d'
          % (len(bp_factor_raw), len(rev_factor_raw), len(vol_factor_raw),
             len(mc_factor_raw), len(raw_common)))

    for d in raw_common:
        if d not in mc_factor_raw:
            continue

        ind_map = get_industry_map(list(bp_factor_raw[d].index), str(d))
        ind_s = pd.Series(ind_map)
        mc_s = mc_factor_raw[d]

        for raw_dict, neut_dict, name in [
            (bp_factor_raw, bp_factor_neut, 'bp'),
            (rev_factor_raw, rev_factor_neut, 'rev'),
            (vol_factor_raw, vol_factor_neut, 'vol'),
        ]:
            if d not in raw_dict:
                continue
            raw_s = raw_dict[d]
            common = sorted(set(raw_s.index) & set(mc_s.index))
            if len(common) < 50:
                continue
            neut_s = cross_sectional_neutralize(
                raw_s[common], ind_s, mc_s[common])
            neut_s = neut_s.dropna()
            if len(neut_s) >= 50:
                neut_dict[d] = zscore(neut_s)

    return bp_factor_neut, rev_factor_neut, vol_factor_neut, quality_ok


bp_neut, rev_neut, vol_neut, quality_ok = cache('factors', build_factors)

# ---- 诊断 ----
print('\n--- 数据管道诊断 ---')
print('mc_all 期数: %d,  样本日期: %s' % (len(mc_all),
      list(mc_all.keys())[:3] if mc_all else '空'))
print('csi2000_universe 期数: %d,  月均%.0f只' % (len(csi2000_universe),
      np.mean([len(v) for v in csi2000_universe.values()]) if csi2000_universe else 0))
print('close_pivot: %d行 × %d列' % close_pivot.shape)
print('ret_20d 有效列: %d' % ret_20d.dropna(how='all', axis=1).shape[1])
print('vol_60d 有效列: %d' % vol_60d.dropna(how='all', axis=1).shape[1])
print('mom_40d 有效列: %d' % mom_40d.dropna(how='all', axis=1).shape[1])
print('bp_factor_raw: %d 期' % len(bp_factor_raw) if 'bp_factor_raw' in dir() else '未定义')
print('--- 诊断结束 ---\n')

n_bp = len(bp_neut)
n_rev = len(rev_neut)
n_vol = len(vol_neut)
print('中性化因子: bp=%d期  rev=%d期  vol=%d期' % (n_bp, n_rev, n_vol))

# --- 合并打分 ---
common_factor_dates = sorted(set(bp_neut.keys())
                              & set(rev_neut.keys())
                              & set(vol_neut.keys()))
print('三因子共同日期: %d' % len(common_factor_dates))

final_score = {}
for d in common_factor_dates:
    bp = bp_neut[d].dropna()
    rv = rev_neut[d].dropna()
    vl = vol_neut[d].dropna()

    # 质量过滤: ROE > 0
    q_stocks = quality_ok.get(d, set())
    q_filter = lambda x: x[x.index.isin(q_stocks)] if q_stocks else x
    bp = q_filter(bp)
    rv = q_filter(rv)
    vl = q_filter(vl)

    common = sorted(set(bp.index) & set(rv.index) & set(vl.index))
    if len(common) < N_HOLD * 2:
        continue
    final_score[d] = (W_BP * bp[common]
                      + W_REV * rv[common]
                      + W_VOL * vl[common])

final_score = pd.DataFrame(final_score).T
print('final_score: %d 期 × %d 标的' % final_score.shape)


# ============================================================
# 5. 未来收益矩阵
# ============================================================
print('\n' + '=' * 60)
print('5. 未来收益矩阵')
print('=' * 60)

fwd_ret = {}
for i, d in enumerate(rebal_days_all[:-1]):
    next_d = rebal_days_all[i + 1]
    d_ts = pd.Timestamp(d)
    n_ts = pd.Timestamp(next_d)

    if d_ts not in close_pivot.index or n_ts not in close_pivot.index:
        continue
    cp = close_pivot.loc[d_ts].dropna()
    np_ = close_pivot.loc[n_ts].dropna()
    common = cp.index.intersection(np_.index)
    fwd_ret[d] = np_[common] / cp[common] - 1.0

fwd_ret = pd.DataFrame(fwd_ret).T
print('未来收益: %d 期 × %d 标的' % fwd_ret.shape)

# 基准：CSI2000等权
bench_rets = {}
for d in fwd_ret.index:
    pool = csi2000_universe.get(d, set())
    valid = [s for s in pool if s in fwd_ret.columns
             and pd.notna(fwd_ret.loc[d, s])]
    if valid:
        bench_rets[d] = fwd_ret.loc[d, valid].mean()
bench_ret = pd.Series(bench_rets)


# ============================================================
# ⛔ 以下仅训练集
# ============================================================

def filter_train(factor_df):
    if isinstance(factor_df, pd.DataFrame):
        dates = [d for d in factor_df.index
                 if d <= pd.Timestamp(TRAIN_END_DATE).date()]
        return factor_df.loc[dates]
    return factor_df


def compute_ic_series(factor_df):
    factor_df = filter_train(factor_df)
    ics = []
    for d in factor_df.index:
        if d not in fwd_ret.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < 30:
            continue
        ic = pd.Series(f_s[common]).corr(pd.Series(r_s[common]), method='spearman')
        if not np.isnan(ic):
            ics.append({'date': d, 'ic': ic, 'n': len(common)})
    return pd.DataFrame(ics)


def layered_returns(factor_df, n_groups=10):
    factor_df = filter_train(factor_df)
    all_layers = {g: [] for g in range(n_groups)}
    for d in factor_df.index:
        if d not in fwd_ret.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret.loc[d].dropna()
        common = sorted(set(f_s.index) & set(r_s.index))
        if len(common) < n_groups * 3:
            continue
        vals = f_s[common]
        rets = r_s[common]
        order = vals.argsort()
        gs = len(common) // n_groups
        for g in range(n_groups):
            s_ = g * gs
            e_ = s_ + gs if g < n_groups - 1 else len(common)
            all_layers[g].append(rets.iloc[order[s_:e_]].mean())
    return {g: pd.Series(all_layers[g]) for g in range(n_groups)}


def simulate_strategy(factor_df, n_hold=N_HOLD):
    """选因子值最高的 n_hold 只，等权月频。
    加动量硬排除：正股40日动量最差MOM_EXCLUDE剔除。"""
    factor_df = filter_train(factor_df)
    monthly_rets = {}

    # 日期类型对齐：统一转为 Timestamp
    fwd_index_ts = pd.DatetimeIndex([pd.Timestamp(d) for d in fwd_ret.index])
    factor_index_ts = pd.DatetimeIndex([pd.Timestamp(d) for d in factor_df.index])

    n_skipped_no_fwd = 0
    n_skipped_few = 0

    for i, d in enumerate(factor_df.index):
        d_ts = pd.Timestamp(d)
        if d_ts not in fwd_index_ts:
            n_skipped_no_fwd += 1
            continue
        f_s = factor_df.loc[d].dropna()
        # 用位置索引更快
        fwd_pos = fwd_index_ts.get_loc(d_ts)
        r_s = fwd_ret.iloc[fwd_pos].dropna()
        eligible = set(f_s.index) & set(r_s.index)

        # 动量硬排除
        if d_ts in mom_40d.index:
            mom_vals = mom_40d.loc[d_ts].dropna()
            mom_in_pool = {s: v for s, v in mom_vals.items()
                           if s in eligible and not np.isnan(v)}
            if len(mom_in_pool) >= 20:
                cutoff = pd.Series(mom_in_pool).quantile(MOM_EXCLUDE)
                eligible = {s for s, v in mom_in_pool.items() if v >= cutoff}

        if len(eligible) < n_hold * 2:
            n_skipped_few += 1
            continue

        eligible_list = sorted(eligible)
        f_vals = f_s[eligible_list]
        r_vals = r_s[eligible_list]

        top_n = f_vals.nlargest(min(n_hold, len(f_vals))).index
        rets = r_vals[top_n].dropna()
        if len(rets) >= n_hold * 0.5:
            monthly_rets[d] = rets.mean()

    print('  simulate: 训练月=%d  无fwd=%d  候选不足=%d  有效=%d'
          % (len(factor_df), n_skipped_no_fwd, n_skipped_few, len(monthly_rets)))
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
# 6. 单因子 IC
# ============================================================
print('\n' + '=' * 60)
print('6. 单因子 IC (训练集)')
print('=' * 60)

for name, f_dict, desc in [
    ('bp_neut',  bp_neut,  'BP(中性化)'),
    ('rev_neut', rev_neut, '20日反转(中性化)'),
    ('vol_neut', vol_neut, '60日低波(中性化)'),
]:
    f_df = pd.DataFrame(f_dict).T
    ic_df = compute_ic_series(f_df)
    if len(ic_df) == 0:
        print('%-12s: 无IC' % name)
        continue
    mean_ic = ic_df['ic'].mean()
    ic_ir = mean_ic / ic_df['ic'].std() if ic_df['ic'].std() > 0 else 0
    ic_pos = (ic_df['ic'] > 0).mean()
    print('%-12s  mean_IC=%+5.4f  IC_IR=%+6.2f  IC>0=%5.1f%%  N=%3d  (%s)'
          % (name, mean_ic, ic_ir, ic_pos * 100, len(ic_df), desc))


# ============================================================
# 7. 分层收益
# ============================================================
print('\n' + '=' * 60)
print('7. 分层收益 (训练集)')
print('=' * 60)

for name, f_dict, desc in [
    ('bp_neut',  bp_neut,  'BP(价值)'),
    ('rev_neut', rev_neut, '反转'),
    ('vol_neut', vol_neut, '低波'),
]:
    f_df = pd.DataFrame(f_dict).T
    if len(f_df) < 12:
        continue
    layers = layered_returns(f_df)
    monthly = {}
    print('\n--- %s ---' % desc)
    print('%-6s %8s %7s %7s %6s' % ('分组', '年化%', '夏普', '回撤%', '月数'))
    for g in sorted(layers.keys()):
        s = layers[g].dropna()
        if len(s) == 0:
            continue
        ann = s.mean() * 12
        vol = s.std() * np.sqrt(12)
        sr = ann / vol if vol > 0 else 0
        dd = (s.cumsum() - s.cumsum().cummax()).min()
        monthly[g] = ann
        print('%2d/%-2d  %+7.1f%% %6.2f %+6.1f%% %5d'
              % (g + 1, len(layers), ann * 100, sr, dd * 100, len(s)))
    if len(monthly) >= 2:
        rho = pd.Series(monthly).corr(
            pd.Series({g: g for g in monthly}), method='spearman')
        top_bot = monthly[max(monthly.keys())] - monthly[min(monthly.keys())]
        print('单调性 rho=%.3f  顶-底差=%+.2f%%' % (rho, top_bot * 100))


# ============================================================
# 8. 策略模拟 vs 基准
# ============================================================
print('\n' + '=' * 60)
print('8. 策略模拟 (训练集, N=%d)' % N_HOLD)
print('=' * 60)

ret_strat = simulate_strategy(final_score, N_HOLD)

if len(ret_strat) < 6:
    print('⚠ 有效月份不足 (%d < 6), 无法计算绩效。诊断: 请检查上面 simulate 输出。' % len(ret_strat))
    print('=' * 60)
    print('⛔ 研究终止 — 数据不足')
    import sys; sys.exit(0)

s_strat = strategy_stats(ret_strat)

# 基准
bench_train = bench_ret[bench_ret.index <= pd.Timestamp(TRAIN_END_DATE).date()]
common_m = ret_strat.index.intersection(bench_train.index)

s_bench = strategy_stats(bench_train[common_m])

print('%-20s %8s %6s %6s %7s %6s %6s' % ('', '年化%', '夏普', '卡玛', '波动%', '回撤%', '月胜率'))
for label, rets in [('CSI2000多因子', ret_strat),
                     ('CSI2000等权(基准)', bench_train[common_m])]:
    s = strategy_stats(rets)
    print('%-20s %+7.1f%% %5.2f %5.2f %6.1f%% %+6.1f%% %5.0f%%'
          % (label, s['年化%'], s['夏普'], s['卡玛'],
             s['波动%'], s['回撤%'], s['月胜率']))

if len(common_m) > 12:
    excess = ret_strat[common_m] - bench_train[common_m]
    ir = excess.mean() / excess.std() * np.sqrt(12) if excess.std() > 0 else 0
    print('\n超额(vs CSI2000等权): %+.1f%%/年  IR=%.2f'
          % (excess.mean() * 12 * 100, ir))

# 分年度
print('\n分年度 (超额 vs CSI2000等权):')
df_s = ret_strat.reset_index()
df_s.columns = ['date', 'ret']
df_s['year'] = pd.to_datetime(df_s['date']).dt.year

df_b = bench_train[common_m].reset_index()
df_b.columns = ['date', 'ret']
df_b['year'] = pd.to_datetime(df_b['date']).dt.year

for yr in sorted(df_s['year'].unique()):
    s_yr = df_s[df_s['year'] == yr]['ret']
    b_yr = df_b[df_b['year'] == yr]['ret']
    s_cum = (1 + s_yr).prod() - 1
    b_cum = (1 + b_yr).prod() - 1
    ex = s_cum - b_cum
    bar = '█' * max(0, int(s_cum * 100 / 5)) if s_cum >= 0 else '░' * max(0, int(-s_cum * 100 / 3))
    print('  %d  策略%+6.1f%%  基准%+6.1f%%  超额%+5.1f%%  %s'
          % (yr, s_cum * 100, b_cum * 100, ex * 100, bar))


# ============================================================
# 9. 前后段一致性
# ============================================================
print('\n' + '=' * 60)
print('9. 前后段一致性')
print('=' * 60)

mid_pt = pd.Timestamp('2019-01-01').date()
for pname, pdates in [('前半(2015-2018)', [d for d in ret_strat.index if d <= mid_pt]),
                        ('后半(2019-2022)', [d for d in ret_strat.index if d > mid_pt])]:
    sub = ret_strat[pdates]
    s = strategy_stats(sub)
    if s:
        print('%s: 年化%+.1f%%  夏普%.2f  回撤%.1f%%  月胜率%.0f%%  %d月'
              % (pname, s['年化%'], s['夏普'], s['回撤%'], s['月胜率'], s['月数']))

pre_d = [d for d in ret_strat.index if d <= mid_pt]
post_d = [d for d in ret_strat.index if d > mid_pt]
if len(pre_d) >= 8 and len(post_d) >= 8:
    sp = strategy_stats(ret_strat[pre_d])
    so = strategy_stats(ret_strat[post_d])
    ds = so['夏普'] - sp['夏普']
    dw = so['月胜率'] - sp['月胜率']
    print('→ 夏普差 %+.2f  |  月胜率差 %+.0f%%  %s'
          % (ds, dw, '⚠ 差异较大' if abs(ds) > 0.5 or abs(dw) > 15 else '✓ 前后一致'))


# ============================================================
# 🚫 10. 测试集一次性 Holdout
# ============================================================
print('\n' + '=' * 60)
print('10. 🚫 测试集 Holdout')
print('=' * 60)

ret_test = simulate_strategy(final_score, N_HOLD)
ret_test = ret_test[ret_test.index >= pd.Timestamp(TEST_START_DATE).date()]
s_test = strategy_stats(ret_test)

bench_test = bench_ret[bench_ret.index >= pd.Timestamp(TEST_START_DATE).date()]
ct = ret_test.index.intersection(bench_test.index)

print('%-20s %8s %6s %6s %7s %6s %6s' % ('', '年化%', '夏普', '卡玛', '波动%', '回撤%', '月胜率'))
for label, rets in [('CSI2000多因子(测试)', ret_test),
                     ('CSI2000等权(测试基准)', bench_test[ct])]:
    s = strategy_stats(rets)
    print('%-20s %+7.1f%% %5.2f %5.2f %6.1f%% %+6.1f%% %5.0f%%'
          % (label, s['年化%'], s['夏普'], s['卡玛'],
             s['波动%'], s['回撤%'], s['月胜率']))

if len(ct) > 6:
    excess_t = ret_test[ct] - bench_test[ct]
    print('\n超额(vs CSI2000等权): %+.1f%%/年  IR=%.2f'
          % (excess_t.mean() * 12 * 100,
             excess_t.mean() / excess_t.std() * np.sqrt(12)
             if excess_t.std() > 0 else 0))

# 训练 vs 测试
print('\n训练集 vs 测试集:')
for metric, tv in [('夏普', s_strat['夏普']), ('卡玛', s_strat['卡玛']),
                    ('月胜率', s_strat['月胜率']), ('回撤%', s_strat['回撤%'])]:
    tst_v = s_test[metric]
    diff = tst_v - tv
    flag = '⚠' if abs(diff) > {'夏普': 0.5, '卡玛': 0.5, '月胜率': 15, '回撤%': 10}[metric] else ''
    print('  %s:  训练%.2f → 测试%.2f  (差%+.2f) %s' % (metric, tv, tst_v, diff, flag))

print()
if s_test['夏普'] > 0.8 and s_test['月胜率'] > 55:
    print('✓ 通过 — 进入模拟盘')
elif s_test['夏普'] > 0.5:
    print('△ 边缘 — 进入模拟盘，标注"证据不足"')
else:
    print('✗ 不通过')
print('🚫 本次 holdout 已作废。')


# ============================================================
# 11. 总结
# ============================================================
print('\n' + '=' * 60)
print('11. 总结')
print('=' * 60)

print('\n========== CSI2000多因子 训练集 ==========')
print('年化: %+.1f%%  夏普: %.2f  卡玛: %.2f  回撤: %.1f%%  月胜率: %.0f%%'
      % (s_strat['年化%'], s_strat['夏普'], s_strat['卡玛'],
         s_strat['回撤%'], s_strat['月胜率']))

print('\n========== 达标检查 ==========')
for label, val, target in [
    ('夏普 > 1.0', s_strat['夏普'], 1.0),
    ('卡玛 > 1.0', s_strat['卡玛'], 1.0),
    ('月胜率 > 60%', s_strat['月胜率'], 60),
]:
    print('  %s: %s (%.2f vs %.1f)' % (label, '✓' if val > target else '✗', val, target))

print('\n========== 跨策略对比 ==========')
print('%-22s %8s %6s %7s %6s' % ('', '年化%', '夏普', '回撤%', '月胜率'))
print('%-22s %+7.1f%% %5.2f %+6.1f%% %5.0f%%' % ('CSI2000多因子',
        s_strat['年化%'], s_strat['夏普'], s_strat['回撤%'], s_strat['月胜率']))
print('%-22s %+7.1f%% %5.2f %+6.1f%% %5.0f%%' % ('CB纯双低(参考)',
        23.5, 1.50, -11.5, 64.6))
print('%-22s %+7.1f%% %5.2f %+6.1f%% %5.0f%%' % ('CSI1000增强(参考)',
        5.8, 0.49, -33.8, 55))
print()
print('⛔ 测试集触碰即作废。模拟盘是唯一前向验证路径。')

print('\n===== 研究完成 =====')
