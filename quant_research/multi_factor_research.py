# -*- coding: utf-8 -*-
# ============================================================
# 多因子选股研究脚本 (聚宽研究环境)
# ============================================================
# 用途: 单因子IC分析、分层回测、相关性矩阵、因子合成验证
# 使用: 在聚宽研究环境中逐个cell运行, 或整篇 Run All
#
# ⚠️ 本脚本是研究工具, 可反复在训练区间运行探索。
#    检验区间和留出区间在冻结策略后只能跑一次。
#
# 目标: 设计一个中证800内选股的多因子月频策略
#   候选因子: BP(价值) ROE(质量) 低波动 动量12-1 低换手
# ============================================================

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# 聚宽环境
from jqdata import *
from jqfactor import *

# 中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

print("=" * 70)
print("多因子选股研究系统 v1.0")
print("=" * 70)


# ============================================================
# 第一节: 参数与区间定义
# ============================================================

# ---- 区间定义 ----
# 训练区间: 可以反复探索, 跑无数次
TRAIN_START = '2015-01-01'
TRAIN_END   = '2021-12-31'

# 检验区间: 每个策略只能测一次! 测完不能回去改参数!
VAL_START   = '2022-01-01'
VAL_END     = '2024-12-31'

# 留出区间: 最终确认, 实盘前只测一次!
HOLDOUT_START = '2025-01-01'
HOLDOUT_END   = '2026-07-31'

# ---- 选股参数 ----
UNIVERSE    = '000906.XSHG'   # 中证800
N_QUANTILES = 5               # 分层数量
N_HOLD      = 30              # 目标持仓数

# ---- 数据清洗 ----
WINSOR_MAD   = 5              # MAD倍数
MIN_LIST_DAYS = 120           # 上市最短自然日

print(f"\n训练区间: {TRAIN_START} → {TRAIN_END}")
print(f"检验区间: {VAL_START} → {VAL_END}")
print(f"留出区间: {HOLDOUT_START} → {HOLDOUT_END}")
print(f"股票池: 中证800 ({UNIVERSE})")


# ============================================================
# 第二节: 数据加载
# ============================================================

def load_monthly_fundamentals(start_date, end_date):
    """
    逐月加载基本面数据和价格数据。

    返回 DataFrame, 每行 = (月份, 股票代码, 各因子原始值, 下月收益)
    """
    trade_days = list(get_trade_days(start_date=start_date, end_date=end_date))

    # 取每月最后一个交易日作为调仓日
    months = pd.Series(trade_days).groupby(
        pd.Series(trade_days).apply(lambda d: d.strftime('%Y-%m'))
    ).last().tolist()

    print(f"  调仓月份数: {len(months)} ({months[0].strftime('%Y-%m')} → {months[-1].strftime('%Y-%m')})")

    all_data = []

    for i, dt in enumerate(months):
        if i >= len(months) - 1:
            break  # 最后一个月没有下月收益

        next_dt = months[i + 1]

        # ---- 成分股 ----
        try:
            pool = get_index_stocks(UNIVERSE, date=dt)
        except:
            continue
        if len(pool) < 200:
            continue

        # ---- 基本面 (PB, ROE, 市值) ----
        try:
            fd = get_fundamentals(
                query(valuation.code, valuation.pb_ratio, valuation.market_cap,
                      indicator.roe).filter(valuation.code.in_(pool)),
                date=dt
            )
        except:
            continue
        if fd is None or fd.empty:
            continue
        fd = fd.set_index('code')
        fd = fd[fd['pb_ratio'] > 0]   # PB<=0 无意义
        fd = fd[fd['market_cap'] > 0]

        # ---- 构建截面 ----
        cross = pd.DataFrame(index=fd.index)
        cross['pb'] = fd['pb_ratio']
        cross['roe'] = fd['roe']
        cross['ln_mcap'] = np.log(fd['market_cap'])

        # ---- 价格数据 (需要更早的数据计算动量和波动率) ----
        lookback_start = dt - pd.Timedelta(days=400)  # 往前取足够覆盖252个交易日
        try:
            px = get_price(
                cross.index.tolist(),
                start_date=lookback_start,
                end_date=dt,
                fields=['close', 'volume', 'high', 'low'],
                fq='pre'
            )
        except:
            continue
        if px is None or px.empty:
            continue

        # 日收益 (用于波动率)
        ret = px['close'].pct_change().dropna(how='all')

        # ---- 计算因子 ----

        # BP (1/PB), 已经去除了 PB<=0
        cross['bp'] = 1.0 / cross['pb']

        # ROE 直接使用
        cross['roe_raw'] = cross['roe']

        # 低波动: 过去60个交易日收益率标准差
        vol_60d = ret.iloc[-60:].std()  # 至少60天数据
        cross['lowvol'] = -vol_60d       # 负号: 低波=高分

        # 动量12-1: 过去12个月(约252日)剔除最近1个月(约21日)
        if len(px['close']) >= 252:
            mom_12m1m = px['close'].iloc[-21] / px['close'].iloc[-252] - 1
            cross['mom_12m1m'] = mom_12m1m
        else:
            cross['mom_12m1m'] = np.nan

        # 低换手: 过去20日均换手率 (负号=低换手高分)
        if len(px['volume']) >= 20:
            turnover = px['volume'].iloc[-20:].mean()
            cross['turnover'] = -turnover
        else:
            cross['turnover'] = np.nan

        # ---- 行业 ----
        try:
            ind_info = get_industry(cross.index.tolist(), date=dt)
            cross['industry'] = [ind_info.get(c, {}).get('sw_l1', {}).get('industry_code', 'NA')
                                for c in cross.index]
        except:
            cross['industry'] = 'NA'

        # ---- 下月收益 ----
        try:
            next_px = get_price(
                cross.index.tolist(),
                start_date=dt,
                end_date=next_dt,
                fields=['close'],
                fq='pre'
            )
            if next_px is not None and not next_px.empty and 'close' in next_px:
                fwd_ret = next_px['close'].iloc[-1] / next_px['close'].iloc[0] - 1
                cross['fwd_ret'] = fwd_ret
            else:
                cross['fwd_ret'] = np.nan
        except:
            cross['fwd_ret'] = np.nan

        cross['date'] = dt
        cross['next_date'] = next_dt
        all_data.append(cross.reset_index())

        if (i + 1) % 20 == 0:
            print(f"    已处理 {i+1}/{len(months)-1} 个月份...")

    df = pd.concat(all_data, ignore_index=True)
    print(f"  总数据: {len(df)} 行, {df['code'].nunique()} 只股票")
    return df


def normalize_date_column(df):
    """统一为 pandas datetime，避免 datetime.date 与字符串无法比较。"""
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    return df


print("\n加载数据...")
# 加载全区间数据
data = normalize_date_column(
    load_monthly_fundamentals(TRAIN_START, HOLDOUT_END)
)
data['year'] = data['date'].dt.year


# ============================================================
# 第三节: 因子处理工具
# ============================================================

def winsorize_mad(s):
    """MAD 去极值"""
    s = s.dropna()
    if len(s) == 0:
        return s
    med = s.median()
    mad = (s - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return s
    scale = WINSOR_MAD * 1.4826 * mad
    return s.clip(med - scale, med + scale)


def zscore(s):
    """Z-Score 标准化"""
    s = s.dropna()
    if len(s) < 5:
        return s
    sd = s.std()
    if not sd or np.isnan(sd) or sd == 0:
        return s * 0.0
    return (s - s.mean()) / sd


def neutralize(s, industry, ln_mcap):
    """
    截面回归取残差: s ~ 行业哑变量 + ln(市值)
    剔除行业暴露和市值暴露
    """
    df = pd.concat([
        s.rename('y'),
        industry.rename('ind'),
        ln_mcap.rename('mc')
    ], axis=1, sort=False).dropna()

    if len(df) < 30 or df['ind'].nunique() < 2:
        return pd.Series(np.nan, index=s.index)

    dummies = pd.get_dummies(df['ind'], drop_first=True).astype(float)
    X = np.column_stack([np.ones(len(df)), df['mc'].values, dummies.values])
    y = df['y'].values

    try:
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X.dot(beta)
        return pd.Series(resid, index=df.index).reindex(s.index)
    except:
        return pd.Series(np.nan, index=s.index)


# 因子列表: (名称, 原始列名, 方向: +1=正向, -1=反向)
FACTOR_DEFS = [
    ('BP',     'bp',        +1),  # 价值: 市净率倒数
    ('ROE',    'roe_raw',   +1),  # 质量: 净资产收益率
    ('低波动',  'lowvol',    +1),  # 低波 (已取负号)
    ('动量12-1','mom_12m1m', +1),  # 趋势动量
    ('低换手',  'turnover',  +1),  # 低换手 (已取负号)
]


# ============================================================
# 第四节: 单因子 IC 分析
# ============================================================

def compute_ic_by_month(df, factor_col, start, end):
    """
    按月计算截面 Rank IC (Spearman)
    返回月度 IC Series 和汇总统计
    """
    chunk = df[(df['date'] >= start) & (df['date'] <= end)].copy()
    # 确保有下月收益
    chunk = chunk.dropna(subset=['fwd_ret'])

    ics = []
    for month, g in chunk.groupby('date'):
        g = g.dropna(subset=[factor_col, 'fwd_ret'])
        if len(g) < 30:
            continue
        ic, pval = stats.spearmanr(g[factor_col], g['fwd_ret'], nan_policy='omit')
        ics.append({'date': month, 'IC': ic if not np.isnan(ic) else 0})

    ic_df = pd.DataFrame(ics)
    if ic_df.empty:
        return None, None

    ic_series = ic_df.set_index('date')['IC']
    mean_ic = ic_series.mean()
    std_ic = ic_series.std()
    icir = mean_ic / std_ic if std_ic > 0 else 0
    pos_ratio = (ic_series > 0).mean()  # IC为正的月份占比

    return ic_series, {
        'Mean IC': mean_ic,
        'Std IC': std_ic,
        'ICIR': icir,
        'Pos Ratio': pos_ratio,
        't-stat': mean_ic / (std_ic / np.sqrt(len(ic_series))) if len(ic_series) > 0 else 0,
        'N months': len(ic_series),
    }


print("\n" + "=" * 70)
print("第四节: 单因子 IC 分析")
print("=" * 70)

for name, col, direction in FACTOR_DEFS:
    print(f"\n{'─' * 60}")
    print(f"因子: {name} ({col})")

    # ---- 训练区间 ----
    ic_train, stats_train = compute_ic_by_month(data, col, TRAIN_START, TRAIN_END)
    if stats_train:
        print(f"  [训练 {TRAIN_START[:4]}-{TRAIN_END[:4]}]  "
              f"Mean IC={stats_train['Mean IC']:.4f}  "
              f"ICIR={stats_train['ICIR']:.2f}  "
              f"IC>0月率={stats_train['Pos Ratio']:.0%}  "
              f"N={stats_train['N months']}")

    # ---- 检验区间 ----
    ic_val, stats_val = compute_ic_by_month(data, col, VAL_START, VAL_END)
    if stats_val:
        # 判断方向是否一致
        consistent = (np.sign(stats_train['Mean IC']) == np.sign(stats_val['Mean IC'])) \
                     if stats_train else 'N/A'
        print(f"  [检验 {VAL_START[:4]}-{VAL_END[:4]}]  "
              f"Mean IC={stats_val['Mean IC']:.4f}  "
              f"ICIR={stats_val['ICIR']:.2f}  "
              f"IC>0月率={stats_val['Pos Ratio']:.0%}  "
              f"方向一致={consistent}")

    # ---- 留出区间 ----
    ic_holdout, stats_holdout = compute_ic_by_month(data, col, HOLDOUT_START, HOLDOUT_END)
    if stats_holdout:
        print(f"  [留出 {HOLDOUT_START[:4]}-{HOLDOUT_END[:4]}]  "
              f"Mean IC={stats_holdout['Mean IC']:.4f}  "
              f"ICIR={stats_holdout['ICIR']:.2f}  "
              f"IC>0月率={stats_holdout['Pos Ratio']:.0%}")


# ============================================================
# 第五节: IC 衰减分析 (滞后1~6期)
# ============================================================

print("\n" + "=" * 70)
print("第五节: IC 衰减分析 (滞后1-6个月)")
print("=" * 70)

def compute_ic_decay(df, factor_col, start, end):
    """计算因子对未来1~6个月收益的IC衰减"""
    chunk = df[(df['date'] >= start) & (df['date'] <= end)].copy()
    chunk = chunk.sort_values(['code', 'date'])

    # 计算未来1~6月收益
    for lag in [1, 2, 3, 6]:
        chunk[f'fwd_ret_{lag}m'] = chunk.groupby('code')['fwd_ret'].shift(-(lag - 1))
        # 近似: 用每月的fwd_ret累乘
    chunk = chunk.dropna(subset=['fwd_ret'])

    # 简化: 计算factor和fwd_ret的IC
    results = {}
    for lag_label, lag_col in [('1M', 'fwd_ret')]:  # 只算1期简化
        ics = []
        for month, g in chunk.groupby('date'):
            g_clean = g.dropna(subset=[factor_col, lag_col])
            if len(g_clean) < 30:
                continue
            ic, _ = stats.spearmanr(g_clean[factor_col], g_clean[lag_col], nan_policy='omit')
            if not np.isnan(ic):
                ics.append(ic)
        if ics:
            results[lag_label] = np.mean(ics)
    return results


for name, col, direction in FACTOR_DEFS:
    decay = compute_ic_decay(data, col, TRAIN_START, TRAIN_END)
    ic_val = decay.get('1M', 0)
    print(f"  {name:10s}: 1个月 IC={ic_val:.4f}")


# ============================================================
# 第六节: 分层回测 (检验因子单调性)
# ============================================================

print("\n" + "=" * 70)
print("第六节: 分层回测")
print("=" * 70)

def quantile_backtest(df, factor_col, start, end, n_q=N_QUANTILES):
    """
    每月按因子值分成 n_q 组等权持有。
    返回每组净值序列。
    """
    chunk = df[(df['date'] >= start) & (df['date'] <= end)].copy()
    chunk = chunk.dropna(subset=[factor_col, 'fwd_ret'])

    nav = {q: [1.0] for q in range(1, n_q + 1)}
    dates = []

    for month, g in chunk.groupby('date'):
        if len(g) < n_q * 10:
            continue

        g['quantile'] = pd.qcut(g[factor_col], n_q, labels=False, duplicates='drop') + 1
        if g['quantile'].nunique() < n_q:
            continue

        dates.append(month)
        for q in range(1, n_q + 1):
            q_ret = g[g['quantile'] == q]['fwd_ret'].mean()
            prev_nav = nav[q][-1]
            nav[q].append(prev_nav * (1 + q_ret))

    if not dates:
        return None

    # nav 初始有 [1.0] (N+1 行), dates 只有 N 个月份 → 补一个起始日
    all_dates = [pd.to_datetime(dates[0]) - pd.DateOffset(months=1)] + list(dates)
    return pd.DataFrame(nav, index=pd.to_datetime(all_dates))


# 只做训练区间的分层回测（探索用）
for name, col, direction in FACTOR_DEFS:
    nav_df = quantile_backtest(data, col, TRAIN_START, TRAIN_END)
    if nav_df is not None:
        # Top Minus Bottom
        long_short = (nav_df[N_QUANTILES].iloc[-1] / nav_df[N_QUANTILES].iloc[0] - 1)
        top_bottom_annual = (nav_df[N_QUANTILES].iloc[-1] - nav_df[1].iloc[-1]) / len(nav_df) * 12

        print(f"\n  {name}:")
        for q in range(1, N_QUANTILES + 1):
            total_ret = nav_df[q].iloc[-1] - 1
            years = len(nav_df) / 12
            ann_ret = (nav_df[q].iloc[-1]) ** (1 / years) - 1 if years > 0 else 0
            print(f"    Q{q}: 总收益={total_ret:+.1%}  年化={ann_ret:+.1%}")

        # 单调性检验: Q1<Q2<Q3<Q4<Q5 的月数占比
        monthly_nav = nav_df.pct_change().dropna()
        monotonic = 0
        for _, row in monthly_nav.iterrows():
            if row.tolist() == sorted(row.tolist()):
                monotonic += 1
        mono_ratio = monotonic / len(monthly_nav) if len(monthly_nav) > 0 else 0
        print(f"    单调率={mono_ratio:.0%} | Q5-Q1 累计={nav_df[N_QUANTILES].iloc[-1] - nav_df[1].iloc[-1]:+.2%}")


# ============================================================
# 第七节: 因子相关性矩阵 (训练区间)
# ============================================================

print("\n" + "=" * 70)
print("第七节: 因子相关性矩阵")
print("=" * 70)

def compute_processed_factors(df_slice):
    """
    对截面数据做完整处理管线: 去极值 → 中性化 → 标准化
    返回处理后的因子 DataFrame
    """
    df = df_slice.dropna(subset=['fwd_ret']).copy()
    processed = pd.DataFrame(index=df.index)

    for name, col, direction in FACTOR_DEFS:
        if col not in df.columns:
            continue
        s = df[col].dropna()

        # 去极值
        s_win = winsorize_mad(s)

        # 中性化
        common_idx = s_win.index.intersection(df['industry'].dropna().index)
        common_idx = common_idx.intersection(df['ln_mcap'].dropna().index)
        s_neut = neutralize(
            s_win.loc[common_idx],
            df.loc[common_idx, 'industry'],
            df.loc[common_idx, 'ln_mcap']
        )

        # 标准化
        processed[name] = zscore(s_neut)

    return processed


# 取训练区间最后一个截面的因子值计算相关性
train_slice = data[(data['date'] >= TRAIN_START) & (data['date'] <= TRAIN_END)]
# 取最后一天
last_date = train_slice['date'].max()
last_cross = train_slice[train_slice['date'] == last_date]
processed_last = compute_processed_factors(last_cross)

if not processed_last.empty and len(processed_last.columns) >= 2:
    corr_matrix = processed_last.corr()
    print(f"\n  基于 {last_date.strftime('%Y-%m-%d')} 截面的因子相关性:")
    print(corr_matrix.round(3).to_string())

    # 平均绝对相关性
    off_diag = []
    for i in range(len(corr_matrix)):
        for j in range(i + 1, len(corr_matrix)):
            off_diag.append(abs(corr_matrix.iloc[i, j]))
    if off_diag:
        print(f"\n  平均绝对相关性: {np.mean(off_diag):.3f}")
else:
    print("  无法计算相关性矩阵 (数据不足)")


# ============================================================
# 第八节: 因子合成 + 组合回测
# ============================================================

print("\n" + "=" * 70)
print("第八节: 合成因子选股回测")
print("=" * 70)

def backtest_synthetic_factor(df, start, end, factor_names, n_hold=N_HOLD, label='',
                              exclude_factor=None, exclude_top_pct=0.0):
    """
    等权合成因子 → Top N 选股 → 月频等权换仓

    因子处理管线 (每月):
      原始值 → MAD去极值 → 行业+市值中性化 → z-score → 等权加总

    可选负向排除:
      exclude_factor: 因子列名, 剔除该因子值最差的 exclude_top_pct 比例股票
      (例如 lowvol 为负波动率, 剔除最低 20% = 剔除 60日波动最高 20%)
    """
    chunk = df[(df['date'] >= start) & (df['date'] <= end)].copy()
    chunk = chunk.sort_values(['date', 'code'])

    nav = [1.0]
    bench_nav = [1.0]
    dates = []
    turnovers = []

    months = sorted(chunk['date'].unique())
    last_held = set()

    for month in months:
        cross = chunk[chunk['date'] == month].dropna(subset=['fwd_ret'])

        # ---- 负向排除：剔除某因子最差尾端 (不用于打分, 仅做过滤) ----
        if (exclude_factor is not None and exclude_factor in cross.columns
                and exclude_top_pct > 0):
            valid_ex = cross[exclude_factor].dropna()
            if len(valid_ex) >= 50:
                threshold = valid_ex.quantile(exclude_top_pct)
                cross = cross[cross[exclude_factor] > threshold]

        # ---- 因子处理管线 ----
        scores = None
        valid_count = 0

        for name in factor_names:
            col_map = {f[0]: f[1] for f in FACTOR_DEFS}
            col = col_map.get(name)
            if col is None or col not in cross.columns:
                continue

            s = cross[col].dropna()

            # 去极值
            s_win = winsorize_mad(s)

            # 中性化
            common_idx = s_win.index.intersection(cross['industry'].dropna().index)
            common_idx = common_idx.intersection(cross['ln_mcap'].dropna().index)
            if len(common_idx) < 50:
                continue
            s_neut = neutralize(
                s_win.loc[common_idx],
                cross.loc[common_idx, 'industry'],
                cross.loc[common_idx, 'ln_mcap']
            )
            valid = s_neut.dropna()
            if len(valid) < 50:
                continue

            # 标准化
            s_z = zscore(valid)
            valid_count += 1

            if scores is None:
                scores = s_z.to_frame('score')
            else:
                scores['score'] = scores['score'].add(s_z, fill_value=None)

        if scores is None or valid_count < 2:
            # 因子数据不足，持有现金
            nav.append(nav[-1])
            if dates:
                bench_ret = chunk[chunk['date'] == dates[-1]]['fwd_ret'].mean()
            else:
                bench_ret = 0
            bench_nav.append(bench_nav[-1] * (1 + bench_ret))
            dates.append(month)
            continue

        # 等权平均
        scores['score'] = scores['score'] / valid_count

        # Top N — ranked.index 是整数行号, 需映射到股票代码
        ranked = scores['score'].sort_values(ascending=False)
        top_indices = ranked.index[:n_hold]
        targets = set(cross.loc[top_indices, 'code'].tolist())

        # 调仓: 计算换手
        if last_held:
            sold = len(last_held - targets)
            bought = len(targets - last_held)
            turnover = (sold + bought) / n_hold
        else:
            turnover = 1.0
        turnovers.append(turnover)
        last_held = targets

        # 本月收益 = 持仓等权平均
        port_ret = cross.set_index('code').loc[list(targets), 'fwd_ret'].mean()
        bench_ret = cross['fwd_ret'].mean()

        if pd.isna(port_ret):
            port_ret = 0
        if pd.isna(bench_ret):
            bench_ret = 0

        nav.append(nav[-1] * (1 + port_ret))
        bench_nav.append(bench_nav[-1] * (1 + bench_ret))
        dates.append(month)

    # ---- 绩效统计 ----
    # nav[N+1 行] ← 初始 1.0 + N 个月, dates[N 行] → 补一个起始日对齐
    if not dates:
        return None, None, {}
    start_dt = pd.to_datetime(dates[0]) - pd.DateOffset(months=1)
    all_dates = pd.to_datetime([start_dt] + list(dates))
    nav_s = pd.Series(nav, index=all_dates)
    bench_s = pd.Series(bench_nav, index=all_dates)

    years = (pd.to_datetime(end) - pd.to_datetime(start)).days / 365.25
    total_ret = nav_s.iloc[-1] - 1
    ann_ret = (nav_s.iloc[-1]) ** (1 / years) - 1 if years > 0 else 0

    bench_total = bench_s.iloc[-1] - 1
    bench_ann = bench_s.iloc[-1] ** (1 / years) - 1 if years > 0 else 0

    excess = ann_ret - bench_ann

    monthly_ret = nav_s.pct_change().dropna()
    ann_vol = monthly_ret.std() * np.sqrt(12)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    # 最大回撤
    peak = nav_s.expanding().max()
    dd = (nav_s / peak - 1)
    max_dd = dd.min()

    # 月度胜率
    win_rate = (monthly_ret > 0).mean()

    avg_turnover = np.mean(turnovers) if turnovers else 0

    result = {
        'label': label,
        '区间': f'{start[:4]}-{end[:4]}',
        '年化': f'{ann_ret:+.1%}',
        '基准年化': f'{bench_ann:+.1%}',
        '超额': f'{excess:+.1%}',
        '夏普': f'{sharpe:.2f}',
        '最大回撤': f'{max_dd:.1%}',
        '月度胜率': f'{win_rate:.0%}',
        '平均换手': f'{avg_turnover:.0%}',
        '因子数': len(factor_names),
        '持仓数': n_hold,
    }

    # 打印
    print(f"\n  [{label}] {start[:4]}-{end[:4]}:")
    print(f"    因子: {', '.join(factor_names)}")
    print(f"    年化: {ann_ret:+.1%} | 基准: {bench_ann:+.1%} | 超额: {excess:+.1%}")
    print(f"    夏普: {sharpe:.2f} | 最大回撤: {max_dd:.1%} | 月度胜率: {win_rate:.0%} | 平均换手: {avg_turnover:.0%}")

    return nav_s, bench_s, result


# ---- 测试不同因子组合 (只在训练区间!) ----
print("\n--- 训练区间因子组合测试 ---")

all_factors = [f[0] for f in FACTOR_DEFS]
results_summary = []

# 组合1: 全部5因子
nav1, bench1, r1 = backtest_synthetic_factor(
    data, TRAIN_START, TRAIN_END, all_factors, label='全5因子')
results_summary.append(r1)

# 组合2: 价值+质量 (只有基本面的稳健组合)
nav2, bench2, r2 = backtest_synthetic_factor(
    data, TRAIN_START, TRAIN_END, ['BP', 'ROE'], label='价值+质量')
results_summary.append(r2)

# 组合3: 全部因子但排除最弱的
nav3, bench3, r3 = backtest_synthetic_factor(
    data, TRAIN_START, TRAIN_END, ['BP', 'ROE', '低波动', '动量12-1'], label='4因子(无低换手)')
results_summary.append(r3)

# 组合4: BP + 低波动 (纯2因子, 看能否替代ROE)
nav4, bench4, r4 = backtest_synthetic_factor(
    data, TRAIN_START, TRAIN_END, ['BP', '低波动'], label='BP+低波动')
results_summary.append(r4)

# 组合5: BP+ROE + 低波动20%排除 (建议方案：保留BP+ROE, 剔除高波动尾端)
nav5, bench5, r5 = backtest_synthetic_factor(
    data, TRAIN_START, TRAIN_END, ['BP', 'ROE'],
    exclude_factor='lowvol', exclude_top_pct=0.20,
    label='BP+ROE_排除高波动20%')
results_summary.append(r5)

# 汇总表
print("\n\n--- 训练区间各组合对比 ---")
summary_df = pd.DataFrame(results_summary)
print(summary_df[['label', '年化', '超额', '夏普', '最大回撤', '月度胜率']].to_string(index=False))


# ============================================================
# 第九节: 最终选定组合 — 检验区间 (只跑一次!)
# ============================================================

print("\n" + "=" * 70)
print("第九节: 选定组合 — 检验区间验证 (只测一次!)")
print("=" * 70)

# ⚠️ 这里写死选定的因子组合 — 由训练区间结果决定
# 当前冻结策略为 BP + ROE; 若组合5(BP+ROE+低波动20%排除) 显著更优,
# 可更新 production 策略后再改此处。
SELECTED_FACTORS = ['BP', 'ROE']

nav_val, bench_val, r_val = backtest_synthetic_factor(
    data, VAL_START, VAL_END, SELECTED_FACTORS,
    label=f'选定组合({",".join(SELECTED_FACTORS)})')

# ---- 留出区间最终确认 ----
print("\n" + "=" * 70)
print("第十节: 留出区间最终确认 (只测一次!)")
print("=" * 70)

nav_ho, bench_ho, r_ho = backtest_synthetic_factor(
    data, HOLDOUT_START, HOLDOUT_END, SELECTED_FACTORS,
    label=f'选定组合({",".join(SELECTED_FACTORS)})')


# ============================================================
# 第十节: 综合报告
# ============================================================

print("\n\n" + "=" * 70)
print("综合报告")
print("=" * 70)

print(f"\n因子组合: {', '.join(SELECTED_FACTORS)}")
print(f"股票池: 中证800 ({UNIVERSE})")
print(f"持仓数: {N_HOLD}")
print(f"调仓频率: 月频")

print("\n┌──────────┬──────────┬──────────┬──────────┬──────────┐")
print("│   指标   │   训练   │   检验   │   留出   │   全区间 │")
print("├──────────┼──────────┼──────────┼──────────┼──────────┤")

# 全区间结果
nav_full, bench_full, r_full = backtest_synthetic_factor(
    data, TRAIN_START, HOLDOUT_END, SELECTED_FACTORS, label='全区间')

for metric in ['年化', '超额', '夏普', '最大回撤', '月度胜率']:
    print(f"│ {metric:8s} │ {r1[metric]:>8s} │ {r_val[metric]:>8s} │ {r_ho[metric]:>8s} │ {r_full[metric]:>8s} │")
print("└──────────┴──────────┴──────────┴──────────┴──────────┘")

print("\n" + "=" * 70)
print("研究脚本完成")
print("=" * 70)
print("\n下一步:")
print("1. 在训练区间反复跑 → 选因子组合 → 记录")
print("2. 在检验区间跑一次 → 确认因子未失效 → 记录")
print("3. 在留出区间跑一次 → 最终确认 → 冻结")
print("4. 写冻结规格文档 → 生成 BigQuant 生产脚本")
