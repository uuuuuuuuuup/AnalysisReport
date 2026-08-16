# 点金 AI 助手 — Skill 与 MCP 功能扩展设计

日期：2026-08-16
状态：已与用户逐节确认

## Context

点金（`code/dashboard/` 投资看板 AI 助手）目前支持 7 个内置数据工具（`tools.ts`）和 SSE 流式对话（`server.ts`）。本次扩展两个能力：

1. **Skill**：开放 skill 配置页面，支持用户创建、上传 skill（SKILL.md + 可执行脚本 python3/node/bash），对话中 agent 按需加载使用。
2. **MCP**：MCP Client 集成，连接外部 MCP Server（stdio / SSE），其工具自动进入点金对话可用工具集。

目标产物：设置面板（技能 tab + MCP tab）、Skill 系统（工具触发式加载 + python 脚本执行）、MCP 连接管理。

## 已确认的关键决策

| 决策点 | 结论 |
|---|---|
| Skill 触发机制 | 工具触发式：system prompt 注入列表，模型调用 `use_skill` 加载全文 |
| Skill 形态 | SKILL.md 提示词 + 可选脚本（python3 / node / bash 按扩展名自动选择解释器） |
| MCP 传输 | stdio（必须，用户现有配置均为 stdio）+ SSE（顺带支持） |
| 架构 | 方案 A 单进程集成：`skills.ts` + `mcp.ts` 两个新模块 |
| 前端 | ai.html 设置按钮 → 右侧抽屉管理面板（两个 tab） |
| Skill 存储 | `~/.tzzb_skills/<name>/`（用户目录） |

## 1. Skill 系统

### 存储格式

```
~/.tzzb_skills/<name>/
  SKILL.md          # frontmatter: name + description，正文为指引
  scripts/          # 可选
    xxx.py
```

- 与 `.claude/skills` 的 SKILL.md 格式一致，未来可互迁。
- 启用状态存 `~/.tzzb_skills_config.json`（`{"<name>": true}`），不写入 SKILL.md。

### 触发机制（工具触发式）

1. system prompt 末尾注入启用 skill 列表（一行一个：`name — description`）+ 指引「任务匹配某技能时先调用 `use_skill` 加载其指引」。
2. `use_skill(name)`：execute 返回 SKILL.md 全文 + scripts 列表，经 tool-result 注入上下文。无需改造 streamText。
3. `run_skill_script(skill, script, args)`：按脚本扩展名选择解释器（`.py`→`python3`，`.js/.mjs/.cjs`→`node`，`.sh`→`bash`），`spawn(解释器, [script, ...args], { cwd: skillDir, timeout: 30000 })`，返回 stdout（截断 50KB）+ exit code + stderr 摘要。

### 脚本安全约束

- 脚本名必须解析后落在该 skill 的 `scripts/` 目录内（防目录穿越）。
- `spawn` 数组参数、不用 shell（防参数注入）。
- 30s 超时强制终止；输出截断 50KB。
- 解释器按脚本扩展名自动选择：`.py`→`python3`、`.js/.mjs/.cjs`→`node`、`.sh`→`bash`（其余扩展名拒绝执行）。

## 2. MCP 集成

### 配置

`~/.tzzb_mcp_config.json`，直接兼容标准 `mcpServers` 格式：

```json
{
  "mcpServers": {
    "AI Tools": {
      "command": "node",
      "args": ["/path/to/index.js"],
      "env": { "AI_TOOLS_BASE_URL": "http://localhost:8080" }
    },
    "某远程服务": { "type": "sse", "url": "https://...", "headers": {} }
  }
}
```

### 连接与工具合并

- 新模块 `mcp.ts`：用 `@modelcontextprotocol/sdk` 的 `Client` + `StdioClientTransport` / `SSEClientTransport`。
- 懒连接：首次对话请求前 `ensureConnected()`；失败标记状态、不阻塞对话。
- 工具名统一 `mcp__<server>__<tool>`（防与内置工具冲突）。
- JSON Schema → zod 转换用 AI SDK 内置 `jsonSchema` helper，生成 AI SDK `tool()`。
- `ALL_TOOLS` 改为动态构建：内置 7 个 + skill 2 个 + MCP 工具；`TOOL_LABELS` 同步扩展（MCP 工具显示「MCP工具 · <tool>」）。

## 3. REST API（沿用现有 cookie 鉴权模式）

```
GET    /api/skills                 # 列表：name/description/enabled/scripts
POST   /api/skills                 # 创建：{name, description, body, scripts:[{filename, content}]}
PUT    /api/skills/:name           # 更新正文/脚本
DELETE /api/skills/:name           # 删除（含目录）
PATCH  /api/skills/:name/toggle    # {enabled} 启用/禁用
POST   /api/skills/upload          # zip 上传导入（解压到 ~/.tzzb_skills/<zip内顶层目录名>/）

GET    /api/mcp                    # 配置 + 各 server 状态（connected/error/工具数）
PUT    /api/mcp                    # 整份保存 mcpServers JSON
POST   /api/mcp/reload             # 断开重连
```

## 4. 前端设置面板

ai.html 内新增右侧滑出抽屉（约 420px 宽），点设置按钮（现为「设置（下期）」toast 占位）打开：

**技能 tab**
- 技能列表：名称、描述摘要、启用开关、编辑/删除按钮。
- 「新建技能」→ 表单：名称、描述、正文 textarea、脚本区（文件名+内容，可添加多个；解释器按扩展名自动识别 .py/.js/.sh）。
- 「导入 zip」：上传 zip 批量导入。
- 内置示例 skill（如「估值分析」）一键创建模板。

**MCP tab**
- 配置编辑：textarea 直接编辑 `mcpServers` JSON + 保存。
- 服务器状态列表：状态灯（未连接/已连接/连接失败+错误信息）、工具数、「重连」按钮。

**对话中**：复用现有 SSE `status` 事件流 —— skill 加载显示「正在加载技能 X…」，MCP 调用显示「正在调用 MCP 工具 Y…」。

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| Skill 不存在 / SKILL.md 损坏 | `use_skill` 返回错误文本，模型如实说明 |
| 脚本超时 / 非零退出 | 返回 exit code + stderr 摘要，模型继续分析 |
| MCP server 连接失败 | 标记 error 状态，对话照常，面板红灯显示原因 |
| MCP tool 调用失败 | 返回错误文本给模型，不中断对话 |
| zip 解压异常 / 目录名冲突 | 400 + 明确错误信息 |

## 6. 改动文件清单

| 文件 | 改动 |
|---|---|
| `skills.ts` 新增 | skill 扫描/CRUD 存储 + `use_skill` + `run_skill_script` 工具 |
| `mcp.ts` 新增 | MCP client 懒连接、工具转换、状态管理 |
| `server.ts` 修改 | 合并动态工具、新增路由、system prompt 注入 skill 列表、status 事件 |
| `ai.html` 修改 | 设置抽屉面板结构 |
| `ai.css` 修改 | 抽屉/表单/状态灯样式 |
| `ai.js` 修改 | 面板交互、skills/mcp API 调用、设置按钮改打开面板 |
| `package.json` 修改 | 新增 `@modelcontextprotocol/sdk` 依赖 |

## 7. 验证

1. `npm run typecheck` 通过。
2. 启动服务，curl 验证 skills/mcp CRUD 全链路。
3. 端到端：创建示例 skill → 对话触发 `use_skill` → 脚本执行返回数据；用真实 AI-Tools / siyuan MCP 配置验证 MCP 工具调用。
4. 负面路径：超时脚本、坏 MCP 配置、路径穿越参数。
