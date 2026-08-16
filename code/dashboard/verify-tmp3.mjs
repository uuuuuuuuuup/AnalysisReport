import { chromium } from 'playwright';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
await page.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('#news-list .news-item', { timeout: 15000 });

// 1. 分类过滤
const totalBefore = await page.locator('#news-list .news-item').count();
const tagBtns = page.locator('#news-tabs .index-tab');
const tagCount = await tagBtns.count();
await tagBtns.nth(1).click();
await page.waitForTimeout(300);
const afterFilter = await page.locator('#news-list .news-item').count();
const activeTab = await page.locator('#news-tabs .index-tab.active').textContent();
console.log(`[标签] 共${tagCount}个 | 点击第2个「${activeTab.trim().slice(0,6)}」后显示${afterFilter}条 (过滤前${totalBefore})`);
await tagBtns.first().click(); // 回到全部

// 2. 市场宽度在 clicking 后仍存在
const bdst = await page.locator('#bdst-body').textContent();
console.log('[宽度]', bdst.replace(/\s+/g,' ').slice(0, 120));

// 3. 摸鱼模式 → 标签变灰
await page.evaluate(() => localStorage.setItem('tzzb_stealth', '1'));
await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(2000);
const dark = await page.evaluate(() => {
  const t = document.querySelector('#news-list .news-tag');
  if (!t) return 'no-tag';
  const s = getComputedStyle(t);
  return `filter=${s.filter} opacity=${s.opacity} color=${s.color}`;
});
console.log('[摸鱼] news-tag:', dark);
const errs = await page.evaluate(() => document.getElementById('news-meta').textContent);
console.log('[meta]', errs);
console.log('[errors]', errors.length);
errors.forEach(e => console.log('  X', e.slice(0,150)));
await browser.close();
