import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1600, height: 2200 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(1500);
await p.evaluate(() => { document.getElementById('loading').style.display = 'none'; });
const geo = await p.evaluate(() => {
  const g = {};
  for (const n of ['tabA', 'news', 'tabB', 'tabD']) {
    const el = document.querySelector('.area-' + n);
    if (el) { const r = el.getBoundingClientRect(); g[n] = `${Math.round(r.y)}y..${Math.round(r.y + r.height)}y`; }
  }
  return g;
});
console.log('布局:', JSON.stringify(geo));
console.log('news底 == tabB底:', geo.news.split('..')[1] === geo.tabB.split('..')[1] ? '✓' : '✗');
// 持仓内容恰好展示检查：股票列表 25 行是否全可见（无内部滚动截断）
const posScroll = await p.evaluate(() => {
  const pane = document.getElementById('stk-pane-pos');
  const scroller = pane.querySelector('.scroll-y');
  return { client: scroller.clientHeight, scroll: scroller.scrollHeight };
});
console.log('股票列表滚动:', JSON.stringify(posScroll), posScroll.scroll > posScroll.client ? '→ 有滚动' : '→ 恰好展示');
// 新闻可见条数
await p.click('.area-tabA .pane-tabs button:nth-child(2)');
await p.waitForTimeout(1200);
console.log('每日盈亏格子:', await p.locator('#chart-monthly .month-cell').count());
console.log('JS错误:', errs.length);
errs.slice(0, 3).forEach(e => console.log('  ✗', e.slice(0, 100)));
await b.close();
