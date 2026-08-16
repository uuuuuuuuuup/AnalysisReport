/**
 * Skill 系统：~/.tzzb_skills/<name>/SKILL.md + scripts/
 * 提供 skill 存储 CRUD、zip 导入；Agent 工具 use_skill / run_skill_script 见 Task 3
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { tool } from 'ai';
import { z } from 'zod';

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

// ============ 脚本执行 + Agent 工具 ============
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
