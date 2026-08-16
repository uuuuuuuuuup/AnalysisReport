import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1600, height: 2200 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(1500);
await p.evaluate(() => { document.getElementById('loading').style.display = 'none'; });
// 几何
const geo = await p.evaluate(() => {
  const g = {};
  for (const n of ['tabA', 'news', 'tabB', 'tabD']) {
    const el = document.querySelector('.area-' + n);
    if (el) { const r = el.getBoundingClientRect(); g[n] = `${Math.round(r.y)}y/${Math.round(r.height)}h`; }
  }
  return g;
});
console.log('布局:', JSON.stringify(geo));
// tabD 默认资金流向
console.log('[tabD→资金流向] canvas:', await p.locator('#chart-mf canvas').count());
// tabD 市场宽度（全市场）
await p.click('.area-tabD .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1200);
console.log('[tabD→市场宽度]:', (await p.locator('#bdst-body').textContent()).replace(/\s+/g, ' ').slice(0, 200));
// 切回资金流向
await p.click('.area-tabD .pane-tabs button:nth-child(1)');
await p.waitForTimeout(800);
console.log('[tabD→回资金流向] canvas:', await p.locator('#chart-mf canvas').count());
// 持仓三合一 tabB 正常
await p.click('.area-tabB .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1200);
console.log('[tabB→K线] canvas:', await p.locator('#chart-kline canvas').count(), '| OHLC:', (await p.locator('#ohlc-row').textContent()).slice(0, 24));
await p.click('.area-tabB .pane-tabs button:nth-child(1)');
console.log('新闻条数:', await p.locator('#news-list .news-item').count());
console.log('JS错误:', errs.length);
errs.slice(0, 4).forEach(e => console.log('  ✗', e.slice(0, 120)));
await p.screenshot({ path: '/tmp/final2.png', fullPage: true });
await b.close();
