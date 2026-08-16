/**
 * MCP Client 集成：连接外部 MCP Server（stdio 命令 / SSE URL），工具转为 AI SDK tool
 * 配置: ~/.tzzb_mcp_config.json（标准 mcpServers 格式）
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';
import { tool as aiTool, jsonSchema } from 'ai';

const CONFIG_FILE = path.join(os.homedir(), '.tzzb_mcp_config.json');
const CONNECT_TIMEOUT = 15_000;
const CALL_TIMEOUT = 30_000;
const RESULT_CAP = 50_000;

type ServerConfig = {
  type?: 'sse';
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
};

// ---------- 配置 ----------
function readConfig(): { mcpServers?: Record<string, ServerConfig> } {
  try { return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8')); } catch { return {}; }
}

export function validateMcpConfig(raw: any): string | null {
  if (!raw || typeof raw !== 'object' || !raw.mcpServers || typeof raw.mcpServers !== 'object')
    return '配置需为 {"mcpServers": {...}} 结构';
  for (const [name, cfg] of Object.entries(raw.mcpServers as Record<string, any>)) {
    if (!cfg || typeof cfg !== 'object') return `server ${name} 配置非法`;
    if (cfg.type === 'sse') { if (!cfg.url) return `server ${name} 缺少 url`; }
    else if (!cfg.command) return `server ${name} 缺少 command`;
  }
  return null;
}

export function saveMcpConfig(raw: any): { error?: string } {
  const err = validateMcpConfig(raw);
  if (err) return { error: err };
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(raw, null, 2));
  return {};
}

// ---------- 连接状态 ----------
type State = {
  name: string;
  type: 'stdio' | 'sse';
  status: 'idle' | 'connecting' | 'connected' | 'error';
  error?: string;
  toolNames: string[];
  client?: Client;
  transport?: any;
};

let states = new Map<string, State>();
let mcpTools: Record<string, any> = {};

function toAISDKTool(server: string, t: any) {
  const params = t.inputSchema && typeof t.inputSchema === 'object' && t.inputSchema.type === 'object'
    ? t.inputSchema : { type: 'object', properties: {} };
  return aiTool({
    description: `MCP 工具（来自 ${server}）: ${t.description || t.name}`,
    parameters: jsonSchema(params),
    execute: async (args: any, options: any) => {
      const st = states.get(server);
      if (!st?.client || st.status !== 'connected') return { error: `MCP server ${server} 未连接` };
      try {
        const res: any = await st.client.callTool(
          { name: t.name, arguments: args as Record<string, unknown> },
          undefined,
          { timeout: CALL_TIMEOUT, signal: options?.abortSignal },
        );
        const text = ((res.content || []).filter((c: any) => c.type === 'text').map((c: any) => c.text).join('\n') || '').slice(0, RESULT_CAP);
        return { server, tool: t.name, isError: !!res.isError, result: text || '(空输出)' };
      } catch (e: any) {
        return { error: `MCP 调用失败: ${e?.message || e}` };
      }
    },
  });
}

async function connectServer(name: string, cfg: ServerConfig): Promise<void> {
  const st: State = { name, type: cfg.type === 'sse' ? 'sse' : 'stdio', status: 'connecting', toolNames: [] };
  states.set(name, st);
  const client = new Client({ name: 'dianjin-dashboard', version: '1.0.0' });
  try {
    let transport;
    if (cfg.type === 'sse') {
      transport = new SSEClientTransport(new URL(cfg.url!), { requestInit: { headers: cfg.headers || {} } });
    } else {
      transport = new StdioClientTransport({ command: cfg.command!, args: cfg.args || [], env: { ...process.env, ...(cfg.env || {}) } as Record<string, string> });
    }
    await Promise.race([
      client.connect(transport),
      new Promise((_, reject) => setTimeout(() => reject(new Error(`连接超时 ${CONNECT_TIMEOUT / 1000}s`)), CONNECT_TIMEOUT)),
    ]);
    const res: any = await client.listTools();
    const tools: Record<string, any> = {};
    for (const t of res.tools || []) tools[`mcp__${name}__${t.name}`] = toAISDKTool(name, t);
    st.client = client;
    st.transport = transport;
    st.toolNames = Object.keys(tools);
    st.status = 'connected';
    st.error = undefined;
    mcpTools = { ...mcpTools, ...tools };
    console.log(`  🔌 MCP 已连接: ${name} (${Object.keys(tools).length} 个工具)`);
  } catch (e: any) {
    st.status = 'error';
    st.error = e?.message || String(e);
    try { await client.close(); } catch { /* 忽略关闭失败 */ }
    console.error(`  ✗ MCP 连接失败: ${name} - ${st.error}`);
  }
}

// 懒连接：只连接尚未连接的 server；失败不抛出（标记状态，不阻塞对话）
export async function ensureMcpConnected(): Promise<void> {
  const { mcpServers } = readConfig();
  const entries = Object.entries(mcpServers || {});
  if (!entries.length) return;
  await Promise.all(entries.filter(([n]) => !states.has(n)).map(([n, cfg]) => connectServer(n, cfg)));
}

export async function reloadMcp(): Promise<void> {
  for (const st of states.values()) { try { await st.client?.close(); } catch { /* 忽略 */ } }
  states = new Map();
  mcpTools = {};
  await ensureMcpConnected();
}

export function getMcpStatus(): { servers: any[]; configured: Record<string, ServerConfig> } {
  const { mcpServers } = readConfig();
  const servers = Object.entries(mcpServers || {}).map(([name, cfg]) => {
    const st = states.get(name);
    return {
      name,
      type: cfg.type === 'sse' ? 'sse' : 'stdio',
      status: st?.status || 'idle',
      error: st?.error || '',
      toolCount: st?.toolNames.length || 0,
      tools: st?.toolNames || [],
    };
  });
  return { servers, configured: mcpServers || {} };
}

export function getMcpTools(): Record<string, any> {
  return mcpTools;
}
