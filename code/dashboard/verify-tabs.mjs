import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1700, height: 2300 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
p.on('console', m => { if (m.type() === 'error') errs.push('CON: ' + m.text().slice(0, 120)); });
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 60000 });
await p.waitForTimeout(5000);

// tabA: 切每日盈亏 → 日历 chart canvas 出现
await p.click('.area-tabA .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1200);
const calCanvas = await p.locator('#chart-monthly canvas').count();
const calTitle = await p.locator('#monthly-status').textContent();
console.log('[tabA→盈亏] canvas:', calCanvas, '| status:', (calTitle || '').slice(0, 40));

// tabA: 资金流水 → 表格行
await p.click('.area-tabA .pane-tabs button:nth-child(3)');
await p.waitForTimeout(800);
const cashRows = await p.locator('#cash-tbody tr').count();
console.log('[tabA→流水] 行数:', cashRows);

// tabA: 回总资产 → 无chart-index
const hasChartIndex = await p.locator('#pane-index #chart-index').count();
console.log('[tabA→总资产] chart-index 已移除:', hasChartIndex === 0);

// tabB: 持仓权重
await p.click('.area-tabB .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1200);
const holdCanvas = await p.locator('#chart-holdings canvas').count();
const holdEl = await p.locator('#chart-holdings canvas').first().boundingBox();
console.log('[tabB→持仓权重] canvas:', holdCanvas, '| 尺寸:', holdEl && Math.round(holdEl.width) + 'x' + Math.round(holdEl.height));

// tabB: 回股票列表
await p.click('.area-tabB .pane-tabs button:nth-child(1)');
await p.waitForTimeout(600);
const posRows = await p.locator('#pos-tbody tr').count();
console.log('[tabB→股票列表] 持仓行:', posRows);

// 布局 box
const boxes = {};
for (const [name, sel] of [['tabA', '.area-tabA'], ['mf', '.area-mf'], ['candl', '.area-candl'], ['tabB', '.area-tabB'], ['news', '.area-news'], ['bdst', '.area-bdst']]) {
  const bb = await p.locator(sel).boundingBox();
  boxes[name] = bb ? `${Math.round(bb.y)}y/${Math.round(bb.width)}w` : 'NONE';
}
console.log('布局:', JSON.stringify(boxes));
console.log('JS错误:', errs.length);
errs.slice(0, 5).forEach(e => console.log('  ✗', e));
await p.screenshot({ path: '/tmp/layout-tabs.png', fullPage: true });
await b.close();
