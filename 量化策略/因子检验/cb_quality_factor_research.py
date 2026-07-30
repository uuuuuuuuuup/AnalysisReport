# -*- coding: utf-8 -*-
# ============================================================
# 质量增强可转债双低轮动 — 因子研究 (BigQuant Notebook)
# ============================================================
# ⛔ 数据边界：训练集 2019-01 ~ 2022-12 | 测试集 2023-01 ~ 2026-07 封存
#
# 本脚本 不包含任何测试集分析代码。所有 IC、分层、N 敏感性均限制在训练集内。
# 测试集只能在冻结参数后跑一次 holdout 脚本。
#
# 待检验因子：
# | 因子          | 定义                           | 方向     |
# |--------------|-------------------------------|---------|
# | f_price      | -z(转债价格)                    | 越低越好 |
# | f_premium    | -z(转股溢价率)                   | 越低越好 |
# | f_roe        | z(PB / PE_ttm)                | 越高越好 |
# | f_gross_margin | z(毛利率)                     | 越高越好 |
# | f_debt       | -z(资产负债率)                   | 越低越好 |
# | f_cash       | z(经营现金流/营收)               | 越高越好 |
# | f_quality    | mean(四个质量子因子)              | 越高越好 |
#
# 最终打分（先验固定）：
#   score = 0.40 × f_price + 0.30 × f_premium + 0.30 × f_quality
#
# 口径：
#   - 池子：全市场可转债（动态更新）
#   - 频率：月频（每月最后一个交易日）
#   - 收益：下一调仓日 close / 当前调仓日 close - 1，等权
#   - 过滤：上市≥30日 / 距到期>12月 / 非ST正股 / 信用过滤
#   - 动量硬排除：正股40日动量最差20%
#   - 去极值：MAD 5倍
# ============================================================

import dai
import pandas as pd
import numpy as np
import pickle
import os
from collections import OrderedDict

pd.set_option('display.width', 300)
pd.set_option('display.max_columns', 30)

# ==================== 配置 ====================
START_DATE = '2019-01-01'
END_DATE   = '2025-12-31'        # 取数终点

N_GROUPS   = 10
N_HOLD     = 20                   # 默认持仓数

# 先验固定权重（不可基于回测调整）
W_PRICE    = 0.40
W_PREMIUM  = 0.30
W_QUALITY  = 0.30

# 过滤参数
MIN_LIST_DAYS      = 30
MIN_TERM_MONTHS    = 12
CREDIT_PRICE_FLOOR = 80
CREDIT_PREMIUM_CEILING = 100
MOM_LOOKBACK       = 40         # 动量计算窗口
MOM_EXCLUDE_PCT    = 0.20       # 排除动量最差的20%

CACHE_DIR = 'cb_quality_cache'

# ⛔ ========== 数据墙 ==========
TRAIN_END_DATE  = '2022-12-31'     # 训练集终点 —— 不可逾越
TEST_START_DATE = '2023-01-01'     # 测试集起点 —— 不可触碰
# ⛔ ================================

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


def cache(name, builder):
    """缓存装饰器：已有则读，无则构建并保存。"""
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
# 1. 拉取 CB 日线 + 基本信息
# ============================================================
print('=' * 60)
print('1. 拉取可转债数据')
print('=' * 60)


def fetch_cb_data():
    """拉取 CB 日线和基本信息，连接正股代码。"""
    # 基本信息
    info = dai.query("""
        SELECT instrument, stock_code, maturity_date, list_date
        FROM cn_cbond_basic_info
        WHERE maturity_date IS NOT NULL
    """).df()
    info['maturity_date'] = pd.to_datetime(info['maturity_date'])
    info['list_date'] = pd.to_datetime(info['list_date'])
    print('CB基本信息: %d 只' % len(info))

    # 日线数据 — 分批拉取
    parts = []
    for year in range(2019, 2026):
        for half, (m1, m2) in enumerate([(1, 6), (7, 12)]):
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

    # 合并基本信息中的 stock_code, maturity_date, list_date
    info_map = info.set_index('instrument')
    cb_df['stock_code'] = cb_df['instrument'].map(info_map['stock_code'])
    cb_df['maturity_date'] = cb_df['instrument'].map(info_map['maturity_date'])
    cb_df['list_date'] = cb_df['instrument'].map(info_map['list_date'])

    # 获取所有出现过的正股代码（用于后续拉取正股数据）
    all_stocks = sorted(cb_df['stock_code'].dropna().unique())

    print('CB日线: %d 行, %d 标的, %d 正股, %s ~ %s'
          % (len(cb_df), cb_df['instrument'].nunique(),
             len(all_stocks),
             cb_df['date'].min().strftime('%Y-%m-%d'),
             cb_df['date'].max().strftime('%Y-%m-%d')))

    return cb_df, all_stocks


cb_df, ALL_STOCKS = cache('cb_data', fetch_cb_data)


# ============================================================
# 2. 构建调仓日 + 动态候选池
# ============================================================
print('\n' + '=' * 60)
print('2. 构建调仓日 & 候选池')
print('=' * 60)

all_dates = sorted(cb_df['date'].unique())
all_dates = pd.to_datetime(all_dates)

months = pd.Series(all_dates).dt.to_period('M').unique()
rebal_days = sorted([max(all_dates[pd.Series(all_dates).dt.to_period('M') == m])
                      for m in months])
rebal_days = [d.date() for d in rebal_days]

print('调仓日: %d 个, %s ~ %s' % (len(rebal_days),
      rebal_days[0], rebal_days[-1]))

# 训练/测试拆分（仅标记用）
train_days = [d for d in rebal_days if d <= pd.Timestamp(TRAIN_END_DATE).date()]
test_days  = [d for d in rebal_days if d >= pd.Timestamp(TEST_START_DATE).date()]
print('训练集调仓日: %d (%s ~ %s)' % (len(train_days), train_days[0], train_days[-1]))
print('测试集调仓日: %d (%s ~ %s) ← ⛔ 封存' % (len(test_days), test_days[0], test_days[-1]))


# ============================================================
# 3. 拉取正股数据
# ============================================================
print('\n' + '=' * 60)
print('3. 拉取正股数据')
print('=' * 60)

# --- 3a. 正股日线（动量计算） ---
PRICE_BATCH = 200
stock_batches = [(i, ALL_STOCKS[i:i + PRICE_BATCH])
                 for i in range(0, len(ALL_STOCKS), PRICE_BATCH)]


def fetch_stock_prices():
    """分批拉取所有正股日线收盘价。"""
    frames = []
    for batch_idx, batch in stock_batches:
        for year in range(2018, 2026):  # 2018 起用于动量计算
            for half, (m1, m2) in enumerate([(1, 6), (7, 12)]):
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
                    """, filters={
                        "date": [d1, d2],
                        "instrument": batch
                    }).df()
                    if len(part) > 0:
                        frames.append(part)
                except Exception:
                    pass
        if batch_idx % 3 == 0:
            print('  正股价 batch %d/%d' % (batch_idx + 1, len(stock_batches)))

    df = pd.concat(frames, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values(['date', 'instrument']).reset_index(drop=True)


stock_price_df = cache('stock_prices', fetch_stock_prices)
print('正股日线: %d 行, %d 标的' % (len(stock_price_df),
      stock_price_df['instrument'].nunique()))

# ---- 预计算 40 日动量矩阵 (大幅加速模拟回测) ----
print('预计算正股动量矩阵...')
_stock_pivot = stock_price_df.pivot_table(
    values='close', index='date', columns='instrument', aggfunc='last')
_stock_pivot = _stock_pivot.sort_index()

# 计算每个调仓日的 40 日动量 (之前收盘 / 40日前收盘 - 1)
_momentum_cache = {}
for i, d in enumerate(rebal_days):
    d_ts = pd.Timestamp(d)
    if d_ts not in _stock_pivot.index:
        # 找最近交易日
        avail = _stock_pivot.index[_stock_pivot.index <= d_ts]
        if len(avail) == 0:
            continue
        d_ts = avail[-1]

    # 找 40 个交易日前的位置
    idx_pos = _stock_pivot.index.get_loc(d_ts)
    lookback_pos = max(0, idx_pos - MOM_LOOKBACK)
    if lookback_pos == idx_pos:
        continue

    recent = _stock_pivot.iloc[idx_pos]
    base = _stock_pivot.iloc[lookback_pos]

    mom = (recent / base - 1).dropna()
    mom = mom[(mom > -1) & (mom < 10)]  # 过滤极端值
    if len(mom) > 0:
        _momentum_cache[d] = mom

print('  动量缓存: %d 期' % len(_momentum_cache))


# --- 3b. 正股估值（PB / PE → ROE 估算） ---
def fetch_stock_valuation():
    """逐期取 PB 和 PE_ttm。"""
    val_data = {}
    for i, d in enumerate(rebal_days):
        # 合并当前池子的正股 + ALL_STOCKS
        try:
            df = dai.query("""
                SELECT instrument, pb, pe_ttm
                FROM cn_stock_valuation_v6
            """, filters={"date": [d]}).df()
            if not df.empty:
                df = df[(df['pb'] > 0) & (df['pe_ttm'] > 0)]
                df['roe_est'] = df['pb'] / df['pe_ttm']
                df = df[(df['roe_est'] > 0) & (df['roe_est'] < 1.0)]
                df = df.set_index('instrument')
                val_data[d] = df['roe_est']
        except Exception:
            pass
        if i % 12 == 0:
            print('  valuation %s  已取%d期' % (d, len(val_data)))

    return pd.DataFrame(val_data).T


roe_tbl = cache('stock_valuation', fetch_stock_valuation)
print('ROE估算: %d 期 × %d 股票' % roe_tbl.shape)


# --- 3c. 正股财务数据（毛利率、资产负债率、经营现金流） ---
def fetch_stock_financials():
    """逐调仓日取最新季报财务数据。
    注意：BigQuant cn_stock_financial_v6 的字段名可能因版本不同有差异。
    如遇报错请根据实际字段调整 SELECT 列表。
    """
    fin_data = {}

    # 尝试拉取全部财报数据一次（减少查询次数）
    # cn_stock_financial_v6 包含 end_date 表示报告期
    try:
        all_fin = dai.query("""
            SELECT instrument, end_date,
                   gross_profit_margin,
                   debt_to_assets,
                   operating_cash_flow_to_revenue
            FROM cn_stock_financial_v6
            WHERE end_date >= '2018-01-01' AND end_date <= '%s'
            ORDER BY instrument, end_date
        """ % TRAIN_END_DATE).df()

        if len(all_fin) > 0:
            all_fin['end_date'] = pd.to_datetime(all_fin['end_date'])
            all_fin = all_fin.sort_values(['instrument', 'end_date'])

            for d in rebal_days:
                if d > pd.Timestamp(TRAIN_END_DATE).date():
                    break
                # 对每只股票取调仓日前最新一期财报
                cutoff = pd.Timestamp(d)
                latest = all_fin[all_fin['end_date'] <= cutoff] \
                    .groupby('instrument').last().reset_index()
                if not latest.empty:
                    fin_data[d] = latest.set_index('instrument')

            print('财务数据: 成功拉取, %d 期' % len(fin_data))
            return pd.DataFrame({
                d: fin_data[d]['gross_profit_margin']
                for d in fin_data if 'gross_profit_margin' in fin_data[d].columns
            }).T, pd.DataFrame({
                d: fin_data[d]['debt_to_assets']
                for d in fin_data if 'debt_to_assets' in fin_data[d].columns
            }).T, pd.DataFrame({
                d: fin_data[d]['operating_cash_flow_to_revenue']
                for d in fin_data if 'operating_cash_flow_to_revenue' in fin_data[d].columns
            }).T
    except Exception as e:
        print('⚠ 财务数据拉取失败: %s' % str(e)[:100])
        print('  质量因子将回退为仅使用 ROE 估算。')

    # 回退：返回空DataFrame
    empty = pd.DataFrame()
    return empty, empty, empty


gross_margin_tbl, debt_tbl, cashflow_tbl = cache(
    'stock_financials', fetch_stock_financials)

has_gross_margin = len(gross_margin_tbl) > 0
has_debt = len(debt_tbl) > 0
has_cashflow = len(cashflow_tbl) > 0

print('毛利率: %s | 资产负债率: %s | 经营现金流: %s'
      % (('✓ %d期×%d股' % gross_margin_tbl.shape) if has_gross_margin else '✗ 无数据',
         ('✓ %d期×%d股' % debt_tbl.shape) if has_debt else '✗ 无数据',
         ('✓ %d期×%d股' % cashflow_tbl.shape) if has_cashflow else '✗ 无数据'))

# 统计可用的质量子因子数量
QUALITY_SUB_FACTORS_AVAILABLE = 1  # ROE 始终可用
if has_gross_margin:
    QUALITY_SUB_FACTORS_AVAILABLE += 1
if has_debt:
    QUALITY_SUB_FACTORS_AVAILABLE += 1
if has_cashflow:
    QUALITY_SUB_FACTORS_AVAILABLE += 1
print('可用质量子因子: %d/4 (含ROE估算)' % QUALITY_SUB_FACTORS_AVAILABLE)


# ============================================================
# 4. 因子预处理工具
# ============================================================
print('\n' + '=' * 60)
print('4. 构建因子')
print('=' * 60)


def winsorize_mad(s, n_mad=5):
    """MAD 去极值。"""
    med = s.median()
    mad = (s - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return s
    return s.clip(med - n_mad * 1.4826 * mad, med + n_mad * 1.4826 * mad)


def zscore(s):
    """截面 z-score。"""
    sd = s.std()
    if not sd or np.isnan(sd):
        return s * 0.0
    return (s - s.mean()) / sd


# ---- 4a. 转债价格因子 (越低越好) ----
def build_price_factor():
    result = {}
    for d in rebal_days:
        sub = cb_df[cb_df['date'] == pd.Timestamp(d)]
        if len(sub) < 20:
            continue
        s = sub.set_index('instrument')['close'].dropna()
        s = s[s > 0]
        if len(s) < 20:
            continue
        s = winsorize_mad(s)
        s = -zscore(s)                 # 越低越好 → 取负
        result[d] = s
    return pd.DataFrame(result).T


price_factor = cache('factor_price', build_price_factor)
print('f_price: %d 期 × %d 标的' % price_factor.shape)


# ---- 4b. 溢价率因子 (越低越好) ----
def build_premium_factor():
    result = {}
    for d in rebal_days:
        sub = cb_df[cb_df['date'] == pd.Timestamp(d)]
        if len(sub) < 20:
            continue
        s = sub.set_index('instrument')['premium_rate'].dropna()
        if len(s) < 20:
            continue
        s = winsorize_mad(s)
        s = -zscore(s)                 # 越低越好 → 取负
        result[d] = s
    return pd.DataFrame(result).T


premium_factor = cache('factor_premium', build_premium_factor)
print('f_premium: %d 期 × %d 标的' % premium_factor.shape)


# ---- 4c. ROE 因子 (从 PB/PE 估算, 越高越好) ----
def build_roe_factor():
    result = {}
    cb_stock_map = cb_df[['instrument', 'stock_code']].drop_duplicates()
    inst_to_stock = dict(zip(cb_stock_map['instrument'], cb_stock_map['stock_code']))

    for d in roe_tbl.index:
        roe_s = roe_tbl.loc[d].dropna()
        if len(roe_s) < 20:
            continue
        roe_s = winsorize_mad(roe_s)
        roe_s = zscore(roe_s)

        # 映射到 CB instrument
        mapped = {}
        for inst, stk in inst_to_stock.items():
            if stk in roe_s.index:
                mapped[inst] = roe_s[stk]
        if len(mapped) >= 20:
            result[d] = pd.Series(mapped)
    return pd.DataFrame(result).T


roe_factor = cache('factor_roe', build_roe_factor)
print('f_roe: %d 期 × %d 标的' % roe_factor.shape)


# ---- 4d. 财务质量子因子 ----
def build_fin_factor(tbl, col_name, higher_is_better=True):
    """通用财务因子构建：映射 stock_code → CB instrument。"""
    if len(tbl) == 0:
        return pd.DataFrame()

    cb_stock_map = cb_df[['instrument', 'stock_code']].drop_duplicates()
    inst_to_stock = dict(zip(cb_stock_map['instrument'], cb_stock_map['stock_code']))

    result = {}
    for d in tbl.index:
        if d not in inst_to_stock:
            continue
        s = tbl.loc[d].dropna()
        if len(s) < 20:
            continue
        s = winsorize_mad(s)
        s = zscore(s)
        if not higher_is_better:
            s = -s

        mapped = {}
        for inst, stk in inst_to_stock.items():
            if stk in s.index:
                mapped[inst] = s[stk]
        if len(mapped) >= 20:
            result[d] = pd.Series(mapped)
    return pd.DataFrame(result).T


gross_margin_factor = build_fin_factor(gross_margin_tbl, 'gross_margin', higher_is_better=True)
debt_factor = build_fin_factor(debt_tbl, 'debt', higher_is_better=False)
cashflow_factor = build_fin_factor(cashflow_tbl, 'cashflow', higher_is_better=True)

if has_gross_margin:
    print('f_gross_margin: %d 期 × %d 标的' % gross_margin_factor.shape)
if has_debt:
    print('f_debt: %d 期 × %d 标的' % debt_factor.shape)
if has_cashflow:
    print('f_cashflow: %d 期 × %d 标的' % cashflow_factor.shape)


# ---- 4e. 质量合并因子 ----
def build_quality_composite():
    """等权合并所有可用质量子因子。缺失 ≥ 2 → 记为 0（退化为纯双低）。"""
    sub_factors = [roe_factor]
    if has_gross_margin:
        sub_factors.append(gross_margin_factor)
    if has_debt:
        sub_factors.append(debt_factor)
    if has_cashflow:
        sub_factors.append(cashflow_factor)

    # 取所有子因子的共同日期
    common_dates = sorted(set.intersection(
        *[set(f.index) for f in sub_factors]))
    print('质量子因子共同调仓日: %d' % len(common_dates))

    result = {}
    for d in common_dates:
        combined = None
        valid_count = None
        for f in sub_factors:
            if d not in f.index:
                continue
            s = f.loc[d].dropna()
            if combined is None:
                combined = pd.DataFrame({'val': s, 'cnt': 1})
            else:
                # 对齐 index
                common_idx = combined.index.intersection(s.index)
                combined = combined.loc[common_idx]
                combined['val'] = combined['val'] + s[common_idx]
                combined['cnt'] = combined['cnt'] + 1

        if combined is None or len(combined) < 20:
            continue

        # 至少需要 QUALITY_SUB_FACTORS_AVAILABLE - 1 个有效值
        min_needed = max(1, QUALITY_SUB_FACTORS_AVAILABLE - 1)
        combined['avg'] = combined['val'] / combined['cnt']
        combined.loc[combined['cnt'] < min_needed, 'avg'] = 0.0  # 退回中性
        result[d] = combined['avg']

    return pd.DataFrame(result).T


quality_factor = cache('factor_quality_composite', build_quality_composite)
print('f_quality: %d 期 × %d 标的' % quality_factor.shape)


# ---- 4f. 最终打分因子 ----
def build_final_score():
    """score = 0.40 × f_price + 0.30 × f_premium + 0.30 × f_quality"""
    common_dates = sorted(set(price_factor.index)
                          & set(premium_factor.index)
                          & set(quality_factor.index))
    print('最终打分共同调仓日: %d' % len(common_dates))

    result = {}
    for d in common_dates:
        p = price_factor.loc[d].dropna()
        pr = premium_factor.loc[d].dropna()
        q = quality_factor.loc[d].dropna()

        common = sorted(set(p.index) & set(pr.index) & set(q.index))
        if len(common) < 20:
            continue

        result[d] = (W_PRICE * p[common]
                     + W_PREMIUM * pr[common]
                     + W_QUALITY * q[common])
    return pd.DataFrame(result).T


final_score = cache('factor_final_score', build_final_score)
print('final_score: %d 期 × %d 标的' % final_score.shape)

# 纯双低对照因子
pure_double_low = {}
for d in sorted(set(price_factor.index) & set(premium_factor.index)):
    p = price_factor.loc[d].dropna()
    pr = premium_factor.loc[d].dropna()
    common = sorted(set(p.index) & set(pr.index))
    if len(common) >= 20:
        pure_double_low[d] = 0.5 * p[common] + 0.5 * pr[common]
pure_double_low = pd.DataFrame(pure_double_low).T
print('pure_double_low(对照): %d 期 × %d 标的' % pure_double_low.shape)


# ============================================================
# 5. 未来收益矩阵
# ============================================================
print('\n' + '=' * 60)
print('5. 构建未来收益矩阵')
print('=' * 60)


def build_fwd_returns():
    """月度 forward return: 下一调仓日 close / 当前调仓日 close - 1"""
    fwd = {}
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
            fwd[d] = pd.Series(row)

    return pd.DataFrame(fwd).T


fwd_ret = cache('fwd_returns', build_fwd_returns)
print('未来收益: %d 期 × %d 标的' % fwd_ret.shape)


# ============================================================
# ⛔ 以下所有分析均限制在训练集 (≤ 2022-12-31)
# ============================================================

def filter_train(factor_df):
    """仅保留训练集日期。"""
    dates = [d for d in factor_df.index
             if d <= pd.Timestamp(TRAIN_END_DATE).date()]
    return factor_df.loc[dates]


# ============================================================
# 6. 工具函数
# ============================================================

def compute_ic_series(factor_df, label=''):
    """Rank IC (Spearman)，仅训练集。"""
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


def layered_returns(factor_df, n_groups=N_GROUPS):
    """分层收益（等权），仅训练集。"""
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
        group_size = len(common) // n_groups
        for g in range(n_groups):
            start = g * group_size
            end = start + group_size if g < n_groups - 1 else len(common)
            idx = order[start:end]
            all_layers[g].append(rets.iloc[idx].mean())

    return {g: pd.Series(all_layers[g]) for g in range(n_groups)}


def analyze_layers(layers_dict, label):
    """打印分层收益 + 单调性。"""
    monthly = {}
    print('\n--- %s (训练集 %s ~ %s) ---' % (label, train_days[0], train_days[-1]))
    print('%-6s %8s %7s %7s %7s %6s' % ('分组', '年化%', '夏普', '波动%', '回撤%', '月数'))
    for g in sorted(layers_dict.keys()):
        s = layers_dict[g].dropna()
        if len(s) == 0:
            continue
        ann = s.mean() * 12
        vol = s.std() * np.sqrt(12)
        sr = ann / vol if vol > 0 else 0
        dd = (s.cumsum() - s.cumsum().cummax()).min()
        monthly[g] = ann
        print('%2d/%-2d   %+7.1f%% %6.2f %6.1f%% %+6.1f%% %5d'
              % (g + 1, len(layers_dict), ann * 100, sr, vol * 100, dd * 100, len(s)))

    if len(monthly) >= 2:
        rho = pd.Series(monthly).corr(
            pd.Series({g: g for g in monthly}), method='spearman')
        top_minus_bot = monthly[max(monthly.keys())] - monthly[min(monthly.keys())]
        print('单调性 spearman = %.3f  顶-底差 = %+.2f%%' % (rho, top_minus_bot * 100))


def simulate_strategy(factor_df, n_hold, with_filters=True):
    """
    模拟策略：选因子值最高的 n_hold 只，等权月频调仓。
    with_filters=True: 加入信用过滤 + 动量硬排除
    """
    factor_df = filter_train(factor_df)
    monthly_rets = {}
    all_stocks_ret = {}

    # 预计算每期的候选过滤条件
    for d in factor_df.index:
        if d not in fwd_ret.index:
            continue
        f_s = factor_df.loc[d].dropna()
        r_s = fwd_ret.loc[d].dropna()

        # 基础过滤
        cur = cb_df[cb_df['date'] == pd.Timestamp(d)]
        cur_info = cur.set_index('instrument')

        eligible = set(f_s.index) & set(r_s.index)
        if with_filters:
            for inst in list(eligible):
                if inst not in cur_info.index:
                    eligible.discard(inst)
                    continue
                info = cur_info.loc[inst]

                # 距到期 > 12 月
                mature = info['maturity_date']
                if pd.notna(mature):
                    months_left = (pd.Timestamp(mature) - pd.Timestamp(d)).days / 30.0
                    if months_left < MIN_TERM_MONTHS:
                        eligible.discard(inst)
                        continue

                # 上市 ≥ 30 天
                list_d = info['list_date']
                if pd.notna(list_d):
                    days_listed = (pd.Timestamp(d) - pd.Timestamp(list_d)).days
                    if days_listed < MIN_LIST_DAYS:
                        eligible.discard(inst)
                        continue

                # 信用过滤
                px = info['close'] if 'close' in info.index else np.nan
                prem = info['premium_rate'] if 'premium_rate' in info.index else np.nan
                if (pd.notna(px) and pd.notna(prem)
                        and px < CREDIT_PRICE_FLOOR
                        and prem > CREDIT_PREMIUM_CEILING):
                    eligible.discard(inst)
                    continue

        if len(eligible) < n_hold * 2:
            continue

        # 动量硬排除：正股 40 日动量最差 MOM_EXCLUDE_PCT
        if with_filters:
            eligible = _apply_momentum_filter(d, eligible, cur_info)

        if len(eligible) < n_hold * 2:
            continue

        eligible_list = sorted(eligible)
        f_vals = f_s[eligible_list]
        r_vals = r_s[eligible_list]

        top_n = f_vals.nlargest(min(n_hold, len(f_vals))).index
        rets = r_vals[top_n].dropna()
        if len(rets) >= n_hold * 0.5:
            monthly_rets[d] = rets.mean()
        all_stocks_ret[d] = r_vals.mean()

    return pd.Series(monthly_rets), pd.Series(all_stocks_ret)


def _apply_momentum_filter(d, eligible, cur_info):
    """动量硬排除：正股 40 日动量最差 MOM_EXCLUDE_PCT 剔除。
    使用预计算的 _momentum_cache，O(N) 查表替代 O(N×M) 逐券过滤。"""
    if d not in _momentum_cache:
        return eligible  # 无缓存时不过滤

    mom_all = _momentum_cache[d]  # Series: stock_instrument → momentum
    if len(mom_all) < 20:
        return eligible

    # inst → stock_code → momentum
    inst_to_stk = dict(zip(
        cb_df[cb_df['date'] == pd.Timestamp(d)]['instrument'],
        cb_df[cb_df['date'] == pd.Timestamp(d)]['stock_code']))
    inst_to_stk = {k: v for k, v in inst_to_stk.items()
                   if pd.notna(v)}

    inst_mom = {}
    for inst in eligible:
        stk = inst_to_stk.get(inst)
        if stk is not None and stk in mom_all.index:
            inst_mom[inst] = mom_all[stk]

    if len(inst_mom) < 20:
        return eligible

    cutoff_val = pd.Series(inst_mom).quantile(MOM_EXCLUDE_PCT)
    return {inst for inst, mom in inst_mom.items() if mom >= cutoff_val}


def strategy_stats(monthly_ret, benchmark_ret=None):
    """计算策略绩效指标。"""
    if len(monthly_ret) < 6:
        return {'年化%': np.nan, '夏普': np.nan, '卡玛': np.nan,
                '回撤%': np.nan, '月胜率': np.nan, '月数': len(monthly_ret)}

    ann_ret = monthly_ret.mean() * 12
    ann_vol = monthly_ret.std() * np.sqrt(12)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    cumsum_ret = monthly_ret.cumsum()
    maxdd = (cumsum_ret - cumsum_ret.cummax()).min()

    # 卡玛比率
    calmar = ann_ret / abs(maxdd) if maxdd < 0 else (ann_ret / 0.001 if maxdd == 0 else np.inf)

    win_rate = (monthly_ret > 0).mean()

    result = {
        '年化%': ann_ret * 100, '夏普': sharpe, '波动%': ann_vol * 100,
        '回撤%': maxdd * 100, '卡玛': calmar, '月胜率': win_rate * 100,
        '月数': len(monthly_ret)
    }

    if benchmark_ret is not None and len(benchmark_ret) > 0:
        common_idx = monthly_ret.index.intersection(benchmark_ret.index)
        if len(common_idx) > 6:
            excess = monthly_ret[common_idx] - benchmark_ret[common_idx]
            result['超额%'] = excess.mean() * 12 * 100
            result['IR'] = excess.mean() / excess.std() * np.sqrt(12) if excess.std() > 0 else 0

    return result


# ============================================================
# 7. 单因子 IC 分析
# ============================================================
print('\n' + '=' * 60)
print('7. 单因子 IC 分析 (训练集)')
print('=' * 60)

factor_configs = [
    ('f_price',          price_factor,          '转债价格(越低越好)'),
    ('f_premium',        premium_factor,        '转股溢价率(越低越好)'),
    ('f_roe',            roe_factor,            'ROE估算(越高越好)'),
]

if has_gross_margin:
    factor_configs.append(('f_gross_margin', gross_margin_factor, '毛利率(越高越好)'))
if has_debt:
    factor_configs.append(('f_debt', debt_factor, '资产负债率(越低越好)'))
if has_cashflow:
    factor_configs.append(('f_cashflow', cashflow_factor, '经营现金流/营收(越高越好)'))

factor_configs.append(('f_quality', quality_factor, '质量合并'))

ic_results = {}
for name, f_df, desc in factor_configs:
    ic_df = compute_ic_series(f_df)
    if len(ic_df) == 0:
        print('%-18s: 无有效IC' % name)
        continue
    mean_ic = ic_df['ic'].mean()
    ic_ir = mean_ic / ic_df['ic'].std() if ic_df['ic'].std() > 0 else 0
    ic_pos = (ic_df['ic'] > 0).mean()
    ic_results[name] = {'mean_ic': mean_ic, 'ic_ir': ic_ir,
                        'ic_pos': ic_pos, 'n': len(ic_df), 'desc': desc}
    print('%-18s  mean_IC=%+5.4f  IC_IR=%+6.2f  IC>0=%5.1f%%  N=%3d  (%s)'
          % (name, mean_ic, ic_ir, ic_pos * 100, len(ic_df), desc))

print('\n----- IC 汇总 -----')
ic_tbl = pd.DataFrame(ic_results).T
print(ic_tbl[['mean_ic', 'ic_ir', 'ic_pos', 'n']].to_string())


# ============================================================
# 8. 因子截面相关性
# ============================================================
print('\n' + '=' * 60)
print('8. 因子截面相关性 (训练集)')
print('=' * 60)

# 构建关键因子的截面相关性
key_factors = {
    'f_price': price_factor,
    'f_premium': premium_factor,
    'f_quality': quality_factor,
}
# 取共同日期（训练集内）
common_corr_dates = sorted(
    set.intersection(*[set(f.index) for f in key_factors.values()]))
common_corr_dates = [d for d in common_corr_dates
                     if d <= pd.Timestamp(TRAIN_END_DATE).date()]

corr_results = {k1: {} for k1 in key_factors}
for k1 in key_factors:
    for k2 in key_factors:
        corrs = []
        for d in common_corr_dates:
            s1 = key_factors[k1].loc[d].dropna()
            s2 = key_factors[k2].loc[d].dropna()
            common = sorted(set(s1.index) & set(s2.index))
            if len(common) >= 20:
                c = s1[common].corr(s2[common])
                if not np.isnan(c):
                    corrs.append(c)
        corr_results[k1][k2] = np.mean(corrs) if corrs else np.nan

corr_df = pd.DataFrame(corr_results).round(3)
print(corr_df.to_string())
print()
# 关键判断
pq_corr = corr_results['f_quality'].get('f_price', 0)
prem_q_corr = corr_results['f_quality'].get('f_premium', 0)
print('f_quality × f_price 相关: %.3f → %s'
      % (pq_corr, '质量与价格高度重叠，增量有限' if abs(pq_corr) > 0.4
         else '质量与价格独立，有分散价值'))
print('f_quality × f_premium 相关: %.3f → %s'
      % (prem_q_corr, '质量与溢价高度重叠' if abs(prem_q_corr) > 0.4
         else '质量与溢价独立'))


# ============================================================
# 9. 分层收益
# ============================================================
print('\n' + '=' * 60)
print('9. 分层收益 (训练集)')
print('=' * 60)

for name, f_df, desc in [
    ('f_price',   price_factor,   '转债价格'),
    ('f_premium', premium_factor, '转股溢价率'),
    ('f_quality', quality_factor, '质量合并'),
]:
    layers = layered_returns(f_df)
    analyze_layers(layers, desc)


# ============================================================
# 10. 策略模拟：质量增强 vs 纯双低 (训练集)
# ============================================================
print('\n' + '=' * 60)
print('10. 策略模拟对比 (训练集, N=%d)' % N_HOLD)
print('=' * 60)

# 质量增强
ret_enhanced, bench_enhanced = simulate_strategy(final_score, N_HOLD, with_filters=True)
stats_enhanced = strategy_stats(ret_enhanced, bench_enhanced)

# 纯双低对照
ret_pure, bench_pure = simulate_strategy(pure_double_low, N_HOLD, with_filters=True)
stats_pure = strategy_stats(ret_pure, bench_pure)

# 全池等权基准
bench_ret = pd.Series({d: fwd_ret.loc[d].mean()
                       for d in fwd_ret.index
                       if d <= pd.Timestamp(TRAIN_END_DATE).date()
                       and d in fwd_ret.index})

for label, stats, rets in [
    ('质量增强双低', stats_enhanced, ret_enhanced),
    ('纯双低(对照)', stats_pure, ret_pure),
]:
    print('%s: 年化%+.1f%%  夏普%.2f  卡玛%.2f  波动%.1f%%  回撤%.1f%%  '
          '月胜率%.1f%%  %d月'
          % (label, stats['年化%'], stats['夏普'], stats['卡玛'],
             stats['波动%'], stats['回撤%'], stats['月胜率'], stats['月数']))

if '超额%' in stats_enhanced and 'IR' in stats_enhanced:
    print('  超额%+.1f%%(vs全池)  IR=%.2f' % (stats_enhanced['超额%'], stats_enhanced['IR']))

# 质量增强 - 纯双低调仓重合度
common_rebal_dates = sorted(set(ret_enhanced.index) & set(ret_pure.index))
if len(common_rebal_dates) > 12:
    diff = ret_enhanced[common_rebal_dates] - ret_pure[common_rebal_dates]
    ann_diff = diff.mean() * 12
    corr_ep = ret_enhanced[common_rebal_dates].corr(ret_pure[common_rebal_dates])
    print('\n质量增强 vs 纯双低:')
    print('  月收益差 %+.2f%%  年化差 %+.1f%%  月收益相关 %.3f'
          % (diff.mean() * 100, ann_diff * 100, corr_ep))


# ============================================================
# 11. 前后段一致性
# ============================================================
print('\n' + '=' * 60)
print('11. 前后段一致性 (训练集拆分)')
print('=' * 60)

mid_point = pd.Timestamp('2021-01-01').date()
dates_sorted = sorted(ret_enhanced.index)
first_half = [d for d in dates_sorted if d <= mid_point]
second_half = [d for d in dates_sorted if d > mid_point]

for label, rets in [('质量增强双低', ret_enhanced), ('纯双低(对照)', ret_pure)]:
    print('\n%s:' % label)
    for period_name, period_dates in [('前半段(~2020)', first_half),
                                       ('后半段(2021~)', second_half)]:
        sub = rets[period_dates]
        if len(sub) < 8:
            continue
        ann = sub.mean() * 12
        vol = sub.std() * np.sqrt(12)
        sr = ann / vol if vol > 0 else 0
        dd = (sub.cumsum() - sub.cumsum().cummax()).min()
        wr = (sub > 0).mean()
        print('  %s: 年化%+.1f%%  夏普%.2f  回撤%.1f%%  月胜率%.0f%%  %d月'
              % (period_name, ann * 100, sr, dd * 100, wr * 100, len(sub)))

    if len(first_half) >= 8 and len(second_half) >= 8:
        s_pre = strategy_stats(rets[first_half])
        s_post = strategy_stats(rets[second_half])
        delta_sr = s_post['夏普'] - s_pre['夏普']
        delta_wr = s_post['月胜率'] - s_pre['月胜率']
        print('  → 夏普差 %+.2f  |  月胜率差 %+.0f%%  %s'
              % (delta_sr, delta_wr,
                 '⚠ 前后段差异较大' if abs(delta_sr) > 0.5 else '✓ 前后段一致'))


# ============================================================
# 12. N × w_quality 稳健性网格 (训练集)
# ============================================================
print('\n' + '=' * 60)
print('12. N × w_quality 稳健性 (训练集)')
print('=' * 60)
print('(IS/OOS 相关性已在 CSI1000 验证为负，此网格仅确认参数不敏感，不用于选最优)')
print()

grid_rows = []
for n in [15, 20, 30]:
    for w_q in [0.20, 0.30, 0.40]:
        w_p = (1.0 - w_q) * 0.57    # 0.40/(0.40+0.30) = 0.571
        w_pr = (1.0 - w_q) * 0.43   # 0.30/(0.40+0.30) = 0.429

        # 用不同的权重重新计算得分
        score_variant = {}
        common_dates_v = sorted(set(price_factor.index)
                                & set(premium_factor.index)
                                & set(quality_factor.index))
        for d in common_dates_v:
            p = price_factor.loc[d].dropna()
            pr = premium_factor.loc[d].dropna()
            q = quality_factor.loc[d].dropna()
            common = sorted(set(p.index) & set(pr.index) & set(q.index))
            if len(common) >= n * 2:
                score_variant[d] = w_p * p[common] + w_pr * pr[common] + w_q * q[common]

        score_variant = filter_train(pd.DataFrame(score_variant).T)
        ret_v, _ = simulate_strategy(score_variant, n, with_filters=True)
        stats_v = strategy_stats(ret_v)
        grid_rows.append({'N': n, 'w_quality': w_q,
                          'w_price': round(w_p, 2), 'w_premium': round(w_pr, 2),
                          '年化%': stats_v['年化%'], '夏普': stats_v['夏普'],
                          '卡玛': stats_v['卡玛'], '回撤%': stats_v['回撤%'],
                          '月胜率': stats_v['月胜率']})

grid_df = pd.DataFrame(grid_rows)
print(grid_df.to_string(index=False))

print('\n--- 汇总 ---')
print('夏普: median=%.2f  min=%.2f  max=%.2f  range=%.2f'
      % (grid_df['夏普'].median(), grid_df['夏普'].min(),
         grid_df['夏普'].max(), grid_df['夏普'].max() - grid_df['夏普'].min()))
print('月胜率: median=%.0f%%  min=%.0f%%  max=%.0f%%'
      % (grid_df['月胜率'].median(), grid_df['月胜率'].min(), grid_df['月胜率'].max()))

for n in [15, 20, 30]:
    sub = grid_df[grid_df['N'] == n]
    print('N=%d: 夏普 median=%.2f  range[%.2f, %.2f]'
          % (n, sub['夏普'].median(), sub['夏普'].min(), sub['夏普'].max()))

for w_q in [0.20, 0.30, 0.40]:
    sub = grid_df[grid_df['w_quality'] == w_q]
    print('w_quality=%.0f%%: 夏普 median=%.2f  range[%.2f, %.2f]'
          % (w_q * 100, sub['夏普'].median(), sub['夏普'].min(), sub['夏普'].max()))


# ============================================================
# 13. 分年度收益
# ============================================================
print('\n' + '=' * 60)
print('13. 分年度收益 (训练集)')
print('=' * 60)

for label, rets in [('质量增强双低', ret_enhanced), ('纯双低(对照)', ret_pure)]:
    print('\n%s:' % label)
    df = rets.reset_index()
    df.columns = ['date', 'ret']
    df['year'] = pd.to_datetime(df['date']).dt.year
    for yr, grp in df.groupby('year'):
        cum = (1 + grp['ret']).prod() - 1
        bar = '█' * max(0, int(cum * 100 / 5)) if cum >= 0 else '░' * max(0, int(-cum * 100 / 3))
        print('  %4d  %+6.1f%%  %s' % (yr, cum * 100, bar))

    ann = rets.mean() * 12
    vol = rets.std() * np.sqrt(12)
    sr = ann / vol if vol > 0 else 0
    print('  全训练集: 年化%+.1f%%  夏普%.2f  回撤%.1f%%  %d月'
          % (ann * 100, sr, (rets.cumsum() - rets.cumsum().cummax()).min() * 100,
             len(rets)))


# ============================================================
# 14. 与纯双低的增量分析
# ============================================================
print('\n' + '=' * 60)
print('14. 增量分析：质量增强 vs 纯双低')
print('=' * 60)

common_dates_comp = sorted(set(ret_enhanced.index) & set(ret_pure.index))
if len(common_dates_comp) > 12:
    diff_series = ret_enhanced[common_dates_comp] - ret_pure[common_dates_comp]
    ann_diff = diff_series.mean() * 12
    t_stat = diff_series.mean() / diff_series.std() * np.sqrt(len(diff_series)) \
        if diff_series.std() > 0 else 0
    diff_pos = (diff_series > 0).mean()

    print('月收益差异: mean=%+.3f%%  std=%.3f%%  t=%.2f'
          % (diff_series.mean() * 100, diff_series.std() * 100, t_stat))
    print('年化超额: %+.1f%%' % (ann_diff * 100))
    print('跑赢月份: %.0f%% (%d/%d)'
          % (diff_pos * 100, (diff_series > 0).sum(), len(diff_series)))

    # 分年看差异
    diff_df = diff_series.reset_index()
    diff_df.columns = ['date', 'diff']
    diff_df['year'] = pd.to_datetime(diff_df['date']).dt.year
    print('\n分年差异:')
    for yr, grp in diff_df.groupby('year'):
        print('  %4d  %+.1f%%/月  (%+.1f%%/年)'
              % (yr, grp['diff'].mean() * 100, grp['diff'].mean() * 12 * 100))

    # 判断
    print()
    if ann_diff > 0.01 and t_stat > 1.0:
        print('✓ 质量因子在训练集上有正向贡献 (年化提升 +%.1f%%)' % (ann_diff * 100))
    elif ann_diff > -0.01:
        print('○ 质量因子在训练集上接近中性 (年化差 %+.1f%%)' % (ann_diff * 100))
    else:
        print('✗ 质量因子在训练集上有负向贡献，应重新审视因子定义')
else:
    print('共同调仓日期不足，无法做增量分析')


# ============================================================
# 15. 训练集总结 & 冻结参数建议
# ============================================================
print('\n' + '=' * 60)
print('15. 训练集总结 & 冻结参数建议')
print('=' * 60)

print()
print('========== 质量增强双低 (N=%d) ==========' % N_HOLD)
print('年化收益:  %+.1f%%' % stats_enhanced['年化%'])
print('夏普:     %.2f' % stats_enhanced['夏普'])
print('卡玛:     %.2f' % stats_enhanced['卡玛'])
print('波动:     %.1f%%' % stats_enhanced['波动%'])
print('最大回撤:  %.1f%%' % stats_enhanced['回撤%'])
print('月胜率:   %.1f%%' % stats_enhanced['月胜率'])
print('月数:     %d' % stats_enhanced['月数'])

print()
print('========== 纯双低对照 (N=%d) ==========' % N_HOLD)
print('年化收益:  %+.1f%%' % stats_pure['年化%'])
print('夏普:     %.2f' % stats_pure['夏普'])
print('卡玛:     %.2f' % stats_pure['卡玛'])
print('最大回撤:  %.1f%%' % stats_pure['回撤%'])
print('月胜率:   %.1f%%' % stats_pure['月胜率'])

print()
print('========== 冻结参数建议 ==========')
print('打分:  %.0f%% × f_price + %.0f%% × f_premium + %.0f%% × f_quality'
      % (W_PRICE * 100, W_PREMIUM * 100, W_QUALITY * 100))
print('质量子因子: ROE估算', end='')
if has_gross_margin:
    print(' + 毛利率', end='')
if has_debt:
    print(' + 资产负债率', end='')
if has_cashflow:
    print(' + 经营现金流/营收', end='')
print('  等权合并  缺失≥2 → 退化为0(纯双低兜底)')
print('持仓:  N=%d, 等权' % N_HOLD)
print('调仓:  月频 (月末最后一个交易日)')
print('池子:  全市场可转债')
print('过滤:  上市≥30日 / 到期>12月 / 信用过滤(低债价+高溢价)')
print('        + 正股40日动量最差%.0f%%硬排除' % (MOM_EXCLUDE_PCT * 100))
print('去极值: MAD 5倍')
print('中性化: 不做')
print()
print('训练集%d个月，夏普标准误 ≈ %.2f'
      % (len(ret_enhanced),
         np.sqrt((1 + stats_enhanced['夏普']**2 / 2) / len(ret_enhanced)) * np.sqrt(12)))
print('→ 95%% 置信区间较宽，参数选择应保守（不做数据驱动优化）。')
print()
print('⛔ 以上全部来自训练集。测试集 (2023-01 ~ 2026-07) 未被触碰。')
print('冻结参数后，只能跑一次 holdout 脚本来获取测试集结果。')

print('\n===== 研究完成 =====')
