# -*- coding: utf-8 -*-
# ============================================================
# 多资产 ETF 动量轮动 (Dual Momentum, 月频)
# ============================================================
# 设计依据: 训练集 2015-10 ~ 2022-11 共86个月
#   年化 8.54%  夏普 0.64  最大回撤 -14.98%  波动 14.60%
#   年化单边换手 307%  成本拖累仅 0.49%/年
#
# 同窗口对照:
#   买入持有 沪深300   年化  2.82%  夏普  0.24  回撤 -32.31%
#   买入持有 中证500   年化 -0.97%  夏普  0.07  回撤 -43.21%
#   买入持有 中证1000  年化 -5.17%  夏普 -0.08  回撤 -58.96%
#
# 逻辑:
#   1. 每月最后一个交易日 14:45 调仓
#   2. 动量 = 当前价 / 6个月前月末收盘价 - 1
#   3. 选动量最高的 2 只, 各 50%
#   4. 绝对动量过滤: 选中标的自身动量 <0 时, 该仓位换成国债ETF
#
# 关键设计决策(有实测依据, 勿随意改动):
#   - K=6/M=2 为先验值(Antonacci双动量标准设定), 跑数据前即写定, 非事后挑选
#     训练集内前后两段夏普排序相关性仅 0.155 -> 参数选择本身不稳定,
#     故坚持先验值, 不用网格峰值
#   - 绝对动量过滤保留: 训练集上它净负(-1个点收益/-0.05夏普, 换+1.6个点回撤),
#     但评估窗口切掉了2015年6月股灾(过滤器最该发挥作用的样本), 测试对它不公平。
#     时序动量有强事前经济解释, 代价小, 保留作尾部保护。
#   - 标的池非后见之明: 全池年化8.54% vs 仅A股8.45%, 差0.09个点
#     (纳指被持有51%月份却几乎无贡献) -> 干活的是信号, 不是特定资产
#   - 无止损/无回撤熔断: 与股票策略同理, 价格型减仓在月频轮动上只会
#     兑现回撤并错过反弹。绝对动量过滤已承担降险职责。
#
# ⚠️ 训练集隐忧(实盘时需知):
#   - 最后两年走平: 2021 -3.6%, 2022 -1.5%, NAV自2021年中横盘
#   - 绝对收益 4/8 年为负(-3.3/-5.4/-3.6/-1.5%), 幅度不大但会连续出现
#   - 网格中位夏普仅0.28, 可能比 0.64 更接近真实预期
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd
import datetime


def initialize(context):
    g.benchmark = '000852.XSHG'
    set_benchmark(g.benchmark)
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # ETF 免印花税; 佣金万0.85 免5 (按实际账户)
    cost = OrderCost(open_tax=0, close_tax=0,
                     open_commission=0.000085, close_commission=0.000085,
                     close_today_commission=0, min_commission=0)
    set_order_cost(cost, type='fund')
    set_order_cost(cost, type='stock')

    # ---- 标的池: 每个都有事前的资产配置理由 ----
    g.universe = [
        '510300.XSHG',   # 沪深300  A股大盘
        '510500.XSHG',   # 中证500  A股中盘
        '159915.XSHE',   # 创业板    A股成长
        '588000.XSHG',   # 科创50     A股成长
        '510880.XSHG',   # 红利      防御风格
        '513100.XSHG',   # 纳指      海外分散
        '518880.XSHG',   # 黄金      实物资产
    ]
    g.safe = '511010.XSHG'          # 国债ETF: 绝对动量为负时的避险仓
    g.names = {
        '510300.XSHG': '沪深300', '510500.XSHG': '中证500',
        '159915.XSHE': '创业板', '510880.XSHG': '红利',
        '513100.XSHG': '纳指', '518880.XSHG': '黄金',
        '588000.XSHG': '科创50',
    }

    # ---- 冻结参数 ----
    g.K = 6                          # 动量回看月数
    g.M = 2                          # 持仓数
    g.abs_filter = True              # 绝对动量过滤

    # ---- 监控 ----
    g.nav_peak = 0
    g.nav_hist = []                  # [(date, 总资产)]
    g.risk_free = 0.02               # 死亡条件用的现金收益基准(货币基金/短债约2%)

    run_daily(daily_check, time='14:45')


# ============================================================
# 工具
# ============================================================

def is_month_end(context):
    """今天是否为本月最后一个交易日。"""
    today = context.current_dt.date()
    if today.month == 12:
        nxt = datetime.date(today.year + 1, 1, 1)
    else:
        nxt = datetime.date(today.year, today.month + 1, 1)
    last_day = nxt - datetime.timedelta(days=1)
    remain = get_trade_days(start_date=today, end_date=last_day)
    return len(remain) <= 1


def month_end_closes(stock, lookback_days=280):
    """返回历史各月末收盘价 Series (index='YYYY-MM'), 不含当月。"""
    df = attribute_history(stock, lookback_days, '1d', ['close'], df=True)
    if df is None or len(df) == 0:
        return None
    s = df['close'].dropna()
    if len(s) == 0:
        return None
    idx = pd.to_datetime(pd.Series(s.index))
    keys = idx.dt.strftime('%Y-%m').values
    return pd.Series(s.values, index=keys).groupby(level=0).last()


def momentum(context, stock):
    """动量 = 当前价 / K个月前月末收盘 - 1。数据不足返回 None。"""
    me = month_end_closes(stock)
    if me is None:
        return None
    cur_ym = context.current_dt.strftime('%Y-%m')
    me = me[me.index < cur_ym]           # 排除当月(未结束)
    if len(me) < g.K:
        return None
    base = me.iloc[-g.K]
    if not base or base <= 0 or np.isnan(base):
        return None
    price = get_current_data()[stock].last_price
    if not price or price <= 0 or np.isnan(price):
        return None
    return price / base - 1.0


# ============================================================
# 选股
# ============================================================

def select_targets(context):
    """返回 {标的: 权重}。数据不足返回 None(本次不调仓)。"""
    cd = get_current_data()
    mom = {}
    for s in g.universe:
        if cd[s].paused:
            continue
        m = momentum(context, s)
        if m is not None:
            mom[s] = m
    if len(mom) < g.M:
        log.warn('可用标的仅%d个(需%d), 本次不调仓' % (len(mom), g.M))
        return None

    ranked = sorted(mom.items(), key=lambda kv: kv[1], reverse=True)
    picks = []
    for s, m in ranked[:g.M]:
        if g.abs_filter and m <= 0:
            picks.append(g.safe)         # 绝对动量为负 -> 换避险仓
        else:
            picks.append(s)

    w = {}
    for s in picks:
        w[s] = w.get(s, 0.0) + 1.0 / g.M

    detail = ' | '.join('%s %+.1f%%' % (g.names.get(s, s), m * 100)
                        for s, m in ranked)
    log.info('%d月动量排名: %s' % (g.K, detail))
    return w


# ============================================================
# 调仓
# ============================================================

def rebalance(context, weights):
    """卖出不在目标中的持仓, 再按权重买入。

    ETF 一手100份, 国债ETF单价约110元(一手约1.1万), 会造成向下取整欠配。
    故买入分多轮放大目标值, 吃掉闲置现金。
    """
    total = context.portfolio.total_value

    # ---- 先卖 ----
    for s in list(context.portfolio.positions.keys()):
        if s not in weights:
            order_target_value(s, 0)
            pos = context.portfolio.positions.get(s)
            if pos is not None and pos.total_amount > 0:
                log.warn('卖出未成交: %s' % s)

    # ---- 后买, 多轮放大消除整数倍欠配 ----
    scale = 1.0
    for _ in range(4):
        for s, w in weights.items():
            order_target_value(s, total * w * scale)
        idle = context.portfolio.available_cash / total if total else 0
        if idle < 0.015:
            break
        scale += idle * 0.95

    holding = ' | '.join('%s %.1f%%' % (g.names.get(s, s),
                                        context.portfolio.positions[s].value / total * 100)
                         for s in sorted(weights)
                         if s in context.portfolio.positions
                         and context.portfolio.positions[s].total_amount > 0)
    log.info('调仓完成 | %s | 闲置现金%.1f%% | 放大系数%.3f'
             % (holding, context.portfolio.available_cash / total * 100, scale))


def daily_check(context):
    total = context.portfolio.total_value
    g.nav_peak = max(g.nav_peak, total)

    if not is_month_end(context):
        return

    weights = select_targets(context)
    if weights is None:
        return                           # 数据异常时保持原持仓

    rebalance(context, weights)
    monthly_report(context)


# ============================================================
# 监控与死亡条件
# ============================================================
# 全部为"告警 + 人工复核", 不做自动清仓。
# 依据: 价格型减仓在月频轮动上只会兑现回撤并错过反弹;
#       绝对动量过滤已承担降险职责(训练集国债避险月份占比24.4%)。
#
# 判据为【绝对】口径, 不用相对中证1000的超额。原因:
#   本策略目标是绝对收益, 不是跑赢中证1000。用相对基准会在牛市误杀
#   (中证1000涨50%、策略赚10% -> 超额-40%, 但策略其实正常)、
#   在熊市失灵(中证1000跌30%、策略跌10% -> 超额+20%, 但已亏钱)。
# ============================================================

def monthly_report(context):
    total = context.portfolio.total_value
    drawdown = total / g.nav_peak - 1 if g.nav_peak else 0
    g.nav_hist.append((context.current_dt.date(), total))

    log.info('月报 | 总资产 %.0f | 现金 %.0f | 回撤 %.1f%%'
             % (total, context.portfolio.available_cash, drawdown * 100))

    # 死亡条件1: 滚动绝对收益跑不过现金
    # 训练集年化8.54%、测试集5.43%; 无风险约2%。长期低于现金即失去存在意义。
    for months, level in [(24, '告警'), (36, '建议停用')]:
        if len(g.nav_hist) > months:
            n0 = g.nav_hist[-months - 1][1]
            ret = total / n0 - 1
            cash_ret = (1 + g.risk_free) ** (months / 12.0) - 1
            if ret < cash_ret:
                log.warn('[死亡条件-%s] 滚动%d个月绝对收益 %.2f%% < 现金 %.2f%%'
                         % (level, months, ret * 100, cash_ret * 100))

    # 死亡条件2: 回撤超训练集最差的2倍(训练集 -14.98%, 测试集 -19.46%)
    if drawdown < -0.30:
        log.warn('[死亡条件-告警] 回撤 %.1f%% 已超训练集最差(-14.98%%)的2倍, '
                 '风险特征与历史不符, 请人工复核' % (drawdown * 100))
