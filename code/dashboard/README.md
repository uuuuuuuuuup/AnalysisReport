# 投资账本 · 金融终端看板

基于同花顺投资账本 API 的暗色模式金融数据看板，纯 JS 实现（Node.js + 原生 HTML/CSS/JS），零第三方依赖（图表库 ECharts 走 CDN）。

## 快速开始

```bash
node server.js
# 自动打开浏览器 → http://localhost:8888
```

**前置条件：**
- Node.js ≥ 18（仅用内置模块，无需 npm install）
- `~/.tzzb_cookies` 文件：浏览器登录同花顺投资账本后，从开发者工具复制 Cookie 存入

## 文件结构

```
dashboard/
├── index.html    # 看板页面（全部 UI + 前端逻辑）
├── server.js     # Node.js 服务器（API 代理 + 静态文件）
├── README.md     # 本文档
├── data.json     # [遗留] 早期静态数据文件，已不再使用，可删除
└── kline.json    # [遗留] 早期 MCP 预取 K 线数据，已不再使用，可删除
```

## 设计风格规范

### 视觉主题

| 维度 | 规范 |
|------|------|
| 整体风格 | 专业交易终端风（Bloomberg / Wind 暗色系） |
| 背景 | `#0d0d0d` 纯黑底 + 细网格线（48px 间距，白色 2% 透明度） |
| 卡片 | `#18181b` 深灰面 + `#252528` 细边框，12px 圆角，无重阴影 |
| 标题样式 | 橙色小方块前缀 `▮` + `英文 // 中文` 双语言格式 |
| 字体 | 数字/代码用 JetBrains Mono（等宽），中文用 Noto Sans SC |
| 涨跌配色 | **A 股惯例**：红 `#ef4444` 涨、绿 `#22c55e` 跌 |
| 点缀色 | 橙 `#f97316`（标题方块、趋势线、温度计） |

### 卡片布局（Bento Grid）

CSS Grid 四列布局，`grid-auto-rows: 240px`，卡片按内容高度自适应（`row-2` 跨 2 行），6 行全部填满无空隙：

```
┌───────────┬───────────┬─────────────┬─────────────┐
│ ACCOUNTS  │ PORTFOLIO │ CANDLESTICK │ CANDLESTICK │
│ 账户红绿灯  │ 账户概览   │ (2×2, 2列宽) │             │
├───────────┴───────────┼─────────────┴─────────────┤
│ P&L CALENDAR 每日盈亏    │ CANDLESTICK               │
│ (col-2, 日历热力图)      │                           │
├───────────┬───────────┼─────────────┬─────────────┤
│ WATCHLIST │ WATCHLIST │ MONEY FLOW  │ MONEY FLOW  │
│ (2×2, 2列)│           │ (2×2  treemap)│             │
├───────────┴───────────┼─────────────┴─────────────┤
│ WATCHLIST             │ MONEY FLOW                │
├───────────┬───────────┼─────────────┬─────────────┤
│ INDEX TAPE│ POSITIONS │ POSITIONS   │ HOLDINGS    │
│ (row-2)   │ (2×2, 2列)│             │ 横向柱形图    │
├───────────┴───────────┼─────────────┼─────────────┤
│ INDEX TAPE            │ POSITIONS   │ CASH FLOW   │
└───────────────────────┴─────────────┴─────────────┘
```

响应式：≤1400px 两列（跨行卡折为单行 240px）、≤680px 单列。

### 隐私模式

顶栏 👁 按钮切换：所有卡片中的金额/涨跌幅数字应用 CSS `filter: blur(5px)` 模糊化（含自选行情、资金流水、月度收益等新卡片），再次点击恢复。顶栏另有 LIVE 时钟与 ⟳ 手动刷新按钮。

## 已实现功能

### 数据层

| 功能 | 数据来源 | 刷新方式 |
|------|----------|----------|
| 账户概览（3 账户资产/市值/仓位） | `account_list` + `stock_position` | 打开页面自动加载 |
| 持仓明细（26 只标的） | `stock_position` | 随账户数据同步 |
| 资产净值走势（Tab 切换账户） | `asset_trend` API | 打开页面自动加载 |
| 收盘价折线图（60 交易日 + MA5/10/20） | `getQuotes` API 逐日查询 | 切换标的时按需拉取 + 缓存 |
| 每日盈亏日历（GitHub 贡献图风格，按日收益率分档红绿） | `asset_trend` `year_profit` | 打开页面自动加载 |
| 资金流水（近 30 天交易/入账记录） | `get_money_history` API | 打开页面加载第 1 页，翻页按需追加 |
| 自选行情（213 只自选涨跌分布 + 列表） | `sort_list` + `rise_fall` | 打开页面自动加载 |
| 资金流向（全市场主力净流入/流出榜，treemap 热力图） | 新浪 `MoneyFlow.ssl_bkzj_ssggzj` | 打开页面自动加载，Tab 切换 |
| K 线图（OHLC 蜡烛图，前复权 120 日） | 腾讯 `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 切换 K 线模式时按需拉取 + 缓存 |

空账户过滤：`store.accounts` 统一过滤「空空如也」空账户，所有卡片自动隐藏。

### UI 组件

1. **账户红绿灯** — 每账户一行：本月盈亏额 + 盈亏率（红涨绿跌）+ 仓位进度条（>90% 红 / >60% 橙 / 其余绿）
2. **P&L CALENDAR 每日盈亏** — GitHub 贡献图风格日历热力图：每个交易日一格，按日收益率分红（正）/绿（负）多档强度；Tab 总合计 / 各账户；统计区间盈亏与区间收益率
3. **HOLDINGS 持仓权重** — 横向柱形图：按市值横向展开，红涨绿跌着色，右侧标注涨跌幅；dataZoom 支持滚动
4. **WATCHLIST 自选行情** — 213 只自选 ↑↓ 计数 + 红绿分布条 + 平均涨跌幅，列表排序切换（涨跌幅↓ / 自选顺序 / 代码），卡片内滚动，只读
5. **收盘价折线 / K 线图** — 标题栏「折线 | K线」一键切换：折线模式用同花顺 60 日收盘价（含 MA5/10/20 面积图），K 线模式用腾讯前复权 120 日蜡烛图（红涨绿跌 + 成交量 + MA + 缩放条），下拉选择器按账户分组列出全部持仓
6. **持仓明细表** — 按市值排序，8 列：名称/代码/持仓/成本/现价/市值/盈亏/盈亏%
7. **账户概览** — 3 账户资产/市值/仓位小卡
8. **资产净值走势** — Tab 切换：全部合计 / 宁静致远 / 淡泊明志，大字号指数值 + 面积图
9. **资金流向** — 全市场主力净流入/流出 treemap 热力图：面积 = 主力净流入额，颜色 = 红涨绿跌；Tab 净流入/净流出；过滤 ETF，悬浮显示现价、涨跌幅、主力净流入
10. **资金流水** — Tab 切换账户，表格：日期/名称/操作/数量/金额/备注，操作列彩色徽章（交易橙 / 资金蓝），「加载更多」翻页到顶自动隐藏
11. **隐私模式** — 👁 一键模糊全部金额，顶栏 LIVE 时钟 + ⟳ 手动刷新

### 服务端（server.js）

- `/` — 看板页面
- `/api/*` — 同花顺 API 反向代理（自动附加 Cookie）
- `/api-check` — Cookie 存在性检查 + userid 提取
- `/kline/{code}?market={m}` — 收盘价历史（60 个交易日，10 并发批次逐日调 `getQuotes`）
- `/proxy/kline?code=sh600519&count=120` — 腾讯前复权日 K 线代理（OHLC + 成交量，带防盗链头）
- `/proxy/moneyflow?order=desc|asc&num=12` — 新浪个股资金流排行代理

## 已知限制

1. **无 K 线（OHLC）数据** — 同花顺投资账本是持仓管理工具，其 API 只提供收盘价（`getQuotes`），无开盘/最高/最低/成交量，因此用收盘价折线替代蜡烛图
2. **收盘价查询较慢** — 首次查询某标的需 60 次 API 调用（约 2-3 秒），前端有缓存，二次查询秒出
3. **市场代码映射** — `getQuotes` 的 market 参数来自持仓数据（1=沪股/深股、2=沪市基金债券），非通用规则
4. **资产走势与每日盈亏均含资金进出影响** — `asset_trend` 返回的净值、每日 `profit` 均含资金流入流出影响，非纯投资收益曲线
5. **清仓统计接口不可用** — 该账户类型不支持 `cleared_position`（所有参数组合 HTTP 400）
6. **自选只读** — 看板不提供加删自选功能
7. **Cookie 过期** — Cookie 失效后需重新从浏览器复制到 `~/.tzzb_cookies`

## 数据源对照

| 接口 | 用途 |
|------|------|
| `POST /caishen_fund/pc/account/v1/account_list` | 账户列表 |
| `POST /caishen_fund/pc/asset/v1/stock_position` | 实时持仓 |
| `POST /caishen_fund/pc/asset/v1/asset_trend` | 历史资产净值（year/month/total_asset；`year_profit` 还用于每日盈亏日历） |
| `POST /caishen_fund/pc/asset/v1/merge_compare` | [已弃用] 月度盈亏对比（原月度收益柱状图） |
| `POST /caishen_fund/pc/account/v2/get_money_history` | 资金流水（近 30 天，分页 20 条） |
| `POST /caishen_fund/pc/optional/v1/sort_list` | 自选列表（现价/涨跌额/涨跌幅/加入时间） |
| `POST /caishen_fund/pc/optional/v1/rise_fall` | 自选涨跌分布（stock_rise / stock_fall / avg_rate） |
| `POST /caishen_fund/invest/getQuotes` | 历史收盘价（按 date 参数，折线模式） |
| `GET 腾讯 web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 前复权日 K 线（OHLC + 成交量，K 线模式，经 `/proxy/kline`） |
| `GET 新浪 vip.stock.finance.sina.com.cn/.../MoneyFlow.ssl_bkzj_ssggzj` | 个股资金流排行（主力净流入 r0_net，经 `/proxy/moneyflow`） |
