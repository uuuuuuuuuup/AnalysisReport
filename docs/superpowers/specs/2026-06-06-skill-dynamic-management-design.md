# Skill 动态管理设计文档

## 概述

将 Claude Code 的 skill 体系从本地 `.claude/skills/` 迁移到思源笔记，通过思源数据库实现 skill 的动态注册、检索与加载。

**核心目标**：
- 解决 skill 过多导致的上下文膨胀问题
- 实现 skill 的按需加载与自动路由
- 建立版本管理机制
- 让 skill 管理可视化（在思源笔记里像 Excel 一样管理）

## 架构设计

### 1. 数据库结构（元数据层）

已部署在「规划/Skill 动态管理」文档内，包含两张 AV 表：

**表一：Skill 分类表**

| 字段 | 类型 | 说明 |
|------|------|------|
| 名称 | text | 主键，如"投资分析" |
| 排序 | number | 显示顺序 |
| 描述 | text | 分类说明 |
| 图标 | text | emoji |

**表二：Skill 注册表**

| 字段 | 类型 | 说明 |
|------|------|------|
| 名称 | text | 主键，skill 唯一标识 |
| 分类 | select | 关联分类 |
| 状态 | select | 启用 / 禁用 / 草稿 |
| 版本 | text | 当前版本号 |
| 标签 | mSelect | 多选标签 |
| 文档路径 | text | 思源笔记内文档路径（hpath） |
| 触发词 | text | 自动路由匹配关键词 |
| 优先级 | number | 1-10，冲突时决策 |
| 使用次数 | number | 累计调用次数 |
| 描述 | text | 功能说明 |
| 最后更新 | date | 更新时间 |

### 2. 目录结构（内容层）

采用**分类文件夹式**（方案二）：

```
/规划/Skill库/
  ├── 投资分析/
  │   ├── turtle-investment-strategy/
  │   │   ├── V1.0              ← 历史版本
  │   │   ├── V1.1
  │   │   ├── V2.0              ← 当前活跃版本
  │   │   └── README            ← skill 说明 + 版本变更记录
  │   ├── fund-arbitrage/
  │   │   └── V1.0
  │   └── ...
  ├── 技术工具/
  └── ...
```

**设计要点**：
- 与数据库「分类」字段完全对齐
- 每个 skill 独立文件夹，版本并列
- 数据库「文档路径」指向当前活跃版本
- README 记录 skill 用途、变更历史、使用示例

### 3. 文档格式规范

所有 skill 文档统一 frontmatter：

```yaml
---
name: turtle-investment-strategy
version: V2.0
description: 基于四因子的价值投资分析框架
category: 投资分析
tags: [价值投资, 四因子, 建仓]
triggers: [分析股票, 四因子, 建仓, 价值投资]
dependencies: [mx-finance-data, mx-stocks-screener]
priority: 8
status: 启用
---
```

**约束**：
- `name` 与数据库主键保持一致
- `category` 与数据库「分类」保持一致
- `version` 与数据库「版本」保持一致
- `status` 与数据库「状态」保持一致

### 4. 同步策略

**思源为主**（策略 A）：
- 思源笔记是 skill 的唯一可信源
- Claude Code 运行时通过 MCP 从思源读取 skill 内容
- 本地 `.claude/skills/` 保留作为备份，但不再主动维护
- 新增/修改 skill 全部在思源笔记中操作

### 5. 数据流

```
用户提问
  ↓
AI 提取关键词
  ↓
查询 Skill 注册表：匹配「触发词」和「标签」
  ↓
筛选「状态 = 启用」
  ↓
按「优先级」排序，取 Top-N
  ↓
根据「文档路径」读取 skill 文档
  ↓
解析 frontmatter 验证元数据
  ↓
提取正文作为 prompt 注入上下文
  ↓
执行
```

### 6. 版本切换机制

回滚/切换版本时，只需修改数据库：
- 更新「版本」字段为目标版本号
- 更新「文档路径」指向目标版本文档
- 无需移动或复制文件

## 待迁移 Skill 清单

当前本地 `.claude/skills/` 下的 skill（20+ 个）：

- turtle-investment-strategy（含 V1.0~V2.0 多个版本）
- fund-arbitrage
- bottom-trend-hunter
- earnings-hunter
- growth-stock-valuation
- industry-research-report
- industry-rotation-radar
- industry-stock-tracker
- initiation-of-coverage-or-deep-dive
- mx-finance-data
- mx-finance-search
- mx-financial-assistant
- mx-macro-data
- mx-stocks-screener
- position-doctor
- short-term-trading
- st-stock-strategy
- stock-earnings-review
- 以及 SKILL.md（顶层通用 skill）

## 注意事项

1. **数据库与文档一致性**：修改 skill 元数据时，需同时更新数据库和文档 frontmatter
2. **依赖管理**：`dependencies` 字段记录 skill 之间的调用关系，修改基础 skill 时需检查影响范围
3. **权限控制**：思源笔记的权限体系决定了哪些 skill 可被 AI 读取
4. **路径稳定性**：skill 文档路径变更时，需同步更新数据库「文档路径」字段
