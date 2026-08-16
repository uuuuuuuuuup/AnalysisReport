import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1600, height: 2200 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(1500);
await p.evaluate(() => { document.getElementById('loading').style.display = 'none'; });
// 默认股票列表
console.log('[默认→股票列表] 持仓行:', await p.locator('#pos-tbody tr').count());
// K线 tab
await p.click('.area-tabB .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1500);
const kb = await p.locator('#chart-kline canvas').boundingBox();
console.log('[tab→K线] canvas:', kb && `${Math.round(kb.width)}x${Math.round(kb.height)}`, '| OHLC:', (await p.locator('#ohlc-row').textContent()).slice(0, 30));
// 持仓权重 tab
await p.click('.area-tabB .pane-tabs button:nth-child(3)');
await p.waitForTimeout(1200);
const hb = await p.locator('#chart-holdings canvas').boundingBox();
console.log('[tab→持仓权重] canvas:', hb && `${Math.round(hb.width)}x${Math.round(hb.height)}`);
// 回股票列表
await p.click('.area-tabB .pane-tabs button:nth-child(1)');
await p.waitForTimeout(600);
console.log('[tab→回股票列表] 持仓行:', await p.locator('#pos-tbody tr').count());
// 几何
const geo = await p.evaluate(() => {
  const g = {};
  for (const n of ['tabA', 'tabB', 'mf', 'news', 'bdst']) {
    const el = document.querySelector('.area-' + n);
    if (el) { const r = el.getBoundingClientRect(); g[n] = `${Math.round(r.y)}y/${Math.round(r.height)}h`; }
  }
  return g;
});
console.log('布局:', JSON.stringify(geo));
console.log('JS错误:', errs.length);
errs.slice(0, 4).forEach(e => console.log('  ✗', e.slice(0, 120)));
await p.screenshot({ path: '/tmp/tri.png', fullPage: true });
await b.close();
