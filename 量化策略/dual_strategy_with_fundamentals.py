# -*- coding: utf-8 -*-
# ============================================================
# 策略: A+B 组合 — 超跌反转 + 趋势动量 (CSI 1000 Dual-Mode)
# ============================================================
# 核心逻辑:
#   超跌反转(A)和趋势动量(B)组合,仓位根据市场状态动态倾斜。
#   MA60下方→A主导(恐慌反弹),MA60上方→B主导(趋势延续)。
#
# 动态仓位分配:
#   B弱势(MA60下方): A最多16只 / B最多4只
#   B试探(刚站上MA60): A最多4只 / B最多8只
#   B正常(MA60上方确认): A最多4只 / B最多16只
#
# A — 超跌反转(不变):
#   大盘条件: 中证1000低于MA60 且 近10日跌幅≥5%
#   买入信号: 10日跌≥15% + 单日跌≥6% + 连续2日缩量<20日均量60%
#   卖出: 止损-5% / 反弹触及MA10/20/60最低值 / 持有20日时间退出
#
# B — 趋势动量 + 多因子选股:
#   入场: 首次站上MA60立即试探(不等确认)
#   加仓: 连续5日站上MA60→正常仓位
#   离场: 连续3日跌破MA60→清仓
#   选股: 三因子(动量50% + ROE 30% + PE 20%)分位数加权
#   仓位: 波动率自适应(高波动少买/低波动多买)
#   卖出: 最高价回撤8% / 调仓日排名跌出前50%收为4%
#         大盘转弱势立即清仓 / 持有60日仍亏损强制退出
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
    g.A_max_positions = 10              # 动态调整,初始化中性值
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
    g.B_regime_confirm_days = 3         # 离场确认(跌破MA60需连续3日)
    g.B_full_position_confirm_days = 5  # 加仓确认(正常仓位需连续5日)
    g.B_momentum_window = 40
    g.B_rebalance_interval = 20
    g.B_max_positions = 10              # 动态调整
    g.B_initial_positions = 5           # 动态调整
    g.B_single_position_pct = 0.05
    g.B_buy_top_pct = 0.20
    g.B_rank_tighten_pct = 0.50
    g.B_normal_trailing_stop = 0.08
    g.B_tight_trailing_stop = 0.04
    g.B_time_exit_days = 60             # 持有超此天数且亏损→强制退出
    g.B_vol_target = 0.03               # 目标日波动率(用于仓位自适应)
    g.B_vol_adj_min = 0.5               # 仓位调整下限
    g.B_vol_adj_max = 1.5               # 仓位调整上限
    g.B_market_state = None
    g.B_above_ma_days = 0
    g.B_below_ma_days = 0
    g.B_days_since_rebalance = g.B_rebalance_interval
    g.B_positions_meta = {}
    g.B_w_momentum = 0.50
    g.B_w_quality = 0.30
    g.B_w_value = 0.20

    g.bond_etf = '511010.XSHG'          # 闲置资金买入国债ETF

    run_daily(daily_process, time='09:35')
    run_monthly(log_portfolio_status, monthday=1, time='15:00')


def ensure_cash(context, needed):
    """确保有足够现金,不足时卖国债补足。"""
    if context.portfolio.available_cash >= needed:
        return True
    bond_pos = context.portfolio.positions.get(g.bond_etf)
    if bond_pos is None or bond_pos.total_amount <= 0:
        return context.portfolio.available_cash >= needed
    shortfall = needed - context.portfolio.available_cash
    sell_value = min(shortfall * 1.02, bond_pos.value)
    order_value(g.bond_etf, -sell_value)
    return True


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
        ensure_cash(context, target_value)
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


def B_update_position_limits():
    """根据B市场状态动态调整A和B的仓位上限。"""
    if g.B_market_state == 'weak':
        g.A_max_positions = 16
        g.B_max_positions = 4
        g.B_initial_positions = 2
    elif g.B_market_state == 'watch':
        g.A_max_positions = 4
        g.B_max_positions = 8
        g.B_initial_positions = 4
    else:  # strong
        g.A_max_positions = 4
        g.B_max_positions = 16
        g.B_initial_positions = 8


def B_volatility_adjustment(stock):
    """仓位调整系数: 近期波动率越高→系数越小。范围[0.5, 1.5]"""
    close = attribute_history(stock, 20, '1d', ['close'])['close']
    if len(close) < 20:
        return 1.0
    daily_ret = close.pct_change().dropna()
    stock_vol = daily_ret.std()
    if stock_vol <= 0:
        return 1.0
    adj = g.B_vol_target / stock_vol
    return min(g.B_vol_adj_max, max(g.B_vol_adj_min, adj))


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
    elif is_above and old_state in ('weak', None):
        g.B_market_state = 'watch'  # 首次站上MA60立即试探

    if g.B_market_state != old_state:
        label = ('B试探仓' if g.B_market_state == 'watch'
                 else 'B正常仓位' if g.B_market_state == 'strong'
                 else 'B弱势' if g.B_market_state == 'weak'
                 else 'B未确认')
        log.info('B大盘状态切换: %s, 收盘 %.2f, MA%d %.2f' % (
            label, close.iloc[-1], g.B_index_ma_window, ma))
        B_update_position_limits()
        if g.B_market_state in ('watch', 'strong'):
            g.B_days_since_rebalance = g.B_rebalance_interval

    return g.B_market_state, old_state in ('watch', 'strong') and g.B_market_state == 'weak'


def B_momentum_return(stock):
    close = attribute_history(stock, g.B_momentum_window + 1, '1d', ['close'])['close']
    if len(close) < g.B_momentum_window + 1:
        return None
    return close.iloc[-1] / close.iloc[0] - 1


def B_build_multifactor_rank(context, current_data):
    """
    多因子综合打分排名。
    三个因子各自计算股票池内分位数(0~1),再按权重加总:
      动量(50%): 40日收益率 → 越高分越高
      质量(30%): ROE       → 越高分越高
      估值(20%): PE        → 越低分越高(反向)
    缺失数据的因子给中性分0.5,不偏袒也不惩罚。
    """
    date = context.previous_date  # avoid_future_data: 09:35不能取当日财报
    stocks = get_index_stocks(g.index_code, date=date)

    # ---- 1. 取财务数据(ROE + PE) ----
    df = get_fundamentals(
        query(valuation.code, valuation.pe_ratio, indicator.roe)
        .filter(valuation.code.in_(stocks)),
        date=date
    )
    pe_map = {}
    roe_map = {}
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            code = row['code']
            pe_map[code] = row['pe_ratio'] if (row['pe_ratio'] and row['pe_ratio'] > 0) else None
            roe_map[code] = row['roe'] if row['roe'] is not None else None

    # ---- 2. 收集所有可交易股票的三个原始值 ----
    records = []
    for stock in stocks:
        if not is_tradable(stock, current_data):
            continue
        ret = B_momentum_return(stock)
        if ret is None:
            continue
        records.append({
            'stock': stock,
            'momentum': ret,
            'pe': pe_map.get(stock),
            'roe': roe_map.get(stock),
        })
    if not records:
        return []

    # ---- 3. 分位数排名 ----
    n = len(records)

    # 动量: 高→好
    sorted_mom = sorted(records, key=lambda r: r['momentum'])
    for i, r in enumerate(sorted_mom):
        r['mom_pct'] = i / (n - 1) if n > 1 else 0.5

    # ROE: 高→好
    valid_roe = sorted([r for r in records if r['roe'] is not None], key=lambda r: r['roe'])
    for i, r in enumerate(valid_roe):
        r['roe_pct'] = i / (len(valid_roe) - 1) if len(valid_roe) > 1 else 0.5

    # PE: 低→好 (降序排列,最小的排最前面得最高分)
    valid_pe = sorted([r for r in records if r['pe'] is not None], key=lambda r: r['pe'], reverse=True)
    for i, r in enumerate(valid_pe):
        r['pe_pct'] = i / (len(valid_pe) - 1) if len(valid_pe) > 1 else 0.5

    # 缺失数据: 给中性分
    for r in records:
        r.setdefault('roe_pct', 0.5)
        r.setdefault('pe_pct', 0.5)

    # ---- 4. 加权总分 ----
    w_mom = g.B_w_momentum
    w_qual = g.B_w_quality
    w_val = g.B_w_value
    for r in records:
        r['score'] = r['mom_pct'] * w_mom + r['roe_pct'] * w_qual + r['pe_pct'] * w_val

    records.sort(key=lambda r: r['score'], reverse=True)

    # ---- 5. 输出: 保持和原B_rank_stocks一致的(stock, 收益率)格式 ----
    ranked = [(r['stock'], r['momentum']) for r in records]

    # 只打印一次(调仓日),show几只样本帮助理解因子作用
    sample = records[:5]
    detail = ' | '.join(
        '%s(A:%.2f M:%.0f Q:%.0f V:%.0f)' % (
            r['stock'], r['score'],
            r['mom_pct'] * 100, r['roe_pct'] * 100, r['pe_pct'] * 100
        ) for r in sample
    )
    log.info('B多因子: 动量%.0f%% 质量%.0f%% 估值%.0f%% | 候选%d只 | Top5→ %s' % (
        w_mom * 100, w_qual * 100, w_val * 100, len(ranked), detail))
    return ranked


def B_rank_stocks(context):
    current_data = get_current_data()
    return B_build_multifactor_rank(context, current_data)


def B_check_exits(context):
    """每日:移动止损 + 持有60日仍亏损强制退出。"""
    for stock in list(context.portfolio.positions):
        if stock not in g.B_positions_meta:
            continue
        price = current_price(stock)
        meta = g.B_positions_meta[stock]
        meta['highest_price'] = max(meta['highest_price'], price)

        # 移动止损
        stop = g.B_tight_trailing_stop if meta['tight_stop'] else g.B_normal_trailing_stop
        drawdown = 1 - price / meta['highest_price']
        if drawdown >= stop:
            reason = ('B排名跌出前%.0f%%,回撤%.1f%%' % (g.B_rank_tighten_pct * 100, drawdown * 100)
                      if meta['tight_stop']
                      else 'B最高价回撤%.1f%%' % (drawdown * 100))
            if exit_order(context, stock):
                g.B_positions_meta.pop(stock, None)
                log.info('卖出 %-12s | %s' % (stock, reason))
            continue

        # 长期持仓退出
        held_days = len(get_trade_days(
            start_date=meta['entry_date'],
            end_date=context.current_dt.date()
        ))
        if held_days >= g.B_time_exit_days and price < meta['entry_price']:
            loss_pct = (price / meta['entry_price'] - 1) * 100
            if exit_order(context, stock):
                g.B_positions_meta.pop(stock, None)
                log.info('卖出 %-12s | B时间退出(%d天,亏损%.1f%%)' % (stock, held_days, loss_pct))


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
    """调仓日:卖出跌出前50%的B持仓,按多因子排名补仓。不再因跌出前20%替换。"""
    if not ranked or g.B_market_state not in ('watch', 'strong'):
        return

    B_update_rank_stop_state(context, ranked)
    rank_cut = max(1, int(len(ranked) * g.B_buy_top_pct))
    total_value = context.portfolio.total_value

    # 卖出跌出前50%的B持仓(收紧止损后仍无起色)
    rank_map = {stock: i for i, (stock, _) in enumerate(ranked)}
    rank_exit_cut = max(1, int(len(ranked) * g.B_rank_tighten_pct))
    for stock in list(context.portfolio.positions):
        if stock not in g.B_positions_meta:
            continue
        pos_rank = rank_map.get(stock)
        if pos_rank is not None and pos_rank >= rank_exit_cut:
            # 排名已跌出前50%且已持续了一段时间(靠tight_stop已先行收紧)
            meta = g.B_positions_meta[stock]
            price = current_price(stock)
            if price < meta['entry_price']:
                if exit_order(context, stock):
                    g.B_positions_meta.pop(stock, None)
                    log.info('卖出 %-12s | B排名跌出前%.0f%%,替换' % (
                        stock, g.B_rank_tighten_pct * 100))

    b_count = len([s for s in context.portfolio.positions if s in g.B_positions_meta])
    target_positions = g.B_initial_positions if g.B_market_state == 'watch' else g.B_max_positions
    slots = max(0, target_positions - b_count)
    if slots <= 0:
        return

    candidates = [(stock, ret) for stock, ret in ranked[:rank_cut]
                  if stock not in context.portfolio.positions]
    for stock, ret in candidates[:slots]:
        vol_adj = B_volatility_adjustment(stock)
        target_value = min(
            total_value * g.B_single_position_pct * vol_adj,
            context.portfolio.available_cash
        )
        if target_value <= 0:
            break
        ensure_cash(context, target_value)
        order_value(stock, target_value)
        position = context.portfolio.positions.get(stock)
        if position is None or position.value <= 0:
            log.info('B买入委托未成交 %-12s' % stock)
            continue
        price = current_price(stock)
        g.B_positions_meta[stock] = {
            'highest_price': price,
            'tight_stop': False,
            'entry_price': price,
            'entry_date': context.current_dt.date(),
        }
        actual_rank = next(i for i, item in enumerate(ranked, start=1)
                           if item[0] == stock)
        log.info('B买入 %-12s | 40日收益率 %+.1f%% | 排名 %d/%d | 波动调整%.1f | 价格 %.2f' % (
            stock, ret * 100, actual_rank, len(ranked), vol_adj, price))


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

    B_check_exits(context)
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

    # 闲置现金买入国债ETF
    cash = context.portfolio.available_cash
    if cash > 1000:
        order_value(g.bond_etf, cash)


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
    bond_pos = context.portfolio.positions.get(g.bond_etf)
    if bond_pos is not None and bond_pos.total_amount > 0:
        bond_pct = bond_pos.value / total_value * 100 if total_value else 0
        log.info('  国债ETF: %.0f (%.1f%%)' % (bond_pos.value, bond_pct))

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
