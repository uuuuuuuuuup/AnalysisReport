#!/usr/bin/env python3
"""QDII-LOF 溢价套利数据采集脚本。"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = BASE_DIR / "config" / "qdii_lof_list.json"
OUTPUT_DIR = BASE_DIR / "data"
OUTPUT_FILE = OUTPUT_DIR / "arbitrage_raw.json"

THRESHOLD_PCT = 3.0
MAX_RETRIES = 3
RETRY_DELAY = 2
BATCH_SIZE = 20
ENRICH_TIMEOUT = 3
ENRICH_MAX_RETRIES = 1
ENABLE_KLINE = True
ENABLE_MONEY_FLOW = False
ENABLE_NEWS = True

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def retry_request(url, headers=None, timeout=15, max_retries=MAX_RETRIES):
    headers = headers or HEADERS
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
    raise last_error


def secid_for(market, code):
    return f"{'1' if market == 'sh' else '0'}.{code}"


def normalize_code(code):
    code = str(code).strip()
    return re.sub(r"^(sh|sz)", "", code, flags=re.I)


def parse_stock_price_response(raw_data):
    if not raw_data:
        return []
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)
    if isinstance(raw_data, dict) and "data" in raw_data and isinstance(raw_data["data"], str):
        raw_data = json.loads(raw_data["data"])
    if isinstance(raw_data, dict) and "stocks" in raw_data:
        return raw_data["stocks"]
    if isinstance(raw_data, dict) and "data" in raw_data and isinstance(raw_data["data"], dict):
        return raw_data["data"].get("stocks", [])
    return []


def fetch_prices_via_mcp(stock_codes):
    try:
        from __main__ import mcp__AI_Tools__QueryStockPriceInfo
    except ImportError:
        return None
    try:
        result = mcp__AI_Tools__QueryStockPriceInfo(stockCodes=stock_codes)
        return parse_stock_price_response(result)
    except Exception:
        return None


def extract_json_object(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    return json.loads(stripped[first:last + 1])


def fetch_prices_via_claude(stock_codes):
    prompt = (
        "调用 AI_Tools 的 QueryStockPriceInfo 查询 "
        f"{stock_codes}，仅输出原始 JSON，不要解释。"
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=BASE_DIR,
        )
        if result.returncode != 0:
            print(f"  [Claude CLI] 退出码非零: {result.returncode}")
            if result.stderr:
                print(f"  [Claude CLI] stderr: {result.stderr[:200]}")
            return None
        payload = json.loads(result.stdout)
        raw_result = payload.get("result", "")
        data = extract_json_object(raw_result)
        if data is None:
            print(f"  [Claude CLI] 无法从响应中提取 JSON")
            return None
        stocks = parse_stock_price_response(data)
        print(f"  [Claude CLI] 成功获取 {len(stocks)} 只基金数据")
        return stocks
    except subprocess.TimeoutExpired:
        print(f"  [Claude CLI] 查询超时")
        return None
    except Exception as e:
        print(f"  [Claude CLI] 异常: {e}")
        return None


def fetch_price_from_eastmoney(market, code):
    url = (
        "https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={secid_for(market, code)}"
        "&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f170"
    )
    try:
        data = retry_request(url).json().get("data") or {}
        if not data:
            return None
        current = float(data.get("f43") or 0) / 100
        prev_close = float(data.get("f60") or 0) / 100
        return {
            "code": code,
            "name": data.get("f58") or data.get("f57") or "",
            "currentPrice": current,
            "changePercent": float(data.get("f170") or 0) / 100,
            "changeAmount": round(current - prev_close, 3) if prev_close else 0,
            "volume": int(data.get("f47") or 0),
            "turnover": float(data.get("f48") or 0),
            "premiumRate": None,
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_price_map(funds):
    price_map = {}
    batch_size = 10

    for i in range(0, len(funds), batch_size):
        batch = funds[i : i + batch_size]
        full_codes = ",".join(
            f"{f.get('market', 'sz')}{normalize_code(f.get('code', ''))}" for f in batch
        )
        print(f"  [批量查询] 第 {i // batch_size + 1} 批 ({len(batch)} 只): {full_codes}")

        stocks = fetch_prices_via_mcp(full_codes)
        if stocks is None:
            stocks = fetch_prices_via_claude(full_codes)

        if stocks is not None:
            for stock in stocks:
                code = normalize_code(stock.get("code", ""))
                if code:
                    price_map[code] = stock
        else:
            print(f"  [批量查询] 第 {i // batch_size + 1} 批失败，回退到单只 HTTP 查询")
            for fund in batch:
                code = normalize_code(fund.get("code", ""))
                market = fund.get("market", "sz")
                price_map[code] = fetch_price_from_eastmoney(market, code)
                time.sleep(0.5)

    return price_map


def fetch_kline(market, code, days=5):
    if not ENABLE_KLINE:
        return []
    url = (
        "https://push2.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid_for(market, code)}"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=1&end=20500101&lmt={days}"
    )
    try:
        klines = retry_request(
            url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES
        ).json().get("data", {}).get("klines", [])
        result = []
        for kline in klines:
            parts = kline.split(",")
            if len(parts) >= 7:
                result.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": int(float(parts[5])),
                    "turnover": float(parts[6]),
                })
        return result
    except Exception:
        return []


def fetch_money_flow(market, code):
    if not ENABLE_MONEY_FLOW:
        return {}
    url = (
        "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        f"?secid={secid_for(market, code)}"
        "&fields1=f1,f2,f3,f7"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
    )
    try:
        klines = retry_request(
            url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES
        ).json().get("data", {}).get("klines", [])
        if not klines:
            return {}
        latest = klines[-1].split(",")
        if len(latest) < 6:
            return {}
        return {
            "date": latest[0],
            "main_inflow": float(latest[1]),
            "small_inflow": float(latest[2]),
            "medium_inflow": float(latest[3]),
            "large_inflow": float(latest[4]),
            "super_large_inflow": float(latest[5]),
        }
    except Exception:
        return {}


def fetch_news(market, code, days=3):
    if not ENABLE_NEWS:
        return []
    url = f"https://searchapi.eastmoney.com/api/suggest/get?input={code}&type=14&count=5"
    try:
        data = retry_request(
            url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES
        ).json()
        items = data.get("QuotationCodeTable", {}).get("Data", [])
        if not items:
            return []
        security_code = items[0].get("SecurityCode", code)
        news_url = f"https://searchapi.eastmoney.com/api/news/get?type=1&code={security_code}&count=3"
        try:
            news_items = retry_request(
                news_url, timeout=ENRICH_TIMEOUT, max_retries=1
            ).json().get("Data", [])
        except Exception:
            return []
        return [
            {
                "title": item.get("Title", ""),
                "date": (item.get("ShowTime") or "")[:10],
                "url": item.get("Url", ""),
            }
            for item in news_items[:3]
        ]
    except Exception:
        return []


def build_fund_data(fund, price_info):
    code = normalize_code(fund.get("code", ""))
    market = fund.get("market", "sz")
    name = fund.get("name", "")
    data = {
        "code": code,
        "name": name,
        "market": market,
        "notes": fund.get("notes", ""),
        "price": None,
        "premium_rate": None,
        "kline_5d": [],
        "money_flow": {},
        "news": [],
        "error": None,
    }

    if price_info and "error" not in price_info:
        data["price"] = {
            "current": price_info.get("currentPrice"),
            "change_pct": price_info.get("changePercent"),
            "change_amount": price_info.get("changeAmount"),
            "volume": price_info.get("volume"),
            "turnover": price_info.get("turnover"),
        }
        data["premium_rate"] = price_info.get("premiumRate")
        if price_info.get("name") and not name:
            data["name"] = price_info["name"]
        try:
            data["kline_5d"] = fetch_kline(market, code, days=5)
        except Exception:
            data["kline_5d"] = []
        try:
            data["money_flow"] = fetch_money_flow(market, code)
        except Exception:
            data["money_flow"] = {}
        try:
            data["news"] = fetch_news(market, code, days=3)
        except Exception:
            data["news"] = []
    else:
        data["error"] = price_info.get("error", "价格获取失败") if price_info else "价格获取失败"

    return data


def summarize(all_funds):
    rates = [
        (code, fund.get("premium_rate"))
        for code, fund in all_funds.items()
        if isinstance(fund.get("premium_rate"), (int, float))
    ]
    above = [(code, rate) for code, rate in rates if rate >= THRESHOLD_PCT]
    max_item = max(rates, key=lambda item: item[1], default=("", 0))
    errors = sum(1 for fund in all_funds.values() if fund.get("error"))
    return {
        "total_funds": len(all_funds),
        "above_threshold": len(above),
        "below_threshold": len(all_funds) - len(above) - errors,
        "max_premium": {"code": max_item[0], "rate": max_item[1]},
        "errors": errors,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    try:
        config = load_config()
    except Exception as e:
        print(f"[错误] 无法加载配置文件: {e}")
        print(f"请确保 {CONFIG_FILE} 存在且格式正确")
        sys.exit(1)

    funds = config.get("funds", [])
    price_map = fetch_price_map(funds)
    all_funds = {}

    print(f"[{now_time}] 开始采集 QDII-LOF 套利数据...")
    print(f"共配置 {len(funds)} 只 QDII-LOF\n")

    for index, fund in enumerate(funds, 1):
        code = normalize_code(fund.get("code", ""))
        name = fund.get("name", "")
        print(f"[{index}/{len(funds)}] 处理: {name} ({code})")
        fund_data = build_fund_data(fund, price_map.get(code))
        all_funds[code] = fund_data

        price = fund_data.get("price") or {}
        if price:
            print(f"  价格: ¥{price.get('current')} ({price.get('change_pct'):+.2f}%)")
        else:
            print(f"  [失败] {fund_data.get('error')}")
        premium = fund_data.get("premium_rate")
        if isinstance(premium, (int, float)):
            print(f"  溢价率: {premium:+.2f}%")
        else:
            print("  [警告] 溢价率获取失败")
        print(f"  K线: {len(fund_data['kline_5d'])} 天")
        print(f"  新闻: {len(fund_data['news'])} 条\n")
        time.sleep(1)

    result = {
        "fetch_date": today,
        "fetch_time": now_time,
        "threshold_pct": THRESHOLD_PCT,
        "funds": all_funds,
        "summary": summarize(all_funds),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    summary = result["summary"]
    print("=" * 50)
    print("数据采集完成")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"扫描标的: {summary['total_funds']} 只")
    print(f"溢价率 > {THRESHOLD_PCT}%: {summary['above_threshold']} 只")
    print(f"数据错误: {summary['errors']} 只")
    print(f"最高溢价: {summary['max_premium']['code']} ({summary['max_premium']['rate']:+.2f}%)")
    print("=" * 50)


if __name__ == "__main__":
    main()
