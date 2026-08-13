# 看板第二期（月度收益 + 自选行情 + 资金流水）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有看板追加 3 张卡片（月度收益柱状图、自选行情列表、资金流水列表），纯前端改动，server.js 零改动。

**Architecture:** 所有数据经 server.js 现有 `/api/*` 通用代理透传（自动附加 Cookie），前端用现有 `apiFetch()` 拼接查询参数。三个新数据模块各自独立加载、渲染、错误占位，挂载到现有 `renderAll()`。

**Tech Stack:** 原生 HTML/CSS/JS + ECharts 5.5（CDN）。零依赖，无测试框架——验证方式为 curl（接口层）+ 浏览器检查（渲染层）。

**规格文档:** `docs/superpowers/specs/2026-08-13-dashboard-features-design.md`（已批准）

**环境约定:**
- 所有改动只涉及 `index.html` 一个文件。**server.js 不改**。
- git 提交：用户全局约定为仅在明确指示时提交。各任务末尾的提交步骤**默认跳过**，除非用户已明确要求提交。
- 服务器：先 `cd /Users/apple/Documents/分析报告/code/dashboard && node server.js`（或确认 8888 端口已有实例）。页面 http://localhost:8888
- 浏览器验证：打开页面后 F12 Console 可直接执行 JS；也可用 kimi-webbridge 的 evaluate（127.0.0.1:10086）。

---

## Task 1: store.accounts 携带 fund_key / manual_id

新卡片的接口都需要账户的 `fund_key`，但 `loadAllData()` 目前丢弃了它。

**Files:**
- Modify: `/Users/apple/Documents/分析报告/code/dashboard/index.html`（loadAllData 中 acctData 定义处）

- [ ] **Step 1: acctData 增加两个字段**

找到 loadAllData 里的 `const acctData = {`（约在 `// 2. For each account` 循环内），old:

```js
      const acctData = {
        name,
        total_asset: parseFloat(ex.total_asset || 0),
```

new:

```js
      const acctData = {
        name,
        fund_key: fk,
        manual_id: mid,
        total_asset: parseFloat(ex.total_asset || 0),
```

（`fk`、`mid` 是该循环上方已有的局部变量，无需新增。）

- [ ] **Step 2: 验证 store.accounts 携带 fund_key**

启动服务器后，浏览器打开 http://localhost:8888，Console 执行：

```js
JSON.stringify(store.accounts.map(a => ({name: a.name, fund_key: a.fund_key, manual_id: a.manual_id})))
```

Expected: 输出 3 个账户对象，每个 `fund_key` 非空（约等于 `145551046` / `147527437` / `68970713`），`manual_id` 为 `""`。

- [ ] **Step 3: 提交（默认跳过，见环境约定）**

---

## Task 2: 月度收益卡 MONTHLY P&L

**Files:**
- Modify: `/Users/apple/Documents/分析报告/code/dashboard/index.html`（HTML 卡片 + JS 模块 + renderAll 挂载）

- [ ] **Step 1: 插入卡片 HTML**

在 `</main>`（`<main class="dashboard">` 的闭合标签）之前插入：

```html
  <!-- 月度收益 -->
  <div class="card col-2">
    <div class="card-title">MONTHLY P&L // 月度收益 <span style="font-size:9px;color:var(--text-3);margin-left:auto;font-family:'JetBrains Mono',monospace;">¥/月</span></div>
    <div id="monthly-status" style="font-size:10px;color:var(--text-3);margin-bottom:4px;font-family:'JetBrains Mono',monospace;"></div>
    <div class="index-tabs" id="monthly-tabs"></div>
    <div class="chart-box" id="chart-monthly" style="height:180px;"></div>
  </div>
```

（`index-tabs` / `chart-box` 为现有 CSS 类，无需新增样式。⚠️ 加载中/错误状态必须写在 `#monthly-status` 独立元素里，**禁止**用 innerHTML 覆盖 `#chart-monthly`——echarts.init 已接管该容器，innerHTML 会把 canvas 子树拆下文档导致图表不可见。）

- [ ] **Step 2: 验证接口数据经代理可用**

```bash
UID=$(curl -s http://localhost:8888/api-check | python3 -c "import json,sys;print(json.load(sys.stdin)['userid'])")
curl -s -X POST "http://localhost:8888/api/caishen_fund/pc/asset/v1/merge_compare?terminal=1&version=0.0.0&userid=$UID&manual_id=&fund_key=147527437&rzrq_fund_key=&fund_id=&custid=" | head -c 300
```

Expected: 输出包含 `"profit_compare"` 且其中 12 个 `"month"` 条目（`2025-09`～`2026-08`）。

- [ ] **Step 3: 插入 JS 模块**

在 `// ========================= FILL STATS =========================` 这一行之前插入：

```js
// ========================= MONTHLY P&L =========================
let monthlyChart = null, monthlyData = {}, monthlyMode = 'total';

async function loadMonthly() {
  const st = document.getElementById('monthly-status');
  st.textContent = '加载中...';
  st.style.color = 'var(--text-3)';
  try {
    const entries = await Promise.all(store.accounts.map(async a => {
      const resp = await apiFetch(`/caishen_fund/pc/asset/v1/merge_compare?manual_id=${a.manual_id}&fund_key=${a.fund_key}&rzrq_fund_key=&fund_id=&custid=`);
      return [a.name, resp.ex_data?.profit_compare || []];
    }));
    monthlyData = Object.fromEntries(entries);
    buildMonthlyTabs();
    updateMonthly();
    st.textContent = '';
  } catch (e) {
    st.textContent = '月度收益加载失败: ' + e.message;
    st.style.color = '#f87171';
    monthlyChart.clear();
  }
}

function buildMonthlyTabs() {
  document.getElementById('monthly-tabs').innerHTML =
    `<button class="index-tab" onclick="switchMonthly('total')">全部合计</button>` +
    store.accounts.map(a => `<button class="index-tab" onclick="switchMonthly('${a.name}')">${a.name}</button>`).join('');
  document.querySelectorAll('#monthly-tabs .index-tab').forEach(t =>
    t.classList.toggle('active', monthlyMode === 'total' ? t.textContent.includes('全部') : t.textContent.includes(monthlyMode)));
}

function switchMonthly(mode) {
  monthlyMode = mode;
  document.querySelectorAll('#monthly-tabs .index-tab').forEach(t =>
    t.classList.toggle('active', mode === 'total' ? t.textContent.includes('全部') : t.textContent.includes(mode)));
  updateMonthly();
}

function updateMonthly() {
  if (!monthlyChart) return;
  let months = [], values = [];
  if (monthlyMode === 'total') {
    const map = {};
    Object.values(monthlyData).forEach(arr => arr.forEach(d => { map[d.month] = (map[d.month] || 0) + d.profit; }));
    months = Object.keys(map).sort();
    values = months.map(m => map[m]);
  } else {
    const arr = monthlyData[monthlyMode] || [];
    months = arr.map(d => d.month);
    values = arr.map(d => d.profit);
  }
  if (!months.length) { monthlyChart.clear(); return; }
  monthlyChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: '8%', right: '3%', top: '8%', bottom: '4%' },
    xAxis: { type: 'category', data: months, axisLabel: { color: '#555', fontSize: 9, formatter: v => v.slice(5) + '月' }, axisLine: { lineStyle: { color: '#333' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: '#555', fontSize: 9, formatter: v => (v / 10000).toFixed(0) + '万' }, splitLine: { lineStyle: { color: '#1a1a22' } }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: 'bar', data: values, barWidth: '55%',
      itemStyle: { color: p => p.value > 0 ? upColor : p.value < 0 ? downColor : '#3f3f46' }
    }],
    tooltip: { trigger: 'axis', backgroundColor: '#1a1a1f', borderColor: '#333', textStyle: { fontSize: 11, fontFamily: 'JetBrains Mono' },
      formatter: ps => { const p = ps[0]; const c = p.value > 0 ? upColor : p.value < 0 ? downColor : '#999';
        return p.axisValue + '<br/><span style="color:' + c + '">' + (p.value >= 0 ? '+' : '') + '¥' + p.value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '</span>'; } }
  });
}

function initMonthly() {
  if (!monthlyChart) {
    monthlyChart = echarts.init(document.getElementById('chart-monthly'), 'dark');
    new ResizeObserver(() => monthlyChart.resize()).observe(document.getElementById('chart-monthly'));
  }
  loadMonthly();
}
```

- [ ] **Step 4: 限定 switchIndex 的 Tab 选择器（防串扰）**

月度卡引入了第二个 `.index-tabs` 容器，而既有 `switchIndex` 用的是全局 `.index-tab` 选择器，切换资产走势 Tab 会错误改掉月度卡 Tab 的高亮。两处小改：

4a. 资产走势卡的 `<div class="index-tabs">` 改为 `<div class="index-tabs" id="index-tabs">`。

4b. switchIndex 中：

old: `document.querySelectorAll('.index-tab').forEach(t => {`
new: `document.querySelectorAll('#index-tabs .index-tab').forEach(t => {`

- [ ] **Step 5: 挂载到 renderAll**

old:

```js
function renderAll() {
  buildSessions();
  initGauge();
  initTreemap();
  initKline();
  initIndex();
  fillAll();
}
```

new:

```js
function renderAll() {
  buildSessions();
  initGauge();
  initTreemap();
  initKline();
  initIndex();
  fillAll();
  initMonthly();
}
```

- [ ] **Step 5: 浏览器验证**

刷新页面，检查：
1. 月度收益卡出现在持仓明细下方左侧宽幅位置，12 根柱（2025-09 起步），正值红、负值绿、0 灰。
2. Console 执行 `JSON.stringify(monthlyData)` → 3 个账户各 12 条。
3. 点击「宁静致远」Tab：柱子变为单账户数据；点「全部合计」：恢复合计。切 Tab 无报错。
4. 数值抽查（对照同花顺页面）：宁静致远 2026-04 应约 +39,620、2026-03 约 -23,176。
5. Console 无新增报错（echarts 关于 gauge/treemap 的既有 "already initialized" 警告可忽略，月度卡不应产生新警告——`initMonthly` 有 `if (!monthlyChart)` 守卫）。

- [ ] **Step 6: 提交（默认跳过）**

---

## Task 3: 自选行情卡 WATCHLIST

**Files:**
- Modify: `/Users/apple/Documents/分析报告/code/dashboard/index.html`（HTML 卡片 + CSS + JS 模块 + renderAll 挂载）

- [ ] **Step 1: 插入卡片 HTML**

在 Task 2 插入的月度收益卡之后（`</main>` 之前）插入：

```html
  <!-- 自选行情 -->
  <div class="card col-1 row-2" style="min-height:480px;">
    <div class="card-title">
      WATCHLIST // 自选行情
      <select id="wl-sort" onchange="renderWatchlist()" style="
        background:#222;color:var(--text-1);border:1px solid var(--border);
        border-radius:4px;padding:2px 6px;font-size:11px;font-family:inherit;
        cursor:pointer;margin-left:auto;">
        <option value="rate">涨跌幅↓</option>
        <option value="add">自选顺序</option>
        <option value="code">代码</option>
      </select>
    </div>
    <div class="wl-summary" id="wl-summary">加载中...</div>
    <div class="scroll-y" style="flex:1;">
      <table class="pos-mini"><thead><tr>
        <th>名称</th><th>现价</th><th>涨跌幅</th>
      </tr></thead><tbody id="wl-tbody"></tbody></table>
    </div>
  </div>
```

- [ ] **Step 2: 插入 CSS**

在 `@media (max-width: 1100px)` 这一行之前插入：

```css
  /* Watchlist */
  .wl-summary { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-2); margin-bottom: 8px; }
  .wl-avg { font-size: 20px; font-weight: 700; }
  .wl-dist { display: flex; height: 4px; border-radius: 2px; overflow: hidden; margin: 4px 0 2px; background: var(--down); }
  .wl-dist .rise { background: var(--up); }
```

- [ ] **Step 3: 验证接口数据经代理可用**

```bash
UID=$(curl -s http://localhost:8888/api-check | python3 -c "import json,sys;print(json.load(sys.stdin)['userid'])")
curl -s -X POST "http://localhost:8888/api/caishen_fund/pc/optional/v1/sort_list?terminal=1&version=0.0.0&userid=$UID&sort_rule=&sort_order=" | python3 -c "import json,sys;d=json.load(sys.stdin);print('count:',len(d['ex_data']['list']));print('first:',d['ex_data']['list'][0]['code'],d['ex_data']['list'][0]['name'],d['ex_data']['list'][0]['rate'])"
curl -s -X POST "http://localhost:8888/api/caishen_fund/pc/optional/v1/rise_fall?terminal=1&version=0.0.0&userid=$UID&stock_code=1:301230,2:688222&fund_code=" | head -c 200
```

Expected: 第一条输出 `count: 213`（或当前自选总数）且 first 有非空 code/name/rate；第二条输出包含 `"avg_rate"`、`"stock_rise"`、`"stock_fall"`。

- [ ] **Step 4: 插入 JS 模块**

在 `// ========================= FILL STATS =========================` 之前插入：

```js
// ========================= WATCHLIST =========================
let wlItems = [], wlStats = { rise: 0, fall: 0, avg: 0 };

async function loadWatchlist() {
  const tbody = document.getElementById('wl-tbody');
  tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:#666;">加载中...</td></tr>';
  try {
    const sl = await apiFetch('/caishen_fund/pc/optional/v1/sort_list?sort_rule=&sort_order=');
    wlItems = (sl.ex_data?.list || []).map(i => ({
      code: i.code || '', name: i.name || '', market: i.market || '',
      price: parseFloat(i.price) || 0, rate: parseFloat(i.rate) || 0, add: parseInt(i.addTime) || 0
    }));
    const codes = wlItems.filter(i => i.market && i.code).map(i => `${i.market}:${i.code}`).join(',');
    const rf = await apiFetch('/caishen_fund/pc/optional/v1/rise_fall?stock_code=' + codes + '&fund_code=');
    const d = rf.ex_data || {};
    wlStats = { rise: parseInt(d.stock_rise) || 0, fall: parseInt(d.stock_fall) || 0, avg: parseFloat(d.avg_rate) || 0 };
    renderWatchlist();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;color:#f87171;">自选行情加载失败: ${e.message}</td></tr>`;
  }
}

function renderWatchlist() {
  const items = [...wlItems];
  const sort = document.getElementById('wl-sort').value;
  if (sort === 'rate') items.sort((a, b) => b.rate - a.rate);
  else if (sort === 'add') items.sort((a, b) => a.add - b.add);
  else items.sort((a, b) => a.code.localeCompare(b.code));
  const s = wlStats, total = s.rise + s.fall;
  const pct = total ? (s.rise / total * 100).toFixed(0) : 50;
  document.getElementById('wl-summary').innerHTML =
    `<span class="up">↑${s.rise}</span> <span class="down">↓${s.fall}</span>` +
    `<span style="color:var(--text-3);margin-left:6px;">平 ${wlItems.length - total}</span>` +
    `<span class="wl-avg ${s.avg > 0 ? 'up' : s.avg < 0 ? 'down' : ''}" style="margin-left:8px;">${s.avg >= 0 ? '+' : ''}${(s.avg * 100).toFixed(2)}%</span>` +
    `<div class="wl-dist"><div class="rise" style="width:${pct}%;"></div></div>`;
  document.getElementById('wl-tbody').innerHTML = items.length ? items.map(i =>
    `<tr><td title="${i.code}">${i.name}</td><td>${i.price ? i.price.toFixed(2) : '-'}</td><td class="${upDown(i.rate)}">${fmtPct(i.rate)}</td></tr>`
  ).join('') : '<tr><td colspan="3" style="text-align:center;color:#666;">自选列表为空</td></tr>';
}

function initWatchlist() { loadWatchlist(); }
```

- [ ] **Step 5: 挂载到 renderAll**

old:

```js
  fillAll();
  initMonthly();
}
```

new:

```js
  fillAll();
  initMonthly();
  initWatchlist();
}
```

- [ ] **Step 6: 浏览器验证**

刷新页面，检查：
1. 自选行情卡在月度收益右侧，跨两行高度；头部显示 ↑N ↓M 计数、平均涨跌幅、红绿分布条。
2. 表格 213 行（`document.querySelectorAll('#wl-tbody tr').length` 应等于自选总数），卡片内滚动正常。
3. 排序下拉：切「自选顺序」后第一行应为首个添加的自选；切「代码」后按代码升序。
4. 分布条计数与接口一致：Console 执行 `JSON.stringify(wlStats)`，对照 Step 3 的 rise_fall 输出（↑ 应为 stock_rise、↓ 应为 stock_fall）。
5. 数值抽查：与同花顺自选页对照 3 只（如泓博医药、成都先导、黄金ETF华安）的现价和涨跌幅。

- [ ] **Step 7: 提交（默认跳过）**

---

## Task 4: 资金流水卡 CASH FLOW

**Files:**
- Modify: `/Users/apple/Documents/分析报告/code/dashboard/index.html`（HTML 卡片 + CSS + JS 模块 + renderAll 挂载）

- [ ] **Step 1: 插入卡片 HTML**

在 Task 3 插入的自选行情卡之后（`</main>` 之前）插入：

```html
  <!-- 资金流水 -->
  <div class="card col-2">
    <div class="card-title">CASH FLOW // 资金流水 <span style="font-size:10px;color:var(--text-3);font-weight:400;margin-left:8px;" id="cash-range"></span></div>
    <div class="index-tabs" id="cash-tabs"></div>
    <div class="scroll-y" style="flex:1;max-height:220px;">
      <table class="pos-mini"><thead><tr>
        <th>日期</th><th>名称</th><th>操作</th><th>数量</th><th>金额</th><th>备注</th>
      </tr></thead><tbody id="cash-tbody"></tbody></table>
    </div>
    <div style="text-align:center;margin-top:8px;"><button id="cash-more" class="index-tab" onclick="loadMoreCash()" style="display:none;">加载更多</button></div>
  </div>
```

- [ ] **Step 2: 插入 CSS**

在 `@media (max-width: 1100px)` 这一行之前插入：

```css
  /* Cash flow */
  .op-badge { font-size: 9px; padding: 1px 5px; border-radius: 3px; }
  .op-badge.trade { background: #f9731626; color: #f97316; }
  .op-badge.fund { background: #448aff26; color: #448aff; }
```

- [ ] **Step 3: 验证接口数据经代理可用**

```bash
UID=$(curl -s http://localhost:8888/api-check | python3 -c "import json,sys;print(json.load(sys.stdin)['userid'])")
curl -s -X POST "http://localhost:8888/api/caishen_fund/pc/account/v2/get_money_history?terminal=1&version=0.0.0&userid=$UID&manual_id=&fund_key=147527437&rzrq_fund_key=&fundid=&custid=&user_id=$UID&start_date=20260714&end_date=20260813&query_list=&page=1&count=20&sort_type=1&sort_order=1&h5id=" | head -c 600
```

Expected: 输出包含 `"list"` 且首条含 `"op_name"`（如 `"卖出"`）、`"entry_date"`、`"entry_money"`。⚠️ 此参数组合为实测可用形态：`query_list` 必须是空字符串（`query_list=[]` 会 400）、`sort_type=1&sort_order=1` 不可省略。

- [ ] **Step 4: 插入 JS 模块**

在 `// ========================= FILL STATS =========================` 之前插入：

```js
// ========================= CASH FLOW =========================
let cashRows = {}, cashPage = {}, cashMax = {}, cashErr = {}, cashMode = '', cashLoadingMore = false;

function cashDates() {
  const end = new Date();
  const start = new Date(end.getTime() - 30 * 24 * 3600 * 1000);
  const f = d => `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  return { start_date: f(start), end_date: f(end) };
}

async function loadCashflow() {
  if (!store.accounts.length) return;
  cashMode = store.accounts[0].name;
  buildCashTabs();
  document.getElementById('cash-tbody').innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666;">加载中...</td></tr>';
  const results = await Promise.allSettled(store.accounts.map(a => fetchCashPage(a.name, 1)));
  store.accounts.forEach((a, i) => {
    cashErr[a.name] = results[i].status === 'rejected' ? (results[i].reason?.message || '加载失败') : '';
  });
  renderCashRows();
}

function buildCashTabs() {
  document.getElementById('cash-tabs').innerHTML = store.accounts.map(a =>
    `<button class="index-tab ${a.name === cashMode ? 'active' : ''}" onclick="switchCash('${a.name}')">${a.name}</button>`).join('');
  const d = cashDates();
  const f = s => s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6);
  document.getElementById('cash-range').textContent = '近30天 ' + f(d.start_date) + ' ~ ' + f(d.end_date);
}

async function fetchCashPage(name, page) {
  const a = store.accounts.find(x => x.name === name);
  const d = cashDates();
  const resp = await apiFetch(`/caishen_fund/pc/account/v2/get_money_history?manual_id=${a.manual_id}&fund_key=${a.fund_key}&rzrq_fund_key=&fundid=&custid=&user_id=${UID}&start_date=${d.start_date}&end_date=${d.end_date}&query_list=&page=${page}&count=20&sort_type=1&sort_order=1&h5id=`);
  const ex = resp.ex_data || {};
  const list = (ex.list || []).map(r => ({
    date: r.entry_date || '', name: r.name || '', code: r.code || '',
    op: r.op_name || '', count: r.entry_count || '',
    money: parseFloat(r.entry_money) || 0, remark: r.remark || ''
  }));
  if (page === 1) { cashRows[name] = []; cashPage[name] = 1; cashMax[name] = parseInt(ex.max_page) || 1; }
  cashRows[name].push(...list);
}

function switchCash(name) {
  cashMode = name;
  document.querySelectorAll('#cash-tabs .index-tab').forEach(t => t.classList.toggle('active', t.textContent.includes(name)));
  renderCashRows();
}

function renderCashRows() {
  if (cashErr[cashMode]) {
    document.getElementById('cash-tbody').innerHTML =
      `<tr><td colspan="6" style="text-align:center;color:#f87171;">资金流水加载失败: ${cashErr[cashMode]}</td></tr>`;
    document.getElementById('cash-more').style.display = 'none';
    return;
  }
  const rows = cashRows[cashMode] || [];
  document.getElementById('cash-tbody').innerHTML = rows.length ? rows.map(r =>
    `<tr><td>${r.date}</td><td title="${r.code}">${r.name}</td>` +
    `<td><span class="op-badge ${['买入', '卖出'].includes(r.op) ? 'trade' : 'fund'}">${r.op || '--'}</span></td>` +
    `<td>${r.count}</td><td>¥${r.money.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>` +
    `<td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${r.remark || ''}</td></tr>`
  ).join('') : '<tr><td colspan="6" style="text-align:center;color:#666;">近30天无流水记录</td></tr>';
  document.getElementById('cash-more').style.display =
    (cashPage[cashMode] || 1) < (cashMax[cashMode] || 1) ? 'block' : 'none';
}

async function loadMoreCash() {
  if (cashLoadingMore) return;
  cashLoadingMore = true;
  const name = cashMode;
  cashPage[name] = (cashPage[name] || 1) + 1;
  try {
    await fetchCashPage(name, cashPage[name]);
  } catch (e) {
    cashPage[name] -= 1;
  }
  cashLoadingMore = false;
  renderCashRows();
}

function initCashflow() { loadCashflow(); }
```

- [ ] **Step 5: 挂载到 renderAll**

old:

```js
  initMonthly();
  initWatchlist();
}
```

new:

```js
  initMonthly();
  initWatchlist();
  initCashflow();
}
```

- [ ] **Step 6: 浏览器验证**

刷新页面，检查：
1. 资金流水卡在自选行情左侧（月度收益下方），Tab 为 3 个账户名，默认选中第一个账户。
2. 每页最多 20 行（`document.querySelectorAll('#cash-tbody tr').length <= 20`），操作列徽章：买入/卖出橙色、入账等蓝色。
3. 「加载更多」追加下一页且不重置已有行；`max_page` 到顶后按钮隐藏（`document.getElementById('cash-more').style.display` 为 `none`）。
4. 切 Tab 切换账户数据，无新请求（数据已缓存）。
5. 数值抽查：对照同花顺账户明细页，检查 3 条记录（如宁静致远 2026-08-12 的 GC001 卖出、申能转债入账）的金额与操作。
6. 默认第一个账户（空空如也）若近 30 天无流水，显示「近30天无流水记录」占位行——这是正常现象，切换 Tab 看其他账户。

- [ ] **Step 7: 提交（默认跳过）**

---

## Task 5: 隐私模式覆盖 + 整体验收

**Files:**
- Modify: `/Users/apple/Documents/分析报告/code/dashboard/index.html`（隐私 CSS）

- [ ] **Step 1: 隐私 CSS 覆盖三张新卡**

在 `body.privacy .pos-mini td:nth-child(8) { filter: blur(5px); user-select: none; }` 这一行之后追加：

```css
  body.privacy #chart-monthly,
  body.privacy #cash-tbody td:nth-child(5),
  body.privacy #wl-tbody td:nth-child(2),
  body.privacy #wl-tbody td:nth-child(3),
  body.privacy .wl-avg { filter: blur(5px); user-select: none; }
```

- [ ] **Step 2: 整体验收（规格第 6 节验收清单）**

浏览器打开 http://localhost:8888，逐项检查：

1. **三卡渲染**：月度收益（12 根柱 + 4 Tab）、自选行情（213 行 + 分布条 + 排序）、资金流水（表格 + 3 Tab + 加载更多）全部正常。
2. **月度卡合计**：Console 执行
   ```js
   // 校验总合计 = 分账户之和
   const sum = {};
   Object.values(monthlyData).forEach(arr => arr.forEach(d => { sum[d.month] = (sum[d.month] || 0) + d.profit; }));
   monthlyData['宁静致远'].map(d => d.month).forEach(m => {
     const tabSum = Object.values(monthlyData).reduce((s, arr) => s + (arr.find(x => x.month === m)?.profit || 0), 0);
     if (Math.abs(sum[m] - tabSum) > 0.01) console.error('合计不一致', m);
   });
   console.log('合计校验通过');
   ```
   Expected: 输出 `合计校验通过`。
3. **流水翻页**：连续点「加载更多」直至按钮消失，行数不重复、不丢失。
4. **自选排序**：三种排序切换各检查一次首行是否正确。
5. **隐私模式**：点 👁 后月度图、流水金额列、自选现价/涨跌幅列、平均涨跌幅全部模糊；再点恢复。
6. **刷新**：点顶栏 ⟳ 后三卡重新加载且数据正确；Console 检查月度卡不产生新的 echarts 实例警告。
7. **server.js 零改动**：`git diff --stat server.js` 输出为空（若 server.js 有改动则视为失败，回查任务执行）。
8. **回归**：既有 7 卡（时段、温度计、热力图、K线、资产走势、账户概览、持仓明细）无异常。

- [ ] **Step 3: 提交（默认跳过）**
