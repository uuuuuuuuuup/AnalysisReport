# 看板第三期：TS 迁移 + AI Agent「灵犀」实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `server.js` → `server.ts`（TypeScript + Vercel AI SDK v4），新增 AI Agent「灵犀」对话接口（7 个 Tool、`streamText` 真流式 SSE、JSON 文件会话持久化），`index.html` 新增可折叠 AI 面板——现有 7 张卡片代码零改动。

**Architecture:** 纯 Node 内置 `http` 服务器 + `tsx` 直跑 TS（无构建步骤）。Agent 用 AI SDK v4 的 `streamText` + `maxSteps`（自动 tool-call 循环，替代手写 while）；Tool 执行通过**回环调用**本服务器现有代理路由（`http://localhost:8888/api/...`、`/proxy/...`）100% 复用 cookie/防盗链逻辑；会话历史存 `~/.tzzb_ai_sessions.json`（原子写入，SDK 原始消息格式直接回存）；前端面板用原生 `fetch` + 手写 SSE 解析，与 server 仅 HTTP 通信。

**Tech Stack:** Node ≥ 18（内置 fetch）、tsx、TypeScript strict、`ai@4.3.x` + `@ai-sdk/deepseek@0.2.x` + `zod@3.x`、原生 SSE（手写帧）、无测试框架（验证方式 = `tsc --noEmit` + curl + 浏览器，与一/二期一致）。

**约定：** 本计划**不含 git 提交步骤**（用户惯例：默认跳过提交，除非明确指示）。

---

## 与已确认计划（2026-08-15 设计稿）的两处小修正

| 修正 | 理由 |
|------|------|
| tsconfig `module: NodeNext` → `module: ESNext` + `moduleResolution: Bundler` | 扩展名省略的相对导入（`import { ALL_TOOLS } from './tools'`）在 `tsc --noEmit` 下不报错；tsx 官方推荐配置 |
| package.json 增加 `"zod": "^3.24.0"` | `ai@4.x` 的 tool 定义用 `z.object(...)`，zod 是 `ai` 的 peerDependency 但 tools.ts 直接 import，必须显式声明（实测 `ai@4.3.19` peerDep 为 `zod ^3.23.8`）。npm 会自动装上 `react`（`ai` 的另一个 peer，仅 React 子路径需要）——无害，忽略即可 |

## 环境约定

- 工作目录：`/Users/apple/Documents/分析报告/code/dashboard`
- 启动：`npx tsx server.ts`；页面 `http://localhost:8888`；启动自动开浏览器（保留现有行为）
- Cookie：`~/.tzzb_cookies`（现有机制不动）；API Key：`TZZB_AI_KEY` 环境变量或 `~/.tzzb_ai_key` 文件；会话：`~/.tzzb_ai_sessions.json`（运行时生成）
- 备份：`server.js` → `server.js.bak`，确认后删除

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `package.json` | 新增 | npm 配置（type: module，ai/@ai-sdk-deepseek/zod + tsx/typescript） |
| `tsconfig.json` | 新增 | 严格类型检查配置（tsx 直跑，无编译产物） |
| `.gitignore` | 新增 | node_modules、*.js.bak |
| `server.ts` | 新增 | 原 server.js 的 TS 翻译 + Agent 路由/会话/SSE（唯一入口） |
| `tools.ts` | 新增 | 7 个 Tool 的 schema 与 execute（纯数据获取，无会话概念） |
| `index.html` | 修改（仅追加） | AI 面板 HTML/CSS/JS 三块新增，现有代码不动 |
| `server.js` | 备份 | → `server.js.bak` |

依赖方向：`server.ts` → `tools.ts`（单向，无循环）。

---

## Task 1: 项目初始化（npm + TypeScript 配置）

**Files:**
- Create: `/Users/apple/Documents/分析报告/code/dashboard/package.json`
- Create: `/Users/apple/Documents/分析报告/code/dashboard/tsconfig.json`
- Create: `/Users/apple/Documents/分析报告/code/dashboard/.gitignore`

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "tzzb-dashboard",
  "version": "3.0.0",
  "private": true,
  "description": "投资账本看板 - 金融终端（AI Agent 版）",
  "type": "module",
  "scripts": {
    "start": "tsx server.ts",
    "dev": "tsx watch server.ts",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "ai": "^4.3.0",
    "@ai-sdk/deepseek": "^0.2.0",
    "zod": "^3.24.0"
  },
  "devDependencies": {
    "typescript": "^5.8.0",
    "@types/node": "^22.0.0",
    "tsx": "^4.19.0"
  }
}
```

- [ ] **Step 2: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true
  },
  "include": ["server.ts", "tools.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: 创建 .gitignore**

```
node_modules/
*.js.bak
```

- [ ] **Step 4: 安装依赖**

```bash
cd /Users/apple/Documents/分析报告/code/dashboard
npm install
```

- [ ] **Step 5: 验证**

```bash
npx tsx --version    # 期望: 输出版本号（如 4.x）
npx tsc --version    # 期望: Version 5.x
node --version       # 期望: ≥ 18（内置 fetch/AbortController）
```

---

## Task 2: server.js → server.ts 纯翻译

**Files:**
- Create: `/Users/apple/Documents/分析报告/code/dashboard/server.ts`（整文件替换为下方代码）
- Backup: `server.js` → `server.js.bak`

**原则：** 纯翻译，不加新功能。仅有的两处"非逻辑"改动：`proxyRes.setEncoding('utf8')`（TS 下 `body += chunk` 需要 string 类型）、`proxyRes.statusCode ?? 502`（strict 模式下 statusCode 为 `number | undefined`）。

- [ ] **Step 1: 备份原文件**

```bash
cd /Users/apple/Documents/分析报告/code/dashboard
cp server.js server.js.bak
```

- [ ] **Step 2: 创建 server.ts（完整代码）**

```typescript
#!/usr/bin/env node
/**
 * 投资账本看板 - TypeScript 服务器
 * 用法: npx tsx server.ts
 *      然后访问 http://localhost:8888
 */

import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { exec } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { IncomingMessage, ServerResponse } from 'node:http';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = 8888;
const COOKIE_FILE = path.join(os.homedir(), '.tzzb_cookies');
const STATIC_DIR = __dirname;
const API_BASE = 'tzzb.10jqka.com.cn';

function readCookie(): string | null {
  try { return fs.readFileSync(COOKIE_FILE, 'utf-8').trim(); }
  catch { return null; }
}

function readFile(filePath: string): Buffer | null {
  try { return fs.readFileSync(filePath); }
  catch { return null; }
}

function mimeType(filePath: string): string {
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

function proxyAPI(reqPath: string, method: string | undefined, cookie: string, res: ServerResponse): void {
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
    proxyRes.setEncoding('utf8');
    proxyRes.on('data', chunk => body += chunk);
    proxyRes.on('end', () => {
      res.writeHead(proxyRes.statusCode ?? 502, {
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

// 外部行情代理（腾讯K线 / 新浪资金流），带防盗链头
function proxyExternal(urlStr: string, referer: string, res: ServerResponse): void {
  console.log(`  ↳ GET ${urlStr.slice(0, 90)}`);
  const req = https.get(urlStr, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Referer': referer,
    }
  }, (proxyRes) => {
    let body = '';
    proxyRes.setEncoding('utf8');
    proxyRes.on('data', chunk => body += chunk);
    proxyRes.on('end', () => {
      res.writeHead(proxyRes.statusCode ?? 502, {
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
}

function proxyKline(code: string, market: string, res: ServerResponse): void {
  const cookie = readCookie();
  if (!cookie) { res.writeHead(401); res.end(JSON.stringify({error:'No cookie'})); return; }

  // Extract userid from cookie
  const uidMatch = cookie.match(/userid=(\d+)/);
  const uid = uidMatch ? uidMatch[1] : '';

  const mktCode = market + ':' + code;

  // Generate last 60 trading days
  const tradingDays: string[] = [];
  const now = new Date();
  const d = new Date(now);
  while (tradingDays.length < 60) {
    const day = d.getDay();
    if (day !== 0 && day !== 6) {
      tradingDays.push(d.toISOString().slice(0,10).replace(/-/g, ''));
    }
    d.setDate(d.getDate() - 1);
  }
  tradingDays.reverse();

  // Fetch in parallel batches of 10
  const results: {date: string, close: number}[] = [];
  let completed = 0;
  const total = tradingDays.length;

  function fetchBatch(start: number): void {
    const batch = tradingDays.slice(start, start + 10);
    if (!batch.length) {
      // Done - return results
      const dates: string[] = [], closes: number[] = [];
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
        // cookie!：fetchBatch 闭包内 TS 不做 control-flow narrowing，非空断言无运行时效果（外层 401 守卫已保证非 null）
        headers: { 'Cookie': cookie!, 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://tzzb.10jqka.com.cn/' }
      }, (pres) => {
        let body = '';
        pres.setEncoding('utf8');
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
function serveDashboard(res: ServerResponse): void {
  const html = readFile(path.join(STATIC_DIR, 'index.html'));
  if (!html) {
    res.writeHead(404);
    res.end('index.html not found');
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(html);
}

const server = http.createServer((req: IncomingMessage, res: ServerResponse) => {
  const url = new URL(req.url ?? '/', 'http://localhost:' + PORT);
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

  // 腾讯 K 线（前复权日K，含 OHLC + 成交量）: /proxy/kline?code=sh600519&count=120
  if (pathname.startsWith('/proxy/kline')) {
    const code = url.searchParams.get('code') || '';
    const count = url.searchParams.get('count') || 120;
    const period = url.searchParams.get('period') || 'day';
    const target = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${encodeURIComponent(`${code},${period},,,${count},qfq`)}`;
    return proxyExternal(target, 'https://gu.qq.com/', res);
  }

  // 新浪个股资金流排行: /proxy/moneyflow?order=desc|asc&num=12
  if (pathname.startsWith('/proxy/moneyflow')) {
    const order = url.searchParams.get('order') === 'asc' ? 1 : 0;
    const num = url.searchParams.get('num') || 12;
    const target = `https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_ssggzj?page=1&num=${num}&sort=netamount&asc=${order}&bankuai=&shichang=`;
    return proxyExternal(target, 'https://finance.sina.com.cn/', res);
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
```

- [ ] **Step 3: 类型检查**

```bash
cd /Users/apple/Documents/分析报告/code/dashboard
npx tsc --noEmit
```
期望：无任何输出（0 错误）。

- [ ] **Step 4: 运行验证（迁移无回归）**

```bash
npx tsx server.ts
```
期望：终端输出 `📊 投资账本 · 金融终端 → http://localhost:8888`，自动打开浏览器；页面 7 张卡片正常渲染（资产总览/持仓明细/自选行情/月度收益热力图/K线图/资金流排行/资金流水），Cookie 检查正常。验证后 Ctrl+C 停掉。

---

## Task 3: tools.ts（7 个 Tool）

**Files:**
- Create: `/Users/apple/Documents/分析报告/code/dashboard/tools.ts`（整文件替换为下方代码）

**关键决策：**
- 执行方式 = **回环调用**本服务器代理路由（`http://localhost:8888`），复用 cookie/防盗链/参数逻辑，零重构
- 每个 execute 返回**精简结构化 JSON**（不把 `ex_data` 原样喂模型），错误返回 `{ error }` 不抛异常
- `get_profit_trend` 统一基于 `year_profit`（结构已核对：`{date:'YYYYMMDD', profit: 累计盈亏, asset: 当日资产}`）；**不使用 `month_profit`**（前端从未使用、结构未知），month 模式 = 按 YYYY-MM 汇总差分后的日盈亏
- 各端点与字段名均与 index.html 实际调用核对（Task 3 表格注释）

- [ ] **Step 1: 创建 tools.ts（完整代码）**

```typescript
/**
 * AI Agent 工具定义：7 个数据查询 Tool
 * 执行方式：回环调用本服务器现有代理路由（http://localhost:8888），100% 复用 cookie/防盗链逻辑
 */
import { tool } from 'ai';
import { z } from 'zod';

const LOOPBACK = 'http://localhost:8888';

// ---------- 回环请求 ----------
async function loopback(path: string, init?: RequestInit): Promise<any> {
  const r = await fetch(LOOPBACK + path, init);
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new Error((data && data.error) ? String(data.error) : `HTTP ${r.status}`);
  return data;
}

const thsPost = (path: string): Promise<any> => loopback(path, { method: 'POST' });

// ---------- 共享数据获取 ----------
type Account = { name: string; mid: string; fk: string };

async function listAccounts(): Promise<Account[]> {
  const resp = await thsPost('/api/caishen_fund/pc/account/v1/account_list');
  return ((resp?.ex_data?.common) || []).map((a: any) => ({
    name: a.manualname || '未知', mid: a.manualid || '', fk: a.fund_key || '',
  }));
}

const posQuery = (a: Account): string =>
  `?manual_id=${a.mid}&fund_key=${a.fk}&rzrq_fund_key=&is_merge=1`;

// 6/5/9 → sh, 0/2/3 → sz, 4/8 → bj（与前端 tencentCode 规则一致）
const tencentCode = (code: string): string =>
  (code.startsWith('6') || code.startsWith('5') || code.startsWith('9')) ? 'sh' + code
  : (code.startsWith('4') || code.startsWith('8')) ? 'bj' + code
  : 'sz' + code;

// ---------- Tool 1: 资产概览 ----------
export const get_portfolio_summary = tool({
  description: '获取账户资产概览：按账户列示总资产、持仓市值、可用资金、仓位比例、数据更新时间，并给出全部账户合计',
  parameters: z.object({}),
  execute: async () => {
    try {
      const accounts = await listAccounts();
      const rows: any[] = [];
      let totalAsset = 0, totalValue = 0, totalCash = 0;
      for (const a of accounts) {
        const resp = await thsPost('/api/caishen_fund/pc/asset/v1/stock_position' + posQuery(a));
        const ex = resp?.ex_data || {};
        const ta = parseFloat(ex.total_asset) || 0;
        const tv = parseFloat(ex.total_value) || 0;
        const mr = parseFloat(ex.money_remain) || 0;
        totalAsset += ta; totalValue += tv; totalCash += mr;
        rows.push({
          account: a.name, total_asset: ta, total_value: tv, money_remain: mr,
          position_rate: parseFloat(ex.position_rate) || 0, upload_time: ex.upload_time || '',
        });
      }
      return {
        accounts: rows,
        total: {
          total_asset: totalAsset, total_value: totalValue, money_remain: totalCash,
          position_rate: totalAsset > 0 ? +(totalValue / totalAsset).toFixed(4) : 0,
        },
      };
    } catch (e: any) { return { error: '获取资产概览失败: ' + (e?.message || String(e)) }; }
  },
});

// ---------- Tool 2: 持仓明细 ----------
async function getPositionsFor(a: Account): Promise<any[]> {
  const resp = await thsPost('/api/caishen_fund/pc/asset/v1/stock_position' + posQuery(a));
  return (resp?.ex_data?.position || []).map((p: any) => ({
    code: p.code || '', name: p.name || '',
    count: parseInt(p.count) || 0,
    cost: parseFloat(p.cost) || 0,
    price: parseFloat(p.price) || 0,
    value: parseFloat(p.value) || 0,
    profit: parseFloat(p.hold_profit) || 0,
    profit_rate: parseFloat(p.hold_rate) || 0,
  }));
}

export const get_positions = tool({
  description: '获取持仓明细：每只股票的名称、数量、成本价、现价、市值、盈亏、盈亏率。可按账户名筛选，缺省返回全部账户',
  parameters: z.object({
    account: z.string().optional().describe('账户名称（如 宁静致远），缺省返回全部账户'),
  }),
  execute: async ({ account }) => {
    try {
      let accounts = await listAccounts();
      if (account) accounts = accounts.filter(a => a.name.includes(account));
      const out: any[] = [];
      for (const a of accounts) {
        const positions = (await getPositionsFor(a))
          .filter(p => p.count > 0)
          .sort((x, y) => y.value - x.value);
        out.push({ account: a.name, positions });
      }
      return { accounts: out };
    } catch (e: any) { return { error: '获取持仓明细失败: ' + (e?.message || String(e)) }; }
  },
});

// ---------- Tool 3: 盈亏趋势 ----------
export const get_profit_trend = tool({
  description: '获取盈亏趋势。period=day 返回最近 60 个交易日的每日盈亏与日收益率；period=month 返回按月汇总的盈亏',
  parameters: z.object({
    period: z.enum(['day', 'month']).describe('day=每日盈亏序列, month=按月汇总盈亏'),
  }),
  execute: async ({ period }) => {
    try {
      const accounts = await listAccounts();
      // 合并各账户 year_profit（date: YYYYMMDD, profit: 截至当日累计盈亏, asset: 当日资产）
      const map: Record<string, { profit: number; asset: number }> = {};
      for (const a of accounts) {
        const resp = await thsPost('/api/caishen_fund/pc/asset/v1/asset_trend' + posQuery(a) + '&fundid=&custid=');
        for (const d of (resp?.ex_data?.year_profit || [])) {
          const key = String(d.date || '');
          if (!map[key]) map[key] = { profit: 0, asset: 0 };
          map[key].profit += parseFloat(d.profit) || 0;
          map[key].asset += parseFloat(d.asset) || 0;
        }
      }
      const sorted = Object.entries(map)
        .map(([date, v]) => ({ date, profit: v.profit, asset: v.asset }))
        .sort((a, b) => a.date.localeCompare(b.date));
      // profit 是累计值 → 逐日差分得当日盈亏；日收益率 = 当日盈亏 / 前一日资产
      const daily = sorted.map((d, i) => {
        const p = d.profit - (i > 0 ? sorted[i - 1].profit : 0);
        const prevAsset = i > 0 ? sorted[i - 1].asset : 0;
        return {
          date: `${d.date.slice(0, 4)}-${d.date.slice(4, 6)}-${d.date.slice(6)}`,
          profit: +p.toFixed(2),
          rate: prevAsset > 0 ? +(p / prevAsset).toFixed(6) : 0,
        };
      });

      if (period === 'day') {
        return { period, series: daily.slice(-60) };
      }
      // 按月汇总
      const months: Record<string, number> = {};
      for (const d of daily) {
        const k = d.date.slice(0, 7);
        months[k] = (months[k] || 0) + d.profit;
      }
      const monthSeries = Object.entries(months)
        .map(([month, profit]) => ({ month, profit: +profit.toFixed(2) }));
      return { period, series: monthSeries.slice(-12) };
    } catch (e: any) { return { error: '获取盈亏趋势失败: ' + (e?.message || String(e)) }; }
  },
});

// ---------- Tool 4: 资金流水 ----------
export const get_cash_flow = tool({
  description: '获取资金流水记录：最近 N 天的转入转出/买卖流水，按账户列示（每账户最多 20 条）',
  parameters: z.object({
    days: z.number().int().min(1).max(365).optional().describe('最近 N 天，缺省 30'),
  }),
  execute: async ({ days }) => {
    try {
      const n = days || 30;
      // userid 通过回环 /api-check 获取（cookie 在服务端文件里，tools 不直接读）
      const check = await loopback('/api-check');
      const uid = check?.userid || '';
      const accounts = await listAccounts();
      const end = new Date();
      const start = new Date(Date.now() - n * 86400_000);
      const s = (d: Date) => d.toISOString().slice(0, 10).replace(/-/g, '');
      const out: any[] = [];
      for (const a of accounts) {
        const q = `?manual_id=${a.mid}&fund_key=${a.fk}&rzrq_fund_key=&fundid=&custid=&user_id=${uid}` +
          `&start_date=${s(start)}&end_date=${s(end)}&query_list=&page=1&count=20&sort_type=1&sort_order=1&h5id=`;
        const resp = await thsPost('/api/caishen_fund/pc/account/v2/get_money_history' + q);
        const rows = ((resp?.ex_data?.list) || []).map((r: any) => ({
          date: r.entry_date || '', name: r.name || '', code: r.code || '',
          op: r.op_name || '', count: r.entry_count || '',
          money: parseFloat(r.entry_money) || 0, remark: r.remark || '',
        }));
        out.push({ account: a.name, rows: rows.slice(0, 20) });
      }
      return { days: n, accounts: out };
    } catch (e: any) { return { error: '获取资金流水失败: ' + (e?.message || String(e)) }; }
  },
});

// ---------- Tool 5: K线技术数据 ----------
export const get_kline_data = tool({
  description: '获取个股前复权日K线（最近 120 日）：最新价、涨跌幅、最近 20 日收盘价、5/10/20 日均线、成交量',
  parameters: z.object({
    code: z.string().regex(/^\d{6}$/, '必须是 6 位数字股票代码').describe('6 位股票代码，如 600519'),
  }),
  execute: async ({ code }) => {
    try {
      const tc = tencentCode(code);
      const data = await loopback(`/proxy/kline?code=${tc}&count=120`);
      const k = data?.data?.[tc];
      // qfqday 行结构: [date, open, close, high, low, volume]
      const rows = (k?.qfqday || k?.day || []);
      if (!rows.length) return { error: `无K线数据: ${code}` };
      const closes: number[] = rows.map((r: any) => +r[2]);
      const ma = (p: number): number | null =>
        closes.length >= p ? +(closes.slice(-p).reduce((a, b) => a + b, 0) / p).toFixed(3) : null;
      const last = rows[rows.length - 1], prev = rows[rows.length - 2];
      const close = +last[2], prevClose = +prev[2];
      return {
        code,
        latest: {
          date: last[0], open: +last[1], close, high: +last[3], low: +last[4],
          volume: +last[5],
          change_pct: prevClose ? +(((close - prevClose) / prevClose) * 100).toFixed(2) : 0,
        },
        ma5: ma(5), ma10: ma(10), ma20: ma(20),
        closes_20d: closes.slice(-20),
        volumes_20d: rows.slice(-20).map((r: any) => +r[5]),
      };
    } catch (e: any) { return { error: '获取K线失败: ' + (e?.message || String(e)) }; }
  },
});

// ---------- Tool 6: 市场资金流向排行 ----------
export const get_money_flow_ranking = tool({
  description: '获取全市场个股资金流向排行（主力净流入/流出前 N 名，已过滤 ETF 基金）',
  parameters: z.object({
    order: z.enum(['desc', 'asc']).optional().describe('desc=净流入榜, asc=净流出榜，缺省 desc'),
    num: z.number().int().min(1).max(50).optional().describe('条数，缺省 10'),
  }),
  execute: async ({ order, num }) => {
    try {
      const data = await loopback(`/proxy/moneyflow?order=${order || 'desc'}&num=${num || 10}`);
      const rows = (Array.isArray(data) ? data : [])
        .filter((x: any) => !/^(sh[15]|sz15)/.test(x.symbol || ''))
        .slice(0, num || 10)
        .map((x: any) => ({
          symbol: x.symbol || '', name: x.name || '',
          price: parseFloat(x.trade) || 0,
          change_pct: parseFloat(x.changeratio) || 0,
          net_inflow: parseFloat(x.r0_net) || 0,
        }));
      return { order: order || 'desc', rows };
    } catch (e: any) { return { error: '获取资金流向排行失败: ' + (e?.message || String(e)) }; }
  },
});

// ---------- Tool 7: 自选行情 ----------
export const get_watchlist = tool({
  description: '获取自选股行情：每只自选股的价格、涨跌幅，以及整体上涨/下跌家数、平均涨跌幅',
  parameters: z.object({}),
  execute: async () => {
    try {
      const sl = await thsPost('/api/caishen_fund/pc/optional/v1/sort_list?sort_rule=&sort_order=');
      const items = ((sl?.ex_data?.list) || []).map((i: any) => ({
        code: i.code || '', name: i.name || '', market: i.market || '',
        price: parseFloat(i.price) || 0, rate: parseFloat(i.rate) || 0,
      }));
      let stats: any = {};
      // rise_fall 的 stock_code 参数是 market:code 形式（与前端一致）
      const codes = items.filter(i => i.market && i.code).map(i => `${i.market}:${i.code}`).join(',');
      if (codes) {
        const rf = await thsPost(`/api/caishen_fund/pc/optional/v1/rise_fall?stock_code=${codes}&fund_code=`);
        const d = rf?.ex_data || {};
        stats = {
          rise: parseInt(d.stock_rise) || 0,
          fall: parseInt(d.stock_fall) || 0,
          avg_rate: parseFloat(d.avg_rate) || 0,
        };
      }
      return { stats, items };
    } catch (e: any) { return { error: '获取自选行情失败: ' + (e?.message || String(e)) }; }
  },
});

// ---------- 汇总导出 ----------
export const ALL_TOOLS = {
  get_portfolio_summary,
  get_positions,
  get_profit_trend,
  get_cash_flow,
  get_kline_data,
  get_money_flow_ranking,
  get_watchlist,
};

export const TOOL_LABELS: Record<string, string> = {
  get_portfolio_summary: '资产概览',
  get_positions: '持仓明细',
  get_profit_trend: '盈亏趋势',
  get_cash_flow: '资金流水',
  get_kline_data: 'K线数据',
  get_money_flow_ranking: '资金流向排行',
  get_watchlist: '自选行情',
};
```

> **注意：** 上方 Tool 7 的 `items` 映射已包含 `market` 字段（`rise_fall` 的 `stock_code` 参数需要 `market:code` 形式，与前端一致）。

- [ ] **Step 2: 类型检查**

```bash
cd /Users/apple/Documents/分析报告/code/dashboard
npx tsc --noEmit
```
期望：无输出（0 错误）。注：此时 server.ts 尚未 import tools.ts，tsc 仍会因 include 而检查它。

- [ ] **Step 3: 单测验证 Tool 数据获取（在 server 运行状态下）**

```bash
# 终端 1
npx tsx server.ts
# 终端 2：逐个验证数据源
curl -s -X POST 'http://localhost:8888/api/caishen_fund/pc/account/v1/account_list' | head -c 300; echo
curl -s -X POST 'http://localhost:8888/api/caishen_fund/pc/optional/v1/sort_list?sort_rule=&sort_order=' | head -c 300; echo
curl -s 'http://localhost:8888/proxy/kline?code=sh600519&count=5' | head -c 300; echo
curl -s 'http://localhost:8888/proxy/moneyflow?order=desc&num=3' | head -c 300; echo
```
期望：4 个请求都返回 JSON（无 error 字段），说明 Tool 依赖的数据源全部可用。

---

## Task 4: server.ts 接入 Agent（路由 + 会话 + SSE）

**执行时追加的 2 处小修正（源于 Task 3 代码质量审查，控制器批准）：**
1. tools.ts 的 `loopback` 增加超时与中断传导：`fetch(..., { signal: AbortSignal.any([init?.signal, AbortSignal.timeout(15000)]) })`（Node 20.3+ 支持 AbortSignal.any）；7 个 execute 签名改为 `(args, options)` 并把 `options.abortSignal`（AI SDK v4 随请求自动传入）转发给 loopback
2. tools.ts 的 `get_kline_data` 单根数据边界修复：`const prevClose = prev ? +prev[2] : 0;`（次新股仅 1 根K线时 `rows[-2]` 为 undefined 会抛 TypeError 文本给 LLM）
3. （无需改码）同花顺上游错误以 HTTP 状态码表达（实测 cookie 失效返回 403），不实现业务错误信封检测（YAGNI）

**Files:**
- Modify: `/Users/apple/Documents/分析报告/code/dashboard/server.ts`（4 处插入，每处代码见步骤）

**插入点汇总：**
1. 顶部 import 区（Step 1）
2. `PORT` 常量之后：AI 配置 + SYSTEM_PROMPT + 会话存储（Step 2）
3. `serveDashboard()` 之后、`const server = ...` 之前：handler 函数（Step 3）
4. `http.createServer` 回调内、`// API proxy` 之前：3 条路由（Step 4）
5. `server.listen(...)` 回调内：`loadSessions()` + AI Key 警告（Step 5）

- [ ] **Step 1: 顶部追加 import**

在 `import type { IncomingMessage, ServerResponse } from 'node:http';` 之后追加：

```typescript
import { streamText, type CoreTool } from 'ai';
import { createDeepSeek } from '@ai-sdk/deepseek';
import { ALL_TOOLS, TOOL_LABELS } from './tools';
// 注意：@ai-sdk/deepseek@0.2.x 的模型级设置不接受 apiKey，必须经 createDeepSeek provider 级注入（默认 deepseek 实例只读 DEEPSEEK_API_KEY 环境变量，无法用 ~/.tzzb_ai_key 文件机制）
```

- [ ] **Step 2: 追加 AI 配置 + SYSTEM_PROMPT + 会话存储**

在 `const API_BASE = 'tzzb.10jqka.com.cn';` 之后追加：

```typescript
// ===== AI Agent 配置 =====
const AI_KEY_FILE = path.join(os.homedir(), '.tzzb_ai_key');
const AI_API_KEY = process.env.TZZB_AI_KEY?.trim() ||
  (fs.existsSync(AI_KEY_FILE) ? fs.readFileSync(AI_KEY_FILE, 'utf-8').trim() : '');
const AI_MODEL = process.env.TZZB_AI_MODEL || 'deepseek-chat';
const modelProvider = createDeepSeek({ apiKey: AI_API_KEY });  // 模块级构造一次，勿在每次请求内新建

const SYSTEM_PROMPT = `你是一个专业的投资看板 AI 助手，名为"灵犀"。

## 角色
- 名字：灵犀
- 风格：专业但不生硬，数据驱动，简洁清晰
- 语言：中文，金额用中文习惯（万/亿）
- 禁忌：不提供具体买卖建议，不预测未来走势，不做投资推荐

## 可用工具
你可以调用以下工具来获取实时数据：
- get_portfolio_summary: 账户资产概览（总资产、仓位、盈亏）
- get_positions: 持仓明细（每只股票成本、现价、盈亏）
- get_profit_trend: 盈亏趋势（period=day 每日盈亏 / period=month 月度盈亏）
- get_cash_flow: 资金流水记录
- get_kline_data: K线技术数据（价格、均线、成交量）
- get_money_flow_ranking: 市场资金流向排行
- get_watchlist: 自选股行情

## 回答规则
1. 必须用工具获取数据后再回答，绝不编造数据
2. 金额使用 ¥万/¥亿 格式，精确到小数点后两位
3. A股惯例：涨=红色，跌=绿色
4. 如果数据不足以回答，诚实说明
5. 回答控制在 200 字以内，除非用户要求详细分析`;

// ===== 会话持久化 =====
const SESSION_FILE = path.join(os.homedir(), '.tzzb_ai_sessions.json');
const MAX_SESSIONS = 10;
const MAX_MESSAGES = 60;

type Session = { updated: number; messages: any[] };
let sessions = new Map<string, Session>();

function loadSessions(): void {
  try {
    const raw = JSON.parse(fs.readFileSync(SESSION_FILE, 'utf-8'));
    if (raw && typeof raw === 'object' && raw.sessions) {
      sessions = new Map(Object.entries(raw.sessions) as [string, Session][]);
    }
  } catch { sessions = new Map(); }  // 文件不存在或损坏 → 空
}

function saveSessions(): void {
  // 裁剪：最多 10 个会话 × 每会话 60 条消息，按 updated 保留最新
  const arr = [...sessions.entries()].sort((a, b) => b[1].updated - a[1].updated);
  const kept = new Map(arr.slice(0, MAX_SESSIONS));
  for (const s of kept.values()) s.messages = s.messages.slice(-MAX_MESSAGES);
  sessions = kept;
  // 原子写入：tmp + rename，杜绝半截文件
  const tmp = SESSION_FILE + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify({ sessions: Object.fromEntries(kept) }, null, 2));
  fs.renameSync(tmp, SESSION_FILE);
}

function getSession(id: string): Session {
  let s = sessions.get(id);
  if (!s) { s = { updated: Date.now(), messages: [] }; sessions.set(id, s); }
  return s;
}

// 从 SDK 消息中提取纯文本（助手消息的 text 类 part；tool 类 part 跳过）
function extractText(m: any): string {
  if (typeof m.content === 'string') return m.content;
  if (Array.isArray(m.content)) {
    return m.content.filter((p: any) => p.type === 'text').map((p: any) => p.text).join('');
  }
  return '';
}
```

- [ ] **Step 3: 追加 handler 函数**

在 `serveDashboard()` 函数之后、`const server = http.createServer(...)` 之前追加：

```typescript
// ===== AI Agent 请求处理 =====
function readJsonBody(req: IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try { resolve(JSON.parse(body || '{}')); }
      catch { reject(new Error('Invalid JSON')); }
    });
  });
}

function sendEvent(res: ServerResponse, event: string, data: object): void {
  if (res.writableEnded) return;
  res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

async function handleAgentRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
  // 鉴权：与现有 /api/ 行为一致
  const cookie = readCookie();
  if (!cookie) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies' }));
    return;
  }

  let body: { sessionId?: string; query?: string };
  try { body = await readJsonBody(req); }
  catch {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Invalid JSON body' }));
    return;
  }
  const sessionId = body.sessionId || 'default';
  const query = (body.query || '').trim();
  if (!query) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'query 不能为空' }));
    return;
  }
  if (!AI_API_KEY) {
    res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: '未配置 AI API Key（TZZB_AI_KEY 环境变量或 ~/.tzzb_ai_key 文件）' }));
    return;
  }

  // SSE 响应头
  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
  });

  // 心跳 + 断连清理
  const controller = new AbortController();
  const heartbeat = setInterval(() => { if (!res.writableEnded) res.write(': ping\n\n'); }, 15000);
  res.on('close', () => { clearInterval(heartbeat); controller.abort(); });

  const session = getSession(sessionId);
  session.messages.push({ role: 'user', content: query });

  try {
    const result = streamText({
      model: modelProvider(AI_MODEL),
      system: SYSTEM_PROMPT,
      messages: session.messages,
      tools: ALL_TOOLS as unknown as Record<string, CoreTool>,
      maxSteps: 5,
      temperature: 0.3,
      abortSignal: controller.signal,
      onStepFinish: (step) => {
        // 每轮 tool call 结束推送状态事件
        const tc = step.toolCalls?.[0];
        if (tc) sendEvent(res, 'status', { content: `正在查询${TOOL_LABELS[tc.toolName] || tc.toolName}…` });
      },
    });

    // 逐字流式推送最终回复文本
    for await (const delta of result.textStream) {
      sendEvent(res, 'text', { delta });
    }

    // 持久化：以 SDK 回吐的完整消息为准（含 tool-call/tool-result，格式天然兼容下次请求）
    // 注意：ai@4.3.19 的 result.response 是 Promise，必须 await
    session.messages = [...(await result.response).messages];
    session.updated = Date.now();
    saveSessions();
    sendEvent(res, 'done', { sessionId });
  } catch (e: any) {
    sendEvent(res, 'error', { message: (e && e.message) ? String(e.message) : 'AI 服务异常' });
  } finally {
    clearInterval(heartbeat);
    res.end();
  }
}

async function handleAgentHistory(req: IncomingMessage, res: ServerResponse, url: URL): Promise<void> {
  const sessionId = url.searchParams.get('sessionId') || 'default';
  const s = sessions.get(sessionId);
  const messages = (s?.messages || [])
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => ({ role: m.role, text: extractText(m) }));
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ messages }));
}

async function handleAgentClear(req: IncomingMessage, res: ServerResponse): Promise<void> {
  let body: any;
  try { body = await readJsonBody(req); }
  catch { body = {}; }
  sessions.delete(body.sessionId || 'default');
  saveSessions();
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true }));
}
```

- [ ] **Step 4: 路由挂载（必须在 `/api/` 通用代理之前）**

在 `http.createServer` 回调内，`const method = req.method;` 之后、`// API proxy` 注释之前插入：

```typescript
  // ===== AI Agent 路由（必须在 /api/ 通用代理之前，否则被拦截） =====
  if (pathname === '/api/agent' && method === 'POST') {
    return handleAgentRequest(req, res);
  }
  if (pathname === '/api/agent/history' && method === 'GET') {
    return handleAgentHistory(req, res, url);
  }
  if (pathname === '/api/agent/clear' && method === 'POST') {
    return handleAgentClear(req, res);
  }
```

- [ ] **Step 5: 启动时加载会话 + AI Key 警告**

在 `server.listen(PORT, () => {` 回调内，`const url = ...;` 之前加一行：

```typescript
  loadSessions();
```

在现有 cookie 警告 `}` 之后追加：

```typescript
  if (!AI_API_KEY) {
    console.log('  ⚠️  未配置 AI API Key');
    console.log('     export TZZB_AI_KEY="your-key" 后重启');
    console.log('     或写入 ~/.tzzb_ai_key 文件');
    console.log('     AI 对话功能将不可用，但不影响其他功能');
  }
```

- [ ] **Step 6: 类型检查**

```bash
cd /Users/apple/Documents/分析报告/code/dashboard
npx tsc --noEmit
```
期望：无输出（0 错误）。

- [ ] **Step 7: 验证 Agent 接口（curl）**

```bash
export TZZB_AI_KEY="sk-xxx"   # 替换为真实 key
npx tsx server.ts
```

另开终端：

```bash
# 1. 正常对话（-N 禁用缓冲，观察流式事件）
curl -N -X POST http://localhost:8888/api/agent \
  -H "Content-Type: application/json" \
  -d '{"sessionId":"test-001","query":"你好，介绍一下你能做什么"}'
# 期望: 依次输出 event: status / event: text(多条) / event: done，无 error

# 2. 历史记录
curl -s 'http://localhost:8888/api/agent/history?sessionId=test-001'
# 期望: {"messages":[{"role":"user","text":"..."},{"role":"assistant","text":"..."}]}

# 3. 多轮（同一 sessionId 追问）
curl -N -X POST http://localhost:8888/api/agent \
  -H "Content-Type: application/json" \
  -d '{"sessionId":"test-001","query":"我持有最多的3只股票是什么？"}'
# 期望: 有 status 事件（正在查询持仓明细…），text 中包含具体股票名

# 4. 清空会话
curl -s -X POST http://localhost:8888/api/agent/clear \
  -H "Content-Type: application/json" -d '{"sessionId":"test-001"}'
# 期望: {"ok":true}
curl -s 'http://localhost:8888/api/agent/history?sessionId=test-001'
# 期望: {"messages":[]}

# 5. 会话文件检查
cat ~/.tzzb_ai_sessions.json   # 期望: 合法 JSON，无 .tmp 残留文件

# 6. 重启后历史仍在：Ctrl+C 重启 server，再查 history（换一个未清空的 sessionId）
# 7. 无 Cookie 401：mv ~/.tzzb_cookies ~/.tzzb_cookies.bak 后请求 /api/agent
#    期望: HTTP 401 {"error":"No cookie found..."}，验证后恢复 cookie 文件
```

---

## Task 5: index.html 新增 AI 面板（现有代码零改动）

**Files:**
- Modify: `/Users/apple/Documents/分析报告/code/dashboard/index.html`（三处追加，现有代码不动）

**插入锚点（当前文件行号）：**
- HTML：`</main>`（440 行）与 `<script>`（442 行）之间
- CSS：`</style>`（281 行）之前
- JS：`</script>`（1454 行）之前（`applySavedState` / `DOMContentLoaded` 之后）
- 顶栏按钮：`.top-actions` 内 `LIVE` span 与 `⟳` span 之间（296-298 行）

- [ ] **Step 1: 顶栏 🤖 按钮**

在 `index.html` 第 296 行 `<span><span class="live-dot"></span>LIVE</span>` 与第 298 行 `<span style="color:var(--text-3);cursor:pointer;" id="refresh-btn" onclick="refreshAll()">⟳</span>` 之间插入：

```html
<button class="ai-toggle-btn" id="ai-toggle" title="AI 助手"
        onclick="toggleAIPanel()">🤖</button>
```

- [ ] **Step 2: AI 面板 HTML**

在 `</main>` 与 `<script>` 之间插入：

```html
<!-- ===== AI PANEL ===== -->
<aside id="ai-panel" class="ai-panel hidden">
  <div class="ai-panel-header">
    <span class="ai-panel-title">▮ AI ASSISTANT · 灵犀</span>
    <button class="ai-panel-clear" onclick="clearAIChat()" title="清空对话">🗑</button>
    <button class="ai-panel-close" onclick="toggleAIPanel()">✕</button>
  </div>

  <div class="ai-panel-quick">
    <button class="ai-quick-btn" onclick="askAgent('生成本日投资简报')">📋 日报</button>
    <button class="ai-quick-btn" onclick="askAgent('分析我的持仓风险和集中度')">🔍 诊断</button>
  </div>

  <div class="ai-panel-messages" id="ai-messages">
    <div class="ai-msg ai-msg-system">
      您好！我是灵犀，您的投资助手。<br>可以问我持仓、盈亏、行情等问题。
    </div>
  </div>

  <div class="ai-panel-input">
    <textarea id="ai-input" rows="1" placeholder="输入问题，Enter 发送..."
              onkeydown="handleAIKeydown(event)"></textarea>
    <button id="ai-send" onclick="sendAIMessage()">↑</button>
  </div>
</aside>
```

- [ ] **Step 3: AI 面板 CSS**

在 `</style>` 之前插入（CSS 变量 `--bg-root/--border/--text-*/--orange` 均已在现有 `:root` 定义）：

```css
  /* ===== AI PANEL ===== */
  .ai-toggle-btn {
    background: #1a1a1c; border: 1px solid #26262a; border-radius: 4px;
    color: var(--text-3); cursor: pointer; padding: 4px 5px; line-height: 1;
    display: inline-flex; align-items: center; justify-content: center;
    font-family: inherit; font-size: 13px; margin-left: 8px; transition: all 0.15s;
  }
  .ai-toggle-btn:hover { color: var(--text-1); border-color: #3a3a3f; background: #222225; }

  .ai-panel {
    position: fixed; top: 0; right: 0; width: 380px; height: 100vh;
    background: var(--bg-root); border-left: 1px solid var(--border);
    display: flex; flex-direction: column; z-index: 200;
    transition: transform 0.3s ease; box-shadow: -8px 0 24px rgba(0,0,0,0.5);
  }
  .ai-panel.hidden { transform: translateX(100%); }

  .ai-panel-header {
    display: flex; align-items: center; gap: 8px;
    padding: 12px 14px; border-bottom: 1px solid var(--border);
    font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-2);
  }
  .ai-panel-title { letter-spacing: 0.5px; }
  .ai-panel-close, .ai-panel-clear {
    background: none; border: none; color: var(--text-3);
    cursor: pointer; font-size: 13px; padding: 2px 4px;
  }
  .ai-panel-clear { margin-left: auto; }
  .ai-panel-close { margin-left: 4px; }
  .ai-panel-clear:hover { color: var(--text-1); }
  .ai-panel-close:hover { color: #f87171; }

  .ai-panel-quick { display: flex; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--border); }
  .ai-quick-btn {
    background: #1a1a1c; border: 1px solid #26262a; border-radius: 6px;
    color: var(--text-2); cursor: pointer; padding: 4px 10px; font-size: 11px;
    font-family: inherit; transition: all 0.15s;
  }
  .ai-quick-btn:hover { color: var(--text-1); border-color: #3a3a3f; }

  .ai-panel-messages {
    flex: 1; overflow-y: auto; padding: 14px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .ai-msg { max-width: 92%; font-size: 12px; line-height: 1.6; word-break: break-word; }
  .ai-msg-ai { align-self: flex-start; border-left: 2px solid #448aff; padding-left: 10px; color: var(--text-1); }
  .ai-msg-user { align-self: flex-end; border-left: 2px solid var(--orange); padding-left: 10px; color: var(--text-2); }
  .ai-msg-system { align-self: center; text-align: center; color: var(--text-3); }

  .ai-panel-input {
    display: flex; gap: 8px; padding: 12px 14px; border-top: 1px solid var(--border);
  }
  .ai-panel-input textarea {
    flex: 1; background: #1a1a1c; border: 1px solid #26262a; border-radius: 6px;
    color: var(--text-1); font-family: inherit; font-size: 12px;
    padding: 8px 10px; resize: none; outline: none; line-height: 1.5;
  }
  .ai-panel-input textarea:focus { border-color: #3a3a3f; }
  #ai-send {
    background: var(--orange); border: none; border-radius: 6px; color: #fff;
    width: 32px; cursor: pointer; font-size: 15px;
  }
  #ai-send:hover { opacity: 0.85; }

  /* 隐私 / 摸鱼：纯 CSS 跟随 body class，无需 JS（现有 togglePrivacy/toggleStealth 不改动） */
  body.privacy .ai-msg { filter: blur(5px); user-select: none; }
  body.stealth .ai-panel { filter: grayscale(1); }

  /* ≤680px 底部抽屉 */
  @media (max-width: 680px) {
    .ai-panel { top: auto; bottom: 0; height: 60vh; width: 100%; border-left: none; border-top: 1px solid var(--border); }
    .ai-panel.hidden { transform: translateY(100%); }
  }
```

- [ ] **Step 4: AI 面板 JavaScript**

在 `</script>` 之前（`DOMContentLoaded` 监听器之后）插入：

```javascript
// ===== AI PANEL =====

let aiPanelOpen = false;
let aiStreaming = false;

// 会话 ID：首次访问生成，存 localStorage，刷新后继续同一会话
const aiSessionId = localStorage.getItem('ai_session_id') ||
  (() => { const id = crypto.randomUUID(); localStorage.setItem('ai_session_id', id); return id; })();

// 切换面板（首次打开时拉取历史）
async function toggleAIPanel() {
  aiPanelOpen = !aiPanelOpen;
  document.getElementById('ai-panel').classList.toggle('hidden', !aiPanelOpen);
  localStorage.setItem('ai_panel_open', aiPanelOpen);
  if (aiPanelOpen) {
    document.getElementById('ai-input').focus();
    if (!document.getElementById('ai-messages').dataset.loaded) {
      document.getElementById('ai-messages').dataset.loaded = '1';
      await loadAIHistory();
    }
  }
}

// 页面加载时恢复面板状态
if (localStorage.getItem('ai_panel_open') === 'true') {
  setTimeout(() => { toggleAIPanel(); }, 500);
}

// 从服务端恢复历史消息
async function loadAIHistory() {
  try {
    const r = await fetch(`/api/agent/history?sessionId=${aiSessionId}`);
    if (!r.ok) return;
    const data = await r.json();
    if (!data.messages?.length) return;
    const box = document.getElementById('ai-messages');
    box.innerHTML = '';
    data.messages.forEach(m => addMessage(m.role === 'assistant' ? 'ai' : 'user', m.text));
  } catch (e) { /* 静默：无历史或服务不可用 */ }
}

function addMessage(role, text) {
  const box = document.getElementById('ai-messages');
  const div = document.createElement('div');
  div.className = 'ai-msg ' + (role === 'user' ? 'ai-msg-user' : 'ai-msg-ai');
  div.innerHTML = '<div class="ai-msg-content"></div>';
  div.querySelector('.ai-msg-content').textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

// 清空对话（服务端 + 本地）
async function clearAIChat() {
  if (aiStreaming || !confirm('清空当前对话？')) return;
  await fetch('/api/agent/clear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessionId: aiSessionId })
  }).catch(() => {});
  const box = document.getElementById('ai-messages');
  box.innerHTML = '<div class="ai-msg ai-msg-system">您好！我是灵犀，您的投资助手。<br>可以问我持仓、盈亏、行情等问题。</div>';
}

function handleAIKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendAIMessage(); }  // !e.isComposing: 中文输入法选词回车不误发送
}

// 发送消息
async function sendAIMessage() {
  const input = document.getElementById('ai-input');
  const query = input.value.trim();
  if (!query || aiStreaming) return;

  input.value = '';
  aiStreaming = true;

  // 添加用户消息 + AI 占位消息
  addMessage('user', query);
  const aiMsg = addMessage('ai', '');
  const contentEl = aiMsg.querySelector('.ai-msg-content');
  let firstText = true;

  try {
    const response = await fetch('/api/agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: aiSessionId, query })
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      input.value = query;  // 失败时恢复用户输入
      contentEl.textContent = '❌ ' + (err.error || '请求失败（请检查 Cookie / AI Key）');
      aiStreaming = false;
      return;
    }

    // SSE 流式读取（事件类型: status / text / done / error）
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', eventName = '', eventData = '';

    const handleEvent = () => {
      if (!eventName || !eventData) return;
      try {
        const data = JSON.parse(eventData);
        if (eventName === 'status') {
          contentEl.textContent = '⏳ ' + data.content;
        } else if (eventName === 'text') {
          if (firstText) { contentEl.textContent = ''; firstText = false; }  // 清除 status 占位
          contentEl.textContent += data.delta;
        } else if (eventName === 'error') {
          contentEl.textContent = '❌ ' + data.message;
        }
        // done 事件无需处理
      } catch (e) { /* 忽略坏行 */ }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE 帧解析：event:/data: 行、心跳注释行（: ping）、事件间空行
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith(':')) continue;                 // 心跳注释行，跳过
        if (line.startsWith('event: ')) eventName = line.slice(7).trim();
        else if (line.startsWith('data: ')) eventData += line.slice(6);
        else if (line === '') { handleEvent(); eventName = ''; eventData = ''; }
      }
    }
  } catch (e) {
    input.value = query;  // 失败时恢复用户输入
    contentEl.textContent = '❌ 网络错误: ' + e.message;
  }

  aiStreaming = false;
  const box = document.getElementById('ai-messages');
  box.scrollTop = box.scrollHeight;
}

// 快捷按钮
function askAgent(query) {
  document.getElementById('ai-input').value = query;
  sendAIMessage();
}
```

- [ ] **Step 5: 浏览器验证**

1. `npx tsx server.ts`（已配置 `TZZB_AI_KEY`）
2. 打开 `http://localhost:8888`，F12 Console 无报错
3. 点击顶栏 🤖 → 面板从右侧滑入，输入框聚焦
4. 点击「📋 日报」→ 消息区先显示 `⏳ 正在查询…`，随后流式逐字输出日报
5. 输入"我这个月亏了多少？" → Agent 调 `get_profit_trend` 返回准确数字
6. 追问"那第二只呢？"（先问过持仓排序）→ 多轮上下文正确
7. 刷新页面 → 面板状态恢复 + 历史消息恢复；重启 server → 历史仍在
8. 点击 🗑 → 确认后清空，`cat ~/.tzzb_ai_sessions.json` 中该会话消失
9. 开启 👁 → AI 消息模糊；开启 🖥 → 面板灰阶（均为纯 CSS 联动，现有卡片行为不变）
10. 关闭面板 → 7 张卡片交互不受影响

---

## Task 6: 端到端验收清单

- [ ] `npx tsc --noEmit` 零错误
- [ ] `npx tsx server.ts` 正常启动，7 张卡片功能不变，自动打开浏览器行为保留
- [ ] 未配置 API Key 时启动提示"⚠️ 未配置 AI API Key"，其他功能不受影响
- [ ] `curl -s http://localhost:8888/api-check` 返回 `{"has_cookie":true,...}`
- [ ] `curl -N -X POST /api/agent -d '{"sessionId":"t1","query":"你好"}'` 输出 status/text/done 事件序列
- [ ] `GET /api/agent/history?sessionId=t1` 返回对话历史；`POST /api/agent/clear` 后为空
- [ ] 重启 server 后历史仍在（`~/.tzzb_ai_sessions.json` 原子写入，无 `.tmp` 残留）
- [ ] 无 Cookie 时 `/api/agent` 返回 401 + 明确错误文案
- [ ] 前端：逐字流式、状态提示、多轮追问、历史恢复、清空按钮、隐私/摸鱼 CSS 联动
- [ ] 现有 7 张卡片交互零回归
- [ ] `server.js.bak` 备份存在，确认无回归后可删除

---

## 已知取舍（实现时无需再决策）

| 取舍 | 理由 |
|------|------|
| tool() 用 `parameters` 而非 `inputSchema` | ai@4.3.19 的 API 命名（`inputSchema` 是 v5 命名），Task 3 实测修正并已同步回本计划 |
| 回环调用而非抽取共享 helper | 零重构，100% 复用代理逻辑；若实测不稳定可改为抽 `fetchTHS` |
| month 模式用 year_profit 聚合 | `month_profit` 字段前端从未使用、结构未知，不冒险 |
| 会话文件放 home 目录 | 与 `.tzzb_cookies` 习惯一致，不污染 git |
| 隐私模式模糊整条消息 | 消息是文字+数字混合，无法只糊数字；5px 与现有规则一致 |
| 单会话自动续接（不做多会话 UI） | 范围外声明，清空按钮已覆盖重置需求 |
