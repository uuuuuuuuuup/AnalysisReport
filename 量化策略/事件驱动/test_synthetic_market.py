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
    # 模式后: 延续强势 +0.8%/日
    assert g.loc[260:, 'close'].pct_change().dropna().mean() > 0.005


def test_distribution_collapse_and_weak():
    df = generate_market(seed=42)
    g = df[df['instrument'] == INSTRUMENTS[6]].reset_index(drop=True)
    # 放量下跌: 251-252 单日 -5%, 量 ≥3倍
    assert g.loc[251, 'close'] / g.loc[250, 'close'] - 1 <= -0.049
    assert g.loc[251, 'volume'] >= 3.0
    # 模式后: 走弱 -0.1%/日
    assert g.loc[263:, 'close'].pct_change().dropna().mean() < 0.0
