#!/usr/bin/env python3
"""
投资组合周报数据采集脚本
遍历关注池所有公司，采集股价、公告、研报、资金流向数据
输出到 _weekly_data/latest_data.json（覆盖式）

数据源：
- 股价：腾讯财经 API（https://qt.gtimg.cn/）
- 公告：东方财富数据中心（带重试和降级）
- 研报：东方财富研报中心（带重试和降级）
- 资金流向：东方财富（带重试和降级）
"""

import os
import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# 配置
BASE_DIR = Path("/Users/apple/Documents/分析报告/每周复盘重点关注")
OUTPUT_DIR = BASE_DIR / "_weekly_data"
OUTPUT_FILE = OUTPUT_DIR / "latest_data.json"

TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def get_company_dirs():
    """获取所有公司目录（排除系统目录）"""
    companies = []
    for d in BASE_DIR.iterdir():
        if d.is_dir() and not d.name.startswith('_') and d.name != 'scripts':
            companies.append(d.name)
    return sorted(companies)


def parse_stock_code(dir_name):
    """从目录名解析股票代码和市场"""
    # 纯数字：A股
    if re.match(r'^\d{6}$', dir_name):
        market = 'sh' if dir_name.startswith(('6', '5', '9')) else 'sz'
        return market, dir_name
    # 含 .HK 或 HK
    hk_match = re.match(r'^(\d{4,5})\.?HK$', dir_name, re.I)
    if hk_match:
        return 'hk', hk_match.group(1)
    # 中文名（需要找报告文件提取代码）
    return None, dir_name


def get_code_from_report(dir_name):
    """从报告文件中提取股票代码"""
    report_dir = BASE_DIR / dir_name
    for f in report_dir.glob('*.md'):
        if 'data_pack' in f.name:
            continue
        try:
            with open(f, 'r', encoding='utf-8') as file:
                first_line = file.readline()
                # 匹配 "# 公司名（代码）" 或 "# 公司名（代码.SZ/SH）"
                m = re.search(r'[（(](\d{6})(?:\.SZ|\.SH)?[）)]', first_line)
                if m:
                    code = m.group(1)
                    market = 'sh' if code.startswith(('6', '5', '9')) else 'sz'
                    return market, code
        except:
            pass
    return None, dir_name


def retry_request(url, headers=None, timeout=TIMEOUT, max_retries=MAX_RETRIES):
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


def fetch_tencent_price(market, code):
    """从腾讯财经获取实时股价"""
    prefix = 'sh' if market == 'sh' else 'sz'
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    try:
        resp = retry_request(url)
        if not resp:
            return None
        text = resp.text
        # 解析 v_sh600519="1~贵州茅台~600519~1326.00~..."
        pattern = rf'v_{prefix}{code}="([^"]+)"'
        m = re.search(pattern, text)
        if not m:
            return None
        parts = m.group(1).split('~')
        if len(parts) < 45:
            return None
        return {
            'name': parts[1],
            'code': parts[2],
            'current': float(parts[3]),
            'prev_close': float(parts[4]),
            'open': float(parts[5]),
            'high': float(parts[33]),
            'low': float(parts[34]),
            'volume': int(parts[6]),
            'turnover': float(parts[37]) if parts[37] else 0,
            'change_pct': round((float(parts[3]) - float(parts[4])) / float(parts[4]) * 100, 2) if float(parts[4]) > 0 else 0,
        }
    except Exception as e:
        return {'error': str(e)}


def fetch_eastmoney_notices(code):
    """从东方财富获取公告（使用 np-anotice-stock API）"""
    url = (
        f"https://np-anotice-stock.eastmoney.com/api/security/ann"
        f"?page_size=5&page_index=1&stock_list={code}"
    )
    try:
        resp = retry_request(url)
        if not resp:
            return []
        data = resp.json()
        items = data.get('data', {}).get('list', [])
        return [
            {
                'title': item.get('title', ''),
                'date': item.get('notice_date', '')[:10] if item.get('notice_date') else '',
                'type': '公告'
            }
            for item in items[:5]
        ]
    except Exception:
        return []


def fetch_eastmoney_reports(code):
    """从东方财富获取研报（带完整参数）"""
    begin_time = datetime.now().replace(year=datetime.now().year - 1).strftime('%Y-%m-%d')
    end_time = datetime.now().strftime('%Y-%m-%d')
    url = (
        f"https://reportapi.eastmoney.com/report/list"
        f"?industryCode=*&pageNo=1&pageSize=3&code={code}"
        f"&beginTime={begin_time}&endTime={end_time}&qType=0"
    )
    try:
        resp = retry_request(url)
        if not resp:
            return []
        data = resp.json()
        items = data.get('data', [])
        return [
            {
                'title': item.get('title', ''),
                'org': item.get('orgSName', ''),
                'date': item.get('publishDate', '')[:10] if item.get('publishDate') else '',
                'rating': item.get('emRatingName', '')
            }
            for item in items[:3]
        ]
    except Exception:
        return []


def fetch_money_flow(code, market):
    """从东方财富获取资金流向（当前网络环境可能不可用，返回空）"""
    # 该API在当前网络环境下连接被重置，暂时返回空数据
    # secid = f"1.{code}" if market == 'sh' else f"0.{code}"
    # url = (
    #     f"https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    #     f"?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
    # )
    return {}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    now_time = datetime.now().strftime('%H:%M:%S')

    print(f"[{now_time}] 开始采集投资组合周报数据...")
    print(f"输出目录: {OUTPUT_DIR}")

    company_dirs = get_company_dirs()
    print(f"发现 {len(company_dirs)} 个关注标的\n")

    all_data = {
        'fetch_date': today,
        'fetch_time': now_time,
        'stocks': {}
    }

    success_count = 0

    for i, dir_name in enumerate(company_dirs, 1):
        print(f"[{i}/{len(company_dirs)}] 处理: {dir_name}")

        # 解析股票代码
        market, code = parse_stock_code(dir_name)
        if market is None:
            market, code = get_code_from_report(dir_name)

        if market is None:
            print(f"  [跳过] 无法解析股票代码: {dir_name}")
            continue

        stock_data = {
            'dir_name': dir_name,
            'market': market,
            'code': code,
            'price': None,
            'notices': [],
            'reports': [],
            'money_flow': {},
            'error': None
        }

        # 1. 获取股价（腾讯API，最可靠）
        if market in ('sh', 'sz'):
            price = fetch_tencent_price(market, code)
            if price and 'error' not in price:
                stock_data['price'] = price
                print(f"  股价: ¥{price['current']} ({price['change_pct']:+.2f}%)")
            else:
                stock_data['error'] = f"股价获取失败: {price.get('error', 'unknown') if price else 'unknown'}"
                print(f"  [失败] 股价: {stock_data['error']}")
        else:
            stock_data['error'] = "暂不支持港股"
            print(f"  [跳过] 港股暂不支持")

        # 2. 获取公告（东方财富）
        if market in ('sh', 'sz'):
            notices = fetch_eastmoney_notices(code)
            stock_data['notices'] = notices
            print(f"  公告: {len(notices)} 条")

        # 3. 获取研报（东方财富）
        if market in ('sh', 'sz'):
            reports = fetch_eastmoney_reports(code)
            stock_data['reports'] = reports
            print(f"  研报: {len(reports)} 条")

        # 4. 获取资金流向
        if market in ('sh', 'sz'):
            flow = fetch_money_flow(code, market)
            stock_data['money_flow'] = flow
            if flow:
                print(f"  资金流向: 主力{flow.get('main_net', 0):+.0f}万")

        all_data['stocks'][code] = stock_data

        if stock_data['price']:
            success_count += 1

        # 间隔避免限流
        if i < len(company_dirs):
            time.sleep(0.5)

        print()

    # 写入文件（覆盖式）
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"=" * 50)
    print(f"数据采集完成")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"成功获取股价: {success_count}/{len(company_dirs)}")
    print(f"=" * 50)


if __name__ == '__main__':
    main()
