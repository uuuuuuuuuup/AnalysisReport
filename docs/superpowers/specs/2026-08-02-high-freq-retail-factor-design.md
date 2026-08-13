# 高频散户行为反向因子设计文档

## 1. 背景与目标

现有 `high_freq_factor_strategy_rq.py` 中的 6 个因子全部来自 2021-2022 年公开研报，2021-2026 年米筐回测收益 -28.08%，夏普 -1.34，已失效。

本设计转向挖掘基于**分钟 OHLCV + amount**、面向**中证1000 小盘股散户市**的新型因子。核心假设：中证1000 散户参与度高，行为偏差更明显，因子应识别并反向利用这些偏差，而非简单追逐"主力大单"。

## 2. 数据约束

- **可用数据**：akshare / 米筐 / 聚宽免费版的分钟 K 线（open/high/low/close/volume/amount）和日 K 线。
- **不可用数据**：Level-2 十档盘口、逐笔委托、毫秒级 tick、龙虎榜明细。
- **平台优先级**：第一阶段仅验证米筐在线免费版分钟级回测；akshare 本地脚本与聚宽/BigQuant 适配作为后续动作。

## 3. 验证区间与回测配置

| 项目 | 配置 |
|---|---|
| 训练/探索区间 | 2021-01-01 ~ 2023-12-31 |
| 验证区间 | 2024-01-01 ~ 2025-12-31 |
| 最新留出区间 | 2026-01-01 ~ 2026-07-29 |
| 标的池 | 中证1000（000852.XSHG）历史成分股 |
| 持仓 | Top 20 等权 |
| 调仓频率 | 先日频，后补充周频对比 |
| 交易成本 | 佣金万3、印花税千1、滑点万1 |
| 评价指标 | 累计收益、年化收益、超额收益、夏普、最大回撤、Rank IC、ICIR、换手率、月度胜率 |

## 4. 现有策略需修正的结构性问题

原 `high_freq_factor_strategy_rq.py`：
- `lookback_days=10` 拉取 10 天分钟线，但因子仍按单日逻辑计算，未对跨日价格跳变做处理；
- `tail_start_idx=210` 等索引假设只适用于单日 240 根分钟线；
- 多日期数据混在一起会造成尾盘/开盘时段识别错误。

新策略改为：
- 每只股票取过去 N 个**完整交易日**的分钟数据；
- 每日单独计算日内因子；
- 过去 N 日因子再聚合为单一截面值；
- 统一使用 `datetime` 字段识别真实交易时段。

## 5. 候选因子

### Factor 1: 冲高回落强度（Intraday Pullback Intensity）

**核心逻辑**  
衡量价格接近日内高点后，成交放大但收盘无法维持的程度。散户追涨导致短时价格偏离，随后兑现。

**计算公式**
```python
high_idx = close.argmax()  # 日内最高价出现位置（分钟索引）
high_price = high.max()
close_price = close.iloc[-1]
total_amount = amount.sum()
amt_after_peak = amount[high_idx:].sum()

# 冲高回落强度 = （高点后成交额占比）* （高点到收盘回撤幅度）
factor = (amt_after_peak / total_amount) * ((high_price - close_price) / high_price)
```

**方向**：-1（值越大，次日越差）

**经济学解释**  
Barberis & Shleifer 风格的投资者情绪模型：散户对近期价格上涨过度外推，在高点附近追涨，随后获利盘或理性交易者卖出导致价格回落。

**为什么未失效**  
与简单"尾盘占比"不同，本因子结合"高点后成交"与"回撤幅度"，识别的是"散户接盘、无法维持"的状态，而不是单纯的尾盘放量。

---

### Factor 2: 上涨路径断裂率（Up-Move Discontinuity）

**核心逻辑**  
识别连续上涨分钟后出现快速反向分钟的频率。真正的信息扩散通常路径平滑，散户追涨更容易"冲一下、断一下"。

**计算公式**
```python
minute_ret = close.pct_change()
up_minutes = minute_ret > 0
# 上涨分钟后紧跟下跌分钟的次数占比
up_then_down = ((up_minutes.shift(1) == True) & (up_minutes == False)).sum()
factor = up_then_down / len(minute_ret)
```

**方向**：-1（断裂越多，次日越差）

**经济学解释**  
Kyle(1985) 单期知情交易模型：信息交易会产生持续同向的价格压力；噪声交易导致价格反复震荡。路径断裂率是噪声交易强度的代理。

**为什么未失效**  
公开研报多关注"单笔金额偏度"或"成交量分布"，很少把"方向转换的微观节奏"作为独立因子。

---

### Factor 3: 下跌成交集中度相对上涨集中度（Down/Up Concentration Ratio）

**核心逻辑**  
分别统计下跌分钟和上涨分钟的成交额集中程度，比较二者。下跌时成交突然集中，通常伴随恐慌性卖出。

**计算公式**
```python
up_amount = amount[close > open].sum()
down_amount = amount[close < open].sum()
# 使用 Herfindahl 或 Top10% 集中度
up_top10 = amount[close > open].quantile(0.9) if up_amount > 0 else 0
down_top10 = amount[close < open].quantile(0.9) if down_amount > 0 else 0
factor = (down_top10 / down_amount) / (up_top10 / up_amount + 1e-8)
```

**方向**：-1（下跌越集中，次日越差）

**经济学解释**  
流动性螺旋与恐慌抛售：散户在下跌时更容易产生羊群效应，导致流动性暂时枯竭和错误定价，但次日往往修复而非持续下跌，因此短期反向看空。

**为什么未失效**  
类似"日内已实现半方差"的思想，但聚焦在成交额的**集中结构**而非波动率本身。

---

### Factor 4: 跌后恢复效率（Post-Decline Recovery Efficiency）

**核心逻辑**  
识别较大下跌分钟之后，价格恢复到跌前水平所需的时间。恢复快可能是流动性冲击后的过度反应。

**计算公式**
```python
# 找出跌幅最大的前 10% 分钟
threshold = minute_ret.quantile(0.1)
big_down_idx = minute_ret[minute_ret <= threshold].index
# 计算每个大跌后 10 分钟内回到跌前价位的比例
recoveries = []
for idx in big_down_idx:
    if idx + 10 >= len(close):
        continue
    pre_price = close.iloc[idx - 1]
    recovered = (close.iloc[idx + 10] >= pre_price).astype(float)
    recoveries.append(recovered)
factor = np.mean(recoveries) if recoveries else np.nan
```

**方向**：训练区间确定，不预设。若恢复快的股票次日上涨，则方向为 +1；若恢复快的股票被继续抛售，则方向为 -1。

**经济学解释**  
Grossman-Miller 流动性提供模型：临时流动性冲击会被套利者迅速吸收，产生短期反转。

**为什么未失效**  "大跌后恢复速度"不是常见公开因子，且对时段窗口和跌幅阈值敏感，批量复制门槛高。

---

### Factor 5: 个股—市场极端同步偏离（Extreme Co-Movement Deviation）

**核心逻辑**  
比较个股与中证1000 指数分钟收益的同步程度，重点观察极端上涨/下跌时的偏离。散户容易在市场热点中羊群式追随。

**计算公式**
```python
# 需要先获取指数分钟收益
stock_ret = close.pct_change()
index_ret = index_close.pct_change()
# 极端分钟：个股涨幅 top 10%
extreme_up = stock_ret >= stock_ret.quantile(0.9)
# 在这些分钟里，个股与指数收益的偏离度
factor = (stock_ret[extreme_up] - index_ret[extreme_up]).std()
```

**方向**：+1（偏离大，说明有独立信息，看好）或 -1（同步高，说明羊群效应，看差）。需训练区间确定。

**经济学解释**  Sias(2004) 机构投资者羊群行为研究：散户更容易跟风行业/市场热点，导致个股暂时脱离基本面；独立走势往往意味着私有信息。

**为什么未失效**  常见 Beta 因子用日频，而分钟级"极端同步偏离"对散户行为刻画更细腻。

---

### Factor 6: 成交爆发后的路径效率衰减（Volume Burst Path Efficiency Decay）

**核心逻辑**  
识别成交量突然爆发的分钟，比较爆发前后价格路径效率。散户注意力集中会造成"量先爆、价后钝化"。

**计算公式**
```python
# 成交量 top 10% 的分钟作为爆发点
burst_mask = volume >= volume.quantile(0.9)
# 爆发前/后各 5 分钟的价格路径效率
pre_eff = abs(close[burst_mask].shift(5) - close[burst_mask].shift(1)) / \
          (high[burst_mask].shift(5).rolling(5).max() - low[burst_mask].shift(5).rolling(5).min())
post_eff = abs(close[burst_mask].shift(-1) - close[burst_mask].shift(-5)) / \
           (high[burst_mask].shift(-5).rolling(5).max() - low[burst_mask].shift(-5).rolling(5).min())
factor = (post_eff / (pre_eff + 1e-8)).mean()
```

**方向**：-1（爆发后效率衰减越严重，次日越差）

**经济学解释**  注意力驱动的交易：散户集中涌入导致成交量放大，但缺乏持续信息流入，价格推进效率下降。

**为什么未失效**  结合了成交量异常与价格路径效率两个维度，不是简单"放量上涨/下跌"。

## 6. 因子聚合与选股流程

1. 每个交易日收盘后，对中证1000 成分股计算过去 5-10 个交易日每日的日内因子；
2. 每日因子取均值或最近一日值，形成截面因子值；
3. 截面上做 MAD 去极值和 Z-Score 标准化；
4. 根据训练区间确定的方向调整符号；
5. 等权合成，选 Top 20；
6. 下一交易日开盘或收盘执行调仓。

## 7. 分析脚本交付物

`factor_discovery_rq_research.py`：米筐研究环境可运行脚本，功能包括：
- 加载中证1000 成分股和分钟数据；
- 计算 6 个候选因子；
- 计算次日收益率；
- 输出 Rank IC、ICIR、方向一致性、因子相关性矩阵、IC 衰减（滞后 1-5 天）；
- 按年/区间拆分结果；
- 保存 CSV 报告。

## 8. 成功标准

- 至少 2 个因子在训练区间有稳定同向 IC；
- 这些因子在验证区间方向不反转；
- 合成后因子的 IR 优于现有 6 因子组合；
- 2026 留出区间不出现显著崩溃；
- 日频和周频均有一定正超额。

## 9. 风险与限制

- 分钟 K 线是降级数据，无法还原真实逐笔；
- 小盘股滑点、停牌、涨跌停可能影响实盘表现；
- 因子可能随市场结构变化而失效，需持续监控；
- 本设计不预设 IC 数值，所有结果以实际回测为准。
