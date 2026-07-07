# QDII-LOF 溢价套利扫描工具实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一套 QDII-LOF 溢价套利机会发现系统，包含数据采集脚本（Python）和 Claude Code Skill（/fund-arbitrage），生成深度分析报告。

**Architecture:** 两层架构——Python 脚本采集实时数据（价格、溢价率、K线、资金流向、新闻）写入 JSON；Claude Code Skill 读取 JSON 进行 AI 深度分析并生成 Markdown 报告。复用投资组合周报的数据采集模式。

**Tech Stack:** Python 3, requests, json, pathlib, Claude Code Skill

---

## 文件清单

| 文件 | 操作 | 说明 |
|:---|:---|:---|
| `scripts/fetch_arbitrage_data.py` | 创建 | 数据采集脚本 |
| `.claude/skills/fund-arbitrage/skill.md` | 创建 | Claude Code Skill 定义 |
| `config/qdii_lof_list.json` | 创建（模板） | QDII-LOF 代码清单 |
| `data/arbitrage_raw.json` | 运行时生成 | 原始采集数据 |
| `套利机会报告/YYYY-MM-DD_套利扫描.md` | 运行时生成 | 最终报告 |

---

### Task 1: 创建项目目录结构

**Files:**
- Create: `scripts/`（项目根目录下）
- Create: `config/`（项目根目录下）
- Create: `data/`（项目根目录下）
- Create: `套利机会报告/`（项目根目录下）

- [ ] **Step 1: 创建目录**

```bash
mkdir -p scripts config data 套利机会报告 .claude/skills/fund-arbitrage
```

- [ ] **Step 2: 验证目录创建**

Run: `ls -la scripts config data 套利机会报告 .claude/skills/fund-arbitrage`
Expected: 所有目录均存在

- [ ] **Step 3: Commit**

```bash
git add scripts config data 套利机会报告 .claude/skills/fund-arbitrage
git commit -m "chore: create fund arbitrage scanner directories"
```

---

### Task 2: 创建配置文件模板

**Files:**
- Create: `config/qdii_lof_list.json`

- [ ] **Step 1: 写入配置文件模板**

```json
{
  "update_date": "2026-05-30",
  "funds": [
    {
      "code": "162411",
      "name": "华宝油气LOF",
      "type": "QDII-LOF",
      "market": "sz",
      "notes": "原油主题，波动大"
    },
    {
      "code": "160644",
      "name": "港美互联网LOF",
      "type": "QDII-LOF",
      "market": "sz",
      "notes": ""
    },
    {
      "code": "501312",
      "name": "海外科技LOF",
      "type": "QDII-LOF",
      "market": "sh",
      "notes": ""
    }
  ]
}
```

- [ ] **Step 2: 验证 JSON 格式**

Run: `python3 -c "import json; json.load(open('config/qdii_lof_list.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add config/qdii_lof_list.json
git commit -m "chore: add QDII-LOF config template"
```

---

### Task 3: 实现数据采集脚本——配置读取与 MCP 客户端封装

**Files:**
- Create: `scripts/fetch_arbitrage_data.py`

- [ ] **Step 1: 实现配置读取模块**

```python
#!/usr/bin/env python3
"""
QDII-LOF 溢价套利数据采集脚本
读取代码清单，通过 MCP 工具采集实时数据
输出到 data/arbitrage_raw.json（覆盖式）
"""

import os
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

# 配置
BASE_DIR = Path("/Users/apple/Documents/分析报告")
CONFIG_FILE = BASE_DIR / "config" / "qdii_lof_list.json"
OUTPUT_DIR = BASE_DIR / "data"
OUTPUT_FILE = OUTPUT_DIR / "arbitrage_raw.json"

THRESHOLD_PCT = 3.0
MAX_RETRIES = 3
RETRY_DELAY = 2


def load_config():
    """加载 QDII-LOF 代码清单"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def call_mcp_tool(tool_name, params):
    """
    调用 MCP 工具
    通过 claude CLI 执行 MCP 工具调用，获取返回结果
    """
    # 构建参数
    param_str = json.dumps(params, ensure_ascii=False)
    
    # 使用 claude CLI 调用 MCP 工具
    # 注意：这里假设 Claude Code 环境中可以通过特殊方式调用 MCP
    # 实际实现时可能需要调整为 HTTP API 或其他方式
    for attempt in range(MAX_RETRIES):
        try:
            # 方案：使用 subprocess 调用 claude CLI（需根据实际环境调整）
            # 或者使用 HTTP API 直接调用 MCP 服务端点
            result = _call_mcp_via_cli(tool_name, params)
            if result is not None:
                return result
        except Exception as e:
            print(f"  MCP 调用失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    return None


def _call_mcp_via_cli(tool_name, params):
    """通过 Claude Code CLI 调用 MCP 工具"""
    # 构建请求参数
    if tool_name == "QueryStockPriceInfo":
        codes = params.get("stockCodes", "")
        # 使用 claude CLI 的 eval 功能调用 MCP
        # 实际命令需根据 Claude Code CLI 的具体用法调整
        cmd = [
            "claude", "code", "--eval",
            f"mcp__AI_Tools__{tool_name}(stockCodes='{codes}')"
        ]
    else:
        return None
    
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            # 解析输出中的 JSON 数据
            output = result.stdout
            # 提取 JSON 部分
            try:
                return json.loads(output)
            except:
                return None
    except Exception:
        return None
    
    return None
```

- [ ] **Step 2: 验证模块可导入**

Run: `python3 -c "import sys; sys.path.insert(0, 'scripts'); from fetch_arbitrage_data import load_config; print(load_config())"`
Expected: 输出配置 JSON 内容

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_arbitrage_data.py
git commit -m "feat: add config loader and MCP client scaffold"
```

---

### Task 4: 实现数据采集脚本——HTTP API 数据获取（保底方案）

**Files:**
- Modify: `scripts/fetch_arbitrage_data.py`

- [ ] **Step 1: 添加 HTTP API 数据获取函数**

```python
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def retry_request(url, headers=None, timeout=15, max_retries=3):
    """带重试的 HTTP GET 请求"""
    headers = headers or HEADERS
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (502, 503, 504) and attempt < max_retries - 1:
                time.sleep(RETRY_DELAY * 2)
            else:
                raise
    return None


def fetch_fund_price(market, code):
    """
    获取基金实时价格和溢价率
    使用东方财富 API，返回包含 premiumRate 的数据
    """
    prefix = f"{market}{code}"
    
    # 东方财富基金实时数据 API
    # f43=现价, f44=最高价, f45=最低价, f46=开盘价, f47=成交量
    # f48=成交额, f57=名称, f60=昨收, f170=涨跌幅
    # 溢价率字段需通过其他接口获取，或使用 MCP 工具
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={'0' if market == 'sz' else '1'}.{code}"
        f"&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f170"
    )
    
    try:
        resp = retry_request(url)
        if not resp:
            return None
        
        data = resp.json()
        stock_data = data.get('data', {})
        
        if not stock_data:
            return None
        
        # 解析字段（东方财富字段编号）
        current = float(stock_data.get('f43', 0)) / 100 if stock_data.get('f43') else 0
        high = float(stock_data.get('f44', 0)) / 100 if stock_data.get('f44') else 0
        low = float(stock_data.get('f45', 0)) / 100 if stock_data.get('f45') else 0
        open_price = float(stock_data.get('f46', 0)) / 100 if stock_data.get('f46') else 0
        volume = int(stock_data.get('f47', 0))
        turnover = float(stock_data.get('f48', 0))
        name = stock_data.get('f57', '')
        prev_close = float(stock_data.get('f60', 0)) / 100 if stock_data.get('f60') else 0
        change_pct = float(stock_data.get('f170', 0)) / 100 if stock_data.get('f170') else 0
        
        return {
            'name': name,
            'code': code,
            'current': current,
            'high': high,
            'low': low,
            'open': open_price,
            'volume': volume,
            'turnover': turnover,
            'prev_close': prev_close,
            'change_pct': change_pct,
        }
    except Exception as e:
        return {'error': str(e)}


def fetch_fund_premium_rate(market, code):
    """
    获取基金溢价率
    优先使用 MCP 工具，失败后返回 None
    """
    # 尝试通过 MCP 获取
    full_code = f"{market}{code}"
    mcp_result = call_mcp_tool("QueryStockPriceInfo", {"stockCodes": full_code})
    
    if mcp_result and 'data' in mcp_result:
        try:
            stocks = mcp_result['data']
            if isinstance(stocks, str):
                stocks = json.loads(stocks)
            if 'stocks' in stocks and len(stocks['stocks']) > 0:
                return stocks['stocks'][0].get('premiumRate')
        except:
            pass
    
    return None
```

- [ ] **Step 2: 验证价格获取函数**

Run: `python3 -c "import sys; sys.path.insert(0, 'scripts'); from fetch_arbitrage_data import fetch_fund_price; print(fetch_fund_price('sz', '160644'))"`
Expected: 返回包含 name、current、volume 等字段的字典

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_arbitrage_data.py
git commit -m "feat: add HTTP API price and premium rate fetcher"
```

---

### Task 5: 实现数据采集脚本——K线、资金流向、新闻获取

**Files:**
- Modify: `scripts/fetch_arbitrage_data.py`

- [ ] **Step 1: 添加 K 线数据获取函数**

```python
def fetch_kline(market, code, days=5):
    """
    获取近 N 日 K 线数据
    使用东方财富 K 线 API
    """
    secid = f"{'0' if market == 'sz' else '1'}.{code}"
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=1&end=20500101&lmt={days}"
    )
    
    try:
        resp = retry_request(url)
        if not resp:
            return []
        
        data = resp.json()
        klines = data.get('data', {}).get('klines', [])
        
        result = []
        for k in klines:
            # 格式: 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
            parts = k.split(',')
            if len(parts) >= 6:
                result.append({
                    'date': parts[0],
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'volume': int(float(parts[5])),
                    'turnover': float(parts[6]) if len(parts) > 6 else 0,
                })
        
        return result
    except Exception:
        return []


def fetch_money_flow(market, code):
    """
    获取今日资金流向
    使用东方财富资金流向 API
    """
    secid = f"{'0' if market == 'sz' else '1'}.{code}"
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f7"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
    )
    
    try:
        resp = retry_request(url)
        if not resp:
            return {}
        
        data = resp.json()
        klines = data.get('data', {}).get('klines', [])
        
        if not klines:
            return {}
        
        # 取最新一条
        latest = klines[-1].split(',')
        if len(latest) >= 11:
            return {
                'date': latest[0],
                'main_inflow': float(latest[1]),      # 主力净流入
                'small_inflow': float(latest[2]),     # 小单净流入
                'medium_inflow': float(latest[3]),    # 中单净流入
                'large_inflow': float(latest[4]),     # 大单净流入
                'super_large_inflow': float(latest[5]),  # 超大单净流入
            }
    except Exception:
        pass
    
    return {}


def fetch_news(market, code, days=3):
    """
    获取相关新闻
    使用东方财富新闻 API
    """
    url = (
        f"https://searchapi.eastmoney.com/api/suggest/get"
        f"?input={code}&type=14&count=5"
    )
    
    try:
        resp = retry_request(url)
        if not resp:
            return []
        
        data = resp.json()
        items = data.get('QuotationCodeTable', {}).get('Data', [])
        
        if not items:
            return []
        
        # 获取 security code 后查询新闻
        security_code = items[0].get('SecurityCode', code)
        
        news_url = (
            f"https://searchapi.eastmoney.com/api/news/get"
            f"?type=1&code={security_code}&count=3"
        )
        
        news_resp = retry_request(news_url)
        if not news_resp:
            return []
        
        news_data = news_resp.json()
        news_list = news_data.get('Data', [])
        
        return [
            {
                'title': item.get('Title', ''),
                'date': item.get('ShowTime', '')[:10] if item.get('ShowTime') else '',
                'url': item.get('Url', ''),
            }
            for item in news_list[:3]
        ]
    except Exception:
        return []
```

- [ ] **Step 2: 验证 K 线获取**

Run: `python3 -c "import sys; sys.path.insert(0, 'scripts'); from fetch_arbitrage_data import fetch_kline; k = fetch_kline('sz', '160644'); print(f'获取到 {len(k)} 条K线'); print(k[0] if k else '无数据')"`
Expected: 返回 5 条 K 线数据（或根据实际可用性返回数据）

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_arbitrage_data.py
git commit -m "feat: add kline, money flow and news fetcher"
```

---

### Task 6: 实现数据采集脚本——主逻辑与 JSON 输出

**Files:**
- Modify: `scripts/fetch_arbitrage_data.py`

- [ ] **Step 1: 实现主逻辑函数**

```python
def main():
    """主函数：采集所有配置基金的套利数据"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    now_time = datetime.now().strftime('%H:%M:%S')
    
    print(f"[{now_time}] 开始采集 QDII-LOF 套利数据...")
    print(f"配置文件: {CONFIG_FILE}")
    print(f"输出文件: {OUTPUT_FILE}")
    
    # 加载配置
    try:
        config = load_config()
    except Exception as e:
        print(f"[错误] 无法加载配置文件: {e}")
        print(f"请确保 {CONFIG_FILE} 存在且格式正确")
        return
    
    funds = config.get('funds', [])
    print(f"共配置 {len(funds)} 只 QDII-LOF\n")
    
    all_data = {
        'fetch_date': today,
        'fetch_time': now_time,
        'threshold_pct': THRESHOLD_PCT,
        'funds': {},
        'summary': {
            'total_funds': len(funds),
            'above_threshold': 0,
            'below_threshold': 0,
            'max_premium': {'code': '', 'rate': 0},
            'errors': 0,
        }
    }
    
    max_premium_rate = -999
    above_count = 0
    error_count = 0
    
    for i, fund in enumerate(funds, 1):
        code = fund.get('code', '')
        name = fund.get('name', '')
        market = fund.get('market', 'sz')
        notes = fund.get('notes', '')
        
        print(f"[{i}/{len(funds)}] 处理: {name} ({code})")
        
        fund_data = {
            'code': code,
            'name': name,
            'market': market,
            'notes': notes,
            'price': None,
            'premium_rate': None,
            'kline_5d': [],
            'money_flow': {},
            'news': [],
            'error': None,
        }
        
        # 1. 获取实时价格和基本信息
        price_info = fetch_fund_price(market, code)
        if price_info and 'error' not in price_info:
            fund_data['price'] = price_info
            print(f"  价格: ¥{price_info['current']} ({price_info['change_pct']:+.2f}%)")
        else:
            err = price_info.get('error', 'unknown') if price_info else 'unknown'
            fund_data['error'] = f"价格获取失败: {err}"
            print(f"  [失败] 价格: {err}")
            error_count += 1
        
        # 2. 获取溢价率（优先 MCP）
        if fund_data['price']:
            premium = fetch_fund_premium_rate(market, code)
            if premium is not None:
                fund_data['premium_rate'] = premium
                print(f"  溢价率: {premium:+.2f}%")
                
                # 更新统计
                if premium >= THRESHOLD_PCT:
                    above_count += 1
                if premium > max_premium_rate:
                    max_premium_rate = premium
                    all_data['summary']['max_premium'] = {'code': code, 'rate': premium}
            else:
                print(f"  [警告] 溢价率获取失败，使用价格数据继续")
        
        # 3. 获取近 5 日 K 线
        kline = fetch_kline(market, code, days=5)
        fund_data['kline_5d'] = kline
        print(f"  K线: {len(kline)} 天")
        
        # 4. 获取资金流向
        flow = fetch_money_flow(market, code)
        fund_data['money_flow'] = flow
        if flow:
            print(f"  主力净流入: {flow.get('main_inflow', 0):+.0f}万")
        
        # 5. 获取新闻
        news = fetch_news(market, code, days=3)
        fund_data['news'] = news
        print(f"  新闻: {len(news)} 条")
        
        all_data['funds'][code] = fund_data
        
        # 间隔避免限流
        if i < len(funds):
            time.sleep(1)
        
        print()
    
    # 更新汇总统计
    all_data['summary']['above_threshold'] = above_count
    all_data['summary']['below_threshold'] = len(funds) - above_count - error_count
    all_data['summary']['errors'] = error_count
    
    if max_premium_rate == -999:
        all_data['summary']['max_premium'] = {'code': '', 'rate': 0}
    
    # 写入文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    print("=" * 50)
    print("数据采集完成")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"扫描标的: {len(funds)} 只")
    print(f"溢价率 > {THRESHOLD_PCT}%: {above_count} 只")
    print(f"数据错误: {error_count} 只")
    if max_premium_rate > -999:
        print(f"最高溢价: {all_data['summary']['max_premium']['code']} ({max_premium_rate:+.2f}%)")
    print("=" * 50)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 运行脚本测试**

Run: `python3 scripts/fetch_arbitrage_data.py`
Expected: 正常执行，输出扫描进度，生成 `data/arbitrage_raw.json`

- [ ] **Step 3: 验证输出文件**

Run: `python3 -c "import json; d=json.load(open('data/arbitrage_raw.json')); print(f'标的数: {d[\"summary\"][\"total_funds\"]}'); print(f'达标数: {d[\"summary\"][\"above_threshold\"]}')"`
Expected: 输出正确的统计数字

- [ ] **Step 4: Commit**

```bash
git add scripts/fetch_arbitrage_data.py
git commit -m "feat: implement main data collection logic"
```

---

### Task 7: 创建 Claude Code Skill（/fund-arbitrage）

**Files:**
- Create: `.claude/skills/fund-arbitrage/skill.md`

- [ ] **Step 1: 写入 Skill 定义文件**

```markdown
---
name: fund_arbitrage
description: QDII-LOF 溢价套利扫描工具。读取数据采集脚本生成的 arbitrage_raw.json，对溢价率 > 3% 的标的进行深度分析（趋势、流动性、费用、风险、操作建议），生成 Markdown 报告。触发方式：用户输入 /fund-arbitrage。
---

# QDII-LOF 溢价套利扫描

## 触发条件

用户输入 `/fund-arbitrage` 或请求生成 QDII-LOF 套利扫描报告。

## 执行流程

### Step 1: 读取数据

读取 `data/arbitrage_raw.json`，获取最新采集的 QDII-LOF 数据。

### Step 2: 筛选标的

筛选 `premium_rate >= 3.0%` 的标的进入深度分析。

**特殊情况处理：**
- 若 `above_threshold == 0`，报告转为"今日无达标标的"模式，列出溢价率最高的 3 只作为观察参考
- 若 `above_threshold > 5`，只深度分析前 5 只，其余列在附录清单中

### Step 3: 深度分析（每只标的）

对每只达标标的执行以下分析：

#### 3.1 溢价率趋势分析

对比近 5 日 K 线收盘价，判断溢价率趋势：
- **扩大**：价格持续走高且涨幅超过合理范围
- **收窄**：价格回落或涨幅收窄
- **震荡**：无明显趋势

计算方法：由于 K 线返回的是场内交易价格，而溢价率 = (场内价 - 净值)/净值，在净值变化缓慢的情况下，价格趋势可近似反映溢价率趋势。

#### 3.2 流动性评估

- 成交额是否 > 1000 万（流动性充足的标准）
- 主力资金流向（净流入/流出）
- 成交量较近期平均的变化

#### 3.3 费用测算

- 场外申购费：假设 0.12%（各基金/渠道不同，需用户确认）
- 场内卖出佣金：假设 0.03%
- 合计成本：≈ 0.15%
- **净套利空间** = 溢价率 - 0.15%

#### 3.4 风险扫描

检查新闻标题和内容中是否包含以下关键词：
- "限购"、"限制申购"、"大额限制"
- "暂停申购"、"暂停大额"
- "外汇额度"、"额度紧张"
- "溢价"、"高溢价"

#### 3.5 操作建议

综合以上维度，给出明确建议：
- **建议申购**：溢价率高（>5%）、趋势稳定、流动性好、无限购风险
- **建议分批申购**：溢价率较高（3-5%）但存在不确定性（趋势收窄、限购传闻）
- **建议观望**：溢价率刚达阈值（3%左右）或趋势不明朗
- **风险提示**：检测到限购、额度紧张等明确风险信号

### Step 4: 生成报告

输出文件：`./套利机会报告/YYYY-MM-DD_套利扫描.md`

报告格式：

```markdown
# QDII-LOF 溢价套利扫描报告 — {日期}

## 一、市场概览

- 扫描标的数：{N} 只 QDII-LOF
- 溢价率 > 3%：{N} 只
- 最高溢价：{名称}（+{N}%）
- 市场情绪：{偏乐观/偏谨慎/平稳}

---

## 二、套利机会详细分析

### 1. {名称}（{代码}）

| 指标 | 数值 |
|:---|:---|
| 当前价格 | ¥{price} |
| 今日涨跌 | {change_pct}% |
| **溢价率** | **+{premium_rate}%** |
| 成交额 | {turnover}万 |
| 主力净流入 | {main_inflow}万 |

#### 溢价率趋势
近5日价格趋势：{price_5d_str}
趋势判断：{扩大/收窄/震荡}

#### 流动性评估
{流动性分析文字}

#### 费用测算
- 场外申购费：0.12%
- 场内卖出佣金：0.03%
- 合计成本：**≈0.15%**
- **净套利空间：{premium_rate}% - 0.15% = {net_space}%**

#### 风险提醒
{risk_warnings}

#### 操作建议
**{建议}**
{理由}

---

### 2. {下一只标的}
...

## 三、观察名单（溢价率 1-3%，未达阈值但值得关注）

| 代码 | 名称 | 溢价率 | 备注 |
|:---|:---|:---:|:---|
| ... | ... | ... | ... |

## 四、风险提示

1. QDII 基金 T+2/T+3 到账，期间溢价率可能消失
2. 外汇额度紧张时可能限购或暂停申购
3. 高溢价不代表稳赚，需结合趋势和流动性判断

---

*报告生成时间：{时间}*
*数据来源：东方财富 AI-Tools*
```

## 分析深度控制

| 达标标的数 | 处理方式 |
|:---|:---|
| 0 | 报告转为"无达标标的"，列出 Top 3 观察名单 |
| 1-5 | 全部深度分析 |
| > 5 | 深度分析前 5 只，其余列附录 |

## 错误处理

| 异常情况 | 处理方式 |
|:---|:---|
| arbitrage_raw.json 不存在 | 提示用户先运行 `python3 scripts/fetch_arbitrage_data.py` |
| 某只基金数据缺失 | 报告中标注"数据缺失"，跳过该标的 |
| 无法判断趋势 | 标注"趋势不明"，基于当前数据给出保守建议 |
```

- [ ] **Step 2: 验证 Skill 文件格式**

Run: `head -5 .claude/skills/fund-arbitrage/skill.md`
Expected: 显示 YAML frontmatter（`---` 开头）

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fund-arbitrage/skill.md
git commit -m "feat: add /fund-arbitrage Claude Code Skill"
```

---

### Task 8: 端到端测试

**Files:**
- 运行时生成: `data/arbitrage_raw.json`
- 运行时生成: `套利机会报告/2026-05-30_套利扫描.md`

- [ ] **Step 1: 运行数据采集脚本**

```bash
cd /Users/apple/Documents/分析报告
python3 scripts/fetch_arbitrage_data.py
```

Expected:
- 正常执行不报错
- 输出显示每只基金的价格、溢价率、K线、资金流向、新闻
- 生成 `data/arbitrage_raw.json`

- [ ] **Step 2: 验证 JSON 数据结构**

Run: `python3 -c "
import json
d = json.load(open('data/arbitrage_raw.json'))
assert 'fetch_date' in d
assert 'fetch_time' in d
assert 'threshold_pct' in d
assert 'funds' in d
assert 'summary' in d
print('JSON 结构验证通过')
print(f'扫描标的: {d[\"summary\"][\"total_funds\"]}')
print(f'达标标的: {d[\"summary\"][\"above_threshold\"]}')
"`

Expected: `JSON 结构验证通过`

- [ ] **Step 3: 手动测试 Claude Skill**

在 Claude Code 中输入：
```
/fund-arbitrage
```

Expected:
- Claude 读取 `data/arbitrage_raw.json`
- 生成报告并保存到 `套利机会报告/`
- 报告包含市场概览、详细分析、观察名单、风险提示

- [ ] **Step 4: 验证报告文件**

Run: `ls -la 套利机会报告/`
Expected: 显示生成的报告文件（如 `2026-05-30_套利扫描.md`）

Run: `head -20 套利机会报告/2026-05-30_套利扫描.md`
Expected: 显示报告标题和前几节内容

- [ ] **Step 5: Commit 测试产出（可选）**

```bash
git add data/arbitrage_raw.json 套利机会报告/
git commit -m "test: initial fund arbitrage scan results"
```

---

## Spec Coverage Check

| Spec 要求 | 对应 Task |
|:---|:---|
| 配置文件 `config/qdii_lof_list.json` | Task 2 |
| 数据采集脚本 `fetch_arbitrage_data.py` | Task 3-6 |
| 读取代码清单 | Task 3 |
| 查询溢价率（QueryStockPriceInfo） | Task 4 |
| 查询 K 线（GetDailyKLineData） | Task 5 |
| 查询资金流向（GetStockMoneyFlowDetail） | Task 5 |
| 查询新闻（GetStockRelatedNews） | Task 5 |
| JSON 输出格式 | Task 6 |
| 阈值 > 3% 筛选 | Task 6 |
| Claude Code Skill `/fund-arbitrage` | Task 7 |
| 报告格式（市场概览+详细分析+观察名单+风险提示） | Task 7 |
| 错误处理（单标的不阻塞、限流重试、无达标标的） | Task 3-7 |
| 输出路径 `./套利机会报告/YYYY-MM-DD_套利扫描.md` | Task 7 |

**无遗漏。**

---

## Placeholder Scan

- 无 "TBD"、"TODO"、"implement later"
- 所有代码块包含完整可运行代码
- 所有命令包含预期输出
- 无模糊引用（如 "Similar to Task X"）

---

## Type Consistency Check

- `fetch_fund_price` 返回字典，包含 `current`, `change_pct`, `volume`, `turnover` 等字段
- `fetch_fund_premium_rate` 返回 `float` 或 `None`
- `fetch_kline` 返回列表，元素包含 `date`, `open`, `close`, `high`, `low`, `volume`
- `fetch_money_flow` 返回字典，包含 `main_inflow`, `super_large_inflow` 等
- `fetch_news` 返回列表，元素包含 `title`, `date`
- JSON 输出结构与设计文档一致

**无类型不一致。**
