---
name: recall
description: 从 memory-store 按需加载记忆到当前对话。Agent 自主浏览 INDEX.md → _profile.md → topic 文件，对话中随时加载更多记忆。触发方式：/recall、/recall <domain>、/recall <domain>/<topic>。
---

# Recall — 记忆加载

## 触发条件

- `/recall` — 浏览所有可用记忆
- `/recall <domain>` — 从指定领域开始
- `/recall <domain>/<topic>` — 加载特定主题

## 执行流程

### Step 1: 读取索引

读取 `memory-store/INDEX.md`，了解有哪些 domain 和 topic。

如果用户指定了 domain 或 topic，直接定位；如果没指定，列出所有 domain 供用户选择。

### Step 2: 按需加载（分层）

```
/recall
  → 展示 INDEX.md 中的 domain 列表
  → 用户选择或 agent 根据对话意图自动选择 domain

/recall <domain>
  → 读 <domain>/_profile.md（领域画像，轻量摘要）
  → agent 判断是否需要深入某个 topic
  → 如需要，继续加载 <domain>/<topic>.md

/recall <domain>/<topic>
  → 直接加载 topic 文件的全部条目
```

### Step 3: 对话中自主扩展

对话过程中，agent 可以自行判断"我需要更多记忆"并回头读更多文件。不是一次性加载完。

例如：
- 聊投资策略时发现涉及心理层面 → 自动去读 `investment/trading-psychology.md`
- 用户提到巴菲特 → 自动去读 `buffett-perspective/_profile.md`

### Step 4: 使用记忆

加载的记忆注入当前对话上下文。Agent 在回答时引用记忆中的事实，标注来源：

```
根据你的记忆（investment/portfolio > 总资产结构），你目前...
```

## 文件格式参见

- `memory-store/INDEX.md` — 全局索引
- `memory-store/domains/<domain>/_profile.md` — 领域画像
- `memory-store/domains/<domain>/<topic>.md` — 主题条目
