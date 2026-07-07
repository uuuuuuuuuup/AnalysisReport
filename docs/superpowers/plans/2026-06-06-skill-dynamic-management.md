# Skill 动态管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将本地 `.claude/skills/` 下的 20+ 个 skill 迁移到思源笔记「规划/Skill库/」目录，建立分类文件夹式结构，并更新数据库「文档路径」字段。

**Architecture:** 在思源笔记中按「分类/skill名/版本」建立文件夹层级，每个 skill 文档包含标准化 frontmatter。AI 运行时通过 MCP 从思源读取 skill 内容，实现动态加载。

**Tech Stack:** SiYuan Note (MCP), Markdown, YAML frontmatter

---

### Task 1: 创建思源笔记目录结构

**Files:**
- Create in SiYuan: `/规划/Skill库/`
- Create in SiYuan: `/规划/Skill库/投资分析/`
- Create in SiYuan: `/规划/Skill库/技术工具/`
- Create in SiYuan: `/规划/Skill库/日常效率/`
- Create in SiYuan: `/规划/Skill库/知识管理/`

- [ ] **Step 1: 创建 Skill库 根目录**

使用 `document.create` 在「规划」下创建 `/规划/Skill库/` 文档。

- [ ] **Step 2: 创建 5 个分类文件夹**

使用 `document.create` 创建：
- `/规划/Skill库/投资分析/`
- `/规划/Skill库/技术工具/`
- `/规划/Skill库/日常效率/`
- `/规划/Skill库/知识管理/`
- `/规划/Skill库/通用/`

**Commit:** 此步骤不产生本地 git 变更，记录 SiYuan 文档 ID 备后续使用。

---

### Task 2: 迁移 turtle-investment-strategy（含多版本）

**Files:**
- Read local: `.claude/skills/turtle-investment-strategy/SKILL.md`
- Read local: `.claude/skills/turtle-investment-strategy/V1.0.md`
- Read local: `.claude/skills/turtle-investment-strategy/V1.1.md`
- Read local: `.claude/skills/turtle-investment-strategy/V1.2.md`
- Read local: `.claude/skills/turtle-investment-strategy/V1.3.md`
- Read local: `.claude/skills/turtle-investment-strategy/V1.4-legacy.md`
- Read local: `.claude/skills/turtle-investment-strategy/V2.0.md`
- Create in SiYuan: `/规划/Skill库/投资分析/turtle-investment-strategy/V1.0`
- Create in SiYuan: `/规划/Skill库/投资分析/turtle-investment-strategy/V1.1`
- Create in SiYuan: `/规划/Skill库/投资分析/turtle-investment-strategy/V2.0`
- Create in SiYuan: `/规划/Skill库/投资分析/turtle-investment-strategy/README`

- [ ] **Step 1: 读取本地所有版本文件**

使用 Bash `cat` 读取 7 个本地文件内容。

- [ ] **Step 2: 创建 skill 文件夹和版本文档**

使用 `document.create` 创建：
- `/规划/Skill库/投资分析/turtle-investment-strategy/` 文件夹（通过创建子文档实现）
- 各版本文档，内容写入本地读取的 markdown

- [ ] **Step 3: 添加标准化 frontmatter**

在 SKILL.md（当前活跃版本，对应 V2.0）内容前添加 frontmatter：

```yaml
---
name: turtle-investment-strategy
version: V2.0
description: 基于四因子的价值投资分析框架，主代理+子代理多阶段架构
category: 投资分析
tags: [价值投资, 四因子, 建仓, 财报分析]
triggers: [分析股票, 四因子, 建仓, 价值投资, 评估公司]
dependencies: [mx-finance-data, mx-stocks-screener, mx-finance-search]
priority: 8
status: 启用
---
```

- [ ] **Step 4: 创建 README**

README 内容包含：
- skill 用途概述
- 版本变更记录（V1.0 → V2.0 的演进）
- 使用示例
- 依赖说明

---

### Task 3: 迁移 fund-arbitrage

**Files:**
- Read local: `.claude/skills/fund-arbitrage/skill.md`
- Create in SiYuan: `/规划/Skill库/投资分析/fund-arbitrage/V1.0`
- Create in SiYuan: `/规划/Skill库/投资分析/fund-arbitrage/README`

- [ ] **Step 1: 读取本地文件**

- [ ] **Step 2: 创建文档并写入内容**

添加 frontmatter：

```yaml
---
name: fund-arbitrage
version: V1.0
description: QDII-LOF 溢价套利扫描工具，读取 data/arbitrage_raw.json 生成分析报告
category: 投资分析
tags: [基金, 套利, LOF, 实时数据]
triggers: [基金套利, LOF, 套利机会, /fund-arbitrage]
dependencies: []
priority: 7
status: 启用
---
```

---

### Task 4: 迁移 bottom-trend-hunter

**Files:**
- Read local: `.claude/skills/bottom-trend-hunter/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/bottom-trend-hunter/V1.0`
- Create in SiYuan: `/规划/Skill库/投资分析/bottom-trend-hunter/README`

- [ ] **Step 1: 读取本地文件**

- [ ] **Step 2: 创建文档并写入内容**

添加 frontmatter（根据实际内容推断）。

---

### Task 5: 迁移 earnings-hunter

**Files:**
- Read local: `.claude/skills/earnings-hunter/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/earnings-hunter/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 6: 迁移 growth-stock-valuation

**Files:**
- Read local: `.claude/skills/growth-stock-valuation/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/growth-stock-valuation/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 7: 迁移 industry-research-report

**Files:**
- Read local: `.claude/skills/industry-research-report/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/industry-research-report/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 8: 迁移 industry-rotation-radar

**Files:**
- Read local: `.claude/skills/industry-rotation-radar/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/industry-rotation-radar/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 9: 迁移 industry-stock-tracker

**Files:**
- Read local: `.claude/skills/industry-stock-tracker/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/industry-stock-tracker/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 10: 迁移 initiation-of-coverage-or-deep-dive

**Files:**
- Read local: `.claude/skills/initiation-of-coverage-or-deep-dive/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/initiation-of-coverage-or-deep-dive/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 11: 迁移 position-doctor

**Files:**
- Read local: `.claude/skills/position-doctor/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/position-doctor/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 12: 迁移 short-term-trading

**Files:**
- Read local: `.claude/skills/short-term-trading/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/short-term-trading/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 13: 迁移 st-stock-strategy

**Files:**
- Read local: `.claude/skills/st-stock-strategy/SKILL.md`
- Create in SiYuan: `/规划/Skill库/投资分析/st-stock-strategy/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 14: 迁移 stock-earnings-review

**Files:**
- Read local: `.claude/skills/stock-earnings-review/SKILL.md`
- Read local: `.claude/skills/stock-earnings-review/BUSINESS_LOGIC.md`
- Create in SiYuan: `/规划/Skill库/投资分析/stock-earnings-review/V1.0`

- [ ] **Step 1: 读取两个本地文件**

- [ ] **Step 2: 创建文档，合并内容**

将 BUSINESS_LOGIC.md 作为附录附加到 SKILL.md 后。

---

### Task 15: 迁移 mx-* 系列技能（数据层）

**分类：技术工具**

| Skill | 文件 | SiYuan 路径 |
|-------|------|-------------|
| mx-finance-data | `.claude/skills/mx-finance-data/SKILL.md` | `/规划/Skill库/技术工具/mx-finance-data/V1.0` |
| mx-finance-search | `.claude/skills/mx-finance-search/SKILL.md` | `/规划/Skill库/技术工具/mx-finance-search/V1.0` |
| mx-financial-assistant | `.claude/skills/mx-financial-assistant/SKILL.md` | `/规划/Skill库/技术工具/mx-financial-assistant/V1.0` |
| mx-macro-data | `.claude/skills/mx-macro-data/SKILL.md` | `/规划/Skill库/技术工具/mx-macro-data/V1.0` |
| mx-stocks-screener | `.claude/skills/mx-stocks-screener/SKILL.md` | `/规划/Skill库/技术工具/mx-stocks-screener/V1.0` |

- [ ] **Step 1: 批量读取 5 个本地文件**

- [ ] **Step 2: 批量创建 5 个思源文档**

每个 mx-* skill 的 frontmatter：

```yaml
---
name: mx-finance-data
version: V1.0
description: 东方财富财务数据采集 skill
category: 技术工具
tags: [数据, 东方财富, API, 财务]
triggers: [采集财务数据, 东方财富]
dependencies: []
priority: 5
status: 启用
---
```

---

### Task 16: 迁移顶层 SKILL.md（通用 skill）

**Files:**
- Read local: `.claude/skills/SKILL.md`
- Create in SiYuan: `/规划/Skill库/通用/基础策略/V1.0`

- [ ] **Step 1: 读取并迁移**

---

### Task 17: 更新数据库「文档路径」字段

**Files:**
- Modify SiYuan AV: `Skill 注册表`

- [ ] **Step 1: 为已录入的 3 个 skill 更新文档路径**

使用 `av(action="set_cells")` 更新：
- turtle-investment-strategy → `/规划/Skill库/投资分析/turtle-investment-strategy/V2.0`
- fund-arbitrage → `/规划/Skill库/投资分析/fund-arbitrage/V1.0`
- bottom-trend-hunter → `/规划/Skill库/投资分析/bottom-trend-hunter/V1.0`

- [ ] **Step 2: 批量添加剩余 skill 到数据库**

使用 `av(action="add_rows")` + `av(action="set_cells")` 将迁移后的 skill 全部录入 Skill 注册表。

---

### Task 18: 验证与清理

- [ ] **Step 1: 验证所有文档可访问**

使用 `fs(action="tree")` 检查 `/规划/Skill库/` 目录结构是否完整。

- [ ] **Step 2: 验证数据库记录**

使用 `av(action="render")` 检查 Skill 注册表，确认所有 skill 的「文档路径」指向正确。

- [ ] **Step 3: 记录完成状态**

在「规划/Skill 动态管理」文档末尾添加迁移完成记录。
