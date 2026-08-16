import { chromium } from 'playwright';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage();
page.on('response', r => { if (r.status() === 404) console.log('404:', r.url()); });
page.on('requestfailed', r => console.log('FAILED:', r.url(), r.failure()?.errorText));
await page.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(3000);
await browser.close();
