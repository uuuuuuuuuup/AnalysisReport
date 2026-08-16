import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1600, height: 2200 } });
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log('goto fail:', e.message.slice(0, 80)));
for (const t of [2000, 5000, 10000]) {
  await p.waitForTimeout(t === 2000 ? 2000 : t - (t - 2000 - 3000 > 0 ? 3000 : 0)).catch(() => {});
  const s = await p.evaluate(() => ({
    loadingDisplay: getComputedStyle(document.getElementById('loading')).display,
    loadingHidden: document.getElementById('loading').style.display,
    errBanner: document.getElementById('error-banner')?.textContent?.slice(0, 40),
  }));
  console.log(t + 'ms:', JSON.stringify(s));
}
await b.close();
