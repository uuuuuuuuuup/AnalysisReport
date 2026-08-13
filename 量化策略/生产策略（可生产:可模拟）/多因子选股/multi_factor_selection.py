# -*- coding: utf-8 -*-
# ============================================================
# 中证800 价值质量多因子选股 (BP + ROE, 月频)
# ============================================================
# 设计依据: 训练集 2015-01 ~ 2021-12 共84个月
#   BP+ROE: 年化 13.1%  超额 8.4%  夏普 0.50  最大回撤 -35.0%
#   月度胜率 57%  月均双边换手 63%
#
# 同窗口对照:
#   全5因子: 年化 7.4%  超额 2.7%  夏普 0.32  回撤 -55.4%
#   4因子:   年化11.2%  超额 6.5%  夏普 0.47  回撤 -39.8%
#
# 逻辑:
#   1. 每月第一个交易日10:00调仓, 信号只使用前一交易日数据
#   2. 池为中证800历史成分股, 剔除ST/停牌/上市<120日
#   3. BP与ROE分别做MAD去极值、行业+市值中性化、z-score
#   4. 综合得分 = 0.5*z(BP残差) + 0.5*z(ROE残差)
#   5. 选前30只等权持有
#
# 关键设计决策(有训练数据依据, 勿随意改动):
#   - 只保留BP+ROE: 加入低波/动量/低换手后收益下降、回撤和换手上升
#   - 50/50等权: 不根据训练期强弱优化权重, 防止样本内过拟合
#   - 不做40日动量硬排除: 本次中证800研究未验证该规则
#   - 无止损/无MA择时/无排名缓冲: 月频硬重排承担退出职责
#   - 10万账户一手买不起的高价股按排名顺延, 避免系统性高价偏差
#
# ⚠️ 训练集隐忧(实盘时需知):
#   - 夏普仅0.50, 历史最大回撤约35%, 不是低回撤策略
#   - 2022-2026单因子IC已被查看, 完整组合属于弱样本外检验
#   - 真正验证依赖后续模拟盘与小账户前向记录
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd


def initialize(context):
    g.index_code = '000906.XSHG'
    set_benchmark(g.index_code)
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.000085, close_commission=0.000085,
        close_today_commission=0, min_commission=0
    ), type='stock')

    # ---- 冻结参数 ----
    g.n_hold = 30
    g.min_list_days = 120
    g.winsor_mad = 5
    g.min_factor_count = 100

    # ---- 运行状态 ----
    g.last_rebalance_ym = None
    g.pending_sells = set()
    g.nav_peak = 0
    g.monthly_nav = []             # [(date, 策略总资产, 基准收盘价)]

    # 10:00避开开盘价差最宽时段; 每天调用以重试卖单
    run_daily(daily_process, time='10:00')
    run_monthly(monthly_report, monthday=1, time='14:50')


# ============================================================
# 因子处理工具
# ============================================================

def winsorize_mad(s, scale):
    """MAD去极值: median ± scale×1.4826×MAD。"""
    s = s.dropna()
    med = s.median()
    mad = (s - med).abs().median()
    if len(s) == 0 or mad == 0 or np.isnan(mad):
        return s
    limit = scale * 1.4826 * mad
    return s.clip(med - limit, med + limit)


def zscore(s):
    """截面标准化; 常数截面返回0。"""
    s = s.dropna()
    sd = s.std()
    if len(s) == 0 or not sd or np.isnan(sd):
        return s * 0.0
    return (s - s.mean()) / sd


def neutralize(s, industry, ln_mcap):
    """截面回归取残差: factor ~ 行业哑变量 + ln(总市值)。"""
    df = pd.concat([
        s.rename('factor'), industry.rename('industry'),
        ln_mcap.rename('ln_mcap')
    ], axis=1).dropna()
    if len(df) < 3 or df['industry'].nunique() < 2:
        return pd.Series(np.nan, index=s.index)

    dummies = pd.get_dummies(df['industry'], drop_first=True).astype(float)
    x = np.column_stack([
        np.ones(len(df)), df['ln_mcap'].values, dummies.values
    ])
    beta, _, _, _ = np.linalg.lstsq(x, df['factor'].values, rcond=-1)
    residual = df['factor'].values - x.dot(beta)
    return pd.Series(residual, index=df.index).reindex(s.index)


def score_factors(raw, mad_scale):
    """按冻结管线处理BP和ROE并等权合成。"""
    required = ['bp', 'roe', 'ln_mcap', 'industry']
    cross = raw[required].dropna()
    if len(cross) == 0:
        return pd.Series(dtype=float)

    factors = []
    for column in ['bp', 'roe']:
        clipped = winsorize_mad(cross[column], mad_scale)
        residual = neutralize(
            clipped, cross.loc[clipped.index, 'industry'],
            cross.loc[clipped.index, 'ln_mcap']
        ).dropna()
        factors.append(zscore(residual))

    common = factors[0].index.intersection(factors[1].index)
    return (factors[0].loc[common] + factors[1].loc[common]) / 2.0


def pick_affordable_targets(ranked, prices, target_value, n_hold):
    """按排名挑选一手可买的前n_hold只。"""
    targets = []
    for stock in ranked:
        price = prices.get(stock)
        if price is None or not np.isfinite(price) or price <= 0:
            continue
        if price * 100 > target_value:
            continue
        targets.append(stock)
        if len(targets) >= n_hold:
            break
    return targets


# ============================================================
# 股票池与选股
# ============================================================

def market_item(current_data, stock):
    """兼容聚宽CurrentData容器，缺少标的时返回None。"""
    try:
        return current_data[stock]
    except (KeyError, TypeError):
        return None


def is_eligible(stock, current_data, current_date):
    """基础池过滤; 涨停仅限制新买入，在目标选择阶段处理。"""
    item = market_item(current_data, stock)
    if item is None:
        return False
    if item.paused or item.is_st or 'ST' in item.name:
        return False
    info = get_security_info(stock)
    if info is None:
        return False
    return (current_date - info.start_date).days >= g.min_list_days


def select_stocks(context):
    """返回按综合得分降序排列的候选股票; 数据异常返回None。"""
    signal_date = context.previous_date
    current_date = context.current_dt.date()
    current_data = get_current_data()

    pool = get_index_stocks(g.index_code, date=signal_date)
    pool = [s for s in pool if is_eligible(s, current_data, current_date)]
    if len(pool) < g.min_factor_count:
        log.warn('可用中证800成分股仅%d只, 本月不调仓' % len(pool))
        return None

    fundamentals = get_fundamentals(
        query(valuation.code, valuation.pb_ratio, valuation.market_cap,
              indicator.roe).filter(valuation.code.in_(pool)),
        date=signal_date
    )
    if fundamentals is None or fundamentals.empty:
        log.warn('基本面数据为空, 本月不调仓')
        return None

    fundamentals = fundamentals.set_index('code')
    pb = fundamentals['pb_ratio'].where(fundamentals['pb_ratio'] > 0)
    market_cap = fundamentals['market_cap'].where(
        fundamentals['market_cap'] > 0)
    raw = pd.DataFrame({
        'bp': 1.0 / pb,
        'roe': fundamentals['roe'],
        'ln_mcap': np.log(market_cap),
    }).dropna()
    if len(raw) < g.min_factor_count:
        log.warn('有效基本面数据仅%d只, 本月不调仓' % len(raw))
        return None

    industry_info = get_industry(list(raw.index), date=signal_date)
    raw['industry'] = pd.Series({
        code: values.get('sw_l1', {}).get('industry_code')
        for code, values in industry_info.items()
    }).reindex(raw.index)
    raw = raw.dropna(subset=['industry'])

    score = score_factors(raw, g.winsor_mad).dropna()
    if len(score) < g.min_factor_count:
        log.warn('因子处理后仅%d只, 本月不调仓' % len(score))
        return None

    ranked = list(score.sort_values(ascending=False).index)
    top = ranked[:5]
    log.info('价值质量选股 | 股票池%d | 有效%d | 前5: %s'
             % (len(pool), len(ranked), ','.join(top)))
    return ranked


# ============================================================
# 调仓执行
# ============================================================

def flush_pending_sells(context):
    """每日重试停牌或跌停导致的卖出失败。"""
    if not g.pending_sells:
        return
    done = set()
    for stock in list(g.pending_sells):
        position = context.portfolio.positions.get(stock)
        if position is None or position.total_amount == 0:
            done.add(stock)
            continue
        order_target_value(stock, 0)
        position = context.portfolio.positions.get(stock)
        if position is None or position.total_amount == 0:
            done.add(stock)
    g.pending_sells -= done
    if g.pending_sells:
        log.info('待卖出未成交%d只, 次日继续重试' % len(g.pending_sells))


def place_buys(context, targets, scale):
    target_value = context.portfolio.total_value * scale / float(g.n_hold)
    for stock in targets:
        order_target_value(stock, target_value)


def rebalance(context, ranked):
    """按排名顺延选30只，先卖后买并有限放大目标值。"""
    total = context.portfolio.total_value
    current_data = get_current_data()
    held = set(context.portfolio.positions.keys())

    # 按最终可能达到的目标值判断一手可买，实际下单从1.0倍逐轮放大到该值。
    max_scale = 1.25
    target_value = total / float(g.n_hold) * max_scale
    prices = {}
    for stock in ranked[:g.n_hold * 3]:
        item = market_item(current_data, stock)
        if item is not None:
            prices[stock] = item.last_price
    affordable = pick_affordable_targets(
        ranked[:g.n_hold * 3], prices, target_value, g.n_hold * 2)

    # 已持仓股票不受涨停限制; 新买入股票涨停时按排名顺延。
    targets = []
    for stock in affordable:
        item = market_item(current_data, stock)
        if item is None:
            continue
        if stock not in held and item.last_price >= item.high_limit:
            continue
        targets.append(stock)
        if len(targets) >= g.n_hold:
            break

    if len(targets) < g.n_hold:
        log.warn('可买目标仅%d只(目标%d), 本月不调仓'
                 % (len(targets), g.n_hold))
        return False

    target_set = set(targets)
    g.pending_sells -= target_set

    to_sell = held - target_set
    sold = 0
    for stock in to_sell:
        order_target_value(stock, 0)
        position = context.portfolio.positions.get(stock)
        if position is None or position.total_amount == 0:
            sold += 1
        else:
            g.pending_sells.add(stock)

    scale = 1.0
    place_buys(context, targets, scale)
    for _ in range(3):
        idle = context.portfolio.available_cash / total if total else 0
        if idle < 0.015:
            break
        scale = min(max_scale, scale + idle * 0.95)
        place_buys(context, targets, scale)

    filled = len([
        stock for stock in targets
        if stock in context.portfolio.positions
        and context.portfolio.positions[stock].total_amount > 0
    ])
    idle_pct = context.portfolio.available_cash / total * 100 if total else 0
    log.info('调仓完成 | 卖出%d/%d(待重试%d) | 建仓%d/%d | '
             '闲置现金%.1f%% | 放大系数%.3f'
             % (sold, len(to_sell), len(g.pending_sells), filled,
                g.n_hold, idle_pct, scale))
    return True


def daily_process(context):
    current_ym = context.current_dt.strftime('%Y-%m')
    if g.last_rebalance_ym == current_ym:
        flush_pending_sells(context)
        return

    # 调仓日先形成新目标，rebalance会先从待卖队列移除重新入选股票。
    ranked = select_stocks(context)
    if ranked is None:
        flush_pending_sells(context)
        return
    if rebalance(context, ranked):
        g.last_rebalance_ym = current_ym


# ============================================================
# 监控与死亡条件
# ============================================================
# 全部为“告警 + 人工复核”，不做自动清仓。

def monthly_report(context):
    total = context.portfolio.total_value
    g.nav_peak = max(g.nav_peak, total)
    drawdown = total / g.nav_peak - 1 if g.nav_peak else 0

    benchmark = attribute_history(
        g.index_code, 1, '1d', ['close'], df=True)['close'].iloc[-1]
    g.monthly_nav.append((context.current_dt.date(), total, benchmark))

    log.info('=' * 62)
    log.info('月报 | 总资产%.0f | 持仓%d/%d | 现金%.0f | 回撤%.1f%%'
             % (total, len(context.portfolio.positions), g.n_hold,
                context.portfolio.available_cash, drawdown * 100))

    for months, level in [(12, '告警'), (24, '建议停用')]:
        if len(g.monthly_nav) > months:
            d0, nav0, benchmark0 = g.monthly_nav[-months - 1]
            d1, nav1, benchmark1 = g.monthly_nav[-1]
            excess = nav1 / nav0 - benchmark1 / benchmark0
            if excess < 0:
                log.warn('[死亡条件-%s] 滚动%d个月超额%.2f%% < 0 (%s~%s)'
                         % (level, months, excess * 100, d0, d1))

    if drawdown < -0.35:
        log.warn('[死亡条件-告警] 回撤%.1f%%达到训练期最差约-35%%, '
                 '请人工复核策略与因子有效性' % (drawdown * 100))
    log.info('=' * 62)
