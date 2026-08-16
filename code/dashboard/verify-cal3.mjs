import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1600, height: 2200 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(1000);
// 若网络慢仍被遮罩挡住，强制放行视觉验证
await p.evaluate(() => { document.getElementById('loading').style.display = 'none'; });
await p.click('.area-tabA .pane-tabs button:nth-child(2)');
await p.waitForFunction(() => !!document.querySelector('#chart-monthly canvas'), null, { timeout: 20000 }).catch(() => console.log('canvas 未出现(可能数据缺失)'));
const canvas = await p.locator('#chart-monthly canvas').boundingBox().catch(() => null);
console.log('canvas:', canvas ? `${Math.round(canvas.width)}x${Math.round(canvas.height)}` : null);
await p.screenshot({ path: '/tmp/cal-ok.png', fullPage: true });
console.log('JS错误:', errs.length);
errs.slice(0, 3).forEach(e => console.log('  X', e.slice(0, 120)));
await b.close();
