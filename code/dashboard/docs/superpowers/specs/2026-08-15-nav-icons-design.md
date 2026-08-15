# 导航与图标优化 设计规格

> **日期：** 2026-08-15
> **状态：** 已获用户批准（浏览器 mockup 投票 + 终端确认）
> **范围：** 看板/点金双页面顶部导航 + 摸鱼/机器人图标重设计 + 隐私/摸鱼两页同步

## 目标

1. 看板顶栏 breadcrumb 区改为「看板」「点金」双 Tab 导航，移除右上角 🤖 临时入口
2. 点金页 Header 改为对称双 Tab + 新增 👁/🖥 按钮
3. 摸鱼图标重设计为咖啡杯（现图标语义不清）；🤖 emoji 以对话气泡图标取代
4. 隐私（模糊金额）/摸鱼（灰阶伪装）状态在两页间同步（localStorage + storage 事件，双开标签页实时生效）

## 已确认决策

| 决策 | 结论 | 理由 |
|------|------|------|
| 导航形态 | 顶部双 Tab（非下拉/浮动） | 两页规模最自然，未来加配置页直接加一项 |
| 点金导航图标 | 对话气泡（15px 细线） | 用户投票 C；聊天语义直观 |
| 摸鱼图标 | 咖啡杯（15px、1.5 描边） | 用户投票 C；摸鱼文化符号 |
| 点金页返回 | 对称双 Tab（非仅返回链接） | 两页导航结构一致 |
| 隐私/摸鱼 | 两页同步生效 | 点金页对话含持仓金额，有隐私需求 |
| 强调色 | 看板 #f97316 / 点金 #F59E0B 各自保持 | 各页色板独立 |

## 图标 SVG（精确规范）

**对话气泡（点金导航项）：**
```html
<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 12a8 8 0 0 1-8 8H5l2.5-3A8 8 0 1 1 21 12z"/></svg>
```

**咖啡杯（摸鱼按钮）：**
```html
<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M17 8h1a3 3 0 0 1 0 6h-1"/><path d="M3 8h14v7a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4z"/><path d="M7 1v2M11 1v2"/></svg>
```

**四宫格（看板导航项）：**
```html
<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
```

## 看板页顶栏改造（index.html）

- 把 `.breadcrumb` 区块替换为 `.top-nav`：
  ```html
  <nav class="top-nav">
    <a class="nav-item active" href="/">[四宫格] 看板</a>
    <a class="nav-item" href="/ai">[气泡] 点金</a>
  </nav>
  ```
  active 态由页面自身决定（看板页「看板」active、点金页「点金」active；不做 JS 自动检测——两页是独立静态文件，直接写死各自 active）
- `.breadcrumb` 的 CSS 规则与"看板 › 投资账本 · 金融终端"文案移除；breadcrumb span 相关的摸鱼文案逻辑（toggleStealth 中 `document.querySelector('.breadcrumb span')`）同步删除/替换（点金页 stealth 只改 document.title，不动导航文字）
- `toggleStealth` 中摸鱼图标按钮 `#stealth-btn` 的 SVG 替换为咖啡杯；`togglePrivacy` 不变
- 🤖 按钮 `<button class="ai-toggle-btn" ...>🤖</button>` 删除；`.ai-toggle-btn` 两条 CSS 规则删除
- 原 `.breadcrumb` 位置：`<div class="breadcrumb">` 及其内容整体被 nav 替换；`.index-tabs`（账户切换）位置与样式不变

## 点金页 Header 改造（ai.html / ai.css / ai.js）

Header 新布局（从左到右）：
```
[#sidebar-toggle 折叠按钮] [.top-nav: 看板 | 点金(active)] [.chat-title 会话标题] ... [.header-actions: 👁 🖥 导出]
```

- `.top-nav` 使用共享 nav.css；点金页 active 下划线颜色 #F59E0B（ai.css 覆盖变量）
- 👁 按钮（复用眼睛 SVG）与 🖥 按钮（咖啡杯 SVG）新增于 `.header-actions` 内、导出按钮左侧；id 为 `#dj-privacy-btn` / `#dj-stealth-btn`（避免与看板页 id 冲突——两页不同文档，可用同名但保持语义明确）
- 摸鱼/隐私行为（点金页）：
  - `body.privacy`：`.msg-ai-body`、`.msg-user`、`.si-title`、`.chat-title` → `filter: blur(5px); user-select: none;`
  - `body.stealth`：`body { filter: grayscale(1); }` 全页灰阶；`document.title` → `数据概览 · Overview`（关闭时还原 `点金 · 投资 AI 助手`）
  - 点金页不修改导航文字（与看板页行为差异：看板页还改 breadcrumb 文案——breadcrumb 已不存在，见上文）

## 两页状态同步机制

- 状态源：localStorage `tzzb_privacy` / `tzzb_stealth`（复用现有 key，值 '1'/'0'）
- 每页初始化：`DOMContentLoaded` 时读 localStorage 应用 body class + 图标/标题状态
- 实时同步：两页都监听 `window.addEventListener('storage', ...)`——任一页切换，另一页（同浏览器其他标签）立即应用对应 body class 与 UI 状态（无需刷新）

## nav.css（新建共享文件）

- 新文件 `code/dashboard/nav.css`，index.html 与 ai.html 均 `<link rel="stylesheet" href="/nav.css">`
- 内容约 30 行：`.top-nav`（flex、gap、字体 11px mono）、`.nav-item`（图标+文字、默认 #5b5b63/点金页变量、hover 亮色、padding-bottom 4px）、`.nav-item.active`（文字亮色 + 2px 下划线，颜色用 CSS 变量 `--nav-accent`：看板页定义为 #f97316，点金页在 ai.css 里覆盖为 #F59E0B）

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `code/dashboard/nav.css` | 新增 | 共享导航样式（约 30 行） |
| `code/dashboard/index.html` | 修改 | breadcrumb→nav、咖啡杯图标、删 🤖+CSS、link nav.css、toggleStealth 文案逻辑调整 |
| `code/dashboard/ai.html` | 修改 | header 加 nav+👁🖥、link nav.css |
| `code/dashboard/ai.css` | 修改 | --nav-accent 覆盖、privacy/stealth 规则、header 新布局微调 |
| `code/dashboard/ai.js` | 修改 | 👁🖥 切换+初始化+storage 监听、stealth 标题切换 |

## 明确不做（YAGNI）

- 不做移动端汉堡菜单（顶栏已有响应式）
- 不迁移账户切换 tabs 到点金页
- 不改 LIVE/时钟/刷新按钮
- 不做导航高亮 JS 自动检测（静态双页，写死 active）
- 看板页 stealth 不再改导航文字（breadcrumb 已移除，仅点金页改 document.title）

## 验收清单

- [ ] 看板页：`[⿻ 看板(active)] [💬 点金]` 双 Tab 渲染正确，active 下划线橙色 #f97316
- [ ] 点金页：对称双 Tab，active 为点金（下划线 #F59E0B）；点击「看板」跳回 `/`
- [ ] 🤖 按钮与 .ai-toggle-btn 样式完全移除，看板无回归（7 卡片/账户切换/刷新/LIVE 正常）
- [ ] 摸鱼按钮显示咖啡杯图标，hover 样式与眼睛按钮一致
- [ ] 看板页 👁/🖥 行为不变（模糊/灰阶 + 标题伪装）
- [ ] 点金页 👁：消息体/会话标题/聊天标题模糊；🖥：全页灰阶 + 标题「数据概览 · Overview」
- [ ] 双开标签页（看板+点金）状态实时同步（storage 事件）
- [ ] 刷新任一页状态保持（localStorage 初始化）
- [ ] 移动端（≤768px）两页导航均正常显示
- [ ] `tsc --noEmit` 零错误；两页 node --check / HTML 解析通过
