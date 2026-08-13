# -*- coding: utf-8 -*-
# ============================================================
# 调试脚本: 定位 load_monthly_fundamentals 每步失败原因
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("调试: 逐步骤诊断数据加载失败原因")
print("=" * 60)

TRAIN_START = '2015-01-01'
TRAIN_END   = '2021-12-31'
UNIVERSE    = '000906.XSHG'   # 中证800

trade_days = list(get_trade_days(start_date=TRAIN_START, end_date=TRAIN_END))
months = pd.Series(trade_days).groupby(
    pd.Series(trade_days).apply(lambda d: d.strftime('%Y-%m'))
).last().tolist()

print(f"\n调仓月份数: {len(months)}")
print(f"首月: {months[0]}, 末月: {months[-1]}")

# ============================================================
# Step 1: 测试 get_index_stocks
# ============================================================
print("\n" + "-" * 40)
print("Step 1: 测试 get_index_stocks")
dt = months[0]
try:
    pool = get_index_stocks(UNIVERSE, date=dt)
    print(f"  UNIVERSE={UNIVERSE}, date={dt}")
    print(f"  返回: {len(pool)} 只股票")
    if pool:
        print(f"  前5只: {pool[:5]}")
except Exception as e:
    print(f"  ❌ 失败: {type(e).__name__}: {e}")
    print(f"  尝试不带市场后缀...")
    try:
        pool = get_index_stocks('000906', date=dt)
        print(f"  000906 返回: {len(pool)} 只")
    except Exception as e2:
        print(f"  ❌ 也失败: {e2}")

# ============================================================
# Step 2: 测试 get_fundamentals
# ============================================================
print("\n" + "-" * 40)
print("Step 2: 测试 get_fundamentals")

# 重新获取 pool
pool = get_index_stocks(UNIVERSE, date=months[0])
print(f"  pool 大小: {len(pool)}")

if len(pool) > 300:
    pool_sample = pool[:300]
    print(f"  取前300只做测试")
else:
    pool_sample = pool

try:
    q = query(valuation.code, valuation.pb_ratio, valuation.market_cap,
              indicator.roe).filter(valuation.code.in_(pool_sample))
    fd = get_fundamentals(q, date=months[0])
    if fd is not None:
        print(f"  ✅ 成功: {len(fd)} 行")
        print(f"  列: {list(fd.columns)}")
        print(f"  PB>0 的: {(fd['pb_ratio'] > 0).sum()} 只")
        print(f"  前3行:\n{fd.head(3)}")
    else:
        print(f"  ⚠️ 返回 None")
except Exception as e:
    print(f"  ❌ 失败: {type(e).__name__}: {e}")
    print(f"\n  尝试分开查询 valuation...")
    try:
        q = query(valuation.code, valuation.pb_ratio, valuation.market_cap
                  ).filter(valuation.code.in_(pool_sample))
        fd = get_fundamentals(q, date=months[0])
        print(f"  valuation 单独查询: {len(fd) if fd is not None else 0} 行")
        if fd is not None:
            print(f"  列: {list(fd.columns)}")
    except Exception as e3:
        print(f"  ❌ valuation 查询也失败: {e3}")

    print(f"\n  尝试分开查询 indicator...")
    try:
        q = query(indicator.code, indicator.roe).filter(indicator.code.in_(pool_sample))
        idr = get_fundamentals(q, date=months[0])
        print(f"  indicator 单独查询: {len(idr) if idr is not None else 0} 行")
        if idr is not None:
            print(f"  列: {list(idr.columns)}")
    except Exception as e4:
        print(f"  ❌ indicator 查询也失败: {e4}")

# ============================================================
# Step 3: 测试 get_price
# ============================================================
print("\n" + "-" * 40)
print("Step 3: 测试 get_price")

lookback_start = months[0] - pd.Timedelta(days=365)
print(f"  日期范围: {lookback_start} → {months[0]}")
print(f"  股票数: {len(pool_sample)}")

try:
    px = get_price(
        pool_sample[:50],  # 先取50只测试
        start_date=lookback_start,
        end_date=months[0],
        fields=['close'],
        skip_paused=True,
        fq='pre'
    )
    print(f"  ✅ 成功: shape={px.shape}")
    print(f"  列 (股票数): {len(px['close'].columns)}")
except Exception as e:
    print(f"  ❌ 失败: {type(e).__name__}: {e}")
    print(f"  尝试不带 fq 参数...")
    try:
        px = get_price(
            pool_sample[:50],
            start_date=lookback_start,
            end_date=months[0],
            fields=['close'],
            skip_paused=True
        )
        print(f"  ✅ (无fq) 成功: shape={px.shape}")
    except Exception as e2:
        print(f"  ❌ 也失败: {e2}")

# ============================================================
# Step 4: 测试 get_industry
# ============================================================
print("\n" + "-" * 40)
print("Step 4: 测试 get_industry")

try:
    ind_info = get_industry(pool_sample[:10], date=months[0])
    print(f"  ✅ 成功: {len(ind_info)} 只")
    first = list(ind_info.items())[0]
    print(f"  第一只: {first}")
    # 检查 sw_l1 结构
    if first[1]:
        print(f"  sw_l1 keys: {list(first[1].keys())}")
        sw = first[1].get('sw_l1', {})
        print(f"  sw_l1: {sw}")
except Exception as e:
    print(f"  ❌ 失败: {type(e).__name__}: {e}")

# ============================================================
# Step 5: 综合测试 — 跑第一个月完整流程
# ============================================================
print("\n" + "=" * 60)
print("Step 5: 跑第一个月完整流程")
print("=" * 60)

dt = months[0]
next_dt = months[1]
print(f"  本月: {dt}, 下月: {next_dt}")

# 5a. 成分股
pool = get_index_stocks(UNIVERSE, date=dt)
print(f"5a. 成分股: {len(pool)} 只")

# 5b. 基本面
try:
    fd = get_fundamentals(
        query(valuation.code, valuation.pb_ratio, valuation.market_cap,
              indicator.roe).filter(valuation.code.in_(pool[:300])),
        date=dt
    )
    print(f"5b. 基本面查询: {len(fd) if fd is not None else 'None'}")
    if fd is not None and not fd.empty:
        fd = fd.set_index('code')
        fd = fd[fd['pb_ratio'] > 0]
        fd = fd[fd['market_cap'] > 0]
        print(f"    过滤PB>0: {len(fd)} 只")
except Exception as e:
    print(f"5b. ❌ {e}")
    fd = None

# 5c. 价格数据
if fd is not None and len(fd) > 0:
    codes = list(fd.index[:50])
    lookback = dt - pd.Timedelta(days=365)
    try:
        px = get_price(codes, start_date=lookback, end_date=dt,
                       fields=['close'], skip_paused=True, fq='pre')
        print(f"5c. 价格数据: {px.shape}")
    except Exception as e:
        print(f"5c. ❌ {e}")

# 5d. 行业
try:
    ind = get_industry(list(fd.index[:10]) if fd is not None and len(fd) > 0 else pool[:10], date=dt)
    print(f"5d. 行业: {len(ind)} 只")
except Exception as e:
    print(f"5d. ❌ {e}")

print("\n" + "=" * 60)
print("调试完成。请将以上输出发给我，我来定位具体问题。")
print("=" * 60)
