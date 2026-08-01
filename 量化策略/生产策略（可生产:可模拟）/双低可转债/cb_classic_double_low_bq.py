# -*- coding: utf-8 -*-
# ============================================================
# Engine 2: 可转债经典双低轮动 (Classic Double-Low, 月频)
# 平台: BigQuant BigTrader  |  市场: Market.CN_CBOND
# ============================================================
# ⚠️ 三引擎合并: 本脚本独立运行在 Market.CN_CBOND,
#   用 merge_three_engine.py 与 unified_etf_engine_bq.py 合并净值。
#   合并公式: 合并NAV = ETF_NAV + 0.35 × CB_NAV - 35,000
#
# 设计依据: 训练集 2019-01 ~ 2022-12 共48个月
#   经典双低: 年化 15.32%  夏普 1.05  最大回撤 -14.9%  月胜率 64.6%
#   BigQuant回测(2019-01~2024-09): 年化 15.02% 夏普 0.77 回撤 -31.4%
#   回撤恶化因2023-2024可转债首次违约(搜特/蓝盾), 实盘须按-31%做心理准备
#
# 逻辑 (严格对齐 monthly_rebalance.py 实盘调仓版 + frozen spec):
#   1. 每月最后一个交易日调仓 (对齐 frozen spec, 不再用每22天)
#   2. 过滤顺序 (对齐 frozen spec):
#      上市≥30天 & 距到期>12月 → 信用过滤(close<80∩premium>100剔除)
#      → ST正股剔除 → 强赎预警(转股价值≥130剔除) → 近似已公告强赎剔除
#   3. 双低打分: 0.5×z(close) + 0.5×z(premium_rate), 值越低越好
#   4. 选前20只, 等权
#   5. 缓冲带: 前25名中已在仓的保留, 补足到20只
#
# ⚠️ 数据权限修复 (2026-08-01):
#   原方案使用 cn_cbond_analyze_metric.conversion_premium_rate (需标准版付费权限)
#   现改为: 通过多张免费表 + 手动计算转股溢价率 ——
#     转股价值 = 100 ÷ 转股价 × 正股收盘价
#     转股溢价率 = (转债收盘价 ÷ 转股价值 - 1) × 100%
#   免费数据表:
#     - cn_cbond_bar1d       (Beta免费): 可转债日行情 close + 正股代码 stock_code
#     - cn_cbond_basic_info  (Alpha免费): 基本信息 maturity_date / list_date / stock_code / stock_name
#     - cn_cbond_conversion  (免费):     转股价 conversion_clause_price
#     - cn_stock_bar1d       (免费):     正股日行情 close (用于算转股价值/溢价率)
#     - cn_stock_static_data (Beta免费): 正股ST状态 st_status (硬约束: 必须过滤ST/*ST正股)
#     - cn_cbond_redemption  (Alpha免费): 赎回条款 (用于近似「已公告强赎」判断)
# ============================================================

from bigquant import bigtrader
import dai
import pandas as pd
import numpy as np

# ---- 冻结参数 (对齐 monthly_rebalance.py + frozen spec) ----
N_HOLD = 20                       # CB_N_HOLD
BUFFER_N = 25                     # CB_BUFFER_N
W_PRICE = 0.50                    # CB_W_PRICE
W_PREMIUM = 0.50                  # CB_W_PREMIUM
MIN_LIST_DAYS = 30                # CB_MIN_LIST_DAYS 上市满30天
MIN_TERM_MONTHS = 12              # CB_MIN_TERM 距到期月数 (>12, 注意是严格大于)
# REBALANCE_DAYS 已废弃, 改为每月最后一个交易日调仓 (见 frozen spec)
CREDIT_PRICE_FLOOR = 80           # CB_CREDIT_PRICE 信用过滤: 债价<80
CREDIT_PREMIUM_CEILING = 100      # CB_CREDIT_PREM 信用过滤:  溢价>100
REDEEM_RISK_THRESHOLD = 130       # CB_REDEEM_RISK_THRESHOLD 强赎预警线: 转股价值≥130 → 常规强赎条款触发区
# 近似「集思录已公告强赎」判定阈值 (BigQuant无集思录表, 用条款+价格组合近似):
#   1) 转股价值连续高位 >= 140 (已经超过强赎触发 130 一段距离, 有高概率已公告)
#   2) 溢价率 <= 5% (接近平价/折价, 说明强赎预期已充分定价)
REDEEM_CONFIRMED_CV = 140
REDEEM_CONFIRMED_PREM = 5.0
# ST判定兜底: 若无 st_status 字段, 用 stock_name 包含 ST/*ST 作为兜底
ST_NAME_KEYWORDS = ('ST', '*ST', 'S*ST', 'S ST', 'S*ST')
# 缓冲带最低保留比例 (原代码 70%, 保留)
MIN_KEEP_RATIO = 0.7


def initialize(context: bigtrader.IContext):
    """策略初始化。

    数据组装步骤 (严格对齐 monthly_rebalance.py 字段 + 顺序 + 过滤逻辑):
      1. 可转债主表 (cn_cbond_bar1d + cn_cbond_basic_info LEFT JOIN)
      2. 月末交易日历: 从主表date推断每月最后1个交易日, 用于调仓判断
      3. 正股ST状态 (cn_stock_static_data LEFT JOIN, 失败则用 stock_name 兜底)
      4. 转股价 (cn_cbond_conversion, 按bond取最小转股价)
      5. 正股收盘价 (cn_stock_bar1d)
      6. 计算转换价值 conversion_value + 转股溢价率 premium_rate
      7. 计算强赎近似标记 redeem_approx_confirmed
      8. 缺失/异常兜底
    """
    # ---- 账户费率 & 滑点 ----
    context.set_commission(bigtrader.PerOrder(
        buy_cost=0.000085,
        sell_cost=0.000085,
        min_cost=0,
        tax_ratio=0
    ))
    context.set_slippage_value(slippage_type=2, slippage_value=0.0005)

    DATE_START = '2019-01-01'
    DATE_END = '2026-07-29'

    # ============================================================
    # Step 1: 可转债主表 —— 行情 LEFT JOIN 基本信息
    #   LEFT JOIN 避免因为 basic_info 缺失导致的误排除 (frozen spec 约定)
    #   同时提取 stock_name 用于 ST 兜底判定
    # ============================================================
    sql_cb = """
    SELECT
        a.date, a.instrument, a.close AS bond_close, a.stock_code,
        b.maturity_date, b.list_date,
        b.name AS bond_name,
        b.stock_name
    FROM cn_cbond_bar1d a
    LEFT JOIN cn_cbond_basic_info b
        ON a.instrument = b.instrument
    WHERE
        a.close > 0
        AND b.maturity_date IS NOT NULL
    ORDER BY a.date, a.instrument
    """
    df = dai.query(sql_cb, filters={"date": [DATE_START, DATE_END]}).df()
    df['date'] = pd.to_datetime(df['date'])
    df['maturity_date'] = pd.to_datetime(df['maturity_date'])
    df['list_date'] = pd.to_datetime(df['list_date'])
    if 'stock_name' not in df.columns:
        df['stock_name'] = ''
    df['stock_name'] = df['stock_name'].fillna('').astype(str)
    context.logger.info('Step1 主表(行情+基本): %d 行, %d 只可转债'
                        % (len(df), df['instrument'].nunique()))

    # ============================================================
    # Step 2: 月末交易日历 → context.month_end_dates set (frozen spec 约束)
    #   每月最后一个交易日用于调仓触发判断 (替代原 REBALANCE_DAYS=22)
    # ============================================================
    cal = df[['date']].drop_duplicates().sort_values('date').reset_index(drop=True)
    cal['ym'] = cal['date'].dt.to_period('M')
    # 取每月最后一行
    month_end = cal.groupby('ym', as_index=False).tail(1)['date']
    context.month_end_dates = set(d.strftime('%Y-%m-%d') for d in month_end.tolist())
    context.logger.info('Step2 月末交易日: 共 %d 个 (%s ~ %s)'
                        % (len(context.month_end_dates),
                           month_end.min().strftime('%Y-%m'),
                           month_end.max().strftime('%Y-%m')))

    # ============================================================
    # Step 3: 正股ST状态过滤 (frozen spec hard constraint)
    #   优先 cn_stock_static_data.st_status; 失败则用 stock_name 关键词兜底
    # ============================================================
    df['is_st_stock'] = False  # 默认 False

    # 方案 A: 用 cn_stock_static_data 取每日 st_status
    try:
        # cn_stock_static_data: Beta免费, 每日快照, 含 st_status 字段 (0=正常,1/2=ST等)
        # 该表按 date 分区
        sql_st = """
        SELECT date, instrument AS stock_code, st_status
        FROM cn_stock_static_data
        WHERE st_status IS NOT NULL
        """
        df_st = dai.query(sql_st, filters={"date": [DATE_START, DATE_END]}).df()
        df_st['date'] = pd.to_datetime(df_st['date'])
        # 约定: st_status != 0 视作ST/*ST (参考 BigQuant 数据字典, 1/2/3/4 都是风险警示类)
        df_st['is_st_stock'] = df_st['st_status'].fillna(0).astype(int) != 0
        df_st = df_st[['date', 'stock_code', 'is_st_stock']]
        context.logger.info('Step3A cn_stock_static_data: %d 行, ST标识取表字段' % len(df_st))

        # 合并到主表
        df = df.merge(df_st, on=['date', 'stock_code'], how='left')
        # 合并后可能产生 is_st_stock_x / is_st_stock_y. 做一次统一:
        if 'is_st_stock_y' in df.columns:
            df['is_st_stock'] = df['is_st_stock_y'].fillna(df['is_st_stock_x'] if 'is_st_stock_x' in df.columns else False)
            df = df.drop(columns=[c for c in ('is_st_stock_x', 'is_st_stock_y') if c in df.columns])
        df['is_st_stock'] = df['is_st_stock'].fillna(False).astype(bool)
    except Exception as e:
        context.logger.warning('Step3A cn_stock_static_data 失败: %s, 回退用 stock_name 关键词兜底' % str(e))

    # 方案 B(兜底, 无论A是否成功都叠加): stock_name 包含 ST/*ST → 标记 True
    def _has_st_keyword(name: str) -> bool:
        if not isinstance(name, str):
            return False
        n = name.upper().strip()
        for kw in ST_NAME_KEYWORDS:
            # 用 " ST " / 开头 / 结尾 避免误匹配 "STRONG" 这类
            if n.startswith(kw) or n.endswith(kw) or (' ' + kw + ' ') in n or ('*' + kw.lstrip('*')) in n:
                return True
            if kw == 'ST' and ('ST' in n):
                # 严格一些: 字符串中出现 ST 且前后非字母
                for i in range(len(n) - 1):
                    if n[i:i+2] == 'ST':
                        before = n[i-1] if i > 0 else ' '
                        after = n[i+2] if (i+2) < len(n) else ' '
                        if not (before.isalpha() and after.isalpha()):
                            return True
        return False

    st_by_name = df['stock_name'].apply(_has_st_keyword)
    # 方案B OR 方案A: 任何一个命中都认为是 ST
    df.loc[st_by_name, 'is_st_stock'] = True
    context.logger.info('Step3B 正股ST标记: 方案A+方案B 合计标记 %d 行 / %d 行 (占比 %.2f%%)'
                        % (int(df['is_st_stock'].sum()), len(df),
                           100.0 * df['is_st_stock'].sum() / max(1, len(df))))

    # ============================================================
    # Step 4: 转股价 —— cn_cbond_conversion
    #   该表 date 字段为"转股起始日期", 非每日分区快照, 此处不加 filters
    #   同 bond 有多条取最小转股价 (保守, 对应转换价值更高, 强赎过滤更严格)
    # ============================================================
    sql_conv = """
    SELECT
        instrument,
        conversion_clause_price AS conversion_price
    FROM cn_cbond_conversion
    WHERE
        conversion_clause_price > 0
    """
    try:
        df_conv = dai.query(sql_conv).df()
        df_conv = df_conv.groupby('instrument', as_index=False)['conversion_price'].min()
        context.logger.info('Step4 转股价: %d 只可转债' % len(df_conv))
    except Exception as e:
        context.logger.warning('Step4 cn_cbond_conversion 失败: %s, 转股价将全部缺失' % str(e))
        df_conv = pd.DataFrame(columns=['instrument', 'conversion_price'])

    df = df.merge(df_conv, on='instrument', how='left')

    # ============================================================
    # Step 5: 正股收盘价 (cn_stock_bar1d 免费) —— 用于转股价值/溢价计算
    # ============================================================
    stock_list = df['stock_code'].dropna().unique().tolist()
    if stock_list:
        sql_stock = """
        SELECT date, instrument AS stock_code, close AS stock_close
        FROM cn_stock_bar1d
        WHERE close > 0
        """
        df_stock = dai.query(sql_stock, filters={"date": [DATE_START, DATE_END]}).df()
        df_stock['date'] = pd.to_datetime(df_stock['date'])
        context.logger.info('Step5 正股收盘价: %d 行, %d 只'
                            % (len(df_stock), df_stock['stock_code'].nunique()))
        df = df.merge(df_stock, on=['date', 'stock_code'], how='left')
    else:
        df['stock_close'] = np.nan
        context.logger.warning('Step5 stock_list 为空')

    # ============================================================
    # Step 6: 计算 conversion_value (转股价值) + premium_rate (转股溢价率)
    # ============================================================
    df['conversion_value'] = np.where(
        (df['conversion_price'] > 0) & (df['stock_close'] > 0),
        100.0 / df['conversion_price'] * df['stock_close'],
        np.nan
    )
    df['premium_rate'] = np.where(
        df['conversion_value'] > 0,
        (df['bond_close'] / df['conversion_value'] - 1.0) * 100.0,
        np.nan
    )

    # ---- premium_rate 兜底填充 (当日截面中位数 → 全局默认 30%) ----
    n_miss = df['premium_rate'].isna().sum()
    if n_miss > 0:
        context.logger.warning('Step6 premium_rate 缺失 %d 行, 先用当日截面中位数填充' % n_miss)
        df['premium_rate'] = df.groupby('date')['premium_rate'].transform(
            lambda x: x.fillna(x.median())
        )
        df['premium_rate'] = df['premium_rate'].fillna(30.0)

    # ---- conversion_value 兜底填充 (当日截面中位数 → 默认 100) —— 用于强赎过滤 ----
    n_cv_miss = df['conversion_value'].isna().sum()
    if n_cv_miss > 0:
        context.logger.warning('Step6 conversion_value 缺失 %d 行, 先用当日截面中位数填充' % n_cv_miss)
        df['conversion_value'] = df.groupby('date')['conversion_value'].transform(
            lambda x: x.fillna(x.median())
        )
        df['conversion_value'] = df['conversion_value'].fillna(100.0)

    # ---- 异常值修剪: premium_rate ∉ [-50%, 500%] / conversion_value 不在 [1, 400] —— 用当日截面中位数 ----
    prem_mask = (df['premium_rate'] > 500) | (df['premium_rate'] < -50)
    cv_mask = (df['conversion_value'] < 1) | (df['conversion_value'] > 400)
    if prem_mask.any() or cv_mask.any():
        context.logger.warning('Step6 异常值修剪: 溢价率 %d 行, 转股价值 %d 行 → 当日截面中位数替换'
                               % (int(prem_mask.sum()), int(cv_mask.sum())))
        df.loc[prem_mask, 'premium_rate'] = np.nan
        df['premium_rate'] = df.groupby('date')['premium_rate'].transform(
            lambda x: x.fillna(x.median())
        ).fillna(30.0)
        df.loc[cv_mask, 'conversion_value'] = np.nan
        df['conversion_value'] = df.groupby('date')['conversion_value'].transform(
            lambda x: x.fillna(x.median())
        ).fillna(100.0)

    # ============================================================
    # Step 7: 近似「集思录已公告强赎」标志 redeem_approx_confirmed
    #   BigQuant 无集思录表, 用转股价值+溢价率组合作为强赎已公告近似:
    #   conversion_value >= 140 且 premium_rate <= 5% → 高度疑似已公告强赎 (强赎期, 市场已经充分定价)
    #   后续如果有 cn_cbond_redemption 表可叠加使用
    # ============================================================
    df['redeem_approx_confirmed'] = (
        (df['conversion_value'] >= REDEEM_CONFIRMED_CV) &
        (df['premium_rate'] <= REDEEM_CONFIRMED_PREM)
    )
    context.logger.info('Step7 近似已公告强赎标记: %d 行 / %d 行 (占比 %.2f%%)'
                        % (int(df['redeem_approx_confirmed'].sum()), len(df),
                           100.0 * df['redeem_approx_confirmed'].sum() / max(1, len(df))))

    # ---- 列名重命名 bond_close → close, 与 handle_data 原有逻辑兼容 ----
    df.rename(columns={'bond_close': 'close'}, inplace=True)

    # ---- 保存主表 ----
    context.cb_data = df

    context.logger.info(
        '初始化完成: %d 行 × %d 列 | %d 只可转债 | %s ~ %s\n'
        '  close 均值 %.2f  溢价率均值 %.2f%%  转换价值均值 %.2f\n'
        '  ST正股 %.2f%% | 近似强赎 %.2f%%'
        % (len(df), df.shape[1], df['instrument'].nunique(),
           df['date'].min().strftime('%Y-%m-%d'),
           df['date'].max().strftime('%Y-%m-%d'),
           df['close'].mean(), df['premium_rate'].mean(), df['conversion_value'].mean(),
           100.0 * df['is_st_stock'].sum() / max(1, len(df)),
           100.0 * df['redeem_approx_confirmed'].sum() / max(1, len(df)))
    )


def handle_data(context: bigtrader.IContext, data: bigtrader.IBarData):
    """每日K线回调。

    触发条件: 当日 ∈ context.month_end_dates (每月最后1个交易日, 对齐 frozen spec + 实盘版)
    过滤顺序 (严格对齐 frozen spec 约定 + monthly_rebalance.py 顺序):
      ① 上市≥30天 ∩ 距到期>12月       (池子过滤)
      ② 信用过滤:  close<80 ∩ premium>100 → 剔除
      ③ ST正股过滤 (hard constraint)
      ④ 强赎预警1:  conversion_value >= 130 → 剔除
      ⑤ 强赎预警2:  近似「已公告强赎」标记 → 剔除
      ⑥ z-score 双低打分
    """
    today = data.current_dt.strftime('%Y-%m-%d')
    today_dt = data.current_dt

    # ---- 调仓触发: 仅月末最后一个交易日调仓 (frozen spec 硬约束) ----
    if today not in context.month_end_dates:
        return

    # 分层计数 (便于和 monthly_rebalance.py 实盘调仓单层结果对照)
    n_raw = n_pool = n_credit = n_st = n_redeem_warn = n_redeem_confirmed = -1

    # ---- 当天数据 ----
    cur = context.cb_data[context.cb_data['date'] == today].copy()
    n_raw = len(cur)
    if n_raw < BUFFER_N:
        context.logger.warning('%s [月末调仓] 仅%d条数据, 不足BUFFER_N, 跳过' % (today, n_raw))
        return

    # ------------------------------------------------------------------
    # ① 池子过滤: 上市≥30天 AND 距到期>12月 (严格 >12, 对齐实盘版)
    # ------------------------------------------------------------------
    cur['days_listed'] = (today_dt - cur['list_date']).dt.days
    cur['months_to_mat'] = (cur['maturity_date'] - today_dt).dt.days / 30.0
    before = len(cur)
    cur = cur[(cur['days_listed'] >= MIN_LIST_DAYS) &
              (cur['months_to_mat'] > MIN_TERM_MONTHS)].copy()   # 注意: 严格 >
    n_pool = len(cur)
    if n_pool < BUFFER_N:
        context.logger.warning('%s ①上市+期限: %d→%d, 不足BUFFER_N, 跳过' % (today, before, n_pool))
        return

    # ------------------------------------------------------------------
    # ② 信用过滤 (frozen spec 顺序第二档): 债价<80 且 溢价>100 → 高风险债剔除
    # ------------------------------------------------------------------
    before = len(cur)
    cur['risky'] = ((cur['close'] < CREDIT_PRICE_FLOOR) &
                    (cur['premium_rate'] > CREDIT_PREMIUM_CEILING))
    cur = cur[~cur['risky']].copy()
    n_credit = len(cur)
    if n_credit < BUFFER_N:
        context.logger.warning('%s ②信用过滤: %d→%d, 不足BUFFER_N, 跳过' % (today, before, n_credit))
        return

    # ------------------------------------------------------------------
    # ③ ST 正股剔除 (project_memory hard constraint: 必须过滤)
    # ------------------------------------------------------------------
    before = len(cur)
    cur = cur[~cur['is_st_stock']].copy()
    n_st = len(cur)
    if n_st < BUFFER_N:
        context.logger.warning('%s ③ST过滤: %d→%d, 不足BUFFER_N, 跳过' % (today, before, n_st))
        return

    # ------------------------------------------------------------------
    # ④ 强赎预警1: 转股价值 >= 130 (常规强赎条款触发阈值区, 对齐 CB_REDEEM_RISK_THRESHOLD)
    # ------------------------------------------------------------------
    before = len(cur)
    cur = cur[cur['conversion_value'] < REDEEM_RISK_THRESHOLD].copy()
    n_redeem_warn = len(cur)
    if n_redeem_warn < BUFFER_N:
        context.logger.warning('%s ④强赎预警(cv>=%d): %d→%d, 不足BUFFER_N, 跳过'
                               % (today, REDEEM_RISK_THRESHOLD, before, n_redeem_warn))
        return

    # ------------------------------------------------------------------
    # ⑤ 近似「集思录已公告强赎」剔除
    # ------------------------------------------------------------------
    before = len(cur)
    cur = cur[~cur['redeem_approx_confirmed']].copy()
    n_redeem_confirmed = len(cur)
    if n_redeem_confirmed < BUFFER_N:
        context.logger.warning('%s ⑤近似强赎(已公告): %d→%d, 不足BUFFER_N, 跳过'
                               % (today, before, n_redeem_confirmed))
        return

    # ------------------------------------------------------------------
    # ⑥ z-score 双低打分 (注意: -(x-mean)/std → 值越低的指标z越大越好)
    # ------------------------------------------------------------------
    for col in ['close', 'premium_rate']:
        s = cur[col]
        mean, std = s.mean(), s.std()
        cur[col + '_z'] = -(s - mean) / std if std > 0 else 0.0
    cur['score'] = W_PRICE * cur['close_z'] + W_PREMIUM * cur['premium_rate_z']
    cur = cur.sort_values('score', ascending=False)

    # ---- 缓冲带 (与实盘版 + 原逻辑一致): 前BUFFER_N名中仍在持仓的优先保留 ----
    held = set(context.portfolio.positions.keys())
    top_pool = cur.head(BUFFER_N)['instrument'].tolist()

    keep = [s for s in top_pool if s in held]
    fresh = [s for s in top_pool if s not in held]
    selected = keep[:N_HOLD] + fresh[:max(0, N_HOLD - len(keep))]

    if len(selected) < N_HOLD * MIN_KEEP_RATIO:
        context.logger.warning('%s 缓冲带后仅%d只 (<%.0f%%), 跳过调仓'
                               % (today, len(selected), 100.0 * MIN_KEEP_RATIO))
        return

    # ---- 调仓 ----
    target_set = set(selected)

    # 卖出
    for s in list(held):
        if s not in target_set:
            context.order_target_percent(s, 0)

    # 等权买入
    w = 1.0 / len(selected)
    for s in selected:
        context.order_target_percent(s, w)

    # 日志 (每层过滤后数量便于和 monthly_rebalance.py 实盘调仓结果对照)
    n_final_pool = len(cur)
    context.logger.info(
        '%s [月末调仓] 选%d只 | 分层:原始%d 池%d 信用%d ST%d 强赎预%d 强赎已%d 打分池%d | '
        '缓冲:保%d/新%d | 资产%.0f | 持仓%d'
        % (today, len(selected),
           n_raw, n_pool, n_credit, n_st, n_redeem_warn, n_redeem_confirmed, n_final_pool,
           len(keep), len(fresh),
           context.get_portfolio_value(),
           len(context.portfolio.positions))
    )


# ============================================================
# 回测入口
# ============================================================
performance = bigtrader.run(
    market=bigtrader.Market.CN_CBOND,
    frequency=bigtrader.Frequency.DAILY,
    start_date='2019-01-01',
    end_date='2026-07-29',
    capital_base=100000,
    benchmark='000852.SH',
    initialize=initialize,
    handle_data=handle_data,
    order_price_field_buy='close',
    order_price_field_sell='close',
    volume_limit=0.1,
)
