import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1600, height: 2200 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(1500);
await p.evaluate(() => { document.getElementById('loading').style.display = 'none'; });
// 切市场宽度
await p.click('.area-tabD .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1500);
const dist = await p.locator('#chart-bdst canvas').boundingBox();
console.log('[市场宽度] 分布图:', dist && `${Math.round(dist.width)}x${Math.round(dist.height)}`);
console.log('内容:', (await p.locator('#bdst-body').textContent()).replace(/\s+/g, ' ').slice(0, 220));
// 切回资金流向
await p.click('.area-tabD .pane-tabs button:nth-child(1)');
await p.waitForTimeout(800);
console.log('[回资金流向] canvas:', await p.locator('#chart-mf canvas').count());
console.log('JS错误:', errs.length);
errs.slice(0, 3).forEach(e => console.log('  ✗', e.slice(0, 120)));
await p.screenshot({ path: '/tmp/bdst-final.png', fullPage: true });
await b.close();
