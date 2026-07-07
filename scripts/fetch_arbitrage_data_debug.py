#!/usr/bin/env python3
"""诊断版：带详细计时日志，定位脚本卡在哪里。"""

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
OUTPUT_FILE = OUTPUT_DIR / "arbitrage_raw_debug.json"

ENRICH_TIMEOUT = 3
ENRICH_MAX_RETRIES = 1
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def log(msg):
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{now}] {msg}")


def retry_request(url, headers=None, timeout=15, max_retries=1):
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
                time.sleep(1)
    raise last_error


def secid_for(market, code):
    return f"{'1' if market == 'sh' else '0'}.{code}"


def normalize_code(code):
    return re.sub(r"^(sh|sz)", "", str(code).strip(), flags=re.I)


def fetch_prices_via_claude(stock_codes):
    prompt = (
        "调用 AI_Tools 的 QueryStockPriceInfo 查询 "
        f"{stock_codes}，仅输出原始 JSON，不要解释。"
    )
    log(f"  [Claude CLI] 启动子进程查询 {stock_codes[:40]}...")
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=BASE_DIR,
        )
        if result.returncode != 0:
            log(f"  [Claude CLI] 失败: rc={result.returncode}")
            return None
        payload = json.loads(result.stdout)
        raw_result = payload.get("result", "")
        log(f"  [Claude CLI] 成功获取数据")
        return raw_result
    except subprocess.TimeoutExpired:
        log(f"  [Claude CLI] 超时")
        return None
    except Exception as e:
        log(f"  [Claude CLI] 异常: {e}")
        return None


def fetch_tencent_kline(market, code, days=5):
    prefix = "sh" if market == "sh" else "sz"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    try:
        payload = retry_request(url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES).json()
        data = payload.get("data", {}).get(f"{prefix}{code}", {})
        day_lines = data.get("qfqday") or data.get("day") or []
        result = []
        for line in day_lines[-days:]:
            if len(line) < 6:
                continue
            result.append({"date": line[0], "open": float(line[1]), "close": float(line[2]),
                           "high": float(line[3]), "low": float(line[4]), "volume": int(float(line[5]))})
        return result
    except Exception:
        return []


def fetch_eastmoney_notices(code):
    url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?page_size=3&page_index=1&stock_list={code}"
    try:
        resp = retry_request(url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES)
        items = resp.json().get("data", {}).get("list", [])
        return [{"title": i.get("title", ""), "date": i.get("notice_date", "")[:10], "source": "公告"} for i in items[:3]]
    except Exception:
        return []


def fetch_eastmoney_reports(code):
    begin = datetime.now().replace(year=datetime.now().year - 1).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    url = f"https://reportapi.eastmoney.com/report/list?industryCode=*&pageNo=1&pageSize=2&code={code}&beginTime={begin}&endTime={end}&qType=0"
    try:
        items = retry_request(url, timeout=ENRICH_TIMEOUT, max_retries=ENRICH_MAX_RETRIES).json().get("data", [])
        return [{"title": i.get("title", ""), "date": i.get("publishDate", "")[:10], "source": "研报"} for i in items[:2]]
    except Exception:
        return []


def build_fund_data(fund, price_info):
    code = normalize_code(fund.get("code", ""))
    market = fund.get("market", "sz")
    data = {"code": code, "name": fund.get("name", ""), "market": market,
            "price": None, "premium_rate": None, "kline_5d": [], "money_flow": {}, "news": [], "error": None}

    if price_info and "error" not in price_info:
        data["price"] = {"current": price_info.get("currentPrice"), "change_pct": price_info.get("changePercent"),
                         "change_amount": price_info.get("changeAmount"), "volume": price_info.get("volume"),
                         "turnover": price_info.get("turnover")}
        data["premium_rate"] = price_info.get("premiumRate")

        tasks = {
            "kline_5d": lambda: fetch_tencent_kline(market, code),
            "news": lambda: fetch_eastmoney_notices(code) + fetch_eastmoney_reports(code),
        }
        defaults = {"kline_5d": [], "news": []}
        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = {ex.submit(fn): key for key, fn in tasks.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    data[key] = future.result()
                except Exception:
                    data[key] = defaults[key]
    else:
        data["error"] = price_info.get("error", "价格获取失败") if price_info else "价格获取失败"
    return data


def main():
    log("开始诊断运行")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        funds = json.load(f).get("funds", [])[:3]  # 只测前3只，快速定位

    log(f"加载配置成功，共 {len(funds)} 只基金（诊断模式只跑前3只）")

    # 测试 Claude CLI 价格查询
    log("=" * 40)
    log("阶段1：测试 Claude CLI 价格查询")
    t0 = time.time()
    codes = ",".join(f"{f['market']}{normalize_code(f['code'])}" for f in funds)
    log(f"查询代码: {codes}")
    result = fetch_prices_via_claude(codes)
    log(f"Claude CLI 耗时: {time.time() - t0:.2f}s, 结果长度: {len(str(result)) if result else 0}")

    # 测试 enrich 接口
    log("=" * 40)
    log("阶段2：测试 enrich 接口（K线 + 公告/研报）")
    for fund in funds:
        code = normalize_code(fund["code"])
        market = fund["market"]
        log(f"  测试 {fund['name']} ({code})")

        t0 = time.time()
        kline = fetch_tencent_kline(market, code)
        log(f"    K线: {len(kline)} 条, 耗时 {time.time() - t0:.2f}s")

        t0 = time.time()
        notices = fetch_eastmoney_notices(code)
        log(f"    公告: {len(notices)} 条, 耗时 {time.time() - t0:.2f}s")

        t0 = time.time()
        reports = fetch_eastmoney_reports(code)
        log(f"    研报: {len(reports)} 条, 耗时 {time.time() - t0:.2f}s")

    # 测试完整 build_fund_data
    log("=" * 40)
    log("阶段3：测试完整 build_fund_data（含并行）")
    t0 = time.time()
    for fund in funds:
        price_info = {"currentPrice": 1.0, "premiumRate": 5.0, "changePercent": 0.0,
                      "changeAmount": 0.0, "volume": 1000, "turnover": 1000.0}
        build_fund_data(fund, price_info)
    log(f"3只基金 build_fund_data 总耗时: {time.time() - t0:.2f}s")

    log("=" * 40)
    log("诊断完成")


if __name__ == "__main__":
    main()
