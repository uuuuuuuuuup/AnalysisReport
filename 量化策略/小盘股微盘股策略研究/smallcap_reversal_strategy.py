# -*- coding: utf-8 -*-
# ============================================================
# 小盘股反转轮动策略 v2 (Small-Cap Reversal + Momentum Confirmation)
# 平台: BigQuant AI Studio | 纯脚本计算（无回测引擎）
# ============================================================
# v1 问题: 纯反转=接飞刀, 训练集年化-19%, 33倍换手
#
# v2 修复:
#   1. 动量确认: 只买"跌得多+已开始反弹"的股票
#      - 反转因子: 过去20日跌幅（选跌得多的）
#      - 动量确认: 过去5日收益>0（已经在反弹中）
#   2. 市场择时: 大盘弱势时降仓
#      - 基准: 中证1000(000852)
#      - 规则: 基准20日收益<-5% → 仓位降至50%
#              基准20日收益<-10% → 清仓
#   3. 双周调仓(每10个交易日): 降低换手
#   4. 止损: 个股持仓期间跌幅>15% → 强制卖出
#
# 数据划分:
#   训练集 2019-01 ~ 2023-12 (5年)
#   ──────────── 数据墙 ────────────
#   测试集 2024-01 ~ 2026-07 (2.5年)
# ============================================================

import dai
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 冻结参数
# ============================================================
N_HOLD = 20              # 持仓数量
BUFFER_N = 25            # 缓冲带候选池
REBALANCE_DAYS = 10      # 调仓频率: 10个交易日=双周频
REVERSAL_PERIOD = 20     # 反转回看: 20个交易日=1月
MOMENTUM_PERIOD = 5      # 动量确认: 5个交易日=1周
VOLATILITY_PERIOD = 20   # 波动率计算窗口
TURNOVER_PERIOD = 20     # 换手率均值窗口
MIN_LIST_DAYS = 60       # 上市天数下限
CAP_PERCENTILE = 0.30    # 小市值域: 后30%
STOP_LOSS = -0.15        # 个股止损线: -15%

# 复合因子权重
W_REVERSAL = 0.50        # 反转因子权重
W_TURNOVER = 0.25        # 低换手因子权重
W_VOLATILITY = 0.25      # 低波动因子权重

# 市场择时参数
BENCHMARK = '000852.SH'  # 中证1000
MARKET_WEAK_THRESHOLD = -0.05    # 基准20日收益<-5% → 半仓
MARKET_CRASH_THRESHOLD = -0.10   # 基准20日收益<-10% → 清仓
MARKET_LOOKBACK = 20             # 基准回看天数

# 数据划分
TRAIN_START = '2019-01-01'
TRAIN_END   = '2023-12-31'
TEST_START  = '2024-01-01'
TEST_END    = '2026-07-29'

# 当前使用训练集
START_DATE = TRAIN_START
END_DATE   = TRAIN_END

# 成本假设
COMMISSION_BUY = 0.0003
COMMISSION_SELL = 0.0013
SLIPPAGE = 0.001


# ============================================================
# 数据加载
# ============================================================
def load_data(start_date, end_date):
    """加载全部所需数据"""
    print('加载数据 %s ~ %s ...' % (start_date, end_date))

    sql = """
    SELECT
        p.date, p.instrument, p.close, p.volume,
        p.turn AS turnover_ratio, p.open, p.high, p.low,
        v.total_market_cap AS market_cap,
        v.float_market_cap AS circulating_market_cap
    FROM cn_stock_bar1d p
    INNER JOIN cn_stock_valuation v
        ON p.date = v.date AND p.instrument = v.instrument
    INNER JOIN cn_stock_prefactors f
        ON p.date = f.date AND p.instrument = f.instrument
    WHERE
        p.close > 0
        AND p.volume > 0
        AND f.st_status = 0
        AND f.suspended = 0
        AND f.list_days >= %d
        AND f.list_sector NOT IN (3, 4)
    ORDER BY p.date, p.instrument
    """ % MIN_LIST_DAYS

    df = dai.query(sql, filters={"date": [start_date, end_date]}).df()
    df['date'] = pd.to_datetime(df['date'])

    print('加载完成: %d 行, %d 标的, %s ~ %s'
          % (len(df), df['instrument'].nunique(),
             df['date'].min().strftime('%Y-%m-%d'),
             df['date'].max().strftime('%Y-%m-%d')))

    return df


def compute_benchmark_from_stocks(df):
    """从已有股票数据计算市场基准收益（全A等权平均收益）
    
    BigQuant 无 cn_index_bar1d 表，改用股票池本身计算市场状态。
    每日全A等权收益 = 市场宽度的代理指标，比单指数更稳健。
    """
    print('从股票池计算市场基准...')

    # 每日等权平均收益
    grouped = df.groupby('date')
    daily_ret = grouped['close'].apply(lambda x: x.pct_change().mean() if len(x) > 100 else np.nan)
    daily_ret = daily_ret.dropna()

    # 累计收益
    bm = pd.DataFrame(index=daily_ret.index)
    bm['close'] = (1 + daily_ret).cumprod()

    print('基准: %d 天' % len(bm))
    return bm


# ============================================================
# 因子计算
# ============================================================
def compute_factors(df):
    """计算策略所需的全部因子"""
    print('计算因子...')

    grouped = df.groupby('instrument')

    # ---- 反转因子: 过去20日收益率取负（跌得多→得分高）----
    df['reversal'] = grouped['close'].transform(
        lambda x: -(x / x.shift(REVERSAL_PERIOD) - 1)
    )

    # ---- 动量确认: 过去5日收益率（已反弹→正数）----
    df['momentum'] = grouped['close'].transform(
        lambda x: x / x.shift(MOMENTUM_PERIOD) - 1
    )

    # ---- 波动率因子: 取负=低波动得分高 ----
    df['daily_ret'] = grouped['close'].transform(lambda x: x.pct_change())
    df['volatility'] = grouped['daily_ret'].transform(
        lambda x: -x.rolling(VOLATILITY_PERIOD, min_periods=10).std()
    )

    # ---- 换手率因子: 取负=低换手得分高 ----
    df['turnover'] = grouped['turnover_ratio'].transform(
        lambda x: -x.rolling(TURNOVER_PERIOD, min_periods=10).mean()
    )

    # ---- 市值排名（每日截面）----
    df['cap_rank'] = df.groupby('date')['circulating_market_cap'].transform(
        lambda x: x.rank(pct=True, na_option='keep')
    )

    # ---- 个股持仓成本（用于止损）----
    # 将在回测中跟踪

    print('因子计算完成')
    return df


# ============================================================
# 策略回测
# ============================================================
def run_backtest(df, bm):
    """运行策略回测，返回净值曲线和统计指标"""

    price_matrix = df.pivot(index='date', columns='instrument', values='close')
    all_dates = price_matrix.index.sort_values()

    nav = [1.0]
    nav_dates = [all_dates[0]]
    holdings = {}          # {instrument: weight}
    entry_prices = {}      # {instrument: entry_price} 用于止损
    day_count = 0
    trade_count = 0
    total_cost = 0.0
    cash_ratio = 1.0       # 现金比例（市场择时控制）

    monthly_returns = []
    last_nav = 1.0
    last_month = None

    # 市场择时状态
    market_regime = 'normal'   # normal / weak / crash

    print('回测中...')

    for i, date in enumerate(all_dates):
        # ---- 市场择时判断 ----
        if date in bm.index:
            bm_loc = bm.index.get_loc(date)
            if bm_loc >= MARKET_LOOKBACK:
                bm_ret = bm['close'].iloc[bm_loc] / bm['close'].iloc[bm_loc - MARKET_LOOKBACK] - 1
                if bm_ret < MARKET_CRASH_THRESHOLD:
                    market_regime = 'crash'
                    cash_ratio = 0.0   # 清仓
                elif bm_ret < MARKET_WEAK_THRESHOLD:
                    market_regime = 'weak'
                    cash_ratio = 0.5   # 半仓
                else:
                    market_regime = 'normal'
                    cash_ratio = 1.0   # 满仓

        # ---- 市场crash时强制清仓 ----
        if market_regime == 'crash' and len(holdings) > 0:
            old_set = set(holdings.keys())
            trade_count += len(old_set)
            cost = len(old_set) / N_HOLD * (COMMISSION_SELL + SLIPPAGE)
            total_cost += cost
            nav.append(nav[-1] * (1 - cost))
            nav_dates.append(date)
            holdings = {}
            entry_prices = {}
            continue

        # ---- 个股止损检查 ----
        if holdings and i > 0:
            prev_date = all_dates[i - 1]
            cur_prices = price_matrix.loc[date]

            stopped = []
            for inst in list(holdings.keys()):
                if inst in cur_prices.index and inst in entry_prices:
                    cp = cur_prices[inst]
                    ep = entry_prices[inst]
                    if not pd.isna(cp) and ep > 0:
                        if cp / ep - 1 < STOP_LOSS:
                            stopped.append(inst)

            if stopped:
                for inst in stopped:
                    del holdings[inst]
                    if inst in entry_prices:
                        del entry_prices[inst]
                trade_count += len(stopped)

        # ---- 调仓日判断 ----
        day_count += 1
        should_rebalance = (day_count % REBALANCE_DAYS == 0)

        if should_rebalance:
            cur = df[df['date'] == date].copy()

            # ---- 小市值域 ----
            cur = cur[cur['cap_rank'] <= CAP_PERCENTILE]

            # ---- 动量确认: 只保留已在反弹的股票 ----
            cur = cur[cur['momentum'] > 0]

            if len(cur) < N_HOLD:
                # 反弹股不够, 保持现有持仓不变
                nav.append(nav[-1])
                nav_dates.append(date)
                continue

            # ---- 去除因子缺失 ----
            cur = cur.dropna(subset=['reversal', 'volatility', 'turnover'])

            if len(cur) < N_HOLD:
                nav.append(nav[-1])
                nav_dates.append(date)
                continue

            # ---- Z-score 标准化 ----
            for col in ['reversal', 'volatility', 'turnover']:
                s = cur[col]
                mean, std = s.mean(), s.std()
                cur[col + '_z'] = (s - mean) / std if std > 0 else 0.0

            # ---- 复合打分 ----
            cur['score'] = (W_REVERSAL * cur['reversal_z'] +
                           W_TURNOVER * cur['turnover_z'] +
                           W_VOLATILITY * cur['volatility_z'])

            cur = cur.sort_values('score', ascending=False)

            # ---- 缓冲带选股 ----
            top_pool = cur.head(BUFFER_N)['instrument'].tolist()
            held_set = set(holdings.keys())

            keep = [s for s in top_pool if s in held_set]
            fresh = [s for s in top_pool if s not in held_set]

            # 按市场择时调整目标持仓数
            target_n = int(N_HOLD * cash_ratio)
            if target_n < 5:
                # 弱市持仓太少, 清仓
                if len(holdings) > 0:
                    old_set = set(holdings.keys())
                    trade_count += len(old_set)
                    cost = len(old_set) / N_HOLD * (COMMISSION_SELL + SLIPPAGE)
                    total_cost += cost
                    holdings = {}
                    entry_prices = {}
                nav.append(nav[-1])
                nav_dates.append(date)
                continue

            selected = keep[:target_n] + fresh[:max(0, target_n - len(keep))]

            if len(selected) < target_n * 0.7:
                nav.append(nav[-1])
                nav_dates.append(date)
                continue

            # ---- 计算换手成本 ----
            old_set = set(holdings.keys())
            new_set = set(selected)
            sell_count = len(old_set - new_set)
            buy_count = len(new_set - old_set)
            trade_count += sell_count + buy_count

            cost = (sell_count + buy_count) / (2 * N_HOLD) * (COMMISSION_BUY + COMMISSION_SELL + 2 * SLIPPAGE)
            total_cost += cost

            # 更新持仓
            w = 1.0 / len(selected)
            holdings = {s: w for s in selected}

            # 更新入场价格
            cur_prices = price_matrix.loc[date]
            for inst in selected:
                if inst in cur_prices.index:
                    entry_prices[inst] = cur_prices[inst]

        # ---- 计算当日收益 ----
        if holdings and i > 0:
            prev_date = all_dates[i - 1]
            cur_prices = price_matrix.loc[date]
            prev_prices = price_matrix.loc[prev_date]

            daily_return = 0.0
            valid_count = 0

            for inst, weight in holdings.items():
                if inst in cur_prices.index and inst in prev_prices.index:
                    cp = cur_prices[inst]
                    pp = prev_prices[inst]
                    if not pd.isna(cp) and not pd.isna(pp) and pp > 0:
                        daily_return += (cp / pp - 1) * weight
                        valid_count += 1

            if valid_count >= len(holdings) * 0.5:
                daily_cost = cost / REBALANCE_DAYS if should_rebalance else 0
                nav.append(nav[-1] * (1 + daily_return - daily_cost))
            else:
                nav.append(nav[-1])
        else:
            nav.append(nav[-1] if nav else 1.0)

        nav_dates.append(date)

        # 月度收益
        current_month = pd.Timestamp(date).strftime('%Y-%m')
        if last_month is not None and current_month != last_month:
            monthly_return = (nav[-2] / last_nav - 1) if len(nav) >= 2 and last_nav > 0 else 0
            monthly_returns.append(monthly_return)
            last_nav = nav[-1]
        elif last_month is None:
            last_nav = nav[-1]
        last_month = current_month

    # ---- 统计指标 ----
    nav_series = pd.Series(nav, index=pd.DatetimeIndex(nav_dates))

    total_days = len(nav_series)
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    annual_return = (1 + total_return) ** (252 / total_days) - 1 if total_days > 0 else 0

    daily_returns = nav_series.pct_change().dropna()
    annual_volatility = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0
    sharpe = (annual_return - 0.03) / annual_volatility if annual_volatility > 0 else 0

    cummax = nav_series.cummax()
    drawdown = (nav_series - cummax) / cummax
    max_drawdown = drawdown.min()

    monthly_returns_s = pd.Series(monthly_returns)
    win_rate = (monthly_returns_s > 0).sum() / len(monthly_returns_s) if len(monthly_returns_s) > 0 else 0

    rebalance_count = day_count // REBALANCE_DAYS
    avg_turnover_per_rebalance = trade_count / (2 * N_HOLD * max(1, rebalance_count))
    annual_turnover = avg_turnover_per_rebalance * (252 / REBALANCE_DAYS)

    stats = {
        'annual_return': annual_return,
        'annual_volatility': annual_volatility,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'total_return': total_return,
        'rebalance_count': rebalance_count,
        'annual_turnover': annual_turnover,
        'total_cost': total_cost,
    }

    return nav_series, stats


# ============================================================
# 分年度分析
# ============================================================
def analyze_by_year(nav_series):
    """分年度统计策略表现"""
    results = []

    for year in sorted(nav_series.index.year.unique()):
        year_nav = nav_series[nav_series.index.year == year]
        if len(year_nav) < 20:
            continue

        year_return = year_nav.iloc[-1] / year_nav.iloc[0] - 1
        daily_ret = year_nav.pct_change().dropna()
        year_vol = daily_ret.std() * np.sqrt(252) if len(daily_ret) > 0 else 0
        year_sharpe = (year_return - 0.03 * len(year_nav) / 252) / year_vol if year_vol > 0 else 0

        cummax = year_nav.cummax()
        max_dd = ((year_nav - cummax) / cummax).min()

        results.append({
            '年份': year,
            '收益': f'{year_return:.1%}',
            '波动': f'{year_vol:.1%}',
            '夏普': f'{year_sharpe:.2f}',
            '最大回撤': f'{max_dd:.1%}',
        })

    return pd.DataFrame(results)


# ============================================================
# 主程序
# ============================================================
def main():
    print('=' * 60)
    print('小盘股反转轮动策略 v2 - 训练集回测')
    print('=' * 60)
    print('v2 修复: 反转+动量确认 + 市场择时 + 双周调仓 + 止损')
    print('训练集: %s ~ %s' % (TRAIN_START, TRAIN_END))
    print('测试集: %s ~ %s (冻结，当前不使用)' % (TEST_START, TEST_END))
    print()

    # 加载数据
    df = load_data(START_DATE, END_DATE)
    # 计算因子
    df = compute_factors(df)

    # 从股票池计算市场基准
    bm = compute_benchmark_from_stocks(df)

    # 回测
    nav, stats = run_backtest(df, bm)

    # 输出结果
    print('\n' + '=' * 60)
    print('回测结果（训练集）')
    print('=' * 60)
    print('年化收益:   %.2f%%' % (stats['annual_return'] * 100))
    print('年化波动:   %.2f%%' % (stats['annual_volatility'] * 100))
    print('夏普比率:   %.2f' % stats['sharpe'])
    print('最大回撤:   %.2f%%' % (stats['max_drawdown'] * 100))
    print('月胜率:     %.1f%%' % (stats['win_rate'] * 100))
    print('总收益:     %.2f%%' % (stats['total_return'] * 100))
    print('调仓次数:   %d' % stats['rebalance_count'])
    print('年化换手:   %.1f倍' % stats['annual_turnover'])

    # 分年度
    print('\n' + '=' * 60)
    print('分年度表现')
    print('=' * 60)
    year_df = analyze_by_year(nav)
    print(year_df.to_string(index=False))

    # 保存净值曲线
    nav_df = nav.reset_index()
    nav_df.columns = ['date', 'nav']
    nav_df.to_csv('smallcap_reversal_nav.csv', index=False)
    print('\n净值曲线已保存: smallcap_reversal_nav.csv')

    return nav, stats


if __name__ == '__main__':
    nav, stats = main()