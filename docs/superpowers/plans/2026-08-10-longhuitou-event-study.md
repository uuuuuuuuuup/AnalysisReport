# 龙回头/多头回踩规律事件研究 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建全A股2016-2026"高换手冒尖"事件研究脚本:检测强势股高换手冒尖事件 → 按"缩量回踩企稳(洗盘A)/放量下跌滞涨(出货B)"分组 → 前向收益四重验证,输出统计报告,回答"龙回头是否存在可预测规律"。

**Architecture:** 单文件研究脚本 `longhuitou_event_research.py`(BigQuant 研究环境运行,与仓库 `event_driven_research.py`/`div_lowvol_research_bq.py` 同款模式):dai 分批拉取全A日线→pickle 缓存→纯 pandas 事件检测/分组/前向收益/统计→CSV+报告。`dai` 用 try/except 守卫,本地无 dai 时走缓存模式,纯函数可直接 import 测试(仓库 `test_multi_factor_research.py` 的 ast 提取方式不需要,因为模块级无 dai 调用)。统计检验用 numpy-only 实现(本地无 scipy)。测试用 `synthetic_market.py` 注入已知模式(洗盘/出货/对照)做确定性验证。

**Tech Stack:** Python 3, pandas, numpy, matplotlib(图表), dai(BigQuant 数据接口), pytest。

**提交规则:** 本仓库规则——仅在用户明确指示时 git commit。计划中所有 commit 步骤默认跳过(保留为待办,不执行)。

---

### Task 1: 合成行情数据生成器

**Files:**
- Create: `量化策略/事件驱动/synthetic_market.py`
- Test: `量化策略/事件驱动/test_synthetic_market.py`

- [ ] **Step 1: 写失败测试**

```python
# test_synthetic_market.py
# -*- coding: utf-8 -*-
"""合成行情生成器测试: 验证注入模式的确定性"""
import pandas as pd
from synthetic_market import generate_market, INSTRUMENTS

def test_market_shape():
    df = generate_market(seed=42)
    assert set(df['instrument'].unique()) == set(INSTRUMENTS)
    assert df['date'].nunique() == 400
    assert {'open', 'high', 'low', 'close', 'volume', 'turnover'}.issubset(df.columns)

def test_spike_day_injected():
    df = generate_market(seed=42)
    for inst in INSTRUMENTS[:10]:  # 前10只含冒尖日
        g = df[df['instrument'] == inst]
        day250 = g.iloc[250]
        assert day250['turnover'] == 0.21
        assert day250['volume'] == 5.0

def test_no_spike_on_control():
    df = generate_market(seed=42)
    g = df[df['instrument'] == INSTRUMENTS[10]]
    assert (g['turnover'] < 0.05).all()
    assert (g['volume'] < 2.0).all()

def test_wash_pullback_and_rebound():
    df = generate_market(seed=42)
    g = df[df['instrument'] == INSTRUMENTS[0]].reset_index(drop=True)
    # 回踩段: 251-256 每日 -0.5%, 缩量
    assert g.loc[251:256, 'close'].pct_change().dropna().lt(-0.003).all()
    assert g.loc[256, 'volume'] <= 0.4
    # 反弹段: 257-259 每日 +2%
    assert g.loc[257:259, 'close'].pct_change().dropna().gt(0.015).all()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_synthetic_market.py -v`
Expected: FAIL,ModuleNotFoundError: No module named 'synthetic_market'

- [ ] **Step 3: 实现生成器**

```python
# synthetic_market.py
# -*- coding: utf-8 -*-
"""合成A股行情生成器: 注入确定性事件模式供本地测试。

模式分布(12只, 400交易日, 冒尖日=第250日, 基准日收益+0.6%):
  - 前6只 'wash'        : 上升趋势 + 高换手冒尖 + 缩量回踩MA20企稳后反弹(→ 洗盘A)
  - 中4只 'distribution' : 上升趋势 + 高换手冒尖 + 放量下跌(→ 出货B)
  - 后2只 'none'         : 纯上升趋势无冒尖(→ 对照样本)
"""
import numpy as np
import pandas as pd

INSTRUMENTS = [f'{600000 + k:06d}.SH' for k in range(12)]
N_DAYS = 400
SPIKE_DAY = 250

MODES = ['wash'] * 6 + ['distribution'] * 4 + ['none'] * 2


def _gen_stock(rng, code, mode):
    n = N_DAYS
    r = rng.normal(0.006, 0.015, n)          # 上升趋势日收益
    vol = rng.uniform(0.8, 1.2, n)           # 相对量(基础1.0附近)
    turn = rng.uniform(0.02, 0.04, n)        # 换手率(基础2%-4%)

    if mode != 'none':
        r[SPIKE_DAY] = 0.06                  # 冒尖日: +6%
        vol[SPIKE_DAY] = 5.0
        turn[SPIKE_DAY] = 0.21               # 高换手: 21%

    if mode == 'wash':
        # 回踩段 251-256: 每日-0.5%, 量递减 0.55→0.37
        for j in range(251, 257):
            r[j] = -0.005
            vol[j] = 0.55 - 0.03 * (j - 250)
            turn[j] = 0.02
        # 反弹段 257-259: 每日+2%
        for j in range(257, 260):
            r[j] = 0.02
            vol[j] = 1.0
    elif mode == 'distribution':
        # 放量下跌 251-252: -5% × 3.5/3.2倍量; 后续阴跌
        r[251] = -0.05; vol[251] = 3.5; turn[251] = 0.10
        r[252] = -0.05; vol[252] = 3.2; turn[252] = 0.09
        r[253:263] = -0.008
        vol[253:263] = 1.0

    close = 10.0 * np.exp(np.cumsum(r))
    open_ = close / (1 + r)
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.02, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.02, n))
    return pd.DataFrame({
        'instrument': code, 'date': pd.bdate_range('2022-01-03', periods=n),
        'open': open_, 'high': high, 'low': low, 'close': close,
        'volume': vol, 'turnover': turn,
    })


def generate_market(seed=42):
    rng = np.random.default_rng(seed)
    return pd.concat([
        _gen_stock(rng, code, mode) for code, mode in zip(INSTRUMENTS, MODES)
    ], ignore_index=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_synthetic_market.py -v`
Expected: PASS,4 passed

- [ ] **Step 5: Commit(跳过 — 仓库规则: 仅用户明确指示时提交)**

---

### Task 2: 研究脚本骨架 + 数据层(缓存读写 + dai 拉取)

**Files:**
- Create: `量化策略/事件驱动/longhuitou_event_research.py`(本任务只写头部 docstring、imports、CONFIG、缓存/拉取函数)
- Test: `量化策略/事件驱动/test_longhuitou_event_research.py`

- [ ] **Step 1: 写失败测试(缓存读写 + 结构字段)**

```python
# test_longhuitou_event_research.py
# -*- coding: utf-8 -*-
"""龙回头事件研究脚本测试: 数据层 + 纯函数(直接 import, 模块级无 dai 调用)"""
import numpy as np
import pandas as pd
import tempfile, os
from pathlib import Path
from longhuitou_event_research import (
    save_cache, load_cache, _normalize_turnover, add_indicators,
    compute_flags, detect_events, classify_event, forward_returns,
    dedupe_events, build_event_panel, welch_t, mann_whitney_u,
    group_stats_table, compare_groups, yearly_breakdown, size_breakdown,
)
from synthetic_market import generate_market, INSTRUMENTS

def _tmpdir():
    d = tempfile.mkdtemp()
    return d

def test_cache_roundtrip():
    d = _tmpdir()
    bar = pd.DataFrame({'instrument': ['a'], 'date': pd.to_datetime(['2022-01-03']), 'close': [1.0]})
    save_cache(d, {'bar': bar, 'basic': None, 'valuation': None})
    loaded = load_cache(d)
    assert loaded['bar'].equals(bar)
    assert loaded['basic'] is None

def test_normalize_turnover():
    assert _normalize_turnover(pd.Series([0.15, 0.21])) == 0.15
    assert _normalize_turnover(pd.Series([15.0, 21.0])) == 0.15  # 百分比口径
    assert _normalize_turnover(pd.Series([0.21, 0.16])) == 0.21
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -v`
Expected: FAIL,ModuleNotFoundError: No module named 'longhuitou_event_research'

- [ ] **Step 3: 实现脚本骨架与数据层**

```python
# longhuitou_event_research.py
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
#   - cn_stock_bar1d          日线行情 (date/instrument/open/high/low/close/volume/turnover)
#   - cn_stock_basic_info     基本信息 (list_date/name, 用于剔除次新与ST)
#   - cn_stock_valuation_v6   市值 (月末快照, 用于大/中/小分组)
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -v`
Expected: PASS,2 passed

- [ ] **Step 5: 追加 dai 拉取函数(追加到同一文件末尾)**

```python
# ============================================================
# 数据层: dai 拉取 (BigQuant 环境)
# ============================================================
def _query_columns(sql, filters=None):
    """运行 dai 查询并打印列名, 返回 DataFrame。"""
    df = dai.query(sql, filters=filters or {}).df()
    print('  列:', list(df.columns))
    return df


def fetch_bars_dai(codes, start, end, batch=200):
    """分批拉取日线。返回 concat 后的 DataFrame。"""
    frames = []
    for i in range(0, len(codes), batch):
        chunk = codes[i:i + batch]
        sql = (
            "SELECT date, instrument, open, high, low, close, volume, amount, turnover "
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
    elif 'turnover_ratio' in bar.columns:
        bar['turnover'] = _normalize_turnover(bar['turnover_ratio'])
    else:
        raise RuntimeError('cn_stock_bar1d 无 turnover/turnover_ratio 字段, 无法研究高换手现象')
    bar['date'] = pd.to_datetime(bar['date'])
    valuation = fetch_valuation_snapshots_dai(cfg['start_date'], cfg['end_date'])
    if valuation is not None and len(valuation):
        valuation['date'] = pd.to_datetime(valuation['date'])
        # 保留每月最后一个交易日快照
        valuation = valuation.sort_values('date').groupby(
            [valuation['instrument'], valuation['date'].dt.to_period('M')]).tail(1)
    save_cache(cfg['cache_dir'], {'bar': bar, 'basic': basic, 'valuation': valuation})
    print(f'缓存完成: {cfg["cache_dir"]}/  (bar {len(bar)} 行)')
```

- [ ] **Step 6: 冒烟验证导入与 dai 守卫**

Run: `cd /Users/apple/Documents/分析报告 && python3 -c "import sys; sys.path.insert(0, '量化策略/事件驱动'); import longhuitou_event_research as m; print('dai =', m.dai); print('CONFIG keys =', len(m.CONFIG))"`
Expected: `dai = None`(本地),CONFIG keys 正常,无 ImportError

- [ ] **Step 7: Commit(跳过)**

---

### Task 3: 指标计算与事件检测

**Files:**
- Modify: `量化策略/事件驱动/longhuitou_event_research.py`(追加)
- Test: `量化策略/事件驱动/test_longhuitou_event_research.py`(追加)

- [ ] **Step 1: 写失败测试**

```python
# 追加到测试文件
def _market_with_indicators():
    bar = generate_market(seed=42)
    return {inst: add_indicators(g.reset_index(drop=True))
            for inst, g in bar.groupby('instrument')}

def test_add_indicators_columns():
    d = _market_with_indicators()
    df = d[INSTRUMENTS[0]]
    for col in ['prev_close', 'ret', 'ma10', 'ma20', 'ma20_shift5',
                'turnover_ma20', 'ret60', 'yiziban']:
        assert col in df.columns

def test_detect_events_finds_injected_spikes():
    d = _market_with_indicators()
    events, controls = [], []
    for inst, df in d.items():
        e, c = detect_events(df, {'abs': 0.15})
        events += e
        controls += c
    insts = {e['instrument'] for e in events}
    assert len(events) == 10                    # 6洗盘 + 4出货
    assert all(e['t_index'] == 250 for e in events)
    assert INSTRUMENTS[10] not in insts         # 对照股无事件
    assert INSTRUMENTS[11] not in insts
    assert len(controls) >= 100                 # 趋势日对照充足

def test_detect_events_abs_thresholds():
    d = _market_with_indicators()
    for cfg in [{'abs': 0.10}, {'abs': 0.18}, {'abs': 0.20}, {'rel': 3.0}]:
        events = [e for inst, df in d.items()
                  for e, _ in detect_events(df, cfg)]
        assert len(events) == 10, f'{cfg} 事件数 {len(events)} != 10'
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k detect -v`
Expected: FAIL,ImportError: cannot import name 'add_indicators'

- [ ] **Step 3: 实现指标与事件检测(追加到脚本末尾)**

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k detect -v`
Expected: PASS,4 passed(含 add_indicators 列检查)

---

### Task 4: 分组判定(洗盘/出货/未分类)

**Files:**
- Modify: `量化策略/事件驱动/longhuitou_event_research.py`(追加)
- Test: `量化策略/事件驱动/test_longhuitou_event_research.py`(追加)

- [ ] **Step 1: 写失败测试**

```python
# 追加到测试文件
def _classify_all(d, events, gp):
    return {e['instrument']: classify_event(d[e['instrument']], e, gp)
            for e in events}

def test_classify_wash_stocks():
    d = _market_with_indicators()
    events = [e for inst, df in d.items() for e, _ in detect_events(df, {'abs': 0.15})]
    for gp in [{'D': 10, 'shrink': 0.3, 'up_vol': 0.6, 'up_drop': 0.05},
               {'D': 15, 'shrink': 0.5, 'up_vol': 0.8, 'up_drop': 0.03}]:
        res = _classify_all(d, events, gp)
        assert all(res[i] == 'A' for i in INSTRUMENTS[:6]), res   # 洗盘股→A
        assert all(res[i] == 'B' for i in INSTRUMENTS[6:10]), res # 出货股→B

def test_classify_no_wash_on_distribution():
    """出货股窗口内不得被判A: 缩量触均线后3日内须收盘回MA10上方。"""
    d = _market_with_indicators()
    events = [e for inst, df in d.items() for e, _ in detect_events(df, {'abs': 0.15})]
    gp = {'D': 10, 'shrink': 0.5, 'up_vol': 0.6, 'up_drop': 0.05}
    res = _classify_all(d, events, gp)
    assert res[INSTRUMENTS[6]] == 'B'
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k classify -v`
Expected: FAIL,ImportError: cannot import name 'classify_event'

- [ ] **Step 3: 实现分组判定(追加到脚本末尾)**

```python
# ============================================================
# 分组判定: 洗盘A / 出货B / 未分类C
# ============================================================
def _stabilizes(df, i, spike_high, gp):
    """i日为缩量触均线日: 之后3日内收盘价回到MA10上方, 且未深破冒尖高点。"""
    end = min(len(df), i + 4)
    for j in range(i + 1, end):
        row = df.iloc[j]
        if row['close'] >= row['ma10']:
            return bool(row['close'] >= spike_high * (1 - gp['floor_drawdown']))
    return False


def classify_event(df, ev, gp):
    """按窗口内首次命中信号判定 (时间优先, 一组一只)。

    gp 字段: D(窗口), shrink(缩量≤冒尖量×shrink), up_vol(放量≥冒尖量×up_vol),
             up_drop(放量日跌幅≥up_drop), wash_ma_pct/floor_drawdown/stagnant_pct 取全局CONFIG
    返回: 'A' 洗盘 / 'B' 出货 / 'C' 未分类
    """
    t0 = ev['t_index']
    D = gp['D']
    spike_high, spike_vol = ev['spike_high'], ev['spike_vol']
    wash_ma = CONFIG['wash_ma_pct']
    floor = CONFIG['floor_drawdown']
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k classify -v`
Expected: PASS,2 passed

---

### Task 5: 前向收益、去重与事件面板

**Files:**
- Modify: `量化策略/事件驱动/longhuitou_event_research.py`(追加)
- Test: `量化策略/事件驱动/test_longhuitou_event_research.py`(追加)

- [ ] **Step 1: 写失败测试**

```python
# 追加到测试文件
def _tiny_df():
    # 10日手工数据: 冒尖日 t0=5, D=2 → 判定完成日=7, ret_3d = close[10]/close[7]-1
    closes = [10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14.0, 14.5, 15.0]
    return pd.DataFrame({
        'date': pd.bdate_range('2022-01-03', periods=len(closes)),
        'close': closes, 'volume': [1.0] * len(closes),
        'turnover': [0.03] * len(closes),
    })

def test_forward_returns_exact():
    df = add_indicators(_tiny_df())
    ev = {'t_index': 5, 'spike_high': 13.0, 'spike_vol': 3.0}
    fr = forward_returns(df, ev['t_index'], 2, [3, 5])
    assert abs(fr[3] - (15.0 / 13.5 - 1)) < 1e-9
    assert fr[5] is None  # 超窗 -> None

def test_forward_returns_stop_halved():
    df = _tiny_df()
    df.loc[8, 'close'] = np.nan  # 持有期缺一根bar
    df = add_indicators(df)
    fr = forward_returns(df, 5, 2, [3])
    assert fr[3] == 15.0 / 14.5 - 1  # ffill 处理

def test_dedupe_events():
    evs = [
        {'instrument': 'a.SH', 't_index': 1, 'date': pd.Timestamp('2022-01-05')},
        {'instrument': 'a.SH', 't_index': 5, 'date': pd.Timestamp('2022-01-10')},  # 5日,去重
        {'instrument': 'a.SH', 't_index': 9, 'date': pd.Timestamp('2022-03-01')},  # 50日,保留
    ]
    out = dedupe_events(evs, gap_days=30)
    assert [e['t_index'] for e in out] == [1, 9]

def test_build_event_panel():
    bar = generate_market(seed=42)
    d = {inst: add_indicators(g.reset_index(drop=True))
         for inst, g in bar.groupby('instrument')}
    events = [e for inst, df in d.items() for e, _ in detect_events(df, {'abs': 0.15})]
    gp = {'D': 10, 'shrink': 0.3, 'up_vol': 0.6, 'up_drop': 0.05}
    panel = build_event_panel(d, events, gp, [5, 20])
    assert len(panel) == 10
    assert {'instrument', 'date', 'group', 'ret_5d', 'ret_20d'}.issubset(panel.columns)
    assert set(panel['group']) == {'A', 'B'}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k "forward or dedupe or panel" -v`
Expected: FAIL,ImportError: cannot import name 'forward_returns'

- [ ] **Step 3: 实现(追加到脚本末尾)**

```python
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
def build_event_panel(bar_by_inst, events, gp, horizons):
    """每事件一行: instrument/date/group/ret_{h}d。停牌样本为NaN。"""
    rows = []
    for ev in events:
        df = bar_by_inst[ev['instrument']]
        fr = forward_returns(df, ev['t_index'], gp['D'], horizons)
        row = {'instrument': ev['instrument'], 'date': ev['date'],
               'group': classify_event(df, ev, gp)}
        for h in horizons:
            row[f'ret_{h}d'] = fr[h]
        rows.append(row)
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k "forward or dedupe or panel" -v`
Expected: PASS,4 passed

---

### Task 6: 统计检验模块(numpy-only)

**Files:**
- Modify: `量化策略/事件驱动/longhuitou_event_research.py`(追加)
- Test: `量化策略/事件驱动/test_longhuitou_event_research.py`(追加)

- [ ] **Step 1: 写失败测试**

```python
# 追加到测试文件
from longhuitou_event_research import _t_tail_p, _norm_cdf

def test_welch_known_value():
    x = np.array([1., 2, 3, 4, 5]); y = np.array([6., 7, 8, 9, 10])
    t, p = welch_t(x, y)
    assert abs(t - (-5.0)) < 1e-6              # t = -5, df = 8
    assert 0.0008 < p < 0.0014                 # 双尾 p ≈ 0.00105

def test_welch_identical():
    x = np.random.default_rng(0).normal(size=200)
    t, p = welch_t(x, x.copy())
    assert p > 0.5

def test_welch_separated():
    x = np.random.default_rng(0).normal(size=200)
    t, p = welch_t(x, x + 1.0)
    assert p < 1e-10

def test_mannwhitney_separated_and_ties():
    x = np.arange(1, 21.0); y = x + 10
    u, p = mann_whitney_u(x, y)
    assert p < 1e-6
    # 相同分布(含并列)不显著
    u, p = mann_whitney_u(np.array([1, 1, 2, 2, 3]), np.array([1, 2, 2, 3, 3]))
    assert p > 0.05

def test_group_stats_table():
    panel = pd.DataFrame({
        'group': ['A', 'A', 'A', 'A', 'B', 'B', 'B', 'B'],
        'ret_20d': [0.10, 0.05, 0.0, -0.02, -0.10, -0.05, 0.01, -0.03],
    })
    out = group_stats_table(panel, [20])
    a = out[out['group'] == 'A'].iloc[0]
    assert abs(a['mean'] - 0.0325) < 1e-9
    assert a['win_rate'] == 0.75
    assert a['pl_ratio'] > 1

def test_compare_groups():
    panel = pd.DataFrame({
        'group': ['A'] * 50 + ['B'] * 50,
        'ret_20d': np.r_[np.random.default_rng(1).normal(0.05, 0.02, 50),
                         np.random.default_rng(2).normal(0.0, 0.02, 50)],
    })
    r = compare_groups(panel, 20)
    assert r['diff_mean'] > 0 and r['significant']

def test_yearly_and_size_breakdown():
    panel = pd.DataFrame({
        'group': ['A'] * 40 + ['B'] * 40,
        'date': pd.to_datetime(['2020-06-01'] * 40 + ['2021-06-01'] * 40),
        'ret_20d': np.r_[np.random.default_rng(3).normal(0.05, 0.02, 40),
                         np.random.default_rng(4).normal(0.0, 0.02, 40)],
    })
    y = yearly_breakdown(panel, 20, min_n=5)
    assert {'year'} <= set(y.columns) and len(y) == 2
    val = pd.DataFrame({
        'instrument': ['a.SH'] * 2 + ['b.SH'] * 2,
        'date': pd.to_datetime(['2020-06-30', '2021-06-30'] * 2),
        'total_market_cap': [1e10, 1e10, 1e9, 1e9],
    })
    panel['instrument'] = ['a.SH'] * 40 + ['b.SH'] * 40
    s = size_breakdown(panel, val, 20)
    assert 'size' in s.columns and len(s) >= 2
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k "welch or mannwhitney or group_stats or compare or yearly" -v`
Expected: FAIL,ImportError: cannot import name 'welch_t'

- [ ] **Step 3: 实现统计模块(追加到脚本末尾)**

```python
# ============================================================
# 统计检验 (numpy-only, 本地无 scipy 也可运行)
# ============================================================
from math import erf, sqrt, gamma


def _norm_cdf(x):
    return 0.5 * (1 + erf(x / sqrt(2.0)))


def _t_tail_p(x, df):
    """Student-t 密度: g*(1+x^2/df)^{-(df+1)/2}"""
    g = gamma((df + 1) / 2) / (sqrt(df * np.pi) * gamma(df / 2))
    return g * (1 + x * x / df) ** (-(df + 1) / 2)


def _t_two_sided_p(t_stat, df):
    """用 Simpson 积分算双尾 p 值 (尾部积分至 40, 衰减可忽略)。"""
    if not np.isfinite(t_stat):
        return 0.0
    a = abs(float(t_stat))
    xs = np.linspace(a, 40.0, 20001)
    return 2.0 * np.trapz(_t_tail_p(xs, df), xs)


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
    z = (min(u1, u2) - mu) / sigma
    return float(min(u1, u2)), 2.0 * (1.0 - _norm_cdf(abs(z)))


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
    """洗盘A vs 出货B: 差异 + 双检验。"""
    a = panel.loc[panel['group'] == g1, f'ret_{h}d'].dropna().values
    b = panel.loc[panel['group'] == g2, f'ret_{h}d'].dropna().values
    t, p_t = welch_t(a, b)
    u, p_u = mann_whitney_u(a, b)
    return {'horizon': h, 'n_A': int(len(a)), 'n_B': int(len(b)),
            'diff_mean': float(a.mean() - b.mean()),
            'diff_median': float(np.median(a) - np.median(b)),
            'welch_t': t, 'welch_p': p_t, 'mw_u': u, 'mw_p': p_u,
            'significant': bool(p_t < 0.05 and p_u < 0.05 and len(a) >= 20 and len(b) >= 20)}


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
    """按事件日所在月末市值分大/中/小, 逐年… 按组汇总差异。"""
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k "welch or mannwhitney or group_stats or compare or yearly" -v`
Expected: PASS,7 passed

---

### Task 7: 主流程编排 + 端到端冒烟测试

**Files:**
- Modify: `量化策略/事件驱动/longhuitou_event_research.py`(追加 main 与汇总)
- Test: `量化策略/事件驱动/test_longhuitou_event_research.py`(追加)

- [ ] **Step 1: 写失败测试(端到端冒烟)**

```python
# 追加到测试文件
def test_main_end_to_end(tmp_path_factory):
    import longhuitou_event_research as m
    d = str(tmp_path_factory.mktemp('cache'))
    o = str(tmp_path_factory.mktemp('out'))
    bar = generate_market(seed=42)
    bar['turnover'] = bar['turnover'] / 100.0 if bar['turnover'].max() > 1 else bar['turnover']
    save_cache(d, {'bar': bar, 'basic': None, 'valuation': None})
    cfg = {
        'cache_dir': d, 'out_dir': o,
        'spike_configs': [{'abs': 0.15}],
        'group_params': [{'D': 10, 'shrink': 0.3, 'up_vol': 0.6, 'up_drop': 0.05}],
        'horizons': [5, 20], 'control_sample_n': 100,
    }
    m.main(cfg)
    assert os.path.exists(os.path.join(o, 'stats_summary.csv'))
    assert os.path.exists(os.path.join(o, 'report.md'))
    summary = pd.read_csv(os.path.join(o, 'stats_summary.csv'))
    assert len(summary) == 2                      # 2 个持有期
    row = summary.iloc[0]
    assert row['n_A'] == 6 and row['n_B'] == 4
    assert row['diff_mean'] > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k end_to_end -v`
Expected: FAIL,AttributeError: module has no attribute 'main'

- [ ] **Step 3: 实现主流程(追加到脚本末尾)**

```python
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
    summary_rows = []
    main_spike, main_gp = spike_configs[1], group_params[0]   # 基准组合: abs15×D10
    for sc in spike_configs:
        events, controls = [], []
        for inst, df in bar_by_inst.items():
            e, c = detect_events(df, sc)
            events += e
            controls += c
        events = dedupe_events(events, gap_days=CONFIG['dedupe_gap_days'])
        print(f'[{_label_spike(sc)}] 事件 {len(events)}, 对照日 {len(controls)}')
        for gp in group_params:
            panel = build_event_panel(bar_by_inst, events, gp, horizons)
            fname = os.path.join(out_dir, f"events_{_label_spike(sc)}_{_label_gp(gp)}.csv")
            panel.to_csv(fname, index=False)
            for h in horizons:
                row = {'spike': _label_spike(sc), 'gp': _label_gp(gp)}
                row.update(compare_groups(panel, h))
                summary_rows.append(row)
            if (sc, gp) == (main_spike, main_gp):
                panel.to_csv(os.path.join(out_dir, 'events_main.csv'), index=False)
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
    ctrl = sample_controls(controls, control_sample_n)
    ctrl_panel = build_event_panel(bar_by_inst, ctrl, main_gp, horizons)
    ctrl_panel['group'] = 'ctrl'
    ctrl_panel.to_csv(os.path.join(out_dir, 'events_control.csv'), index=False)
    ctrl_rows = []
    for h in horizons:
        ev = panel_main.copy()
        ev['group'] = 'spike'
        both = pd.concat([ev[['group', f'ret_{h}d']], ctrl_panel[['group', f'ret_{h}d']]])
        t, pv = welch_t(both.loc[both.group == 'spike', f'ret_{h}d'].values,
                        both.loc[both.group == 'ctrl', f'ret_{h}d'].values)
        ctrl_rows.append({'horizon': h, 'n_spike': int((both.group == 'spike').sum()),
                          'n_ctrl': int((both.group == 'ctrl').sum()),
                          'diff_mean': float(both.loc[both.group == 'spike', f'ret_{h}d'].mean()
                                             - both.loc[both.group == 'ctrl', f'ret_{h}d'].mean()),
                          'welch_p': pv})
    pd.DataFrame(ctrl_rows).to_csv(os.path.join(out_dir, 'control_20d.csv'), index=False)
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


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k end_to_end -v`
Expected: FAIL,ImportError: cannot import name 'generate_report'

- [ ] **Step 5: 临时 stub 以便先验证主流程(追加到脚本末尾, Task 8 会替换为完整实现)**

```python
def generate_report(out_dir, summary, panel_main):
    """占位: Task 8 替换为完整报告。"""
    summary.to_csv(os.path.join(out_dir, 'report.csv'), index=False)
    with open(os.path.join(out_dir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write('# 龙回头事件研究报告(生成中)\n')
```

- [ ] **Step 6: 运行确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/test_longhuitou_event_research.py -k end_to_end -v`
Expected: PASS,1 passed(完整测试套件 `python3 -m pytest 量化策略/事件驱动/ -v` 应全部通过)

- [ ] **Step 7: Commit(跳过)**

---

### Task 8: 报告生成(markdown + 图表)

**Files:**
- Modify: `量化策略/事件驱动/longhuitou_event_research.py`(替换 generate_report 占位)

- [ ] **Step 1: 先调用 dataviz 技能获取图表规范**

按技能规则:写任何图表代码前必须调用 `Skill(dataviz)` 读取图表配色/标记规范,再写 `make_charts` 中的 matplotlib 代码。若技能不可用,使用默认 matplotlib 样式(研究图表, 保持简洁)。

- [ ] **Step 2: 实现完整报告生成(替换 Task 7 Step 5 的占位函数)**

```python
# ============================================================
# 报告生成 (markdown + matplotlib 图表)
# ============================================================
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# 中文字体回退: 各平台常见 CJK 字体
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'WenQuanYi Zen Hei',
                                   'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def _fmt_p(p):
    return '<0.001' if p < 0.001 else f'{p:.3f}'


def make_charts(out_dir, summary, panel_main):
    os.makedirs(out_dir, exist_ok=True)
    h = 20
    # 图1: 基准组合 20日收益 A vs B 箱线图
    fig, ax = plt.subplots(figsize=(6, 4))
    a = panel_main.loc[panel_main['group'] == 'A', f'ret_{h}d'].dropna()
    b = panel_main.loc[panel_main['group'] == 'B', f'ret_{h}d'].dropna()
    ax.boxplot([a, b], labels=['洗盘A', '出货B'], showmeans=True)
    ax.axhline(0, color='gray', lw=0.8)
    ax.set_title(f'{h}日收益分布 (基准组合)')
    ax.set_ylabel('收益')
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, 'chart_group_dist.png'), dpi=120)
    plt.close(fig)

    # 图2: 参数稳健性热力图 (20日 diff_mean, spike × gp)
    s20 = summary[summary['horizon'] == h]
    pivot = s20.pivot_table(index='spike', columns='gp', values='diff_mean', aggfunc='first')
    fig, ax = plt.subplots(figsize=(8, 4))
    im = ax.imshow(pivot.values, cmap='RdYlGn', vmin=-abs(pivot.values).max(),
                   vmax=abs(pivot.values).max())
    ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns, rotation=30)
    ax.set_yticks(range(len(pivot.index))); ax.set_yticklabels(pivot.index)
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            ax.text(j, i, f'{pivot.values[i, j]:.1%}', ha='center', va='center', fontsize=8)
    ax.set_title(f'{h}日 洗盘-出货 收益差 参数稳健性矩阵')
    fig.colorbar(im, ax=ax, label='diff_mean')
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, 'chart_robustness.png'), dpi=120)
    plt.close(fig)

    # 图3: 分年度柱状图
    yearly = pd.read_csv(os.path.join(out_dir, 'yearly_20d.csv'))
    if len(yearly):
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(yearly['year'].astype(str), yearly['diff_mean'],
               color=['#2e8b57' if d > 0 else '#b22222' for d in yearly['diff_mean']])
        ax.axhline(0, color='gray', lw=0.8)
        ax.set_title(f'{h}日 洗盘-出货 收益差 分年度')
        ax.set_ylabel('diff_mean')
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, 'chart_yearly.png'), dpi=120)
        plt.close(fig)


def generate_report(out_dir, summary, panel_main):
    """主报告: 结论摘要 + 参数矩阵 + 分年度 + 分市值 + 对照 + 局限。"""
    make_charts(out_dir, summary, panel_main)
    s20 = summary[summary['horizon'] == 20]
    main = s20.iloc[0]
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
        w(s20.pivot_table(index='spike', columns='gp', values='diff_mean',
                          aggfunc='first').round(4).to_markdown() + '\n\n')
        w('![参数稳健性](chart_robustness.png)\n\n')
        w('![分组收益分布](chart_group_dist.png)\n\n')
        w('## 3. 分年度检验\n\n')
        w(pd.read_csv(os.path.join(out_dir, 'yearly_20d.csv')).round(4).to_markdown() + '\n\n')
        w('![分年度](chart_yearly.png)\n\n')
        w('## 4. 分市值检验\n\n')
        import os as _os
        if _os.path.exists(os.path.join(out_dir, 'size_20d.csv')):
            w(pd.read_csv(os.path.join(out_dir, 'size_20d.csv')).round(4).to_markdown() + '\n\n')
        else:
            w('(市值数据不可用, 跳过)\n\n')
        w('## 5. 对照检验 (高换手冒尖本身是否有信息量)\n\n')
        w(pd.read_csv(os.path.join(out_dir, 'control_20d.csv')).round(4).to_markdown() + '\n\n')
        w('## 6. 局限\n\n')
        w('- 事件研究只能证明统计关联, 不能证明"主力洗盘/出货"的因果解释\n')
        w('- 退市股数据若缺失, 存在幸存者偏差\n')
        w('- 换手率口径(自由流通/总股本)与涨停规则近似处理, 详见脚本头注释\n')
```

- [ ] **Step 3: 全量测试确认通过**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/ -v`
Expected: PASS,全部通过(合成生成器4 + 研究脚本 2+4+2+4+7+1 ≈ 24 项)

- [ ] **Step 4: 手工验证报告输出**

Run: `cd /Users/apple/Documents/分析报告 && python3 -c "
import sys; sys.path.insert(0, '量化策略/事件驱动')
import tempfile, os
from synthetic_market import generate_market
import longhuitou_event_research as m
d = tempfile.mkdtemp(); o = tempfile.mkdtemp()
m.save_cache(d, {'bar': generate_market(seed=42), 'basic': None, 'valuation': None})
m.main({'cache_dir': d, 'out_dir': o, 'spike_configs': [{'abs': 0.10}, {'abs': 0.15}],
        'group_params': [{'D': 10, 'shrink': 0.3, 'up_vol': 0.6, 'up_drop': 0.05}],
        'horizons': [5, 20], 'control_sample_n': 50})
print('--- report.md 前40行 ---'); print(open(os.path.join(o, 'report.md')).read()[:2000])
print('--- 输出文件 ---'); print(sorted(os.listdir(o)))
"`
Expected: main() 正常结束;report.md 含结论摘要与 markdown 表格;输出目录含 events_*.csv、stats_summary.csv、chart_*.png

- [ ] **Step 5: Commit(跳过)**

---

### Task 9: 收尾 — 全量验证与 BigQuant 运行说明核对

**Files:**
- Modify: `量化策略/事件驱动/longhuitou_event_research.py`(头注释核对, 无需改动)

- [ ] **Step 1: 全量测试**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/ -v`
Expected: 全部 PASS

- [ ] **Step 2: 核对脚本头 docstring 覆盖运行说明**

逐条核对(不改代码, 缺则补):
- [ ] BigQuant 研究环境运行方式(新建 Notebook → 粘贴 → 运行)
- [ ] 数据表清单与字段假设(turnover 口径, 缺失时 RuntimeError 提示)
- [ ] 缓存目录与二次运行跳过拉数
- [ ] `CONFIG['sample_stocks']` 快速试跑
- [ ] 输出文件清单(output/ 下 events_*.csv / stats_summary.csv / yearly_20d.csv / size_20d.csv / control_20d.csv / report.md / chart_*.png)

- [ ] **Step 3: 全量测试收尾确认**

Run: `cd /Users/apple/Documents/分析报告 && python3 -m pytest 量化策略/事件驱动/ -v`
Expected: 全部 PASS,无残留 stub/占位

- [ ] **Step 4: 汇报**

总结:文件清单、测试结果、BigQuant 运行步骤、预期耗时(拉数约30-60分钟, 分析阶段10-30分钟)、输出解读路径。不提交 git。

---

## Self-Review 记录(写入计划后由主执行者完成)

1. **Spec 覆盖检查**: 事件触发参数(绝对4档×相对1档)✓Task3;分组判定(洗盘/出货/滞涨/未分类, D×缩量×放量×跌幅 4组)✓Task4;前向收益防前视✓Task5;四重验证(统计/经济/稳健性/对照)✓Task6-7;分年度✓Task6;分市值✓Task6;事件去重✓Task5;产出 CSV+报告+图表✓Task7-8。局限说明✓Task8 section 6。
2. **占位符扫描**: generate_report 在 Task7 Step5 有明确占位并被 Task8 完整替换(计划内临时步骤, 非残留)。其余步骤均为完整代码。
3. **类型/签名一致性**: `detect_events(df, spike_cfg) -> (events, controls)` 在 Task3/7 一致;`classify_event(df, ev, gp)` 在 Task4/5/7 一致;`forward_returns(df, t0, D, horizons) -> dict` 一致;`compare_groups(panel, h)` 返回字段在 Task6/7 一致;`welch_t/mann_whitney_u` 返回 (值, p) 顺序一致。`_normalize_turnover` 在 Task2 定义并被 Task2 测试使用。
