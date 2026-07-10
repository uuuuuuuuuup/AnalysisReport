---
name: "siyuan-skill-loader"
description: "动态 skill 加载器 - 通过思源笔记数据库查询匹配的 skill，并加载其内容注入上下文。所有其他 skill 均存储在思源笔记中，此 skill 负责按需检索。"
triggers: ["加载skill", "查找skill", "skill路由", "动态加载", "/skill", "执行分析", "分析股票", "基金套利", "财报", "估值", "行业研究"]
priority: 10
---

# 思源笔记 Skill 动态加载器

## 职责

本 skill 是 Claude Code 的唯一常驻 skill，所有其他 skill 均存储在思源笔记中。当用户提出任何请求时，先通过本 skill 从思源笔记查询并加载匹配的 skill，再执行具体任务。

## 加载流程（分层检索）

```
用户输入
  ↓
【第一层：查分类表】
→ av render "Skill 分类表"
→ 获取分类：投资分析、技术工具、日常效率、知识管理、通用
→ 根据用户输入判断归属哪个分类
  ↓
【第二层：查注册表（在分类内匹配触发词）】
→ av render "Skill 注册表"
→ 筛选：分类=目标分类 AND 状态=启用
→ 读取这些 skill 的「触发词」字段，与用户输入匹配
→ 按匹配度排序，取 Top 1~3
  ↓
【第三层：选择性读取】
→ 只读取 Top 1~3 的「文档路径」对应文档（fs read）
→ 解析 frontmatter：name/version/dependencies
→ 递归加载依赖 skill
  ↓
执行用户请求
```

## 查询方式（MCP 优先，CLI 备选）

⚠️ **SQL 无法查询 AV 数据库**，分类表和注册表需通过 `av` 工具访问。

### 第一层：查询分类表

**MCP：**
```javascript
// 搜索分类表 AV
av(action="search", keyword: "Skill 分类表")
// 返回: [{id: "分类表AV_ID", name: "Skill 分类表"}]

// 渲染分类表
av(action="render", id: "分类表AV_ID")
// 返回: {view: {rows: [{cells: [{value: {block: {content: "投资分析"}}}]}]}}
// 字段：名称(text主键)、排序(number)、描述(text)、图标(text)
```

**CLI：**
```bash
siyuan-sisyphus av search --keyword "Skill 分类表" --json
siyuan-sisyphus av render --id <分类表AV_ID> --json
```

### 第二层：查询注册表（分类内匹配）

**MCP：**
```javascript
// 搜索注册表 AV
av(action="search", keyword: "Skill 注册表")
// 返回: [{id: "注册表AV_ID", name: "Skill 注册表"}]

// 渲染注册表
av(action="render", id: "注册表AV_ID")
// 返回: {view: {rows: [...]}}

// 内存中筛选和匹配
const category = "投资分析";  // 第一层判断的分类
const keyword = "分析股票";    // 用户输入的关键词

// 1. 筛选该分类下启用的 skill
const categorySkills = result.view.rows.filter(row => {
  const cat = row.cells.find(c => c.value?.keyID === '分类列ID')?.value?.mSelect?.[0]?.content;
  const status = row.cells.find(c => c.value?.keyID === '状态列ID')?.value?.mSelect?.[0]?.content;
  return cat === category && status === '启用';
});

// 2. 触发词匹配
const matched = categorySkills.map(row => {
  const name = row.cells.find(c => c.valueType === 'block')?.value?.block?.content;
  const triggers = row.cells.find(c => c.value?.keyID === '触发词列ID')?.value?.text?.content || '';
  const priority = row.cells.find(c => c.value?.keyID === '优先级列ID')?.value?.number?.content || 0;
  const path = row.cells.find(c => c.value?.keyID === '文档路径列ID')?.value?.text?.content;
  
  let score = parseInt(priority);
  triggers.split('、').forEach(t => {
    if (keyword.includes(t) || t.includes(keyword)) score += 10;
  });
  
  return { name, triggers, path, score };
}).filter(s => s.score > parseInt(priority))  // 必须有触发词匹配才保留
  .sort((a, b) => b.score - a.score)
  .slice(0, 3);
```

**CLI：**
```bash
# 渲染注册表保存到文件
siyuan-sisyphus av render --id <注册表AV_ID> --json > /tmp/registry.json

# 用 jq 筛选投资分析类、启用状态，提取触发词
cat /tmp/registry.json | jq '
  .view.rows | map({
    name: (.cells[] | select(.valueType == "block") | .value.block.content),
    triggers: (.cells[] | select(.value.keyID == "触发词列ID") | .value.text.content),
    path: (.cells[] | select(.value.keyID == "文档路径列ID") | .value.text.content),
    priority: (.cells[] | select(.value.keyID == "优先级列ID") | .value.number.content)
  })
'
```

### 第三层：读取 skill 内容

**MCP：**
```javascript
// 读取候选 skill 的完整内容
fs(action="read", path: matched[0].path)

// 解析 frontmatter（内容前 --- 包裹的 YAML）
// 确认：
// - name 与数据库主键一致
// - category 与第一层判断一致
// - dependencies: [] 是否需要额外加载
```

**CLI：**
```bash
siyuan-sisyphus fs read "/规划/Skill库/投资分析/turtle-investment-strategy/V2.0" --json
```

## 获取列 ID 的方法

注册表的列 ID 需要通过 `get_attribute_view_keys` 获取：

```javascript
av(action="get_attribute_view_keys", id: "注册表AV_ID")
// 返回: [
//   {id: "xxxxx", name: "主键", type: "block"},
//   {id: "xxxxx", name: "分类", type: "select"},
//   {id: "xxxxx", name: "状态", type: "select"},
//   {id: "xxxxx", name: "版本", type: "text"},
//   {id: "xxxxx", name: "标签", type: "mSelect"},
//   {id: "xxxxx", name: "文档路径", type: "text"},
//   {id: "xxxxx", name: "触发词", type: "text"},
//   {id: "xxxxx", name: "优先级", type: "number"},
//   {id: "xxxxx", name: "使用次数", type: "number"},
//   {id: "xxxxx", name: "描述", type: "text"},
//   {id: "xxxxx", name: "最后更新", type: "date"}
// ]
```

## 决策规则

| 场景 | 决策 |
|---|---|
| **单一候选触发词精确匹配** | 直接加载该 skill |
| **多个候选匹配度相近** | 同时加载 Top 2~3，按依赖排序后注入 |
| **分类内无触发词匹配** | 降级到全库搜索（跨分类扫描触发词） |
| **全库无匹配** | 回退到基础策略（/规划/Skill库/通用/基础策略/V1.0） |
| **含股票代码 + 投资分析类多个匹配** | 优先 turtle-investment-strategy |

## Skill 内容格式

从思源读取的 skill 文档包含 YAML frontmatter：

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

## 版本切换

当用户请求特定版本时：
1. 查询数据库「版本」字段
2. 拼接路径：`/规划/Skill库/{分类}/{skill名}/{版本}`
3. 读取该版本文档

## 注意事项

1. **必须先从思源读取**：不要依赖本地缓存，每次加载前查询数据库
2. **分层查询**：先查分类表 → 再查注册表 → 最后读文档，不要跳层
3. **依赖自动加载**：如果 skill 的 `dependencies` 字段非空，先加载依赖 skill
4. **使用次数更新**：成功执行后，通过 MCP 更新数据库「使用次数」字段 +1
5. **路径稳定性**：skill 文档路径变更时，需同步更新数据库「文档路径」字段

## 示例调用

**用户说"分析一下万科A"：**

【第一层：查分类表】
- av render 分类表 → 获取 5 个分类
- 输入含股票代码 + "分析" → 判断为**投资分析**

【第二层：查注册表】
- av render 注册表 → 筛选「分类=投资分析 AND 状态=启用」
- 读取这些 skill 的触发词：
  - turtle-investment-strategy：触发词"分析股票" ✅ 精确匹配
  - fund-arbitrage：触发词"基金套利" ❌ 不匹配
  - bottom-trend-hunter：触发词"底部趋势" ❌ 不匹配
- 匹配结果：turtle-investment-strategy 匹配度最高

【第三层：选择性读取】
- fs read `/规划/Skill库/投资分析/turtle-investment-strategy/V2.0`
- 解析 frontmatter，确认 dependencies: [mx-finance-data, mx-stocks-screener]
- 递归加载依赖 skill

【执行】
- 注入 turtle-investment-strategy 正文到上下文
- 执行四因子分析流程

---

**用户说"帮我写个采集数据的脚本"：**

【第一层：查分类表】
- 输入含"采集数据"、"脚本" → 判断为**技术工具**

【第二层：查注册表】
- 筛选「分类=技术工具 AND 状态=启用」
- 触发词匹配：
  - mx-finance-data："财务数据、东方财富" ⚠️ 部分匹配（数据）
  - mx-macro-data："宏观数据" ⚠️ 部分匹配（数据）
- 匹配结果：mx-finance-data 匹配度最高

【第三层：选择性读取】
- fs read `/规划/Skill库/技术工具/mx-finance-data/V1.0`
- 无 dependencies，直接注入

【执行】
- 按 mx-finance-data 的指引执行数据采集
