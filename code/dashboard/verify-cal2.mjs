import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1500, height: 2000, deviceScaleFactor: 1 } }); // DPR=1 → CSS px = 物理 px
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 60000 });
await p.waitForTimeout(3500);
await p.click('.area-tabA .pane-tabs button:nth-child(2)'); // 每日盈亏 tab
await p.waitForTimeout(1200);
const box = await p.locator('#chart-monthly canvas').boundingBox();
// 以 CSS 坐标裁减日历 canvas
const clip = { x: box.x, y: box.y, width: box.width, height: box.height };
await p.screenshot({ path: '/tmp/cal-1x.png', clip }); // PNG 尺寸 = CSS 尺寸（DPR=1）
await b.close();
