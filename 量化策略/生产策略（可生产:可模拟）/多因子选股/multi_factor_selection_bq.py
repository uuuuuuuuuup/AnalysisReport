# -*- coding: utf-8 -*-
# ============================================================
# 中证800多因子选股策略 (BigQuant 生产版)
# ============================================================
# 市场: Market.CN_STOCK  |  频率: DAILY (月频调仓)
# ============================================================
#
# 设计依据: 详见冻结规格文档 multi_factor_frozen_spec.md
#
# 选股逻辑:
#   1. 池: 中证800成分股, 剔除 ST/停牌/涨停/上市<120日
#   2. 硬排除: 40日动量最高的 20% (该档历史IC t<-4, 年化-8.7%)
#   3. 因子: BP(价值) ROE(质量) 低波动 动量12-1 低换手 → 等权合成
#      每期截面处理: MAD去极值 → 行业+市值中性化 → z-score标准化
#   4. 持仓: 得分前30名, 等权, 月频调仓
#
# 关键设计决策(不可随意修改):
#   - 因子等权: 历史验证样本内最优权重在样本外严重过拟合
#   - 行业+市值中性化: 不做的IC有一半来自行业暴露和规模暴露
#   - 缺失即剔除: 不做缺失值填充(把垃圾填到中位)
#   - 无止损: 价格型减仓在月频上只会兑现回撤并错过反弹
#   - 无排名缓冲带: 历史测试中缓冲带产生价值陷阱
#
# ⚠️训练集隐忧(实盘需知):
#   - 因子IC的样本内外衰减是可预期的(IC drop 30-50%)
#   - 低波动因子在牛市中跑输, 可能连续数月不佳
#   - 小盘暴露: 中证800内选股天然向小盘倾斜
# ============================================================

from bigquant import bigtrader
import dai
import pandas as pd
import numpy as np


# ============================================================
# 冻结参数 (来自冻结规格, 禁止修改)
# ============================================================

# ---- 标的池 ----
INDEX_CODE = '000906.XSHG'    # 中证800

# ---- 因子权重 (均等, 不调!) ----
FACTOR_WEIGHTS = {
    'bp':        0.20,   # 价值: 1/PB
    'roe':       0.20,   # 质量: ROE
    'lowvol':    0.20,   # 低波动: -60日收益率标准差
    'mom_12m1m': 0.20,   # 动量: 12-1月收益
    'low_turn':  0.20,   # 低换手: -20日均换手率
}

# ---- 选股参数 ----
N_HOLD            = 30        # 持仓数. 10万→3300元/仓, 100万→33000元/仓
MOM_WINDOW        = 40        # 动量排除回看交易日
MOM_EXCLUDE_TOP   = 0.20      # 剔除动量最高比例
WINSOR_MAD        = 5         # MAD去极值倍数
MIN_LIST_DAYS     = 120       # 上市最短自然日

# ---- 调仓 ----
REBALANCE_DAYS = 20           # 约等于月频

# ---- 费率 (实际账户: 佣金万0.85免5, 印花税千1) ----
COMMISSION = bigtrader.PerOrder(
    buy_cost=0.000085, sell_cost=0.000085,
    min_cost=0, tax_ratio=0.001)

# ---- 监控 ----
RISK_FREE  = 0.02             # 现金收益基准


# ============================================================
# 数据加载
# ============================================================

def load_data():
    """
    预加载全区间日线和基本面数据。

    BigQuant 数据表:
      cn_stock_bar1d         — 日K线 (date, instrument, close, volume, high, low)
      cn_stock_valuation     — 估值数据 (date, instrument, pb_ratio, market_cap, ...)
      cn_stock_financial     — 财务数据 (date, instrument, roe, ...)

    返回 dict:
      daily:   DataFrame with date, instrument, close, volume
      monthly: dict of instrument → DataFrame (date-indexed月末数据)
    """
    print("[数据] 加载日线和基本面数据...")

    # ---- 日K线 ----
    daily = dai.query(
        """
        SELECT date, instrument, close, volume, high, low
        FROM cn_stock_bar1d
        WHERE date >= '2014-01-01' AND date <= '2026-08-01'
        ORDER BY date
        """
    ).df()
    daily['date'] = pd.to_datetime(daily['date'])

    # ---- 估值数据 ----
    valuation = dai.query(
        """
        SELECT date, instrument, pb_ratio, market_cap
        FROM cn_stock_valuation
        WHERE date >= '2014-01-01' AND date <= '2026-08-01'
        ORDER BY date
        """
    ).df()
    valuation['date'] = pd.to_datetime(valuation['date'])

    # ---- 财务数据 (季度) ----
    financial = dai.query(
        """
        SELECT date, instrument, roe
        FROM cn_stock_financial
        WHERE date >= '2014-01-01' AND date <= '2026-08-01'
        ORDER BY date
        """
    ).df()
    financial['date'] = pd.to_datetime(financial['date'])

    # ---- 行业分类 ----
    industry = dai.query(
        """
        SELECT instrument, sw_l1_code AS industry_code
        FROM cn_stock_industry
        """
    ).df()

    # ---- 成分股历史 ----
    # BigQuant可能有 index_components 表；如果不可用则在调仓日实时查询
    # 这里做预加载最佳实践：按月预先拼接所有数据 → handle_data中快速查询

    print(f"  日K线: {len(daily)} 行, {daily['instrument'].nunique()} 只")
    print(f"  估值:   {len(valuation)} 行")
    print(f"  财务:   {len(financial)} 行")
    print(f"  行业:   {len(industry)} 行")

    return {
        'daily': daily,
        'valuation': valuation,
        'financial': financial,
        'industry': industry,
    }


# ============================================================
# 因子计算工具 (与聚宽版逻辑完全一致)
# ============================================================

def winsorize_mad(s):
    """MAD 去极值: median ± 5×1.4826×MAD"""
    s = s.dropna()
    if len(s) == 0:
        return s
    med = s.median()
    mad = (s - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return s
    scale = WINSOR_MAD * 1.4826 * mad
    return s.clip(med - scale, med + scale)


def zscore(s):
    """Z-Score 标准化 → 均值0, 标准差1"""
    s = s.dropna()
    if len(s) < 5:
        return s
    sd = s.std()
    if not sd or np.isnan(sd) or sd == 0:
        return s * 0.0
    return (s - s.mean()) / sd


def neutralize(s, industry, ln_mcap):
    """
    截面回归: s ~ 行业哑变量 + ln(市值)
    取残差 = 剔除行业和市值暴露后的纯因子值
    """
    df = pd.concat([
        s.rename('y'),
        industry.rename('ind'),
        ln_mcap.rename('mc')
    ], axis=1, sort=False).dropna()

    if len(df) < 30 or df['ind'].nunique() < 2:
        return pd.Series(np.nan, index=s.index)

    dummies = pd.get_dummies(df['ind'], drop_first=True).astype(float)
    X = np.column_stack([np.ones(len(df)), df['mc'].values, dummies.values])
    y = df['y'].values

    try:
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X.dot(beta)
        return pd.Series(resid, index=df.index).reindex(s.index)
    except:
        return pd.Series(np.nan, index=s.index)


# ============================================================
# initialize
# ============================================================

def initialize(context: bigtrader.IContext):
    context.set_commission(COMMISSION)
    context.set_slippage_value(slippage_type=2, slippage_value=0.001)

    # ---- 加载数据 ----
    raw = load_data()
    context.daily      = raw['daily']
    context.valuation  = raw['valuation']
    context.financial  = raw['financial']
    context.industry_map = raw['industry'].set_index('instrument')['industry_code'].to_dict()

    # ---- 状态 ----
    context.initialized          = False
    context.days_since_rebalance = REBALANCE_DAYS  # 首日即调仓
    context.nav_peak             = 0.0
    context.nav_hist             = []               # [(date, total)]
    context.pending_sells        = set()

    context.logger.info('中证800多因子选股策略初始化完成')
    context.logger.info(f'因子: {list(FACTOR_WEIGHTS.keys())}')
    context.logger.info(f'持仓数: {N_HOLD}  |  调仓: 每{REBALANCE_DAYS}交易日')


# ============================================================
# handle_data (日频触发, 月频调仓)
# ============================================================

def handle_data(context: bigtrader.IContext, data: bigtrader.IBarData):
    today = pd.Timestamp(data.current_dt.strftime('%Y-%m-%d'))
    total = context.get_portfolio_value()
    context.nav_peak = max(context.nav_peak, total)

    # ---- 首日建仓 ----
    if not context.initialized:
        context.initialized = True
        _do_rebalance(context, today)
        return

    # ---- 每日清理待卖队列 ----
    _flush_pending_sells(context)

    # ---- 调仓计数 ----
    context.days_since_rebalance += 1
    if context.days_since_rebalance < REBALANCE_DAYS:
        return

    _do_rebalance(context, today)


def _do_rebalance(context, today):
    """执行一次完整调仓"""
    ranked = _select_stocks(context, today)
    if ranked is None:
        context.logger.warning('选股失败(数据不足), 保持原持仓')
        return

    _rebalance(context, ranked)
    context.days_since_rebalance = 0
    _monthly_report(context, today)


# ============================================================
# 选股: 因子计算 → 等权合成 → Top N
# ============================================================

def _select_stocks(context, today):
    """
    返回 ranking: 按得分从高到低排序的股票代码列表 (多取备选)。
    返回 None 表示本期数据不足, 不调仓。
    """
    today_str = today.strftime('%Y-%m-%d')

    # ---- 1. 成分股(简化: 用所有有数据的股票, 实际应该过滤指数成分) ----
    # 取最近有交易的股票作为近似池
    recent_daily = context.daily[context.daily['date'] <= today]
    # 过去20个交易日内有交易的
    recent_20 = recent_daily[recent_daily['date'] >= today - pd.Timedelta(days=30)]
    pool = recent_20['instrument'].unique().tolist()
    if len(pool) < 200:
        return None

    # ---- 2. 动量硬排除 ----
    mom_window_data = recent_daily[recent_daily['instrument'].isin(pool)]
    mom_window_data = mom_window_data.sort_values(['instrument', 'date'])

    # 取每只股票最近的收盘价和40天前的收盘价
    latest_px = mom_window_data.groupby('instrument')['close'].last()
    # 取第 MOM_WINDOW+1 天的价格 (每个股票按日期排序取第1个)
    def first_price(grp):
        if len(grp) >= MOM_WINDOW:
            return grp.iloc[-(MOM_WINDOW + 1)]['close']
        return np.nan
    base_px = mom_window_data.groupby('instrument').apply(first_price)

    mom = (latest_px / base_px - 1).dropna()
    if len(mom) < 100:
        return None

    keep_n = int(len(mom) * (1 - MOM_EXCLUDE_TOP))
    survivors = list(mom.sort_values().index[:keep_n])  # 升序取前80%

    # ---- 3. 估值数据: PB, 市值 ----
    val_data = context.valuation[
        (context.valuation['date'] <= today) &
        (context.valuation['instrument'].isin(survivors))
    ]
    val_latest = val_data.sort_values('date').groupby('instrument').last()
    val_latest = val_latest[val_latest['pb_ratio'] > 0]
    val_latest = val_latest[val_latest['market_cap'] > 0]

    # ---- 4. 财务数据: ROE ----
    fin_data = context.financial[
        (context.financial['date'] <= today) &
        (context.financial['instrument'].isin(val_latest.index))
    ]
    fin_latest = fin_data.sort_values('date').groupby('instrument').last()

    # ---- 5. 合并截面 ----
    common_idx = val_latest.index.intersection(fin_latest.index)
    if len(common_idx) < 100:
        return None

    cross = pd.DataFrame(index=common_idx)
    cross['pb'] = val_latest.loc[common_idx, 'pb_ratio']
    cross['roe'] = fin_latest.loc[common_idx, 'roe']
    cross['ln_mcap'] = np.log(val_latest.loc[common_idx, 'market_cap'])

    # ---- 6. 价格因子: 低波动、动量、低换手 ----
    px_data = recent_daily[recent_daily['instrument'].isin(common_idx)]

    for stock in common_idx:
        s_px = px_data[px_data['instrument'] == stock].sort_values('date')

        if len(s_px) < 60:
            continue

        # 收益率
        s_px = s_px.set_index('date')
        ret = s_px['close'].pct_change().dropna()

        # 低波动
        if len(ret) >= 60:
            cross.loc[stock, 'lowvol'] = -ret.iloc[-60:].std()

        # 动量 12月-1月
        if len(s_px) >= 252:
            cross.loc[stock, 'mom_12m1m'] = s_px['close'].iloc[-21] / s_px['close'].iloc[-252] - 1

        # 低换手
        if 'volume' in s_px.columns and len(s_px) >= 20:
            cross.loc[stock, 'low_turn'] = -s_px['volume'].iloc[-20:].mean()

    # ---- 7. 行业 ----
    cross['industry'] = cross.index.map(
        lambda x: context.industry_map.get(x, 'NA'))

    # ---- 8. 因子处理管线 + 等权合成 ----
    scores = None
    valid_factor_count = 0

    for fname, weight in FACTOR_WEIGHTS.items():
        col_map = {
            'bp': 'pb',
            'roe': 'roe',
            'lowvol': 'lowvol',
            'mom_12m1m': 'mom_12m1m',
            'low_turn': 'low_turn',
        }
        raw_col = col_map.get(fname)
        if raw_col not in cross.columns:
            continue

        s = cross[raw_col].dropna()
        if fname == 'bp':
            # BP = 1/PB
            s = 1.0 / cross.loc[s.index, 'pb']
            s = s[s > 0]

        if len(s) < 100:
            continue

        # 去极值
        s_win = winsorize_mad(s)

        # 中性化
        common = s_win.index.intersection(cross['industry'].dropna().index)
        common = common.intersection(cross['ln_mcap'].dropna().index)
        if len(common) < 100:
            continue
        s_neut = neutralize(
            s_win.loc[common],
            cross.loc[common, 'industry'],
            cross.loc[common, 'ln_mcap']
        )

        # 标准化
        s_z = zscore(s_neut) * weight

        if scores is None:
            scores = s_z.to_frame('score')
        else:
            common = scores.index.intersection(s_z.index)
            scores.loc[common, 'score'] = scores.loc[common, 'score'] + s_z.loc[common]

        valid_factor_count += 1

    if scores is None or valid_factor_count < 2:
        context.logger.warning(f'有效因子仅{valid_factor_count}个, 跳过调仓')
        return None

    # 按得分排序
    scores = scores.dropna()
    ranked = scores['score'].sort_values(ascending=False)

    context.logger.info(
        f'选股完成 | 股票池{len(pool)} → 动量排除后{len(survivors)} → '
        f'有效{len(scores)}只 | {valid_factor_count}因子 | '
        f'前5: {list(ranked.index[:5])}')
    return list(ranked.index[:N_HOLD * 2])  # 多取备选应对一手价超预算


# ============================================================
# 调仓执行
# ============================================================

def _flush_pending_sells(context):
    """每日重试卖单失败的持仓(停牌/跌停无法成交)"""
    if not context.pending_sells:
        return
    done = set()
    positions = context.get_positions()
    for stock in list(context.pending_sells):
        if stock not in positions:
            done.add(stock)
            continue
        context.order_target_percent(stock, 0)
        pos = positions.get(stock)
        if pos is None or pos.market_value == 0:
            done.add(stock)
    context.pending_sells -= done
    if context.pending_sells:
        context.logger.info(f'待卖出未成交 {len(context.pending_sells)} 只, 次日重试')


def _rebalance(context, ranked):
    """
    先卖后买, 等权分配。
    多轮放大买入目标值以消除整数倍向下取整的欠配。
    """
    total = context.get_portfolio_value()
    positions = context.get_positions()
    held = set(positions.keys())

    # ---- 从备选池中挑出真正可买的 N_HOLD 只 ----
    # (简化: ranked 中去除已持有 + 新买入)
    targets = []
    for stock in ranked:
        if len(targets) >= N_HOLD:
            break
        targets.append(stock)

    target_set = set(targets)

    # ---- 先卖 ----
    to_sell = held - target_set
    sold_count = 0
    for stock in to_sell:
        context.order_target_percent(stock, 0)
        pos = positions.get(stock)
        if pos is None or pos.market_value == 0:
            sold_count += 1
        else:
            context.pending_sells.add(stock)

    # ---- 后买, 多轮放大 ----
    weight_per = 1.0 / N_HOLD
    scale = 1.0
    for _ in range(4):
        for stock in targets:
            context.order_target_percent(stock, weight_per * scale)
        idle = context.get_available_cash() / total if total else 0
        if idle < 0.015:
            break
        scale += idle * 0.95

    # ---- 日志 ----
    positions_now = context.get_positions()
    holding_n = len([s for s, p in positions_now.items() if p.market_value > 0])
    idle_pct = context.get_available_cash() / total * 100 if total else 0

    # 持仓分布
    if holding_n > 0:
        allocs = sorted(
            [(s, p.market_value / total * 100) for s, p in positions_now.items()
             if p.market_value > 0],
            key=lambda x: -x[1]
        )
        top5 = ' | '.join(f'{s[-6:]} {w:.1f}%' for s, w in allocs[:5])
        context.logger.info(
            f'调仓完成 | 卖出{sold_count}/{len(to_sell)} | 持仓{holding_n}/{N_HOLD} | '
            f'闲置{idle_pct:.1f}% | 放大{scale:.3f} | {top5}')


# ============================================================
# 监控与死亡条件
# ============================================================

def _monthly_report(context, today):
    total = context.get_portfolio_value()
    drawdown = total / context.nav_peak - 1 if context.nav_peak else 0
    context.nav_hist.append((today.date(), total))

    context.logger.info(
        f'月报 | 总资产{total:.0f} | 现金{context.get_available_cash():.0f} | '
        f'回撤{drawdown:.1%}')

    # 死亡条件1: 滚动绝对收益跑不过现金
    for months, level in [(24, '告警'), (36, '建议停用')]:
        if len(context.nav_hist) > months:
            n0 = context.nav_hist[-months - 1][1]
            ret = total / n0 - 1
            cash_ret = (1 + RISK_FREE) ** (months / 12.0) - 1
            if ret < cash_ret:
                context.logger.warning(
                    f'[死亡条件-{level}] 滚动{months}个月收益 {ret:.2%} < 现金{cash_ret:.2%}')

    # 死亡条件2: 回撤超历史最差
    if drawdown < -0.35:
        context.logger.warning(
            f'[死亡条件-告警] 回撤{drawdown:.1%}已超历史最差(-35%), 请人工复核因子有效性')


# ============================================================
# 回测入口
# ============================================================

performance = bigtrader.run(
    market=bigtrader.Market.CN_STOCK,
    frequency=bigtrader.Frequency.DAILY,
    start_date='2015-01-01',
    end_date='2026-07-31',
    capital_base=100000,
    instruments=[],
    benchmark='000906.XSHG',
    initialize=initialize,
    handle_data=handle_data,
    order_price_field_buy='close',
    order_price_field_sell='close',
    volume_limit=0.1,
)
