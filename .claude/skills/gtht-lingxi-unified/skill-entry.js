#!/usr/bin/env node
// ============================================================================
// 国泰海通灵犀 (GTHT Lingxi) 统一 Skill
// 版本: 2.0.0
// 整合: 行情查询 | 市场榜单 | 自选股管理 | 金融数据 | 智能选股 | 回测 | 研报搜索
// ============================================================================

"use strict";

const https = require("https");
const http = require("http");
const fs = require("fs");
const path = require("path");
const os = require("os");
const crypto = require("crypto");

// ============================================================================
// 1. 工具函数 (Utilities)
// ============================================================================

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const isNum = (v) => typeof v === "number" || (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v.trim()));

const toNum = (v) => {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && isNum(v)) { const n = Number(v); return Number.isFinite(n) ? n : null; }
  return null;
};

const numVal = (v) => (v && typeof v === "object" && "value" in v) ? toNum(v.value) : toNum(v);

const safeJson = (s) => {
  try { return JSON.parse(s); } catch {
    // 有时响应文本前面有中文提示，找第一个 { 开始解析
    const idx = s.indexOf("{");
    if (idx > 0) {
      try { return JSON.parse(s.slice(idx)); } catch { /* fall through */ }
    }
    try { return JSON.parse(s.replace(/"bgStatus"\s*:\s*,/g, '"bgStatus": null,')); } catch { return null; }
  }
};

const fmtNum = (v, d = 2) => Number.isFinite(v) ? new Intl.NumberFormat("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v) : "--";

const fmtPct = (v, d = 2) => Number.isFinite(v) ? `${v > 0 ? "+" : ""}${v.toFixed(d)}%` : "--";

const fmtPrice = (v, d = 2) => Number.isFinite(v) ? `${v > 0 ? "+" : ""}${fmtNum(v, d)} 元` : "--";

const fmtYi = (v, d = 2) => {
  if (!Number.isFinite(v)) return "--";
  const n = v / 1e8;
  const sign = n > 0 ? "+" : "";
  return `${sign}${fmtNum(n, d)}亿元`;
};

const fmtYiNoSign = (v, d = 2) => Number.isFinite(v) ? `${fmtNum(v / 1e8, d)}亿元` : "--";

const fmtWanGu = (v) => Number.isFinite(v) ? `${fmtNum(Math.round(v / 1e4), 0)}万股` : "--";

const fmtYiShiZhi = (v) => Number.isFinite(v) ? `${Math.round(v / 1e8)}亿` : "--";

const fmtVol = (v, unit = 100) => {
  if (!Number.isFinite(v)) return "--";
  const n = v / unit;
  return Math.abs(n) >= 1e4 ? `${fmtNum(n / 1e4, 2)}万手` : `${fmtNum(n, 2)}手`;
};

const fmtAmount = (v, pDiv = 1) => {
  if (!Number.isFinite(v)) return "--";
  const n = v / pDiv;
  return Math.abs(n) >= 1e8 ? `${fmtNum(n / 1e8, 2)}亿` : Math.abs(n) >= 1e4 ? `${fmtNum(n / 1e4, 2)}万元` : `${fmtNum(n, 2)}元`;
};

// 列宽计算（中文字符占2个宽度）
const charWidth = (s) => { let w = 0; for (const c of String(s)) w += c.charCodeAt(0) > 255 ? 2 : 1; return w; };
const padStr = (s, w) => { const diff = w - charWidth(s); const l = Math.floor(diff / 2), r = diff - l; return " ".repeat(l) + s + " ".repeat(r); };

// Markdown 表格生成
function mkTable(headers, rows) {
  const widths = headers.map((h, i) => Math.max(charWidth(h), ...rows.map(r => charWidth(String(r[i] || "--")))));
  const sep = "|" + widths.map(w => "-".repeat(w + 2)).join("|") + "|";
  const hdr = "| " + headers.map((h, i) => padStr(h, widths[i])).join(" | ") + " |";
  const body = rows.map(r => "| " + r.map((c, i) => padStr(String(c ?? "--"), widths[i])).join(" | ") + " |").join("\n");
  return hdr + "\n" + sep + "\n" + body;
}

// ============================================================================
// 2. 配置管理 (Config)
// ============================================================================

function resolveSkillDir() { return path.resolve(__dirname); }

function resolveAuthFile() {
  const here = resolveSkillDir();
  const parent = path.dirname(here);
  const gparent = path.dirname(parent);
  const ggparent = path.dirname(gparent);
  const candidates = [
    path.join(parent, "gtht-skill-shared", "gtht-entry.json"),
    path.join(gparent, "gtht-skill-shared", "gtht-entry.json"),
    path.join(ggparent, "gtht-skill-shared", "gtht-entry.json"),
    path.join(here, "gtht-entry.json"),
  ];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  // 首选：当前目录
  const pref = path.join(here, "gtht-entry.json");
  fs.mkdirSync(path.dirname(pref), { recursive: !0 });
  return pref;
}

function loadApiKey() {
  try {
    const f = resolveAuthFile();
    if (!fs.existsSync(f)) return null;
    const raw = JSON.parse(fs.readFileSync(f, "utf8"));
    const key = raw?.apiKey ?? raw?.["api-key"] ?? raw?.apikey;
    return key && String(key).trim() ? String(key).trim() : null;
  } catch { return null; }
}

function saveApiKey(key) {
  const f = resolveAuthFile();
  fs.mkdirSync(path.dirname(f), { recursive: !0 });
  fs.writeFileSync(f, JSON.stringify({ apiKey: String(key).trim() }));
  console.log(`✓ API Key 已保存到: ${f}`);
}

function clearAuth() {
  const f = resolveAuthFile();
  if (fs.existsSync(f)) { fs.unlinkSync(f); console.log("✓ 授权已清除"); }
  else console.log("✓ 未找到授权文件");
}

function getJwtToken() {
  const key = loadApiKey();
  if (!key) return "";
  let t = String(key).trim();
  if (t.startsWith("{") && t.endsWith("}")) { try { const o = JSON.parse(t); t = String(o["api-key"] || o.apiKey || o.jwtToken || "").trim(); } catch { return ""; } }
  const idx = t.indexOf("||");
  const n = idx >= 0 ? t.slice(idx + 2).trim() : t;
  return n.length > 16 ? n.slice(16) : n;
}

function parseUserCode(jwt) {
  try {
    if (!jwt) return "";
    const parts = jwt.split(".");
    if (parts.length < 2) return "";
    const payload = Buffer.from(parts[1].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8");
    return String(JSON.parse(payload).userCode || "");
  } catch { return ""; }
}

function loadGatewayConfig() {
  const cfgPath = path.join(resolveSkillDir(), "gateway-config.json");
  const def = {
    active_env: "prod",
    base_urls: { prod: "https://zx.app.gtja.com:8443/" },
    gateways: { market: "https://zx.app.gtja.com:8443/mcp/marketdata", mqtt: "https://zx.app.gtja.com:8443/mcp/mqtt" },
  };
  try {
    if (fs.existsSync(cfgPath)) {
      const c = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
      const env = c.active_env || "prod";
      const base = (c.base_urls || {})[env] || def.base_urls.prod;
      if (c.gateways) return c.gateways;
      const paths = c.gateway_paths || {};
      const gws = {};
      for (const [k, p] of Object.entries(paths)) gws[k] = new URL(p, base.endsWith("/") ? base : base + "/").toString();
      return gws;
    }
  } catch (e) { console.error("加载网关配置失败:", e.message); }
  return def.gateways;
}

// ============================================================================
// 3. 网络层 (Network)
// ============================================================================

const CHANNEL = "junhong";
const PLATFORM = "Xclow_skills";
const SKILL_NAME = "gtht-lingxi-unified";
const SKILL_VERSION = "2.0.0";

async function jsonRpc(gatewayUrl, toolName, args = {}, extraHeaders = {}, opts = {}) {
  const { includeKey = true, includeJwt = true, includeChannel = true } = opts;
  const jwt = getJwtToken();
  const userCode = parseUserCode(jwt);

  const params = includeKey ? { ...args, key: jwt } : { ...args };

  const body = JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: toolName, arguments: params } });
  const url = new URL(gatewayUrl);
  const headers = {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
    "skill-name": SKILL_NAME,
    "version": SKILL_VERSION,
    platform: PLATFORM,
    ...(includeJwt && jwt ? { "jwt-assertion": jwt, usercode: userCode } : {}),
    ...(includeChannel ? { channel: CHANNEL } : {}),
    ...extraHeaders,
  };

  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: url.hostname, port: url.port || 443, path: url.pathname,
      method: "POST", headers, rejectUnauthorized: true,
    }, (res) => {
      let data = "";
      res.on("data", (c) => { data += c; });
      res.on("end", () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(new Error(`解析响应失败: ${data}`)); }
      });
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function parseResponse(rpcResp) {
  if (rpcResp.error) return { error: rpcResp.error.message };
  if (rpcResp.result?.content) {
    const textItem = rpcResp.result.content.find((c) => c.type === "text");
    if (textItem) {
      const parsed = safeJson(textItem.text);
      return parsed !== null ? parsed : { text: textItem.text };
    }
  }
  return rpcResp.result || rpcResp;
}

async function callTool(gateway, toolName, args = {}, opts = {}) {
  const gws = loadGatewayConfig();
  const url = gws[gateway];
  if (!url) throw new Error(`未知网关: ${gateway}，可用: ${Object.keys(gws).join(", ")}`);
  const key = loadApiKey();
  if (!key) throw new Error("未授权: 请先执行 node skill-entry.js auth save <你的API_KEY>");

  // 金融类工具使用 question 参数名而非 query
  const mappedArgs = { ...args };
  if (mappedArgs.query !== undefined) {
    mappedArgs.question = mappedArgs.query;
    delete mappedArgs.query;
  }

  const resp = await jsonRpc(url, toolName, mappedArgs, {}, opts);
  return parseResponse(resp);
}

// ============================================================================
// 4. 股票映射 (StockMap)
// ============================================================================

let _stockMap = null;

function loadStockMap() {
  if (_stockMap) return _stockMap;
  const p = path.join(resolveSkillDir(), "stock_code_name.json");
  if (!fs.existsSync(p)) { _stockMap = { nameToCode: {}, codeToName: {} }; return _stockMap; }
  const arr = JSON.parse(fs.readFileSync(p, "utf8"));
  const n2c = {}, c2n = {};
  for (const item of arr) {
    if (!item || typeof item !== "object") continue;
    const code = String(item.code ?? "").trim();
    const name = String(item.name ?? "").trim();
    if (code && name) { n2c[name] = code; c2n[code] = name; }
  }
  _stockMap = { nameToCode: n2c, codeToName: c2n };
  return _stockMap;
}

function findCodeByName(name) {
  const m = loadStockMap();
  return m.nameToCode[name] || null;
}

function findNameByCode(code) {
  const m = loadStockMap();
  return m.codeToName[code.toUpperCase()] || null;
}

function resolveStockCode(input) {
  const s = String(input || "").trim();
  if (/^(SH|SZ|HK|US|UK|SX|BJ)\d+$/i.test(s)) return s.toUpperCase();
  const code = findCodeByName(s);
  if (code) return code;
  throw new Error(`未找到股票代码: ${s}`);
}

// ============================================================================
// 5. 授权模块 (Auth)
// ============================================================================

function getMacAddress() {
  const nets = os.networkInterfaces();
  for (const name of Object.keys(nets)) {
    for (const iface of nets[name] || []) {
      if (!iface.internal && iface.mac && iface.mac !== "00:00:00:00:00:00") return iface.mac.replace(/:/g, "");
    }
  }
  return crypto.randomBytes(6).toString("hex").toUpperCase();
}

function generateDeviceId() {
  const mac = getMacAddress();
  const ts = String(Math.floor(Date.now() / 1000)).padStart(10, "0");
  const rand = Array.from({ length: 5 }, () => "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ".charAt(Math.floor(Math.random() * 36))).join("");
  return mac + ts + rand;
}

async function pollToken(deviceId, maxAttempts = 100, interval = 3000) {
  for (let i = 1; i <= maxAttempts; i++) {
    process.stdout.write(`\r▶ [${i}/${maxAttempts}] 等待扫码授权 (${Math.floor(interval / 1000) * i}秒)   `);
    try {
      const resp = await callTool("mqtt", "get-token", {
        openDeviceId: deviceId, pageNo: "1", pageSize: "1", mobileUserCode: "0", accountNo: "", accType: "",
      }, { includeKey: false, includeJwt: false, includeChannel: false });
      // 提取 tokenSerialNo||userToken
      let token = "";
      const candidates = [resp?.data?.tokenList?.[0], resp?.data, resp?.result?.data?.tokenList?.[0], resp?.result?.data, resp?.tokenList?.[0], resp];
      for (const c of candidates) {
        const ts = c?.tokenSerialNo, ut = c?.userToken;
        if (ts && ut) { token = `${ts}||${ut}`; break; }
      }
      if (token) {
        saveApiKey(token);
        process.stdout.write("\n\n");
        console.log("========================================");
        console.log("  ✓ 授权成功！API Key 已保存");
        console.log("========================================\n");
        return token;
      }
    } catch (e) {
      if (!String(e.message || "").includes("查询key失败")) {
        process.stdout.write("\n");
        console.error(`✗ 授权结果处理失败: ${e.message}`);
      }
    }
    if (i < maxAttempts) await sleep(interval);
  }
  throw new Error("授权超时（5分钟）");
}

async function authFlow() {
  const deviceId = generateDeviceId();
  const authUrl = `https://apicdn2.app.gtht.com/web2/jh-static-QRCode/?token=${deviceId}`;
  console.log("\n--- 二维码内容信息 ---");
  console.log(`Device ID:   ${deviceId}\n`);
  console.log("云端授权页已生成。请先扫码授权：\n");
  console.log("方式一：扫码授权");
  console.log(`👉 点击链接：${authUrl}\n`);
  console.log("方式二：API Key 授权");
  console.log("进入灵犀 Skills 领取活动页 → API KEY 管理 → 新建或复制生效中的 API KEY\n");
  console.log(`token: ${deviceId}`);
  console.log(`\n用户回复"已扫码授权成功"后，请执行：node skill-entry.js auth poll ${deviceId}`);
  return { mode: "awaiting-confirmation", deviceId, authUrl };
}

async function authMain(args) {
  const cmd = args[0];
  if (cmd === "check") {
    const key = loadApiKey();
    if (key) console.log(`✓ 已授权\nAPI Key: ${key.substring(0, 8)}...${key.substring(key.length - 8)}`);
    else { console.log("✗ 未授权"); process.exit(1); }
  } else if (cmd === "save") {
    const key = args.slice(1).join(" ").trim();
    if (!key) { console.error("请提供 API Key"); process.exit(1); }
    saveApiKey(key);
    console.log("✓ 授权成功！");
  } else if (cmd === "poll") {
    const deviceId = args[1];
    if (!deviceId) { console.error("请提供 token（deviceId）"); process.exit(1); }
    await pollToken(deviceId);
  } else if (cmd === "clear") {
    clearAuth();
  } else {
    // 默认执行 auth 流程
    await authFlow();
  }
}

// ============================================================================
// 6. 行情查询 (MarketData)
// ============================================================================

function parseMarketItem(item) {
  if (!item || typeof item !== "object") return null;
  const code = item.code || "--";
  const name = item.name || "--";
  const pDec = numVal(item.price_decimal_places) ?? 2;
  const rDec = numVal(item.ratio_decimal_places) ?? 2;
  const pDiv = 10 ** pDec;
  const rDiv = 10 ** rDec;
  const unit = numVal(item.min_order_unit) ?? 100;

  const last = numVal(item.last_price);
  const open = numVal(item.open_price);
  const high = numVal(item.high_price);
  const low = numVal(item.low_price);
  const change = numVal(item.price_change);
  const chgRate = numVal(item.change_rate);
  const osc = numVal(item.osc_rate);
  const volRatio = numVal(item.relative_volume_ratio);
  const volume = numVal(item.total_volume);
  const amount = numVal(item.total_amount);
  const mktCap = numVal(item.total_market_capital);
  const turnover = numVal(item.turnover_rate);
  const capFlow = numVal(item.capital_flow);

  return {
    code, name,
    last: last != null ? last / pDiv : null,
    open: open != null ? open / pDiv : null,
    high: high != null ? high / pDiv : null,
    low: low != null ? low / pDiv : null,
    change: change != null ? change / pDiv : null,
    chgRate: chgRate != null ? chgRate / rDiv * 100 : null,
    osc: osc != null ? osc / rDiv * 100 : null,
    volRatio: volRatio != null ? volRatio / rDiv : null,
    volume: volume,
    amount: amount != null ? amount / pDiv : null,
    mktCap: mktCap != null ? mktCap / pDiv : null,
    turnover: turnover != null ? turnover / rDiv * 100 : null,
    capFlow: capFlow != null ? capFlow / pDiv : null,
    unit, pDec, rDec,
  };
}

function formatMarketItem(d) {
  if (!d) return "无数据";
  const pd = Math.min(d.pDec, 3);
  const rd = Math.min(d.rDec, 2);
  const lines = [
    `【${d.name} (${d.code})】`,
    ``,
    `最新价：${d.last != null ? fmtNum(d.last, pd) + " 元" : "--"}`,
    `开盘价：${d.open != null ? fmtNum(d.open, pd) + " 元" : "--"}`,
    `最高价：${d.high != null ? fmtNum(d.high, pd) + " 元" : "--"}`,
    `最低价：${d.low != null ? fmtNum(d.low, pd) + " 元" : "--"}`,
    `涨跌幅：${d.chgRate != null ? fmtPct(d.chgRate, rd) : "--"}`,
    `涨跌额：${d.change != null ? fmtPrice(d.change, pd) : "--"}`,
    `振幅：${d.osc != null ? fmtPct(d.osc, rd) : "--"}`,
    `量比：${d.volRatio != null ? fmtNum(d.volRatio, rd) : "--"}`,
    `成交量：${d.volume != null ? fmtVol(d.volume, d.unit) : "--"}`,
    `成交额：${d.amount != null ? fmtAmount(d.amount) : "--"}`,
  ];
  if (d.turnover != null && d.turnover !== 0) lines.push(`换手率：${d.turnover.toFixed(d.rDec)}%`);
  if (d.capFlow != null && d.capFlow !== 0) lines.push(`当日资金净流入：${fmtAmount(d.capFlow)}`);
  if (d.mktCap != null && d.mktCap !== 0) lines.push(`总市值：${fmtAmount(d.mktCap)}`);
  return lines.join("\n");
}

async function marketdataMain(args) {
  if (args.length === 0 || args[0] === "--help") {
    console.log("用法: node skill-entry.js marketdata <股票代码或名称> [股票代码或名称...]");
    console.log("示例: node skill-entry.js marketdata SH601211");
    console.log("      node skill-entry.js marketdata 贵州茅台 宁德时代");
    return;
  }
  const codes = [];
  for (const arg of args) {
    try { codes.push(resolveStockCode(arg)); } catch (e) { console.error(`✗ ${e.message}`); }
  }
  if (codes.length === 0) { console.error("没有有效的股票代码"); process.exit(1); }

  const normalizedCodes = codes.map(c => ({
    code: c,
    market_data_mask: { mask: { M_64_0: 549755813887 } },
    product_mask: { mask: { M_64_0: 111111 } },
  }));
  const resp = await callTool("market", "marketdata-tool", {
    reduced_codes: normalizedCodes,
  });

  const items = extractItems(resp);
  if (items.length === 0) { console.log("未获取到行情数据"); return; }

  for (const item of items) {
    const d = parseMarketItem(item);
    console.log(formatMarketItem(d));
    console.log("");
  }
}

function extractItems(resp) {
  if (Array.isArray(resp)) return resp;
  if (resp?.stocks && Array.isArray(resp.stocks)) return resp.stocks;
  if (resp?.items && Array.isArray(resp.items) && resp.items[0]?.board_items) return resp.items[0].board_items;
  if (resp?.data && Array.isArray(resp.data)) return resp.data;
  if (resp?.list && Array.isArray(resp.list)) return resp.list;
  if (resp?.rank_list && Array.isArray(resp.rank_list)) return resp.rank_list;
  if (resp?.board_items && Array.isArray(resp.board_items)) return resp.board_items;
  if (resp?.data?.list && Array.isArray(resp.data.list)) return resp.data.list;
  if (resp && typeof resp === "object") {
    for (const v of Object.values(resp)) {
      if (Array.isArray(v) && v.length > 0 && typeof v[0] === "object") return v;
    }
  }
  return [];
}

// ============================================================================
// 7. 榜单查询 (RankList)
// ============================================================================

const RANK_ORDER_MAP = {
  0: { name: "最新价", fmt: (v) => v != null ? fmtNum(v, 2) + "元" : "--" },
  1: { name: "涨跌值", fmt: (v) => v != null ? fmtPrice(v, 2) : "--" },
  2: { name: "涨跌幅", fmt: (v) => v != null ? fmtPct(v * 100) : "--" },
  3: { name: "振幅", fmt: (v) => v != null ? fmtPct(v * 100) : "--" },
  4: { name: "5分钟涨幅", fmt: (v) => v != null ? fmtPct(v * 100) : "--" },
  5: { name: "换手率", fmt: (v) => v != null ? fmtPct(v * 10000) : "--" },
  6: { name: "总市值", fmt: (v) => v != null ? fmtYiShiZhi(v) : "--" },
  7: { name: "市盈率", fmt: (v) => v != null ? fmtNum(v, 2) : "--" },
  8: { name: "量比", fmt: (v) => v != null ? fmtNum(v, 2) : "--" },
  9: { name: "成交量", fmt: (v) => v != null ? fmtWanGu(v) : "--" },
  10: { name: "成交额", fmt: (v) => v != null ? fmtYiNoSign(v) : "--" },
  11: { name: "当日资金净流入", fmt: (v) => v != null ? fmtYi(v) : "--" },
};

const RANK_FIELD_MAP = {
  0: "last_price", 1: "deal_price_change", 2: "price_change_percent",
  3: "osc", 4: "price_change_speed_5m", 5: "turnover_ratio",
  6: "market_cap", 7: "price_to_earn", 8: "relative_volume_ratio",
  9: "total_volume", 10: "total_amount", 11: "capital_flow",
};

async function ranklistMain(args) {
  // 解析参数，支持 --key value 和 --key=value 两种格式
  let orderBy = 2, limit = 20, sortedType = 1;
  for (let i = 0; i < args.length; i++) {
    let key = args[i], val = null, consumedNext = false;
    if (key.includes("=")) {
      const parts = key.split("=");
      key = parts[0];
      val = parts.slice(1).join("=");
    } else if (i + 1 < args.length) {
      val = args[i + 1];
      consumedNext = true;
    }
    if (key === "--order-by" && val) { orderBy = parseInt(val); if (consumedNext) i++; }
    else if (key === "--limit" && val) { limit = parseInt(val); if (consumedNext) i++; }
    else if (key === "--sort" && val) { sortedType = val === "asc" ? 2 : 1; if (consumedNext) i++; }
  }

  if (orderBy < 0 || orderBy > 11) orderBy = 0;
  const rankInfo = RANK_ORDER_MAP[orderBy];

  const resp = await callTool("ranklist", "ranklist", {
    code: "BK101003", limit, offset: 0, sorted_type: sortedType, order_by: orderBy,
    mask: { M_64_0: 35184372088831 },
  });

  const items = extractItems(resp);
  if (items.length === 0) { console.log("未获取到榜单数据"); return; }

  const fieldName = RANK_FIELD_MAP[orderBy];
  const sortLabel = sortedType === 1 ? "降序" : "升序";
  const title = `【${rankInfo.name}排行榜 TOP ${Math.min(limit, items.length)}】（${sortLabel}）`;

  const rows = items.slice(0, limit).map((item, idx) => {
    const name = item.name || "--";
    const code = item.code || "--";
    const rawVal = numVal(item[fieldName]);
    const val = rawVal != null ? rankInfo.fmt(rawVal) : "--";
    return [String(idx + 1), name, code, val];
  });

  console.log(`\n${title}\n`);
  console.log(mkTable(["排名", "名称", "代码", rankInfo.name], rows));
  console.log(`\n数据时间：${new Date().toISOString().slice(0, 16).replace("T", " ")}`);
  console.log(`\n> 市场热榜查询Skill仅提供客观数据，不构成投资建议。\n`);
}

// ============================================================================
// 8. 金融数据查询 (Financial)
// ============================================================================

async function financialMain(args) {
  const query = args.join(" ").trim();
  if (!query) { console.error("请提供查询内容"); process.exit(1); }

  const resp = await callTool("financial", "financial-search", { query });
  // 提取 text 字段中的内容并格式化
  const text = resp?.text;
  if (text) {
    try {
      const parsed = JSON.parse(text);
      console.log(`\n📊 查询结果：\n`);
      // 如果 result 字段是 markdown 表格，直接输出
      if (parsed.result) {
        console.log(parsed.result);
      } else {
        console.log(JSON.stringify(parsed, null, 2));
      }
    } catch {
      console.log(text);
    }
  } else {
    console.log(JSON.stringify(resp, null, 2));
  }
  console.log(`\n> 以上信息源自第三方数据整理，仅供参考。金融数据查询Skill仅提供客观数据，不构成投资建议。\n`);
}

// ============================================================================
// 9. 智能选股 (StockSelect)
// ============================================================================

async function stockselectMain(args) {
  const query = args.join(" ").trim();
  if (!query) { console.error("请提供选股条件"); process.exit(1); }

  const resp = await callTool("stockselect", "financial-search", { query });
  console.log(JSON.stringify(resp, null, 2));
  console.log(`\n> 以上信息源自第三方数据整理。智能选股Skill仅提供客观数据，不构成投资建议。\n`);
}

// ============================================================================
// 10. 回测 (Backtest)
// ============================================================================

async function backtestMain(args) {
  let query = "", startDate, endDate, holdingPeriod, stockHoldCount, dayBuyStockNum;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--query" && args[i + 1]) { query = args[i + 1]; i++; }
    else if (args[i] === "--start-date" && args[i + 1]) { startDate = args[i + 1]; i++; }
    else if (args[i] === "--end-date" && args[i + 1]) { endDate = args[i + 1]; i++; }
    else if (args[i] === "--holding-period" && args[i + 1]) { holdingPeriod = args[i + 1]; i++; }
    else if (args[i] === "--stock-hold" && args[i + 1]) { stockHoldCount = args[i + 1]; i++; }
    else if (args[i] === "--day-buy" && args[i + 1]) { dayBuyStockNum = args[i + 1]; i++; }
    else if (!args[i].startsWith("--")) query = query ? query + " " + args[i] : args[i];
  }
  if (!query) { console.error("请提供选股条件"); process.exit(1); }

  const params = { query };
  if (startDate) params.startDate = startDate;
  if (endDate) params.endDate = endDate;
  if (holdingPeriod) params.holdingPeriod = holdingPeriod;
  if (stockHoldCount) params.stockHoldCount = stockHoldCount;
  if (dayBuyStockNum) params.dayBuyStockNum = dayBuyStockNum;

  if (!startDate && !endDate && !holdingPeriod && !stockHoldCount && !dayBuyStockNum) {
    console.log("ℹ 使用默认回测参数：开始=三年前, 结束=今天, 持仓周期=10天, 持股上限=10只, 单日买入=5只");
  }

  const resp = await callTool("backtest", "backtest", params);
  console.log(JSON.stringify(resp, null, 2));
  console.log(`\n> 以上展示模拟历史回测结果仅供参考，不代表未来收益，不构成任何投资建议。\n`);
}

// ============================================================================
// 11. 研报搜索 (Research)
// ============================================================================

async function researchMain(args) {
  const query = args.join(" ").trim();
  if (!query) { console.error("请提供搜索关键词"); process.exit(1); }

  const resp = await callTool("researchReport", "search-research-report", { query });
  console.log(JSON.stringify(resp, null, 2));
  console.log(`\n> 研报搜索Skill仅提供客观数据，不构成投资建议。\n`);
}

// ============================================================================
// 12. 自选股管理 (Watchlist)
// ============================================================================

// 获取手机号
async function fetchMobile() {
  const jwt = getJwtToken();
  const userCode = parseUserCode(jwt);
  try {
    const resp = await callTool("usercode", "get-usercode", { mobileUserCode: userCode });
    const text = resp?.result?.content?.[0]?.text;
    if (text) {
      const d = JSON.parse(text);
      return { mobile: d?.data?.mobile || "", userCode: d?.data?.userCode || userCode };
    }
  } catch {}
  return { mobile: "", userCode };
}

function parseStkContent(text) {
  const s = String(text || "").trim();
  if (!s) return [];
  // 格式: "1,我的自选,0:601211,SH,0;300750,SZ,0;"
  const parts = s.split(/\|(?=\d+,[^|:,]+,\d+:)/).map(p => p.trim()).filter(Boolean);
  for (const part of parts) {
    const colonIdx = part.indexOf(":");
    if (colonIdx < 0) continue;
    const header = part.slice(0, colonIdx).split(",");
    if (String(header[1] || "").trim() === "我的自选") {
      return part.slice(colonIdx + 1).split(";").map(stk => stk.trim()).filter(Boolean);
    }
  }
  return [];
}

function parseWatchlistItems(text) {
  const raw = parseStkContent(text);
  return raw.map(r => {
    const [code, market, group] = r.split(",");
    return { fullCode: `${(market || "").toUpperCase()}${code}`, code, market, group };
  });
}

async function watchlistMain(args) {
  const cmd = args[0];
  if (!cmd || cmd === "list") {
    // 查询自选股列表 + 行情
    const resp = await callTool("optionalStock", "get_optionalStock", {
      PAGE_SIZE: "1000", PAGE_NO: "1", ACCT_TYPE: "6",
    });
    const text = resp?.result?.content?.[0]?.text || JSON.stringify(resp);
    const items = parseWatchlistItems(text);
    if (items.length === 0) { console.log("\n📋 自选股列表为空（【我的自选】分组）\n"); return; }

    const codes = items.map(i => i.fullCode);
    let marketData = {};
    try {
      const mdResp = await callTool("market", "marketdata-tool", {
        reduced_codes: codes,
        market_data_mask: { mask: { M_64_0: 549755813887 } },
        product_mask: { mask: { M_64_0: 111111 } },
      });
      const mdItems = extractItems(mdResp);
      for (const item of mdItems) {
        const d = parseMarketItem(item);
        if (d) marketData[d.code] = d;
      }
    } catch {}

    console.log(`\n📊 自选股行情查询（共 ${items.length} 只）\n`);
    console.log("=".repeat(60));
    const rows = items.map((item, idx) => {
      const d = marketData[item.fullCode] || {};
      const name = d.name || item.code || "--";
      const code = item.fullCode;
      const last = d.last != null ? fmtNum(d.last, 3) + " 元" : "--";
      const chg = d.chgRate != null ? fmtPct(d.chgRate, d.rDec || 2) : "--";
      const flow = d.capFlow != null ? fmtAmount(d.capFlow) : "--";
      return [String(idx + 1), name, code, last, chg, flow];
    });
    console.log(mkTable(["#", "名称", "代码", "最新价", "涨跌幅", "当日资金净流入"], rows));
    console.log("");
  } else if (cmd === "add") {
    const stocks = args.slice(1);
    if (stocks.length === 0) { console.error("请提供要添加的股票"); process.exit(1); }
    const codes = [];
    for (const s of stocks) {
      try { codes.push(resolveStockCode(s)); } catch (e) { console.error(`✗ ${e.message}`); }
    }
    if (codes.length === 0) { console.error("没有有效的股票代码"); process.exit(1); }
    const batchData = codes.map(c => ({ STOCK_CODE: c.substring(2), MARKET_CODE: c.substring(0, 2), GROUP_NO: "0" }));
    const resp = await callTool("optionalStock", "op_optionalStock", {
      ACTION_FLAG: "10", BATCH_DATA: batchData, ACCT_TYPE: "6", GROUP_NO: "0",
    });
    const totalNum = (JSON.stringify(resp).match(/"TOTAL_NUM"\s*:\s*"(\d+)"/) || [])[1];
    console.log(`✅ 添加成功！当前自选股数量: ${totalNum || "?"}`);
  } else if (cmd === "remove") {
    const stocks = args.slice(1);
    if (stocks.length === 0) { console.error("请提供要删除的股票"); process.exit(1); }
    // 先获取当前自选股列表以匹配代码
    const resp = await callTool("optionalStock", "get_optionalStock", {
      PAGE_SIZE: "1000", PAGE_NO: "1", ACCT_TYPE: "6",
    });
    const text = resp?.result?.content?.[0]?.text || "";
    const existing = parseWatchlistItems(text);
    const codes = [];
    for (const s of stocks) {
      const upper = s.toUpperCase();
      if (/^(SH|SZ)\d+$/i.test(upper)) {
        const found = existing.find(i => i.fullCode === upper);
        if (found) codes.push(found.fullCode);
        else console.error(`✗ 未在自选股中找到: ${s}`);
      } else {
        const found = existing.filter(i => i.code === upper || i.fullCode.includes(upper));
        if (found.length === 1) codes.push(found[0].fullCode);
        else if (found.length > 1) console.error(`✗ 存在多个匹配: ${s}，请使用完整代码`);
        else console.error(`✗ 未在自选股中找到: ${s}`);
      }
    }
    if (codes.length === 0) { console.error("没有有效的股票代码"); process.exit(1); }
    console.log(`\n📝 将要删除: ${codes.join(", ")}\n`);
    const batchData = codes.map(c => ({ STOCK_CODE: c.substring(2), MARKET_CODE: c.substring(0, 2), GROUP_NO: "0" }));
    const delResp = await callTool("optionalStock", "op_optionalStock", {
      ACTION_FLAG: "11", BATCH_DATA: batchData, ACCT_TYPE: "6", GROUP_NO: "0",
    });
    const totalNum = (JSON.stringify(delResp).match(/"TOTAL_NUM"\s*:\s*"(\d+)"/) || [])[1];
    console.log(`✅ 删除成功！当前自选股数量: ${totalNum || "?"}`);
  } else {
    console.log("用法: node skill-entry.js watchlist [list|add|remove] [股票...]");
  }
}

// ============================================================================
// 13. 主入口 (CLI Router)
// ============================================================================

function printHelp() {
  console.log(`
╔══════════════════════════════════════════════════════════════╗
║       国泰海通灵犀 (GTHT Lingxi) 统一 Skill v2.0.0           ║
╠══════════════════════════════════════════════════════════════╣
║  用法: node skill-entry.js <命令> [参数...]                   ║
╠══════════════════════════════════════════════════════════════╣
║  命令:                                                       ║
║    auth       授权管理 (check/save/poll/clear)                ║
║    marketdata 实时行情查询                                    ║
║    ranklist   市场榜单查询                                    ║
║    watchlist  自选股管理 (list/add/remove)                    ║
║    financial  金融数据自然语言查询                            ║
║    stockselect 智能多指标选股                                 ║
║    backtest   策略回测                                        ║
║    research   研报搜索                                        ║
╠══════════════════════════════════════════════════════════════╣
║  示例:                                                       ║
║    node skill-entry.js auth save <API_KEY>                   ║
║    node skill-entry.js auth check                            ║
║    node skill-entry.js marketdata 贵州茅台 宁德时代           ║
║    node skill-entry.js ranklist --order-by=2 --limit=10      ║
║    node skill-entry.js watchlist list                        ║
║    node skill-entry.js financial "科大讯飞营业收入"            ║
║    node skill-entry.js research "新能源汽车"                  ║
║    node skill-entry.js backtest "涨幅超5%的股票"              ║
╚══════════════════════════════════════════════════════════════╝
`);
}

async function main() {
  const args = process.argv.slice(2);
  const cmd = args[0];
  const rest = args.slice(1);

  if (!cmd || cmd === "help" || cmd === "--help" || cmd === "-h") {
    printHelp();
    return;
  }

  try {
    switch (cmd) {
      case "auth":        await authMain(rest); break;
      case "marketdata":  await marketdataMain(rest); break;
      case "ranklist":    await ranklistMain(rest); break;
      case "watchlist":   await watchlistMain(rest); break;
      case "financial":   await financialMain(rest); break;
      case "stockselect": await stockselectMain(rest); break;
      case "backtest":    await backtestMain(rest); break;
      case "research":    await researchMain(rest); break;
      default:
        console.error(`未知命令: ${cmd}`);
        console.error("可用命令: auth, marketdata, ranklist, watchlist, financial, stockselect, backtest, research");
        process.exit(1);
    }
  } catch (e) {
    console.error(`\n✗ 错误: ${e.message}`);
    process.exit(1);
  }
}

if (require.main === module) {
  main().catch(e => { console.error(`\n✗ 错误: ${e.message}`); process.exit(1); });
}

module.exports = { main, callTool, loadApiKey, saveApiKey, clearAuth, resolveStockCode, findCodeByName, findNameByCode };