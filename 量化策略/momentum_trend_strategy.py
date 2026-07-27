# -*- coding: utf-8 -*-
# ============================================================
# 策略: 中证1000趋势动量 (CSI 1000 Momentum Trend)
# ============================================================
# 核心逻辑:
#   市场趋势向上时,过去40个交易日表现强的股票更可能继续强势。
#   指数连续3日站上MA60后试探建仓,连续5日站上后补足仓位;
#   指数连续3日跌破MA60时立即清仓。
#
# 买入:
#   - 中证1000成分股内,过去40日收益率排名前20%
#   - 初步确认后买入10只,总仓位约50%;充分确认后补足至20只
#   - 后续每20个交易日调仓,最多持有20只,等权
#
# 卖出:
#   - 持仓后最高价回撤8%
#   - 调仓日跌出可交易成分股收益率前50%后,回撤阈值收紧为4%
#   - 调仓日跌出前20%时卖出,替换为更强的候选
#   - 中证1000连续3日跌破MA60,全部清仓
#
# 暂不使用成交量确认、基本面过滤和组合总回撤保护。
# ============================================================

from jqdata import *


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
    g.index_ma_window = 60
    g.regime_confirm_days = 3
    g.full_position_confirm_days = 5
    g.momentum_window = 40
    g.rebalance_interval = 20
    g.max_positions = 20
    g.initial_positions = 10
    g.single_position_pct = 0.05
    g.buy_top_pct = 0.20
    g.rank_tighten_pct = 0.50
    g.normal_trailing_stop = 0.08
    g.tight_trailing_stop = 0.04

    g.market_state = None       # 'watch' / 'strong' / 'weak'
    g.above_ma_days = 0
    g.below_ma_days = 0
    g.days_since_rebalance = g.rebalance_interval
    # 初步确认后为watch,连续5日站上MA60后为strong
    # {stock: {'highest_price': float, 'tight_stop': bool}}
    g.positions_meta = {}

    run_daily(daily_process, time='09:35')
    run_monthly(log_portfolio_status, monthday=1, time='15:00')


def current_price(stock):
    return get_current_data()[stock].last_price


def is_tradable(stock, current_data=None):
    """过滤停牌、ST、涨跌停无法正常交易的标的。"""
    if current_data is None:
        current_data = get_current_data()
    data = current_data[stock]
    return (not data.paused and not data.is_st
            and data.last_price > data.low_limit
            and data.last_price < data.high_limit)


def get_index_closes():
    """获取指数最近MA窗口加完整确认窗口所需的收盘价。"""
    count = g.index_ma_window + g.full_position_confirm_days - 1
    return attribute_history(g.index_code, count, '1d', ['close'])['close']


def update_market_state():
    """
    用连续3个交易日确认市场状态,避免指数在MA60附近反复开关。
    返回 (当前状态, 是否从已建仓状态切换为弱势)。
    """
    close = get_index_closes()
    if len(close) < g.index_ma_window:
        return g.market_state, False

    ma = close.iloc[-g.index_ma_window:].mean()
    is_above = close.iloc[-1] > ma
    is_below = close.iloc[-1] < ma
    g.above_ma_days = g.above_ma_days + 1 if is_above else 0
    g.below_ma_days = g.below_ma_days + 1 if is_below else 0

    old_state = g.market_state
    if g.below_ma_days >= g.regime_confirm_days:
        g.market_state = 'weak'
    elif g.above_ma_days >= g.full_position_confirm_days:
        g.market_state = 'strong'
    elif g.above_ma_days >= g.regime_confirm_days and old_state != 'strong':
        g.market_state = 'watch'

    if g.market_state != old_state:
        label = ('试探仓(约50%)' if g.market_state == 'watch'
                 else '强势(正常仓位)' if g.market_state == 'strong'
                 else '弱势(清仓)' if g.market_state == 'weak'
                 else '未确认')
        log.info('大盘状态切换: %s, 收盘 %.2f, MA%d %.2f' % (
            label, close.iloc[-1], g.index_ma_window, ma))
        if g.market_state in ('watch', 'strong'):
            g.days_since_rebalance = g.rebalance_interval - 1

    return g.market_state, old_state in ('watch', 'strong') and g.market_state == 'weak'


def momentum_return(stock):
    close = attribute_history(stock, g.momentum_window + 1, '1d', ['close'])['close']
    if len(close) < g.momentum_window + 1:
        return None
    return close.iloc[-1] / close.iloc[0] - 1


def rank_stocks(context):
    """按40日收益率降序返回可交易成分股及排名。"""
    stocks = get_index_stocks(g.index_code, date=context.current_dt.date())
    current_data = get_current_data()
    ranked = []
    for stock in stocks:
        if not is_tradable(stock, current_data):
            continue
        ret = momentum_return(stock)
        if ret is not None:
            ranked.append((stock, ret))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def exit_position(context, stock, reason):
    order_target_value(stock, 0)
    position = context.portfolio.positions.get(stock)
    if position is None or position.value <= 0:
        g.positions_meta.pop(stock, None)
        log.info('卖出 %-12s | %s' % (stock, reason))
        return True
    log.info('卖出委托未成交 %-12s | %s' % (stock, reason))
    return False


def check_trailing_stops(context):
    """每日更新最高价并执行已确认的个股移动止损。"""
    for stock in list(context.portfolio.positions):
        price = current_price(stock)
        meta = g.positions_meta.setdefault(stock, {
            'highest_price': price,
            'tight_stop': False,
        })
        meta['highest_price'] = max(meta['highest_price'], price)

        stop = g.tight_trailing_stop if meta['tight_stop'] else g.normal_trailing_stop
        drawdown = 1 - price / meta['highest_price']
        if drawdown >= stop:
            reason = '排名跌出前%.0f%%,最高价回撤%.1f%%' % (
                g.rank_tighten_pct * 100, drawdown * 100
            ) if meta['tight_stop'] else '最高价回撤%.1f%%' % (drawdown * 100)
            exit_position(context, stock, reason)


def update_rank_stop_state(context, ranked):
    """仅在调仓日根据排名更新持仓的止损档位。"""
    rank_map = {stock: i for i, (stock, _) in enumerate(ranked)}
    rank_cut = max(1, int(len(ranked) * g.rank_tighten_pct))
    for stock in list(context.portfolio.positions):
        meta = g.positions_meta.setdefault(stock, {
            'highest_price': current_price(stock),
            'tight_stop': False,
        })
        position_rank = rank_map.get(stock)
        meta['tight_stop'] = position_rank is not None and position_rank >= rank_cut


def rebalance(context, ranked):
    """调仓日:卖出跌出前20%的持仓,再按动量排名补齐仓位。"""
    if not ranked or g.market_state not in ('watch', 'strong'):
        return

    update_rank_stop_state(context, ranked)
    rank_cut = max(1, int(len(ranked) * g.buy_top_pct))
    top_set = {stock for stock, _ in ranked[:rank_cut]}
    total_value = context.portfolio.total_value

    # 调仓日卖出已跌出前20%的持仓,替换为更强的候选
    for stock in list(context.portfolio.positions):
        if stock not in top_set:
            exit_position(context, stock, '排名跌出前%.0f%%,替换' % (g.buy_top_pct * 100))

    held = set(context.portfolio.positions)
    target_positions = g.initial_positions if g.market_state == 'watch' else g.max_positions
    slots = max(0, target_positions - len(held))
    if slots <= 0:
        return

    candidates = [(stock, ret) for stock, ret in ranked[:rank_cut]
                  if stock not in held]
    for stock, ret in candidates[:slots]:
        target_value = min(
            total_value * g.single_position_pct,
            context.portfolio.available_cash
        )
        if target_value <= 0:
            break
        order_value(stock, target_value)
        position = context.portfolio.positions.get(stock)
        if position is None or position.value <= 0:
            log.info('买入委托未成交 %-12s' % stock)
            continue
        price = current_price(stock)
        g.positions_meta[stock] = {
            'highest_price': price,
            'tight_stop': False,
        }
        actual_rank = next(i for i, item in enumerate(ranked, start=1)
                           if item[0] == stock)
        log.info('买入 %-12s | 40日收益率 %+.1f%% | 排名 %d/%d | 价格 %.2f' % (
            stock, ret * 100, actual_rank, len(ranked), price
        ))


def daily_process(context):
    state, switched_to_weak = update_market_state()
    ranked = rank_stocks(context)

    # 强势转弱势时,先清空全部持仓,不等待个股止损。
    if switched_to_weak:
        for stock in list(context.portfolio.positions):
            exit_position(context, stock, '大盘连续%d日跌破MA%d' % (
                g.regime_confirm_days, g.index_ma_window
            ))
        g.days_since_rebalance = 0
        return

    if state not in ('watch', 'strong'):
        return

    check_trailing_stops(context)
    g.days_since_rebalance += 1
    if g.days_since_rebalance < g.rebalance_interval:
        return

    rebalance(context, ranked)
    g.days_since_rebalance = 0


def log_portfolio_status(context):
    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash
    positions = context.portfolio.positions
    cash_pct = cash / total_value * 100 if total_value else 0
    log.info('=' * 60)
    log.info('月度仓位快照 | 总资产 %.0f | 现金 %.0f (%.1f%%) | 持仓 %d/%d | 大盘 %s' % (
        total_value, cash, cash_pct, len(positions), g.max_positions,
        ('强势(正常仓位)' if g.market_state == 'strong'
         else '试探仓(约50%)' if g.market_state == 'watch'
         else '弱势' if g.market_state == 'weak' else '未确认')
    ))
    for stock, position in positions.items():
        meta = g.positions_meta.get(stock, {})
        high = meta.get('highest_price', current_price(stock))
        drawdown = (1 - current_price(stock) / high) * 100 if high else 0
        log.info('  %-12s | 现价 %.2f | 持仓后高点 %.2f | 回撤 %.1f%% | 止损 %s' % (
            stock, current_price(stock), high, drawdown,
            '4%' if meta.get('tight_stop') else '8%'
        ))
    log.info('=' * 60)
