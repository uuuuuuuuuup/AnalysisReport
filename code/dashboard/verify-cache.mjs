import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const ctx = await b.newContext();
const p = await ctx.newPage({ viewport: { width: 1500, height: 900 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGE: ' + e.message));
// 首次加载
let t0 = Date.now();
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 90000 });
const first = Date.now() - t0;
const cacheInfo = await p.evaluate(() => {
  const raw = localStorage.getItem('tzzb_accounts_cache_v1');
  return raw ? { has: true, size: raw.length, accounts: JSON.parse(raw).accounts.length } : { has: false };
});
console.log('首次加载:', first + 'ms', '| 缓存:', JSON.stringify(cacheInfo));
// 二次加载（模拟切页回来）
t0 = Date.now();
await p.goto('http://127.0.0.1:8899/?x=2', { waitUntil: 'networkidle', timeout: 90000 });
const second = Date.now() - t0;
console.log('二次加载:', second + 'ms');
console.log('持仓行:', await p.locator('#pos-tbody tr').count());
console.log('JS错误:', errs.length);
errs.slice(0, 3).forEach(e => console.log('  ✗', e.slice(0, 100)));
await b.close();
