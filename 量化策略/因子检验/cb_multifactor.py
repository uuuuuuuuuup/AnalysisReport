# -*- coding: utf-8 -*-
# %% [markdown]
# # 可转债多因子轮动 — 【训练集】研究
#
# # ⛔ 数据边界声明 —— 修改 TRAIN_END 即销毁测试集
#
# ```
# 训练集  2019-01 ~ 2022-12  ( 48个月)   ← 本 notebook 只取这段，可反复试
# ────────────────── 数据墙 ──────────────────
# 测试集  2023-01 ~ 2026-07  ( 43个月)   ← 物理上不取，冻结参数后只看一次
# ```
#
# 起点选 2019-01 而非 2018-09 的原因：
# 1. 可转债日行情 CONBOND_DAILY_PRICE 从 2018-09-13 才开始
# 2. 动量回看需要 3 个月前置数据
# 3. 2017 年信用申购改革前市场不足 30 只，无法做截面排名
# 4. 2018 年末市场已有 100+ 只可转债，截面排名可行
#
# **本 notebook 的 `TRAIN_END = '2022-12-31'` 是硬边界。**
# 测试集对可转债方向是**完全干净的**——此前从未取过任何可转债数据。
#
# ---
#
# ## 策略逻辑（事前可辩护）
#
# ### 为什么是可转债？
# 1. **债底保护**：面值 100 元以下的可转债有纯债价值兜底，下行空间有限
# 2. **T+0 交易**：部分标的支持日内回转，流动性好
# 3. **免印花税**：散户账户万 0.85 佣金 + 免 5，往返成本 ~0.17%
# 4. **散户占比高**：定价效率低于股票 → α 空间更大
# 5. **双低策略十多年有效**：低价 + 低溢价率的等权组合长期年化 12-18%
#
# ### 因子候选（均有事前经济解释）
# | 因子 | 方向 | 经济解释 |
# |---|---|---|
# | 转债价格 | 越低越好 | 低价离债底近，下行空间有限；经典双低第一维 |
# | 转股溢价率 | 越低越好 | 低溢价 = 股性强，正股涨 10% 转债涨 8-9%；经典双低第二维 |
# | 正股 1 月动量 | 越高越好 | 短期趋势延续；可转债跟随正股 |
# | 正股 3 月反转 | 越低越好 | A 股小盘短期过度反应，转债正股多为中小盘 |
# | 纯债溢价率 | 越低越好 | 越低 = 越接近纯债价值，下行保护越强 |
# | 剩余期限 | 剔除 < 1 年 | 太短则期权时间价值快速衰减 |
# | 发行规模 | 剔除 < 1 亿 | 余额太小流动性差，散户进出困难 |
#
# ### 不做的事
# - 不做信用风险模型（可转债历史零违约；低于面值时 YTM 会自行补偿）
# - 不做 delta/gamma 复杂定价（不是做市商，截面排名就够了）
# - 不优化权重（已证 IS/OOS -0.815，等权是最强防御）
#
# ---
#
# ## 测试集能检测什么
#
# 48 个月训练 + 43 个月测试 → 夏普标准误 ≈ 0.59。
# 与 ETF 策略一样：**只能检测灾难性失败，不能确认策略有效。**
# 真正的验证是前向模拟盘。
#

# %%
from jqdata import *
import numpy as np
import pandas as pd
import pickle, os, warnings
from datetime import date
from collections import OrderedDict
import matplotlib
import matplotlib.pyplot as plt
%matplotlib inline

warnings.filterwarnings('ignore')
pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 60)

# ==================== 数据边界 ====================
FETCH_PRICE_START = '2018-09-13'  # CONBOND_DAILY_PRICE 最早日期
TRAIN_END = '2022-12-31'          # ⛔ 硬边界
MOM_LOOKBACK = 60                 # 动量回看所需交易日(约3个月)
# =================================================

CACHE = 'cb_cache_train'
if not os.path.exists(CACHE):
    os.makedirs(CACHE)

assert TRAIN_END == '2022-12-31', \
    '数据边界被修改。若确实要越界，必须先声明测试集作废。'

def cache(name, fn):
    p = os.path.join(CACHE, name + '.pkl')
    if os.path.exists(p):
        with open(p, 'rb') as f:
            print('[cache hit ] %s' % name)
            return pickle.load(f)
    o = fn()
    with open(p, 'wb') as f:
        pickle.dump(o, f)
    print('[cache save] %s' % name)
    return o


# %% [markdown]
# ## 1. 获取可转债基本信息
#
# 从 `bond.CONBOND_BASIC_INFO` 获取所有可转债列表，
# 提取：代码、正股代码、上市日期、到期日、发行规模、转股价。

# %%
def fetch_cb_info():
    """获取所有可转债基本信息，返回 DataFrame。"""
    from jqdata import bond

    df = bond.run_query(query(
        bond.CONBOND_BASIC_INFO.code,
        bond.CONBOND_BASIC_INFO.short_name,
        bond.CONBOND_BASIC_INFO.company_code,
        bond.CONBOND_BASIC_INFO.list_date,
        bond.CONBOND_BASIC_INFO.maturity_date,
        bond.CONBOND_BASIC_INFO.convert_price,
        bond.CONBOND_BASIC_INFO.actual_raise_fund,
        bond.CONBOND_BASIC_INFO.exchange_code,
    ))
    print('全量可转债: %d 只' % len(df))

    # 构建带后缀的代码
    xchg_map = {705001: 'XSHG', 705002: 'XSHE', 705003: 'XSHE',
                705004: 'XSHE', 705005: 'XSHG', 705006: 'XSHE'}
    df['suffix'] = df['exchange_code'].map(xchg_map).fillna('XSHE')
    df['cb_code'] = df['code'].astype(str) + '.' + df['suffix']

    # 过滤: 有正股代码、有上市日期、有到期日
    df = df[df['company_code'].notna() & df['list_date'].notna() & df['maturity_date'].notna()]
    df['list_date'] = pd.to_datetime(df['list_date'])
    df['maturity_date'] = pd.to_datetime(df['maturity_date'])

    print('有效(有正股/上市日/到期日): %d 只' % len(df))
    print('上市日期范围: %s ~ %s' % (df['list_date'].min().date(), df['list_date'].max().date()))
    print('到期日期范围: %s ~ %s' % (df['maturity_date'].min().date(), df['maturity_date'].max().date()))

    return df

cb_info = cache('cb_basic_info', fetch_cb_info)
print('列:', list(cb_info.columns))

# 看看正股代码格式
print('\n正股代码示例:')
print(cb_info[['code', 'short_name', 'company_code', 'cb_code', 'list_date', 'maturity_date']].head(10))


# %% [markdown]
# ## 2. 获取可转债日行情
#
# 用 `get_price()` 批量获取所有可转债的日线收盘价和成交量。
# 这比 `bond.run_query` 逐批查询高效得多，且没有 5000 行限制。

# %%
def fetch_cb_prices():
    """用 bond.run_query 获取所有可转债日线收盘价(CONBOND_DAILY_PRICE 表)。"""
    from jqdata import bond

    # 分批: 每批约10个交易日，400只CB × 10天 ≈ 4000行 < 5000限制
    all_dates = sorted(set(
        get_trade_days(start_date=FETCH_PRICE_START, end_date=TRAIN_END)
    ))
    all_dates = pd.to_datetime(all_dates)
    print('总交易日: %d' % len(all_dates))

    batch_days = 10
    frames = []
    for i in range(0, len(all_dates), batch_days):
        batch = all_dates[i:i + batch_days]
        d0 = batch[0].strftime('%Y-%m-%d')
        d1 = batch[-1].strftime('%Y-%m-%d')
        try:
            df = bond.run_query(query(
                bond.CONBOND_DAILY_PRICE.date,
                bond.CONBOND_DAILY_PRICE.code,
                bond.CONBOND_DAILY_PRICE.close,
            ).filter(
                bond.CONBOND_DAILY_PRICE.date >= d0,
                bond.CONBOND_DAILY_PRICE.date <= d1,
            ))
            if df is not None and len(df) > 0:
                frames.append(df)
        except Exception as e:
            print('  %s~%s 失败: %s' % (d0, d1, str(e)[:80]))

    if not frames:
        raise RuntimeError('未获取到任何可转债价格数据')

    raw = pd.concat(frames, ignore_index=True)
    raw['date'] = pd.to_datetime(raw['date'])

    # 构建带后缀代码的映射
    code_to_suffix = cb_info.set_index('code')['suffix'].to_dict()
    raw['cb_code'] = raw['code'].astype(str).map(
        lambda c: str(c) + '.' + code_to_suffix.get(str(c), 'XSHE'))

    # 透视: date × cb_code
    prices = raw.pivot_table(values='close', index='date', columns='cb_code', aggfunc='last')
    prices = prices.sort_index()
    print('价格面板: %d 交易日 × %d 可转债' % (len(prices), len(prices.columns)))
    print('日期范围: %s ~ %s' % (prices.index[0].date(), prices.index[-1].date()))
    return prices

prices = cache('cb_prices', fetch_cb_prices)


# %% [markdown]
# ## 3. 获取转股溢价率
#
# 从 `bond.CONBOND_DAILY_CONVERT` 获取每日转股溢价率和转股价。
# 该表从 2018-09-13 开始有溢价率数据，且有 5000 行/次限制。
# 按月分批查询，只取月末日期（调仓日）。

# %%
def fetch_convert_stats():
    """获取转股溢价率(只取月末附近日期，减少数据量)。"""
    from jqdata import bond

    # 先生成所有可能需要的查询日期（每月最后交易日 + 调仓日）
    price_dates = prices.index
    ym = pd.Series(price_dates).dt.strftime('%Y-%m')
    # 每月取最后 3 个交易日（覆盖月末调仓日 + 可能的周频调仓）
    month_ends_list = []
    for _ym, grp in pd.Series(price_dates).groupby(ym):
        month_ends_list.extend(grp.iloc[-3:].tolist())
    month_ends = sorted(set(month_ends_list))
    month_ends = pd.to_datetime(month_ends)
    print('需要查询的交易日数: %d' % len(month_ends))

    # 按小批日期查询（每月转债数 × 天数可能超5000行限制，分批）
    date_batches = [month_ends[i:i+5] for i in range(0, len(month_ends), 5)]
    print('需要查询的交易日数: %d  分 %d 批' % (len(month_ends), len(date_batches)))

    frames = []
    for batch_dates in date_batches:
        d0 = batch_dates[0].strftime('%Y-%m-%d')
        d1 = batch_dates[-1].strftime('%Y-%m-%d')
        try:
            q = query(
                bond.CONBOND_DAILY_CONVERT.date,
                bond.CONBOND_DAILY_CONVERT.code,
                bond.CONBOND_DAILY_CONVERT.convert_price,
                bond.CONBOND_DAILY_CONVERT.convert_premium,
                bond.CONBOND_DAILY_CONVERT.convert_premium_rate,
                bond.CONBOND_DAILY_CONVERT.acc_convert_ratio,
            ).filter(
                bond.CONBOND_DAILY_CONVERT.date >= d0,
                bond.CONBOND_DAILY_CONVERT.date <= d1,
            )
            df = bond.run_query(q)
            if df is not None and len(df) > 0:
                frames.append(df)
        except Exception as e:
            print('  %s~%s 查询失败: %s' % (d0, d1, str(e)[:80]))

    if not frames:
        raise RuntimeError('未获取到任何转股统计数据')

    df = pd.concat(frames, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'])

    # 构建带后缀代码 (从 cb_info 获取映射)
    code_suffix = cb_info.set_index('code')['suffix']
    df['cb_code'] = df['code'].astype(str) + '.' + df['code'].astype(str).map(
        lambda c: code_suffix.get(c, 'XSHE'))

    print('转股统计: %d 行' % len(df))
    print('日期范围: %s ~ %s' % (df['date'].min().date(), df['date'].max().date()))
    print('列:', list(df.columns))
    return df

convert_stats = cache('cb_convert_stats', fetch_convert_stats)

print('\n转股溢价率分布:')
print(convert_stats['convert_premium_rate'].describe())
print('\n转股溢价率缺失: %d / %d (%.1f%%)'
      % (convert_stats['convert_premium_rate'].isna().sum(), len(convert_stats),
         100.0 * convert_stats['convert_premium_rate'].isna().sum() / len(convert_stats)))


# %% [markdown]
# ## 4. 获取正股价格（用于动量因子）

# %%
def fetch_stock_prices():
    """获取所有可转债对应正股的日线收盘价。"""
    stock_codes = sorted(cb_info['company_code'].dropna().unique().tolist())
    print('正股数量: %d' % len(stock_codes))

    batch_size = 100
    frames = []
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        try:
            px = get_price(batch, start_date=FETCH_PRICE_START, end_date=TRAIN_END,
                          frequency='daily', fields=['close'], fq='pre', skip_paused=False)
            if px is not None and len(px) > 0:
                frames.append(px['close'])
        except Exception as e:
            pass

    if not frames:
        raise RuntimeError('未获取到任何正股价格数据')

    sprices = pd.concat(frames, axis=1).sort_index()
    sprices.index = pd.to_datetime(sprices.index)
    print('正股价格面板: %d 交易日 × %d 股票' % (len(sprices), len(sprices.columns)))
    return sprices

stock_prices = cache('stock_prices', fetch_stock_prices)


# %% [markdown]
# ## 5. 构建调仓日期序列 + 策略引擎

# %%
# 月度调仓日期: 每月最后一个交易日
ym_series = pd.Series(prices.index).dt.strftime('%Y-%m')
rebal_dates = pd.Series(prices.index).groupby(ym_series).last().sort_values().tolist()
rebal_dates = pd.to_datetime(rebal_dates)

# 动量回看需要前置数据, 从第3个月开始评估
MIN_IDX = 3
rebal = rebal_dates[MIN_IDX:]
print('调仓期数: %d  (%s ~ %s)'
      % (len(rebal), rebal[0].date(), rebal[-1].date()))

# 构建每期的可转债池: 已上市 + 未到期 + 剩余期限 > 1年
def build_pool_info():
    """返回 dict: {调仓日期: [cb_code列表]}"""
    pool = {}
    cb_info_indexed = cb_info.set_index('cb_code')
    # 调试: 看看第一期的过滤条件
    debug_done = False
    for dt in rebal:
        valid = []
        n_no_info = n_not_listed = n_matured = n_no_price = 0
        for cb in prices.columns:
            if cb not in cb_info_indexed.index:
                n_no_info += 1
                continue
            info = cb_info_indexed.loc[cb]
            list_date = info['list_date']
            mat_date = info['maturity_date']
            if pd.isna(list_date) or pd.isna(mat_date):
                continue
            if list_date > dt:
                n_not_listed += 1
                continue
            if mat_date <= dt + pd.DateOffset(months=12):
                n_matured += 1
                continue
            if dt not in prices.index or pd.isna(prices.loc[dt, cb]) or prices.loc[dt, cb] <= 0:
                n_no_price += 1
                continue
            valid.append(cb)
        pool[dt] = valid
        if not debug_done:
            print('  调试 首期 %s: 总列%d 无info=%d 未上市=%d 临近到期=%d 无价格=%d → 有效=%d'
                  % (dt.date(), len(prices.columns), n_no_info, n_not_listed,
                     n_matured, n_no_price, len(valid)))
            if len(valid) == 0:
                # 看看哪些CB有有效价格
                row = prices.loc[dt].dropna()
                print('    当天有有效价格的CB总数: %d' % len(row))
                if len(row) > 0:
                    print('    有价格的CB样本: %s' % list(row.index[:5]))
                # 看价格面板中非NaN的总列数
                n_notna = prices.notna().sum(axis=0)
                n_has_data = (n_notna > 0).sum()
                print('    价格面板中至少有一个非NaN的CB: %d / %d' % (n_has_data, len(prices.columns)))
                # 看第一天有几个有效价格
                first_day = prices.index[0]
                first_valid = prices.loc[first_day].dropna()
                print('    价格面板首日(%s)有效价格: %d' % (first_day.date(), len(first_valid)))
            debug_done = True
    return pool

pool_map = cache('cb_pool_map', build_pool_info)
pool_sizes = {k.date(): len(v) for k, v in pool_map.items()}
print('每期可转债数量: min=%d max=%d median=%d'
      % (min(pool_sizes.values()), max(pool_sizes.values()),
         int(np.median(list(pool_sizes.values())))))


# %% [markdown]
# ## 6. 因子计算引擎
#
# 每次调仓时计算所有可转债的因子值。

# %%
def compute_factors(dt):
    """在给定调仓日期计算所有候选可转债的因子值。
    返回 DataFrame, index=cb_code, columns=各因子。
    """
    candidates = pool_map.get(dt, [])
    if len(candidates) < 20:
        return None

    # 当天转债价格
    cb_close = prices.loc[dt, candidates].dropna()
    if len(cb_close) < 20:
        return None

    # 转股溢价率 —— 从 convert_stats 获取当天的数据
    day_conv = convert_stats[convert_stats['date'] == dt].set_index('cb_code')
    premium_col = 'convert_premium_rate'

    # 正股价格
    # 找到每个转债对应的正股代码
    cb_to_stock = cb_info.set_index('cb_code')['company_code']
    stock_codes_needed = [cb_to_stock.get(c) for c in cb_close.index]
    stock_codes_needed = [s for s in stock_codes_needed if pd.notna(s)]

    # 正股当日收盘价
    stock_close = pd.Series(index=cb_close.index, dtype=float)
    for cb_code in cb_close.index:
        stk = cb_to_stock.get(cb_code)
        if pd.isna(stk) or stk not in stock_prices.columns:
            continue
        if dt in stock_prices.index and not pd.isna(stock_prices.loc[dt, stk]):
            stock_close[cb_code] = stock_prices.loc[dt, stk]

    # 正股动量因子需要回溯
    stock_mom_1m = pd.Series(np.nan, index=cb_close.index)
    stock_rev_3m = pd.Series(np.nan, index=cb_close.index)

    # 找1个月前和3个月前的交易日（用股票价格面板的索引，可能与转债面板不同）
    try:
        dt_idx = stock_prices.index.get_loc(dt)
    except KeyError:
        mask = stock_prices.index <= dt
        dt_idx = mask.sum() - 1 if mask.any() else 0

    if dt_idx >= 63:  # 有足够历史数据才计算动量
        lookback_1m = dt_idx - 21
        dt_1m = stock_prices.index[lookback_1m]
        lookback_3m = dt_idx - 63
        dt_3m = stock_prices.index[lookback_3m]

        for cb_code in cb_close.index:
            stk = cb_to_stock.get(cb_code)
            if pd.isna(stk) or stk not in stock_prices.columns:
                continue
            try:
                p_now = stock_prices.loc[dt, stk]
                p_1m = stock_prices.loc[dt_1m, stk]
                p_3m = stock_prices.loc[dt_3m, stk]
                if p_now > 0 and p_1m > 0 and p_3m > 0:
                    stock_mom_1m[cb_code] = p_now / p_1m - 1
                    stock_rev_3m[cb_code] = -(p_now / p_3m - 1)  # 反转: 取负号
            except (KeyError, IndexError):
                pass

    # 组装因子 DataFrame
    factors = pd.DataFrame({
        'price': cb_close,                              # 转债价格(越低越好)
        'premium': day_conv[premium_col].reindex(cb_close.index),  # 转股溢价率(越低越好)
        'mom_1m': stock_mom_1m,                        # 正股1月动量(越高越好)
        'rev_3m': stock_rev_3m,                        # 正股3月反转(越高越好)
    })

    # 纯债溢价率近似: (转债价格 - 100) / 100 (简化; 真正的纯债价值需要YTM计算)
    # 用价格本身已经捕获了大部分债底接近程度
    # 补充: 发行规模因子
    issue_size = cb_info.set_index('cb_code')['actual_raise_fund'].reindex(cb_close.index)
    factors['size'] = issue_size.fillna(issue_size.median())

    return factors


# %% [markdown]
# ## 7. 策略引擎
#
# - 每个因子 z-score 标准化（处理方向后等权加总）
# - 选前 N 只，等权
# - 月频调仓
# - 成本: 往返 0.17%（万0.85 × 2 + 无印花税 + 价差 0.05% × 2）

# %%
COST_RT = 0.0017  # 可转债往返成本
HAS_DATA = False   # 在 cell 10 执行成功后设为 True

# 因子方向和权重（先验固定，不优化）
# positive=True 表示因子值越高得分越高
FACTOR_CONFIG = OrderedDict([
    ('price',   {'direction': -1, 'weight': 0.35}),   # 越低越好, 权重35%
    ('premium', {'direction': -1, 'weight': 0.35}),   # 越低越好, 权重35%
    ('mom_1m',  {'direction':  1, 'weight': 0.15}),   # 越高越好, 权重15%
    ('rev_3m',  {'direction':  1, 'weight': 0.15}),   # 越高越好, 权重15%
])

def zscore(s):
    """截面 z-score，处理全同值情况。"""
    s = s.dropna()
    if len(s) < 5:
        return pd.Series(np.nan, index=s.index)
    sd = s.std()
    if not sd or np.isnan(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def score_candidates(dt):
    """给当天所有可转债打分。返回按得分降序排列的 Series。"""
    f = compute_factors(dt)
    if f is None or len(f) < 20:
        return None

    total = None
    for factor_name, cfg in FACTOR_CONFIG.items():
        if factor_name not in f.columns:
            continue
        z = zscore(f[factor_name])
        if len(z.dropna()) < 10:
            continue
        weighted = z * cfg['direction'] * cfg['weight']
        if total is None:
            total = weighted
        else:
            total = total.add(weighted, fill_value=0)

    if total is None or total.dropna().empty:
        return None
    return total.dropna().sort_values(ascending=False)


def run_strategy(N=20, cost_rt=COST_RT, score_fn=score_candidates):
    """运行策略，返回月收益序列、换手序列、持仓历史。"""
    rets, turns, hist = {}, {}, {}
    held = set()

    for i in range(len(rebal) - 1):
        t0, t1 = rebal[i], rebal[i + 1]
        scores = score_fn(t0)
        if scores is None or len(scores) < N:
            continue

        picks = list(scores.index[:N])
        new_set = set(picks)

        # 换手: 新入 / 持仓数
        turnover = len(new_set - held) / float(N) if N > 0 else 0

        # 等权收益 = 各标的下一期收益的平均
        w = 1.0 / N
        r_sum = 0.0
        valid_n = 0
        for cb in picks:
            try:
                if cb in prices.columns and t0 in prices.index and t1 in prices.index:
                    p0 = prices.loc[t0, cb]
                    p1 = prices.loc[t1, cb]
                    if not pd.isna(p0) and not pd.isna(p1) and p0 > 0:
                        r_sum += (p1 / p0 - 1) * w
                        valid_n += 1
            except (KeyError, IndexError):
                pass

        if valid_n < N * 0.5:  # 有效标的太少，跳过
            continue

        # 成本 = 换手 × 往返成本率
        rets[t0.date()] = r_sum - turnover * cost_rt
        turns[t0.date()] = turnover
        hist[t0.date()] = picks
        held = new_set

    return pd.Series(rets).sort_index(), pd.Series(turns).sort_index(), hist


# %% [markdown]
# ## 8. 业绩评估指标

# %%
def maxdd(nav):
    return float((nav / nav.cummax() - 1).min())

def perf(r, label=''):
    n = len(r)
    if n < 12:
        return None
    nav = (1 + r).cumprod()
    return OrderedDict([
        ('strategy', label), ('n_m', n),
        ('ann_ret', round(nav.iloc[-1] ** (12.0 / n) - 1, 4)),
        ('vol', round(r.std() * np.sqrt(12), 4)),
        ('sharpe', round(r.mean() / r.std() * np.sqrt(12), 2) if r.std() else np.nan),
        ('maxdd', round(maxdd(nav), 4)),
        ('win_m', round((r > 0).mean(), 3)),
        ('worst_m', round(r.min(), 4)),
        ('avg_turn', round(turns.reindex(r.index).fillna(0).mean(), 3) if 'turns' in globals() else np.nan),
    ])


# %% [markdown]
# ## 9. 先验固定参数 N=20 + 参数敏感性

# %%
# 先运行几个 N 值看敏感性
GRID_N = [10, 15, 20, 25, 30]
store_results = {}
rows_grid = []

for N in GRID_N:
    r, tn, hist = run_strategy(N=N)
    if r is None or len(r) < 24:
        print('N=%d: 数据不足' % N)
        continue
    store_results[N] = (r, tn, hist)

    # 训练集内分两段看稳定性
    SPLIT = date(2021, 1, 1)
    r1 = r[[d for d in r.index if d < SPLIT]]
    r2 = r[[d for d in r.index if d >= SPLIT]]

    p_all = perf(r, 'N=%d' % N)
    p1 = perf(r1, '') if len(r1) >= 12 else {}
    p2 = perf(r2, '') if len(r2) >= 12 else {}

    rows_grid.append(OrderedDict([
        ('config', 'N=%d' % N),
        ('ann_ret', p_all['ann_ret']),
        ('sharpe', p_all['sharpe']),
        ('maxdd', p_all['maxdd']),
        ('前段sharpe', p1.get('sharpe', np.nan)),
        ('后段sharpe', p2.get('sharpe', np.nan)),
        ('worst_m', p_all['worst_m']),
        ('win_m', p_all['win_m']),
        ('avg_turn', round(tn.mean(), 3)),
    ]))

grid = pd.DataFrame(rows_grid)
print('=' * 100)
print('参数敏感性 [训练集 %s ~ %s]' % (rebal[0].date(), rebal[-1].date()))
print('=' * 100)

if grid.empty:
    print('⚠️ 所有 N 值均未产生 >= 24 个月的收益序列！')
    print('   诊断信息:')
    print('   调仓期数: %d' % len(rebal))
    # 看第一期的候选数和打分结果
    if len(rebal) > 0:
        test_dt = rebal[0]
        print('   第一期 %s:' % test_dt.date())
        print('   候选可转债数: %d' % len(pool_map.get(test_dt, [])))
        test_scores = score_candidates(test_dt)
        if test_scores is not None:
            print('   有效打分数: %d' % len(test_scores))
            print('   前5名:')
            for cb, sc in test_scores.head(5).items():
                name = cb_info.set_index('cb_code')['short_name'].get(cb, '?')
                print('     %s %s score=%.3f' % (cb, name, sc))
        else:
            print('   score_candidates 返回 None!')
            # 进一步诊断
            f = compute_factors(test_dt)
            if f is None:
                print('   compute_factors 返回 None (候选不足20?)')
            else:
                print('   factors shape:', f.shape, 'columns:', list(f.columns))
                for col in f.columns:
                    print('   %s: 非空%d 中位数%.3f' % (col, f[col].notna().sum(), f[col].median()))
else:
    print(grid.sort_values('sharpe', ascending=False).to_string(index=False))
    if len(grid) >= 3:
        print('\n前后两段夏普排序相关性 %.3f' %
              grid['前段sharpe'].corr(grid['后段sharpe'], method='spearman'))


# %% [markdown]
# ## 10. 先验固定参数 (N=20) 详细分析

# %%
PRIOR_N = 20
r_p, tn_p, hist_p = run_strategy(N=PRIOR_N)

if r_p is None or len(r_p) < 12:
    print('⚠ ===== 策略未产生足够收益数据 (%s 个月) =====' % (len(r_p) if r_p is not None else 0))
    print('可能原因:')
    print('  1. convert_stats 转股溢价率数据为空或日期不匹配')
    print('  2. pool_map 每期候选转债 < 20')
    print('  3. score_candidates 无法计算因子值')
    print('  请查看上一 cell 的诊断输出定位问题。')
else:
    print('=' * 90)
    print('先验固定参数 N=%d  训练集 %s ~ %s'
          % (PRIOR_N, r_p.index[0], r_p.index[-1]))
    print('=' * 90)
    p = perf(r_p, 'CB双低多因子 N=%d' % PRIOR_N)
    for k, v in p.items():
        print('  %-14s %s' % (k, v))

    # 年化换手
    ann_turn = tn_p.mean() * 12
    cost_drag = tn_p.mean() * COST_RT * 12
    print('  年化单边换手  %.0f%%' % (ann_turn * 100))
    print('  成本拖累      %.2f%%/年' % (cost_drag * 100))

    # 每期持仓数
    actual_holdings = [len(v) for v in hist_p.values()]
    print('  平均持仓数    %.1f (目标 %d)' % (np.mean(actual_holdings), PRIOR_N))

    # 被选中次数最多的标的
    cnt = pd.Series([cb for v in hist_p.values() for cb in v]).value_counts()
    print('\n被选中次数最多的前10只可转债:')
    for cb_code, n in cnt.head(10).items():
        name = cb_info.set_index('cb_code').loc[cb_code, 'short_name'] if cb_code in cb_info.set_index('cb_code').index else '?'
        print('  %-16s %-12s %d 次 (%.0f%%)' % (cb_code, name, n, 100.0 * n / len(hist_p)))

HAS_DATA = r_p is not None and len(r_p) >= 12


# %% [markdown]
# ## 11. 因子贡献度分析
#
# 每个因子单独跑，看各自贡献多少夏普和收益。

# %%
if not HAS_DATA:
    print('跳过: 策略无足够数据')
else:
    single_factor_results = []
    for factor_name in FACTOR_CONFIG.keys():
        # 临时改为单因子(权重100%)
        orig = FACTOR_CONFIG.copy()
        # 创建单因子配置
        for k in FACTOR_CONFIG:
            FACTOR_CONFIG[k] = {**FACTOR_CONFIG[k], 'weight': 1.0 if k == factor_name else 0.0}

        r_s, tn_s, _ = run_strategy(N=PRIOR_N)
        if r_s is not None and len(r_s) >= 24:
            p_s = perf(r_s, factor_name)
            single_factor_results.append(OrderedDict([
                ('factor', factor_name),
                ('ann_ret', p_s['ann_ret']),
                ('sharpe', p_s['sharpe']),
                ('maxdd', p_s['maxdd']),
                ('avg_turn', round(tn_s.mean(), 3)),
            ]))

        # 恢复原始配置
        for k in orig:
            FACTOR_CONFIG[k] = orig[k]

    print('=' * 70)
    print('单因子贡献度 (各因子单独跑, N=%d)' % PRIOR_N)
    print('=' * 70)
    print(pd.DataFrame(single_factor_results).to_string(index=False))


# %% [markdown]
# ## 12. 变体对照：经典双低 vs 多因子

# %%
if not HAS_DATA:
    print('跳过: 策略无足够数据')
else:
    # 经典双低: 只取 price + premium 各 50%, 不用动量因子
    orig_config = FACTOR_CONFIG.copy()
    FACTOR_CONFIG['price']   = {'direction': -1, 'weight': 0.50}
    FACTOR_CONFIG['premium'] = {'direction': -1, 'weight': 0.50}
    FACTOR_CONFIG['mom_1m']  = {'direction':  1, 'weight': 0.0}
    FACTOR_CONFIG['rev_3m']  = {'direction':  1, 'weight': 0.0}

    r_classic, tn_classic, _ = run_strategy(N=PRIOR_N)
    p_classic = perf(r_classic, '经典双低') if r_classic is not None else {}

    # 恢复
    for k in orig_config:
        FACTOR_CONFIG[k] = orig_config[k]

    # 零成本对照
    r_nc, _, _ = run_strategy(N=PRIOR_N, cost_rt=0.0)
    p_nc = perf(r_nc, '零成本') if r_nc is not None else {}

    print('=' * 90)
    print('变体对照')
    print('=' * 90)
    comparisons = [p]
    if p_classic:
        comparisons.append(p_classic)
    if p_nc:
        comparisons.append(p_nc)
    for pc in comparisons:
        print('  %-22s  年化%6.2f%%  夏普%6.2f  回撤%6.1f%%  月胜率%4.1f%%'
              % (pc['strategy'], pc['ann_ret'] * 100, pc['sharpe'],
                 pc['maxdd'] * 100, pc['win_m'] * 100))

    if p_classic:
        delta_sharpe = p['sharpe'] - p_classic['sharpe']
        print('\n>>> 多因子 vs 经典双低 夏普差 %+.2f' % delta_sharpe)
        if delta_sharpe > 0:
            print('    动量因子有增量贡献')
        else:
            print('    动量因子无增量(或为负) → 坚持经典双低即可')


# %% [markdown]
# ## 13. 分年度表现

# %%
if not HAS_DATA:
    print('跳过: 策略无足够数据')
else:
    yr = r_p.groupby(pd.Series(r_p.index).apply(lambda x: x.year).values).apply(
        lambda s: (1 + s).prod() - 1)
    print('---- 分年度(%) 训练集 ----')
    print((yr * 100).round(1).to_string())
    print('\n策略为正 %d/%d' % ((yr > 0).sum(), len(yr)))


# %% [markdown]
# ## 14. 图表

# %%
if not HAS_DATA:
    print('跳过: 策略无足够数据')
else:
    fig, axes = plt.subplots(2, 2, figsize=(16, 9))

    # NAV 曲线
    ax = axes[0][0]
    nav_p = (1 + r_p).cumprod()
    ax.plot(nav_p.index, nav_p.values, label='CB多因子 N=%d' % PRIOR_N, lw=2, color='steelblue')
    if r_classic is not None:
        nav_c = (1 + r_classic).cumprod()
        ax.plot(nav_c.index, nav_c.values, label='经典双低', lw=1.2, color='gray', ls='--')
    ax.set_yscale('log')
    ax.set_title('NAV (训练集)')
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)

    # N 敏感性
    ax = axes[0][1]
    for N, (r_s, _, _) in store_results.items():
        nav_s = (1 + r_s).cumprod()
        alpha = 1.0 if N == PRIOR_N else 0.4
        lw = 2 if N == PRIOR_N else 0.8
        ax.plot(nav_s.index, nav_s.values, label='N=%d' % N, lw=lw, alpha=alpha)
    ax.set_yscale('log')
    ax.set_title('持仓数敏感性')
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)

    # 回撤
    ax = axes[1][0]
    dd = (nav_p / nav_p.cummax() - 1) * 100
    ax.fill_between(dd.index, dd.values, 0, color='r', alpha=.4)
    ax.set_title('回撤 %')
    ax.grid(alpha=.3)

    # 分年度
    ax = axes[1][1]
    x = np.arange(len(yr))
    colors = ['steelblue' if v > 0 else 'tomato' for v in yr.values]
    ax.bar(x, yr.values * 100, color=colors)
    ax.set_xticks(x)
    ax.set_xticklabels(yr.index, rotation=45)
    ax.axhline(0, color='k', lw=.8)
    ax.set_title('年度收益 %')
    ax.grid(alpha=.3)

    plt.tight_layout()
    plt.savefig('cb_multifactor_train.png', dpi=110)
    grid.to_csv('cb_grid_train.csv', index=False, encoding='utf-8-sig')
    print('已导出 cb_multifactor_train.png / cb_grid_train.csv')
    plt.show()


# %% [markdown]
# ## 训练集小结
#
# 训练集只用于理解策略特性，不用于参数选择。
# 最终配置将采用先验固定值（双低为主 + 动量辅助），
# 然后冻结全部参数，创建独立 notebook 跑测试集 2023-01~2026-07。

# %%
if not HAS_DATA:
    print('跳过: 策略无足够数据')
else:
    print('\n' + '=' * 70)
    print('训练集小结 — 这不是验证结果')
    print('=' * 70)
    print('策略: 可转债双低+动量多因子  持仓 %d 只  月频调仓' % PRIOR_N)
    print('训练集: %s ~ %s  (%d个月)'
          % (r_p.index[0], r_p.index[-1], len(r_p)))
    print()
    print('年化 %.2f%%  夏普 %.2f  最大回撤 %.1f%%  月胜率 %.1f%%'
          % (p['ann_ret'] * 100, p['sharpe'], p['maxdd'] * 100, p['win_m'] * 100))
    print('年化换手 %.0f%%  成本拖累 %.2f%%/年'
          % (ann_turn * 100, cost_drag * 100))
    if p_classic:
        print('vs 经典双低: 夏普差 %+.2f' % (p['sharpe'] - p_classic['sharpe']))
    print()
    if not grid.empty:
        print('N敏感性: 中位夏普 %.2f' % grid['sharpe'].median())
        if len(grid) >= 3:
            print('前后段夏普排序相关性 %.3f (接近0或负 → 参数选择本身不稳定)'
                  % grid['前段sharpe'].corr(grid['后段sharpe'], method='spearman'))
    print()
    print('下一步: 把参数写入冻结规格, 然后创建 holdout notebook 跑 2023-01~2026-07。')
    print('测试集只能看一次。')
