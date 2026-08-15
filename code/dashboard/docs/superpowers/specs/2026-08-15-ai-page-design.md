# 「点金」AI 独立页面 设计规格

> **日期：** 2026-08-15
> **状态：** 已获用户批准（2026-08-15 对话确认）
> **范围：** 第四期 A 部分——AI 页面升级（Markdown 渲染 + 历史会话 + 独立页面）。配置页与 skills/MCP 为第四期 B 部分，另行设计。

## 目标

将看板 AI 助手从抽屉面板升级为独立专业对话页面 `/ai`，命名为「点金」（点石成金）。视觉语言：深色专业工具质感（类 Cursor/Vercel），卡片式消息而非气泡，去除"AI 味"。支持多会话管理（新建/切换/重命名/删除/搜索）与 Markdown 渲染（含代码高亮）。顶栏 🤖 按钮改为跳转 `/ai`，原抽屉代码移除。

## 已确认的关键决策

| 决策 | 结论 | 理由 |
|------|------|------|
| 技术栈 | 零构建原生（ai.html/ai.css/ai.js + vendored 单文件库） | 保持项目零构建架构；视觉规范 95% 是 CSS 层面，原生可 1:1 还原；运行方式不变（npm start） |
| 布局 | DeepSeek 官方结构（左会话栏 + 主对话区） | 用户对照 chat.deepseek.com 确认 |
| 配色 | 用户提供的深蓝灰规范（#0B1120 系），非纯黑 | 专业冷静，像高端开发工具 |
| 名字 | 点金 | 用户指定；标识 = 金锭线稿 + 右上一点（点金之意），灰白单色，hover 时点变金色 #F59E0B |
| 深/浅色 | 只做深色 | 与看板一致，少一套色板 |
| 抽屉 | 移除，🤖 跳转 /ai | 一套聊天 UI，避免双份维护 |

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `code/dashboard/ai.html` | 新增 | 页面结构（sidebar + header + 消息区 + 输入区 + 空状态） |
| `code/dashboard/ai.css` | 新增 | 全部样式（色板变量 + 组件 + 动效 + 响应式） |
| `code/dashboard/ai.js` | 新增 | 页面逻辑（会话管理、SSE 消费、Markdown 渲染管道、交互） |
| `code/dashboard/vendor/marked.min.js` | 新增 | Markdown → HTML（本地 vendored，无 CDN） |
| `code/dashboard/vendor/highlight.min.js` | 新增 | 代码语法高亮（含常见语言包，本地 vendored） |
| `code/dashboard/vendor/dompurify.min.js` | 新增 | AI 输出 XSS 消毒（本地 vendored） |
| `code/dashboard/server.ts` | 修改 | `/ai` 路由 + 4 个新 API + toolsEnabled 参数 + Session.title 字段 |
| `code/dashboard/index.html` | 修改 | 顶栏按钮跳转 /ai；删除 AI 面板三块（约 248 行） |
| `~/.tzzb_ai_sessions.json` | 复用 | 会话存储，新增 title 字段（向后兼容） |

依赖方向：`ai.html` → `ai.css`/`ai.js`/`vendor/*` → `/api/agent*`（HTTP）。无新 npm 依赖。

## 服务端设计（server.ts 修改）

### 路由

在现有 AI Agent 路由区（`/api/` 通用代理之前）新增：

```
GET  /ai                        → 静态 ai.html（与 / 同机制）
GET  /api/agent/sessions        → 会话列表
POST /api/agent/rename          → 重命名会话
POST /api/agent/delete          → 删除会话
POST /api/agent/regenerate      → 重新生成最后一条回复
POST /api/agent                 → 已有；新增可选参数 toolsEnabled
```

除 `/ai` 外，新路由与 `/api/agent` 相同的 cookie 鉴权（无 cookie → 401）。

### 数据结构（Session）

```json
{
  "updated": 1786778000000,
  "title": "昨日投资复盘",
  "messages": [ /* AI SDK 原始消息数组，同现状 */ ]
}
```

- `title` 缺省时，`GET /api/agent/sessions` 服务端从首条 user 消息提取前 20 字返回；持久化时不强制补齐（读取时兜底）
- 首条 user 消息到达且 title 为空时写入 title（首次对话自动命名）

### API 契约（精确字段）

**GET /api/agent/sessions** → `200`
```json
{ "sessions": [ { "id": "uuid", "title": "昨日投资复盘", "updated": 1786778000000 } ] }
```
按 updated 倒序；无 cookie → 401（同 /api/agent）。

**POST /api/agent/rename** body `{ "sessionId": "...", "title": "..." }` → `200 { "ok": true }`；title 为空或超 50 字 → `400 { "error": "title 不合法" }`。

**POST /api/agent/delete** body `{ "sessionId": "..." }` → `200 { "ok": true }`；不存在 → 200（幂等）。

**POST /api/agent/regenerate** body `{ "sessionId": "..." }` → SSE 流（协议同 /api/agent 四事件）。服务端行为：若最后一条是 assistant 则弹出；若最后一条是 user（上次失败）直接重跑。无 user 消息 → `400 { "error": "无可重新生成的消息" }`。

**POST /api/agent** body 增加 `"toolsEnabled": false`（可选，默认 true）→ `tools: {}` 禁用工具调用。

### 会话上限

维持现状：10 会话 × 60 条消息，按 updated 裁剪。

## 前端设计（ai.html / ai.css / ai.js）

### 色彩系统（CSS 变量，严格按用户规范）

```
--bg-page: #0B1120;        --bg-surface: #111827;     --bg-strong: #1F2937;
--bg-code: #0D1117;        --bg-input: #111827;
--text-1: #F3F4F6;         --text-2: #9CA3AF;         --text-3: #6B7280;   --text-4: #4B5563;
--border: #1F2937;         --divider: #374151;        --border-hover: #4B5563;
--ok: #10B981;             --warn: #F59E0B;           --danger: #EF4444;    --data-blue: #3B82F6;
```

### 布局

```
┌────────────────────────────┬──────────────────────────────┐
│ Sidebar 260px（可折叠60px） │ Header 56px（标题可编辑+按钮） │
│  搜索框                    │ ──────────────────────────── │
│  新对话按钮                 │ 消息列表（flex-1，卡片式消息）  │
│  今天/近7天/更早 会话列表    │ ──────────────────────────── │
│  用户区/设置               │ 输入区（底部固定）             │
└────────────────────────────┴──────────────────────────────┘
```

### 消息组件

- **用户消息**：无头像，右对齐，max-width 85%；背景 --bg-strong；圆角 `12px 12px 4px 12px`；padding 12px 16px；文字 14px/22px --text-1
- **AI 消息**：左侧「点金」几何标识（24px，灰白线稿）；背景 --bg-surface + 1px --border；圆角 `12px 12px 12px 4px`；max-width 90%；顶部行 = 标识 + "点金" + 时间戳（12px --text-3）+ 6px 呼吸绿点（--ok，2s 呼吸动画）
- **消息操作栏**（AI 消息底部，hover 显示，opacity 0→1 150ms）：复制 / 重新生成（11px --text-3，hover --text-2，背景 --bg-strong，圆角 4px）
- **打字状态**：三点 6px --text-3，1.4s 弹跳循环，依次延迟 0.2s，显示于 AI 消息位置

### Markdown 渲染管道

`AI 文本 → marked.parse() → DOMPurify.sanitize() → 注入消息卡片`。代码块：header（语言标签 + 复制按钮，hover 显示）+ highlight.js 高亮（背景 --bg-code、1px --border、圆角 8px、12px/20px 等宽、色 #9CA3AF）。

### 输入区

- 底部固定；容器圆角 12px、1px --border、背景 --bg-input、padding 12px 16px
- textarea auto-resize、无背景无边框、placeholder --text-4；Enter 发送、Shift+Enter 换行（含 `!e.isComposing` 守卫）
- 右侧：发送按钮 32×32 圆角 8px 背景 #F3F4F6 图标黑、hover opacity 0.85（附件按钮不做）
- 上方：chips 行 = 4 个投资语境快捷标签（"今日盈亏"/"持仓诊断"/"自选异动"/"资金流水"，点击填入并发送）+「数据工具」切换胶囊（开启=橙色语义点，请求带 toolsEnabled）

### 空状态

无会话时主区显示 4 张磁贴卡片（--bg-surface、1px --border、圆角 12px、padding 20px、24px 图标+标题+描述）：
1. 📋 生成本日投资简报
2. 🔍 分析持仓集中度
3. 📈 本周盈亏回顾
4. 💡 K线技术解读
点击卡片 → 填入输入框并直接发送。

### Sidebar

- 背景 --bg-page、右边框 1px --border；折叠按钮位于 Header 左端（300ms 宽度过渡 260px↔60px，折叠态只显示图标）
- 搜索框：顶部，圆角 8px，--bg-input + 1px --border，placeholder --text-4，前端过滤会话列表
- "新对话"按钮：全宽圆角 10px，背景 --bg-strong，hover --divider，文字 --text-1
- 会话项：圆角 8px、padding 8px 12px；默认透明，hover --bg-strong；选中态 --bg-strong + 左边框 2px #F3F4F6；标题 14px --text-1 单行截断；时间/摘要 12px --text-3；hover 显示删除按钮（opacity 切换），点击后 `confirm()` 确认再调 delete API
- 分组：今天 / 近 7 天 / 更早（按 updated 前端分组，组标签 11px --text-4 字距 2px）
- 重命名：会话项 hover 显示 ✎ 按钮 → 行内输入框（Enter 保存 Esc 取消），调 rename API
- 底部：用户名（mx_520687019）+ 设置齿轮（本页暂无动作，占位 title="设置（下期）"）

### Header

- 56px，透明背景、底部 1px --border
- 左侧：折叠侧栏图标按钮 + 当前会话标题（17px/500，点击变行内输入框可编辑，Enter 保存调 rename API）
- 右侧：导出 Markdown 按钮（拼接当前会话 user/assistant 文本 → 复制剪贴板 + toast 提示）

### 动效（克制）

- 状态切换 150ms ease-out；消息出现 200ms（opacity 0→1 + translateY(8px)→0）；侧栏 300ms；按钮 hover 150ms

### 响应式

- 桌面：侧栏展开 260px
- 平板（≤1024px）：侧栏折叠为 60px 图标栏，点击展开
- 移动（≤768px）：侧栏变抽屉（translateX 滑出 + 遮罩）；聊天区全宽；输入框 fixed 底部（`visualViewport` 监听处理键盘弹起，输入区随键盘上移）

### 数据流

1. 加载：`GET /api/agent/sessions` → 渲染侧栏；无会话 → 空状态；有会话 → 默认选中最近一个 → `GET /api/agent/history` 渲染消息
2. 发送：`POST /api/agent {sessionId, query, toolsEnabled}` → SSE 四事件（status→打字/状态提示，text→流式增量，done→收尾并刷新侧栏标题，error→卡片内 ❌）
3. 新对话：前端 `crypto.randomUUID()` 生成 sessionId → 直接进入对话（服务端懒创建，同现状）
4. 重新生成：`POST /api/agent/regenerate {sessionId}` → 同 SSE 协议
5. 历史消息渲染：仅文本（无 tool 重放），Markdown 管道渲染
6. 会话数达上限（10）时新建：服务端裁剪逻辑自动挤掉最旧会话，前端刷新列表

### 错误处理

- 401（cookie 缺失）：页面顶部错误条"请先配置 ~/.tzzb_cookies"，不阻塞页面其余功能
- 503（无 AI Key）：错误条"未配置 AI API Key（~/.tzzb_ai_config.json）"
- SSE error 事件：消息卡片内 ❌ + message，提供"重新生成"按钮
- 网络中断：卡片内 ❌ 网络错误 + 重新生成按钮
- sessions/history 拉取失败：侧栏显示重试按钮

## 明确不做（YAGNI 删减，已获用户确认）

| 项 | 理由 |
|----|------|
| 附件上传按钮 | AI 无文件理解能力 |
| 👍👎 反馈 | 无后端存储语义 |
| 分享按钮 | 本地单人工具 |
| 深/浅色切换 | 已确认只做深色 |
| 消息内 tool 过程重放 | 历史只存文本 |
| 多用户/鉴权体系 | 现有 cookie 门禁不变 |

## 验收清单

- [ ] `/ai` 页面可访问，视觉严格符合规范色板与组件规格
- [ ] 顶栏 🤖 跳转 /ai；原抽屉代码从 index.html 完全移除且看板无回归
- [ ] 新对话/切换/重命名/删除/搜索会话全部可用且持久化（重启不丢）
- [ ] 会话标题自动生成（首条消息前 20 字）且可重命名
- [ ] Markdown 正确渲染（标题/列表/粗体/表格/行内代码/代码块高亮 + 复制按钮）；XSS 消毒生效（注入 `<script>`/`onerror` 被清除）
- [ ] 流式输出逐字显示；状态事件显示"正在查询…"；三点打字动画
- [ ] "数据工具"开关关闭后模型不调用工具
- [ ] 重新生成可用（正常轮次与失败轮次两种）
- [ ] 复制消息、导出 Markdown 可用
- [ ] 响应式：1024px 折叠、768px 抽屉 + 键盘弹起输入框不遮挡
- [ ] 401/503/网络错误提示符合设计
- [ ] 会话上限裁剪行为不变（10×60）
- [ ] `tsc --noEmit` 零错误；AI 页面与看板互不影响
