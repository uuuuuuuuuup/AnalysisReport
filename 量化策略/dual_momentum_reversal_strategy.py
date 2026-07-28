# -*- coding: utf-8 -*-
# ============================================================
# 策略: A+B 组合 — 超跌反转 + 趋势动量 (CSI 1000 Dual-Mode)
# ============================================================
# 核心逻辑:
#   将超跌反转(A)和趋势动量(B)组合在一个账户中,各分配约50%仓位。
#   A在市场恐慌时捕捉超跌反弹,B在市场走强时捕捉趋势延续。
#   两者信号来源不同、市场环境互补,在同一账户中独立运行。
#
# 资金分配:
#   - A: 最多10只,每只约总资产5%,总仓位上限约50%
#   - B: 最多10只(试探5只/正常10只),每只约总资产5%,总仓位上限约50%
#   - 共用同一现金池,按先A后B的顺序执行
#
# A — 超跌反转:
#   大盘条件: 中证1000低于MA60 且 近10日跌幅≥5%
#   买入信号: 10日跌≥15% + 单日跌≥6% + 连续2日缩量<20日均量60%
#   卖出: 止损-5% / 反弹触及MA10/20/60最低值 / 持有20日时间退出
#
# B — 趋势动量:
#   大盘条件: 连续3日站上MA60→试探(5只),连续5日→正常(10只)
#            连续3日跌破MA60→清仓
#   买入信号: 40日收益率排名前20%
#   卖出: 最高价回撤8% / 调仓日排名跌出前50%收为4% / 跌出前20%替换
#        大盘转弱势立即清仓
# ============================================================

from jqdata import *
import numpy as np
import datetime


def initialize(context):
    set_benchmark('000852.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.0003, close_commission=0.0003,
        close_today_commission=0, min_commission=5
    ), type='stock')

    g.index_code = '000852.XSHG'

    # ======== A: 超跌反转参数 ========
    g.A_lookback_days = 10
    g.A_min_drawdown = -0.15
    g.A_single_day_drop = -0.06
    g.A_volume_ma_days = 20
    g.A_volume_shrink_ratio = 0.6
    g.A_volume_shrink_days = 2
    g.A_max_positions = 10
    g.A_single_position_pct = 0.05
    g.A_stop_loss_pct = -0.05
    g.A_time_exit_days = 20
    g.A_index_ma_window = 60
    g.A_index_panic_days = 10
    g.A_index_panic_threshold = -0.05
    g.A_market_was_fearful = None
    g.A_positions_meta = {}

    # ======== B: 趋势动量参数 ========
    g.B_index_ma_window = 60
    g.B_regime_confirm_days = 3
    g.B_full_position_confirm_days = 5
    g.B_momentum_window = 40
    g.B_rebalance_interval = 20
    g.B_max_positions = 10
    g.B_initial_positions = 5
    g.B_single_position_pct = 0.05
    g.B_buy_top_pct = 0.20
    g.B_rank_tighten_pct = 0.50
    g.B_normal_trailing_stop = 0.08
    g.B_tight_trailing_stop = 0.04
    g.B_market_state = None
    g.B_above_ma_days = 0
    g.B_below_ma_days = 0
    g.B_days_since_rebalance = g.B_rebalance_interval
    g.B_positions_meta = {}

    run_daily(daily_process, time='09:35')
    run_monthly(log_portfolio_status, monthday=1, time='15:00')


# ============================================================
# 通用工具
# ============================================================

def current_price(stock):
    return get_current_data()[stock].last_price


def is_tradable(stock, current_data=None):
    if current_data is None:
        current_data = get_current_data()
    data = current_data[stock]
    return (not data.paused and not data.is_st
            and data.last_price > data.low_limit
            and data.last_price < data.high_limit)


def exit_order(context, stock):
    """下单清仓并返回是否已成交。"""
    order_target_value(stock, 0)
    position = context.portfolio.positions.get(stock)
    return position is None or position.value <= 0


# ============================================================
# A: 超跌反转
# ============================================================

def A_is_market_fearful():
    close = attribute_history(g.index_code,
                              g.A_lookback_days + g.A_index_ma_window,
                              '1d', ['close'])['close']
    if len(close) < g.A_index_ma_window:
        return False
    below_ma60 = close.iloc[-1] < close.iloc[-g.A_index_ma_window:].mean()
    if not below_ma60:
        return False
    index_ret = close.iloc[-1] / close.iloc[-g.A_index_panic_days - 1] - 1
    return index_ret <= g.A_index_panic_threshold


def A_check_signal(stock):
    days_needed = g.A_lookback_days + 1 + g.A_volume_ma_days
    df = attribute_history(stock, days_needed, '1d', ['close', 'money'])
    if len(df) < days_needed:
        return False
    close = df['close']
    money = df['money']

    total_ret = close.iloc[-1] / close.iloc[-g.A_lookback_days - 1] - 1
    if total_ret > g.A_min_drawdown:
        return False

    close_window = close.iloc[-(g.A_lookback_days + 1):]
    daily_rets = close_window.pct_change().dropna()
    if not (daily_rets <= g.A_single_day_drop).any():
        return False

    avg_money = money.iloc[-(g.A_volume_ma_days + g.A_volume_shrink_days):-g.A_volume_shrink_days].mean()
    if avg_money <= 0:
        return False
    recent_money = money.iloc[-g.A_volume_shrink_days:]
    if not (recent_money < avg_money * g.A_volume_shrink_ratio).all():
        return False

    return True


def A_lowest_ma(stock):
    close = attribute_history(stock, 60, '1d', ['close'])['close']
    if len(close) < 60:
        return None
    mas = [
        ('MA10', close.iloc[-10:].mean()),
        ('MA20', close.iloc[-20:].mean()),
        ('MA60', close.iloc[-60:].mean()),
    ]
    name, value = min(mas, key=lambda x: x[1])
    return value, name


def A_check_exit(context, stock, meta):
    price = current_price(stock)
    entry_price = meta['entry_price']

    if price <= entry_price * (1 + g.A_stop_loss_pct):
        loss_pct = (price / entry_price - 1) * 100
        return True, 'A止损(亏损%.1f%%)' % loss_pct

    result = A_lowest_ma(stock)
    if result is not None:
        target, ma_name = result
        if price >= target:
            gain_pct = (price / entry_price - 1) * 100
            return True, 'A反弹至%s(%.2f),盈利%.1f%%' % (ma_name, target, gain_pct)

    held_days = len(get_trade_days(
        start_date=meta['entry_date'],
        end_date=context.current_dt.date()
    ))
    if held_days >= g.A_time_exit_days:
        gain_pct = (price / entry_price - 1) * 100
        return True, 'A时间退出(%d天,收益%.1f%%)' % (held_days, gain_pct)

    return False, None


def A_scan_candidates(context):
    index_stocks = get_index_stocks(g.index_code, date=context.current_dt.date())
    candidates = []
    for stock in index_stocks:
        if stock in context.portfolio.positions:
            continue
        if not is_tradable(stock):
            continue
        if A_check_signal(stock):
            close = attribute_history(stock, g.A_lookback_days + 1, '1d', ['close'])['close']
            ret = close.iloc[-1] / close.iloc[-g.A_lookback_days - 1] - 1
            candidates.append((stock, ret))
    candidates.sort(key=lambda x: x[1])
    return candidates


def A_daily(context):
    """A策略每日:检查退出、扫描新信号买入。"""
    # 第一步: 只检查A自己的持仓退出,不碰B的
    for stock in list(g.A_positions_meta.keys()):
        if stock not in context.portfolio.positions:
            g.A_positions_meta.pop(stock, None)
            continue
        meta = g.A_positions_meta[stock]
        should_exit, reason = A_check_exit(context, stock, meta)
        if should_exit:
            if exit_order(context, stock):
                g.A_positions_meta.pop(stock, None)
                log.info('卖出 %-12s | %s' % (stock, reason))
            else:
                log.info('A卖出委托未成交 %s' % stock)

    # 第二步: 开新仓
    a_count = len([s for s in context.portfolio.positions if s in g.A_positions_meta])
    slots = g.A_max_positions - a_count
    if slots <= 0:
        return

    fearful = A_is_market_fearful()
    if fearful != g.A_market_was_fearful:
        log.info('A大盘环境切换: %s' % ('恐慌(允许开仓)' if fearful else '非恐慌'))
        g.A_market_was_fearful = fearful
    if not fearful:
        return

    candidates = A_scan_candidates(context)
    if not candidates:
        return

    total_value = context.portfolio.total_value
    for stock, drawdown in candidates[:slots]:
        target_value = min(
            total_value * g.A_single_position_pct,
            context.portfolio.available_cash
        )
        if target_value <= 0:
            break
        order_value(stock, target_value)
        if (stock in context.portfolio.positions
                and context.portfolio.positions[stock].value > 0):
            g.A_positions_meta[stock] = {
                'entry_price': current_price(stock),
                'entry_date': context.current_dt.date()
            }
            log.info('A买入 %-12s | 10日跌幅 %+.1f%% | 价格 %.2f' % (
                stock, drawdown * 100, current_price(stock)))
        else:
            log.info('A买入委托未成交 %s' % stock)


# ============================================================
# B: 趋势动量
# ============================================================

def B_get_index_closes():
    count = g.B_index_ma_window + g.B_full_position_confirm_days - 1
    return attribute_history(g.index_code, count, '1d', ['close'])['close']


def B_update_market_state():
    close = B_get_index_closes()
    if len(close) < g.B_index_ma_window:
        return g.B_market_state, False

    ma = close.iloc[-g.B_index_ma_window:].mean()
    is_above = close.iloc[-1] > ma
    is_below = close.iloc[-1] < ma
    g.B_above_ma_days = g.B_above_ma_days + 1 if is_above else 0
    g.B_below_ma_days = g.B_below_ma_days + 1 if is_below else 0

    old_state = g.B_market_state
    if g.B_below_ma_days >= g.B_regime_confirm_days:
        g.B_market_state = 'weak'
    elif g.B_above_ma_days >= g.B_full_position_confirm_days:
        g.B_market_state = 'strong'
    elif g.B_above_ma_days >= g.B_regime_confirm_days and old_state != 'strong':
        g.B_market_state = 'watch'

    if g.B_market_state != old_state:
        label = ('B试探仓' if g.B_market_state == 'watch'
                 else 'B正常仓位' if g.B_market_state == 'strong'
                 else 'B弱势' if g.B_market_state == 'weak'
                 else 'B未确认')
        log.info('B大盘状态切换: %s, 收盘 %.2f, MA%d %.2f' % (
            label, close.iloc[-1], g.B_index_ma_window, ma))
        if g.B_market_state in ('watch', 'strong'):
            g.B_days_since_rebalance = g.B_rebalance_interval - 1

    return g.B_market_state, old_state in ('watch', 'strong') and g.B_market_state == 'weak'


def B_momentum_return(stock):
    close = attribute_history(stock, g.B_momentum_window + 1, '1d', ['close'])['close']
    if len(close) < g.B_momentum_window + 1:
        return None
    return close.iloc[-1] / close.iloc[0] - 1


def B_rank_stocks(context):
    stocks = get_index_stocks(g.index_code, date=context.current_dt.date())
    current_data = get_current_data()
    ranked = []
    for stock in stocks:
        if not is_tradable(stock, current_data):
            continue
        ret = B_momentum_return(stock)
        if ret is not None:
            ranked.append((stock, ret))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def B_check_trailing_stops(context):
    for stock in list(context.portfolio.positions):
        if stock not in g.B_positions_meta:
            continue
        price = current_price(stock)
        meta = g.B_positions_meta[stock]
        meta['highest_price'] = max(meta['highest_price'], price)

        stop = g.B_tight_trailing_stop if meta['tight_stop'] else g.B_normal_trailing_stop
        drawdown = 1 - price / meta['highest_price']
        if drawdown >= stop:
            reason = ('B排名跌出前%.0f%%,回撤%.1f%%' % (g.B_rank_tighten_pct * 100, drawdown * 100)
                      if meta['tight_stop']
                      else 'B最高价回撤%.1f%%' % (drawdown * 100))
            if exit_order(context, stock):
                g.B_positions_meta.pop(stock, None)
                log.info('卖出 %-12s | %s' % (stock, reason))
            else:
                log.info('B卖出委托未成交 %s' % stock)


def B_update_rank_stop_state(context, ranked):
    rank_map = {stock: i for i, (stock, _) in enumerate(ranked)}
    rank_cut = max(1, int(len(ranked) * g.B_rank_tighten_pct))
    for stock in list(context.portfolio.positions):
        if stock not in g.B_positions_meta:
            continue
        position_rank = rank_map.get(stock)
        g.B_positions_meta[stock]['tight_stop'] = (
            position_rank is not None and position_rank >= rank_cut
        )


def B_rebalance(context, ranked):
    if not ranked or g.B_market_state not in ('watch', 'strong'):
        return

    B_update_rank_stop_state(context, ranked)
    rank_cut = max(1, int(len(ranked) * g.B_buy_top_pct))
    top_set = {stock for stock, _ in ranked[:rank_cut]}
    total_value = context.portfolio.total_value

    # 卖出跌出前20%的B持仓
    for stock in list(context.portfolio.positions):
        if stock not in g.B_positions_meta:
            continue
        if stock not in top_set:
            if exit_order(context, stock):
                g.B_positions_meta.pop(stock, None)
                log.info('卖出 %-12s | B排名跌出前%.0f%%,替换' % (
                    stock, g.B_buy_top_pct * 100))

    b_count = len([s for s in context.portfolio.positions if s in g.B_positions_meta])
    target_positions = g.B_initial_positions if g.B_market_state == 'watch' else g.B_max_positions
    slots = max(0, target_positions - b_count)
    if slots <= 0:
        return

    candidates = [(stock, ret) for stock, ret in ranked[:rank_cut]
                  if stock not in context.portfolio.positions]
    for stock, ret in candidates[:slots]:
        target_value = min(
            total_value * g.B_single_position_pct,
            context.portfolio.available_cash
        )
        if target_value <= 0:
            break
        order_value(stock, target_value)
        position = context.portfolio.positions.get(stock)
        if position is None or position.value <= 0:
            log.info('B买入委托未成交 %-12s' % stock)
            continue
        price = current_price(stock)
        g.B_positions_meta[stock] = {
            'highest_price': price,
            'tight_stop': False,
        }
        actual_rank = next(i for i, item in enumerate(ranked, start=1)
                           if item[0] == stock)
        log.info('B买入 %-12s | 40日收益率 %+.1f%% | 排名 %d/%d | 价格 %.2f' % (
            stock, ret * 100, actual_rank, len(ranked), price))


def B_daily(context, ranked):
    """B策略每日:检查市场状态、止损、调仓。"""
    state, switched_to_weak = B_update_market_state()

    if switched_to_weak:
        for stock in list(context.portfolio.positions):
            if stock in g.B_positions_meta:
                if exit_order(context, stock):
                    g.B_positions_meta.pop(stock, None)
                    log.info('卖出 %-12s | B大盘连续%d日跌破MA%d' % (
                        stock, g.B_regime_confirm_days, g.B_index_ma_window))
        g.B_days_since_rebalance = 0
        return

    if state not in ('watch', 'strong'):
        return

    B_check_trailing_stops(context)
    g.B_days_since_rebalance += 1
    if g.B_days_since_rebalance < g.B_rebalance_interval:
        return

    B_rebalance(context, ranked)
    g.B_days_since_rebalance = 0


# ============================================================
# 每日主逻辑
# ============================================================

def daily_process(context):
    ranked = B_rank_stocks(context)

    # A先执行,因为A的触发条件更严格(需要恐慌环境),机会更稀缺
    A_daily(context)

    # B后执行,共用剩余现金
    B_daily(context, ranked)


# ============================================================
# 月度报告
# ============================================================

def log_portfolio_status(context):
    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash
    positions = context.portfolio.positions
    cash_pct = cash / total_value * 100 if total_value else 0

    a_stocks = [s for s in positions if s in g.A_positions_meta]
    b_stocks = [s for s in positions if s in g.B_positions_meta]

    fearful = A_is_market_fearful()
    a_regime = '恐慌(可开仓)' if fearful else '非恐慌'
    b_regime = ('试探仓' if g.B_market_state == 'watch'
                else '正常仓位' if g.B_market_state == 'strong'
                else '弱势' if g.B_market_state == 'weak'
                else '未确认')

    log.info('=' * 60)
    log.info('月度快照 | 总资产 %.0f | 现金 %.0f (%.1f%%) | A:%d/%d B:%d/%d' % (
        total_value, cash, cash_pct,
        len(a_stocks), g.A_max_positions,
        len(b_stocks), g.B_max_positions))
    log.info('  A大盘: %s | B大盘: %s' % (a_regime, b_regime))

    if a_stocks:
        log.info('  --- A持仓(超跌反转) ---')
        for stock in a_stocks:
            meta = g.A_positions_meta.get(stock, {})
            entry_price = meta.get('entry_price', 0)
            price = current_price(stock)
            pnl_pct = (price / entry_price - 1) * 100 if entry_price > 0 else 0
            held_days = len(get_trade_days(
                start_date=meta.get('entry_date', context.current_dt.date()),
                end_date=context.current_dt.date()
            )) if isinstance(meta.get('entry_date'), datetime.date) else '?'
            log.info('    %-12s | 买入 %.2f | 现价 %.2f | %+.1f%% | 持%s天' % (
                stock, entry_price, price, pnl_pct, held_days))

    if b_stocks:
        log.info('  --- B持仓(趋势动量) ---')
        for stock in b_stocks:
            meta = g.B_positions_meta.get(stock, {})
            high = meta.get('highest_price', current_price(stock))
            price = current_price(stock)
            drawdown = (1 - price / high) * 100 if high else 0
            log.info('    %-12s | 现价 %.2f | 高点 %.2f | 回撤 %.1f%% | 止损 %s' % (
                stock, price, high, drawdown,
                '4%' if meta.get('tight_stop') else '8%'))

    if not a_stocks and not b_stocks:
        log.info('  当前完全空仓')

    log.info('=' * 60)
