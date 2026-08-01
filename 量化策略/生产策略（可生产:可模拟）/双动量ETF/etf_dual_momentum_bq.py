# -*- coding: utf-8 -*-
# ============================================================
# 多资产 ETF 动量轮动 (Dual Momentum, 月频)  — BigQuant 版
# 平台: BigQuant BigTrader  |  市场: Market.CN_STOCK
# ============================================================
# 独立纯双动量版本 (100% 资金投入), 非三引擎合并版。
# 三引擎合并版见 ../unified_etf_engine_bq.py (Engine1+Engine3, 共用65%资金)。
#
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
#   1. 每月最后一个交易日 (新月首日触发) 调仓
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

from bigquant import bigtrader
import dai
import pandas as pd
import numpy as np


# ============================================================
# 冻结参数 (与聚宽版 / 月度调仓脚本完全一致, 禁止修改)
# ============================================================

# ---- 标的池: 每个都有事前的资产配置理由 ----
ETF_UNIVERSE = [
    '510300.SH',   # 沪深300  A股大盘
    '510500.SH',   # 中证500  A股中盘
    '159915.SZ',   # 创业板    A股成长
    '510880.SH',   # 红利      防御风格
    '588000.XSHG',   # 科创50     A股成长
    '513100.SH',   # 纳指      海外分散
    '518880.SH',   # 黄金      实物资产
]
ETF_SAFE = '511010.SH'          # 国债ETF: 绝对动量为负时的避险仓

# ---- 名称映射 (日志用) ----
NAMES = {
    '510300.SH': '沪深300', '510500.SH': '中证500',
    '159915.SZ': '创业板',  '510880.SH': '红利',
    '513100.SH': '纳指',    '518880.SH': '黄金',
    '588000.XSHG': '科创50',
}

# ---- 冻结参数 ----
ETF_K      = 6                 # 动量回看月数
ETF_M      = 2                 # 持仓数
ETF_ABS    = True              # 绝对动量过滤

# ---- 通用 ----
BENCHMARK  = '000852.SH'       # 中证1000
RISK_FREE  = 0.02              # 死亡条件用的现金收益基准(货币基金/短债约2%)

# ---- 费率 (实际账户: 佣金万0.85免5, ETF免印花税) ----
COMMISSION = bigtrader.PerOrder(
    buy_cost=0.000085, sell_cost=0.000085,
    min_cost=0, tax_ratio=0)


# ============================================================
# initialize
# ============================================================

def initialize(context: bigtrader.IContext):
    context.set_commission(COMMISSION)
    context.set_slippage_value(slippage_type=2, slippage_value=0.0005)

    # ---- 加载 ETF 历史日线 (cn_fund_bar1d, 不是 cn_stock_bar1d!) ----
    all_etfs = ETF_UNIVERSE + [ETF_SAFE]
    df = dai.query(
        "SELECT date, instrument, close FROM cn_fund_bar1d ORDER BY date",
        filters={"date": ["2014-01-01", "2026-07-29"], "instrument": all_etfs}
    ).df()
    df['date'] = pd.to_datetime(df['date'])

    # 预计算: 按标的+年月分组, 保存月末收盘价便于快速查询
    df['ym'] = df['date'].dt.strftime('%Y-%m')
    month_end = df.groupby(['ym', 'instrument'])['close'].last().reset_index()
    # 为每个标的建立 month→close 映射
    etf_monthly = {}
    for s in all_etfs:
        me = month_end[month_end['instrument'] == s].set_index('ym')['close']
        etf_monthly[s] = me

    context.etf_monthly = etf_monthly
    context.etf_daily = df  # 用于取最新价格

    context.logger.info('ETF 数据加载: %d 标的, %d 行, %s ~ %s'
                        % (len(all_etfs), len(df),
                           df['date'].min().strftime('%Y-%m-%d'),
                           df['date'].max().strftime('%Y-%m-%d')))

    # ---- 状态 ----
    context.initialized   = False   # 首日建仓标志
    context.nav_peak      = 0.0
    context.nav_hist      = []      # 月末总资产序列 [(date, total)]
    context.last_ym       = None    # 上次调仓的年月, 避免同月重复

    context.logger.info('ETF 双动量策略 (独立版 100%%资金) 初始化完成')


# ============================================================
# handle_data  (日频触发)
# ============================================================

def handle_data(context: bigtrader.IContext, data: bigtrader.IBarData):
    today    = pd.Timestamp(data.current_dt.strftime('%Y-%m-%d'))
    today_ym = today.strftime('%Y-%m')
    total    = context.get_portfolio_value()
    context.nav_peak = max(context.nav_peak, total)

    # ============ 首日建仓 ============
    # 首日: 不直接买入, 等待第一个月末判断, 保证信号基于完整 K 个月月末价
    if not context.initialized:
        context.initialized = True
        context.last_ym = today_ym
        return

    # ============ 月末调仓 ============
    # 判断条件: 年月变化 (跨月时即为新月首日, 等价于"上个月刚结束")
    if today_ym == context.last_ym:
        return

    context.last_ym = today_ym
    weights = _select_targets(context, today)
    if weights is None:
        _monthly_report(context, today)
        return                           # 数据异常时保持原持仓

    _rebalance(context, weights, total)
    _monthly_report(context, today)


# ============================================================
# Engine 1: ETF 动量选股
# ============================================================

def _select_targets(context, today):
    """
    6个月动量排名 → 选 top-ETF_M, 绝对动量<0 的切国债。
    返回 {instrument: weight (总资产百分比, 如 0.5=50%)}, 或 None (数据不足跳过)。
    """
    today_ym = today.strftime('%Y-%m')
    current_prices = {}

    # 当前价 = 预加载日线中 <=today 的最后一根收盘价 (替代聚宽 get_current_data.last_price)
    for s in ETF_UNIVERSE:
        d = context.etf_daily
        cur = d[(d['instrument'] == s) & (d['date'] <= today)]
        if len(cur) > 0:
            current_prices[s] = cur['close'].iloc[-1]

    mom = {}
    for s in ETF_UNIVERSE:
        if s not in current_prices:
            continue
        me = context.etf_monthly.get(s)
        if me is None:
            continue
        # 只用当月之前的月末数据
        me = me[me.index < today_ym].sort_index()
        if len(me) < ETF_K:
            continue
        base = me.iloc[-ETF_K]
        if pd.isna(base) or base <= 0:
            continue
        px = current_prices[s]
        if pd.isna(px) or px <= 0:
            continue
        mom[s] = px / base - 1.0

    if len(mom) < ETF_M:
        context.logger.warning('ETF 动量: 仅 %d 个可用 (需 %d), 本月不调仓'
                               % (len(mom), ETF_M))
        return None

    ranked = sorted(mom.items(), key=lambda kv: kv[1], reverse=True)
    picks = []
    for s, m in ranked[:ETF_M]:
        if ETF_ABS and m <= 0:
            picks.append(ETF_SAFE)
        else:
            picks.append(s)

    w = {}
    for s in picks:
        w[s] = w.get(s, 0.0) + 1.0 / ETF_M

    detail = ' | '.join('%s %+.1f%%' % (NAMES.get(s, s), m * 100)
                        for s, m in ranked)
    context.logger.info('%d月动量排名: %s' % (ETF_K, detail))
    context.logger.info('本月持仓: %s'
                        % ', '.join('%s %.0f%%' % (NAMES.get(s, s), w[s] * 100)
                                    for s, _ in sorted(w.items(), key=lambda kv: -kv[1])))
    return w


# ============================================================
# 月末调仓执行
# ============================================================

def _rebalance(context, weights, total):
    """卖出不在目标中的持仓, 再按权重买入。多轮放大消除 ETF 整数倍欠配。

    ETF 一手100份, 国债ETF单价约110元(一手约1.1万), 会造成向下取整欠配。
    故买入分多轮放大目标值, 吃掉闲置现金。
    """
    # ---- 先卖 ----
    positions = context.get_positions()
    for s in list(positions.keys()):
        if s not in weights:
            context.order_target_percent(s, 0)

    # ---- 后买, 多轮放大消除整数倍欠配 ----
    scale = 1.0
    for _ in range(4):
        for s, w in weights.items():
            if w > 0:
                context.order_target_percent(s, w * scale)
        idle = context.get_available_cash() / total if total else 0
        if idle < 0.015:
            break
        scale += idle * 0.95

    # ---- 日志 ----
    positions = context.get_positions()
    holding = ' | '.join(
        '%s %.1f%%' % (NAMES.get(s, s), p.market_value / total * 100)
        for s, p in sorted(positions.items()) if p.market_value > 0
    )
    context.logger.info('调仓完成 | %s | 闲置现金 %.1f%% | 放大系数 %.3f'
                        % (holding,
                           context.get_available_cash() / total * 100,
                           scale))


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

def _monthly_report(context, today):
    total = context.get_portfolio_value()
    drawdown = total / context.nav_peak - 1 if context.nav_peak else 0
    context.nav_hist.append((today.date(), total))

    context.logger.info('月报 | 总资产 %.0f | 现金 %.0f | 回撤 %.1f%%'
                        % (total, context.get_available_cash(), drawdown * 100))

    # 死亡条件1: 滚动绝对收益跑不过现金
    # 训练集年化8.54%、测试集5.43%; 无风险约2%。长期低于现金即失去存在意义。
    for months, level in [(24, '告警'), (36, '建议停用')]:
        if len(context.nav_hist) > months:
            n0 = context.nav_hist[-months - 1][1]
            ret = total / n0 - 1
            cash_ret = (1 + RISK_FREE) ** (months / 12.0) - 1
            if ret < cash_ret:
                context.logger.warning(
                    '[死亡条件-%s] 滚动%d个月绝对收益 %.2f%% < 现金 %.2f%%'
                    % (level, months, ret * 100, cash_ret * 100))

    # 死亡条件2: 回撤超训练集最差的2倍(训练集 -14.98%, 测试集 -19.46%)
    if drawdown < -0.30:
        context.logger.warning(
            '[死亡条件-告警] 回撤 %.1f%% 已超训练集最差(-14.98%%)的2倍, '
            '风险特征与历史不符, 请人工复核' % (drawdown * 100))


# ============================================================
# 回测入口
# ============================================================

performance = bigtrader.run(
    market=bigtrader.Market.CN_STOCK,
    frequency=bigtrader.Frequency.DAILY,
    start_date='2015-10-01',
    end_date='2026-07-29',
    capital_base=100000,
    instruments=ETF_UNIVERSE + [ETF_SAFE],
    benchmark=BENCHMARK,
    initialize=initialize,
    handle_data=handle_data,
    order_price_field_buy='close',
    order_price_field_sell='close',
    volume_limit=0.1,
)
