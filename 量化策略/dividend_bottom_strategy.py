# -*- coding: utf-8 -*-
# 策略:沪深300高股息底部轮动
# 买入(需同时满足):股息率>5% + 股价处于近3年历史百分位20%以下 + 股价<=250日均线 + MACD底背离
# 卖出:股息率<3%
# 买卖均分批执行,最多同时持有5只股票

from jqdata import *
import re
import datetime

# 分红公告 board_plan_bonusnote 里都是"每10股派X元"的口径,不管前面有没有转/送股说明
DIVIDEND_PATTERN = re.compile(r'派([\d\.]+)元')


def initialize(context):
    # 用沪深300做业绩基准,方便回测报告里对比策略跟指数的收益差
    set_benchmark('000300.XSHG')
    # 用真实价格计算收益,而不是聚宽默认的前复权价,避免分红/拆股导致数字失真
    set_option('use_real_price', True)
    # 佣金万三、卖出印花税千一、最低5元,是A股常见的默认费率,可按你自己券商实际费率调整
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                              open_commission=0.0003, close_commission=0.0003,
                              close_today_commission=0, min_commission=5), type='stock')

    g.max_stocks = 5           # 最多同时持有几只股票
    g.max_buy_batches = 6      # 每只股票买入最多分几批(单只股票目标仓位20%,平均分给这么多批)
    g.max_sell_batches = 5     # 每只股票卖出最多分几批
    g.buy_step_pct = 0.04      # 股价比上次买入价再跌这个比例,才买下一批(4%)
    g.sell_step_pct = 0.05     # 股价比上次卖出价再涨这个比例,才卖下一批(5%)
    g.buy_yield = 5.0          # 股息率高于这个值(单位:%)才允许买入/加仓
    g.sell_yield = 3.0         # 股息率低于这个值(单位:%)才触发卖出
    g.dividend_lookback_days = 365  # 往前找多少天内的分红公告来算股息率(近12个月)
    g.percentile_window = 750  # 算历史百分位用多少个交易日(约等于3年)
    g.percentile_threshold = 0.20   # 现价在历史价格里排在最低20%以内才算"便宜"
    g.ma_window = 250          # 250日(约1年)均线,用来判断股价是否处于长期低位
    g.macd_lookback = 60       # 找MACD底背离时往前看多少个交易日
    # g 是聚宽提供的全局对象,数据会在整个回测/交易期间持续保留
    # positions_meta 记录每只持仓股当前买了几批、卖了几批、上次买卖价格,方便判断下一批的触发条件
    # 结构: {股票代码: {'batches': 已买批数, 'last_buy_price': 上次买入价, 'sell_batches': 已卖批数, 'last_sell_price': 上次卖出价}}
    g.positions_meta = {}

    # run_daily 让聚宽每个交易日在指定时间自动调用一次对应函数
    # 先跑卖出再跑买入,避免同一天既想卖又想买时资金被买入占用
    run_daily(check_sell, time='09:35')
    run_daily(check_buy, time='09:40')
    # 每月第1个交易日收盘前打印一次仓位快照,方便按月核对资金利用率、避免每天都打太多日志
    run_monthly(log_portfolio_status, monthday=1, time='15:00')


def extract_dividend_per_share(bonusnote):
    """从分红公告文本(如"10派3.5元")里解析出每股派息金额,解析不到就当作0(不分红)"""
    if not isinstance(bonusnote, str):
        return 0.0
    match = DIVIDEND_PATTERN.search(bonusnote)
    if not match:
        return 0.0
    return float(match.group(1)) / 10.0  # "10派X元" 是每10股派X元,除以10换算成每股


def get_dividend_yield_map(context, stocks):
    """批量算一批股票的股息率(%),返回 {股票代码: 股息率} 的字典,没有分红数据的股票不会出现在结果里"""
    if not stocks:
        return {}
    end_date = context.current_dt.date()
    start_date = end_date - datetime.timedelta(days=g.dividend_lookback_days)
    # finance.STK_XR_XD 是聚宽的"除权除息"表,board_plan_bonusnote 就是分红方案的文字说明
    # 用股权登记日筛选近12个月的分红方案,按 code 累加每股派息(一年可能分红多次,要加总)
    q = query(
        finance.STK_XR_XD.code,
        finance.STK_XR_XD.board_plan_bonusnote
    ).filter(
        finance.STK_XR_XD.code.in_(stocks),
        finance.STK_XR_XD.a_registration_date >= start_date,
        finance.STK_XR_XD.a_registration_date <= end_date
    )
    df = finance.run_query(q)

    dividend_per_share = {}
    for _, row in df.iterrows():
        amount = extract_dividend_per_share(row['board_plan_bonusnote'])
        dividend_per_share[row['code']] = dividend_per_share.get(row['code'], 0.0) + amount

    # 股息率 = 近12个月每股派息总额 / 当前股价 * 100
    yield_map = {}
    for stock, amount in dividend_per_share.items():
        if amount <= 0:
            continue
        price = current_price(stock)
        if price and price > 0:
            yield_map[stock] = amount / price * 100
    return yield_map


def log_portfolio_status(context):
    """每月打印一次仓位快照:总资产、现金占比、每只持仓股的市值占比和已买/已卖批数"""
    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash
    cash_pct = cash / total_value * 100 if total_value else 0
    log.info('=== 仓位快照 总资产%.0f 现金%.0f(占比%.1f%%) 持仓%d只 ===' % (
        total_value, cash, cash_pct, len(context.portfolio.positions)))
    for stock, position in context.portfolio.positions.items():
        weight_pct = position.value / total_value * 100 if total_value else 0
        meta = g.positions_meta.get(stock, {})
        log.info('    %s 市值%.0f 占比%.1f%% 已买%s批 已卖%s批' % (
            stock, position.value, weight_pct, meta.get('batches', '?'), meta.get('sell_batches', '?')))


def is_tradable(stock):
    """是否可交易:没有停牌、不是ST股"""
    current_data = get_current_data()
    return not current_data[stock].paused and not current_data[stock].is_st


def exclude_real_estate(stocks, dt):
    """排除申万一级行业为"房地产"的股票——地产这几年是行业性趋势下跌,不是短期错杀,容易被"历史低位+MACD底背离"误判成买点"""
    if not stocks:
        return stocks
    industry_map = get_industry(stocks, date=dt)
    result = []
    for stock in stocks:
        sw = (industry_map.get(stock) or {}).get('sw_l1') or {}
        if '房地产' in (sw.get('industry_name') or ''):
            continue
        result.append(stock)
    return result


def current_price(stock):
    """取股票的最新价"""
    return get_current_data()[stock].last_price


def price_percentile(stock, window):
    """现价在过去 window 个交易日收盘价里的百分位排名(0~1,越小说明现价越便宜)"""
    close = attribute_history(stock, window, '1d', ['close'])['close']
    if len(close) < window:
        return None  # 上市不满 window 天,数据不够,不参与判断
    return (close < close.iloc[-1]).mean()  # 历史上比现价还低的天数占比


def below_long_ma(stock, window):
    """现价是否 <= 过去 window 天的收盘价均值(简化版长期均线,判断是否处于低位)"""
    close = attribute_history(stock, window, '1d', ['close'])['close']
    if len(close) < window:
        return False
    return close.iloc[-1] <= close.mean()


def find_troughs(series, min_gap=5):
    """在一段价格序列里找局部低点(比左右各2天都低的点),min_gap天内的相邻低点只保留更低的那个"""
    raw = []
    for i in range(2, len(series) - 2):
        window = series.iloc[i - 2:i + 3]
        if series.iloc[i] == window.min():
            raw.append(i)
    # 合并5天内的相邻低点,只保留更低的那个
    troughs = []
    for i in raw:
        if troughs and i - troughs[-1] < min_gap:
            if series.iloc[i] < series.iloc[troughs[-1]]:
                troughs[-1] = i
        else:
            troughs.append(i)
    return troughs


def macd_bottom_divergence(stock, lookback):
    """
    判断MACD底背离:股价创了新低,但MACD的DIF指标没有跟着创新低,说明下跌动能在减弱。
    做法:自己用收盘价算EMA12、EMA26,相减得到DIF序列(标准MACD公式,聚宽没有现成的历史序列接口)。
    """
    close = attribute_history(stock, lookback + 60, '1d', ['close'])['close']
    if len(close) < lookback + 60:
        return False  # 多取60天是为了让EMA有足够数据"预热",避免序列刚开始时不准
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = (ema12 - ema26).iloc[-lookback:]   # 只截取最近 lookback 天来找底背离
    price = close.iloc[-lookback:]

    troughs = find_troughs(price.reset_index(drop=True))
    if len(troughs) < 2:
        return False  # 找不到两个低点就没法比较,判定为不满足
    prev_idx, last_idx = troughs[-2], troughs[-1]  # 最近的两个低点:前一个、最后一个
    price_lower_low = price.iloc[last_idx] < price.iloc[prev_idx]  # 价格创新低
    dif_higher_low = dif.iloc[last_idx] > dif.iloc[prev_idx]       # 但DIF反而更高
    return price_lower_low and dif_higher_low


def buy_one_batch(context, stock, meta):
    """买入一批仓位:每只股票的目标总仓位是 总资产/最多持股数,再平均分成 max_buy_batches 批买入"""
    total_value = context.portfolio.total_value
    batch_value = min(total_value / g.max_stocks / g.max_buy_batches, context.portfolio.available_cash)
    if batch_value <= 0:
        return
    order_value(stock, batch_value)  # order_value: 按金额下单买入
    meta['batches'] += 1
    meta['last_buy_price'] = current_price(stock)
    # 用下单后的最新持仓市值算仓位占比,方便判断这只股票、以及整体资金有没有被有效用起来
    weight_pct = context.portfolio.positions[stock].value / total_value * 100 if total_value else 0
    log.info('买入 %s 第%d批,价格%.2f,本批金额%.0f,该股仓位占比%.1f%%' % (
        stock, meta['batches'], meta['last_buy_price'], batch_value, weight_pct))


def sell_one_batch(context, stock, meta):
    """卖出一批仓位:剩余批次只有1批(或以下)时直接清仓,否则按剩余批次数平均卖出当前持仓市值"""
    price = current_price(stock)
    total_value = context.portfolio.total_value
    remaining_batches = g.max_sell_batches - meta['sell_batches']
    if remaining_batches <= 1:
        order_target_value(stock, 0)  # order_target_value(stock, 0): 把该股票仓位调整到0,即清仓
        g.positions_meta.pop(stock, None)
        log.info('清仓 %s,价格%.2f' % (stock, price))
        return
    position = context.portfolio.positions[stock]
    order_value(stock, -position.value / remaining_batches)  # 负数金额表示卖出
    meta['sell_batches'] += 1
    meta['last_sell_price'] = price
    weight_pct = context.portfolio.positions[stock].value / total_value * 100 if total_value else 0
    log.info('卖出 %s 第%d批,价格%.2f,卖出后仓位占比%.1f%%' % (
        stock, meta['sell_batches'], price, weight_pct))


def check_buy(context):
    """每天开盘后跑一次:先给已持仓的股票按条件加仓,再从沪深300里挑新股票首次建仓"""
    index_stocks = [s for s in get_index_stocks('000300.XSHG') if is_tradable(s)]
    index_stocks = exclude_real_estate(index_stocks, context.current_dt.date())
    dividend_map = get_dividend_yield_map(context, index_stocks)

    # 已持仓股票尝试加仓:股息率仍然达标,且股价比上次买入价又跌了一个批次步长(5%),就买下一批
    for stock in list(g.positions_meta.keys()):
        meta = g.positions_meta[stock]
        if meta['batches'] >= g.max_buy_batches:
            continue  # 已经买满 max_buy_batches 批,不再加仓
        yield_now = dividend_map.get(stock)
        if yield_now is None or yield_now <= g.buy_yield:
            continue  # 股息率跌破5%,停止加仓(但已买的不动,由 check_sell 单独处理卖出)
        if current_price(stock) <= meta['last_buy_price'] * (1 - g.buy_step_pct):
            buy_one_batch(context, stock, meta)

    # 新股票首次建仓:先看有没有空余持仓名额
    slots_left = g.max_stocks - len(context.portfolio.positions)
    if slots_left <= 0:
        return

    # 从沪深300里筛出同时满足四个条件的候选股:高股息 + 历史低位 + 低于250日均线 + MACD底背离
    candidates = []
    for stock in index_stocks:
        if stock in g.positions_meta:
            continue  # 已经持仓的股票不参与"首次建仓"逻辑
        yield_now = dividend_map.get(stock)
        if yield_now is None or yield_now <= g.buy_yield:
            continue
        pct = price_percentile(stock, g.percentile_window)
        if pct is None or pct >= g.percentile_threshold:
            continue
        if not below_long_ma(stock, g.ma_window):
            continue
        if not macd_bottom_divergence(stock, g.macd_lookback):
            continue
        candidates.append((stock, yield_now))

    # 候选股超过剩余名额时,优先买股息率更高的
    candidates.sort(key=lambda x: x[1], reverse=True)
    for stock, _ in candidates[:slots_left]:
        g.positions_meta[stock] = {'batches': 0, 'last_buy_price': None, 'sell_batches': 0, 'last_sell_price': None}
        buy_one_batch(context, stock, g.positions_meta[stock])


def check_sell(context):
    """每天开盘后先跑这个:检查所有持仓股票的股息率,跌破卖出线就分批卖出"""
    held = list(context.portfolio.positions.keys())
    dividend_map = get_dividend_yield_map(context, held)

    for stock in held:
        yield_now = dividend_map.get(stock)
        if yield_now is None or yield_now >= g.sell_yield:
            continue  # 股息率还在3%以上,不卖

        # 持仓股票理论上都应该在 positions_meta 里,这里用 setdefault 兜底(比如账户里手工加过的老仓位)
        meta = g.positions_meta.setdefault(
            stock, {'batches': g.max_buy_batches, 'last_buy_price': None, 'sell_batches': 0, 'last_sell_price': None})
        # 第一次跌破3%直接卖一批;之后要等股价比上次卖出价又涨了 sell_step_pct 才卖下一批
        if meta['sell_batches'] == 0 or current_price(stock) >= meta['last_sell_price'] * (1 + g.sell_step_pct):
            sell_one_batch(context, stock, meta)
