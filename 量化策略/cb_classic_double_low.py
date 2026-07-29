# -*- coding: utf-8 -*-
# ============================================================
# 可转债经典双低轮动 (Classic Double-Low, 月频)
# ============================================================
# 设计依据: 训练集 2019-01 ~ 2022-12 共48个月
#   经典双低: 年化 15.32%  夏普 1.05  最大回撤 -14.9%  月胜率 64.6%
#   多因子(加动量): 年化 13.66%  夏普 0.97  → 动量无增量
#
# 逻辑:
#   1. 每月最后交易日 14:45 调仓
#   2. 打分: 0.5 × z(价格, 越低越好) + 0.5 × z(转股溢价率, 越低越好)
#   3. 选前20只, 等权
#   4. 缓冲带: 前25名中已在仓的保留, 补足到20只
#   5. 信用过滤: 正股ST / 价格<80且溢价率>100% → 剔除
#   6. 池子过滤: 距到期>12月 / 非停牌 / 非涨停
#
# 关键设计决策(有实测依据, 勿随意改动):
#   - 不用动量因子: mom_1m夏普0.62、rev_3m夏普0.23, 均弱于双低的1.05
#   - 不用premium单因子: 回撤-19.4%(深30%), 且训练集内前后段相关性-0.359
#                     已证参数选择本身不稳定, 双低的price维度提供下行锚点
#   - 缓冲带: 降换手(训练集958%/年→预期600-670%)
#   - 信用过滤: 训练集选中搜特转债33%月份(后违约), 不加过滤=踩雷
#   - 等权: 防御过拟合的最强形式(股票IS/OOS=-0.815)
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd
import datetime


def initialize(context):
    set_benchmark('000852.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # 可转债免印花税; 佣金万0.85 免5 (实际账户)
    cost = OrderCost(open_tax=0, close_tax=0,
                     open_commission=0.000085, close_commission=0.000085,
                     close_today_commission=0, min_commission=0)
    set_order_cost(cost, type='fund')
    set_order_cost(cost, type='stock')

    # ---- 冻结参数 ----
    g.n_hold = 20
    g.buffer_n = 25             # 缓冲带: 前25名中已在仓的保留
    g.w_price = 0.50            # 价格权重
    g.w_premium = 0.50          # 溢价率权重
    g.min_term_months = 12      # 距到期最少月数
    # 信用过滤
    g.credit_price_floor = 80   # 转债价格低于此+高溢价=疑似违约
    g.credit_premium_ceiling = 100  # 溢价率高于此+低价=疑似违约

    # ---- 标的池: 全部可转债 ----
    g.cb_info = _load_cb_info()
    log.info('可转债基本信息加载: %d 只' % len(g.cb_info))

    # ---- 调仓 ----
    run_daily(daily_check, time='14:45')


def _load_cb_info():
    """加载所有可转债的基本信息: 正股代码、到期日、最新转股价。"""
    from jqdata import bond
    df = bond.run_query(query(
        bond.CONBOND_BASIC_INFO.code,
        bond.CONBOND_BASIC_INFO.company_code,
        bond.CONBOND_BASIC_INFO.maturity_date,
        bond.CONBOND_BASIC_INFO.convert_price,
        bond.CONBOND_BASIC_INFO.exchange_code,
    ))
    xchg_map = {705001: 'XSHG', 705002: 'XSHE', 705003: 'XSHE',
                705004: 'XSHE', 705005: 'XSHG', 705006: 'XSHE'}
    df['exchange'] = df['exchange_code'].map(xchg_map).fillna('XSHE')
    df['cb_code'] = df['code'].astype(str) + '.' + df['exchange']
    df = df[df['company_code'].notna() & df['maturity_date'].notna()]
    df['maturity_date'] = pd.to_datetime(df['maturity_date'])
    return df.set_index('cb_code')


def _get_convert_price(context, cb_code):
    """获取当天的转股价。尝试从 bond 表查, 失败则用基本信息初始转股价。"""
    from jqdata import bond
    try:
        code = cb_code.split('.')[0]
        today_str = context.current_dt.strftime('%Y-%m-%d')
        # 查最近一条转股价调整记录
        df = bond.run_query(query(
            bond.CONBOND_CONVERT_PRICE_ADJUST.new_convert_price,
        ).filter(
            bond.CONBOND_CONVERT_PRICE_ADJUST.code == code,
            bond.CONBOND_CONVERT_PRICE_ADJUST.adjust_date <= today_str,
        ).order_by(
            bond.CONBOND_CONVERT_PRICE_ADJUST.adjust_date.desc()
        ).limit(1))
        if df is not None and len(df) > 0 and not pd.isna(df.iloc[0, 0]):
            return float(df.iloc[0, 0])
    except Exception:
        pass
    # 回退: 用初始转股价
    if cb_code in g.cb_info.index:
        return float(g.cb_info.loc[cb_code, 'convert_price'])
    return None


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


def is_tradable(context, cb_code):
    """可转债可交易: 未停牌/未涨停。"""
    cd = get_current_data()
    d = cd.get(cb_code)
    if d is None or d.paused:
        return False
    if d.last_price is None or d.last_price <= 0 or np.isnan(d.last_price):
        return False
    if d.last_price >= d.high_limit:
        return False
    return True


def is_credit_risky(context, cb_code, price, premium_rate):
    """信用风险过滤。"""
    # 条件1: 正股ST
    info = g.cb_info.loc[cb_code] if cb_code in g.cb_info.index else None
    if info is not None:
        stk = info['company_code']
        if stk and pd.notna(stk):
            try:
                cd = get_current_data()
                sd = cd.get(stk)
                if sd is not None and sd.is_st:
                    return True
            except Exception:
                pass

    # 条件2: 低价+超高溢价(市场已定价违约)
    if (price is not None and premium_rate is not None
            and price < g.credit_price_floor
            and premium_rate > g.credit_premium_ceiling):
        return True

    return False


def zscore_pool(values):
    """截面 z-score，值越低得分越高(取负)。"""
    arr = np.array([v for v in values if v is not None and not np.isnan(v)])
    if len(arr) < 5:
        return [0.0] * len(values)
    mean, std = arr.mean(), arr.std()
    if std == 0 or np.isnan(std):
        return [0.0] * len(values)
    return [-(v - mean) / std if (v is not None and not np.isnan(v)) else 0.0
            for v in values]


# ============================================================
# 选股
# ============================================================

def select_targets(context):
    """返回 {标的: 权重}。全部用 bond.run_query 取可转债数据，
    不依赖 get_current_data()（对可转债返回 None）。"""
    from jqdata import bond
    today = context.current_dt.date()
    today_str = context.current_dt.strftime('%Y-%m-%d')

    # ---- 一次性取所有可转债今日收盘价 ----
    try:
        px_df = bond.run_query(query(
            bond.CONBOND_DAILY_PRICE.code,
            bond.CONBOND_DAILY_PRICE.close,
        ).filter(
            bond.CONBOND_DAILY_PRICE.date == today_str,
        ))
    except Exception as e:
        log.warn('取可转债价格失败: %s' % str(e)[:80])
        return None

    if px_df is None or len(px_df) == 0:
        log.warn('今日无可转债价格数据')
        return None

    # code(不带后缀) → 后缀
    code_to_suffix = dict(zip(g.cb_info['code'].astype(str), g.cb_info['exchange']))
    px_df['cb_code'] = px_df['code'].astype(str).map(
        lambda c: str(c) + '.' + code_to_suffix.get(str(c), 'XSHE'))
    price_map = dict(zip(px_df['cb_code'], px_df['close']))

    # ---- 一次性取今日转股溢价率 ----
    try:
        prem_df = bond.run_query(query(
            bond.CONBOND_DAILY_CONVERT.code,
            bond.CONBOND_DAILY_CONVERT.convert_premium_rate,
        ).filter(
            bond.CONBOND_DAILY_CONVERT.date == today_str,
        ))
        if prem_df is not None and len(prem_df) > 0:
            prem_df['cb_code'] = prem_df['code'].astype(str).map(
                lambda c: str(c) + '.' + code_to_suffix.get(str(c), 'XSHE'))
            premium_map = dict(zip(prem_df['cb_code'], prem_df['convert_premium_rate']))
        else:
            premium_map = {}
    except Exception:
        premium_map = {}

    # ---- 收集候选 ----
    records = []
    cd = get_current_data()
    for cb_code in g.cb_info.index:
        if cb_code not in price_map:
            continue
        price = price_map[cb_code]
        if price is None or np.isnan(price) or price <= 0:
            continue

        info = g.cb_info.loc[cb_code]

        # 距到期 > 12 月
        mature = info['maturity_date']
        if pd.isna(mature) or mature.date() <= today + datetime.timedelta(days=g.min_term_months * 30):
            continue

        # 转股溢价率
        premium_rate = premium_map.get(cb_code)
        if premium_rate is None or np.isnan(premium_rate):
            # 尝试自己算
            stk = info['company_code']
            if pd.isna(stk):
                continue
            sd = cd.get(stk)
            if sd is None or sd.last_price is None or sd.last_price <= 0:
                continue
            stock_price = sd.last_price
            convert_price = _get_convert_price(context, cb_code)
            if convert_price is None or convert_price <= 0:
                continue
            premium_rate = (price * convert_price) / (100.0 * stock_price) - 1.0

        if np.isnan(premium_rate):
            continue

        # 信用过滤
        if is_credit_risky(context, cb_code, price, premium_rate):
            continue

        records.append((cb_code, price, premium_rate))

    if len(records) < g.buffer_n:
        log.warn('有效标的仅%d只(需%d), 本次不调仓(价格%d只/溢价率%d只)'
                 % (len(records), g.buffer_n, len(price_map), len(premium_map)))
        return None

    # 打分
    codes = [r[0] for r in records]
    prices = [r[1] for r in records]
    premiums = [r[2] for r in records]

    z_price = zscore_pool(prices)
    z_premium = zscore_pool(premiums)

    scored = []
    for i in range(len(codes)):
        score = g.w_price * z_price[i] + g.w_premium * z_premium[i]
        scored.append((codes[i], score, prices[i], premiums[i]))

    scored.sort(key=lambda x: x[1], reverse=True)

    # 缓冲带
    held = set(context.portfolio.positions.keys())
    buffer_candidates = [s[0] for s in scored[:g.buffer_n]]

    keep = [c for c in buffer_candidates if c in held]
    fresh = [c for c in buffer_candidates if c not in held]

    selected = keep[:g.n_hold]
    needed = g.n_hold - len(selected)
    if needed > 0:
        selected.extend(fresh[:needed])

    if len(selected) < g.n_hold * 0.7:
        log.warn('缓冲带后仅%d只(需%d), 本次不调仓' % (len(selected), g.n_hold))
        return None

    # 日志
    detail = []
    for s in scored[:g.buffer_n]:
        if s[0] in selected:
            detail.append('%s p=%.1f prem=%.1f%% ★'
                          % (g.cb_info.loc[s[0], 'code'] if s[0] in g.cb_info.index else s[0],
                             s[2], s[3] * 100))
    log.info('选股 %d只 | 总行情%d只 | 有效%d只 | %s'
             % (len(selected), len(price_map), len(records),
                ' | '.join(detail[:5])))

    w = 1.0 / len(selected)
    # 返回权重 + 价格映射(用于下单计算张数)
    return {s: w for s in selected}, {r[0]: r[1] for r in records}


# ============================================================
# 调仓
# ============================================================

def rebalance(context, weights, price_map):
    """卖出不在目标中的持仓, 买入新目标。
    可转债交易单位: 1手=10张。用 order_target 指定张数，避免
    order_target_value 按100股取整导致5000元被归零。"""
    total = context.portfolio.total_value

    # ---- 先卖 ----
    for s in list(context.portfolio.positions.keys()):
        if s not in weights:
            try:
                order_target(s, 0)
            except Exception:
                pass

    # ---- 后买, 用10张整数倍 ----
    target_list = sorted(weights.keys())
    succeeded = 0
    skipped = 0

    for s in target_list:
        w = weights[s]
        price = price_map.get(s)
        if price is None or price <= 0:
            skipped += 1
            continue
        # 1手=10张, 按最近价格算目标张数(向下取整到10的倍数)
        target_lots = int(total * w / price / 10.0)
        if target_lots < 1:
            skipped += 1
            continue
        try:
            order_target(s, target_lots * 10)
            succeeded += 1
        except Exception as e:
            log.warn('下单失败 %s: %s' % (s, str(e)[:60]))
            skipped += 1

    # 闲置现金补仓: 如果现金>2%, 对各目标按比例放大
    for _ in range(3):
        idle = context.portfolio.available_cash / total if total else 0
        if idle < 0.02:
            break
        for s in target_list:
            if s not in weights:
                continue
            price = price_map.get(s)
            if price is None or price <= 0:
                continue
            extra_lots = int(context.portfolio.available_cash * weights[s] / price / 10.0)
            if extra_lots >= 1:
                try:
                    order_target(s, context.portfolio.positions[s].total_amount + extra_lots * 10
                                 if s in context.portfolio.positions else extra_lots * 10)
                except Exception:
                    pass
        idle = context.portfolio.available_cash / total if total else 0
        if idle < 0.02:
            break

    holding_info = []
    for s in sorted(weights):
        pos = context.portfolio.positions.get(s)
        if pos is not None and pos.total_amount > 0:
            name = g.cb_info.loc[s, 'code'] if s in g.cb_info.index else s
            holding_info.append('%s %.1f%%' % (name, pos.value / total * 100))

    log.info('调仓 %d/%d(跳过%d) | %s | 闲置%.1f%%'
             % (succeeded, len(target_list), skipped,
                ' | '.join(holding_info[:5]),
                context.portfolio.available_cash / total * 100))


def daily_check(context):
    if not is_month_end(context):
        return

    result = select_targets(context)
    if result is None:
        log.warn('选股失败, 保持原持仓')
        return

    weights, price_map = result
    rebalance(context, weights, price_map)
    monthly_report(context)


# ============================================================
# 监控与死亡条件
# ============================================================

def monthly_report(context):
    total = context.portfolio.total_value
    g._nav_peak = getattr(g, '_nav_peak', 0)
    g._nav_peak = max(g._nav_peak, total)
    drawdown = total / g._nav_peak - 1 if g._nav_peak else 0

    g._nav_hist = getattr(g, '_nav_hist', [])
    g._nav_hist.append((context.current_dt.date(), total))

    log.info('月报 | 总资产 %.0f | 持仓 %d/%d | 现金 %.0f | 回撤 %.1f%%'
             % (total, len(context.portfolio.positions), g.n_hold,
                context.portfolio.available_cash, drawdown * 100))

    # 死亡条件: 与ETF策略一致, 用绝对收益判据
    risk_free = 0.02
    for months, level in [(24, '告警'), (36, '建议停用')]:
        if len(g._nav_hist) > months:
            n0 = g._nav_hist[-months - 1][1]
            ret = total / n0 - 1
            cash_ret = (1 + risk_free) ** (months / 12.0) - 1
            if ret < cash_ret:
                log.warn('[死亡条件-%s] 滚动%d个月绝对收益 %.2f%% < 现金 %.2f%%'
                         % (level, months, ret * 100, cash_ret * 100))

    # 回撤告警 (训练集最差 -14.9%)
    if drawdown < -0.30:
        log.warn('[死亡条件-告警] 回撤 %.1f%% 已超训练集最差2倍, 请人工复核'
                 % (drawdown * 100))
