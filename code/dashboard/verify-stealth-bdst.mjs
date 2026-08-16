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
await p.waitForTimeout(1200);
// 切摸鱼模式
await p.evaluate(() => toggleStealth());
await p.waitForTimeout(1500);
// 从 canvas 取分布图柱子颜色（读系列颜色：检查 chart option? 直接读 body class + 截图）
const stealth = await p.evaluate(() => document.body.classList.contains('stealth'));
// 通过图表数据取色：读第一个正柱与负柱的 itemStyle 颜色 —— 直接 eval 调用内部函数拿 colors
const colors = await p.evaluate(() => {
  // 重新触发渲染拿颜色（内部变量不可直接读，改用 canvas 像素？）
  // 简化：检查 bdstChart 存在 + 截图分析
  return { hasChart: !!window.bdstChart };
});
console.log('stealth:', stealth, '| bdstChart:', colors.hasChart);
await p.screenshot({ path: '/tmp/stealth-bdst.png', fullPage: true });
console.log('JS错误:', errs.length);
errs.slice(0, 3).forEach(e => console.log('  ✗', e.slice(0, 120)));
await b.close();
