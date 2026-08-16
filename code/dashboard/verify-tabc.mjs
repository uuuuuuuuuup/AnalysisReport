import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1600, height: 2200 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(1500);
await p.evaluate(() => { document.getElementById('loading').style.display = 'none'; });
// tabC 默认 K线
const klineBox = await p.locator('#chart-kline canvas').boundingBox();
console.log('[tabC→K线] canvas:', klineBox && `${Math.round(klineBox.width)}x${Math.round(klineBox.height)}`);
const ohlc = await p.locator('#ohlc-row').textContent();
console.log('OHLC:', (ohlc || '').slice(0, 40));
// 切到持仓权重
await p.click('.area-tabC .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1200);
const holdBox = await p.locator('#chart-holdings canvas').boundingBox();
console.log('[tabC→持仓权重] canvas:', holdBox && `${Math.round(holdBox.width)}x${Math.round(holdBox.height)}`);
// 切回 K线
await p.click('.area-tabC .pane-tabs button:nth-child(1)');
await p.waitForTimeout(800);
const kline2 = await p.locator('#chart-kline canvas').boundingBox();
console.log('[tabC→切回K线] canvas:', kline2 && `${Math.round(kline2.width)}x${Math.round(kline2.height)}`);
// 布局几何
const geo = await p.evaluate(() => {
  const g = {};
  for (const n of ['tabA', 'tabB', 'tabC', 'mf', 'news', 'bdst']) {
    const el = document.querySelector('.area-' + n);
    if (el) { const r = el.getBoundingClientRect(); g[n] = `${Math.round(r.y)}y/${Math.round(r.width)}w/${Math.round(r.height)}h`; }
  }
  return g;
});
console.log('布局:', JSON.stringify(geo));
console.log('JS错误:', errs.length);
errs.slice(0, 4).forEach(e => console.log('  ✗', e.slice(0, 120)));
await p.screenshot({ path: '/tmp/tabc.png', fullPage: true });
await b.close();
