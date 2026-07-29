# -*- coding: utf-8 -*-
"""
Engine 3: 红利ETF 静态持有 (515180 红利ETF易方达)
==================================================
30% 仓位，始终持有，季度再平衡。
不选股、不择时、不切换。唯一作用是持续吃分红。

监控：与 Engine 1/2 一致的死亡条件体系。
"""

from jqdata import *
import numpy as np
import datetime


def initialize(context):
    set_benchmark('000852.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # ETF 费率和实际账户一致: 佣金万0.85免5, 无印花税
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0,
        open_commission=0.000085, close_commission=0.000085,
        close_today_commission=0, min_commission=0
    ), type='fund')

    # ---- 参数 ----
    g.etf_code = '515180.XSHG'
    g.target_weight = 0.30          # 目标仓位

    # 再平衡: 季度末（3/6/9/12 月最后交易日）
    g.rebalance_months = [3, 6, 9, 12]

    # ---- 监控 ----
    g.nav_peak = 0
    g.monthly_nav = []
    g.day_count = 0

    # 先买入初始仓位
    run_daily(initial_buy, time='14:50')

    # 日常 + 季度再平衡
    run_daily(daily_check, time='14:50')


def is_quarter_end(context):
    """本月最后交易日且月份在 3/6/9/12。"""
    today = context.current_dt.date()
    if today.month not in g.rebalance_months:
        return False
    if today.month == 12:
        nxt = datetime.date(today.year + 1, 1, 1)
    else:
        nxt = datetime.date(today.year, today.month + 1, 1)
    last_day = nxt - datetime.timedelta(days=1)
    remain = get_trade_days(start_date=today, end_date=last_day)
    return len(remain) <= 1


def do_rebalance(context):
    """按目标权重调整 515180 仓位。"""
    total = context.portfolio.total_value
    target_value = total * g.target_weight

    pos = context.portfolio.positions.get(g.etf_code)
    current_value = pos.value if pos is not None else 0

    if abs(current_value - target_value) / total < 0.02:
        return  # 偏离不到2%，不调

    order_target_value(g.etf_code, target_value)


def daily_check(context):
    g.day_count += 1

    # 首日建仓
    if g.day_count == 1:
        return  # 由 initial_buy 处理

    # 季度再平衡
    if is_quarter_end(context):
        do_rebalance(context)


def initial_buy(context):
    """首次买入，只执行一次。"""
    if g.day_count > 0:
        return  # 不是第一天
    g.day_count = 1

    total = context.portfolio.total_value
    target_value = total * g.target_weight
    order_target_value(g.etf_code, target_value)
    log.info('初始建仓 %s: %.0f元 (%.0f%%)' % (g.etf_code, target_value, g.target_weight * 100))


# ============================================================
# 监控与死亡条件
# ============================================================
# 与 Engine 1/2 一致:
#   回撤 > 30% → 告警
#   滚动24个月绝对收益 < 现金 → 告警
#   滚动36个月绝对收益 < 现金 → 建议停用
# 全部为告警+人工复核，不做自动清仓。

def monthly_report(context):
    """月末输出监控指标。"""
    total = context.portfolio.total_value
    g.nav_peak = max(g.nav_peak, total)
    drawdown = total / g.nav_peak - 1 if g.nav_peak else 0

    bench_px = attribute_history('000852.XSHG', 1, '1d', ['close'])['close'].iloc[-1]
    g.monthly_nav.append((context.current_dt.date(), total, bench_px))

    pos = context.portfolio.positions.get(g.etf_code)
    etf_weight = pos.value / total * 100 if pos is not None else 0

    log.info('=' * 50)
    log.info('[Engine 3] 月报 | 总资产 %.0f | 515180 %.0f%% | 回撤 %.1f%%'
             % (total, etf_weight, drawdown * 100))

    # 死亡条件
    risk_free = 0.02
    for months, level in [(24, '告警'), (36, '建议停用')]:
        if len(g.monthly_nav) > months:
            n0 = g.monthly_nav[-months - 1][1]
            ret = total / n0 - 1
            cash_ret = (1 + risk_free) ** (months / 12.0) - 1
            if ret < cash_ret:
                log.warn('[死亡条件-%s] 滚动%d个月绝对收益 %.2f%% < 现金 %.2f%%'
                         % (level, months, ret * 100, cash_ret * 100))

    if drawdown < -0.30:
        log.warn('[死亡条件-告警] 回撤 %.1f%% 已超 30%%, 请人工复核'
                 % (drawdown * 100))
    log.info('=' * 50)


# 月末报告
def after_trading_end(context):
    """收盘后运行，用于月末报告。"""
    today = context.current_dt.date()
    if today.month == 12:
        nxt = datetime.date(today.year + 1, 1, 1)
    else:
        nxt = datetime.date(today.year, today.month + 1, 1)
    last_day = nxt - datetime.timedelta(days=1)
    remain = get_trade_days(start_date=today, end_date=last_day)
    if len(remain) <= 1:
        monthly_report(context)
