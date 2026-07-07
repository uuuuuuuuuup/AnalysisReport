"""
value-mispricing-scanner: API 调用层

封装三个端点：
1. selectSecurity  → L1 选股（A股 / 港股通）
2. searchData      → L2 批量财务健康查询（每批 ≤5 只）
3. stock-analysis  → L3 单票诊断（仅 A股）

所有函数均为 async，错误时返回空结果（safe-fail）而非抛出异常。
"""

import asyncio
import csv
import io
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as urllib_request, error as urllib_error

import httpx

EM_API_KEY = os.environ.get("EM_API_KEY", "em_4Z1jwV7bcrxM0aGNau9awdcnZfjvLG3a").strip()

SCREENER_URL = "https://ai-saas.eastmoney.com/proxy/b/mcp/tool/selectSecurity"
SEARCH_DATA_URL = "https://ai-saas.eastmoney.com/proxy/b/mcp/tool/searchData"
STOCK_ANALYSIS_URL = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/stock-analysis"
ENTITY_API_URL = "https://ai-saas.eastmoney.com/proxy/entity/saas"

TIMEOUT = 45.0


# ─────────────────────────────────────────────
# 通用工具
# ─────────────────────────────────────────────

def _call_id() -> str:
    return f"call_{uuid.uuid4().hex[:8]}"

def _user_id() -> str:
    return f"user_{uuid.uuid4().hex[:8]}"

def _to_float(v: Any) -> Optional[float]:
    """
    将各种格式的数值字符串转为 float，失败返回 None。
    支持：逗号分隔、%、亿/万 单位后缀。
    """
    if v is None or v == "" or v == "--" or v == "N/A":
        return None
    s = str(v).replace(",", "").replace("%", "").strip()
    # 处理中文单位（市值常带"亿"，不做单位换算，保持原始数值含义）
    for suffix in ("亿元", "万元", "亿", "万"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    try:
        return float(s)
    except ValueError:
        return None


def _find_val(row: Dict, *keys: str) -> Optional[str]:
    """
    在 row 中查找值：
    1. 先精确匹配键名
    2. 再按关键词做部分匹配（适配带日期后缀的列名，如"市净率(倍) 2026.07.02"）
    返回第一个非空值。
    """
    empty = ("", "--", "N/A", "nan", "None")
    # 精确匹配
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip() not in empty:
            return str(v).strip()
    # 模糊匹配：键名中包含 k
    for k in keys:
        for col, val in row.items():
            if k in col and val is not None and str(val).strip() not in empty:
                return str(val).strip()
    return None


# ─────────────────────────────────────────────
# L1：selectSecurity 选股
# ─────────────────────────────────────────────

def _build_screener_body(query: str, select_type: str) -> Dict:
    return {
        "query": query,
        "selectType": select_type,
        "toolContext": {
            "callId": _call_id(),
            "userInfo": {"userId": _user_id()},
        },
    }


def _parse_column_map(columns: List[Dict]) -> Tuple[Dict[str, str], List[str]]:
    """返回 (英文->中文 映射, 英文列名顺序列表)。"""
    col_map: Dict[str, str] = {}
    col_order: List[str] = []
    for col in columns or []:
        if not isinstance(col, dict):
            continue
        en = col.get("field") or col.get("name") or col.get("key") or ""
        cn = col.get("displayName") or col.get("title") or col.get("label") or en
        date_msg = col.get("dateMsg") or ""
        if date_msg:
            cn = f"{cn} {date_msg}"
        if en:
            col_map[str(en)] = str(cn)
            col_order.append(str(en))
    return col_map, col_order


def _parse_screener_response(raw: Dict) -> List[Dict[str, str]]:
    """从 selectSecurity 响应中提取行列表（中文列名）。"""
    if not isinstance(raw, dict):
        return []

    all_results = raw.get("allResults") or {}
    result_node = (all_results.get("result") if isinstance(all_results, dict) else None) or {}
    data_list = result_node.get("dataList") if isinstance(result_node, dict) else None
    columns = result_node.get("columns") if isinstance(result_node, dict) else None

    if isinstance(data_list, list) and data_list and isinstance(columns, list) and columns:
        col_map, col_order = _parse_column_map(columns)
        rows = []
        for item in data_list:
            if not isinstance(item, dict):
                continue
            row = {}
            for en_key in col_order:
                cn_key = col_map.get(en_key, en_key)
                val = item.get(en_key)
                row[cn_key] = "" if val is None else str(val)
            rows.append(row)
        return rows

    # 回退：解析 partialResults markdown 表格
    partial = raw.get("partialResults") or ""
    if isinstance(partial, str) and "|" in partial:
        return _parse_markdown_table(partial)

    return []


def _parse_markdown_table(text: str) -> List[Dict[str, str]]:
    """解析 markdown 表格字符串为行字典列表。"""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return []

    def split_row(line: str) -> List[str]:
        return [c.strip() for c in line.split("|") if c.strip()]

    headers = split_row(lines[0])
    if not headers:
        return []

    start = 1
    if start < len(lines) and re.match(r"^[\|\s\-:]+$", lines[start]):
        start = 2

    rows = []
    for line in lines[start:]:
        cells = split_row(line)
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        rows.append(dict(zip(headers, cells[: len(headers)])))
    return rows


async def screen_stocks(query: str, select_type: str) -> List[Dict[str, str]]:
    """
    调用 selectSecurity 进行选股。

    Args:
        query:       自然语言筛选条件
        select_type: "A股" 或 "港股"

    Returns:
        行字典列表（中文列名），失败返回 []
    """
    body = _build_screener_body(query, select_type)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                SCREENER_URL,
                json=body,
                headers={"Content-Type": "application/json", "em_api_key": EM_API_KEY},
            )
            payload = resp.json()
    except Exception as e:
        print(f"[screen_stocks] {select_type} 调用失败: {e}")
        return []

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        print(f"[screen_stocks] {select_type} 响应无 data 字段")
        return []

    rows = _parse_screener_response(data)
    print(f"[screen_stocks] {select_type}: 获得 {len(rows)} 只候选")
    return rows


# ─────────────────────────────────────────────
# L2：searchData 批量财务健康查询
# ─────────────────────────────────────────────

def _build_search_body(query: str) -> Dict:
    return {
        "query": query,
        "toolContext": {
            "callId": _call_id(),
            "userInfo": {"userId": _user_id()},
        },
    }


def _extract_dto_list(api_result: Dict) -> List[Dict]:
    """从 searchData 响应中提取 dataTableDTOList。"""
    if not isinstance(api_result, dict):
        return []
    for path in [
        lambda r: r.get("dataTableDTOList"),
        lambda r: (r.get("data") or {}).get("searchDataResultDTO", {}).get("dataTableDTOList"),
        lambda r: (r.get("data") or {}).get("dataTableDTOList"),
    ]:
        try:
            val = path(api_result)
            if isinstance(val, list):
                return val
        except Exception:
            pass
    return []


def _extract_metric_values(block: Dict) -> Dict[str, List[Optional[float]]]:
    """
    从单个 dataTableDTO 块中提取指标数值列表。
    优先使用 rawTable（干净数字），回退到 table（带单位后缀）。
    返回 {指标中文名: [float|None, ...]} 形式的字典。
    """
    raw_table = block.get("rawTable")
    table = raw_table if isinstance(raw_table, dict) and raw_table else block.get("table") or {}
    name_map = block.get("nameMap") or {}
    if isinstance(name_map, list):
        name_map = {str(i): v for i, v in enumerate(name_map)}
    if not isinstance(name_map, dict):
        name_map = {}

    if not isinstance(table, dict):
        return {}

    metrics: Dict[str, List[Optional[float]]] = {}
    for key, values in table.items():
        if key == "headName":
            continue
        cn_name = str(name_map.get(str(key), key))
        if not isinstance(values, list):
            values = [values]
        metrics[cn_name] = [_to_float(v) for v in values]
    return metrics


def _assess_financial_health(metrics: Dict[str, List[Optional[float]]]) -> Dict[str, Any]:
    """
    根据提取的指标值评估财务健康度。
    返回 {roe, revenue_trend, profit_trend, cashflow_ok, is_trap}。
    """
    health: Dict[str, Any] = {
        "roe": None,
        "revenue_trend": "unknown",
        "profit_trend": "unknown",
        "cashflow_ok": None,
        "is_trap": False,
        "trap_reasons": [],
    }

    # 查找 ROE（净资产收益率绝对值，排除"增长率/环比/同比"等变体）
    for key, vals in metrics.items():
        is_roe = ("roe" in key.lower() or "净资产收益率" in key)
        is_growth = any(g in key for g in ["增长", "环比", "同比", "增速"])
        if is_roe and not is_growth:
            non_null = [v for v in vals if v is not None]
            if non_null:
                health["roe"] = non_null[0]  # 最新期（headName 首列为最新）
            break

    # 查找营收同比增速
    for key, vals in metrics.items():
        if any(kw in key for kw in ["营收", "营业收入", "revenue", "Revenue"]) and any(kw in key for kw in ["增速", "增长", "同比", "yoy", "YOY"]):
            non_null = [v for v in vals if v is not None]
            if non_null:
                neg_count = sum(1 for v in non_null if v < 0)
                health["revenue_trend"] = "declining" if neg_count >= len(non_null) * 0.75 else "mixed"
            break

    # 查找净利润同比增速
    for key, vals in metrics.items():
        if any(kw in key for kw in ["净利润", "profit", "Profit"]) and any(kw in key for kw in ["增速", "增长", "同比", "yoy", "YOY"]):
            non_null = [v for v in vals if v is not None]
            if non_null:
                neg_count = sum(1 for v in non_null if v < 0)
                health["profit_trend"] = "declining" if neg_count >= len(non_null) * 0.75 else "mixed"
            break

    # 查找经营现金流
    for key, vals in metrics.items():
        if any(kw in key for kw in ["经营", "operating"]) and any(kw in key for kw in ["现金", "cash"]):
            non_null = [v for v in vals if v is not None]
            if non_null:
                health["cashflow_ok"] = sum(non_null) > 0  # 累计为正则 OK
            break

    # 判断是否为价值陷阱
    # 说明：ROE 接口返回的是单季度/混合口径值，绝对值不可靠，
    # 因此陷阱判定主要依赖同比增速趋势与现金流（口径一致、更可靠）。
    traps = []
    if health["revenue_trend"] == "declining":
        traps.append("营收持续下滑")
    if health["profit_trend"] == "declining":
        traps.append("净利润持续下滑")
    if health["cashflow_ok"] is False:
        traps.append("经营现金流为负")
    if health["roe"] is not None and health["roe"] < 0:
        traps.append(f"ROE为负({health['roe']:.1f}%)")

    health["is_trap"] = len(traps) >= 2  # 命中2条及以上才判定为陷阱
    health["trap_reasons"] = traps
    return health


async def get_financial_health_batch(
    stocks: List[Dict[str, str]]
) -> Dict[str, Dict[str, Any]]:
    """
    对一批（≤5只）股票查询财务健康数据。

    Args:
        stocks: 每个 dict 须含 "code"、"name" 键

    Returns:
        {stock_code: health_dict}，失败的股票不在结果中（safe-fail）
    """
    if not stocks:
        return {}

    names_str = "、".join(
        f"{s.get('name', '')}({s.get('code', '')})" for s in stocks
    )
    query = (
        f"请查询以下股票最近四个季度的营业收入同比增长率、净利润同比增长率、加权净资产收益率，"
        f"以及经营活动产生的现金流量净额：{names_str}"
    )

    body = _build_search_body(query)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                SEARCH_DATA_URL,
                json=body,
                headers={"Content-Type": "application/json", "em_api_key": EM_API_KEY},
            )
            payload = resp.json()
    except Exception as e:
        print(f"[get_financial_health_batch] 调用失败: {e}")
        return {}

    data = payload.get("data") if isinstance(payload, dict) else payload
    dto_list = _extract_dto_list(payload if isinstance(payload, dict) else data)

    result: Dict[str, Dict[str, Any]] = {}
    for block in dto_list:
        if not isinstance(block, dict):
            continue
        entity_name = str(block.get("entityName") or "")
        block_code = str(block.get("code") or "")  # 如 "600104.SH"
        # 匹配到输入的股票（按名称或代码前缀）
        matched_code = None
        for s in stocks:
            s_code = s.get("code", "")
            s_name = s.get("name", "")
            if (s_name and (s_name in entity_name or entity_name.startswith(s_name))) or \
               (s_code and block_code.startswith(s_code)):
                matched_code = s_code
                break
        if matched_code is None:
            continue
        metrics = _extract_metric_values(block)
        result[matched_code] = _assess_financial_health(metrics)

    return result


# ─────────────────────────────────────────────
# L3：stock-analysis 单票诊断（仅 A股）
# ─────────────────────────────────────────────

def _http_diagnose(question: str) -> str:
    """同步 HTTP 调用 stock-analysis，返回诊断文本。"""
    payload = {"question": question}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url=STOCK_ANALYSIS_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "em_api_key": EM_API_KEY},
    )
    try:
        with urllib_request.urlopen(req, timeout=int(TIMEOUT)) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib_error.HTTPError, urllib_error.URLError, json.JSONDecodeError) as e:
        return f"[诊断接口错误: {e}]"

    # 提取 displayData
    data = raw.get("data") if isinstance(raw, dict) else None
    if isinstance(data, dict):
        dd = data.get("displayData")
        if isinstance(dd, str) and dd.strip():
            return dd.strip()
    return "[未获取到诊断内容]"


async def diagnose_stock(name: str, code: str) -> str:
    """
    异步调用 stock-analysis 对单只 A 股做综合诊断。

    Args:
        name: 股票名称
        code: 股票代码

    Returns:
        诊断报告文本
    """
    question = f"请综合分析{name}（{code}）当前的投资价值，重点关注基本面质量、估值水平和主要风险"
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _http_diagnose, question)
    return text
