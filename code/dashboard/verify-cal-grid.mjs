import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1600, height: 2200 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(1500);
await p.evaluate(() => { document.getElementById('loading').style.display = 'none'; });
// 切每日盈亏
await p.click('.area-tabA .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1500);
const cells = await p.locator('#chart-monthly .month-cell').count();
const cell0 = await p.locator('#chart-monthly .month-cell').first().boundingBox();
const gridBox = await p.locator('#chart-monthly').boundingBox();
console.log('格子数:', cells);
console.log('容器:', gridBox && `${Math.round(gridBox.width)}x${Math.round(gridBox.height)}`);
console.log('首格:', cell0 && `${Math.round(cell0.width)}x${Math.round(cell0.height)}`);
console.log('title示例:', await p.locator('#chart-monthly .month-cell').first().getAttribute('title'));
console.log('status:', (await p.locator('#monthly-status').textContent()).slice(0, 60));
// 格子分布：首格 grid-column/grid-row
const pos = await p.locator('#chart-monthly .month-cell').first().evaluate(el => getComputedStyle(el).gridColumnStart + '/' + getComputedStyle(el).gridRowStart);
console.log('首格位置 col/row:', pos);
console.log('JS错误:', errs.length);
errs.slice(0, 3).forEach(e => console.log('  ✗', e.slice(0, 120)));
await p.screenshot({ path: '/tmp/calgrid.png', fullPage: true });
await b.close();
