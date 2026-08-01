# -*- coding: utf-8 -*-
# ============================================================
# 事件驱动策略 - 训练集数据分析 (2019-01 ~ 2023-12)
# ============================================================
# 目的:
#   1. 检查事件数据表是否存在、字段是否正确
#   2. 统计事件分布: 每月有多少业绩超预期/增持回购事件
#   3. 计算事件后收益: 业绩超预期后5/10/15/20日平均超额收益
#   4. 计算增持/回购后收益: 同上
#   5. 确定最优持有期和阈值
# ============================================================

import dai
import pandas as pd
import numpy as np
from datetime import datetime as dt, timedelta

# 数据划分
TRAIN_START = '2019-01-01'
TRAIN_END = '2023-12-31'
DATA_START = '2018-09-01'  # 前置数据(计算事件后收益需要)

print('=' * 60)
print('事件驱动策略 - 训练集数据分析')
print('训练集: %s ~ %s' % (TRAIN_START, TRAIN_END))
print('=' * 60)

# ============================================================
# 1. 加载行情数据
# ============================================================
print('\n加载行情数据...')
sql_price = """
SELECT
    a.date, a.instrument, a.close, a.amount,
    v.float_market_cap AS circulating_market_cap
FROM cn_stock_bar1d a
INNER JOIN cn_stock_valuation v
    ON a.instrument = v.instrument AND a.date = v.date
WHERE a.close > 0
ORDER BY a.date, a.instrument
"""
df_price = dai.query(sql_price, filters={"date": [DATA_START, TRAIN_END]}).df()
df_price['date'] = pd.to_datetime(df_price['date'])
print('行情: %d 行, %d 标的, %s ~ %s'
      % (len(df_price), df_price['instrument'].nunique(),
         df_price['date'].min().strftime('%Y-%m-%d'),
         df_price['date'].max().strftime('%Y-%m-%d')))

# 构建价格矩阵(用于快速查找未来收益)
price_pivot = df_price.pivot_table(index='date', columns='instrument', values='close')
print('价格矩阵: %d 天 × %d 标的' % price_pivot.shape)

# 构建 security_code → instrument 映射
# 事件表用 security_code (如 '600519'), 行情表用 instrument (如 '600519.SH')
inst_set = set(df_price['instrument'].unique())
code_to_inst = {}
for inst in inst_set:
    # '600519.SH' → '600519'
    code = inst.split('.')[0]
    code_to_inst[code] = inst


def map_code_to_inst(df, code_col='security_code'):
    """将 security_code 映射为 instrument 格式"""
    df['instrument'] = df[code_col].map(code_to_inst)
    return df[df['instrument'].notna()].copy()


# ============================================================
# 2. 检查并加载事件数据表
# ============================================================
def safe_query(name, sql, filters_col, date_range):
    """安全查询, 表不存在时返回空DataFrame"""
    try:
        df = dai.query(sql, filters={filters_col: date_range}).df()
        print('  ✅ %s: %d 行' % (name, len(df)))
        return df
    except Exception as e:
        err_str = str(e)
        if 'does not exist' in err_str or 'not found' in err_str:
            print('  ❌ %s: 表不存在' % name)
        else:
            print('  ⚠️ %s: %s' % (name, err_str[:120]))
        return pd.DataFrame()


print('\n检查事件数据表...')

# 业绩预告
# 字段: security_code, ann_date, profit_yoy_min, profit_yoy_max, forecast_type
print('\n--- 业绩预告 (cn_stock_forecast) ---')
sql_forecast = """
SELECT security_code, ann_date,
       profit_yoy_min, profit_yoy_max, forecast_type
FROM astock_forecast
WHERE profit_yoy_min IS NOT NULL
ORDER BY ann_date, security_code
"""
df_forecast = safe_query('业绩预告', sql_forecast, 'ann_date', [TRAIN_START, TRAIN_END])
if len(df_forecast) > 0:
    df_forecast['ann_date'] = pd.to_datetime(df_forecast['ann_date'])
    df_forecast = map_code_to_inst(df_forecast)
    print('  映射后: %d 行' % len(df_forecast))

# 业绩快报
# 字段: security_code, ann_date, net_profit_yoy
print('\n--- 业绩快报 (cn_stock_financial_brief) ---')
sql_brief = """
SELECT security_code, ann_date, net_profit_yoy
FROM astock_financial_brief
WHERE net_profit_yoy IS NOT NULL
ORDER BY ann_date, security_code
"""
df_brief = safe_query('业绩快报', sql_brief, 'ann_date', [TRAIN_START, TRAIN_END])
if len(df_brief) > 0:
    df_brief['ann_date'] = pd.to_datetime(df_brief['ann_date'])
    df_brief = map_code_to_inst(df_brief)
    print('  映射后: %d 行' % len(df_brief))

# 增持
# 字段: security_code, ann_date, trade_direction, trade_amount, trade_volume
print('\n--- 增持 (cn_stock_stk_holdertrade) ---')
sql_holder = """
SELECT security_code, ann_date,
       trade_direction, trade_amount, trade_volume
FROM astock_holder_trade
WHERE trade_direction = 'BUY'
  AND trade_volume > 0
ORDER BY ann_date, security_code
"""
df_holder = safe_query('增持', sql_holder, 'ann_date', [TRAIN_START, TRAIN_END])
if len(df_holder) > 0:
    df_holder['ann_date'] = pd.to_datetime(df_holder['ann_date'])
    df_holder = map_code_to_inst(df_holder)
    print('  映射后: %d 行' % len(df_holder))

# 回购
# 字段: security_code, ann_date, complete_amount, status
print('\n--- 回购 (cn_stock_repurchase) ---')
sql_repo = """
SELECT security_code, ann_date,
       complete_amount, status
FROM astock_repurchase
WHERE complete_amount IS NOT NULL
  AND complete_amount > 0
ORDER BY ann_date, security_code
"""
df_repo = safe_query('回购', sql_repo, 'ann_date', [TRAIN_START, TRAIN_END])
if len(df_repo) > 0:
    df_repo['ann_date'] = pd.to_datetime(df_repo['ann_date'])
    df_repo = map_code_to_inst(df_repo)
    print('  映射后: %d 行' % len(df_repo))


# ============================================================
# 3. 事件分布统计
# ============================================================
print('\n' + '=' * 60)
print('事件分布统计')
print('=' * 60)

# 业绩预告分布
if len(df_forecast) > 0:
    fc_monthly = df_forecast.set_index('ann_date').resample('M').size()
    fc_yoy = df_forecast['profit_yoy_min']
    print('\n业绩预告:')
    print('  总事件数: %d' % len(df_forecast))
    print('  月均事件: %.0f' % fc_monthly.mean())
    if 'forecast_type' in df_forecast.columns:
        print('  预告类型分布:')
        for ft, cnt in df_forecast['forecast_type'].value_counts().head(10).items():
            print('    %s: %d' % (ft, cnt))
    print('  同比增幅分布:')
    for thresh in [0.3, 0.5, 1.0, 2.0]:
        n = (fc_yoy > thresh).sum()
        print('    同比>%.0f%%: %d 只 (%.1f%%)' % (thresh * 100, n, n / len(df_forecast) * 100))

# 业绩快报分布
if len(df_brief) > 0:
    bf_monthly = df_brief.set_index('ann_date').resample('M').size()
    bf_yoy = df_brief['net_profit_yoy']
    print('\n业绩快报:')
    print('  总事件数: %d' % len(df_brief))
    print('  月均事件: %.0f' % bf_monthly.mean())
    print('  同比增幅分布:')
    for thresh in [0.3, 0.5, 1.0, 2.0]:
        n = (bf_yoy > thresh).sum()
        print('    同比>%.0f%%: %d 只 (%.1f%%)' % (thresh * 100, n, n / len(df_brief) * 100))

# 增持分布
if len(df_holder) > 0:
    hd_monthly = df_holder.set_index('ann_date').resample('M').size()
    print('\n增持:')
    print('  总事件数: %d' % len(df_holder))
    print('  月均事件: %.0f' % hd_monthly.mean())
    if 'trade_amount' in df_holder.columns:
        amt = df_holder['trade_amount'].dropna()
        if len(amt) > 0:
            print('  增持金额中位数: %.0f万' % (amt.median() / 10000))

# 回购分布
if len(df_repo) > 0:
    rp_monthly = df_repo.set_index('ann_date').resample('M').size()
    print('\n回购:')
    print('  总事件数: %d' % len(df_repo))
    print('  月均事件: %.0f' % rp_monthly.mean())
    if 'complete_amount' in df_repo.columns:
        amt = df_repo['complete_amount'].dropna()
        if len(amt) > 0:
            print('  已回购金额中位数: %.0f万' % (amt.median() / 10000))


# ============================================================
# 4. 事件后收益分析 (PEAD)
# ============================================================
print('\n' + '=' * 60)
print('事件后收益分析')
print('=' * 60)

def calc_event_returns(events_df, date_col, instrument_col, price_pivot,
                       holding_days=[5, 10, 15, 20], label=''):
    """计算事件后N日平均收益"""
    if len(events_df) == 0:
        print('\n%s: 无数据, 跳过' % label)
        return {}

    results = {d: [] for d in holding_days}
    valid = 0
    total = 0

    dates = events_df[date_col].values
    instruments = events_df[instrument_col].values

    for i in range(len(events_df)):
        event_date = pd.Timestamp(dates[i])
        inst = instruments[i]
        total += 1

        if inst not in price_pivot.columns:
            continue
        if event_date not in price_pivot.index:
            continue
        px0 = price_pivot.loc[event_date, inst]
        if pd.isna(px0) or px0 <= 0:
            continue

        future_dates = price_pivot.index[price_pivot.index > event_date]
        if len(future_dates) == 0:
            continue

        for d in holding_days:
            idx = min(d, len(future_dates) - 1)
            future_date = future_dates[idx]
            px1 = price_pivot.loc[future_date, inst]
            if pd.isna(px1) or px1 <= 0:
                continue
            ret = px1 / px0 - 1
            results[d].append(ret)

        valid += 1

    print('\n%s (有效事件: %d/%d):' % (label, valid, total))
    if valid == 0:
        return results

    for d in holding_days:
        if len(results[d]) > 0:
            avg = np.mean(results[d])
            med = np.median(results[d])
            win = np.mean(np.array(results[d]) > 0)
            print('  %d日后: 均值 %+.2f%%  中位数 %+.2f%%  胜率 %.1f%%  (n=%d)'
                  % (d, avg * 100, med * 100, win * 100, len(results[d])))

    return results


# 业绩预告: 不同同比阈值的事件后收益
print('\n--- 业绩预告: 事件后收益 ---')
if len(df_forecast) > 0:
    for thresh in [0.3, 0.5, 1.0]:
        fc_sub = df_forecast[df_forecast['profit_yoy_min'] > thresh]
        calc_event_returns(fc_sub, 'ann_date', 'instrument', price_pivot,
                          holding_days=[5, 10, 15, 20],
                          label='预告同比>%.0f%%' % (thresh * 100))
else:
    print('  业绩预告无数据')

# 业绩快报: 不同同比阈值的事件后收益
print('\n--- 业绩快报: 事件后收益 ---')
if len(df_brief) > 0:
    for thresh in [0.3, 0.5, 1.0]:
        bf_sub = df_brief[df_brief['net_profit_yoy'] > thresh]
        calc_event_returns(bf_sub, 'ann_date', 'instrument', price_pivot,
                          holding_days=[5, 10, 15, 20],
                          label='快报同比>%.0f%%' % (thresh * 100))
else:
    print('  业绩快报无数据')

# 增持: 事件后收益
print('\n--- 增持: 事件后收益 ---')
if len(df_holder) > 0:
    calc_event_returns(df_holder, 'ann_date', 'instrument', price_pivot,
                      holding_days=[5, 10, 15, 20], label='大股东增持')
else:
    print('  增持无数据')

# 回购: 事件后收益
print('\n--- 回购: 事件后收益 ---')
if len(df_repo) > 0:
    calc_event_returns(df_repo, 'ann_date', 'instrument', price_pivot,
                      holding_days=[5, 10, 15, 20], label='公司回购')
else:
    print('  回购无数据')


# ============================================================
# 5. 复合事件: 同时有业绩超预期+增持的标的表现
# ============================================================
print('\n' + '=' * 60)
print('复合事件: 业绩超预期 + 增持/回购')
print('=' * 60)

if len(df_forecast) > 0 and len(df_holder) > 0:
    fc_events = set()
    for _, row in df_forecast[df_forecast['profit_yoy_min'] > 0.5].iterrows():
        fc_events.add((row['instrument'], row['ann_date']))

    hd_events = set()
    for _, row in df_holder.iterrows():
        hd_events.add((row['instrument'], row['ann_date']))

    dual_events = []
    for inst, fc_date in fc_events:
        for inst2, hd_date in hd_events:
            if inst == inst2 and abs((fc_date - hd_date).days) <= 30:
                dual_events.append({'instrument': inst,
                                    'ann_date': min(fc_date, hd_date)})
                break

    if len(dual_events) > 0:
        df_dual = pd.DataFrame(dual_events)
        calc_event_returns(df_dual, 'ann_date', 'instrument', price_pivot,
                          holding_days=[5, 10, 15, 20],
                          label='复合事件(业绩+增持)')
    else:
        print('  未找到同时触发两种事件的标的')
else:
    print('  缺少业绩预告或增持数据, 无法分析复合事件')


# ============================================================
# 6. 参数建议
# ============================================================
print('\n' + '=' * 60)
print('参数建议 (基于训练集分析)')
print('=' * 60)
print('''
基于以上分析, 建议策略参数:

1. 业绩超预期阈值: 根据事件数量和后收益选择
   - 事件太少(月均<15) → 降低阈值
   - 事件太多(月均>100) → 提高阈值
   - 目标: 每次调仓有20-30个候选

2. 持有期: 根据PEAD衰减速度选择
   - 如果10日收益最高 → 持有10天
   - 如果15日收益最高 → 持有15天
   - 超过20日效应通常已衰减完毕

3. 事件窗口: 30天(覆盖一个月的事件)

4. 增持/回购权重: 根据两类事件的后收益对比调整
''')

print('\n===== 分析完成, 请根据结果调整 event_driven_strategy_bq.py 的参数 =====')
