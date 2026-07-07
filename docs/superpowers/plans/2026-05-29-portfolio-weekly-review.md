# 投资组合周报自动化系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建投资组合周报自动化系统，从274份分析报告中筛选30只关注标的，每周自动采集数据、生成周报、汇总报告并发送邮件。

**Architecture:** Python脚本负责数据采集和邮件发送，Claude Code Skill负责周报分析和汇总，数据通过JSON文件和Markdown文件传递。

**Tech Stack:** Python 3, AI-Tools MCP, SMTP (QQ邮箱)

---

## 文件结构规划

```
每周复盘重点关注/
├── _weekly_data/
│   └── latest_data.json          # 最新采集数据（覆盖式）
├── _summary/
│   └── 2026-05-29_汇总报告.md     # 汇总报告输出
├── scripts/
│   ├── filter_watchlist.py       # 筛选关注池
│   ├── fetch_weekly_data.py      # 数据采集
│   └── send_email.py             # 邮件发送
└── {code}/                       # 各公司目录（30个）
    ├── {原始报告}.md
    ├── data_pack_market.md
    ├── data_pack_report.md
    └── {date}.md                 # 周报文件
```

---

### Task 1: 创建关注池筛选脚本

**Files:**
- Create: `每周复盘重点关注/scripts/filter_watchlist.py`

**Context:** 从 `稳健投资策略分析报告/` 下274份报告中提取关键指标，筛选出30只关注标的并复制到 `每周复盘重点关注/`。

- [ ] **Step 1: 编写筛选脚本**

```python
#!/usr/bin/env python3
"""
从274份分析报告中筛选关注池，复制到每周复盘重点关注目录
"""
import os
import re
import shutil
import glob
from pathlib import Path

BASE_DIR = "/Users/apple/Documents/分析报告/稳健投资策略分析报告"
TARGET_DIR = "/Users/apple/Documents/分析报告/每周复盘重点关注"


def extract_key_metrics(filepath):
    """从报告文件中提取关键指标"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    metrics = {}

    # 提取仓位建议
    m = re.search(r'\| 仓位建议 \| \*\*(.+?)\*\* \|', content)
    metrics['rating'] = m.group(1).strip() if m else 'N/A'

    # 提取距离目标价
    m = re.search(r'\| 距离目标价 \| \*\*(.+?)\*\* \|', content)
    metrics['distance'] = m.group(1).strip() if m else 'N/A'

    # 提取安全边际
    m = re.search(r'\| 安全边际 \| \*\*(.+?)\*\* \|', content)
    metrics['margin'] = m.group(1).strip() if m else 'N/A'

    # 提取精算穿透回报率
    m = re.search(r'\| 精算穿透回报率 \| \*\*(.+?)\*\* \|', content)
    metrics['return_rate'] = m.group(1).strip() if m else 'N/A'

    # 提取公司名称
    m = re.search(r'\*\*(.+?)\*\*\s*·\s*(\d+)', content)
    metrics['name'] = m.group(1).strip() if m else 'Unknown'

    return metrics


def priority_score(metrics):
    """计算关注优先级分数"""
    score = 0
    rating = metrics.get('rating', '')
    distance = metrics.get('distance', 'N/A')
    margin = metrics.get('margin', 'N/A')

    # 可建仓/配置的优先级最高
    if any(kw in rating for kw in ['建仓', '配置', '可适度']):
        score += 100
    elif '观察' in rating:
        score += 50
    elif any(kw in rating for kw in ['否决', '排除', '不建仓']):
        score -= 50

    # 负距离（低于目标价）加分
    try:
        d_str = distance.replace('%', '').replace('+', '').replace('−', '-')
        d = float(d_str)
        if d < 0:
            score += 30
        elif d < 5:
            score += 20
    except (ValueError, TypeError):
        pass

    # 正安全边际加分
    try:
        m_str = margin.replace('pct', '').replace('+', '').replace('−', '-')
        m = float(m_str)
        if m > 1.5:
            score += 25
        elif m > 0:
            score += 15
    except (ValueError, TypeError):
        pass

    return score


def main():
    os.makedirs(TARGET_DIR, exist_ok=True)

    # 收集所有报告
    results = []
    report_files = glob.glob(f"{BASE_DIR}/*/*.md")

    for filepath in report_files:
        # 跳过数据包文件
        if 'data_pack' in filepath:
            continue

        # 从路径提取股票代码（目录名）
        match = re.search(r'/([^/]+)/[^/]+\.md$', filepath)
        if not match:
            continue
        symbol = match.group(1)

        metrics = extract_key_metrics(filepath)
        if not metrics:
            continue

        metrics['symbol'] = symbol
        metrics['filepath'] = filepath
        metrics['score'] = priority_score(metrics)
        results.append(metrics)

    # 按优先级排序，取前30
    results.sort(key=lambda x: x['score'], reverse=True)
    top30 = results[:30]

    print(f"从 {len(results)} 份报告中筛选出 {len(top30)} 只关注标的\n")

    # 复制到目标目录
    copied = 0
    for item in top30:
        symbol = item['symbol']
        src_dir = os.path.join(BASE_DIR, symbol)
        dst_dir = os.path.join(TARGET_DIR, symbol)

        if os.path.exists(src_dir):
            if os.path.exists(dst_dir):
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            copied += 1
            print(f"✅ {symbol} ({item['name']}) - {item['rating']} - 分数:{item['score']}")
        else:
            print(f"⚠️  {symbol} 目录不存在，跳过")

    print(f"\n共复制 {copied} 只标的到 {TARGET_DIR}")

    # 生成关注池清单
    watchlist_path = os.path.join(TARGET_DIR, '_watchlist.md')
    with open(watchlist_path, 'w', encoding='utf-8') as f:
        f.write("# 关注池清单\n\n")
        f.write("| 排名 | 代码 | 名称 | 仓位建议 | 精算回报率 | 安全边际 | 距离目标价 |\n")
        f.write("|:---|:---|:---|:---|:---|:---|:---|\n")
        for i, item in enumerate(top30, 1):
            f.write(f"| {i} | {item['symbol']} | {item['name']} | "
                    f"{item['rating']} | {item['return_rate']} | "
                    f"{item['margin']} | {item['distance']} |\n")

    print(f"关注池清单已保存到 {watchlist_path}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 运行脚本生成关注池**

Run:
```bash
cd "/Users/apple/Documents/分析报告"
python3 "每周复盘重点关注/scripts/filter_watchlist.py"
```

Expected: 输出30只标的的复制结果，生成 `_watchlist.md`

- [ ] **Step 3: 验证关注池**

Run:
```bash
ls "/Users/apple/Documents/分析报告/每周复盘重点关注/" | head -35
```

Expected: 看到30个公司目录 + `_watchlist.md`

---

### Task 2: 创建数据采集脚本

**Files:**
- Create: `每周复盘重点关注/scripts/fetch_weekly_data.py`

**Context:** 遍历关注池所有公司，调用 AI-Tools MCP 获取股价、公告、研报、资金流向，输出到 `latest_data.json`。

- [ ] **Step 1: 编写数据采集脚本**

```python
#!/usr/bin/env python3
"""
每周数据采集脚本
遍历关注池所有公司，获取最新股价、公告、研报、资金流向
输出: _weekly_data/latest_data.json (覆盖式)
"""
import os
import sys
import json
import time
import glob
import re
from datetime import datetime

# 将项目根目录加入路径以导入 MCP 工具
sys.path.insert(0, "/Users/apple/Documents/分析报告")

BASE_DIR = "/Users/apple/Documents/分析报告/每周复盘重点关注"
OUTPUT_DIR = os.path.join(BASE_DIR, "_weekly_data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "latest_data.json")


def get_company_code(symbol_dir):
    """从目录名解析股票代码"""
    # 去除后缀如 _2025年报
    code = re.sub(r'_.*$', '', symbol_dir)
    # 处理 .HK 后缀
    if 'HK' in code.upper():
        code = re.sub(r'^(\d+)', r'\1', code)
        code = re.sub(r'[^\d\.]', '', code)
        if not code.endswith('.HK'):
            code = code + '.HK'
    return code


def get_company_name(symbol_dir):
    """从目录下的报告文件名提取公司名称"""
    report_files = glob.glob(os.path.join(BASE_DIR, symbol_dir, "*.md"))
    for f in report_files:
        if 'data_pack' in f:
            continue
        try:
            with open(f, 'r', encoding='utf-8') as file:
                first_line = file.readline()
                match = re.search(r'#\s*(.+?)\s*[（(]', first_line)
                if match:
                    return match.group(1).strip()
        except:
            pass
    return symbol_dir


def call_mcp_tool(tool_name, params):
    """调用 MCP 工具"""
    try:
        # 通过导入方式调用
        from mcp_ai_tools import invoke_tool
        result = invoke_tool(tool_name, params)
        return result
    except Exception as e:
        print(f"    MCP调用失败 {tool_name}: {e}")
        return None


def parse_price_data(raw_data):
    """解析股价数据"""
    try:
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        if 'data' in data:
            stocks = json.loads(data['data'])
            if stocks.get('count', 0) > 0:
                stock = stocks['stocks'][0]
                return {
                    'current': float(stock.get('currentPrice', 0)),
                    'change_pct': float(stock.get('changePercent', 0)),
                    'volume': int(stock.get('volume', 0)),
                    'turnover': float(stock.get('turnover', 0))
                }
    except Exception as e:
        print(f"    解析股价数据失败: {e}")
    return None


def parse_notices(raw_data):
    """解析公告数据"""
    try:
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        if 'data' in data:
            notices = json.loads(data['data'])
            return [
                {
                    'title': n.get('title', ''),
                    'date': n.get('noticeDate', '')[:10],
                    'type': n.get('columnName', '')
                }
                for n in notices[:5]  # 只取最近5条
            ]
    except Exception as e:
        print(f"    解析公告数据失败: {e}")
    return []


def parse_reports(raw_data):
    """解析研报数据"""
    try:
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        if 'data' in data:
            reports = json.loads(data['data'])
            return [
                {
                    'title': r.get('title', ''),
                    'orgName': r.get('orgName', ''),
                    'date': r.get('publishDate', '')[:10],
                    'content': r.get('reportContent', '')[:500]  # 截断
                }
                for r in reports[:3]  # 只取最近3条
            ]
    except Exception as e:
        print(f"    解析研报数据失败: {e}")
    return []


def parse_money_flow(raw_data):
    """解析资金流向数据"""
    try:
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        if 'data' in data:
            flow = json.loads(data['data'])
            return {
                'mainInflow': float(flow.get('mainInflow', 0)),
                'superLargeInflow': float(flow.get('superLargeInflow', 0)),
                'largeInflow': float(flow.get('largeInflow', 0))
            }
    except Exception as e:
        print(f"    解析资金流向失败: {e}")
    return {}


def fetch_stock_data(stock_code, stock_name):
    """获取单只股票的完整数据"""
    result = {
        'name': stock_name,
        'price': None,
        'notices': [],
        'reports': [],
        'money_flow': {},
        'error': None
    }

    # 1. 获取股价
    try:
        print(f"  获取股价...")
        # 使用 subprocess 调用 claude mcp 工具
        import subprocess
        cmd = [
            'python3', '-c',
            f'''
import json
from mcp_ai_tools import invoke_tool
result = invoke_tool("QueryStockPriceInfo", {{"stockCodes": "{stock_code}"}})
print(json.dumps(result, ensure_ascii=False))
'''
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            result['price'] = parse_price_data(proc.stdout.strip())
    except Exception as e:
        result['error'] = f"股价获取失败: {e}"
        print(f"    失败: {e}")

    time.sleep(1)

    # 2. 获取公告
    try:
        print(f"  获取公告...")
        import subprocess
        cmd = [
            'python3', '-c',
            f'''
import json
from mcp_ai_tools import invoke_tool
result = invoke_tool("GetStockNotice", {{"stockCode": "{stock_code}", "pageSize": 5}})
print(json.dumps(result, ensure_ascii=False))
'''
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            result['notices'] = parse_notices(proc.stdout.strip())
    except Exception as e:
        print(f"    失败: {e}")

    time.sleep(1)

    # 3. 获取研报
    try:
        print(f"  获取研报...")
        import subprocess
        cmd = [
            'python3', '-c',
            f'''
import json
from mcp_ai_tools import invoke_tool
result = invoke_tool("GetStockResearchReport", {{"stockCode": "{stock_code}", "days": 7}})
print(json.dumps(result, ensure_ascii=False))
'''
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            result['reports'] = parse_reports(proc.stdout.strip())
    except Exception as e:
        print(f"    失败: {e}")

    time.sleep(1)

    # 4. 获取资金流向
    try:
        print(f"  获取资金流向...")
        import subprocess
        cmd = [
            'python3', '-c',
            f'''
import json
from mcp_ai_tools import invoke_tool
result = invoke_tool("GetStockMoneyFlowDetail", {{"stockCode": "{stock_code}"}})
print(json.dumps(result, ensure_ascii=False))
'''
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            result['money_flow'] = parse_money_flow(proc.stdout.strip())
    except Exception as e:
        print(f"    失败: {e}")

    return result


def fetch_macro_news():
    """获取全市场热点新闻"""
    try:
        import subprocess
        cmd = [
            'python3', '-c',
            '''
import json
from mcp_ai_tools import invoke_tool
result = invoke_tool("GetSinaFinanceNews", {"limit": 10})
print(json.dumps(result, ensure_ascii=False))
'''
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip())
            if 'data' in data:
                news = json.loads(data['data'])
                return [
                    {
                        'title': n.get('content', '')[:100],
                        'isRed': n.get('isRed', False),
                        'time': n.get('publishTime', '')
                    }
                    for n in news[:10]
                ]
    except Exception as e:
        print(f"获取宏观新闻失败: {e}")
    return []


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    today = datetime.now().strftime('%Y-%m-%d')
    print(f"=== 开始采集数据: {today} ===\n")

    # 获取所有公司目录
    company_dirs = [
        d for d in os.listdir(BASE_DIR)
        if os.path.isdir(os.path.join(BASE_DIR, d)) and not d.startswith('_')
    ]
    print(f"发现 {len(company_dirs)} 只关注标的\n")

    # 采集宏观新闻
    print("采集宏观新闻...")
    macro_news = fetch_macro_news()
    print(f"获取 {len(macro_news)} 条宏观新闻\n")

    # 采集每家公司数据
    all_data = {
        'fetch_date': today,
        'fetch_time': datetime.now().strftime('%H:%M:%S'),
        'macro_news': macro_news,
        'stocks': {}
    }

    for i, symbol_dir in enumerate(company_dirs, 1):
        stock_code = get_company_code(symbol_dir)
        stock_name = get_company_name(symbol_dir)

        print(f"[{i}/{len(company_dirs)}] {stock_code} ({stock_name})")

        stock_data = fetch_stock_data(stock_code, stock_name)
        all_data['stocks'][stock_code] = stock_data

        # 间隔避免限流
        if i < len(company_dirs):
            time.sleep(2)

        print()

    # 写入文件（覆盖式）
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"=== 数据采集完成 ===")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"共采集 {len(all_data['stocks'])} 家公司数据")

    # 统计成功率
    success = sum(1 for s in all_data['stocks'].values() if s.get('price'))
    print(f"股价数据获取成功: {success}/{len(all_data['stocks'])}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 测试数据采集脚本**

Run:
```bash
cd "/Users/apple/Documents/分析报告"
python3 "每周复盘重点关注/scripts/fetch_weekly_data.py"
```

Expected: 依次采集30家公司的股价、公告、研报、资金流向，最终生成 `latest_data.json`

- [ ] **Step 3: 验证输出文件**

Run:
```bash
ls -lh "/Users/apple/Documents/分析报告/每周复盘重点关注/_weekly_data/"
python3 -c "
import json
with open('/Users/apple/Documents/分析报告/每周复盘重点关注/_weekly_data/latest_data.json') as f:
    data = json.load(f)
print(f'日期: {data[\"fetch_date\"]}')
print(f'公司数: {len(data[\"stocks\"])}')
for code, info in list(data['stocks'].items())[:3]:
    print(f'  {code}: 股价={info.get(\"price\", {}).get(\"current\")}, 公告={len(info.get(\"notices\", []))}')
"
```

Expected: 看到 fetch_date、公司数量、前3家公司的股价和公告数量

---

### Task 3: 创建 weekly-review Skill

**Files:**
- Create: `.claude/skills/weekly-review/SKILL.md`

**Context:** Claude Code Skill，读取 `latest_data.json` 和原始分析报告，逐家生成周报。

- [ ] **Step 1: 编写 Skill 文件**

```markdown
---
name: "weekly-review"
description: "投资组合周报生成。遍历每周复盘重点关注目录下所有公司，读取最新采集数据和原始分析报告，生成轻量级周报（日期.md）。触发条件：用户输入 /weekly-review 或请求生成投资组合周报。"
---

# 投资组合周报生成 Skill

## 触发条件

当用户输入以下任一内容时触发：
1. `/weekly-review`
2. "生成周报"
3. "投资组合周报"
4. "每周复盘"

## 执行流程

### Phase 1: 读取数据

1. 读取 `每周复盘重点关注/_weekly_data/latest_data.json`
2. 获取 `fetch_date` 作为周报日期
3. 读取 `每周复盘重点关注/_watchlist.md` 确认关注池清单

### Phase 2: 逐家生成周报

对 `latest_data.json` 中 `stocks` 下的每家公司：

**Step 1: 读取原始分析报告**
- 找到 `每周复盘重点关注/{code}/` 目录下的原始分析报告（非 data_pack 文件）
- 提取：目标买入价、精算穿透回报率、安全边际、监控清单、后续跟踪事项

**Step 2: 读取最新数据**
- 从 `latest_data.json` 读取该公司的：
  - `price`: 当前股价、涨跌幅
  - `notices`: 近期公告
  - `reports`: 近期研报
  - `money_flow`: 资金流向
  - `error`: 采集错误（如有）

**Step 3: 分析对比**

1. **股价对比**：当前股价 vs 目标买入价
   - 计算当前距离目标价
   - 与原始报告中的距离目标价对比

2. **精算回报率更新**：
   - 原始精算回报率 × (原始目标价 / 当前股价)
   - 近似估算当前精算回报率（仅因股价变动）

3. **公告重大性判断**：
   - 检查公告标题关键词：回购、分红、增持、减持、高管变动、业绩、诉讼、担保
   - 标记重大事项

4. **研报评级变化**：
   - 提取最新研报的评级
   - 与原始报告中的机构观点对比

5. **资金流向判断**：
   - 主力资金净流入 > 0: 资金流入
   - 主力资金净流入 < 0: 资金流出
   - 超大单流向判断机构动向

6. **风险信号检查**（基于原始报告监控清单）：
   - 股价是否跌破关键支撑位
   - 是否出现新的负面公告
   - 资金是否持续大幅流出

**Step 4: 生成周报文件**

输出路径：`每周复盘重点关注/{code}/{fetch_date}.md`

周报格式：

```markdown
# {公司名}（{代码}）周报 — {日期}

## 一、本周股价
- 当前股价：¥{current_price}（周涨跌 {change_pct}%）
- 目标买入价：¥{target_price}（原始报告）
- 距离目标价：{distance}%（vs 原始 {original_distance}%）
- 精算回报率（估算）：{estimated_return}%（vs 原始 {original_return}%）

## 二、本周大事
### 公告（{N}条）
{每条公告的日期、类型、标题}

### 研报（{N}条）
{每条研报的日期、机构、评级、核心观点}

## 三、资金动向
- 主力资金净流入：{amount} 万元（{流入/流出}）
- 超大单净流入：{amount} 万元

## 四、风险信号检查
| 监控项 | 原始阈值 | 当前状态 | 触发 |
|:---|:---|:---|:---:|
| 股价相对目标价 | < {target} | ¥{current} | {是/否} |
| 负面公告 | 无 | {描述} | {是/否} |
| 资金大幅流出 | 无 | {描述} | {是/否} |

## 五、本周结论
**信号**：{🟢 正常 / 🟡 关注 / 🔴 告警}

**核心判断**：{1-2句}

**操作建议**：{维持 / 加仓 / 减仓 / 清仓 / 进一步观察}

**需跟踪事项**：
1. {事项1}
2. {事项2}
```

### Phase 3: 汇总报告

所有公司周报生成后，读取所有 `{date}.md` 文件，生成汇总报告：

输出路径：`每周复盘重点关注/_summary/{date}_汇总报告.md`

汇总报告结构：

```markdown
# 投资组合周报汇总 — {日期}

## 一、本周市场概览
{宏观新闻摘要}

## 二、关注池表现
- 关注标的数：{N} 只
- 平均涨跌幅：{N}%

## 三、信号统计
| 信号 | 数量 | 标的 |
|:---|:---:|:---|
| 🟢 正常 | {N} | {列表} |
| 🟡 关注 | {N} | {列表} |
| 🔴 告警 | {N} | {列表} |

## 四、本周重点事件
{重点事件列表}

## 五、操作建议
### 可建仓/加仓
{列表}

### 需减仓/清仓
{列表}

### 继续观察
{列表}

## 六、下周跟踪清单
{清单}
```

## 注意事项

1. **数据缺失处理**：如果 `latest_data.json` 中某字段缺失或报错，在周报中标注"数据缺失"，不阻塞其他公司
2. **覆盖机制**：如果该日期周报已存在，直接覆盖
3. **精算回报率估算**：仅基于股价变动做近似估算，不重新计算完整财务数据
4. **信号判定规则**：
   - 🟢 正常：无重大公告、资金未异常流出、股价未大幅偏离
   - 🟡 关注：有需关注公告、资金小幅流出、股价接近目标价
   - 🔴 告警：重大负面公告、资金大幅流出、股价跌破关键位
```

- [ ] **Step 2: 验证 Skill 文件可被识别**

Run:
```bash
ls -la "/Users/apple/.claude/skills/weekly-review/"
cat "/Users/apple/.claude/skills/weekly-review/SKILL.md" | head -20
```

Expected: 文件存在，内容正确

---

### Task 4: 创建邮件发送脚本

**Files:**
- Create: `每周复盘重点关注/scripts/send_email.py`

**Context:** 读取汇总报告文件，通过 QQ 邮箱 SMTP 发送邮件。

- [ ] **Step 1: 编写邮件发送脚本**

```python
#!/usr/bin/env python3
"""
邮件发送脚本
读取汇总报告，通过QQ邮箱SMTP发送
"""
import os
import sys
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime

BASE_DIR = "/Users/apple/Documents/分析报告/每周复盘重点关注"
SUMMARY_DIR = os.path.join(BASE_DIR, "_summary")

# 邮箱配置
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
SMTP_USER = "broccoli_ovo@qq.com"
SMTP_PASS = "xtqhbfdfhmnijbai"
RECIPIENT = "broccoli_ovo@qq.com"


def find_latest_summary():
    """找到最新的汇总报告"""
    if not os.path.exists(SUMMARY_DIR):
        return None

    files = [f for f in os.listdir(SUMMARY_DIR) if f.endswith('_汇总报告.md')]
    if not files:
        return None

    # 按文件名排序（日期格式 YYYY-MM-DD）
    files.sort(reverse=True)
    return os.path.join(SUMMARY_DIR, files[0])


def parse_summary_for_subject(filepath):
    """从汇总报告中提取信息用于邮件主题"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return None, 0, 0, 0

    # 提取日期
    date_match = re.search(r'投资组合周报汇总[—-]\s*(\d{4}-\d{2}-\d{2})', content)
    date_str = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')

    # 统计信号数量
    normal = len(re.findall(r'🟢\s*正常', content))
    warning = len(re.findall(r'🟡\s*关注', content))
    alert = len(re.findall(r'🔴\s*告警', content))

    return date_str, normal, warning, alert


def send_email(summary_path):
    """发送邮件"""
    date_str, normal, warning, alert = parse_summary_for_subject(summary_path)

    # 读取汇总报告内容
    with open(summary_path, 'r', encoding='utf-8') as f:
        report_content = f.read()

    # 构建邮件主题
    subject = f"[投资组合周报] {date_str} | 🟢{normal} 🟡{warning} 🔴{alert}"

    # 构建邮件正文（简化表格以兼容邮件客户端）
    body = f"""投资组合周报汇总 - {date_str}

========================================

{report_content}

========================================
本邮件由投资组合周报系统自动发送
"""

    # 创建邮件
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = RECIPIENT
    msg['Subject'] = subject

    # 添加正文
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    # 添加附件
    with open(summary_path, 'rb') as f:
        attachment = MIMEApplication(f.read())
        attachment.add_header(
            'Content-Disposition',
            'attachment',
            filename=os.path.basename(summary_path)
        )
        msg.attach(attachment)

    # 发送邮件
    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, RECIPIENT, msg.as_string())
        server.quit()
        print(f"✅ 邮件发送成功: {subject}")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False


def main():
    # 检查命令行参数
    if len(sys.argv) > 1:
        # 指定日期
        date_str = sys.argv[1]
        summary_path = os.path.join(SUMMARY_DIR, f"{date_str}_汇总报告.md")
        if not os.path.exists(summary_path):
            print(f"错误: 找不到汇总报告 {summary_path}")
            sys.exit(1)
    else:
        # 自动找最新的
        summary_path = find_latest_summary()
        if not summary_path:
            print("错误: 找不到汇总报告")
            sys.exit(1)

    print(f"准备发送: {summary_path}")
    success = send_email(summary_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 测试邮件发送脚本**

先创建一个测试汇总报告：

```bash
mkdir -p "/Users/apple/Documents/分析报告/每周复盘重点关注/_summary"
cat > "/Users/apple/Documents/分析报告/每周复盘重点关注/_summary/2026-05-29_汇总报告.md" << 'EOF'
# 投资组合周报汇总 — 2026-05-29

## 测试报告

这是一份测试汇总报告，用于验证邮件发送功能。

| 信号 | 数量 |
|:---|:---:|
| 🟢 正常 | 25 |
| 🟡 关注 | 3 |
| 🔴 告警 | 2 |
EOF
```

Run:
```bash
cd "/Users/apple/Documents/分析报告"
python3 "每周复盘重点关注/scripts/send_email.py" 2026-05-29
```

Expected: 输出"邮件发送成功"，用户邮箱收到测试邮件

---

### Task 5: 创建执行入口脚本

**Files:**
- Create: `每周复盘重点关注/scripts/run_weekly_review.sh`

**Context:** 一键执行完整流程的 shell 脚本。

- [ ] **Step 1: 编写执行脚本**

```bash
#!/bin/bash
# 投资组合周报一键执行脚本

set -e

PROJECT_DIR="/Users/apple/Documents/分析报告"
WATCH_DIR="${PROJECT_DIR}/每周复盘重点关注"
DATE=$(date +%Y-%m-%d)

echo "========================================"
echo "投资组合周报 - ${DATE}"
echo "========================================"
echo ""

# Step 1: 采集数据
echo "[Step 1/3] 采集最新数据..."
cd "${PROJECT_DIR}"
python3 "${WATCH_DIR}/scripts/fetch_weekly_data.py"
echo ""

# Step 2: 生成周报（需要用户在 Claude Code 中执行）
echo "[Step 2/3] 请在 Claude Code 中执行:"
echo "    /weekly-review"
echo ""
echo "    这将生成各公司周报和汇总报告"
echo ""

# Step 3: 发送邮件
echo "[Step 3/3] 发送邮件..."
python3 "${WATCH_DIR}/scripts/send_email.py" "${DATE}"
echo ""

echo "========================================"
echo "周报流程完成: ${DATE}"
echo "========================================"
```

- [ ] **Step 2: 添加执行权限**

Run:
```bash
chmod +x "/Users/apple/Documents/分析报告/每周复盘重点关注/scripts/run_weekly_review.sh"
```

---

## Self-Review

### Spec Coverage Check

| 设计文档章节 | 对应任务 | 状态 |
|:---|:---|:---:|
| 关注池筛选逻辑 | Task 1 | ✅ |
| 数据采集接口 | Task 2 | ✅ |
| 周报生成格式 | Task 3 (Skill) | ✅ |
| 汇总报告格式 | Task 3 (Skill) | ✅ |
| 邮件发送配置 | Task 4 | ✅ |
| 覆盖机制 | Task 2 | ✅ |
| 错误处理 | 各任务中 | ✅ |

### Placeholder Scan

- 无 "TBD"、"TODO"、"implement later"
- 所有代码块包含完整实现
- 所有命令包含预期输出

### Type Consistency

- `latest_data.json` 结构在 Task 2 中定义，Task 3 Skill 中引用一致
- 文件路径使用统一的 BASE_DIR 常量
- 日期格式统一为 YYYY-MM-DD

---

## 执行选项

**Plan complete and saved to `docs/superpowers/plans/2026-05-29-portfolio-weekly-review.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints for review

**Which approach?**
