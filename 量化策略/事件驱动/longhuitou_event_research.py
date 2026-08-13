# -*- coding: utf-8 -*-
# ============================================================
# 龙回头/多头回踩规律 事件研究 (BigQuant 研究环境)
# ============================================================
# 研究问题:
#   强势股上升趋势中出现"高换手冒尖"后, 后续走势分化为——
#   A 洗盘: 缩量回踩至 MA10/MA20 附近企稳, 行情延续
#   B 出货: 放量下跌或滞涨, 主力派发
#   本脚本用全A股 2016-01 ~ 2026-06 日线数据, 多参数扫描验证
#   两组事件的前向收益差异是否统计显著且稳健。
#
# 运行方式 (BigQuant 研究环境):
#   1. 新建研究 Notebook, 将本文件全部内容粘贴进一个 cell
#   2. 运行: 自动分批拉取全A日线 → pickle 缓存 → 事件检测 →
#      分组判定 → 前向收益 → 统计检验 → output/ 下 CSV + 报告
#   3. 二次运行跳过拉数 (缓存命中); 快速试跑设 CONFIG['sample_stocks']
#
# 数据表:
#   - cn_stock_bar1d          日线行情 (date/instrument/open/high/low/close/volume/amount/turn/name)
#                             换手率字段为 turn(口径自动归一化为小数), name 用于逐日ST过滤
#   - cn_stock_basic_info     基本信息 (list_date, 用于剔除次新)
#   - cn_stock_valuation_v6   市值 (月末快照, 用于大/中/小分组)
#   注: 换手率字段缺失时脚本报 RuntimeError; 换手率口径(小数/百分比)自动归一化
#
# 输出文件 (out_dir):
#   events_<spike>_<gp>.csv   每参数组合事件库
#   events_main.csv           基准组合(abs15×D10)事件库
#   events_control.csv        对照样本事件库
#   stats_summary.csv         全参数组合统计矩阵 (均值差/t值/p值/显著性)
#   yearly_20d.csv            分年度 20日检验
#   size_20d.csv              分市值 20日检验
#   control_20d.csv           对照检验 (冒尖事件 vs 趋势日无高换手)
#   report.md                 研究报告
#   chart_*.png               图表
#
# 数据墙: 本计划为事件统计研究(非参数拟合), 参数来自经验而非训练集,
#         不设训练/测试切分; 稳健性由分年度 + 多参数矩阵检验承担。
# ============================================================

try:
    import dai
except ImportError:
    dai = None  # 本地无 dai 时仅支持缓存模式 (测试/离线分析)

import numpy as np
import pandas as pd
import os
import time
from datetime import datetime

# ============================================================
# 配置
# ============================================================
CONFIG = {
    'start_date': '2016-01-01',
    'end_date':   '2026-06-30',
    'cache_dir':  'longhuitou_cache',   # 本地/工作区缓存目录
    'out_dir':    'output',             # 输出目录
    'fetch_batch': 200,                 # 每批拉取股票数

    # 高换手冒尖定义 (各定义生成独立事件集)
    'spike_configs': [
        {'abs': 0.10}, {'abs': 0.15}, {'abs': 0.18}, {'abs': 0.20},
        {'rel': 3.0},                  # 相对: 换手 ≥ 3×20日均值
    ],

    # 分组判定参数 (D 窗口, 缩量比例, 放量比例, 放量跌幅)
    'group_params': [
        {'D': 10, 'shrink': 0.3, 'up_vol': 0.6, 'up_drop': 0.05},
        {'D': 10, 'shrink': 0.5, 'up_vol': 0.8, 'up_drop': 0.03},
        {'D': 15, 'shrink': 0.5, 'up_vol': 0.6, 'up_drop': 0.05},
        {'D': 15, 'shrink': 0.3, 'up_vol': 0.8, 'up_drop': 0.03},
    ],
    'horizons': [5, 10, 20, 60],

    # 判定细节
    'wash_ma_pct': 0.03,        # 触及均线 ±3%
    'floor_drawdown': 0.15,     # 回踩不破冒尖高点-15%
    'stagnant_pct': 0.03,       # 滞涨: 窗口最高 ≤ 冒尖高点×1.03
    'min_60d_return': 0.20,     # 强势: 60日涨幅 ≥ 20%
    'dedupe_gap_days': 30,      # 同股事件去重间隔
    'min_list_days': 250,       # 剔除上市不足250自然日
    'control_sample_n': 50000,  # 对照样本数 (趋势日但非高换手)
    'sample_stocks': None,      # 快速试跑: 只取前 N 只 (None=全部)
}

# ============================================================
# 数据层: 缓存读写
# ============================================================
def save_cache(cache_dir, data):
    """data: {'bar': DataFrame, 'basic': DataFrame|None, 'valuation': DataFrame|None}"""
    os.makedirs(cache_dir, exist_ok=True)
    for key, df in data.items():
        path = os.path.join(cache_dir, key + '.pkl')
        pd.to_pickle(df, path)


def load_cache(cache_dir):
    out = {'bar': None, 'basic': None, 'valuation': None}
    for key in out:
        path = os.path.join(cache_dir, key + '.pkl')
        if os.path.exists(path):
            out[key] = pd.read_pickle(path)
    return out


def _normalize_turnover(s):
    """换手率统一为小数口径: 若多数值 >1 视为百分比。"""
    s = pd.to_numeric(s, errors='coerce')
    if s.max() > 1.0:
        s = s / 100.0
    return s


# ============================================================
# 数据层: dai 拉取 (BigQuant 环境)
# ============================================================
def _query_columns(sql, filters=None):
    """运行 dai 查询并打印列名, 返回 DataFrame。"""
    df = dai.query(sql, filters=filters or {}).df()
    print('  列:', list(df.columns))
    return df


def fetch_bars_dai(codes, start, end, batch=200):
    """分批拉取日线。返回 concat 后的 DataFrame。

    cn_stock_bar1d 的换手率字段为 turn (非 turnover), 口径自动归一化;
    name 字段用于逐日 ST 过滤。
    """
    frames = []
    for i in range(0, len(codes), batch):
        chunk = codes[i:i + batch]
        sql = (
            "SELECT date, instrument, open, high, low, close, volume, amount, "
            "turn, name "
            "FROM cn_stock_bar1d WHERE instrument IN ('" + "','".join(chunk) + "') "
            "AND close > 0 ORDER BY instrument, date"
        )
        df = dai.query(sql, filters={"date": [start, end]}).df()
        frames.append(df)
        print(f'  批次 {i // batch + 1}/{(len(codes) - 1) // batch + 1}: '
              f'{len(chunk)} 只, {len(df)} 行')
        time.sleep(1)
    return pd.concat(frames, ignore_index=True)


def fetch_basic_info_dai():
    """股票基本信息: list_date 与名称(ST判定)。表缺失时返回 None。"""
    try:
        return _query_columns(
            "SELECT instrument, list_date, name FROM cn_stock_basic_info")
    except Exception as e:
        print(f'  ⚠️ cn_stock_basic_info 不可用({e}), 跳过次新/ST过滤')
        return None


def fetch_valuation_snapshots_dai(start, end):
    """月末市值快照 (total_market_cap), 用于大/中/小分组。"""
    try:
        return _query_columns(
            "SELECT date, instrument, total_market_cap "
            "FROM cn_stock_valuation_v6 WHERE total_market_cap > 0")
    except Exception as e:
        print(f'  ⚠️ cn_stock_valuation_v6 不可用({e}), 跳过市值分组')
        return None


def build_cache(cfg):
    """全流程拉数: 代码清单 → 分批日线 → 基本信息 → 市值快照 → 缓存。"""
    print('=' * 60)
    print('拉取数据: %s ~ %s' % (cfg['start_date'], cfg['end_date']))
    print('=' * 60)
    basic = fetch_basic_info_dai()
    if basic is not None and len(basic):
        codes = sorted(basic['instrument'].dropna().unique().tolist())
    else:
        inst = _query_columns(
            "SELECT DISTINCT instrument FROM cn_stock_bar1d",
            filters={"date": [cfg['start_date'], cfg['end_date']]})
        codes = sorted(inst['instrument'].unique().tolist())
    if cfg['sample_stocks']:
        codes = codes[:cfg['sample_stocks']]
    print(f'标的数: {len(codes)}, 按 {cfg["fetch_batch"]} 只/批拉取...')
    bar = fetch_bars_dai(codes, cfg['start_date'], cfg['end_date'], cfg['fetch_batch'])
    if 'turnover' in bar.columns:
        bar['turnover'] = _normalize_turnover(bar['turnover'])
    elif 'turn' in bar.columns:
        bar['turnover'] = _normalize_turnover(bar['turn'])
    elif 'turnover_ratio' in bar.columns:
        bar['turnover'] = _normalize_turnover(bar['turnover_ratio'])
    else:
        raise RuntimeError('cn_stock_bar1d 无 turn/turnover/turnover_ratio 字段, 无法研究高换手现象')
    bar['date'] = pd.to_datetime(bar['date'])
    valuation = fetch_valuation_snapshots_dai(cfg['start_date'], cfg['end_date'])
    if valuation is not None and len(valuation):
        valuation['date'] = pd.to_datetime(valuation['date'])
        # 保留每月最后一个交易日快照
        valuation = valuation.sort_values('date').groupby(
            [valuation['instrument'], valuation['date'].dt.to_period('M')]).tail(1)
    save_cache(cfg['cache_dir'], {'bar': bar, 'basic': basic, 'valuation': valuation})
    print(f'缓存完成: {cfg["cache_dir"]}/  (bar {len(bar)} 行)')


# ============================================================
# 指标计算
# ============================================================
def add_indicators(df):
    """按日期升序补齐技术指标列。df 需含 open/high/low/close/volume/turnover。"""
    df = df.sort_values('date').reset_index(drop=True).copy()
    df['prev_close'] = df['close'].shift(1)
    df['ret'] = df['close'] / df['prev_close'] - 1
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma20_shift5'] = df['ma20'].shift(5)
    df['turnover_ma20'] = df['turnover'].rolling(20).mean()
    df['ret60'] = df['close'] / df['close'].shift(60) - 1
    # 一字涨停: 开盘=最高=最低且涨幅≥9.5% (近似, 用于事件日剔除)
    df['yiziban'] = ((df['open'] == df['high']) & (df['open'] == df['low'])
                     & (df['ret'] >= 0.095))
    return df


# ============================================================
# 事件检测 (向量化, 逐股)
# ============================================================
def compute_flags(df, spike_cfg):
    """返回 trend_day / spike_day 布尔列 (已含趋势前置与一字剔除)。"""
    df = df.copy()
    df['trend_day'] = ((df['close'] > df['ma20'])
                       & (df['ma20'] > df['ma20_shift5'])
                       & (df['ret60'] >= CONFIG['min_60d_return']))
    if spike_cfg.get('abs'):
        df['spike_day'] = df['turnover'] >= spike_cfg['abs']
    else:
        df['spike_day'] = df['turnover'] >= spike_cfg['rel'] * df['turnover_ma20']
    df['spike_day'] = df['spike_day'] & df['trend_day'] & ~df['yiziban']
    # 逐日 ST 过滤 (仅当行情带 name 字段时; 合成数据无此列自动跳过)
    if 'name' in df.columns:
        df['spike_day'] = (df['spike_day']
                           & ~df['name'].astype(str).str.contains('ST', na=False))
    return df


def detect_events(df, spike_cfg):
    """检测单只股票的高换手冒尖事件与对照样本(趋势日但非高换手)。

    返回 (events, controls):
      events  : list[dict], {instrument, t_index, date, spike_high, spike_vol, spike_turnover}
      controls: list[dict], {instrument, t_index, date}
    """
    fl = compute_flags(df, spike_cfg)
    idx = np.flatnonzero(fl['spike_day'].values)
    events = [{
        'instrument': df['instrument'].iloc[0], 't_index': int(i),
        'date': df['date'].iloc[i], 'spike_high': float(df['high'].iloc[i]),
        'spike_vol': float(df['volume'].iloc[i]),
        'spike_turnover': float(df['turnover'].iloc[i]),
    } for i in idx]
    ctrl_idx = np.flatnonzero(
        (fl['trend_day'].values & ~fl['spike_day'].values))
    controls = [{'instrument': df['instrument'].iloc[0], 't_index': int(i),
                 'date': df['date'].iloc[i]} for i in ctrl_idx]
    return events, controls


# ============================================================
# 分组判定: 洗盘A / 出货B / 未分类C
# ============================================================
def _stabilizes(df, i, spike_high, gp):
    """i日为缩量触均线日: 之后3日内收盘价回到MA10上方, 且未深破冒尖高点。"""
    floor = gp.get('floor_drawdown', CONFIG['floor_drawdown'])
    end = min(len(df), i + 4)
    for j in range(i + 1, end):
        row = df.iloc[j]
        if row['close'] >= row['ma10']:
            return bool(row['close'] >= spike_high * (1 - floor))
    return False


def classify_event(df, ev, gp):
    """按窗口内首次命中信号判定 (时间优先, 一组一只)。

    gp 字段: D(窗口), shrink(缩量≤冒尖量×shrink), up_vol(放量≥冒尖量×up_vol),
             up_drop(放量日跌幅≥up_drop), floor_drawdown(回踩不破位幅度)
    wash_ma_pct / stagnant_pct 取全局 CONFIG。
    返回: 'A' 洗盘 / 'B' 出货 / 'C' 未分类
    """
    t0 = ev['t_index']
    D = gp['D']
    spike_high, spike_vol = ev['spike_high'], ev['spike_vol']
    wash_ma = CONFIG['wash_ma_pct']
    end = min(len(df), t0 + D + 1)
    if end <= t0 + 1:
        return 'C'
    for i in range(t0 + 1, end):
        row = df.iloc[i]
        # 洗盘信号: 缩量 + 盘中触及MA10/MA20附近
        shrink = row['volume'] <= spike_vol * gp['shrink']
        lo, hi = min(row['ma10'], row['ma20']), max(row['ma10'], row['ma20'])
        touch = (row['low'] >= lo * (1 - wash_ma)) and (row['low'] <= hi * (1 + wash_ma))
        if shrink and touch and _stabilizes(df, i, spike_high, gp):
            return 'A'
        # 出货信号: 放量下跌
        if row['volume'] >= spike_vol * gp['up_vol'] and row['ret'] <= -gp['up_drop']:
            return 'B'
    # 窗口结束仍未触发: 滞涨判B
    hi = float(df['high'].iloc[t0 + 1:end].max())
    if hi <= spike_high * (1 + CONFIG['stagnant_pct']):
        return 'B'
    return 'C'


# ============================================================
# 前向收益 (防前视: 从判定完成日 t0+D 收盘起算)
# ============================================================
def forward_returns(df, t0, D, horizons):
    """返回 {h: ret} 字典; 停牌(缺bar)>50% 或 起点缺bar → None。"""
    out = {}
    start = t0 + D
    if start >= len(df) or pd.isna(df['close'].iloc[start]):
        return {h: None for h in horizons}
    c0 = float(df['close'].iloc[start])
    for h in horizons:
        end = start + h
        if end >= len(df):
            out[h] = None
            continue
        window = df['close'].iloc[start:end + 1]
        missing = int(window.isna().sum())
        if missing > h / 2:
            out[h] = None
        else:
            out[h] = float(window.ffill().iloc[-1]) / c0 - 1.0
    return out


# ============================================================
# 事件去重 (同股 gap_days 内仅保留首个)
# ============================================================
def dedupe_events(events, gap_days=30):
    seen = {}
    out = []
    for ev in sorted(events, key=lambda e: (e['instrument'], e['date'])):
        last = seen.get(ev['instrument'])
        if last is None or (ev['date'] - last).days >= gap_days:
            seen[ev['instrument']] = ev['date']
            out.append(ev)
    return out


# ============================================================
# 事件面板
# ============================================================
def build_event_panel(bar_by_inst, events, gp, horizons, classify=True):
    """每事件一行: instrument/date/group/ret_{h}d。停牌样本为None。

    classify=False 时用于对照样本(无冒尖字段, 不分组, group 为 None)。
    """
    rows = []
    for ev in events:
        df = bar_by_inst[ev['instrument']]
        fr = forward_returns(df, ev['t_index'], gp['D'], horizons)
        row = {'instrument': ev['instrument'], 'date': ev['date'],
               'group': classify_event(df, ev, gp) if classify else None}
        for h in horizons:
            row[f'ret_{h}d'] = fr[h]
        rows.append(row)
    return pd.DataFrame(rows)


# ============================================================
# 统计检验 (numpy-only, 本地无 scipy 也可运行)
# ============================================================
from math import erf, sqrt, lgamma, log


def _norm_cdf(x):
    return 0.5 * (1 + erf(x / sqrt(2.0)))


def _t_tail_p(x, df):
    """Student-t 密度: g*(1+x^2/df)^{-(df+1)/2}, g 用 lgamma 防大 df 溢出"""
    g = np.exp(lgamma((df + 1) / 2) - lgamma(df / 2) - 0.5 * log(df * np.pi))
    return g * (1 + x * x / df) ** (-(df + 1) / 2)


def _t_two_sided_p(t_stat, df):
    """用梯形积分算双尾 p 值 (尾部积分至 40, 衰减可忽略)。兼容 numpy<2 环境。"""
    if not np.isfinite(t_stat):
        return 0.0
    a = abs(float(t_stat))
    xs = np.linspace(a, 40.0, 20001)
    integ = getattr(np, 'trapezoid', None) or np.trapz   # numpy>=2 用 trapezoid, 旧版回退 trapz
    return 2.0 * integ(_t_tail_p(xs, df), xs)


def welch_t(x, y):
    """Welch t 检验, 返回 (t, p)。同均值时 se=0 返回 (0.0, 1.0)。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    nx, ny = len(x), len(y)
    vx, vy = x.var(ddof=1), y.var(ddof=1)
    se = np.sqrt(vx / nx + vy / ny)
    if se == 0:
        return 0.0, 1.0
    t = (x.mean() - y.mean()) / se
    df = (vx / nx + vy / ny) ** 2 / (
        (vx / nx) ** 2 / (nx - 1) + (vy / ny) ** 2 / (ny - 1))
    return float(t), _t_two_sided_p(t, df)


def mann_whitney_u(x, y):
    """Mann-Whitney U (正态近似 + 并列修正), 返回 (U, p)。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    nx, ny = len(x), len(y)
    ranked = pd.Series(np.concatenate([x, y])).rank(method='average')
    u1 = ranked.iloc[:nx].sum() - nx * (nx + 1) / 2.0
    u2 = nx * ny - u1
    mu = nx * ny / 2.0
    counts = ranked.value_counts().values
    tie = (counts ** 3 - counts).sum() / ((nx + ny) * (nx + ny - 1))
    sigma = np.sqrt(nx * ny / 12.0 * ((nx + ny + 1) - tie))
    if sigma == 0:
        return float(min(u1, u2)), 1.0
    u = min(u1, u2)
    z = (u - mu) / sigma
    return float(u), 2.0 * (1.0 - _norm_cdf(abs(z)))


def group_stats_table(panel, horizons, group_col='group'):
    """每组 × 每持有期: n/mean/median/win_rate/pl_ratio。"""
    rows = []
    for h in horizons:
        col = f'ret_{h}d'
        for g in sorted(panel[group_col].dropna().unique()):
            s = panel.loc[panel[group_col] == g, col].dropna()
            if len(s) == 0:
                continue
            wins = s[s > 0]
            losses = s[s < 0]
            pl = (wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else np.nan
            rows.append({'horizon': h, 'group': g, 'n': int(len(s)),
                         'mean': s.mean(), 'median': s.median(),
                         'win_rate': (s > 0).mean(), 'pl_ratio': pl})
    return pd.DataFrame(rows)


def compare_groups(panel, h, g1='A', g2='B'):
    """洗盘A vs 出货B: 差异 + 双检验。significant 需 p<0.05 且两组样本≥20。"""
    a = panel.loc[panel['group'] == g1, f'ret_{h}d'].dropna().values
    b = panel.loc[panel['group'] == g2, f'ret_{h}d'].dropna().values
    t, p_t = welch_t(a, b)
    u, p_u = mann_whitney_u(a, b)
    return {'horizon': h, 'n_A': int(len(a)), 'n_B': int(len(b)),
            'diff_mean': float(a.mean() - b.mean()),
            'diff_median': float(np.median(a) - np.median(b)),
            'welch_t': t, 'welch_p': p_t, 'mw_u': u, 'mw_p': p_u,
            'significant': bool(p_t < 0.05 and p_u < 0.05
                                and len(a) >= 20 and len(b) >= 20)}


def yearly_breakdown(panel, h, min_n=10):
    """逐年 洗盘-出货 收益差与 p 值。"""
    p = panel.copy()
    p['year'] = pd.to_datetime(p['date']).dt.year
    rows = []
    for y, g in p.groupby('year'):
        a = g.loc[g['group'] == 'A', f'ret_{h}d'].dropna()
        b = g.loc[g['group'] == 'B', f'ret_{h}d'].dropna()
        if len(a) >= min_n and len(b) >= min_n:
            t, pv = welch_t(a.values, b.values)
            rows.append({'year': int(y), 'n_A': int(len(a)), 'n_B': int(len(b)),
                         'diff_mean': float(a.mean() - b.mean()), 'welch_p': pv})
    return pd.DataFrame(rows)


def size_breakdown(panel, valuation, h):
    """按事件日所在月末市值分大/中/小, 输出各组洗盘-出货差异。"""
    p = panel.copy()
    p['yearmonth'] = pd.to_datetime(p['date']).dt.to_period('M')
    v = valuation.copy()
    v['yearmonth'] = pd.to_datetime(v['date']).dt.to_period('M')
    m = p.merge(v[['instrument', 'yearmonth', 'total_market_cap']],
                on=['instrument', 'yearmonth'], how='left')
    m = m.dropna(subset=['total_market_cap'])
    if len(m) < 30:
        return pd.DataFrame()
    m['size'] = pd.qcut(m['total_market_cap'], 3, labels=['小', '中', '大'])
    rows = []
    for sz, g in m.groupby('size'):
        a = g.loc[g['group'] == 'A', f'ret_{h}d'].dropna()
        b = g.loc[g['group'] == 'B', f'ret_{h}d'].dropna()
        if len(a) >= 10 and len(b) >= 10:
            t, pv = welch_t(a.values, b.values)
            rows.append({'size': sz, 'n_A': int(len(a)), 'n_B': int(len(b)),
                         'diff_mean': float(a.mean() - b.mean()), 'welch_p': pv})
    return pd.DataFrame(rows)


# ============================================================
# 汇总与主流程
# ============================================================
def _label_spike(cfg):
    if cfg.get('abs'):
        return 'abs' + str(int(cfg['abs'] * 100)).zfill(2)
    return 'rel' + str(cfg['rel'])


def _label_gp(gp):
    return (f"D{gp['D']}_s{int(gp['shrink'] * 100)}"
            f"_v{int(gp['up_vol'] * 100)}_d{int(gp['up_drop'] * 100)}")


def sample_controls(controls_all, n, seed=42):
    """从全部对照日中随机抽样。"""
    if len(controls_all) <= n:
        return controls_all
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(controls_all), n, replace=False)
    return [controls_all[i] for i in idx]


def run_analysis(bar_by_inst, spike_configs, group_params, horizons,
                 out_dir, control_sample_n, cache):
    """事件检测 → 分组 → 前向收益 → 统计, 写出统计矩阵与事件库。"""
    os.makedirs(out_dir, exist_ok=True)
    # 基准组合: 优先 abs15 × 第一组判定参数
    main_spike = next((c for c in spike_configs if c.get('abs') == 0.15),
                      spike_configs[0])
    main_gp = group_params[0]
    summary_rows = []
    main_controls = []
    for sc in spike_configs:
        events, controls = [], []
        for inst, df in bar_by_inst.items():
            e, c = detect_events(df, sc)
            events += e
            controls += c
        events = dedupe_events(events, gap_days=CONFIG['dedupe_gap_days'])
        print(f'[{_label_spike(sc)}] 事件 {len(events)}, 对照日 {len(controls)}')
        if sc == main_spike:
            main_controls = controls
        for gp in group_params:
            panel = build_event_panel(bar_by_inst, events, gp, horizons)
            fname = os.path.join(out_dir, f"events_{_label_spike(sc)}_{_label_gp(gp)}.csv")
            panel.to_csv(fname, index=False)
            is_main = (sc == main_spike and gp == main_gp)
            if is_main:
                panel.to_csv(os.path.join(out_dir, 'events_main.csv'), index=False)
            for h in horizons:
                row = {'spike': _label_spike(sc), 'gp': _label_gp(gp),
                       'is_main': is_main}
                row.update(compare_groups(panel, h))
                summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(os.path.join(out_dir, 'stats_summary.csv'), index=False)

    # 基准组合的附加检验
    panel_main = pd.read_csv(os.path.join(out_dir, 'events_main.csv'),
                             parse_dates=['date'])
    yearly_breakdown(panel_main, 20).to_csv(
        os.path.join(out_dir, 'yearly_20d.csv'), index=False)
    if cache['valuation'] is not None and len(cache['valuation']):
        size_breakdown(panel_main, cache['valuation'], 20).to_csv(
            os.path.join(out_dir, 'size_20d.csv'), index=False)
    else:
        print('  ⚠️ 无市值数据, 跳过大小盘分组')

    # 对照检验: 全部冒尖事件 vs 趋势日无高换手样本
    ctrl = sample_controls(main_controls, control_sample_n)
    ctrl_panel = build_event_panel(bar_by_inst, ctrl, main_gp, horizons,
                                   classify=False)
    ctrl_panel['group'] = 'ctrl'
    ctrl_panel.to_csv(os.path.join(out_dir, 'events_control.csv'), index=False)
    ctrl_rows = []
    for h in horizons:
        ev = panel_main.copy()
        ev['group'] = 'spike'
        both = pd.concat([ev[['group', f'ret_{h}d']],
                          ctrl_panel[['group', f'ret_{h}d']]])
        t, pv = welch_t(both.loc[both.group == 'spike', f'ret_{h}d'].values,
                        both.loc[both.group == 'ctrl', f'ret_{h}d'].values)
        ctrl_rows.append({'horizon': h,
                          'n_spike': int((both.group == 'spike').sum()),
                          'n_ctrl': int((both.group == 'ctrl').sum()),
                          'diff_mean': float(
                              both.loc[both.group == 'spike', f'ret_{h}d'].mean()
                              - both.loc[both.group == 'ctrl', f'ret_{h}d'].mean()),
                          'welch_p': pv})
    pd.DataFrame(ctrl_rows).to_csv(os.path.join(out_dir, 'control_20d.csv'),
                                   index=False)
    return summary, panel_main


def main(config=None):
    """主入口: 缓存 → 指标 → 检测 → 分组 → 收益 → 统计 → 报告。"""
    cfg = {**CONFIG, **(config or {})}
    t0 = time.time()
    cache = load_cache(cfg['cache_dir'])
    if cache['bar'] is None:
        if dai is None:
            raise RuntimeError('本地无 dai 且无缓存, 无法拉取数据')
        build_cache(cfg)
        cache = load_cache(cfg['cache_dir'])
    bar = cache['bar']
    print(f'行情 {len(bar)} 行, {bar["instrument"].nunique()} 只')

    # 次新过滤
    basic = cache['basic']
    if basic is not None and len(basic) and 'list_date' in basic.columns:
        basic['list_date'] = pd.to_datetime(basic['list_date'])
        min_list = pd.Timestamp(cfg['start_date']) - pd.Timedelta(days=cfg['min_list_days'])
        ok_codes = set(basic.loc[basic['list_date'] <= min_list, 'instrument'])
        bar = bar[bar['instrument'].isin(ok_codes)]
        print(f'剔除次新后 {bar["instrument"].nunique()} 只')

    bar_by_inst = {inst: add_indicators(g.reset_index(drop=True))
                   for inst, g in bar.groupby('instrument')}
    print(f'事件检测与分组判定 (耗时约 {time.time() - t0:.0f}s)...')
    summary, panel_main = run_analysis(
        bar_by_inst, cfg['spike_configs'], cfg['group_params'], cfg['horizons'],
        cfg['out_dir'], cfg['control_sample_n'], cache)
    generate_report(cfg['out_dir'], summary, panel_main)
    print('=' * 60)
    print(f'完成: {cfg["out_dir"]}/stats_summary.csv 与 report.md')
    print(f'总耗时 {time.time() - t0:.0f}s')


# ============================================================
# 报告生成 (markdown + matplotlib 图表)
# 图表配色采用 dataviz 技能已验证的参考调色板 (light mode):
#   洗盘A=slot1蓝 #2a78d6, 出货B=slot2橙 #eb6834 (相邻对通过 CVD 检验)
#   差异极性: 蓝↔红 双极 + 中性灰中点 (非彩虹渐变)
# ============================================================
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

C_SERIES_1 = '#2a78d6'   # 洗盘A
C_SERIES_2 = '#eb6834'   # 出货B
C_POS = '#e34948'        # 正差异 (红极)
C_NEG = '#104281'        # 负差异 (蓝极)
C_MID = '#f0efec'        # 中性中点
C_INK = '#0b0b0b'
C_INK2 = '#52514e'
C_MUTED = '#898781'
C_GRID = '#e1e0d9'
C_AXIS = '#c3c2b7'
C_SURFACE = '#fcfcfb'

plt.rcParams.update({
    'font.sans-serif': ['PingFang SC', 'Heiti SC', 'WenQuanYi Zen Hei',
                        'Arial Unicode MS', 'DejaVu Sans'],
    'axes.unicode_minus': False,
    'figure.facecolor': C_SURFACE,
    'axes.facecolor': C_SURFACE,
    'axes.edgecolor': C_AXIS,
    'axes.labelcolor': C_INK2,
    'text.color': C_INK,
    'xtick.color': C_MUTED,
    'ytick.color': C_MUTED,
    'grid.color': C_GRID,
    'grid.linewidth': 0.8,
})


def _fmt_p(p):
    return '<0.001' if p < 0.001 else f'{p:.3f}'


def _read_csv_optional(path):
    """缺失/空文件返回 None (小样本下部分检验表可能为空)。"""
    try:
        df = pd.read_csv(path)
    except (pd.errors.EmptyDataError, FileNotFoundError, OSError):
        return None
    return df if len(df) else None


def make_charts(out_dir, summary, panel_main):
    os.makedirs(out_dir, exist_ok=True)
    h = 20
    # 图1: 基准组合 20日收益 A vs B 箱线图 (均值用菱形标出, 零线为基准)
    fig, ax = plt.subplots(figsize=(6, 4))
    a = panel_main.loc[panel_main['group'] == 'A', f'ret_{h}d'].dropna()
    b = panel_main.loc[panel_main['group'] == 'B', f'ret_{h}d'].dropna()
    bp = ax.boxplot([a, b], showmeans=True,
                    meanprops={'marker': 'D', 'markersize': 5,
                               'markerfacecolor': C_INK, 'markeredgecolor': C_INK},
                    medianprops={'color': C_INK, 'lw': 1.2},
                    whiskerprops={'lw': 1.0}, capprops={'lw': 1.0},
                    widths=0.5, patch_artist=True)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(['洗盘A', '出货B'])   # 兼容旧版 matplotlib (tick_labels 需 3.9+)
    bp['boxes'][0].set_facecolor(C_SERIES_1)
    bp['boxes'][1].set_facecolor(C_SERIES_2)
    for box in bp['boxes']:
        box.set_edgecolor(C_INK)
        box.set_linewidth(1.0)
    ax.axhline(0, color=C_MUTED, lw=0.8, ls='--')
    ax.set_title(f'{h}日收益分布 (基准组合)', fontsize=11)
    ax.set_ylabel('前向收益')
    ax.grid(axis='y', alpha=0.5)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, 'chart_group_dist.png'), dpi=120)
    plt.close(fig)

    # 图2: 参数稳健性热力图 (20日 diff_mean, spike × gp) — 蓝↔红双极+灰中点
    s20 = summary[summary['horizon'] == h]
    pivot = s20.pivot_table(index='spike', columns='gp', values='diff_mean',
                            aggfunc='first')
    cmap = LinearSegmentedColormap.from_list('blue_gray_red', [C_NEG, C_MID, C_POS])
    vmax = abs(pivot.values).max() or 1e-9
    fig, ax = plt.subplots(figsize=(8, 4))
    im = ax.imshow(pivot.values, cmap=cmap, vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=30, fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=8)
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            ax.text(j, i, f'{pivot.values[i, j]:+.1%}', ha='center', va='center',
                    fontsize=8, color=C_INK)
    ax.set_title(f'{h}日 洗盘-出货 收益差 参数稳健性矩阵', fontsize=11)
    fig.colorbar(im, ax=ax, label='diff_mean')
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, 'chart_robustness.png'), dpi=120)
    plt.close(fig)

    # 图3: 分年度柱状图 (正=红 负=蓝)
    yearly = _read_csv_optional(os.path.join(out_dir, 'yearly_20d.csv'))
    if yearly is not None and len(yearly):
        colors = [C_POS if d > 0 else C_NEG for d in yearly['diff_mean']]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(yearly['year'].astype(str), yearly['diff_mean'], color=colors,
               width=0.6)
        ax.axhline(0, color=C_MUTED, lw=0.8, ls='--')
        ax.set_title(f'{h}日 洗盘-出货 收益差 分年度', fontsize=11)
        ax.set_ylabel('diff_mean')
        ax.grid(axis='y', alpha=0.5)
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, 'chart_yearly.png'), dpi=120)
        plt.close(fig)


def generate_report(out_dir, summary, panel_main):
    """主报告: 结论摘要 + 参数矩阵 + 分年度 + 分市值 + 对照 + 局限。"""
    make_charts(out_dir, summary, panel_main)
    s20 = summary[summary['horizon'] == 20]
    main_rows = s20[s20['is_main']]
    main = main_rows.iloc[0] if len(main_rows) else s20.iloc[0]
    with open(os.path.join(out_dir, 'report.md'), 'w', encoding='utf-8') as f:
        w = f.write
        w('# 龙回头/多头回踩规律 事件研究报告\n\n')
        w(f'生成时间: {datetime.now():%Y-%m-%d %H:%M}\n\n')
        w('## 1. 结论摘要\n\n')
        w(f'- 基准组合(换手≥15% × D10): 洗盘A n={int(main["n_A"])}, '
          f'出货B n={int(main["n_B"])}\n')
        w(f'- 20日收益差 均值 {main["diff_mean"]:+.2%}, 中位数差 {main["diff_median"]:+.2%}, '
          f'Welch p={_fmt_p(main["welch_p"])}, Mann-Whitney p={_fmt_p(main["mw_p"])}\n')
        w(f'- 四重验证判定: {"✅ 发现规律" if main["significant"] else "❌ 未通过"} '
          f'(统计显著+经济幅度+多参数一致+样本量, 详见下表)\n\n')
        w('## 2. 参数稳健性矩阵 (20日 洗盘-出货 收益差)\n\n')
        mat = s20.pivot_table(index='spike', columns='gp', values='diff_mean',
                              aggfunc='first')
        mat = mat.applymap(lambda x: f'{x:+.2%}')   # applymap 兼容旧版 pandas
        w(mat.to_markdown() + '\n\n')
        w('![参数稳健性](chart_robustness.png)\n\n')
        w('![分组收益分布](chart_group_dist.png)\n\n')
        w('## 3. 分年度检验\n\n')
        yearly = _read_csv_optional(os.path.join(out_dir, 'yearly_20d.csv'))
        if yearly is not None and len(yearly):
            w(yearly.round(4).to_markdown() + '\n\n')
            w('![分年度](chart_yearly.png)\n\n')
        else:
            w('(样本不足, 无分年度结果)\n\n')
        w('## 4. 分市值检验\n\n')
        size = _read_csv_optional(os.path.join(out_dir, 'size_20d.csv'))
        if size is not None and len(size):
            w(size.round(4).to_markdown() + '\n\n')
        else:
            w('(市值数据不可用或样本不足, 跳过)\n\n')
        w('## 5. 对照检验 (高换手冒尖本身是否有信息量)\n\n')
        ctrl = _read_csv_optional(os.path.join(out_dir, 'control_20d.csv'))
        if ctrl is not None and len(ctrl):
            w(ctrl.round(4).to_markdown() + '\n\n')
        else:
            w('(对照样本不足, 跳过)\n\n')
        w('## 6. 局限\n\n')
        w('- 事件研究只能证明统计关联, 不能证明"主力洗盘/出货"的因果解释\n')
        w('- 退市股数据若缺失, 存在幸存者偏差\n')
        w('- 换手率口径(自由流通/总股本)与涨停规则近似处理, 详见脚本头注释\n')


if __name__ == '__main__':
    main()
