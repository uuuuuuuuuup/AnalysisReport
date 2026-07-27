# -*- coding: utf-8 -*-
# ============================================================
# 策略: 中证1000超跌反转 (CSI 1000 Oversold Reversal) + 大盘恐慌过滤器
# ============================================================
# 核心逻辑:
#   散户恐慌性抛售 → 股价短期内急跌 → 成交量萎缩(恐慌盘出清) →
#   价格均值回归反弹。赚的是"散户情绪性错杀后的修复"。
#
# 前置条件 (大盘环境双重过滤,缺一不可):
#   条件1: 中证1000收盘价 < 60日均线 (趋势偏弱)
#   条件2: 中证1000过去10天自身跌超5% (恐慌真实存在,非磨蹭)
#   两条同时满足才开仓。已持仓的照常管理退出,不受影响。
#
# 买入条件 (三个同时满足):
#   1. 过去10个交易日累计跌幅 ≥ 15%
#   2. 至少有一天单日跌幅 ≥ 6% (确认是急跌,不是阴跌)
#   3. 最近连续2天成交额 < 过去20日均额的60% (缩量,恐慌衰竭)
#
# 排除: ST、停牌、当日跌停封死的股票
#
# 持仓规则:
#   - 最多20只,等权分配,单只不超过总仓位5%
#   - 允许空仓(无符合条件的股票时)
#   - 允许不满仓(候选不足20只时)
#
# 卖出条件 (三条并行,谁先触发谁生效):
#   1. 止损: 从买入价跌5%
#   2. 动态均线止盈: 反弹触及 MA10/MA20/MA60 中最低的那根
#   3. 时间退出: 持有满20个交易日仍不触发以上两条,强制清仓
#
# 设计理念:
#   - 参数极少(4个),逻辑简单,经济学含义清晰
#   - 不追求"每个信号都对",追求"整体期望值为正"
#   - 分散持仓消化单次判断错误,止盈止损控制尾部风险
# ============================================================

from jqdata import *
import numpy as np
import datetime


def initialize(context):
    """策略初始化: 设置参数、费率、定时任务"""
    # ---- 基准与费率 ----
    set_benchmark('000852.XSHG')  # 中证1000为业绩基准
    set_option('use_real_price', True)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.0003, close_commission=0.0003,
        close_today_commission=0, min_commission=5
    ), type='stock')

    # ---- 信号参数 ----
    g.lookback_days = 10            # 回看多少个交易日
    g.min_drawdown = -0.15          # 累计跌幅阈值 (-15%)
    g.single_day_drop = -0.06       # 单日急跌阈值 (-6%)
    g.volume_ma_days = 20           # 均量计算窗口
    g.volume_shrink_ratio = 0.6     # 缩量阈值 (低于均量的60%)
    g.volume_shrink_days = 2        # 需要连续几天缩量

    # ---- 持仓与风控 ----
    g.max_positions = 20            # 最多持仓数
    g.single_position_pct = 0.05   # 单只仓位上限 (5%)
    g.stop_loss_pct = -0.05         # 止损线 (-5%)
    g.time_exit_days = 20           # 时间退出 (持有20个交易日)

    # ---- 大盘环境过滤 ----
    g.index_ma_window = 60          # 中证1000低于此均线(条件1)
    g.index_panic_days = 10         # 指数近期急跌回看天数(条件2)
    g.index_panic_threshold = -0.05 # 指数自身跌幅阈值,如-5%(条件2)
    g.index_code = '000852.XSHG'    # 中证1000指数代码
    g.market_was_fearful = None     # 上次的大盘状态,用于只在切换时打日志

    # ---- 持仓元数据 ----
    # 结构: {stock: {'entry_price': 买入价, 'entry_date': 买入日期}}
    g.positions_meta = {}

    # ---- 定时任务 ----
    run_daily(check_and_trade, time='09:35')
    run_monthly(log_status, monthday=1, time='15:00')


# ============================================================
# 辅助函数
# ============================================================

def is_tradable(stock):
    """是否可交易: 未停牌、非ST、非当日跌停封死"""
    cd = get_current_data()
    return (not cd[stock].paused
            and not cd[stock].is_st
            and cd[stock].last_price > cd[stock].low_limit)


def current_price(stock):
    """取最新价"""
    return get_current_data()[stock].last_price


def is_market_fearful():
    """
    大盘环境过滤器: 双重确认市场中存在恐慌情绪。

    条件1: 中证1000收盘价 < 60日均线 (趋势偏弱)
    条件2: 中证1000过去 index_panic_days 天自己也跌了 ≥ index_panic_threshold
            (确认恐慌真实存在,不是磨蹭式阴跌)

    两条同时满足才允许开仓。大盘不恐慌时个股的急跌更可能是真利空,
    而非散户情绪性错杀——策略不捡垃圾。
    """
    close = attribute_history(g.index_code, g.lookback_days + g.index_ma_window, '1d', ['close'])['close']
    if len(close) < g.index_ma_window:
        return False

    # 条件1: 指数低于60日均线
    below_ma60 = close.iloc[-1] < close.iloc[-g.index_ma_window:].mean()
    if not below_ma60:
        return False

    # 条件2: 指数自身近期也在急跌(恐慌确认)
    index_ret = close.iloc[-1] / close.iloc[-g.index_panic_days - 1] - 1
    return index_ret <= g.index_panic_threshold


# ============================================================
# 买入信号检测
# ============================================================

def check_signal(stock):
    """
    检测超跌反转买入信号,三条件同时满足才触发:
      条件① 过去10天累计跌幅 ≥ 15%
      条件② 至少一天单日跌幅 ≥ 6% (排除温和阴跌,只抓恐慌急跌)
      条件③ 最近2天成交额都 < 20日均额的60% (缩量确认恐慌盘衰竭)
    """
    # 取够数据: lookback_days + 1 (多1天给pct_change算首日收益)
    #          + volume_ma_days (算均量用)
    days_needed = g.lookback_days + 1 + g.volume_ma_days
    df = attribute_history(stock, days_needed, '1d', ['close', 'money'])
    if len(df) < days_needed:
        return False  # 上市时间不够,数据不足

    close = df['close']
    money = df['money']

    # ---- 条件①: 过去10天累计跌幅 ≥ 15% ----
    total_ret = close.iloc[-1] / close.iloc[-g.lookback_days - 1] - 1
    if total_ret > g.min_drawdown:
        # 例: -10% > -15% → True → 跌幅不够,拒绝
        return False

    # ---- 条件②: 至少有一天单日跌幅 ≥ 6% ----
    # 多取1天数据,让 pct_change 能覆盖完整的10个日收益率
    close_window = close.iloc[-(g.lookback_days + 1):]
    daily_rets = close_window.pct_change().dropna()
    if not (daily_rets <= g.single_day_drop).any():
        return False

    # ---- 条件③: 最近2天成交额都 < 20日均量的60% ----
    avg_money = money.iloc[-(g.volume_ma_days + g.volume_shrink_days):-g.volume_shrink_days].mean()
    if avg_money <= 0:
        return False
    recent_money = money.iloc[-g.volume_shrink_days:]
    if not (recent_money < avg_money * g.volume_shrink_ratio).all():
        return False

    return True


# ============================================================
# 退出条件检测
# ============================================================

def lowest_ma(stock):
    """
    计算 MA10/MA20/MA60 中的最小值。
    一只暴跌的股票,所有均线都在股价上方,
    最低的那根均线是反弹的第一道有效阻力位,也是动态止盈目标。

    注意: 不使用 MA5——暴跌后 MA5 几乎贴着现价,用它止盈会把利润
    压缩到 1-3%,覆盖不了止损。MA10 给反弹留了合理空间。
    """
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


def check_exit(context, stock, meta):
    """
    检查是否触发退出条件。
    返回 (是否退出: bool, 退出原因: str or None)
    三条退出规则并行,谁先触发谁生效。
    """
    price = current_price(stock)
    entry_price = meta['entry_price']

    # ---- 规则1: 止损 -5% ----
    if price <= entry_price * (1 + g.stop_loss_pct):
        loss_pct = (price / entry_price - 1) * 100
        return True, '止损(亏损%.1f%%)' % loss_pct

    # ---- 规则2: 反弹至最近均线(动态止盈) ----
    result = lowest_ma(stock)
    if result is not None:
        target, ma_name = result
        if price >= target:
            gain_pct = (price / entry_price - 1) * 100
            return True, '反弹至%s(%.2f),盈利%.1f%%' % (ma_name, target, gain_pct)

    # ---- 规则3: 时间退出 ----
    held_days = len(get_trade_days(
        start_date=meta['entry_date'],
        end_date=context.current_dt.date()
    ))
    if held_days >= g.time_exit_days:
        gain_pct = (price / entry_price - 1) * 100
        return True, '时间退出(%d天,收益%.1f%%)' % (held_days, gain_pct)

    return False, None


# ============================================================
# 候选股扫描
# ============================================================

def scan_candidates(context):
    """
    扫描中证1000全部成分股,找出符合超跌反转信号的候选股。
    返回 [(stock, drawdown), ...], 按跌幅从大到小排列。
    """
    index_stocks = get_index_stocks('000852.XSHG')
    candidates = []

    for stock in index_stocks:
        # 已持仓的跳过
        if stock in context.portfolio.positions:
            continue
        # 不可交易(停牌/ST/跌停)的跳过
        if not is_tradable(stock):
            continue
        # 检查买入信号
        if check_signal(stock):
            close = attribute_history(stock, g.lookback_days + 1, '1d', ['close'])['close']
            ret = close.iloc[-1] / close.iloc[-g.lookback_days - 1] - 1
            candidates.append((stock, ret))

    # 按跌幅从大到小排序(跌幅最大的优先买入)
    candidates.sort(key=lambda x: x[1])
    return candidates


# ============================================================
# 每日主逻辑
# ============================================================

def check_and_trade(context):
    """每天开盘后执行: ① 检查持仓退出  ② 扫描新候选买入"""

    # ======== 第一步: 检查持仓退出 ========
    for stock in list(context.portfolio.positions):
        meta = g.positions_meta.get(stock)
        if meta is None:
            # 兜底: 如果元数据丢了(比如模拟盘重启异常),用当前价记录
            g.positions_meta[stock] = {
                'entry_price': current_price(stock),
                'entry_date': context.current_dt.date()
            }
            continue

        should_exit, reason = check_exit(context, stock, meta)
        if should_exit:
            order_target_value(stock, 0)
            # 确认是否真的清掉了(跌停可能卖不出去)
            if (stock not in context.portfolio.positions
                    or context.portfolio.positions[stock].value <= 0):
                g.positions_meta.pop(stock, None)
                log.info('卖出 %-12s | %s' % (stock, reason))
            else:
                log.info('卖出委托未成交 %s (可能跌停), 明天继续' % stock)

    # ======== 第二步: 检查大盘环境,决定是否开新仓 ========
    slots = g.max_positions - len(context.portfolio.positions)
    if slots <= 0:
        return

    fearful = is_market_fearful()
    # 只在大盘状态切换时打日志,避免每天刷屏
    if fearful != g.market_was_fearful:
        log.info('大盘环境切换: %s → 不开新仓' % ('弱势(允许开仓)' if fearful else '强势'))
        g.market_was_fearful = fearful

    if not fearful:
        return

    candidates = scan_candidates(context)
    if not candidates:
        return

    total_value = context.portfolio.total_value
    for stock, drawdown in candidates[:slots]:
        # 单只仓位 = min(总资产×5%, 可用现金)
        target_value = min(
            total_value * g.single_position_pct,
            context.portfolio.available_cash
        )
        if target_value <= 0:
            break

        order_value(stock, target_value)

        # 确认是否真的买到了(涨停/停牌可能买不到)
        if (stock in context.portfolio.positions
                and context.portfolio.positions[stock].value > 0):
            g.positions_meta[stock] = {
                'entry_price': current_price(stock),
                'entry_date': context.current_dt.date()
            }
            log.info('买入 %-12s | 10日跌幅 %+.1f%% | 价格 %.2f' % (
                stock, drawdown * 100, current_price(stock)))
        else:
            log.info('买入委托未成交 %s (可能涨停/停牌), 换下一个候选' % stock)


# ============================================================
# 月度报告
# ============================================================

def log_status(context):
    """每月一次仓位快照"""
    tv = context.portfolio.total_value
    cash = context.portfolio.available_cash
    positions = context.portfolio.positions
    pos_count = len(positions)

    fearful = is_market_fearful()
    regime = '弱势(可开仓)' if fearful else '强势(不开新仓)'

    log.info('=' * 60)
    log.info('月度仓位快照 | 总资产: %.0f | 现金: %.0f (%.1f%%) | 持仓: %d/%d 只 | 大盘: %s' % (
        tv, cash, cash / tv * 100 if tv > 0 else 0, pos_count, g.max_positions, regime))
    log.info('-' * 60)

    if pos_count == 0:
        log.info('  当前空仓,无符合条件的超跌信号')
    else:
        for stock, pos in positions.items():
            meta = g.positions_meta.get(stock, {})
            entry_price = meta.get('entry_price', 0)
            price = current_price(stock)
            pnl_pct = (price / entry_price - 1) * 100 if entry_price > 0 else 0
            weight = pos.value / tv * 100 if tv > 0 else 0
            entry_date = meta.get('entry_date', '?')
            held_days = len(get_trade_days(
                start_date=entry_date,
                end_date=context.current_dt.date()
            )) if isinstance(entry_date, datetime.date) else '?'
            log.info('  %-12s | 买入价 %.2f | 现价 %.2f | 盈亏 %+.1f%% | 占比 %.1f%% | 已持 %s 天' % (
                stock, entry_price, price, pnl_pct, weight, held_days))
    log.info('=' * 60)
