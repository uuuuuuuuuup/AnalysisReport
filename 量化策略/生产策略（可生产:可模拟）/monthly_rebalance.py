# -*- coding: utf-8 -*-
# ============================================================
# 三引擎月度调仓单生成器 (BigQuant Notebook)
# ============================================================
# 用法: 每月最后一个交易日跑一次, 输出买卖清单。
# 不需要 BigTrader, 只用 dai.query() 拉数据。
#
# 修复点：可转债切换新版数据表cn_cbond_bar1d，关联cn_cbond_analyze_metric获取溢价率
# 输出:
#   1. Engine 1 ETF 动量排名 → 本月选哪 2 只
#   2. Engine 2 可转债双低排名 → 本月选哪 20 只
#   3. Engine 3 红利ETF → 季度再平衡检查
#   4. 汇总操作清单
# ============================================================

import dai
import pandas as pd
import numpy as np
from datetime import datetime as dt, timedelta

# ============================================================
# 冻结参数
# ============================================================

# -- Engine 1: ETF 双动量 --
ETF_UNIVERSE = {
    '510300.SH': '沪深300',
    '510500.SH': '中证500',
    '159915.SZ': '创业板',
    '510880.SH': '红利',
    '513100.SH': '纳指',
    '518880.SH': '黄金',
}
ETF_SAFE  = '511010.SH'   # 国债ETF
ETF_K     = 6              # 动量回看月数
ETF_M     = 2              # 持仓数
W1        = 0.35           # 仓位

# -- Engine 2: 可转债双低 --
CB_N_HOLD       = 20
CB_BUFFER_N     = 25
CB_W_PRICE      = 0.50
CB_W_PREMIUM    = 0.50
CB_MIN_LIST_DAYS = 30
CB_MIN_TERM     = 12       # 距到期月数
CB_CREDIT_PRICE = 80
CB_CREDIT_PREM  = 100
W2              = 0.35     # 仓位

# -- Engine 3: 红利ETF --
DIV_ETF = '515180.SH'
W3      = 0.30
DIV_RB_MONTHS = {3, 6, 9, 12}

# 资金
TOTAL_CAPITAL = 100_000


# ============================================================
# 1. 确定调仓日 (最近一个交易日)
# ============================================================

# 从 ETF 数据取最近的交易日
test = dai.query("""
    SELECT date FROM cn_fund_bar1d ORDER BY date DESC LIMIT 1
""", full_db_scan=True).df()
latest_dt = pd.to_datetime(test['date'].iloc[0])
print('数据日期: %s' % latest_dt.strftime('%Y-%m-%d'))

# 用最近交易日作为调仓日
today = latest_dt


# ============================================================
# 2. Engine 1: ETF 动量选股
# ============================================================

print('\n' + '=' * 60)
print('[Engine 1] ETF 双动量 (%.0f%%仓位 ≈ %.0f元)'
      % (W1 * 100, TOTAL_CAPITAL * W1))
print('=' * 60)

# 拉取约 12 个月 ETF 日线 (覆盖 K=6 回看 + 缓冲)
d1 = (today - timedelta(days=400)).strftime('%Y-%m-%d')
d2 = today.strftime('%Y-%m-%d')
all_etfs = list(ETF_UNIVERSE.keys()) + [ETF_SAFE]

etf_df = dai.query("""
    SELECT date, instrument, close FROM cn_fund_bar1d ORDER BY date
""", filters={"date": [d1, d2], "instrument": all_etfs}).df()

if len(etf_df) == 0:
    raise RuntimeError('cn_fund_bar1d 无数据, 检查 filters')

etf_df['date'] = pd.to_datetime(etf_df['date'])

# 月末价格映射
etf_df['ym'] = etf_df['date'].dt.strftime('%Y-%m')
etf_me = etf_df.groupby(['ym', 'instrument'])['close'].last().reset_index()

today_ym = today.strftime('%Y-%m')
mom = {}

for s in all_etfs:
    # 当前价
    cur = etf_df[(etf_df['instrument'] == s) & (etf_df['date'] <= today)]
    if len(cur) == 0:
        continue
    px = cur['close'].iloc[-1]
    if px <= 0:
        continue

    # K 个月前的月末价
    me = etf_me[etf_me['instrument'] == s]
    me = me[me['ym'] < today_ym].sort_values('ym')
    if len(me) < ETF_K:
        continue
    base = me['close'].iloc[-ETF_K]
    if pd.isna(base) or base <= 0:
        continue

    mom[s] = (px / base - 1, px, base)

# 排名
ranked = sorted(mom.items(), key=lambda kv: kv[1][0], reverse=True)

print('\n6个月动量排名:')
for s, (m, px, base) in ranked:
    label = ETF_UNIVERSE.get(s, '国债')
    flag = '← 正动量' if m > 0 else '(避险)'
    print('  %-8s %s  %+.1f%%  (%.3f / %.3f) %s'
          % (s, label, m * 100, px, base, flag))

# 选股
picks = []
for s, (m, _, _) in ranked[:ETF_M]:
    if m <= 0:
        picks.append(ETF_SAFE)
    else:
        picks.append(s)

e1_targets = {}
for s in picks:
    e1_targets[s] = e1_targets.get(s, 0.0) + 1.0 / ETF_M

print('\n本月持仓:')
for s, w in e1_targets.items():
    label = ETF_UNIVERSE.get(s, '国债')
    print('  %s %s  %.1f%%仓位 ≈ %.0f元'
          % (s, label, w * W1 * 100, TOTAL_CAPITAL * W1 * w))


# ============================================================
# 3. Engine 2: 可转债双低选股【修复新版数据表关联】
# ============================================================

print('\n' + '=' * 60)
print('[Engine 2] 可转债经典双低 (%.0f%%仓位 ≈ %.0f元)'
      % (W2 * 100, TOTAL_CAPITAL * W2))
print('=' * 60)

# 取最近5天区间
cb_d1 = (today - timedelta(days=5)).strftime('%Y-%m-%d')
cb_d2 = today.strftime('%Y-%m-%d')

cb_raw = dai.query("""
    SELECT 
        a.date, 
        a.instrument, 
        a.close, 
        m.conversion_premium_rate AS premium_rate,
        b.maturity_date, 
        b.list_date, 
        b.name AS bond_name
    FROM cn_cbond_bar1d a
    INNER JOIN cn_cbond_basic_info b ON a.instrument = b.instrument
    INNER JOIN cn_cbond_analyze_metric m 
        ON a.instrument = m.instrument AND a.date = m.date
    WHERE a.date >= '%s' AND a.date <= '%s'
      AND a.close > 0 
      AND b.maturity_date IS NOT NULL
    ORDER BY a.date, a.instrument
""" % (cb_d1, cb_d2)).df()

if len(cb_raw) == 0:
    print('⚠️ cn_cbond_bar1d + cn_cbond_analyze_metric 查询无数据，确认账户数据权限')
    e2_targets = {}
else:
    cb_raw['date'] = pd.to_datetime(cb_raw['date'])
    cb_raw['maturity_date'] = pd.to_datetime(cb_raw['maturity_date'])
    cb_raw['list_date'] = pd.to_datetime(cb_raw['list_date'])

    # 取最新交易日数据
    cb_latest_date = cb_raw['date'].max()
    cb = cb_raw[cb_raw['date'] == cb_latest_date].copy()
    print('可转债数据日期: %s, %d 只标的'
          % (cb_latest_date.strftime('%Y-%m-%d'), len(cb)))

    # 过滤条件
    cb['days_listed'] = (cb_latest_date - cb['list_date']).dt.days
    cb['months_to_mat'] = (cb['maturity_date'] - cb_latest_date).dt.days / 30.0
    cb = cb[(cb['days_listed'] >= CB_MIN_LIST_DAYS) &
            (cb['months_to_mat'] >= CB_MIN_TERM)]
    print('上市+期限过滤后: %d 只' % len(cb))

    # 信用风险过滤
    cb = cb[~((cb['close'] < CB_CREDIT_PRICE) &
              (cb['premium_rate'] > CB_CREDIT_PREM))]
    print('信用过滤后: %d 只' % len(cb))

    # Z-score标准化打分
    for col in ['close', 'premium_rate']:
        s = cb[col]
        m, std = s.mean(), s.std()
        cb[col + '_z'] = -(s - m) / std if std > 0 else 0

    cb['score'] = CB_W_PRICE * cb['close_z'] + CB_W_PREMIUM * cb['premium_rate_z']
    cb = cb.sort_values('score', ascending=False)

    # 选出持仓标的
    e2_selected = cb.head(CB_N_HOLD)
    e2_targets = {row['instrument']: 1.0 / CB_N_HOLD
                  for _, row in e2_selected.iterrows()}

    print('\n本月选中 %d 只:' % len(e2_targets))
    for _, row in e2_selected.iterrows():
        bond_show_name = row['bond_name'][:12]
        print('  %-10s %-12s  价格 %6.1f  溢价 %+.0f%%  得分 %+.2f'
              % (row['instrument'], bond_show_name,
                 row['close'], row['premium_rate'], row['score']))


# ============================================================
# 4. Engine 3: 红利ETF 静态持有
# ============================================================

print('\n' + '=' * 60)
print('[Engine 3] 红利ETF 静态持有 (%.0f%%仓位 ≈ %.0f元)'
      % (W3 * 100, TOTAL_CAPITAL * W3))
print('=' * 60)

if today.month in DIV_RB_MONTHS:
    print('本月为季度再平衡月, 调整 %s 到目标仓位 %.0f元' % (DIV_ETF, TOTAL_CAPITAL * W3))
else:
    # 取 515180 当前价格
    div_px = etf_df[(etf_df['instrument'] == DIV_ETF) &
                     (etf_df['date'] <= today)]
    if len(div_px) > 0:
        px = div_px['close'].iloc[-1]
        lots = int(TOTAL_CAPITAL * W3 / (px * 100)) * 100
        print('持有不动: %s 红利ETF易方达  价格 %.3f  约 %d份 (%.0f元)'
              % (DIV_ETF, px, lots, lots * px))
    else:
        print('持有不动: %s 红利ETF易方达  仓位 %.0f%%' % (DIV_ETF, W3 * 100))

e3_targets = {DIV_ETF: W3}


# ============================================================
# 5. 汇总操作清单
# ============================================================

print('\n' + '=' * 60)
print('操作清单')
print('=' * 60)

# 合并所有目标
all_targets = {}

# E1: engine内权重 → 占总资产权重
for s, w in e1_targets.items():
    all_targets[s] = w * W1

# E2
for s, w in e2_targets.items():
    all_targets[s] = w * W2

# E3
all_targets[DIV_ETF] = W3

# 按权重排序
print('\n目标持仓:')
total_w = 0
for s, w in sorted(all_targets.items(), key=lambda kv: -kv[1]):
    label = ETF_UNIVERSE.get(s, '')
    if not label:
        label = '(可转债)'
    amount = TOTAL_CAPITAL * w
    print('  %s %-12s  %.1f%%  ≈ %.0f元  (约%d手)'
          % (s, label, w * 100, amount,
             max(1, int(amount / 1100))))  # 可转债1手≈1100
    total_w += w

print('\n总仓位: %.0f%%  闲置现金: %.0f%% (%.0f元)'
      % (total_w * 100, (1 - total_w) * 100,
         TOTAL_CAPITAL * (1 - total_w)))

# 风险提示
print('\n--- 风险提示 ---')
# E1 检查
n_pos = sum(1 for s, (m, _, _) in ranked if m > 0)
if n_pos <= 1:
    print('⚠️ E1: 仅 %d/6 只 ETF 正动量, 市场趋势偏弱' % n_pos)

# E2 检查
if not e2_targets:
    print('⚠️ E2: 可转债数据不可用, 本月跳过, 闲置资金 35%%')

print('\n===== 以上为参考调仓单, 实际下单请确认盘口价格 =====')