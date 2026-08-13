# -*- coding: utf-8 -*-
"""合成A股行情生成器: 注入确定性事件模式供本地测试。

模式分布(12只, 400交易日, 冒尖日=第250日, 基准日收益+0.6%):
  - 前6只 'wash'        : 上升趋势 + 高换手冒尖 + 缩量回踩MA20企稳后反弹
                          (回踩251-256日 -0.5%缩量 → 反弹257-259日 +2% → 260日起 +0.8%/日) → 洗盘A
  - 中4只 'distribution' : 上升趋势 + 高换手冒尖 + 放量下跌
                          (251-252日 -5%放量 → 253-262日阴跌 → 263日起 -0.1%/日) → 出货B
  - 后2只 'none'         : 纯上升趋势无冒尖(→ 对照样本)

注: 模式结束后的漂移差异(洗盘+0.8% vs 出货-0.1%)模拟"洗盘后行情延续、出货后走弱",
    使前向收益(判定完成日后)天然可分, 事件研究才可检验。
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
        # 模式后: 行情延续 +0.8%/日
        r[260:] = 0.008
    elif mode == 'distribution':
        # 放量下跌 251-252: -5.5%(连续复利, 简单收益约-5.35%) × 3.5/3.2倍量;
        # 换手 9%/8% (低于 10% 冒尖阈值, 避免下跌日被误判为新的冒尖事件)
        r[251] = -0.055; vol[251] = 3.5; turn[251] = 0.09
        r[252] = -0.055; vol[252] = 3.2; turn[252] = 0.08
        r[253:263] = -0.008
        vol[253:263] = 1.0
        # 模式后: 走弱 -0.1%/日
        r[263:] = -0.001

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
