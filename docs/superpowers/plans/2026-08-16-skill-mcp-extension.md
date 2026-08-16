# 点金 Skill 与 MCP 功能扩展 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为点金 AI 助手（code/dashboard）增加 Skill 系统（工具触发式加载 + 脚本执行）与 MCP Client 集成（stdio/SSE），并提供设置抽屉管理面板。

**Architecture:** 单进程集成。新增 `skills.ts`（skill 存储 CRUD + `use_skill`/`run_skill_script` 两个 AI 工具）与 `mcp.ts`（MCP 懒连接 + 工具转换），`server.ts` 动态合并工具与注入 system prompt，前端 ai.html 新增设置抽屉（技能/MCP 两个 tab）。

**Tech Stack:** Node 22 + tsx、AI SDK v4（ai + @ai-sdk/deepseek + zod 3）、@modelcontextprotocol/sdk（新增依赖）、原生 http/fs/child_process、系统 unzip。

**Spec:** `docs/superpowers/specs/2026-08-16-skill-mcp-extension-design.md`

**验证策略说明：** 本项目无测试框架（package.json 无 test script），且按用户约定测试代码不提交。各任务验证方式：
- 模块级：`npx tsx -e "<inline script>"` 直接调用模块函数（不落盘、不提交）
- 集成级：`npm run typecheck` + 启动服务 curl 验证 + 浏览器手测清单
- 每任务以 git commit 收尾

**约定：** 所有命令在 `/Users/apple/Documents/分析报告/code/dashboard` 目录执行。服务地址 `http://localhost:8888`。

---

### Task 1: 安装 MCP SDK 依赖

**Files:**
- Modify: `package.json`

- [ ] **Step 1: 安装 @modelcontextprotocol/sdk**

Run: `npm install @modelcontextprotocol/sdk`

Expected: 安装成功，`package.json` 的 dependencies 新增 `"@modelcontextprotocol/sdk": "^1.x"`（以实际安装版本为准）。

- [ ] **Step 2: 确认导入路径可用**

Run: `ls node_modules/@modelcontextprotocol/sdk/dist/esm/client/`

Expected: 存在 `index.js`、`stdio.js`、`sse.js`（本项目 type:module，走 esm 目录）。

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: 新增 @modelcontextprotocol/sdk 依赖（MCP Client 集成）"
```

---

### Task 2: skills.ts — 存储层（frontmatter 解析 / 扫描 / CRUD / 启用配置）

**Files:**
- Create: `skills.ts`

- [ ] **Step 1: 创建 skills.ts 存储层（不含工具与脚本执行）**

```ts
/**
 * Skill 系统：~/.tzzb_skills/<name>/SKILL.md + scripts/
 * 提供 skill 存储 CRUD、zip 导入；Agent 工具 use_skill / run_skill_script 见 Task 3
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const SKILLS_DIR = path.join(os.homedir(), '.tzzb_skills');
const CONFIG_FILE = path.join(os.homedir(), '.tzzb_skills_config.json');
const NAME_RE = /^[\w-]{1,50}$/;

export type ScriptInput = { filename: string; content: string };
export type SkillInput = { name: string; description: string; body: string; scripts?: ScriptInput[] };
export type SkillInfo = { name: string; description: string; enabled: boolean; scripts: string[] };

// ---------- frontmatter ----------
export function parseFrontmatter(md: string): { name: string; description: string; body: string } | null {
  const m = md.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return null;
  const fm: Record<string, string> = {};
  for (const line of m[1].split('\n')) {
    const kv = line.match(/^([\w-]+):\s*(.*)$/);
    if (kv) fm[kv[1]] = kv[2].trim();
  }
  return { name: fm.name || '', description: fm.description || '', body: m[2].trim() };
}

function buildFrontmatter(name: string, description: string): string {
  return `---\nname: ${name}\ndescription: ${description}\n---\n`;
}

// ---------- 启用配置 ----------
function loadConfig(): Record<string, boolean> {
  try { return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8')); } catch { return {}; }
}
function saveConfig(cfg: Record<string, boolean>): void {
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2));
}

function listScripts(dir: string): string[] {
  const scriptsDir = path.join(dir, 'scripts');
  return fs.existsSync(scriptsDir) ? fs.readdirSync(scriptsDir).filter(f => f !== '.DS_Store') : [];
}

// ---------- 查询 ----------
export function listSkills(): SkillInfo[] {
  if (!fs.existsSync(SKILLS_DIR)) return [];
  const cfg = loadConfig();
  return fs.readdirSync(SKILLS_DIR, { withFileTypes: true })
    .filter(d => d.isDirectory())
    .map(d => {
      const dir = path.join(SKILLS_DIR, d.name);
      let name = d.name, description = '';
      const mdPath = path.join(dir, 'SKILL.md');
      if (fs.existsSync(mdPath)) {
        const fm = parseFrontmatter(fs.readFileSync(mdPath, 'utf-8'));
        if (fm) { name = fm.name || name; description = fm.description; }
      }
      return { name, description, enabled: cfg[name] !== false, scripts: listScripts(dir) };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function getSkill(name: string): (SkillInfo & { body: string }) | null {
  if (!NAME_RE.test(name)) return null;
  const mdPath = path.join(SKILLS_DIR, name, 'SKILL.md');
  if (!fs.existsSync(mdPath)) return null;
  const fm = parseFrontmatter(fs.readFileSync(mdPath, 'utf-8'));
  if (!fm) return null;
  const info = listSkills().find(s => s.name === name);
  return { name, description: fm.description, body: fm.body, enabled: info?.enabled ?? true, scripts: info?.scripts ?? [] };
}

// ---------- 校验与写入 ----------
export function validateSkillInput(input: any): string | null {
  const name = String(input?.name || '').trim();
  if (!NAME_RE.test(name)) return '名称不合法：仅允许字母/数字/下划线/连字符，1-50 位';
  if (!String(input?.description || '').trim()) return '描述不能为空';
  const scripts: ScriptInput[] = Array.isArray(input?.scripts) ? input.scripts : [];
  if (scripts.some(s => !s || !/^[\w.-]+$/.test(String(s.filename || '')) || !String(s.filename).includes('.')))
    return '脚本文件名不合法：仅文件名（不含路径），需带扩展名 .py/.js/.sh';
  return null;
}

function writeSkill(input: SkillInput): void {
  const dir = path.join(SKILLS_DIR, input.name);
  fs.mkdirSync(path.join(dir, 'scripts'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'SKILL.md'), buildFrontmatter(input.name, input.description.trim()) + (input.body || '').trim() + '\n');
  const scriptsDir = path.join(dir, 'scripts');
  for (const f of fs.readdirSync(scriptsDir)) fs.rmSync(path.join(scriptsDir, f), { force: true });  // 脚本整体重写
  for (const s of input.scripts || []) fs.writeFileSync(path.join(scriptsDir, s.filename), s.content);
}

export function createSkill(input: SkillInput): { error?: string } {
  if (fs.existsSync(path.join(SKILLS_DIR, input.name))) return { error: `技能 ${input.name} 已存在` };
  writeSkill(input);
  return {};
}

export function updateSkill(input: SkillInput): { error?: string } {
  if (!fs.existsSync(path.join(SKILLS_DIR, input.name))) return { error: `技能 ${input.name} 不存在` };
  writeSkill(input);
  return {};
}

export function deleteSkill(name: string): void {
  fs.rmSync(path.join(SKILLS_DIR, name), { recursive: true, force: true });
  const cfg = loadConfig();
  delete cfg[name];
  saveConfig(cfg);
}

export function setEnabled(name: string, enabled: boolean): void {
  const cfg = loadConfig();
  cfg[name] = enabled;
  saveConfig(cfg);
}
```

- [ ] **Step 2: 内联验证存储层**

Run:
```bash
npx tsx -e "
import { createSkill, updateSkill, listSkills, getSkill, deleteSkill, setEnabled, validateSkillInput } from './skills';
console.log('validate bad:', validateSkillInput({ name: '../x', description: 'a' }));
console.log('create:', createSkill({ name: 'test-skill', description: '测试技能', body: '# 指引', scripts: [{ filename: 'hello.py', content: 'print(\"hi\")' }] }));
console.log('create dup:', createSkill({ name: 'test-skill', description: 'x', body: 'y' }));
console.log('list:', JSON.stringify(listSkills()));
console.log('get:', JSON.stringify(getSkill('test-skill')));
setEnabled('test-skill', false);
console.log('disabled:', JSON.stringify(listSkills()));
setEnabled('test-skill', true);
updateSkill({ name: 'test-skill', description: '更新后', body: '# 新指引', scripts: [] });
console.log('updated:', JSON.stringify(listSkills()));
deleteSkill('test-skill');
console.log('after delete:', JSON.stringify(listSkills()));
"
```

Expected: 依次输出 — validate bad 返回名称非法错误；create 返回 `{}`；create dup 返回 `{ error: '技能 test-skill 已存在' }`；list 含 test-skill 且 scripts 含 hello.py；get 的 body 为 `# 指引`；disabled 后 enabled=false；updated 后描述为「更新后」且 scripts 为空；after delete 后列表为空。验证后 `ls ~/.tzzb_skills` 确认无 test-skill 残留。

- [ ] **Step 3: Commit**

```bash
git add skills.ts
git commit -m "feat: skills.ts 存储层 - SKILL.md 解析/扫描/CRUD/启用配置"
```

---

### Task 3: skills.ts — 脚本执行、Agent 工具与 zip 导入

**Files:**
- Modify: `skills.ts`（在 Task 2 基础上追加）

- [ ] **Step 1: 追加脚本执行与工具定义**

在 `skills.ts` 文件末尾追加：

```ts
// ============ 脚本执行 + Agent 工具 ============
import { spawn } from 'node:child_process';
import { tool } from 'ai';
import { z } from 'zod';

const INTERPRETERS: Record<string, string> = { '.py': 'python3', '.js': 'node', '.mjs': 'node', '.cjs': 'node', '.sh': 'bash' };
const STDOUT_CAP = 50_000, STDERR_CAP = 5_000, SCRIPT_TIMEOUT = 30_000;

// 执行技能脚本：仅允许 skill 自己的 scripts/ 目录内文件，解释器按扩展名选择
export function runSkillScript(skill: string, script: string, args: string[]): Promise<any> {
  return new Promise((resolve) => {
    const scriptsDir = path.resolve(SKILLS_DIR, skill, 'scripts');
    const resolved = path.resolve(scriptsDir, script);
    if (!resolved.startsWith(scriptsDir + path.sep)) return resolve({ error: '非法脚本路径' });
    if (!fs.existsSync(resolved)) return resolve({ error: `脚本不存在: ${script}` });
    const interp = INTERPRETERS[path.extname(script).toLowerCase()];
    if (!interp) return resolve({ error: `不支持的脚本类型: ${path.extname(script)}` });
    const child = spawn(interp, [script, ...args], { cwd: scriptsDir, timeout: SCRIPT_TIMEOUT, killSignal: 'SIGKILL' });
    let stdout = '', stderr = '';
    child.stdout.on('data', c => { stdout = (stdout + c).slice(0, STDOUT_CAP); });
    child.stderr.on('data', c => { stderr = (stderr + c).slice(0, STDERR_CAP); });
    child.on('error', e => resolve({ error: `脚本执行失败: ${e.message}` }));
    child.on('close', (code, signal) => resolve({
      exit_code: code,
      signal: signal || undefined,
      timed_out: signal === 'SIGKILL',
      stdout: stdout || undefined,
      stderr: stderr || undefined,
    }));
  });
}

// 读取 skill 全部脚本内容（编辑表单回填用）
export function getSkillScriptContents(name: string): Record<string, string> {
  const dir = path.join(SKILLS_DIR, name, 'scripts');
  const out: Record<string, string> = {};
  if (!fs.existsSync(dir)) return out;
  for (const f of fs.readdirSync(dir)) {
    try { out[f] = fs.readFileSync(path.join(dir, f), 'utf-8'); } catch { /* 读不到留空 */ }
  }
  return out;
}

export const use_skill = tool({
  description: '加载指定技能的完整指引(SKILL.md)。当用户任务匹配某个已启用技能时,先调用本工具获取指引与用法,再严格按指引执行。',
  parameters: z.object({
    name: z.string().describe('技能名称,从 system prompt 的可用技能列表中选择'),
  }),
  execute: async ({ name }) => {
    const s = getSkill(name);
    if (!s) return { error: `技能不存在: ${name}` };
    return {
      name: s.name,
      description: s.description,
      guide: s.body,
      scripts: s.scripts.map(f => `${f}（${INTERPRETERS[path.extname(f).toLowerCase()] || '未知解释器'}）`),
      usage: '如需执行附带脚本,调用 run_skill_script 工具: skill=技能名, script=脚本文件名, args=命令行参数数组',
    };
  },
});

export const run_skill_script = tool({
  description: '执行某个技能附带的脚本(技能指引要求时使用)。返回 stdout/stderr/退出码;输出截断 50KB,超时 30 秒。',
  parameters: z.object({
    skill: z.string().describe('技能名称'),
    script: z.string().regex(/^[\w.-]+$/, '仅文件名,不含路径').describe('脚本文件名,如 fetch_pe.py'),
    args: z.array(z.string()).optional().describe('传给脚本的命令行参数,如 ["600519"]'),
  }),
  execute: async ({ skill, script, args }) => runSkillScript(skill, script, args || []),
});

export const SKILL_TOOL_LABELS: Record<string, string> = {
  use_skill: '技能指引',
  run_skill_script: '技能脚本',
};
```

- [ ] **Step 2: 追加 zip 导入函数**

继续追加到 `skills.ts`：

```ts
// ============ zip 导入（用系统 unzip，零新依赖） ============
// zip 结构要求：根下 <name>/SKILL.md（可选 scripts/），name 即技能名
export async function importSkillZip(buf: Buffer): Promise<{ error?: string; name?: string }> {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'tzzb_skill_'));
  const zipPath = path.join(tmpDir, 'upload.zip');
  fs.writeFileSync(zipPath, buf);
  try {
    await new Promise<void>((resolve, reject) => {
      const p = spawn('unzip', ['-o', '-q', zipPath, '-d', tmpDir]);
      p.on('error', reject);
      p.on('close', code => code === 0 ? resolve() : reject(new Error(`unzip 退出码 ${code}`)));
    });
    const tops = fs.readdirSync(tmpDir).filter(n => n !== 'upload.zip');
    const dir = tops.find(n => fs.statSync(path.join(tmpDir, n)).isDirectory() && fs.existsSync(path.join(tmpDir, n, 'SKILL.md')));
    if (!dir) return { error: 'zip 内未找到含 SKILL.md 的技能目录（结构应为 zip 根下 <名称>/SKILL.md）' };
    if (!NAME_RE.test(dir)) return { error: `目录名 ${dir} 不合法（仅字母/数字/_/-，1-50 位）` };
    const target = path.join(SKILLS_DIR, dir);
    if (fs.existsSync(target)) return { error: `技能 ${dir} 已存在` };
    fs.mkdirSync(SKILLS_DIR, { recursive: true });
    fs.renameSync(path.join(tmpDir, dir), target);
    return { name: dir };
  } catch (e: any) {
    return { error: '导入失败: ' + (e?.message || String(e)) };
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}
```

- [ ] **Step 3: 内联验证脚本执行**

Run:
```bash
npx tsx -e "
import { createSkill, deleteSkill, runSkillScript, use_skill } from './skills';
createSkill({ name: 'demo', description: '演示', body: '# demo', scripts: [
  { filename: 'calc.py', content: 'import sys; print(float(sys.argv[1]) * 2)' },
  { filename: 'calc.js', content: 'console.log(Number(process.argv[2]) * 3)' },
  { filename: 'calc.sh', content: 'echo \$((\$1 * 4))' },
  { filename: 'slow.py', content: 'import time; time.sleep(60)' },
]});
console.log('py:', JSON.stringify(await runSkillScript('demo', 'calc.py', ['21'])));
console.log('js:', JSON.stringify(await runSkillScript('demo', 'calc.js', ['21'])));
console.log('sh:', JSON.stringify(await runSkillScript('demo', 'calc.sh', ['21'])));
console.log('traversal:', JSON.stringify(await runSkillScript('demo', '../etc/passwd', [])));
console.log('unknown ext:', JSON.stringify(await runSkillScript('demo', 'calc.txt', [])));
console.log('timeout:', JSON.stringify(await runSkillScript('demo', 'slow.py', [])));
console.log('use_skill:', JSON.stringify(await use_skill.execute({ name: 'demo' }, { abortSignal: undefined })));
deleteSkill('demo');
"
```

Expected:
- py: `exit_code:0, stdout:"42"`（21×2）
- js: stdout `63`（21×3）
- sh: stdout `84`（21×4）
- traversal: `{ error: '非法脚本路径' }`
- unknown ext: `{ error: '不支持的脚本类型: .txt' }`
- timeout: `timed_out:true, signal:'SIGKILL'`（约 30 秒后返回）
- use_skill: 返回 `{ name:'demo', description:'演示', guide:'# demo', scripts:[...], usage:'...' }`

- [ ] **Step 4: 内联验证 zip 导入**

Run:
```bash
cd /tmp && rm -rf zipdemo && mkdir -p zipdemo/my-analyzer/scripts && printf -- '---\nname: my-analyzer\ndescription: 导入测试\n---\n\n# 导入的技能\n' > zipdemo/my-analyzer/SKILL.md && echo 'print(1+1)' > zipdemo/my-analyzer/scripts/x.py && zip -qr /tmp/demo-skill.zip zipdemo && cd /Users/apple/Documents/分析报告/code/dashboard && npx tsx -e "
import { importSkillZip, listSkills, deleteSkill } from './skills';
import fs from 'node:fs';
console.log('import:', await importSkillZip(fs.readFileSync('/tmp/demo-skill.zip')));
console.log('list:', JSON.stringify(listSkills()));
deleteSkill('my-analyzer');
console.log('cleaned');
"
```

Expected: import 返回 `{ name: 'my-analyzer' }`；list 含 my-analyzer（scripts: ['x.py']）。

- [ ] **Step 5: typecheck**

Run: `npm run typecheck`

Expected: 无错误。

- [ ] **Step 6: Commit**

```bash
git add skills.ts
git commit -m "feat: skills.ts 脚本执行 + use_skill/run_skill_script 工具 + zip 导入"
```

---

### Task 4: mcp.ts — 配置读写、懒连接与工具转换

**Files:**
- Create: `mcp.ts`

- [ ] **Step 1: 创建 mcp.ts**

```ts
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
      transport = new StdioClientTransport({ command: cfg.command!, args: cfg.args || [], env: { ...process.env, ...(cfg.env || {}) } });
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
```

- [ ] **Step 2: typecheck**

Run: `npm run typecheck`

Expected: 无错误。（若 MCP SDK 类型与 AI SDK 不兼容报错，按报错修 `toAISDKTool` 参数类型，不改行为。）

- [ ] **Step 3: 内联验证（连接本机 AI Tools MCP）**

先检查用户是否已有配置（有则备份，测后还原）：
```bash
[ -f ~/.tzzb_mcp_config.json ] && cp ~/.tzzb_mcp_config.json /tmp/tzzb_mcp_config_backup.json
cat > ~/.tzzb_mcp_config.json <<'EOF'
{"mcpServers": {"AI Tools": {"command": "node", "args": ["/Users/apple/Documents/code/AI-Tools/mcp-server/index.js"], "env": {"AI_TOOLS_BASE_URL": "http://localhost:8080"}}}}
EOF
```

Run:
```bash
npx tsx -e "
import { ensureMcpConnected, getMcpStatus, getMcpTools, reloadMcp } from './mcp';
await ensureMcpConnected();
console.log('status:', JSON.stringify(getMcpStatus().servers, null, 2));
console.log('tool count:', Object.keys(getMcpTools()).length);
const [toolName, t] = Object.entries(getMcpTools())[0];
console.log('first tool:', toolName);
console.log('execute:', JSON.stringify(await t.execute({}, { abortSignal: undefined })).slice(0, 300));
await reloadMcp();
console.log('reloaded status:', JSON.stringify(getMcpStatus().servers.map(s => s.status)));
"
```

Expected:
- status 中 AI Tools 为 `connected`（若 AI_TOOLS_BASE_URL 指向的服务未启动则为 `error` 并带错误信息——两种结果都算通过，error 需含原因而非崩溃）
- tool count > 0（连接成功时）
- first tool 名以 `mcp__AI Tools__` 开头
- execute 返回 MCP 调用结果对象
- 若连接成功：reloaded 后 status 仍为 connected；若失败：整个脚本不崩溃

验证后还原配置：
```bash
[ -f /tmp/tzzb_mcp_config_backup.json ] && mv /tmp/tzzb_mcp_config_backup.json ~/.tzzb_mcp_config.json || rm ~/.tzzb_mcp_config.json
```

- [ ] **Step 4: 负面验证（坏配置不崩溃）**

Run:
```bash
echo '{"mcpServers": {"bad": {"command": "/nonexistent/cmd"}}}' > ~/.tzzb_mcp_config.json && npx tsx -e "
import { ensureMcpConnected, getMcpStatus, validateMcpConfig } from './mcp';
console.log('validate missing url:', validateMcpConfig({ mcpServers: { x: { type: 'sse' } } }));
await ensureMcpConnected();
console.log('status:', JSON.stringify(getMcpStatus().servers));
" ; rm ~/.tzzb_mcp_config.json
```

Expected: validate 返回 `server x 缺少 url`；status 为 `error` 且含 spawn 错误信息；脚本正常退出（不崩溃、不挂起）。

- [ ] **Step 5: Commit**

```bash
git add mcp.ts
git commit -m "feat: mcp.ts MCP Client 集成 - stdio/SSE 懒连接、工具转换、状态管理"
```

---

### Task 5: server.ts — 动态工具合并、system prompt 注入与新路由

**Files:**
- Modify: `server.ts`

- [ ] **Step 1: 追加 import 与动态构建函数**

在 `server.ts` 第 20 行 `import { ALL_TOOLS, TOOL_LABELS } from './tools';` 之后追加：

```ts
import { use_skill, run_skill_script, SKILL_TOOL_LABELS, listSkills, getSkill, getSkillScriptContents, createSkill, updateSkill, deleteSkill, setEnabled, validateSkillInput, importSkillZip, type SkillInput } from './skills';
import { ensureMcpConnected, getMcpTools, getMcpStatus, saveMcpConfig, reloadMcp } from './mcp';
```

在 `SYSTEM_PROMPT` 常量定义之后（第 97 行之后）追加：

```ts
// system prompt 动态注入启用 skill 列表
function buildSystemPrompt(): string {
  const skills = listSkills().filter(s => s.enabled);
  if (!skills.length) return SYSTEM_PROMPT;
  const lines = skills.map(s => `- ${s.name}: ${s.description || '(无描述)'}`).join('\n');
  return SYSTEM_PROMPT + `\n\n## 可用技能\n以下技能已启用。当任务匹配技能用途时，先调用 use_skill 加载其完整指引，再按指引执行：\n${lines}`;
}

// 动态工具集：内置 7 + skill 2 + MCP 工具
function buildTools(): Record<string, CoreTool> {
  return {
    ...(ALL_TOOLS as unknown as Record<string, CoreTool>),
    use_skill,
    run_skill_script,
    ...getMcpTools(),
  };
}

// status 事件文案：原有工具保持不变，skill/MCP 按 spec 措辞
function toolStatusText(tc: any): string {
  const input = tc.input as any;
  if (tc.toolName === 'use_skill') return `正在加载技能 ${input?.name || ''}…`;
  if (tc.toolName === 'run_skill_script') return `正在执行技能脚本 ${input?.script || ''}…`;
  if (tc.toolName.startsWith('mcp__')) return `正在调用 MCP 工具 ${tc.toolName.split('__')[2] || ''}…`;
  return `正在查询${TOOL_LABELS[tc.toolName] || tc.toolName}…`;
}
```

- [ ] **Step 2: 修改 runAgentStream**

在 `runAgentStream` 函数体内（约 578-635 行）做两处替换：

第一处 — 在 `try {` 之前（streamText 调用之前）插入 MCP 懒连接，并把 `system: SYSTEM_PROMPT` 与 `tools: toolsEnabled ? ...` 改为动态版本：

原：
```ts
  try {
    const result = streamText({
      model: modelProvider(AI_MODEL),
      system: SYSTEM_PROMPT,
      messages: session.messages,
      tools: toolsEnabled ? (ALL_TOOLS as unknown as Record<string, CoreTool>) : {},
```
改为：
```ts
  // MCP 懒连接（失败不阻塞对话，状态经 /api/mcp 查询）
  await ensureMcpConnected();

  try {
    const result = streamText({
      model: modelProvider(AI_MODEL),
      system: buildSystemPrompt(),
      messages: session.messages,
      tools: toolsEnabled ? buildTools() : {},
```

第二处 — status 事件文案。用 `grep -n "TOOL_LABELS\[tc.toolName\]" server.ts` 定位所在行，把：
```ts
          sendEvent(res, 'status', { content: `正在查询${TOOL_LABELS[tc.toolName] || tc.toolName}…` });
```
改为：
```ts
          sendEvent(res, 'status', { content: toolStatusText(tc) });
```

- [ ] **Step 3: 追加 skills/mcp REST handlers**

在 `handleAgentRegenerate` 函数之后、`const server = http.createServer(...)` 之前追加（`IncomingMessage`/`ServerResponse`/`readJsonBody`/`readCookie`/`sendEvent` 均已存在于本文件）：

```ts
// ===== Skill / MCP 管理 API =====
async function handleSkillsList(req: IncomingMessage, res: ServerResponse, url: URL): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  const detail = url.searchParams.get('detail');
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  if (detail) {
    const s = getSkill(detail);
    if (!s) { res.end(JSON.stringify({ skill: null })); return; }
    res.end(JSON.stringify({ skill: { name: s.name, description: s.description, body: s.body, enabled: s.enabled, scripts: s.scripts, scriptContents: getSkillScriptContents(detail) } }));
    return;
  }
  res.end(JSON.stringify({ skills: listSkills() }));
}

async function handleSkillCreate(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  let body: any;
  try { body = await readJsonBody(req); } catch { body = {}; }
  const err = validateSkillInput(body);
  if (err) { res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: err })); return; }
  const input: SkillInput = { name: String(body.name).trim(), description: String(body.description).trim(), body: String(body.body || ''), scripts: body.scripts || [] };
  const r = createSkill(input);
  if (r.error) { res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: r.error })); return; }
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true }));
}

async function handleSkillUpdate(req: IncomingMessage, res: ServerResponse, name: string): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  let body: any;
  try { body = await readJsonBody(req); } catch { body = {}; }
  const err = validateSkillInput({ ...body, name });
  if (err) { res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: err })); return; }
  const input: SkillInput = { name, description: String(body.description).trim(), body: String(body.body || ''), scripts: body.scripts || [] };
  const r = updateSkill(input);
  if (r.error) { res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: r.error })); return; }
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true }));
}

async function handleSkillDelete(req: IncomingMessage, res: ServerResponse, name: string): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  deleteSkill(name);
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true }));
}

async function handleSkillToggle(req: IncomingMessage, res: ServerResponse, name: string): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  let body: any;
  try { body = await readJsonBody(req); } catch { body = {}; }
  setEnabled(name, !!body.enabled);
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true }));
}

// zip 上传：body 为原始 zip 二进制
async function handleSkillUpload(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  const chunks: Buffer[] = [];
  req.on('data', c => chunks.push(c as Buffer));
  req.on('end', async () => {
    const r = await importSkillZip(Buffer.concat(chunks));
    if (r.error) { res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: r.error })); return; }
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ ok: true, name: r.name }));
  });
}

async function handleMcpGet(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(getMcpStatus()));
}

async function handleMcpPut(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  let body: any;
  try { body = await readJsonBody(req); } catch { body = {}; }
  const r = saveMcpConfig(body);
  if (r.error) { res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: r.error })); return; }
  await reloadMcp();
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ ok: true, ...getMcpStatus() }));
}

async function handleMcpReload(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (!readCookie()) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ error: 'No cookie' })); return; }
  await reloadMcp();
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(getMcpStatus()));
}
```

- [ ] **Step 4: 注册路由**

在 `server.ts` 的路由区，`/api/agent/regenerate` 判断之后、`// API proxy` 之前插入：

```ts
  // ===== Skill / MCP 管理路由（必须在 /api/ 通用代理之前） =====
  if (pathname === '/api/skills' && method === 'GET') return handleSkillsList(req, res, url);
  if (pathname === '/api/skills/upload' && method === 'POST') return handleSkillUpload(req, res);
  if (pathname === '/api/skills' && method === 'POST') return handleSkillCreate(req, res);
  if (pathname.startsWith('/api/skills/') && method === 'PUT') return handleSkillUpdate(req, res, decodeURIComponent(pathname.split('/')[3] || ''));
  if (pathname.startsWith('/api/skills/') && method === 'DELETE') return handleSkillDelete(req, res, decodeURIComponent(pathname.split('/')[3] || ''));
  if (pathname.endsWith('/toggle') && method === 'PATCH') return handleSkillToggle(req, res, decodeURIComponent(pathname.split('/')[3] || ''));
  if (pathname === '/api/mcp' && method === 'GET') return handleMcpGet(req, res);
  if (pathname === '/api/mcp' && method === 'PUT') return handleMcpPut(req, res);
  if (pathname === '/api/mcp/reload' && method === 'POST') return handleMcpReload(req, res);
```

注意：`pathname.startsWith('/api/skills/')` 会匹配 `/api/skills/upload`，故 upload 判断必须在其之前（上面顺序已保证）。

- [ ] **Step 5: typecheck**

Run: `npm run typecheck`

Expected: 无错误。

- [ ] **Step 6: 启动服务并 curl 验证 CRUD**

Run（后台启动）: `npm start`

再开一个终端执行：
```bash
# 创建
curl -s -X POST http://localhost:8888/api/skills -H 'Content-Type: application/json' -d '{"name":"curl-demo","description":"curl 测试","body":"# 指引","scripts":[{"filename":"a.py","content":"print(\"ok\")"}]}'
# 期望 {"ok":true}
curl -s http://localhost:8888/api/skills
# 期望列表含 curl-demo
curl -s "http://localhost:8888/api/skills?detail=curl-demo"
# 期望 {"skill":{"name":"curl-demo",...,"scriptContents":{"a.py":"print(\"ok\")"}}}
curl -s -X PATCH http://localhost:8888/api/skills/curl-demo/toggle -H 'Content-Type: application/json' -d '{"enabled":false}'
# 期望 {"ok":true}；再 GET 确认 enabled=false
curl -s -X PUT http://localhost:8888/api/skills/curl-demo -H 'Content-Type: application/json' -d '{"description":"改","body":"# 新","scripts":[]}'
# 期望 {"ok":true}
curl -s -X DELETE http://localhost:8888/api/skills/curl-demo
# 期望 {"ok":true}
curl -s http://localhost:8888/api/mcp
# 期望 {"servers":[],"configured":{}}
curl -s -X PUT http://localhost:8888/api/mcp -H 'Content-Type: application/json' -d '{"mcpServers": {}}'
# 期望 {"ok":true,...}
curl -s -X POST http://localhost:8888/api/mcp/reload
# 期望 {"servers":[],"configured":{}}
```

Expected: 输出与各注释一致。另验证错误路径：`curl -s -X POST http://localhost:8888/api/skills -d '{"name":"bad name!"}'` 应返回 400 与名称不合法错误。

- [ ] **Step 7: 验证对话可用 MCP 工具（真实 AI Tools 配置）**

写回测试配置（与 Task 4 Step 3 相同内容）：
```bash
cat > ~/.tzzb_mcp_config.json <<'EOF'
{"mcpServers": {"AI Tools": {"command": "node", "args": ["/Users/apple/Documents/code/AI-Tools/mcp-server/index.js"], "env": {"AI_TOOLS_BASE_URL": "http://localhost:8080"}}}}
EOF
```

重启服务（`Ctrl-C` 后 `npm start`），观察启动日志，然后浏览器打开 `http://localhost:8888/ai` 发消息「用 MCP 工具查一下今天的市场热点新闻」。Expected: 服务端日志出现 `🔌 MCP 已连接: AI Tools (...)`；对话中 status 事件显示「正在调用 MCP 工具 …」；模型能调用 MCP 工具返回数据。（若 AI Tools 后端未运行则跳过此步，改为确认日志出现 `✗ MCP 连接失败` 且对话仍正常。）

- [ ] **Step 8: Commit**

```bash
git add server.ts
git commit -m "feat: server.ts 集成 Skill/MCP - 动态工具合并、system prompt 注入、管理路由"
```

---

### Task 6: ai.html + ai.css — 设置抽屉结构与样式

**Files:**
- Modify: `ai.html`
- Modify: `ai.css`

- [ ] **Step 1: ai.html 加入设置面板结构**

在 `ai.html` 中 `id="banner"` 的 div 之后、`<script src="/ai.js"></script>` 之前插入：

```html
  <!-- 设置面板（技能 / MCP 管理） -->
  <div class="settings-overlay hidden" id="settings-overlay"></div>
  <aside class="settings-panel hidden" id="settings-panel">
    <div class="settings-header">
      <div class="settings-tabs">
        <button class="settings-tab active" data-tab="skills">技能</button>
        <button class="settings-tab" data-tab="mcp">MCP 工具</button>
      </div>
      <button class="icon-btn" id="settings-close" title="关闭">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </div>
    <div class="settings-body">
      <!-- 技能页 -->
      <div class="settings-page" id="page-skills">
        <div class="page-actions">
          <button class="btn-primary" id="skill-new">＋ 新建技能</button>
          <button class="btn-ghost" id="skill-upload">导入 zip</button>
          <input type="file" id="skill-zip-input" accept=".zip" hidden>
        </div>
        <div class="skill-list" id="skill-list"></div>
        <form class="skill-form hidden" id="skill-form">
          <h3 id="skill-form-title">新建技能</h3>
          <label>名称<input id="skill-name" placeholder="如 valuation-analysis（字母/数字/_/-）" required></label>
          <label>描述<input id="skill-desc" placeholder="一句话说明技能用途" required></label>
          <label>正文指引<textarea id="skill-body" rows="10" placeholder="技能指引内容（Markdown）"></textarea></label>
          <div class="skill-scripts">
            <div class="skill-scripts-head">
              <span>附带脚本（可选，按扩展名选择解释器：.py→python3 / .js→node / .sh→bash）</span>
              <button type="button" class="btn-ghost" id="skill-add-script">＋ 添加脚本</button>
            </div>
            <div id="skill-script-list"></div>
          </div>
          <div class="form-actions">
            <button type="button" class="btn-ghost" id="skill-form-cancel">取消</button>
            <button type="submit" class="btn-primary">保存</button>
          </div>
        </form>
      </div>
      <!-- MCP 页 -->
      <div class="settings-page hidden" id="page-mcp">
        <p class="page-hint">配置外部 MCP Server（stdio 命令 / SSE URL），其工具自动进入点金可用工具集，保存后立即重连</p>
        <textarea id="mcp-config" rows="16" spellcheck="false" placeholder='{"mcpServers": {}}'></textarea>
        <div class="page-actions">
          <button class="btn-primary" id="mcp-save">保存并重连</button>
          <button class="btn-ghost" id="mcp-reload">重连</button>
        </div>
        <div class="mcp-server-list" id="mcp-server-list"></div>
      </div>
    </div>
  </aside>
```

同时把设置按钮（`id="settings-btn"`）的 title 从 `title="设置（下期）"` 改为 `title="设置"`。

- [ ] **Step 2: ai.css 追加设置面板样式**

在 `ai.css` 末尾追加（复用现有 CSS 变量）：

```css
/* ---------- 设置面板 ---------- */
.settings-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 90;
}
.settings-panel {
  position: fixed; top: 0; right: 0; bottom: 0; width: 420px; max-width: 92vw;
  background: var(--bg-surface); border-left: 1px solid var(--border);
  z-index: 91; display: flex; flex-direction: column;
  transform: translateX(0); transition: transform 250ms ease;
}
.settings-panel.hidden { transform: translateX(100%); }
.settings-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.settings-tabs { display: flex; gap: 4px; }
.settings-tab {
  background: transparent; border: none; color: var(--text-3);
  font-size: 14px; padding: 6px 14px; border-radius: 8px;
}
.settings-tab:hover { color: var(--text-1); background: var(--bg-strong); }
.settings-tab.active { color: var(--nav-accent); background: var(--bg-strong); }
.settings-body { flex: 1; overflow-y: auto; padding: 16px; }
.page-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.btn-primary {
  background: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.4);
  color: var(--warn); padding: 6px 14px; border-radius: 8px; font-size: 13px;
}
.btn-primary:hover { background: rgba(245,158,11,0.25); }
.btn-ghost {
  background: var(--bg-input); border: 1px solid var(--border);
  color: var(--text-2); padding: 6px 14px; border-radius: 8px; font-size: 13px;
}
.btn-ghost:hover { border-color: var(--border-hover); color: var(--text-1); }
.page-hint { color: var(--text-3); font-size: 12.5px; margin-bottom: 10px; }

/* 技能列表 */
.skill-item {
  display: flex; align-items: center; gap: 10px;
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: 10px; padding: 10px 12px; margin-bottom: 8px;
}
.skill-item-main { flex: 1; min-width: 0; }
.skill-item-name { font-weight: 600; font-size: 13.5px; }
.skill-item-desc {
  color: var(--text-3); font-size: 12px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; margin-top: 2px;
}
.skill-item-meta { color: var(--text-4); font-size: 11px; margin-top: 2px; }
.skill-item-actions { display: flex; gap: 6px; flex-shrink: 0; }
.mini-btn {
  background: transparent; border: 1px solid var(--border); color: var(--text-3);
  border-radius: 6px; padding: 3px 8px; font-size: 12px;
}
.mini-btn:hover { border-color: var(--border-hover); color: var(--text-1); }
.mini-btn.danger:hover { border-color: var(--danger); color: var(--danger); }

/* 开关 */
.switch { position: relative; width: 34px; height: 20px; flex-shrink: 0; }
.switch input { opacity: 0; width: 0; height: 0; }
.switch .slider {
  position: absolute; inset: 0; background: var(--bg-strong);
  border: 1px solid var(--border-hover); border-radius: 10px; cursor: pointer;
  transition: background 150ms;
}
.switch .slider::before {
  content: ''; position: absolute; width: 12px; height: 12px;
  left: 3px; top: 3px; background: var(--text-3); border-radius: 50%; transition: 150ms;
}
.switch input:checked + .slider { background: rgba(245,158,11,0.35); border-color: rgba(245,158,11,0.5); }
.switch input:checked + .slider::before { transform: translateX(14px); background: var(--warn); }

/* 表单 */
.skill-form {
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px; margin-top: 8px;
}
.skill-form h3 { font-size: 14px; margin-bottom: 10px; }
.skill-form label {
  display: block; font-size: 12px; color: var(--text-3); margin-bottom: 10px;
}
.skill-form input, .skill-form textarea, #mcp-config {
  width: 100%; background: var(--bg-page); border: 1px solid var(--border);
  border-radius: 8px; color: var(--text-1); font-size: 13px;
  padding: 8px 10px; margin-top: 4px; font-family: inherit; resize: vertical;
}
.skill-form input:focus, .skill-form textarea:focus, #mcp-config:focus {
  outline: none; border-color: var(--border-hover);
}
.skill-scripts { margin-bottom: 10px; }
.skill-scripts-head {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px; color: var(--text-3); margin-bottom: 6px; gap: 8px;
}
.script-row {
  display: flex; gap: 8px; align-items: flex-start; margin-bottom: 8px;
}
.script-row .script-filename { flex: 0 0 40%; }
.script-row .script-content { flex: 1; }
.script-row textarea { min-height: 70px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; }

/* MCP 状态列表 */
#mcp-config {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
}
.mcp-server-list { margin-top: 14px; }
.mcp-server-item {
  display: flex; align-items: center; gap: 10px;
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: 10px; padding: 10px 12px; margin-bottom: 8px;
}
.mcp-server-main { flex: 1; min-width: 0; }
.mcp-server-name { font-weight: 600; font-size: 13.5px; }
.mcp-server-error {
  color: var(--danger); font-size: 12px; margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-dot.connected { background: var(--ok); }
.status-dot.error { background: var(--danger); }
.status-dot.idle { background: var(--text-4); }
.status-dot.connecting { background: var(--warn); }
.mcp-server-tools { color: var(--text-4); font-size: 11px; margin-top: 2px; }
```

- [ ] **Step 3: 浏览器验证结构**

Run: 确保服务在跑（Task 5 已启动），浏览器打开 `http://localhost:8888/ai`，控制台执行 `$('#settings-panel').classList.remove('hidden'); $('#settings-overlay').classList.remove('hidden')`。

Expected: 右侧滑出 420px 深色抽屉，含「技能 / MCP 工具」tab、新建按钮、MCP 页 textarea 与按钮；样式与整体深色主题一致。`$('#settings-panel').classList.add('hidden')` 可收起。

- [ ] **Step 4: Commit**

```bash
git add ai.html ai.css
git commit -m "feat: 设置抽屉面板结构与样式（技能/MCP 两个 tab）"
```

---

### Task 7: ai.js — 面板交互与 API 调用

**Files:**
- Modify: `ai.js`

- [ ] **Step 1: ai.js 追加设置面板逻辑**

在 `ai.js` 的 `toggleSidebar` 函数之后、`// ---------- 初始化 ----------` 之前追加（`showToast`/`escapeHtml`/`$` 均为本文件已有）：

```js
// ---------- 设置面板：技能 / MCP ----------
const settingsState = { editing: null };  // editing: null=新建 | skill 名=编辑

function openSettings() {
  $('#settings-overlay').classList.remove('hidden');
  $('#settings-panel').classList.remove('hidden');
  loadSkills();
  loadMcp();
}
function closeSettings() {
  $('#settings-overlay').classList.add('hidden');
  $('#settings-panel').classList.add('hidden');
  $('#skill-form').classList.add('hidden');
  $('#skill-list').classList.remove('hidden');
}

async function apiJSON(url, options) {
  const r = await fetch(url, options);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
  return data;
}

// ---------- 技能 ----------
async function loadSkills() {
  try {
    const data = await apiJSON('/api/skills');
    renderSkillList(data.skills || []);
  } catch (e) { renderSkillList([]); showToast('技能列表加载失败：' + e.message); }
}
function renderSkillList(skills) {
  const box = $('#skill-list');
  if (!skills.length) {
    box.innerHTML = '<p class="page-hint">暂无技能。点击「新建技能」创建，或「导入 zip」批量导入。</p>'
      + '<button class="btn-ghost" onclick="createExampleSkill()">创建示例：估值分析</button>';
    return;
  }
  box.innerHTML = skills.map(s => `
    <div class="skill-item">
      <div class="skill-item-main">
        <div class="skill-item-name">${escapeHtml(s.name)}</div>
        <div class="skill-item-desc">${escapeHtml(s.description || '(无描述)')}</div>
        <div class="skill-item-meta">${s.scripts.length ? '脚本: ' + s.scripts.map(escapeHtml).join(', ') : '无脚本'}</div>
      </div>
      <label class="switch" title="启用/禁用">
        <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="toggleSkill('${escapeHtml(s.name)}', this.checked)">
        <span class="slider"></span>
      </label>
      <div class="skill-item-actions">
        <button class="mini-btn" onclick="editSkill('${escapeHtml(s.name)}')">编辑</button>
        <button class="mini-btn danger" onclick="removeSkill('${escapeHtml(s.name)}')">删除</button>
      </div>
    </div>`).join('');
}
async function createExampleSkill() {
  try {
    await apiJSON('/api/skills', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'valuation-analysis',
        description: '个股估值分析：计算 PE/PB/股息率等指标并与行业对比，给出综合估值判断',
        body: '# 估值分析\n\n对指定股票进行估值分析：\n1. 调用内置工具获取财务指标与行情\n2. 计算 PE/PB/股息率等估值指标\n3. 与行业水平对比，给出估值结论与风险提示',
        scripts: [],
      }),
    });
    showToast('已创建示例技能');
    loadSkills();
  } catch (e) { showToast('创建失败：' + e.message); }
}
async function toggleSkill(name, enabled) {
  try {
    await apiJSON('/api/skills/' + encodeURIComponent(name) + '/toggle', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) });
    showToast(enabled ? '已启用 ' + name : '已禁用 ' + name);
  } catch (e) { showToast('操作失败：' + e.message); loadSkills(); }
}
async function removeSkill(name) {
  if (!confirm('删除技能 ' + name + '？将同时删除其脚本，不可恢复。')) return;
  try { await apiJSON('/api/skills/' + encodeURIComponent(name), { method: 'DELETE' }); showToast('已删除 ' + name); loadSkills(); }
  catch (e) { showToast('删除失败：' + e.message); }
}
function openSkillForm() {
  settingsState.editing = null;
  $('#skill-form-title').textContent = '新建技能';
  $('#skill-name').value = '';
  $('#skill-name').disabled = false;
  $('#skill-desc').value = '';
  $('#skill-body').value = '';
  $('#skill-script-list').innerHTML = '';
  addScriptRow('', '');
  $('#skill-list').classList.add('hidden');
  $('#skill-form').classList.remove('hidden');
}
async function editSkill(name) {
  try {
    const data = await apiJSON('/api/skills?detail=' + encodeURIComponent(name));
    if (!data.skill) throw new Error('技能不存在');
    const s = data.skill;
    settingsState.editing = name;
    $('#skill-form-title').textContent = '编辑技能：' + name;
    $('#skill-name').value = name;
    $('#skill-name').disabled = true;  // 名称即目录名，编辑时不改
    $('#skill-desc').value = s.description || '';
    $('#skill-body').value = s.body || '';
    $('#skill-script-list').innerHTML = '';
    const names = s.scripts || [];
    names.forEach(f => addScriptRow(f, (s.scriptContents || {})[f] || ''));
    if (!names.length) addScriptRow('', '');
    $('#skill-list').classList.add('hidden');
    $('#skill-form').classList.remove('hidden');
  } catch (e) { showToast('加载技能详情失败：' + e.message); }
}
function addScriptRow(filename, content) {
  const row = document.createElement('div');
  row.className = 'script-row';
  row.innerHTML = `
    <input class="script-filename" placeholder="如 fetch_pe.py" value="${escapeHtml(filename || '')}">
    <textarea class="script-content" placeholder="脚本内容">${escapeHtml(content || '')}</textarea>
    <button type="button" class="mini-btn danger" title="移除脚本">×</button>`;
  row.querySelector('button').onclick = () => row.remove();
  $('#skill-script-list').appendChild(row);
}
function collectScripts() {
  return [...document.querySelectorAll('#skill-script-list .script-row')]
    .map(row => ({ filename: row.querySelector('.script-filename').value.trim(), content: row.querySelector('.script-content').value }))
    .filter(s => s.filename);
}
async function submitSkill(e) {
  e.preventDefault();
  const body = {
    name: $('#skill-name').value.trim(),
    description: $('#skill-desc').value.trim(),
    body: $('#skill-body').value,
    scripts: collectScripts(),
  };
  const isEdit = !!settingsState.editing;
  try {
    await apiJSON('/api/skills' + (isEdit ? '/' + encodeURIComponent(settingsState.editing) : ''), {
      method: isEdit ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    showToast(isEdit ? '已保存 ' + body.name : '已创建 ' + body.name);
    settingsState.editing = null;
    $('#skill-form').classList.add('hidden');
    $('#skill-list').classList.remove('hidden');
    loadSkills();
  } catch (e) { showToast('保存失败：' + e.message); }
}
async function uploadSkillZip(file) {
  if (!file) return;
  try {
    await apiJSON('/api/skills/upload', { method: 'POST', body: file });  // 原始 zip 二进制
    showToast('导入成功');
    loadSkills();
  } catch (e) { showToast('导入失败：' + e.message); }
}

// ---------- MCP ----------
async function loadMcp() {
  try {
    const data = await apiJSON('/api/mcp');
    if ($('#mcp-config').value.trim() === '' || document.activeElement !== $('#mcp-config'))
      $('#mcp-config').value = JSON.stringify(data.configured || {}, null, 2);
    renderMcpServers(data.servers || []);
  } catch (e) { showToast('MCP 状态加载失败：' + e.message); }
}
function renderMcpServers(servers) {
  const box = $('#mcp-server-list');
  if (!servers.length) { box.innerHTML = '<p class="page-hint">未配置 MCP Server。在下方填入 mcpServers JSON 后保存。</p>'; return; }
  box.innerHTML = servers.map(s => `
    <div class="mcp-server-item">
      <span class="status-dot ${escapeHtml(s.status)}"></span>
      <div class="mcp-server-main">
        <div class="mcp-server-name">${escapeHtml(s.name)} <span style="color:var(--text-4);font-size:11px">(${escapeHtml(s.type)})</span></div>
        ${s.error ? `<div class="mcp-server-error">${escapeHtml(s.error)}</div>` : ''}
        <div class="mcp-server-tools">${s.toolCount} 个工具${s.status === 'connected' ? ' · 已进入点金可用工具' : ''}</div>
      </div>
    </div>`).join('');
}
async function saveMcp() {
  let raw;
  try { raw = JSON.parse($('#mcp-config').value); } catch (e) { showToast('JSON 格式错误：' + e.message); return; }
  try {
    const data = await apiJSON('/api/mcp', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(raw) });
    renderMcpServers(data.servers || []);
    showToast('已保存并重连');
  } catch (e) { showToast('保存失败：' + e.message); }
}
```

- [ ] **Step 2: ai.js 修改初始化绑定**

把 `ai.js` 中设置按钮的占位逻辑（`grep -n "settings-btn" ai.js` 定位）：
```js
  $('#settings-btn').onclick = () => showToast('设置页将在下期（能力扩展）提供');
```
改为：
```js
  $('#settings-btn').onclick = openSettings;
```

并在同函数（DOMContentLoaded）内 `$('#tool-toggle').onclick = ...` 绑定之后追加：

```js
  // 设置面板
  $('#settings-close').onclick = closeSettings;
  $('#settings-overlay').onclick = closeSettings;
  document.querySelectorAll('.settings-tab').forEach(t => {
    t.onclick = () => {
      document.querySelectorAll('.settings-tab').forEach(x => x.classList.toggle('active', x === t));
      $('#page-skills').classList.toggle('hidden', t.dataset.tab !== 'skills');
      $('#page-mcp').classList.toggle('hidden', t.dataset.tab !== 'mcp');
      if (t.dataset.tab === 'mcp') loadMcp();
    };
  });
  $('#skill-new').onclick = () => openSkillForm();
  $('#skill-form').onsubmit = submitSkill;
  $('#skill-form-cancel').onclick = () => { $('#skill-form').classList.add('hidden'); $('#skill-list').classList.remove('hidden'); };
  $('#skill-add-script').onclick = () => addScriptRow('', '');
  $('#skill-upload').onclick = () => $('#skill-zip-input').click();
  $('#skill-zip-input').onchange = (e) => { uploadSkillZip(e.target.files[0]); e.target.value = ''; };
  $('#mcp-save').onclick = saveMcp;
  $('#mcp-reload').onclick = async () => {
    try { const data = await apiJSON('/api/mcp/reload', { method: 'POST' }); renderMcpServers(data.servers || []); showToast('已重连'); }
    catch (e) { showToast('重连失败：' + e.message); }
  };
```

- [ ] **Step 3: typecheck**

Run: `npm run typecheck`

Expected: 无错误。

- [ ] **Step 4: 浏览器端到端手测**

重启服务（使 Task 5/6 改动生效），浏览器打开 `http://localhost:8888/ai`，按清单操作：
1. 点右下角设置按钮 → 抽屉滑出，技能 tab 显示「暂无技能」+「创建示例：估值分析」按钮
2. 「新建技能」→ 填名称 `demo-skill`、描述、正文「# 演示」，添加脚本 `hello.py`（内容 `print('hello from py')`）→ 保存 → 列表出现 demo-skill（脚本: hello.py），toast「已创建」
3. 「编辑」→ 表单回填名称（禁用）/描述/正文/脚本内容 → 改正文保存 → 列表不变、toast「已保存」
4. 开关关闭再开启 → toast 提示
5. MCP tab → textarea 出现 `{}` → 粘贴 AI Tools 配置 → 「保存并重连」→ 状态列表出现 AI Tools 绿点 + 工具数
6. 关闭面板 → 对话输入「用 demo-skill 技能执行 hello.py 脚本」→ status 依次出现「正在加载技能 demo-skill…」「正在执行技能脚本 hello.py…」，回复含 `hello from py`
7. 「导入 zip」→ 选 Task 3 生成的 /tmp/demo-skill.zip → toast「导入成功」→ 列表出现 my-analyzer → 删除它
8. 空状态点「创建示例：估值分析」→ 列表出现 valuation-analysis
9. 删除 demo-skill 与 valuation-analysis → 列表空

Expected: 全部按清单表现；控制台无报错。

- [ ] **Step 5: Commit**

```bash
git add ai.js
git commit -m "feat: 设置面板交互 - 技能 CRUD/脚本编辑/示例模板/zip 导入/MCP 配置与状态"
```

---

### Task 8: 端到端回归验证

**Files:** 无新文件（仅验证）

- [ ] **Step 1: typecheck 全量**

Run: `npm run typecheck`

Expected: 无错误。

- [ ] **Step 2: 对话回归（原有功能不受影响）**

浏览器 `http://localhost:8888/ai`：
1. 关闭设置面板后「今日盈亏」chip → 原有 7 工具正常，status 显示「正在查询资产概览…」（原文案不变）
2. 「数据工具」开关关闭 → 纯对话（不调任何工具，含 skill/MCP）
3. 新对话/历史会话/导出/重命名 → 原有功能正常

Expected: 原有行为不变。

- [ ] **Step 3: 负面路径**

1. 创建名称含中文的 skill → 表单提交被 400 拒绝并 toast（名称正则）
2. 对话触发不存在的 skill 脚本参数 → 模型收到 error 文本并如实说明
3. MCP 配置填坏 JSON → 前端 toast「JSON 格式错误」；填合法 JSON 但 command 指向不存在路径 → 保存后状态红灯 + 错误信息，对话仍可用

Expected: 均不崩溃、不阻塞对话。

- [ ] **Step 4: 清理与提交（如无改动则跳过 commit）**

```bash
git status
```

确认无意外改动（`~/.tzzb_*` 均在用户目录，不入库）。若有残留调试文件则清理。

---

## Self-Review 记录

- **Spec 覆盖**：Skill 存储/触发/脚本（Task 2-3）、MCP 集成（Task 4）、动态合并与 prompt 注入（Task 5）、设置面板（Task 6-7，含 spec 要求的示例 skill 模板）、错误处理（Task 3/4 负面验证 + Task 8）、zip 导入（Task 3 + Task 7）、status 事件文案（Task 5 `toolStatusText`，精确实现「正在加载技能 X…」「正在调用 MCP 工具 Y…」，原有工具文案不变）。全部覆盖。
- **占位符**：无 TBD/TODO；所有代码块完整；Task 5 Step 7 已内联重复测试配置内容。
- **类型一致性**：`getSkillScriptContents` 于 Task 3 定义、Task 5 使用并 import；`handleSkillsList(req, res, url)` 签名在 Task 5 定稿（含 `?detail=` 支持），Task 7 前端直接消费，无二次修订；`toolStatusText(tc)` 替代早期 toolLabel 方案，签名统一。
