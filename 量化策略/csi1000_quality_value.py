# -*- coding: utf-8 -*-
# ============================================================
# 中证1000 多因子指数增强 (Quality + Value, 月频)
# ============================================================
# 设计依据: 2015-01~2025-12 共131个月分层检验 + 样本内外拆分
#   样本外(2021-2025): 超额 +6.1%, IR 0.49, 绝对回撤 -23.2%
#   全区间(2015-2025): 超额 +5.8%, IR 0.49, 绝对回撤 -33.8%  ← 心理准备按这个
#
# 选股逻辑:
#   1. 池: 中证1000成分股, 剔除 停牌/ST/涨停/上市<120日
#   2. 硬排除: 40日动量最高的20%     (该档年化-8.7%, IC t=-4.05)
#   3. 打分: 0.5*z(中性化ROE) + 0.5*z(中性化BP)
#      中性化 = 对 申万一级行业哑变量 + ln(总市值) 回归取残差
#   4. 持仓: 打分前40名, 等权, 月频硬性重排
#
# 关键设计决策(均有实测依据, 勿随意改动):
#   - 无移动止损: 8%止损使 IR 0.44->0.06、回撤 -33.8%->-38.2%
#                月波动12.6%下,8%阈值在噪音带内,月均触发49%
#   - 无排名缓冲带: 缓冲带在价值型打分上制造价值陷阱(越跌bp越高→永不卖出)
#                  全区间超额 +3.3% -> -2.3%, 回撤 -36% -> -53%
#   - 无MA60仓位择时: 使超额IR 0.49->0.08。且因子alpha在MA60下方更强
#                    (月均+0.693% vs 上方+0.360%), 与择时方向相反
#   - 月频硬重排本身就是风控: 基本面恶化→ROE降→排名落→自然换出
#   - 不做缺失值中性填充: 缺失即剔除(ep缺失填0.5会把亏损股拉到中位)
#   - 权重锁定50/50: 样本内最优是roe70/bp30(IS_IR 1.35),但其样本外IR仅0.06
#                   IS/OOS排序相关性 -0.815, 参数优化在此问题上是有害的
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd


def initialize(context):
    set_benchmark('000852.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # 免5 + 万0.85 (按实际账户设置)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.000085, close_commission=0.000085,
        close_today_commission=0, min_commission=0
    ), type='stock')

    g.index_code = '000852.XSHG'

    # ---- 选股参数 ----
    g.n_hold = 40                  # 持仓数. 10万->2500元/仓, 50万->12500元/仓
    g.mom_window = 40              # 动量回看天数
    g.mom_exclude_top = 0.20       # 剔除动量最高的比例
    g.w_quality = 0.50             # ROE 权重
    g.w_value = 0.50               # BP 权重
    g.min_list_days = 120
    g.winsor_mad = 5               # MAD去极值倍数

    # ---- 调仓 ----
    g.rebalance_interval = 20      # 交易日
    g.days_since_rebalance = g.rebalance_interval   # 首日即调仓

    # ---- 监控(告警用,不自动减仓) ----
    g.nav_peak = 0
    g.monthly_nav = []             # [(date, 策略净值, 基准净值)]

    # 待卖出队列: 停牌/跌停导致卖单失败的股票, 每日重试直至清空
    g.pending_sells = set()

    # 10:00 执行而非09:35 —— 开盘5分钟价差最宽,滑点占总成本63%
    run_daily(daily_process, time='10:00')
    run_monthly(monthly_report, monthday=1, time='14:50')


# ============================================================
# 工具
# ============================================================

def is_tradable(stock, cd, current_date):
    """可交易过滤: 未停牌/非ST/未涨停/上市满120日"""
    d = cd[stock]
    if d.paused or d.is_st:
        return False
    if not (d.low_limit < d.last_price < d.high_limit):
        return False
    info = get_security_info(stock)
    if info is None:
        return False
    return (current_date - info.start_date).days >= g.min_list_days


def winsorize_mad(s):
    med = s.median()
    mad = (s - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return s
    scale = g.winsor_mad * 1.4826 * mad
    return s.clip(med - scale, med + scale)


def zscore(s):
    sd = s.std()
    if not sd or np.isnan(sd):
        return s * 0.0
    return (s - s.mean()) / sd


def neutralize(s, industry, ln_mcap):
    """截面回归取残差: s ~ 行业哑变量 + ln(市值)。剔除行业与市值暴露。"""
    df = pd.concat([s.rename('y'), industry.rename('ind'),
                    ln_mcap.rename('mc')], axis=1, sort=False).dropna()
    if len(df) < 30 or df['ind'].nunique() < 2:
        return pd.Series(np.nan, index=s.index)
    dummies = pd.get_dummies(df['ind'], drop_first=True).astype(float)
    X = np.column_stack([np.ones(len(df)), df['mc'].values, dummies.values])
    beta, _, _, _ = np.linalg.lstsq(X, df['y'].values, rcond=None)
    resid = df['y'].values - X.dot(beta)
    return pd.Series(resid, index=df.index).reindex(s.index)


# ============================================================
# 选股
# ============================================================

def select_stocks(context):
    """返回目标持仓列表。数据不足时返回 None(本次不调仓)。"""
    prev_date = context.previous_date
    cd = get_current_data()
    today = context.current_dt.date()

    pool = get_index_stocks(g.index_code, date=prev_date)
    pool = [s for s in pool if is_tradable(s, cd, today)]
    if len(pool) < 100:
        log.warn('可交易池仅%d只, 跳过调仓' % len(pool))
        return None

    # ---- 1. 动量硬排除 ----
    closes = history(g.mom_window + 1, '1d', 'close', pool, df=True)
    if len(closes) < g.mom_window + 1:
        log.warn('价格历史不足, 跳过调仓')
        return None
    mom = (closes.iloc[-1] / closes.iloc[0] - 1).dropna()
    if len(mom) < 100:
        return None
    keep_n = int(len(mom) * (1 - g.mom_exclude_top))
    survivors = list(mom.sort_values().index[:keep_n])   # 升序取前80%,剔除动量最高20%

    # ---- 2. 基本面 ----
    fd = get_fundamentals(
        query(valuation.code, valuation.pb_ratio, valuation.market_cap,
              indicator.roe).filter(valuation.code.in_(survivors)),
        date=prev_date
    )
    if fd is None or fd.empty:
        log.warn('财务数据为空, 跳过调仓')
        return None
    fd = fd.set_index('code')

    pb = fd['pb_ratio'].where(fd['pb_ratio'] > 0)
    mc = fd['market_cap'].where(fd['market_cap'] > 0)
    raw = pd.DataFrame({
        'roe': fd['roe'],
        'bp': 1.0 / pb,
        'ln_mcap': np.log(mc),
    }).dropna()                      # 缺失即剔除,不做中性填充
    if len(raw) < 100:
        log.warn('有效因子数据仅%d只, 跳过调仓' % len(raw))
        return None

    # ---- 3. 行业 ----
    ind_info = get_industry(list(raw.index), date=prev_date)
    industry = pd.Series({c: v.get('sw_l1', {}).get('industry_code', 'NA')
                          for c, v in ind_info.items()})
    industry = industry.reindex(raw.index)

    # ---- 4. 去极值 -> 中性化 -> 标准化 -> 加权 ----
    score = None
    for col, w in [('roe', g.w_quality), ('bp', g.w_value)]:
        f = zscore(winsorize_mad(raw[col]))
        f = neutralize(f, industry, raw['ln_mcap']).dropna()
        if len(f) < 100:
            log.warn('%s 中性化后仅%d只, 跳过调仓' % (col, len(f)))
            return None
        f = zscore(f) * w
        score = f if score is None else score.add(f, fill_value=None).dropna()

    if score is None or len(score) < g.n_hold:
        return None

    coverage = float(len(score)) / len(pool)
    if coverage < 0.60:
        log.warn('因子覆盖率仅%.0f%%, 数据可能异常' % (coverage * 100))

    # 多取候选: 单仓约 总资产/n_hold, 一手价超过它的股票会被向下取整成0股
    # (10万/40 -> 约3000元 -> 股价>30元买不起)。多备候选以补足到真正 n_hold 只。
    return list(score.sort_values(ascending=False).index[:g.n_hold * 2])


# ============================================================
# 调仓
# ============================================================

def flush_pending_sells(context):
    """每日重试卖出失败的股票(停牌/跌停当日无法成交)。"""
    if not g.pending_sells:
        return
    done = set()
    for stock in list(g.pending_sells):
        if stock not in context.portfolio.positions:
            done.add(stock)
            continue
        order_target_value(stock, 0)
        pos = context.portfolio.positions.get(stock)
        if pos is None or pos.total_amount == 0:
            done.add(stock)
    g.pending_sells -= done
    if g.pending_sells:
        log.info('待卖出未成交 %d 只, 次日重试: %s'
                 % (len(g.pending_sells), ','.join(sorted(g.pending_sells))))


def place_buys(context, targets, scale):
    """按 总资产*scale/n_hold 下单。scale>1 用于抵补整数倍向下取整的欠配。"""
    tv = context.portfolio.total_value * scale / float(g.n_hold)
    for stock in targets:
        order_target_value(stock, tv)


def pick_affordable(context, ranked, target_value):
    """按排名顺序挑出"一手买得起"的前 n_hold 只。

    聚宽下单按100股向下取整, 一手价(股价*100)超过单仓目标值的股票会被
    取整成0股而静默落空(实测建仓仅36-37/40, 且系统性排除高价股)。
    故按排名往下顺延, 补足到真正 n_hold 只。
    """
    cd = get_current_data()
    picked, skipped = [], 0
    for stock in ranked:
        if len(picked) >= g.n_hold:
            break
        price = cd[stock].last_price
        if not price or price <= 0 or np.isnan(price):
            continue
        if price * 100 > target_value:      # 一手就超预算 -> 顺延
            skipped += 1
            continue
        picked.append(stock)
    if skipped:
        log.info('跳过%d只一手超预算(>%.0f元)的高价股, 按排名顺延'
                 % (skipped, target_value / 100))
    return picked


def rebalance(context, ranked):
    """月频硬性重排: 卖出所有落榜股, 买入所有新入选股, 等权。

    聚宽下单按 100 股向下取整, 单笔平均欠配约 12%, 会造成长期低仓位
    (实测 Beta 仅 0.829)。故买入分多轮, 逐步放大目标值吃掉闲置现金。
    """
    total = context.portfolio.total_value
    base_target = total / float(g.n_hold)
    # 门槛按放大后的目标值判断: 买入会多轮放大以抵补整数倍欠配(实测系数1.23),
    # 若用未放大的 base_target 会把25~31元区间本可买入的股票也排除掉。
    targets = pick_affordable(context, ranked, base_target * 1.25)
    if len(targets) < g.n_hold * 0.8:
        log.warn('可买标的仅%d只(目标%d), 本次不调仓' % (len(targets), g.n_hold))
        return
    g.pending_sells -= set(targets)

    held = set(context.portfolio.positions.keys())
    target_set = set(targets)

    # ---- 先卖, 释放现金; 失败的进入重试队列 ----
    to_sell = held - target_set
    sold = 0
    for stock in to_sell:
        order_target_value(stock, 0)
        pos = context.portfolio.positions.get(stock)
        if pos is None or pos.total_amount == 0:
            sold += 1
        else:
            g.pending_sells.add(stock)

    # ---- 后买, 多轮放大以消除整数倍欠配 ----
    scale = 1.0
    place_buys(context, targets, scale)
    for _ in range(3):
        idle = context.portfolio.available_cash / total if total else 0
        if idle < 0.015:
            break
        scale += idle * 0.95
        place_buys(context, targets, scale)

    filled = len([s for s in targets if s in context.portfolio.positions
                  and context.portfolio.positions[s].total_amount > 0])
    idle_pct = context.portfolio.available_cash / total * 100 if total else 0
    log.info('调仓完成 | 卖出%d/%d(待重试%d) | 建仓%d/%d | 持仓%d | 闲置现金%.1f%% | 放大系数%.3f'
             % (sold, len(to_sell), len(g.pending_sells), filled, g.n_hold,
                len(context.portfolio.positions), idle_pct, scale))


def daily_process(context):
    # 每日优先清理卖出失败的持仓, 防止组合漂移超过 n_hold
    flush_pending_sells(context)

    g.days_since_rebalance += 1
    if g.days_since_rebalance < g.rebalance_interval:
        return

    ranked = select_stocks(context)
    if ranked is None:
        return                      # 数据异常时保持原持仓,不空仓

    rebalance(context, ranked)
    g.days_since_rebalance = 0


# ============================================================
# 监控与死亡条件
# ============================================================
# 注意: 全部为"告警 + 人工复核", 不做自动清仓。
# 依据: 8%移动止损测试显示价格型减仓使 IR 0.44->0.06、回撤 -33.8%->-38.2%
#       市场级回撤在所有持仓上同向, 减仓只是兑现回撤并错过反弹。
#       同样的逻辑适用于账户层回撤熔断, 故不实现自动熔断。

def monthly_report(context):
    total = context.portfolio.total_value
    g.nav_peak = max(g.nav_peak, total)
    drawdown = total / g.nav_peak - 1 if g.nav_peak else 0

    bench_px = attribute_history(g.index_code, 1, '1d', ['close'])['close'].iloc[-1]
    g.monthly_nav.append((context.current_dt.date(), total, bench_px))

    log.info('=' * 62)
    log.info('月报 | 总资产 %.0f | 持仓 %d/%d | 现金 %.0f | 回撤 %.1f%%'
             % (total, len(context.portfolio.positions), g.n_hold,
                context.portfolio.available_cash, drawdown * 100))

    # 滚动超额(12个月/24个月)
    for months, level in [(12, '告警'), (24, '建议停用')]:
        if len(g.monthly_nav) > months:
            d0, nav0, b0 = g.monthly_nav[-months - 1]
            d1, nav1, b1 = g.monthly_nav[-1]
            excess = (nav1 / nav0) - (b1 / b0)
            if excess < 0:
                log.warn('[死亡条件-%s] 滚动%d个月超额 %.2f%% < 0 (%s~%s)'
                         % (level, months, excess * 100, d0, d1))

    # 绝对回撤告警(历史最差 -33.8%)
    if drawdown < -0.35:
        log.warn('[死亡条件-告警] 回撤 %.1f%% 已超历史最差(-33.8%%), 请人工复核因子有效性'
                 % (drawdown * 100))
    log.info('=' * 62)
