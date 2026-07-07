#!/usr/bin/env python3
"""QDII-LOF 溢价套利数据采集脚本。"""

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            timeout=10,
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
        data = retry_request(url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES).json().get("data") or {}
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


def parse_tencent_price_data(data):
    """解析腾讯财经 sqt.gtimg.cn 返回的 JSON 数据，返回标准价格字典。"""
    if not data or not isinstance(data, list) or len(data) < 78:
        return None

    code = data[2] if data[2] else ""
    name = data[1] if data[1] else ""
    current = float(data[3]) if data[3] else 0.0
    prev_close = float(data[4]) if data[4] else 0.0
    change_pct = float(data[32]) if data[32] else 0.0
    change_amount = float(data[31]) if data[31] else 0.0
    volume = int(data[6]) if data[6] else 0
    turnover = float(data[57]) if data[57] else 0.0
    premium_rate = float(data[77]) if data[77] else None

    return {
        "code": code,
        "name": name,
        "currentPrice": current,
        "changePercent": change_pct,
        "changeAmount": change_amount,
        "volume": volume,
        "turnover": turnover,
        "premiumRate": premium_rate,
    }


def fetch_prices_from_tencent(stock_codes):
    """从腾讯财经批量获取实时价格（含溢价率）。
    stock_codes: 逗号分隔的代码串，如 'sh501018,sz161125'
    """
    url = f"https://sqt.gtimg.cn/?q={stock_codes}&fmt=json"
    headers = {
        **HEADERS,
        "Origin": "https://gu.qq.com",
        "Referer": "https://gu.qq.com/",
    }
    try:
        resp = retry_request(url, headers=headers, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES)
        data = resp.json()
        results = []
        for key, value in data.items():
            item = parse_tencent_price_data(value)
            if item:
                results.append(item)
        print(f"  [腾讯财经] 成功获取 {len(results)} 只基金数据")
        return results
    except Exception as e:
        print(f"  [腾讯财经] 异常: {e}")
        return None


def fetch_price_map(funds):
    price_map = {}
    t0 = time.time()

    # 1. 一次性用腾讯财经批量查询全部基金
    full_codes = ",".join(
        f"{f.get('market', 'sz')}{normalize_code(f.get('code', ''))}" for f in funds
    )
    print(f"  [批量查询] 共 {len(funds)} 只: {full_codes[:80]}...")

    stocks = fetch_prices_from_tencent(full_codes)
    print(f"  [批量查询] 腾讯财经耗时: {time.time() - t0:.2f}s")

    if stocks is not None:
        for stock in stocks:
            code = normalize_code(stock.get("code", ""))
            if code:
                price_map[code] = stock
    else:
        # 2. 腾讯财经失败时，回退到单只 Eastmoney 查询
        print(f"  [批量查询] 腾讯财经失败，回退到单只 HTTP 查询")
        for fund in funds:
            code = normalize_code(fund.get("code", ""))
            market = fund.get("market", "sz")
            price_map[code] = fetch_price_from_eastmoney(market, code)

    # # 3. 对仍未获取到价格的基金，跳过（Claude CLI 额度已用完，不再尝试）
    # missing = [f for f in funds if normalize_code(f.get("code", "")) not in price_map or not price_map.get(normalize_code(f.get("code", "")))]
    # if missing:
    #     missing_names = ", ".join(f"{f.get('name', '')}({f.get('code', '')})" for f in missing)
    #     print(f"  [补查] {len(missing)} 只未获取到价格（腾讯财经不支持）: {missing_names}")

    print(f"  [批量查询] 总耗时: {time.time() - t0:.2f}s, 成功 {len(price_map)}/{len(funds)}")
    return price_map


def fetch_tencent_kline(market, code, days=5):
    prefix = "sh" if market == "sh" else "sz"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    try:
        payload = retry_request(
            url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES
        ).json()
        data = payload.get("data", {}).get(f"{prefix}{code}", {})
        day_lines = data.get("qfqday") or data.get("day") or []
        result = []
        for line in day_lines[-days:]:
            if len(line) < 6:
                continue
            result.append({
                "date": line[0],
                "open": float(line[1]),
                "close": float(line[2]),
                "high": float(line[3]),
                "low": float(line[4]),
                "volume": int(float(line[5])),
                "turnover": float(line[5]),
            })
        return result
    except Exception:
        return []


def fetch_kline(market, code, days=5):
    if not ENABLE_KLINE:
        return []
    kline = fetch_tencent_kline(market, code, days=days)
    if kline:
        return kline
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




def fetch_eastmoney_notices(code):
    url = (
        "https://np-anotice-stock.eastmoney.com/api/security/ann"
        f"?page_size=5&page_index=1&stock_list={code}"
    )
    try:
        resp = retry_request(
            url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES
        )
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        return [
            {
                "title": item.get("title", ""),
                "date": item.get("notice_date", "")[:10] if item.get("notice_date") else "",
                "source": "公告",
                "url": "",
            }
            for item in items[:5]
        ]
    except Exception:
        return []


def fetch_eastmoney_reports(code):
    begin_time = datetime.now().replace(year=datetime.now().year - 1).strftime("%Y-%m-%d")
    end_time = datetime.now().strftime("%Y-%m-%d")
    url = (
        "https://reportapi.eastmoney.com/report/list"
        f"?industryCode=*&pageNo=1&pageSize=3&code={code}"
        f"&beginTime={begin_time}&endTime={end_time}&qType=0"
    )
    try:
        resp = retry_request(
            url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES
        )
        items = resp.json().get("data", [])
        return [
            {
                "title": item.get("title", ""),
                "date": item.get("publishDate", "")[:10] if item.get("publishDate") else "",
                "source": "研报",
                "url": "",
            }
            for item in items[:3]
        ]
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
    notices = fetch_eastmoney_notices(code)
    reports = fetch_eastmoney_reports(code)
    return notices + reports


# 实测 fundBuyStatus 映射（来自31只标的抽样）：
# 1 → 开放申购 或 限大额（均可操作）
# 4 → 暂停申购（上限极低，实际不可操作）
# 6 → 暂停申购 / 基金终止（不可操作）
# 以页面实际交易状态文字为准，不依赖状态码推断


def fetch_subscription_status(code):
    """从东方财富基金详情页获取申购状态及实际申购费率。"""
    url = f"https://fund.eastmoney.com/{code}.html"
    try:
        resp = retry_request(url, timeout=ENRICH_TIMEOUT + 2, max_retries=ENRICH_MAX_RETRIES)
        resp.encoding = 'utf-8'
        html = resp.text

        # fundBuyStatus（辅助参考）
        status_code = None
        m = re.search(r'var\s+fundBuyStatus\s*=\s*"(\d+)"', html)
        if m:
            status_code = m.group(1)

        # 从页面提取真实交易状态文字（含括号内限额说明）
        trading_status_text = None
        idx = html.find('交易状态：</span>')
        if idx != -1:
            chunk = html[idx:idx + 600]
            cells = re.findall(
                r'<span[^>]*class=["\']staticCell["\'][^>]*>(.*?)</span\s*>',
                chunk, re.S
            )
            if cells:
                raw = cells[0]
                text = re.sub(r'<[^>]+>', '', raw)
                trading_status_text = re.sub(r'\s+', ' ', text).strip()

        # 提取单日累计购买上限（支持"万元"单位）
        limit_amount = None
        m = re.search(r'单日累计购买上限\s*([\d,.]+(?:万)?元)', html)
        if m:
            limit_amount = m.group(1)

        # 提取实际折后申购费率
        buy_fee = None
        m = re.search(r'<span class="nowPrice">([\d.]+%)</span>', html)
        if m:
            buy_fee = m.group(1)

        # 根据实际文字判断可操作性
        status_text = trading_status_text or "未知"
        is_terminated = '终止' in status_text
        is_suspended = '暂停' in status_text or is_terminated or status_code in ('4', '6')
        is_restricted = '限大额' in status_text
        is_fully_open = '开放申购' in status_text and not is_suspended

        return {
            "status_code": status_code,
            "status_text": status_text,
            "limit_amount": limit_amount,
            "buy_fee_pct": buy_fee,
            "is_fully_open": is_fully_open,
            "is_restricted": is_restricted,
            "is_suspended": is_suspended,
        }
    except Exception as e:
        return {
            "status_code": None,
            "status_text": "查询失败",
            "limit_amount": None,
            "buy_fee_pct": None,
            "is_fully_open": None,
            "is_restricted": None,
            "is_suspended": None,
            "error": str(e),
        }


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
        "subscription": None,
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

        enrich_tasks = {
            "kline_5d": lambda: fetch_kline(market, code, days=5),
            "money_flow": lambda: fetch_money_flow(market, code),
            "news": lambda: fetch_news(market, code, days=3),
            "subscription": lambda: fetch_subscription_status(code),
        }
        defaults = {"kline_5d": [], "money_flow": {}, "news": [], "subscription": {}}

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(fn): key for key, fn in enrich_tasks.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    data[key] = future.result()
                except Exception:
                    data[key] = defaults[key]
    else:
        data["error"] = price_info.get("error", "价格获取失败") if price_info else "价格获取失败"

    return data


def summarize(all_funds, skipped_count=0):
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
        "suspended_filtered": skipped_count,
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
    skipped = 0

    print(f"[{now_time}] 开始采集 QDII-LOF 套利数据...")
    print(f"共配置 {len(funds)} 只 QDII-LOF\n")

    for index, fund in enumerate(funds, 1):
        code = normalize_code(fund.get("code", ""))
        name = fund.get("name", "")
        print(f"[{index}/{len(funds)}] 处理: {name} ({code})")
        fund_data = build_fund_data(fund, price_map.get(code))

        # 过滤掉暂停申购/基金终止的标的
        sub = fund_data.get("subscription") or {}
        if sub.get("is_suspended"):
            skipped += 1
            print(f"  [跳过] 申购状态: {sub.get('status_text', '暂停申购')}，不纳入报告\n")
            continue

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
        sub_text = sub.get("status_text", "未知")
        limit = sub.get("limit_amount")
        print(f"  申购状态: {sub_text}" + (f"（上限 {limit}）" if limit else ""))
        print(f"  K线: {len(fund_data['kline_5d'])} 天")
        print(f"  新闻: {len(fund_data['news'])} 条\n")

    result = {
        "fetch_date": today,
        "fetch_time": now_time,
        "threshold_pct": THRESHOLD_PCT,
        "funds": all_funds,
        "summary": summarize(all_funds, skipped_count=skipped),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    summary = result["summary"]
    print("=" * 50)
    print("数据采集完成")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"扫描标的: {len(funds)} 只（过滤暂停/终止: {skipped} 只，保留: {summary['total_funds']} 只）")
    print(f"溢价率 > {THRESHOLD_PCT}%: {summary['above_threshold']} 只")
    print(f"数据错误: {summary['errors']} 只")
    print(f"最高溢价: {summary['max_premium']['code']} ({summary['max_premium']['rate']:+.2f}%)")
    print("=" * 50)


if __name__ == "__main__":
    main()
