#!/usr/bin/env node
/**
 * 投资账本看板 - 纯 JS 服务器
 * 零依赖，仅需 Node.js 内置模块
 * 用法: node server.js
 *      然后访问 http://localhost:8888
 * （TS 迁移版：改用 npx tsx server.ts 启动，新增 AI Agent 依赖，见 package.json）
 */

import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import type { IncomingMessage, ServerResponse } from 'node:http';
import iconv from 'iconv-lite';
import { streamText, type CoreTool } from 'ai';
import { createDeepSeek } from '@ai-sdk/deepseek';
import { ALL_TOOLS, TOOL_LABELS } from './tools';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = 8888;
const COOKIE_FILE = path.join(os.homedir(), '.tzzb_cookies');
const STATIC_DIR = __dirname;
const API_BASE = 'tzzb.10jqka.com.cn';

// ===== AI Agent 配置 =====
// 优先级：环境变量 > ~/.tzzb_ai_config.json（统一配置文件）> ~/.tzzb_ai_key（仅 Key 旧方式）> 默认值
const AI_KEY_FILE = path.join(os.homedir(), '.tzzb_ai_key');
const AI_CONFIG_FILE = path.join(os.homedir(), '.tzzb_ai_config.json');

function readAIConfig(): { apiKey?: string; model?: string; baseURL?: string } {
  try {
    const raw = JSON.parse(fs.readFileSync(AI_CONFIG_FILE, 'utf-8'));
    return raw && typeof raw === 'object' ? raw : {};
  } catch { return {}; }  // 文件不存在或损坏 → 空
}

const aiConfig = readAIConfig();
const AI_API_KEY = process.env.TZZB_AI_KEY?.trim() ||
  (aiConfig.apiKey || '').trim() ||
  (fs.existsSync(AI_KEY_FILE) ? fs.readFileSync(AI_KEY_FILE, 'utf-8').trim() : '');
const AI_MODEL = process.env.TZZB_AI_MODEL?.trim() || aiConfig.model || 'deepseek-chat';
const AI_BASE_URL = process.env.TZZB_AI_BASE_URL?.trim() || aiConfig.baseURL || undefined;  // 可选：自定义 OpenAI 兼容端点（未设置走 DeepSeek 官方）

// 网关兼容层：部分 OpenAI 兼容网关（如 New API）的 JSON Schema 校验要求 tool 的 parameters 必须含 required 数组；
// 而 zod 转 JSON Schema 时对无必填字段的对象会省略 required，导致上游 400。
// 发送前给缺 required 的对象型 schema 补上 required: []（合法的 JSON Schema，不影响其他端点）。
const gatewayFetch: typeof fetch = async (url, init) => {
  if (init?.body && typeof init.body === 'string') {
    try {
      const body = JSON.parse(init.body);
      if (Array.isArray(body.tools)) {
        let touched = false;
        for (const t of body.tools) {
          const p = t?.function?.parameters;
          if (p && typeof p === 'object' && p.type === 'object' && !Array.isArray(p.required)) {
            p.required = [];
            touched = true;
          }
        }
        if (touched) init = { ...init, body: JSON.stringify(body) };
      }
    } catch { /* 非 JSON 请求体，跳过 */ }
  }
  return fetch(url, init);
};

const modelProvider = createDeepSeek({ apiKey: AI_API_KEY, baseURL: AI_BASE_URL, fetch: gatewayFetch });  // 模块级构造一次，勿在每次请求内新建

const SYSTEM_PROMPT = `你是一个专业的投资看板 AI 助手，名为"点金"。

## 角色
- 名字：点金
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

type Session = { updated: number; messages: any[]; title?: string };
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

// 会话标题兜底：取首条 user 消息前 20 字
function deriveTitle(messages: any[]): string {
  const first = messages.find(m => m.role === 'user');
  if (!first) return '新对话';
  const t = typeof first.content === 'string' ? first.content : extractText(first);
  return t.trim().slice(0, 20) || '新对话';
}

// 从 SDK 消息中提取纯文本（助手消息的 text 类 part；tool 类 part 跳过）
function extractText(m: any): string {
  if (typeof m.content === 'string') return m.content;
  if (Array.isArray(m.content)) {
    return m.content.filter((p: any) => p.type === 'text').map((p: any) => p.text).join('');
  }
  return '';
}

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

// 新浪实时行情代理: /proxy/stock-price?codes=sh000300,sz399006
// 返回 [{code, name, current, prevClose, change, changePct, state}]
function proxyStockPrice(codes: string, res: ServerResponse): void {
  const list = codes.split(',').map(c => c.trim()).filter(Boolean).join(',');
  const target = `http://hq.sinajs.cn/list=${list}`;
  console.log(`  ↳ GET ${target}`);
  const req = http.get(target, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Referer': 'https://finance.sina.com.cn',
    }
  }, (proxyRes) => {
    const chunks: Buffer[] = [];
    proxyRes.on('data', chunk => chunks.push(chunk as Buffer));
    proxyRes.on('end', () => {
      const raw = Buffer.concat(chunks);
      const body = iconv.decode(raw, 'gbk');
      const result = parseSinaStockPrice(body, codes.split(',').map(c => c.trim()).filter(Boolean));
      res.writeHead(proxyRes.statusCode ?? 502, {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': '*',
      });
      res.end(JSON.stringify(result));
    });
  });
  req.on('error', (e) => {
    res.writeHead(502);
    res.end(JSON.stringify({error: 'Proxy error: ' + e.message}));
  });
}

function parseSinaStockPrice(body: string, codes: string[]) {
  const result: { code: string; name: string; current: number; prevClose: number; change: number; changePct: number; state: string; }[] = [];
  for (const code of codes) {
    const re = new RegExp(`var hq_str_${code}="([^"]*)";`);
    const m = body.match(re);
    if (!m || !m[1]) continue;
    const parts = m[1].split(',');
    if (parts.length < 3) continue;
    let name: string, current: number, prevClose: number, change: number, changePct: number;
    if (code.toLowerCase().startsWith('hk')) {
      // 港股格式：英文名,中文名,当前价,昨收,今开,最高,最低,涨跌额,涨跌幅,...
      name = parts[1] || '';
      current = parseFloat(parts[2]) || 0;
      prevClose = parseFloat(parts[3]) || 0;
      change = parseFloat(parts[7]) || 0;
      changePct = parseFloat(parts[8]) || 0;
    } else {
      name = parts[0];
      current = parseFloat(parts[3]) || 0;
      prevClose = parseFloat(parts[2]) || 0;
      change = current - prevClose;
      changePct = prevClose ? (change / prevClose) * 100 : 0;
    }
    result.push({ code, name, current, prevClose, change, changePct: parseFloat(changePct.toFixed(2)), state: 'close' });
  }
  return result;
}

function proxyGlobalIndexes(res: ServerResponse): void {
  const target = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/rank/indexRankDetail2';
  console.log(`  ↳ GET ${target}`);
  const req = https.get(target, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Referer': 'https://stockapp.finance.qq.com/mstats',
      'Host': 'proxy.finance.qq.com',
    }
  }, (proxyRes) => {
    let body = '';
    proxyRes.setEncoding('utf8');
    proxyRes.on('data', chunk => body += chunk);
    proxyRes.on('end', () => {
      // 腾讯接口在字段值中夹杂换行符/控制字符，需清理后再返回 JSON
      const cleaned = body.replace(/[\x00-\x1f]/g, '');
      res.writeHead(proxyRes.statusCode ?? 502, {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': '*',
      });
      res.end(cleaned);
    });
  });
  req.on('error', (e) => {
    res.writeHead(502);
    res.end(JSON.stringify({ error: 'Proxy error: ' + e.message }));
  });
}

// 新浪财经直播新闻: /proxy/news?num=20
// 与 AI-Tools MarketNewsTool 同源接口（zhibo.sina.com.cn JSONP），服务端剥 JSONP 包装 + 去 HTML 标签
const stripRichText = (s: string): string => s
  .replace(/<[^>]*>/g, '')
  .replace(/&(amp|lt|gt|quot|#39|nbsp);/gi, m => ({
    '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&nbsp;': ' '
  })[m] || m)
  // 新浪 rich_text 内嵌样式控制字符（转义序列落在 0x00-0x1F / 0x7F-0x9F），一并剥离
  .replace(/[\u0000-\u001f\u007f-\u009f]/g, '')
  .replace(/\s+/g, ' ')
  .trim();

function proxyNews(num: string, res: ServerResponse): void {
  const n = Math.min(Math.max(parseInt(num) || 20, 1), 100);
  const target = `https://zhibo.sina.com.cn/api/zhibo/feed?callback=callback&page=1&page_size=${n}&zhibo_id=152&tag_id=0&dire=f&dpc=1&pagesize=${n}&id=4161089&type=0&_=${Date.now()}`;
  console.log(`  ↳ GET zhibo.sina.com.cn (新闻 ×${n})`);
  https.get(target, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Referer': 'https://finance.sina.com.cn',
    }
  }, (pres) => {
    let body = '';
    pres.setEncoding('utf8');
    pres.on('data', c => body += c);
    pres.on('end', () => {
      try {
        // JSONP 包装: try{callback({...});}catch(e){};
        const m = body.match(/try\{callback\((.*)\);\}catch\(e\)\{\};/s);
        if (!m) throw new Error('JSONP 解析失败');
        const data = JSON.parse(m[1]);
        const list = data?.result?.data?.feed?.list || [];
        const news = list.map((it: any) => ({
          text: stripRichText(String(it.rich_text || it.title || '')).replace(/\s+/g, ' ').trim(),
          time: it.create_time || '',
          tags: (it.tag || []).map((t: any) => t.name).filter(Boolean),
          url: it.docurl || '',   // 新浪 7x24 详情页原始链接
        })).filter((x: any) => x.text);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' });
        res.end(JSON.stringify({ list: news, fetched_at: new Date().toLocaleString('zh-CN', { hour12: false }) }));
      } catch (e: any) {
        res.writeHead(502);
        res.end(JSON.stringify({ error: 'News proxy: ' + e.message }));
      }
    });
  }).on('error', (e) => {
    res.writeHead(502);
    res.end(JSON.stringify({ error: 'Proxy error: ' + e.message }));
  });
}

// 新浪行业资金排名（最活跃板块）: /proxy/sector-money
// 与 AI-Tools MoneyFlowTool 同源：Windows Edge UA + Host/Referer 防盗链头，缺一可能返回 mock
function proxySectorMoney(res: ServerResponse): void {
  const target = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk?page=1&num=20&sort=netamount&asc=0&fenlei=0';
  console.log('  ↳ GET vip.stock.finance.sina.com.cn (行业资金排行)');
  https.get(target, {
    headers: {
      'Host': 'vip.stock.finance.sina.com.cn',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
      'Referer': 'https://finance.sina.com.cn',
    }
  }, (pres) => {
    let body = '';
    pres.setEncoding('utf8');
    pres.on('data', c => body += c);
    pres.on('end', () => {
      res.writeHead(pres.statusCode ?? 502, {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': '*',
      });
      res.end(body);
    });
  }).on('error', (e) => {
    res.writeHead(502);
    res.end(JSON.stringify({ error: 'Proxy error: ' + e.message }));
  });
}

function httpGetJsonp(urlStr: string, headers: Record<string, string>): Promise<string> {
  return new Promise((resolve, reject) => {
    https.get(urlStr, { headers }, (pres) => {
      let body = '';
      pres.setEncoding('utf8');
      pres.on('data', c => body += c);
      pres.on('end', () => resolve(body));
    }).on('error', reject);
  });
}

// 全市场市场宽度: /proxy/market-breadth
// 涨跌家数/平盘/中位数档 ← 东财涨跌分布(push2ex)；领涨领跌 ← 新浪 Market_Center 排行
// （东财 push2 clist 对 node TLS 指纹风控会 socket hang up，故排行改走新浪）
function proxyMarketBreadth(res: ServerResponse): void {
  const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0';
  const distUrl = 'https://push2ex.eastmoney.com/getTopicZDFenBu?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt';
  const rankUrl = (asc: number) => `https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=1&sort=changepercent&asc=${asc}&node=hs_a`;
  console.log('  ↳ GET eastmoney(分布) + sina(涨跌幅榜)');
  Promise.all([
    httpGetJsonp(distUrl, { 'Referer': 'https://quote.eastmoney.com/', 'User-Agent': UA }),
    httpGetJsonp(rankUrl(0), { 'Referer': 'https://finance.sina.com.cn', 'User-Agent': UA }),
    httpGetJsonp(rankUrl(1), { 'Referer': 'https://finance.sina.com.cn', 'User-Agent': UA }),
  ]).then(([distRaw, topRaw, bottomRaw]) => {
    try {
      const dist = JSON.parse(distRaw)?.data || {};
      const fenbu = dist.fenbu || [];
      let rise = 0, fall = 0, flat = 0, total = 0;
      const bands: [number, number][] = [];
      for (const it of fenbu) {
        const k = Object.keys(it)[0];
        const n = parseInt(it[k]) || 0;
        bands.push([parseInt(k), n]);
        const v = parseInt(k);
        if (v > 0) rise += n; else if (v < 0) fall += n; else flat += n;
        total += n;
      }
      // 涨跌幅中位数（按分档累计取覆盖 50% 的档位）
      const sorted = [...bands].sort((a, b) => a[0] - b[0]);
      let acc = 0, median = 0;
      for (const [v, n] of sorted) { acc += n; if (acc >= total / 2) { median = v; break; } }
      // 原始分档（-11 ~ +11 缺失档补 0），供前端画涨跌分布直方图
      const distBands: { pct: number; count: number }[] = [];
      for (let v = -11; v <= 11; v++) {
        const hit = bands.find(x => x[0] === v);
        distBands.push({ pct: v, count: hit ? hit[1] : 0 });
      }
      const pick = (raw: string) => {
        const arr = JSON.parse(raw);
        const item = Array.isArray(arr) ? arr[0] : null;
        return item ? { name: item.name || '', code: item.code || '', pct: parseFloat(item.changepercent) || 0 } : null;
      };
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' });
      res.end(JSON.stringify({ date: dist.qdate || '', rise, fall, flat, total, median, bands: distBands, top: pick(topRaw), bottom: pick(bottomRaw) }));
    } catch (e: any) {
      res.writeHead(502);
      res.end(JSON.stringify({ error: 'Breadth proxy: ' + e.message }));
    }
  }).catch((e) => {
    res.writeHead(502);
    res.end(JSON.stringify({ error: 'Proxy error: ' + e.message }));
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

// 公共流式执行核心（发送 / 重新生成共用）
async function runAgentStream(res: ServerResponse, session: Session, sessionId: string, toolsEnabled: boolean): Promise<void> {
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

  try {
    const result = streamText({
      model: modelProvider(AI_MODEL),
      system: SYSTEM_PROMPT,
      messages: session.messages,
      tools: toolsEnabled ? (ALL_TOOLS as unknown as Record<string, CoreTool>) : {},
      maxSteps: 5,
      temperature: 0.3,
      abortSignal: controller.signal,
      onStepFinish: (step) => {
        // 每轮 tool call 结束推送状态事件
        const tc = step.toolCalls?.[0];
        if (tc) {
          console.log(`  🔧 tool: ${tc.toolName} ${JSON.stringify(tc.args).slice(0, 100)}`);
          sendEvent(res, 'status', { content: `正在查询${TOOL_LABELS[tc.toolName] || tc.toolName}…` });
        }
        if (step.text) console.log(`  💬 step文本: ${step.text.slice(0, 60).replace(/\n/g, ' ')}`);
        console.log(`  ⏱ step结束: finishReason=${step.finishReason} toolCalls=${step.toolCalls?.length || 0}`);
      },
    });

    // 逐字流式推送最终回复文本
    let textLen = 0;
    for await (const delta of result.textStream) {
      textLen += delta.length;
      sendEvent(res, 'text', { delta });
    }

    // 持久化：以 SDK 回吐的完整消息为准（含 tool-call/tool-result，格式天然兼容下次请求）
    const response = await result.response;
    session.messages = [...response.messages];
    session.updated = Date.now();
    saveSessions();
    console.log(`  ✓ agent完成: 文本${textLen}字, 共${response.messages.length}条消息${textLen === 0 ? '（⚠️ 空回复）' : ''}`);
    sendEvent(res, 'done', { sessionId });
  } catch (e: any) {
    console.error('  ✗ agent错误:', (e && e.message) ? e.message : e, (e && e.statusCode) ? `(HTTP ${e.statusCode})` : '');
    if (e && e.cause) console.error('      cause:', e.cause);
    sendEvent(res, 'error', { message: (e && e.message) ? String(e.message) : 'AI 服务异常' });
  } finally {
    clearInterval(heartbeat);
    res.end();
  }
}

async function handleAgentRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
  // 鉴权：与现有 /api/ 行为一致
  const cookie = readCookie();
  if (!cookie) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies' }));
    return;
  }

  let body: { sessionId?: string; query?: string; toolsEnabled?: boolean };
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
    res.end(JSON.stringify({ error: '未配置 AI API Key（~/.tzzb_ai_config.json 配置文件 / TZZB_AI_KEY 环境变量 / ~/.tzzb_ai_key 文件）' }));
    return;
  }

  console.log(`  🤖 ${sessionId} | ${query.slice(0, 50)}${query.length > 50 ? '…' : ''}`);
  console.log(`  → model=${AI_MODEL} baseURL=${AI_BASE_URL || 'DeepSeek官方'} key=${AI_API_KEY.slice(0, 8)}…`);

  const session = getSession(sessionId);
  session.messages.push({ role: 'user', content: query });
  if (!session.title) session.title = query.slice(0, 20);  // 首次对话自动命名

  await runAgentStream(res, session, sessionId, body.toolsEnabled !== false);
}

async function handleAgentHistory(req: IncomingMessage, res: ServerResponse, url: URL): Promise<void> {
  const cookie = readCookie();
  if (!cookie) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies' }));
    return;
  }

  const sessionId = url.searchParams.get('sessionId') || 'default';
  const s = sessions.get(sessionId);
  const messages = (s?.messages || [])
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => ({ role: m.role, text: extractText(m) }));
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ messages }));
}

async function handleAgentClear(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const cookie = readCookie();
  if (!cookie) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies' }));
    return;
  }

  let body: any;
  try { body = await readJsonBody(req); }
  catch { body = {}; }
  sessions.delete(body.sessionId || 'default');
  saveSessions();
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true }));
}

async function handleAgentSessions(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const cookie = readCookie();
  if (!cookie) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies' }));
    return;
  }
  const list = [...sessions.entries()]
    .map(([id, s]) => ({ id, title: s.title || deriveTitle(s.messages), updated: s.updated }))
    .sort((a, b) => b.updated - a.updated);
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ sessions: list }));
}

async function handleAgentRename(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const cookie = readCookie();
  if (!cookie) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies' }));
    return;
  }
  let body: any;
  try { body = await readJsonBody(req); }
  catch { body = {}; }
  const title = String(body.title || '').trim();
  if (!title || title.length > 50) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'title 不合法（1-50 字）' }));
    return;
  }
  const s = sessions.get(body.sessionId);
  if (!s) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: '会话不存在' }));
    return;
  }
  s.title = title;
  saveSessions();
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true }));
}

async function handleAgentDelete(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const cookie = readCookie();
  if (!cookie) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies' }));
    return;
  }
  let body: any;
  try { body = await readJsonBody(req); }
  catch { body = {}; }
  sessions.delete(body.sessionId || 'default');  // 幂等
  saveSessions();
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true }));
}

async function handleAgentRegenerate(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const cookie = readCookie();
  if (!cookie) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'No cookie found. Run: echo "your-cookie" > ~/.tzzb_cookies' }));
    return;
  }
  let body: any;
  try { body = await readJsonBody(req); }
  catch { body = {}; }
  const sessionId = body.sessionId || 'default';
  const session = sessions.get(sessionId);
  if (!session || !session.messages.some(m => m.role === 'user')) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: '无可重新生成的消息' }));
    return;
  }
  if (!AI_API_KEY) {
    res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: '未配置 AI API Key（~/.tzzb_ai_config.json 配置文件 / TZZB_AI_KEY 环境变量 / ~/.tzzb_ai_key 文件）' }));
    return;
  }
  // 弹出最后一条 assistant 消息重新生成；若最后一条是 user（上次失败），直接重跑
  const last = session.messages[session.messages.length - 1];
  if (last && last.role === 'assistant') session.messages.pop();
  console.log(`  🤖 ${sessionId} | 重新生成`);
  await runAgentStream(res, session, sessionId, body.toolsEnabled !== false);
}

const server = http.createServer((req: IncomingMessage, res: ServerResponse) => {
  const url = new URL(req.url ?? '/', 'http://localhost:' + PORT);
  const pathname = url.pathname;
  const method = req.method;

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
  if (pathname === '/api/agent/sessions' && method === 'GET') {
    return handleAgentSessions(req, res);
  }
  if (pathname === '/api/agent/rename' && method === 'POST') {
    return handleAgentRename(req, res);
  }
  if (pathname === '/api/agent/delete' && method === 'POST') {
    return handleAgentDelete(req, res);
  }
  if (pathname === '/api/agent/regenerate' && method === 'POST') {
    return handleAgentRegenerate(req, res);
  }

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

  // 全球主要股指: /proxy/global-indexes
  if (pathname.startsWith('/proxy/global-indexes')) {
    return proxyGlobalIndexes(res);
  }

  // 新浪实时行情（A 股指数补充）: /proxy/stock-price?codes=sh000300,sz399006
  if (pathname.startsWith('/proxy/stock-price')) {
    const codes = url.searchParams.get('codes') || '';
    if (codes) return proxyStockPrice(codes, res);
    res.writeHead(400);
    res.end(JSON.stringify({ error: 'Missing codes parameter' }));
    return;
  }

  // 新浪财经直播新闻: /proxy/news?num=20
  if (pathname.startsWith('/proxy/news')) {
    return proxyNews(url.searchParams.get('num') || '20', res);
  }

  // 新浪行业资金排名（最活跃板块）: /proxy/sector-money
  if (pathname.startsWith('/proxy/sector-money')) {
    return proxySectorMoney(res);
  }

  // 全市场涨跌家数 + 领涨领跌: /proxy/market-breadth
  if (pathname.startsWith('/proxy/market-breadth')) {
    return proxyMarketBreadth(res);
  }

  // Static files
  let filePath = pathname === '/' ? '/index.html' : pathname === '/ai' ? '/ai.html' : pathname;
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

server.listen(PORT, '127.0.0.1', () => {
  loadSessions();
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

  if (!AI_API_KEY) {
    console.log('  ⚠️  未配置 AI API Key');
    console.log('     推荐写入 ~/.tzzb_ai_config.json（apiKey/model/baseURL，见 README）');
    console.log('     或用 TZZB_AI_KEY 环境变量 / ~/.tzzb_ai_key 文件');
    console.log('     AI 对话功能将不可用，但不影响其他功能');
  } else {
    console.log(`  🤖 AI: ${AI_MODEL} @ ${AI_BASE_URL || 'DeepSeek 官方端点'} (key ${AI_API_KEY.slice(0, 8)}…)`);
  }

  console.log('  启动完成，不会自动打开浏览器，请手动访问上面的地址');
});
