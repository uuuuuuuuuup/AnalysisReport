# -*- coding: utf-8 -*-
"""龙回头事件研究脚本测试: 数据层 + 纯函数 (模块级无 dai 调用, 本地可测)"""
import os
import tempfile

import numpy as np
import pandas as pd

import longhuitou_event_research as m
from synthetic_market import generate_market, INSTRUMENTS


def _tmpdir():
    return tempfile.mkdtemp()


# ============================================================
# T2 数据层
# ============================================================
def test_cache_roundtrip():
    d = _tmpdir()
    bar = pd.DataFrame({'instrument': ['a'], 'date': pd.to_datetime(['2022-01-03']),
                        'close': [1.0]})
    m.save_cache(d, {'bar': bar, 'basic': None, 'valuation': None})
    loaded = m.load_cache(d)
    assert loaded['bar'].equals(bar)
    assert loaded['basic'] is None


def test_normalize_turnover():
    s = m._normalize_turnover(pd.Series([0.15, 0.21]))
    assert s.iloc[0] == 0.15 and s.iloc[1] == 0.21
    s = m._normalize_turnover(pd.Series([15.0, 21.0]))   # 百分比口径
    assert s.iloc[0] == 0.15 and s.iloc[1] == 0.21


def test_dai_guard_local():
    assert m.dai is None   # 本地环境无 dai, 仅缓存模式


# ============================================================
# T3 指标与事件检测
# ============================================================
def _market_with_indicators():
    bar = generate_market(seed=42)
    return {inst: m.add_indicators(g.reset_index(drop=True))
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
        e, c = m.detect_events(df, {'abs': 0.15})
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
        evs = []
        for inst, df in d.items():
            e, _ = m.detect_events(df, cfg)
            evs += e
        assert len(evs) == 10, f'{cfg} 事件数 {len(evs)} != 10'


def test_st_filter_in_compute_flags():
    """事件日为 ST 名称的股票应被剔除 (仅当行情带 name 列时)。"""
    bar = generate_market(seed=42)
    df = m.add_indicators(
        bar[bar['instrument'] == INSTRUMENTS[0]].reset_index(drop=True))
    df['name'] = '普通股票'
    n1 = int(m.compute_flags(df, {'abs': 0.15})['spike_day'].sum())
    assert n1 == 1
    df.loc[250, 'name'] = 'ST某某'      # 冒尖日变 ST → 该事件剔除
    n2 = int(m.compute_flags(df, {'abs': 0.15})['spike_day'].sum())
    assert n2 == n1 - 1


# ============================================================
# T4 分组判定
# ============================================================
def _classify_all(d, events, gp):
    return {e['instrument']: m.classify_event(d[e['instrument']], e, gp)
            for e in events}


def _all_events(d, cfg):
    evs = []
    for inst, df in d.items():
        e, _ = m.detect_events(df, cfg)
        evs += e
    return evs


def test_classify_wash_stocks():
    d = _market_with_indicators()
    events = _all_events(d, {'abs': 0.15})
    for gp in [{'D': 10, 'shrink': 0.3, 'up_vol': 0.6, 'up_drop': 0.05},
               {'D': 15, 'shrink': 0.5, 'up_vol': 0.8, 'up_drop': 0.03}]:
        res = _classify_all(d, events, gp)
        assert all(res[i] == 'A' for i in INSTRUMENTS[:6]), res   # 洗盘股→A
        assert all(res[i] == 'B' for i in INSTRUMENTS[6:10]), res  # 出货股→B


def test_classify_no_wash_on_distribution():
    """出货股窗口内不得被判A: 缩量触均线后3日内须收盘回MA10上方。"""
    d = _market_with_indicators()
    events = _all_events(d, {'abs': 0.15})
    gp = {'D': 10, 'shrink': 0.5, 'up_vol': 0.6, 'up_drop': 0.05}
    res = _classify_all(d, events, gp)
    assert res[INSTRUMENTS[6]] == 'B'


# ============================================================
# T5 前向收益 / 去重 / 面板
# ============================================================
def _tiny_df():
    # 11日手工数据: 冒尖日 t0=5, D=2 → 判定完成日=7, ret_3d = close[10]/close[7]-1
    closes = [10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14.0, 14.5, 15.0]
    return pd.DataFrame({
        'date': pd.bdate_range('2022-01-03', periods=len(closes)),
        'open': closes, 'high': [c * 1.01 for c in closes],
        'low': [c * 0.99 for c in closes],
        'close': closes, 'volume': [1.0] * len(closes),
        'turnover': [0.03] * len(closes),
    })


def test_forward_returns_exact():
    df = m.add_indicators(_tiny_df())
    fr = m.forward_returns(df, 5, 2, [3, 5])
    assert abs(fr[3] - (15.0 / 13.5 - 1)) < 1e-9
    assert fr[5] is None  # 超窗 -> None


def test_forward_returns_stop_halved():
    df = _tiny_df()
    df.loc[8, 'close'] = np.nan  # 持有期缺一根bar
    df = m.add_indicators(df)
    fr = m.forward_returns(df, 5, 2, [3])
    assert abs(fr[3] - (15.0 / 13.5 - 1)) < 1e-9  # ffill 处理后用末值


def test_dedupe_events():
    evs = [
        {'instrument': 'a.SH', 't_index': 1, 'date': pd.Timestamp('2022-01-05')},
        {'instrument': 'a.SH', 't_index': 5, 'date': pd.Timestamp('2022-01-10')},  # 5日,去重
        {'instrument': 'a.SH', 't_index': 9, 'date': pd.Timestamp('2022-03-01')},  # 50日,保留
    ]
    out = m.dedupe_events(evs, gap_days=30)
    assert [e['t_index'] for e in out] == [1, 9]


def test_build_event_panel():
    d = _market_with_indicators()
    events = _all_events(d, {'abs': 0.15})
    gp = {'D': 10, 'shrink': 0.3, 'up_vol': 0.6, 'up_drop': 0.05}
    panel = m.build_event_panel(d, events, gp, [5, 20])
    assert len(panel) == 10
    assert {'instrument', 'date', 'group', 'ret_5d', 'ret_20d'}.issubset(panel.columns)
    assert set(panel['group']) == {'A', 'B'}


# ============================================================
# T6 统计检验
# ============================================================
def test_welch_known_value():
    x = np.array([1., 2, 3, 4, 5]); y = np.array([6., 7, 8, 9, 10])
    t, p = m.welch_t(x, y)
    assert abs(t - (-5.0)) < 1e-6              # t = -5, df = 8
    assert 0.0008 < p < 0.0014                 # 双尾 p ≈ 0.00105


def test_welch_identical():
    x = np.random.default_rng(0).normal(size=200)
    t, p = m.welch_t(x, x.copy())
    assert p > 0.5


def test_welch_separated():
    x = np.random.default_rng(0).normal(size=200)
    t, p = m.welch_t(x, x + 1.0)
    assert p < 1e-10


def test_mannwhitney_separated_and_ties():
    x = np.arange(1, 21.0); y = x + 20          # 完全分离
    u, p = m.mann_whitney_u(x, y)
    assert p < 1e-6
    # 相同分布(含并列)不显著
    u, p = m.mann_whitney_u(np.array([1, 1, 2, 2, 3]), np.array([1, 2, 2, 3, 3]))
    assert p > 0.05


def test_group_stats_table():
    panel = pd.DataFrame({
        'group': ['A', 'A', 'A', 'A', 'B', 'B', 'B', 'B'],
        'ret_20d': [0.10, 0.05, 0.0, -0.02, -0.10, -0.05, 0.01, -0.03],
    })
    out = m.group_stats_table(panel, [20])
    a = out[out['group'] == 'A'].iloc[0]
    assert abs(a['mean'] - 0.0325) < 1e-9
    assert a['win_rate'] == 0.5
    assert a['pl_ratio'] > 1


def test_compare_groups():
    panel = pd.DataFrame({
        'group': ['A'] * 50 + ['B'] * 50,
        'ret_20d': np.r_[np.random.default_rng(1).normal(0.05, 0.02, 50),
                         np.random.default_rng(2).normal(0.0, 0.02, 50)],
    })
    r = m.compare_groups(panel, 20)
    assert r['diff_mean'] > 0 and r['significant']


def test_yearly_and_size_breakdown():
    rng3, rng4 = np.random.default_rng(3), np.random.default_rng(4)
    n = 20
    panel = pd.DataFrame({
        'group': ['A'] * (2 * n) + ['B'] * (2 * n),
        'date': pd.to_datetime(['2020-06-01'] * n + ['2021-06-01'] * n
                               + ['2020-06-01'] * n + ['2021-06-01'] * n),
        'ret_20d': np.r_[rng3.normal(0.05, 0.02, 2 * n), rng4.normal(0.0, 0.02, 2 * n)],
        'instrument': ['a.SH'] * (2 * n) + ['b.SH'] * (2 * n),
    })
    y = m.yearly_breakdown(panel, 20, min_n=5)
    assert {'year'} <= set(y.columns) and len(y) == 2   # 两年各含 A/B 各20
    assert (y['diff_mean'] > 0).all()
    # 市值: 三档
    caps = {'a.SH': 1e10, 'b.SH': 5e9, 'c.SH': 1e9}
    frames = []
    for inst, cap in caps.items():
        for grp in ['A', 'B']:
            frames.append(pd.DataFrame({
                'instrument': inst, 'group': grp,
                'date': pd.to_datetime(['2020-06-01', '2021-06-01'] * 8)[:16],
                'ret_20d': np.random.default_rng(5).normal(
                    0.05 if grp == 'A' else 0.0, 0.02, 16),
            }))
    panel2 = pd.concat(frames, ignore_index=True)
    val = pd.DataFrame({
        'instrument': ['a.SH'] * 2 + ['b.SH'] * 2 + ['c.SH'] * 2,
        'date': pd.to_datetime(['2020-06-30', '2021-06-30'] * 3),
        'total_market_cap': [1e10, 1e10, 5e9, 5e9, 1e9, 1e9],
    })
    s = m.size_breakdown(panel2, val, 20)
    assert 'size' in s.columns and len(s) == 3
    assert set(s['size']) == {'小', '中', '大'}


# ============================================================
# T7 端到端冒烟
# ============================================================
def test_main_end_to_end(tmp_path_factory):
    d = str(tmp_path_factory.mktemp('cache'))
    o = str(tmp_path_factory.mktemp('out'))
    bar = generate_market(seed=42)
    m.save_cache(d, {'bar': bar, 'basic': None, 'valuation': None})
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
