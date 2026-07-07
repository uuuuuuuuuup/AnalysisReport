#!/usr/bin/env python3
"""批量抓取31个QDII-LOF标的，验证 fundBuyStatus 与交易状态的映射关系。"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = BASE_DIR / "config" / "qdii_lof_list.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_fund_page(code):
    """抓取东方财富基金详情页，提取 fundBuyStatus 和交易状态。"""
    url = f"https://fund.eastmoney.com/{code}.html"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = 'utf-8'  # eastmoney 页面是 UTF-8，requests 有时猜错
        html = resp.text

        # 提取 fundBuyStatus
        fund_buy_status = None
        m = re.search(r'var\s+fundBuyStatus\s*=\s*"(\d+)"', html)
        if m:
            fund_buy_status = m.group(1)

        # 提取交易状态：先定位到 "交易状态：</span>" 的位置，
        # 再从后续 600 字符切片里找所有 staticCell，取第一个的完整文本
        trading_status = None
        idx = html.find('交易状态：</span>')
        if idx != -1:
            chunk = html[idx:idx + 600]
            # DEBUG：打印原始切片，看实际 HTML 结构
            if code in ("501018", "501312"):  # 只打印前两个，避免刷屏
                print(f"\n  [DEBUG {code}] 原始切片:\n{chunk[:400]}\n")
            # 用贪婪匹配拿到 staticCell 的完整内容（含嵌套 span）
            cells = re.findall(
                r'<span[^>]*class=["\']staticCell["\'][^>]*>(.*?)</span\s*>',
                chunk, re.S
            )
            if cells:
                raw = cells[0]
                text = re.sub(r'<[^>]+>', '', raw)   # 去掉所有子标签
                trading_status = re.sub(r'\s+', ' ', text).strip()
        else:
            if code in ("501018", "501312"):
                print(f"\n  [DEBUG {code}] 未找到 '交易状态：</span>' 关键字")

        # 提取单日累计购买上限
        limit_amount = None
        m = re.search(r'单日累计购买上限\s*([\d,.]+元)', html)
        if m:
            limit_amount = m.group(1)

        return {
            "code": code,
            "fund_buy_status": fund_buy_status,
            "trading_status": trading_status,
            "limit_amount": limit_amount,
            "url": url,
            "success": True,
        }
    except Exception as e:
        return {
            "code": code,
            "fund_buy_status": None,
            "trading_status": None,
            "limit_amount": None,
            "url": url,
            "success": False,
            "error": str(e),
        }


def main():
    config = load_config()
    funds = config.get("funds", [])

    print(f"开始批量抓取 {len(funds)} 个标的的申购状态...\n")

    results = []
    total = len(funds)
    done = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fetch_fund_page, f["code"]): f for f in funds}
        for future in as_completed(futures):
            fund = futures[future]
            result = future.result()
            results.append(result)
            done += 1
            status = "✅" if result["success"] else "❌"
            print(
                f"[{done}/{total}] {status} {fund['name']} ({fund['code']}): "
                f"fundBuyStatus={result['fund_buy_status']}, "
                f"交易状态={result['trading_status']}"
            )
            if result.get("limit_amount"):
                print(f"   限额: {result['limit_amount']}")
            time.sleep(0.1)

    # 统计映射关系
    print("\n" + "=" * 60)
    print("【映射关系统计】")
    print("=" * 60)

    mapping = {}
    for r in results:
        if not r["success"]:
            continue
        key = f"fundBuyStatus={r['fund_buy_status']}"
        trading = r["trading_status"] or "未知"
        if key not in mapping:
            mapping[key] = {}
        if trading not in mapping[key]:
            mapping[key][trading] = []
        mapping[key][trading].append(r["code"])

    for status_code in sorted(mapping.keys(), key=lambda x: x or ""):
        print(f"\n{status_code}:")
        for trading_status, codes in mapping[status_code].items():
            print(f"  → {trading_status}: {', '.join(codes)}")

    # 输出详细表格
    print("\n" + "=" * 60)
    print("【详细数据表】")
    print("=" * 60)
    print(f"{'代码':<10} {'fundBuyStatus':<15} {'交易状态':<20} {'限额':<15}")
    print("-" * 60)
    for r in sorted(results, key=lambda x: x["code"]):
        if r["success"]:
            print(
                f"{r['code']:<10} {r['fund_buy_status'] or 'N/A':<15} "
                f"{r['trading_status'] or 'N/A':<20} {r['limit_amount'] or 'N/A':<15}"
            )
        else:
            print(f"{r['code']:<10} 抓取失败: {r.get('error', '')}")

    # 保存结果到文件
    output_file = BASE_DIR / "data" / "buy_status_mapping.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
