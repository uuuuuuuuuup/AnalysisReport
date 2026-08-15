/**
 * AI Agent 工具定义：7 个数据查询 Tool
 * 执行方式：回环调用本服务器现有代理路由（http://localhost:8888），100% 复用 cookie/防盗链逻辑
 */
import { tool } from 'ai';
import { z } from 'zod';

const LOOPBACK = 'http://localhost:8888';

// ---------- 回环请求 ----------
async function loopback(path: string, init?: RequestInit): Promise<any> {
  const signal = init?.signal
    ? AbortSignal.any([init.signal, AbortSignal.timeout(15000)])
    : AbortSignal.timeout(15000);
  const r = await fetch(LOOPBACK + path, { ...init, signal });
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new Error((data && data.error) ? String(data.error) : `HTTP ${r.status}`);
  return data;
}

const thsPost = (path: string, signal?: AbortSignal): Promise<any> => loopback(path, { method: 'POST', signal });

// ---------- 共享数据获取 ----------
type Account = { name: string; mid: string; fk: string };

async function listAccounts(signal?: AbortSignal): Promise<Account[]> {
  const resp = await thsPost('/api/caishen_fund/pc/account/v1/account_list', signal);
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
  execute: async (_args, options) => {
    try {
      const accounts = await listAccounts(options?.abortSignal);
      const rows: any[] = [];
      let totalAsset = 0, totalValue = 0, totalCash = 0;
      for (const a of accounts) {
        const resp = await thsPost('/api/caishen_fund/pc/asset/v1/stock_position' + posQuery(a), options?.abortSignal);
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
async function getPositionsFor(a: Account, signal?: AbortSignal): Promise<any[]> {
  const resp = await thsPost('/api/caishen_fund/pc/asset/v1/stock_position' + posQuery(a), signal);
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
  execute: async ({ account }, options) => {
    try {
      let accounts = await listAccounts(options?.abortSignal);
      if (account) accounts = accounts.filter(a => a.name.includes(account));
      const out: any[] = [];
      for (const a of accounts) {
        const positions = (await getPositionsFor(a, options?.abortSignal))
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
  execute: async ({ period }, options) => {
    try {
      const accounts = await listAccounts(options?.abortSignal);
      // 合并各账户 year_profit（date: YYYYMMDD, profit: 截至当日累计盈亏, asset: 当日资产）
      const map: Record<string, { profit: number; asset: number }> = {};
      for (const a of accounts) {
        const resp = await thsPost('/api/caishen_fund/pc/asset/v1/asset_trend' + posQuery(a) + '&fundid=&custid=', options?.abortSignal);
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
  execute: async ({ days }, options) => {
    try {
      const n = days || 30;
      // userid 通过回环 /api-check 获取（cookie 在服务端文件里，tools 不直接读）
      const check = await loopback('/api-check', { signal: options?.abortSignal });
      const uid = check?.userid || '';
      const accounts = await listAccounts(options?.abortSignal);
      const end = new Date();
      const start = new Date(Date.now() - n * 86400_000);
      const s = (d: Date) => d.toISOString().slice(0, 10).replace(/-/g, '');
      const out: any[] = [];
      for (const a of accounts) {
        const q = `?manual_id=${a.mid}&fund_key=${a.fk}&rzrq_fund_key=&fundid=&custid=&user_id=${uid}` +
          `&start_date=${s(start)}&end_date=${s(end)}&query_list=&page=1&count=20&sort_type=1&sort_order=1&h5id=`;
        const resp = await thsPost('/api/caishen_fund/pc/account/v2/get_money_history' + q, options?.abortSignal);
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
  execute: async ({ code }, options) => {
    try {
      const tc = tencentCode(code);
      const data = await loopback(`/proxy/kline?code=${tc}&count=120`, { signal: options?.abortSignal });
      const k = data?.data?.[tc];
      // qfqday 行结构: [date, open, close, high, low, volume]
      const rows = (k?.qfqday || k?.day || []);
      if (!rows.length) return { error: `无K线数据: ${code}` };
      const closes: number[] = rows.map((r: any) => +r[2]);
      const ma = (p: number): number | null =>
        closes.length >= p ? +(closes.slice(-p).reduce((a, b) => a + b, 0) / p).toFixed(3) : null;
      const last = rows[rows.length - 1], prev = rows[rows.length - 2];
      const close = +last[2], prevClose = prev ? +prev[2] : 0;
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
  execute: async ({ order, num }, options) => {
    try {
      const data = await loopback(`/proxy/moneyflow?order=${order || 'desc'}&num=${num || 10}`, { signal: options?.abortSignal });
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
  execute: async (_args, options) => {
    try {
      const sl = await thsPost('/api/caishen_fund/pc/optional/v1/sort_list?sort_rule=&sort_order=', options?.abortSignal);
      const items: any[] = ((sl?.ex_data?.list) || []).map((i: any) => ({
        code: i.code || '', name: i.name || '', market: i.market || '',
        price: parseFloat(i.price) || 0, rate: parseFloat(i.rate) || 0,
      }));
      let stats: any = {};
      // rise_fall 的 stock_code 参数是 market:code 形式（与前端一致）
      const codes = items.filter(i => i.market && i.code).map(i => `${i.market}:${i.code}`).join(',');
      if (codes) {
        const rf = await thsPost(`/api/caishen_fund/pc/optional/v1/rise_fall?stock_code=${codes}&fund_code=`, options?.abortSignal);
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
