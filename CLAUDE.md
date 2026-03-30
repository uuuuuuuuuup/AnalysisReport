# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

这是一个基于价值投资理念的股票分析报告展示网站，采用"龟龟投资策略"四因子分析框架。

## Architecture

### Frontend Structure
- **Entry Point**: `龟龟投资策略分析报告/index.html` - SPA 应用，使用原生 JavaScript
- **Styles**: `龟龟投资策略分析报告/styles.css` - CSS3 响应式设计
- **Logic**: `龟龟投资策略分析报告/app.js` - 应用状态管理、报告加载、视图切换
- **Components**:
  - `comments.js` - 评论功能
  - `annotations.js` - 批注功能

### Data Architecture

报告数据通过 `reportData` 数组在 `app.js` 中集中定义，支持多模型分析：

```javascript
// app.js 第 25-180 行
const reportData = [
    { code: '000002', name: '万科 A', file: 'GLM5/000002/万科A_000002_分析报告.md', rating: 'exclude', model: 'GLM5' },
    // ...
];
```

**模型配置**: `modelConfig` 对象定义支持的 AI 模型（GLM5、Qwen3.5-Plus 等）

### Directory Structure

```
龟龟投资策略分析报告/
├── index.html              # 主入口
├── app.js                  # 应用逻辑
├── styles.css              # 样式表
├── {model}/                # 按模型分组的报告目录
│   └── {stock_code}/
│       ├── {name}_{code}_分析报告.md
│       ├── data_pack_market.md      # 市场数据采集
│       └── data_pack_report.md      # 深度财务数据
└── .github/workflows/
    └── deploy.yml          # GitHub Pages 部署
```

## Development Commands

### Local Development

```bash
# 启动本地服务器（在项目根目录）
cd 龟龟投资策略分析报告
python -m http.server 8000

# 或使用 npx serve
npx serve .

# 访问 http://localhost:8000
```

### Deployment

GitHub Actions 自动部署：
- **Trigger**: Push 到 `main` 或 `master` 分支
- **Target**: GitHub Pages
- **Config**: `.github/workflows/deploy.yml`

## Adding New Reports

1. **创建目录**: `mkdir -p 龟龟投资策略分析报告/{model}/{stock_code}/`

2. **添加报告文件**: `{name}_{code}_分析报告.md`

3. **更新数据注册**: 在 `app.js` 的 `reportData` 数组中添加条目：
   ```javascript
   { code: '123456', name: '公司名称', file: 'Model/123456/公司名称_123456_分析报告.md', rating: 'good|warning|exclude', model: 'Model' }
   ```

4. **可选数据包**:
   - `data_pack_market.md` - 市场数据采集（Phase 1）
   - `data_pack_report.md` - 深度财务数据（Phase 2）

## Investment Strategy Framework

四因子分析框架（定义在 `.trae/skills/turtle-investment-strategy/V1.1.md`）:

1. **因子 1A** - 五分钟快筛（一票否决机制）
2. **因子 1B** - 深度定性分析
3. **因子 2/3** - 穿透回报率计算（粗算 + 精算）
4. **因子 4** - 估值与安全边际

### Rating System

- `good` (✅) - 建议建仓/持有
- `warning` (⚠️) - 需要关注风险
- `exclude` (❌) - 建议不建仓

## Key Technical Details

- **Markdown Parser**: Marked.js (CDN: `https://cdn.jsdelivr.net/npm/marked/marked.min.js`)
- **Fonts**: 阿里巴巴普惠体 + Inter (数字/英文)
- **State Management**: 全局 `state` 对象，localStorage 持久化收藏和侧边栏状态
- **Search**: Cmd/Ctrl + K 快捷键，支持股票代码和名称搜索
- **Responsive**: 移动端侧边栏可折叠，独立移动端搜索界面

## Important File Paths

- **报告根目录**: `龟龟投资策略分析报告/`
- **策略规则**: `.trae/skills/turtle-investment-strategy/V1.1.md`
- **归档文件**: `归档/` - 包含批量报告总结和进度记录
