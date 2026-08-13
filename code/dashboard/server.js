#!/usr/bin/env node
/**
 * 投资账本看板 - 纯 JS 服务器
 * 零依赖，仅需 Node.js 内置模块
 * 用法: node server.js
 *      然后访问 http://localhost:8888
 */

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

const PORT = 8888;
const COOKIE_FILE = path.join(require('os').homedir(), '.tzzb_cookies');
const STATIC_DIR = __dirname;
const API_BASE = 'tzzb.10jqka.com.cn';

function readCookie() {
  try { return fs.readFileSync(COOKIE_FILE, 'utf-8').trim(); }
  catch { return null; }
}

function readFile(filePath) {
  try { return fs.readFileSync(filePath); }
  catch { return null; }
}

function mimeType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return {
    '.html': 'text/html; charset=utf-8',
    '.js':   'application/javascript; charset=utf-8',
    '.css':  'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png':  'image/png',
    '.svg':  'image/svg+xml',
    '.ico':  'image/x-icon',
  }[ext] || 'application/octet-stream';
}

function proxyAPI(reqPath, method, cookie, res) {
  const targetPath = reqPath.replace(/^\/api/, '');
  // Build the full URL with query params
  const fullPath = 'https://' + API_BASE + '/caishen_httpserver/tzzb' + targetPath;

  console.log(`  ↳ ${method} ${targetPath}`);

  const req = https.request(fullPath, {
    method: method,
    headers: {
      'Cookie': cookie,
      'User-Agent': 'Mozilla/5.0',
      'Referer': 'https://tzzb.10jqka.com.cn/',
    }
  }, (proxyRes) => {
    let body = '';
    proxyRes.on('data', chunk => body += chunk);
    proxyRes.on('end', () => {
      res.writeHead(proxyRes.statusCode, {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': '*',
      });
      res.end(body);
    });
  });

  req.on('error', (e) => {
    res.writeHead(502);
    res.end(JSON.stringify({error: 'Proxy error: ' + e.message}));
  });

  req.end();
}

function proxyKline(code, market, res) {
  const cookie = readCookie();
  if (!cookie) { res.writeHead(401); res.end(JSON.stringify({error:'No cookie'})); return; }

  // Extract userid from cookie
  const uidMatch = cookie.match(/userid=(\d+)/);
  const uid = uidMatch ? uidMatch[1] : '';

  const mktCode = market + ':' + code;

  // Generate last 60 trading days
  const tradingDays = [];
  const now = new Date();
  let d = new Date(now);
  while (tradingDays.length < 60) {
    const day = d.getDay();
    if (day !== 0 && day !== 6) {
      tradingDays.push(d.toISOString().slice(0,10).replace(/-/g, ''));
    }
    d.setDate(d.getDate() - 1);
  }
  tradingDays.reverse();

  // Fetch in parallel batches of 10
  const results = [];
  let completed = 0;
  const total = tradingDays.length;

  function fetchBatch(start) {
    const batch = tradingDays.slice(start, start + 10);
    if (!batch.length) {
      // Done - return results
      const dates = [], closes = [];
      results.sort((a,b) => a.date.localeCompare(b.date));
      results.forEach(r => { dates.push(r.date); closes.push(r.close); });
      res.writeHead(200, {'Content-Type':'application/json; charset=utf-8'});
      res.end(JSON.stringify({code, dates, closes}));
      return;
    }

    let batchDone = 0;
    batch.forEach(dateStr => {
      const dateFormatted = dateStr.slice(0,4)+'-'+dateStr.slice(4,6)+'-'+dateStr.slice(6);
      const params = new URLSearchParams({
        terminal:'1', version:'0.0.0', userid: uid,
        code: mktCode, date: dateStr
      });
      const url = 'https://' + API_BASE + '/caishen_httpserver/tzzb/caishen_fund/invest/getQuotes?' + params.toString();

      https.get(url, {
        headers: { 'Cookie': cookie, 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://tzzb.10jqka.com.cn/' }
      }, (pres) => {
        let body = '';
        pres.on('data', chunk => body += chunk);
        pres.on('end', () => {
          try {
            const data = JSON.parse(body);
            const quote = data?.ex_data?.[0];
            if (quote?.xianjia) {
              results.push({date: dateFormatted, close: parseFloat(quote.xianjia)});
            }
          } catch(e) {}
          batchDone++;
          if (batchDone === batch.length) {
            completed += batch.length;
            fetchBatch(start + 10);
          }
        });
      }).on('error', () => {
        batchDone++;
        if (batchDone === batch.length) {
          completed += batch.length;
          fetchBatch(start + 10);
        }
      });
    });
  }

  fetchBatch(0);
}

// Build the HTML with embedded API proxy info
function serveDashboard(res) {
  let html = readFile(path.join(STATIC_DIR, 'index.html'));
  if (!html) {
    res.writeHead(404);
    res.end('index.html not found');
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(html);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:' + PORT);
  const pathname = url.pathname;
  const method = req.method;

  // API proxy
  if (pathname.startsWith('/api/')) {
    const cookie = readCookie();
    if (!cookie) {
      res.writeHead(401);
      res.end(JSON.stringify({error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies'}));
      return;
    }
    // Reconstruct the full path with query string
    const fullPath = pathname + (url.search || '');
    return proxyAPI(fullPath, method, cookie, res);
  }

  // Cookie status check
  if (pathname === '/api-check') {
    const cookie = readCookie();
    // Extract userid from cookie string
    let userid = '';
    if (cookie) {
      const m = cookie.match(/userid=(\d+)/);
      if (m) userid = m[1];
    }
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({has_cookie: !!cookie, userid}));
    return;
  }

  // K-line: close price history from tzzb getQuotes
  if (pathname.startsWith('/kline/')) {
    const code = pathname.split('/')[2];
    const market = url.searchParams.get('market') || '2';
    if (code) return proxyKline(code, market, res);
  }

  // Static files
  let filePath = pathname === '/' ? '/index.html' : pathname;
  // Security: prevent directory traversal
  filePath = path.normalize(filePath).replace(/^(\.\.[\/\\])+/, '');
  const fullPath = path.join(STATIC_DIR, filePath);

  const content = readFile(fullPath);
  if (content) {
    res.writeHead(200, { 'Content-Type': mimeType(fullPath) });
    res.end(content);
  } else {
    res.writeHead(404);
    res.end('404 Not Found');
  }
});

server.listen(PORT, () => {
  const url = `http://localhost:${PORT}`;
  console.log('');
  console.log('  📊 投资账本 · 金融终端');
  console.log(`  → ${url}`);
  console.log('');

  const cookie = readCookie();
  if (!cookie) {
    console.log('  ⚠️  未找到 Cookie 文件');
    console.log(`     请创建 ${COOKIE_FILE} 并写入浏览器 Cookie`);
  }

  // Auto-open browser
  const platform = process.platform;
  const openCmd = platform === 'darwin' ? 'open' : platform === 'win32' ? 'start' : 'xdg-open';
  exec(`${openCmd} ${url}`);
});
