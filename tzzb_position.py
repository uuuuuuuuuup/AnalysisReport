#!/usr/bin/env python3
"""
同花顺投资账本 - 持仓查询脚本

通过 API 直接获取账户持仓信息，无需浏览器。

## 首次使用

1. 在浏览器中打开 https://tzzb.10jqka.com.cn/pc/index.html 并登录
2. 按 F12 打开开发者工具 → Application → Cookies → tzzb.10jqka.com.cn
3. 找到 `userid` cookie，复制它的值
4. 运行: python3 tzzb_position.py --userid <你的userid>

或者从浏览器复制完整的 Cookie 字符串（更可靠）:
   python3 tzzb_position.py --cookie "userid=xxx; other=yyy; ..."

Cookie 会自动缓存到 ~/.tzzb_cookies，后续直接运行 `python3 tzzb_position.py` 即可。
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path

BASE_URL = "https://tzzb.10jqka.com.cn/caishen_httpserver/tzzb"
COOKIE_FILE = Path.home() / ".tzzb_cookies"


def load_cached_cookies() -> str | None:
    """从缓存文件加载 cookie"""
    if COOKIE_FILE.exists():
        return COOKIE_FILE.read_text().strip()
    return None


def save_cookies(cookie: str) -> None:
    """缓存 cookie 到文件"""
    COOKIE_FILE.write_text(cookie)
    COOKIE_FILE.chmod(0o600)
    print(f"Cookie 已缓存到 {COOKIE_FILE}")


def api_call(path: str, params: dict, cookie: str) -> dict:
    """调用 API，返回解析后的 JSON"""
    url = BASE_URL + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="POST")
    req.add_header("Cookie", cookie)
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Referer", "https://tzzb.10jqka.com.cn/")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"error_code": str(e.code), "error_msg": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"error_code": "-1", "error_msg": str(e)}


def get_accounts(cookie: str, userid: str) -> list[dict]:
    """获取账户列表"""
    params = {"terminal": "1", "version": "0.0.0", "userid": userid}
    resp = api_call("/caishen_fund/pc/account/v1/account_list", params, cookie)
    if resp.get("error_code") != "0":
        print(f"获取账户列表失败: {resp.get('error_msg', '未知错误')}")
        sys.exit(1)
    ex_data = resp.get("ex_data", {})
    return ex_data.get("common", [])


def get_positions(cookie: str, userid: str, account: dict) -> dict:
    """获取单个账户的持仓"""
    params = {
        "terminal": "1",
        "version": "0.0.0",
        "userid": userid,
        "manual_id": account.get("manualid", ""),
        "fund_key": account.get("fund_key", ""),
        "rzrq_fund_key": "",
        "is_merge": "1",
    }
    resp = api_call("/caishen_fund/pc/asset/v1/stock_position", params, cookie)
    if resp.get("error_code") != "0":
        return {"error": resp.get("error_msg", "未知错误")}
    return resp.get("ex_data", {})


def safe_float(v: str | None, default: float = 0.0) -> float:
    """安全转换为 float，空字符串返回默认值"""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def format_price(v: str | None) -> str:
    """格式化价格"""
    if v is None or v == "":
        return "-"
    try:
        return f"{float(v):,.2f}"
    except (ValueError, TypeError):
        return str(v)


def format_rate(v: str | None) -> str:
    """格式化比例/收益率"""
    if v is None or v == "":
        return "-"
    try:
        return f"{float(v) * 100:+.2f}%"
    except (ValueError, TypeError):
        return str(v)


def print_positions(account_name: str, data: dict) -> None:
    """打印单个账户的持仓表格"""
    if "error" in data:
        print(f"\n{'='*80}")
        print(f"  账户: {account_name}  — 错误: {data['error']}")
        return

    positions = data.get("position", [])
    total_asset = safe_float(data.get("total_asset"))
    total_value = safe_float(data.get("total_value"))
    money_remain = safe_float(data.get("money_remain"))
    position_rate = safe_float(data.get("position_rate"))
    upload_ts = data.get("upload_time", "")
    upload_str = ""
    if upload_ts and upload_ts.isdigit():
        try:
            dt = datetime.datetime.fromtimestamp(int(upload_ts) / 1000)
            upload_str = f"  |  数据时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}"
        except (ValueError, OSError):
            pass

    print(f"\n{'='*80}")
    print(f"  账户: {account_name}")
    print(f"  总资产: ¥{total_asset:,.2f}  |  持仓市值: ¥{total_value:,.2f}  |  可用资金: ¥{money_remain:,.2f}  |  仓位: {position_rate*100:.1f}%{upload_str}")
    print(f"{'='*80}")

    if not positions:
        print("  (空仓)")
        return

    # 表头
    header = f"  {'代码':<8} {'名称':<10} {'持仓':<6} {'成本':>8} {'现价':>8} {'市值':>12} {'盈亏':>10} {'盈亏%':>8} {'仓位%':>7}"
    print(header)
    print(f"  {'-'*78}")

    for p in positions:
        code = p.get("code", "")
        name = p.get("name", "")
        count = p.get("count", "0")
        cost = format_price(p.get("cost"))
        price = format_price(p.get("price"))
        value = format_price(p.get("value"))
        hold_profit = format_price(p.get("hold_profit"))
        hold_rate = format_rate(p.get("hold_rate"))
        pos_rate = format_rate(p.get("position_rate"))

        print(f"  {code:<8} {name:<10} {count:>6} {cost:>8} {price:>8} {value:>12} {hold_profit:>10} {hold_rate:>8} {pos_rate:>7}")

    print(f"  {'-'*78}")
    # 合计行
    total_count = sum(int(safe_float(p.get("count"))) for p in positions)
    total_hold_profit = sum(safe_float(p.get("hold_profit")) for p in positions)
    print(f"  {'合计':<8} {'':<10} {total_count:>6} {'':>8} {'':>8} {format_price(str(total_value)):>12} {format_price(str(total_hold_profit)):>10}")


def main():
    parser = argparse.ArgumentParser(description="同花顺投资账本 - 持仓查询")
    parser.add_argument("--userid", help="用户 ID (从浏览器 cookie 中获取)")
    parser.add_argument("--cookie", help="完整的 Cookie 字符串 (更可靠)")
    parser.add_argument("--save-cookie", action="store_true", default=True,
                        help="缓存 cookie 到本地文件 (默认开启)")
    parser.add_argument("--no-cache", action="store_true",
                        help="不缓存 cookie")
    parser.add_argument("--account", help="只查询指定账户 (按名称模糊匹配)")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = parser.parse_args()

    # 确定 cookie
    cookie = args.cookie
    if not cookie:
        cookie = load_cached_cookies()

    if not cookie:
        print("未找到 Cookie。请通过以下方式之一提供:")
        print()
        print("  方式1 (推荐): 从浏览器复制完整 Cookie")
        print("    1. 打开 https://tzzb.10jqka.com.cn/pc/index.html 并登录")
        print("    2. F12 → Application → Cookies → tzzb.10jqka.com.cn")
        print("    3. 复制所有 cookie，格式: userid=xxx; other=yyy; ...")
        print("    4. 运行: python3 tzzb_position.py --cookie '你的cookie'")
        print()
        print("  方式2: 只提供 userid")
        print("    python3 tzzb_position.py --userid <你的userid>")
        sys.exit(1)

    # 提取 userid
    userid = args.userid
    if not userid:
        cookies = dict(c.split("=", 1) for c in cookie.replace("; ", ";").split(";") if "=" in c)
        userid = cookies.get("userid", "")
    if not userid:
        print("错误: 无法从 cookie 中提取 userid，请用 --userid 指定")
        sys.exit(1)

    # 缓存 cookie
    if not args.no_cache:
        save_cookies(cookie)

    print(f"正在查询持仓 (userid={userid})...")

    # 获取账户列表
    accounts = get_accounts(cookie, userid)
    if not accounts:
        print("没有找到任何账户")
        return

    # 过滤账户
    if args.account:
        accounts = [a for a in accounts if args.account in a.get("manualname", "")]
        if not accounts:
            print(f"未找到名称包含 '{args.account}' 的账户")
            return

    print(f"找到 {len(accounts)} 个账户")

    # 逐个查询持仓
    for acc in accounts:
        name = acc.get("manualname", "未知")
        data = get_positions(cookie, userid, acc)

        if args.json:
            print(f"\n--- {name} ---")
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print_positions(name, data)

    print()


if __name__ == "__main__":
    main()
