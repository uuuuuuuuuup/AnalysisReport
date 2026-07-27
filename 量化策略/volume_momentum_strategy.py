# -*- coding: utf-8 -*-
# 策略:沪深300量价共振轮动
# 不看估值,只看价格和成交量本身:
#   大盘"放量+站上250日均线"(真正的活跃上涨行情,不是恐慌性放量下跌)时,
#   买入涨幅排名靠前 + 涨幅本身为正 + 个股自身也放量的强势股
#   每只股票一次性建满仓位(不分批),最多同时持有5只
# 离场(不分批,一次性清仓):
#   大盘跌破250日均线 或者 沪深300市盈率处于历史极端高估区间(>17倍):不等个股逐只止损,直接清空全部持仓避险
#   (触发高估清仓后要等市盈率回落到14倍以下才恢复买入,避免在17倍上下反复开关)
#   移动止损:自买入后最高价回撤超过15%(动量排名跌出前50%后收紧为7.5%)
#   动量排名跌出前50%时不立刻卖,只是收紧移动止损,让市场自己检验这只股票是暂时落后还是真的转弱

from jqdata import *


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                              open_commission=0.0003, close_commission=0.0003,
                              close_today_commission=0, min_commission=5), type='stock')

    g.max_stocks = 5                  # 最多同时持有几只股票
    g.regime_short_window = 5         # 大盘活跃度:最近几天的平均成交额
    g.regime_long_window = 20         # 大盘活跃度:作为基准的前面几天平均成交额(不跟short_window重叠)
    g.regime_threshold = 1.0          # 近期/基准 的比值超过这个数才算"放量"
    g.index_ma_window = 250           # 判断大盘趋势用的均线天数(约1年)
    g.pe_extreme_high = 17.0          # 沪深300市盈率超过这个值算历史极端高估区间(2015年6月顶部约20倍,15年均值约10.5倍)
    g.pe_recovery = 14.0              # 触发高估清仓后,要等市盈率回落到这个值以下才恢复买入(历史高估区间14~17倍的下沿,避免刚跌破17倍一点点就又买回去)
    g.momentum_window = 20            # 算个股涨幅用多少个交易日
    g.momentum_top_pct = 0.20         # 涨幅排名前20%才算"强势"
    g.momentum_min_return = 0.0       # 个股涨幅本身必须大于这个值,避免普跌市场里选出"跌得慢的伪强势股"
    g.volume_short_window = 5         # 个股放量确认:最近几天的平均成交额
    g.volume_long_window = 20         # 个股放量确认:作为基准的前面几天平均成交额
    g.volume_ratio_threshold = 1.2    # 近期/基准 的比值超过这个数才算"真的在放量"
    g.trailing_stop_pct = 0.15        # 移动止损:从买入后最高价回撤超过这个比例就清仓
    g.rank_exit_pct = 0.50            # 动量排名跌出前50%,不立刻卖,但止损线收紧
    g.rank_exit_trailing_stop_pct = 0.075  # 排名跌出前50%后用这个更严格的止损线(回撤7.5%就清仓)
    # g.positions_meta 只记录每只持仓股"买入后至今的最高收盘价",给移动止损用
    # 结构: {股票代码: {'highest_price': 最高收盘价}}
    g.positions_meta = {}
    g.market_was_active = None  # 上一次判断的大盘活跃状态,None表示还没判断过,用于只在状态切换时打日志
    g.market_was_overvalued = None  # 上一次判断的估值状态,同上,只在切换时打日志

    # 止损每天检查,要及时;换仓看的是"排名"和"放量",没必要每天算,按周做更符合动量策略的调仓节奏
    run_daily(check_stop_loss, time='09:35')
    run_weekly(check_rebalance, weekday=1, time='09:40')   # 每周一
    run_monthly(log_portfolio_status, monthday=1, time='15:00')


def is_tradable(stock):
    """是否可交易:没有停牌、不是ST股"""
    current_data = get_current_data()
    return not current_data[stock].paused and not current_data[stock].is_st


def current_price(stock):
    """取股票的最新价"""
    return get_current_data()[stock].last_price


def volume_ratio(stock, short_window, long_window):
    """
    成交额动能:最近short_window天的日均成交额 / 之前long_window天(不重叠、更早)的日均成交额。
    大于1说明最近的成交比之前更活跃,不管是判断大盘还是判断个股都用这同一个函数。
    """
    money = attribute_history(stock, short_window + long_window, '1d', ['money'])['money']
    if len(money) < short_window + long_window:
        return None  # 数据不够(比如刚上市不久),不参与判断
    recent = money.iloc[-short_window:].mean()
    baseline = money.iloc[:long_window].mean()
    if baseline <= 0:
        return None
    return recent / baseline


def is_market_active(context):
    """
    大盘是否处于"放量+上升趋势"的活跃行情:只看成交量放大不够,恐慌性抛售一样会放量,
    必须同时满足"成交额比之前明显放大"和"现价在250日均线之上",才算真正值得进场的活跃行情。
    """
    ratio = volume_ratio('000300.XSHG', g.regime_short_window, g.regime_long_window)
    if ratio is None or ratio <= g.regime_threshold:
        return False
    return market_trend_up()


def market_trend_up():
    """沪深300现价是否在index_ma_window日均线之上,用来判断大盘长期趋势是涨是跌"""
    close = attribute_history('000300.XSHG', g.index_ma_window, '1d', ['close'])['close']
    if len(close) < g.index_ma_window:
        return False  # 数据不够,保守起见当作"趋势未确认"
    return close.iloc[-1] > close.mean()

def get_index_pe_ttm(context):
    """
    计算沪深300指数市盈率,用"整体法":成分股总市值 / 成分股总净利润(TTM)。
    不能用"个股PE按权重加权平均"——净利润很小的个股PE会爆炸到几百倍,
    哪怕权重很低也会把加权平均值拉得远高于真实水平(实测算出32.80倍这种明显失真的数字)。
    净利润也不直接用income.net_profit——这个字段是某一期财报的发生额,不指定statDate时
    口径不确定(可能是单季度或非年化累计),分母被低估导致PE虚高(实测算出41.88倍)。
    改用valuation.pe_ratio反推:pe_ratio本身就是聚宽按TTM净利润算出来的个股市盈率,
    净利润(TTM) = 市值 / pe_ratio,口径统一,不会有财报期限的坑。
    """
    date = context.current_dt.date()
    stocks = get_index_stocks('000300.XSHG', date=date)
    if not stocks:
        return None
    q = query(valuation.market_cap, valuation.pe_ratio).filter(valuation.code.in_(stocks))
    df = get_fundamentals(q, date=date)
    if df is None or df.empty:
        return None
    df = df[df['pe_ratio'] != 0]  # pe_ratio为0说明净利润数据缺失,反推会除零
    total_mv = df['market_cap'].sum()
    total_profit = (df['market_cap'] / df['pe_ratio']).sum()
    if total_profit <= 0:
        return None  # 成分股整体净利润为负,市盈率无意义
    return total_mv / total_profit


def is_market_overvalued(context):
    """
    沪深300是否处于"应该规避"的高估状态,用双阈值(滞后区间)避免在17倍上下反复开关买卖:
    从"正常"变成"高估"要突破pe_extreme_high(17倍,历史极端高估区间下沿);
    一旦进入"高估",要等回落到更低的pe_recovery(14倍,历史高估区间下沿,回到核心中枢附近)
    以下才恢复"正常"——不能刚跌破17倍一点点(比如16.6倍,仍处于14~17倍的历史高估区间)
    就恢复买入,否则会在阈值附近反复开关,买了又被打回来。
    """
    pe = get_index_pe_ttm(context)
    if pe is None:
        return bool(g.market_was_overvalued), pe  # 拿不到数据时保持原状态,不能因为缺数据就误判
    threshold = g.pe_recovery if g.market_was_overvalued else g.pe_extreme_high
    overvalued = pe > threshold
    if overvalued != g.market_was_overvalued:
        log.info('沪深300估值状态切换为:%s(市盈率%.2f倍)' % ('高估' if overvalued else '正常', pe))
        g.market_was_overvalued = overvalued
    return overvalued, pe


def momentum_return(stock, window):
    """过去window个交易日的涨幅(现价/window天前的收盘价 - 1)"""
    close = attribute_history(stock, window, '1d', ['close'])['close']
    if len(close) < window:
        return None
    return close.iloc[-1] / close.iloc[0] - 1


def rank_all_by_momentum(context):
    """给沪深300全部可交易成分股按momentum_window日涨幅从高到低排序,返回[(股票代码, 涨幅), ...]"""
    index_stocks = [s for s in get_index_stocks('000300.XSHG') if is_tradable(s)]
    returns = []
    for stock in index_stocks:
        ret = momentum_return(stock, g.momentum_window)
        if ret is not None:
            returns.append((stock, ret))
    returns.sort(key=lambda x: x[1], reverse=True)
    return returns


def buy_full_position(context, stock):
    """
    一次性建满目标仓位,不分批——动量策略讲究右侧确认后果断进场,分批反而会错过启动阶段。
    返回是否真正成交:动量最强的股票经常正好是涨停/一字板买不进的股票,委托可能没有成交,
    这种情况不能白白占用一个持仓名额,要让调用方去试下一个候选股。
    """
    total_value = context.portfolio.total_value
    target_value = min(total_value / g.max_stocks, context.portfolio.available_cash)
    if target_value <= 0:
        return False
    order_value(stock, target_value)
    if stock not in context.portfolio.positions or context.portfolio.positions[stock].value <= 0:
        return False  # 大概率涨停/停牌导致委托未成交
    position = context.portfolio.positions[stock]
    g.positions_meta[stock] = {'highest_price': current_price(stock)}
    weight_pct = position.value / total_value * 100 if total_value else 0
    log.info('买入 %s,动量排名靠前+放量确认,价格%.2f,仓位占比%.1f%%' % (
        stock, current_price(stock), weight_pct))
    return True


def position_closed(context, stock):
    """下单清仓后,检查是不是真的清掉了——跌停/停牌时清仓委托可能没成交,不能想当然认为已经卖出"""
    return stock not in context.portfolio.positions or context.portfolio.positions[stock].value <= 0


def check_stop_loss(context):
    """
    每天检查:大盘趋势转熊(跌破250日均线)或者估值处于历史极端高估区间时,不等个股一个个触发止损,
    直接清空全部持仓避险;两者都没触发,才继续走"逐只移动止损"的逻辑。
    """
    trend_down = not market_trend_up()
    overvalued, pe = is_market_overvalued(context)
    if trend_down or overvalued:
        reason = ('大盘跌破%d日均线' % g.index_ma_window) if trend_down else (
            '沪深300估值处于高估区间(市盈率%s)' % (('%.2f倍' % pe) if pe is not None else '未知'))
        for stock in list(context.portfolio.positions):
            order_target_value(stock, 0)
            if position_closed(context, stock):
                g.positions_meta.pop(stock, None)
                log.info('%s,清仓避险 %s' % (reason, stock))
            else:
                # 跌停/停牌卖不出去,保留原来的highest_price,明天继续按这个止损基准重试,不能重置
                log.info('%s但%s可能跌停/停牌未能卖出,明天继续尝试' % (reason, stock))
        return

    for stock in list(context.portfolio.positions):
        meta = g.positions_meta.setdefault(stock, {'highest_price': current_price(stock)})
        price = current_price(stock)
        meta['highest_price'] = max(meta['highest_price'], price)
        # 排名还在前50%用正常止损线,排名已经跌出去的用更严格的止损线,提前发现"真的转弱"
        stop_pct = g.rank_exit_trailing_stop_pct if meta.get('tight_stop') else g.trailing_stop_pct
        if price <= meta['highest_price'] * (1 - stop_pct):
            drawdown_pct = (1 - price / meta['highest_price']) * 100
            order_target_value(stock, 0)
            if position_closed(context, stock):
                g.positions_meta.pop(stock, None)
                log.info('止损清仓 %s,最高价%.2f 现价%.2f 回撤%.1f%%(止损线%.1f%%)' % (
                    stock, meta['highest_price'], price, drawdown_pct, stop_pct * 100))
            else:
                log.info('止损委托未成交(可能跌停/停牌) %s,现价%.2f,明天继续尝试' % (stock, price))


def check_rebalance(context):
    """每周一跑一次:排名跌出前50%的老股票收紧止损(不立刻卖),大盘活跃时再从强势+放量的候选股里补齐空缺名额"""
    ranked = rank_all_by_momentum(context)
    if not ranked:
        return
    total_ranked = len(ranked)
    top_pct_cut = max(1, int(total_ranked * g.momentum_top_pct))    # 涨幅前20%的分界名次
    rank_exit_cut = max(1, int(total_ranked * g.rank_exit_pct))     # 涨幅前50%的分界名次
    rank_position = {stock: i for i, (stock, _) in enumerate(ranked)}  # 名次从0开始,0=涨幅最强

    # 已持仓股票:排名跌出前50%不立刻卖,只收紧止损线,交给check_stop_loss每天去判断是不是真的转弱了
    # 已经不在沪深300可交易范围内(下证/ST/停牌等)是另一种情况,直接换出
    for stock in list(context.portfolio.positions):
        pos_rank = rank_position.get(stock)
        meta = g.positions_meta.get(stock)
        if pos_rank is None:
            order_target_value(stock, 0)
            if position_closed(context, stock):
                g.positions_meta.pop(stock, None)
                log.info('换出 %s,已不在沪深300可交易范围内' % stock)
            else:
                log.info('换出委托未成交(可能跌停/停牌) %s,下周继续尝试' % stock)
        elif pos_rank >= rank_exit_cut:
            if meta is not None and not meta.get('tight_stop'):
                meta['tight_stop'] = True
                log.info('%s 动量排名跌出前%.0f%%,止损线收紧为%.1f%%' % (
                    stock, g.rank_exit_pct * 100, g.rank_exit_trailing_stop_pct * 100))
        else:
            if meta is not None and meta.get('tight_stop'):
                meta['tight_stop'] = False
                log.info('%s 动量排名回到前%.0f%%,止损线恢复为%.1f%%' % (
                    stock, g.rank_exit_pct * 100, g.trailing_stop_pct * 100))

    # 大盘不活跃、或者估值处于历史极端高估区间,都不开新仓,只做上面的"换出/收紧止损"
    # 只在状态发生切换时打日志,避免连续几十周都是同一个状态时反复刷屏
    active = is_market_active(context)
    if active != g.market_was_active:
        log.info('大盘活跃度切换为:%s' % ('活跃' if active else '不活跃'))
        g.market_was_active = active

    overvalued, _ = is_market_overvalued(context)

    if not active or overvalued:
        return

    slots_left = g.max_stocks - len(context.portfolio.positions)
    if slots_left <= 0:
        return

    # 从涨幅排名前20%里再挑出"涨幅本身为正 + 自身也放量"的股票,按涨幅从高到低补齐空缺名额
    for stock, ret in ranked[:top_pct_cut]:
        if slots_left <= 0:
            break
        if stock in context.portfolio.positions:
            continue
        if ret <= g.momentum_min_return:
            continue  # 普跌市场里排名靠前也可能是负收益,只是跌得比别人慢,不是真强势
        vr = volume_ratio(stock, g.volume_short_window, g.volume_long_window)
        if vr is None or vr <= g.volume_ratio_threshold:
            continue
        if buy_full_position(context, stock):
            slots_left -= 1  # 只有真正成交才占用名额,涨停/停牌买不进就换下一个候选股


def log_portfolio_status(context):
    """每月打印一次仓位快照:总资产、现金占比、每只持仓股的市值占比、当前沪深300市盈率"""
    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash
    cash_pct = cash / total_value * 100 if total_value else 0
    pe = get_index_pe_ttm(context)
    log.info('=== 仓位快照 总资产%.0f 现金%.0f(占比%.1f%%) 持仓%d只 沪深300PE%s ===' % (
        total_value, cash, cash_pct, len(context.portfolio.positions),
        ('%.2f倍' % pe) if pe is not None else '未知'))
    for stock, position in context.portfolio.positions.items():
        weight_pct = position.value / total_value * 100 if total_value else 0
        log.info('    %s 市值%.0f 占比%.1f%%' % (stock, position.value, weight_pct))
