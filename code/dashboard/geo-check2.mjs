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
    if (el) { const r = el.getBoundingClientRect(); g[n] = `${Math.round(r.y)}y/${Math.round(r.height)}h/${Math.round(r.bottom)}b`; }
  }
  return g;
});
console.log('布局:', JSON.stringify(geo));
const newsBottom = geo.news.split('/')[2];
const tabBBottom = geo.tabB.split('/')[2];
console.log('底部对齐:', newsBottom === tabBBottom ? '✓ 一致' : `✗ news=${newsBottom} tabB=${tabBBottom}`);
// 持仓列表是否恰好展示（25 行滚动区内）
const posCount = await p.locator('#pos-tbody tr').count();
console.log('持仓行数:', posCount);
// 新闻可见条数估算
const newsItems = await p.locator('#news-list .news-item').count();
console.log('新闻渲染:', newsItems, '条（滚动区）');
console.log('JS错误:', errs.length);
errs.slice(0, 3).forEach(e => console.log('  ✗', e.slice(0, 120)));
await p.screenshot({ path: '/tmp/height-fit.png', fullPage: true });
await b.close();
