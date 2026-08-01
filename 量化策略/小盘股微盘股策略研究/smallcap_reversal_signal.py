# -*- coding: utf-8 -*-
# ============================================================
# 小盘股反转轮动 - 周度调仓信号生成器
# ============================================================
# 用法: 每周最后一个交易日跑一次, 输出买卖清单。
# 不需要回测引擎, 只用 dai.query() 拉数据。
#
# 输出:
#   1. 当日因子排名 → 选出的20只标的
#   2. 与上周持仓对比 → 买卖操作清单
# ============================================================

import dai
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 冻结参数（与策略代码一致，禁止修改）
# ============================================================
N_HOLD = 20
BUFFER_N = 25
REVERSAL_PERIOD = 20
VOLATILITY_PERIOD = 20
TURNOVER_PERIOD = 20
MIN_LIST_DAYS = 60
CAP_PERCENTILE = 0.30
W_REVERSAL = 0.40
W_TURNOVER = 0.30
W_VOLATILITY = 0.30

TOTAL_CAPITAL = 100_000


# ============================================================
# 确定调仓日
# ============================================================
print('确定调仓日期...')

# 取最近交易日
test = dai.query("""
    SELECT date FROM cn_stock_bar1d ORDER BY date DESC LIMIT 1
""", full_db_scan=True).df()
latest_dt = pd.to_datetime(test['date'].iloc[0])
today = latest_dt
print('数据日期: %s' % today.strftime('%Y-%m-%d'))


# ============================================================
# 加载数据（取最近60个交易日，覆盖反转回看+缓冲）
# ============================================================
print('加载数据...')

d1 = (today - timedelta(days=120)).strftime('%Y-%m-%d')
d2 = today.strftime('%Y-%m-%d')

sql = """
SELECT
    p.date, p.instrument, p.close, p.volume,
    p.turn AS turnover_ratio,
    v.float_market_cap AS circulating_market_cap
FROM cn_stock_bar1d p
INNER JOIN cn_stock_valuation v
    ON p.date = v.date AND p.instrument = v.instrument
INNER JOIN cn_stock_prefactors f
    ON p.date = f.date AND p.instrument = f.instrument
WHERE
    p.close > 0
    AND p.volume > 0
    AND f.st_status = 0
    AND f.suspended = 0
    AND f.list_days >= %d
    AND f.list_sector NOT IN (3, 4)
ORDER BY p.date, p.instrument
""" % MIN_LIST_DAYS

df = dai.query(sql, filters={"date": [d1, d2]}).df()
df['date'] = pd.to_datetime(df['date'])

print('数据加载完成: %d 行, %d 标的' % (len(df), df['instrument'].nunique()))


# ============================================================
# 因子计算
# ============================================================
print('计算因子...')

# 取最新交易日数据
latest_date = df['date'].max()
cur = df[df['date'] == latest_date].copy()

# 市值排名
cur['cap_rank'] = cur['circulating_market'].rank(pct=True, na_option='keep') \
    if 'circulating_market' in cur.columns else \
    cur['circulating_market_cap'].rank(pct=True, na_option='keep')

# 小市值域
cur = cur[cur['cap_rank'] <= CAP_PERCENTILE]
print('小市值域: %d 只' % len(cur))

# 反转因子（需要历史数据）
grouped = df.groupby('instrument')
reversal = grouped['close'].transform(
    lambda x: -(x / x.shift(REVERSAL_PERIOD) - 1)
)
df['reversal'] = reversal

# 波动率因子
df['daily_ret'] = grouped['close'].transform(lambda x: x.pct_change())
df['volatility'] = grouped['daily_ret'].transform(
    lambda x: -x.rolling(VOLATILITY_PERIOD, min_periods=10).std()
)

# 换手率因子
df['turnover'] = grouped['turnover_ratio'].transform(
    lambda x: -x.rolling(TURNOVER_PERIOD, min_periods=10).mean()
)

# 取最新日数据
cur = df[df['date'] == latest_date].copy()
cur = cur[cur['cap_rank'] <= CAP_PERCENTILE]
cur = cur.dropna(subset=['reversal', 'volatility', 'turnover'])

print('因子计算完成: %d 只候选' % len(cur))

# ---- Z-score 标准化 ----
for col in ['reversal', 'volatility', 'turnover']:
    s = cur[col]
    mean, std = s.mean(), s.std()
    cur[col + '_z'] = (s - mean) / std if std > 0 else 0.0

# ---- 复合打分 ----
cur['score'] = (W_REVERSAL * cur['reversal_z'] +
               W_TURNOVER * cur['turnover_z'] +
               W_VOLATILITY * cur['volatility_z'])

cur = cur.sort_values('score', ascending=False)


# ============================================================
# 选股
# ============================================================
print('\n' + '=' * 60)
print('小盘股反转轮动 - 调仓信号')
print('=' * 60)
print('日期: %s' % latest_date.strftime('%Y-%m-%d'))

# 缓冲带选股（首次无持仓，直接选前20）
top_pool = cur.head(BUFFER_N)
selected = cur.head(N_HOLD)

print('\n选出的 %d 只标的:' % len(selected))
for i, (_, row) in enumerate(selected.iterrows(), 1):
    cap_yi = row['circulating_market_cap'] / 1e8 if not pd.isna(row['circulating_market_cap']) else 0
    ret_20d = -row['reversal']  # 反转因子取负过，这里还原原始跌幅
    print('  %2d. %-10s  价格 %7.2f  市值 %5.1f亿  20日跌幅 %5.1f%%  得分 %+.2f'
          % (i, row['instrument'], row['close'], cap_yi, ret_20d * 100, row['score']))


# ============================================================
# 操作清单
# ============================================================
print('\n' + '=' * 60)
print('操作清单（等权，每只约 %.0f 元）' % (TOTAL_CAPITAL / N_HOLD))
print('=' * 60)

target_set = set(selected['instrument'].tolist())
w = 1.0 / N_HOLD

for inst in sorted(target_set):
    amount = TOTAL_CAPITAL * w
    print('  买入  %-10s  目标仓位 %.1f%%  ≈ %.0f 元' % (inst, w * 100, amount))

print('\n合计: %d 只, 总仓位 %.0f%%' % (len(target_set), len(target_set) * w * 100))


# ============================================================
# 风险提示
# ============================================================
print('\n--- 风险提示 ---')

# 检查小市值集中度
avg_cap = selected['circulating_market_cap'].mean() / 1e8
print('平均流通市值: %.1f 亿' % avg_cap)

if avg_cap < 30:
    print('⚠️ 持仓平均市值 < 30亿，流动性风险较高')

# 检查跌幅集中度
avg_reversal = -selected['reversal'].mean()
if avg_reversal > 0.15:
    print('⚠️ 持仓平均20日跌幅 > 15%，可能存在价值陷阱')

print('\n===== 以上为参考调仓单, 实际下单请确认盘口价格 =====')