import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const p = await b.newPage({ viewport: { width: 1700, height: 2300 } });
await p.goto('http://127.0.0.1:8899/', { waitUntil: 'networkidle', timeout: 60000 });
await p.waitForTimeout(4000);
const geo = await p.evaluate(() => {
  const out = {};
  for (const name of ['tabA', 'tabB', 'candl', 'mf', 'news', 'bdst']) {
    const el = document.querySelector('.area-' + name);
    if (el) { const r = el.getBoundingClientRect(); out[name] = `x=${Math.round(r.x)} y=${Math.round(r.y)} w=${Math.round(r.width)} h=${Math.round(r.height)}`; }
  }
  return out;
});
for (const [k, v] of Object.entries(geo)) console.log(k.padEnd(6), v);
await b.close();
