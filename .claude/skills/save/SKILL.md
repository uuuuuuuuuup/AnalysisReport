---
name: save
description: 将当前对话中新产生的信息增量写入 memory-store。自动对比已有记忆，判断 save（新建）还是 update（更新），输出预览令用户确认后写入。触发方式：/save。
---

# Save — 记忆保存与更新

## 触发条件

- `/save` — 保存本次对话的增量记忆

## 执行流程

### Step 1: 加载已有记忆

1. 读取 `memory-store/INDEX.md`
2. 根据本次对话涉及的主题，加载相关 domain 下的所有已有条目
3. 如果本次对话是通过 `/recall` 开始的，优先加载 `/recall` 过的 domain

### Step 2: 逐条对比（判断 save or update）

对本次对话中产生的每条新信息，和所有已加载条目做语义比对：

```
新信息                              已有记忆匹配？
──────────────────────────────────────────────────
"我把海螺水泥卖了"          ──→   命中 "进攻账户持仓"条目
                                  → UPDATE：更新该条目，追加变更记录

"我开始关注医药板块"         ──→   无命中
                                  → SAVE：新建 topic 或条目

"巴菲特说要有耐心"          ──→   buffett 下已有类似内容
                                  → UPDATE：追加来源，丰富条目
```

**匹配原则**：
- 优先在本次 `/recall` 过的 domain 内匹配
- 语义相似度 > 字面相似度
- 不确定时标记 ⚠️ 让用户裁决

跳过的内容：
- 过程讨论、临时问答（不产生新事实）
- 与已有记忆完全重复的内容
- 用户明确说"这个不用记"

### Step 3: 输出变更预览

按 domain/topic 分组展示：

```
📥 变更预览：

  UPDATE investment/portfolio > ## 进攻账户持仓
    原: 持有海螺水泥
    新: 已清仓海螺水泥，资金转入短融ETF

  SAVE  investment > ## 医药板块关注
    新: 用户开始关注医药板块，暂未建仓

  UPDATE buffett/value-framework > ## 安全边际
    原: 已有1条来源
    新: 追加1条来源（本次对话 2026-08-11）

  无变化:
    investment/portfolio > ## 总资产结构
    investment/risk-appetite（本次未涉及）
    buffett/feedback（本次未涉及）
```

**等待用户确认**：确认后进入写入步骤，用户可以要求修改任何条目。

### Step 4: 写入

用户确认后执行：

1. **新条目** → append 到对应 topic 文件末尾（新建 topic/domain 则创建文件）
2. **变更条目** → 更新原条目的"事实"字段，在"变更记录"追加一行
3. **新建 topic** → 使用标准 frontmatter 模板创建 `.md` 文件
4. **新建 domain** → 创建目录 + `_profile.md` + 首个 topic 文件

### Step 5: 更新索引

1. 重新聚合涉及 domain 的 `_profile.md`（更新摘要 + entry_count）
2. 更新 `INDEX.md`（更新文件列表 + 条目数）

### Step 6: 输出总结

```
✅ 已写入：
  investment/portfolio        ~1 UPDATE + 1 SAVE
  buffett/value-framework     ~1 UPDATE

📊 memory-store 状态：
  investment: 11 → 13 条
  buffett: 13 → 14 条
```

## 条目格式

```markdown
## 条目标题
- **事实**: 一句话核心事实
- **来源**: 对话标识 + 日期
- **可信度**: 高/中/低
- 变更记录:
  - YYYY-MM-DD: 变更描述
```

## 特殊格式约定：investment/health-check-list（公司检查台账）

该文件不使用上方的「事实/来源/可信度」条目格式，而是**一张台账表 + 文字记录区**。凡涉及对关注池公司的检查动作（财报体检 / investment-checklist 六关核查 / income-investment 收息分析 / investment-research 深度研究），按下述规则写入：

1. **每个标的一行，多类型堆叠**：列固定为 `| 公司 | 检查日 | 报告期 | 池子·细分 | 类型 | 标签 | 核心发现 | 下一步 |`。同一公司做过多种/多轮检查时，各占一行。检查日省略年份；报告期带 `*` 表示垫底数据（Q1或上年报顶替），正式披露后须复扫。
2. **skill 结果只写一行摘要**：六关核查记「通过 X/6 或否决原因」；收息分析记「verdict + 分红覆盖结论」；深度研究记「买入/观望/回避 + 核心风险」。下一步里放报告文件路径（如 `reports/<公司>-income-investment-<日期>.md`）。完整报告落在各自 skill 规定的文件位置，**绝不把长文搬运进记忆**。
3. **没检查过的也必须占行**：标签 ⬜，核心发现写"本轮未纳入"，下一步写排期——保证"谁还没查"一眼可见。
4. **标签体系**：🚨雷 / ⚠️瑕疵 / ➡️平稳 / ✅改善 / ⬜未检查 / ❓（备用：分析过但存在硬欠账）。
5. **避免跨行重复**：板块级结论、宏观判断写成文字记录区的叙述段；可复用的阅读方法论优先沉淀到 `domains/investment/investment-logic.md`，台账用 [[investment-logic]] 引用即可。
6. 写入后同步该文件头部 `updated:` 字段与末尾变更记录。

## 文件格式参见

- `memory-store/INDEX.md` — 全局索引
- `memory-store/domains/<domain>/_profile.md` — 领域画像
- `memory-store/domains/<domain>/<topic>.md` — 主题条目
