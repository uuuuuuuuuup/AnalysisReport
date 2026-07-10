"""
mx-data: Query structured financial/macro/screener/comparable data.

Outputs Excel/CSV/Markdown files and prints a JSON result.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add mx-common package to path.
_COMMON = Path(__file__).resolve().parents[2] / "mx-common" / "scripts"
if str(_COMMON) not in sys.path:
    sys.path.insert(0, str(_COMMON))

from mx_common.api_client import ApiCallError, post
from mx_common.cli import parse_query, reconfigure_stdio
from mx_common.content import check_business_status, extract_data_message
from mx_common.data_parsers import (
    comparable_parse_response,
    finance_count_entities,
    finance_parse_tables,
    macro_parse_response,
    screener_parse_response,
)
from mx_common.endpoints import data_endpoint
from mx_common.entity import recognize_entities_saas
from mx_common.output import (
    default_output_dir,
    ensure_output_dir,
    unique_suffix,
    write_csv,
    write_excel,
    write_markdown,
    write_text_file,
)


GENERAL_ERROR_MSG = "数据查询服务暂时不可用，请稍后重试。"
DIRECT_QUERY_ENTITY_LIMIT = 5
MAX_ENTITY_TAGS = 500


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _build_tool_context() -> Dict[str, Any]:
    call_id = f"call_{uuid.uuid4().hex[:8]}"
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    return {
        "callId": call_id,
        "userInfo": {"userId": user_id},
    }


# ---------------------------------------------------------------------------
# Finance data
# ---------------------------------------------------------------------------


def _build_multi_entity_query(indicators: str) -> str:
    return f"选定实体的{indicators.strip()}"


async def _query_finance(
    query: str,
    indicators: Optional[str],
    output_dir: Path,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "data_type": "finance",
        "query": query,
        "files": [],
        "row_count": 0,
    }

    recognized_tags = await recognize_entities_saas(query)
    recognized_count = len(recognized_tags)
    result["recognized_entity_count"] = recognized_count

    entity_tags: Optional[List[Dict[str, Any]]] = None
    if recognized_count > DIRECT_QUERY_ENTITY_LIMIT:
        if not indicators or not indicators.strip():
            result["error_code"] = "MISSING_INDICATORS"
            result["message"] = (
                "多实体查数（识别实体数 > 5）缺少 --indicators，"
                "请从 query 中提取金融指标后传入，用于构造「选定实体的{indicators}」"
            )
            return result
        entity_tags = recognized_tags[:MAX_ENTITY_TAGS]
        result["use_entity_tags"] = True
        result["indicators"] = indicators.strip()
        search_query = _build_multi_entity_query(indicators)
        result["search_query"] = search_query
    else:
        result["use_entity_tags"] = False
        search_query = query
        if indicators and indicators.strip():
            result["indicators"] = indicators.strip()

    body: Dict[str, Any] = {"query": search_query, "toolContext": _build_tool_context()}
    if entity_tags:
        body["toolContext"]["toolPreTaskResultList"] = [
            {
                "taskName": "股票基金筛选",
                "entityTagListMap": {"1": entity_tags},
            }
        ]

    resp = await post(data_endpoint("finance"), json_body=body, timeout=120.0)
    payload = resp.json_data

    status_err = check_business_status(payload)
    if status_err:
        result["error_code"] = "API_ERROR"
        result["message"] = status_err
        return result

    tables, _, total_rows, err = finance_parse_tables(payload)
    if err:
        result["error_code"] = "PARSE_ERROR"
        result["message"] = err
        data_msg = extract_data_message(payload)
        if data_msg:
            result["message"] = f"{data_msg}\n（{err}）"
        return result

    suffix = unique_suffix()
    excel_path = output_dir / f"mx_data_finance_{suffix}.xlsx"
    md_path = output_dir / f"mx_data_finance_{suffix}.md"
    write_excel(tables, excel_path)
    write_markdown(tables, md_path)

    returned_count = finance_count_entities(tables)
    completeness_warning = None
    if recognized_count > 0 and returned_count < recognized_count:
        completeness_warning = (
            f"警告: 查数结果仅覆盖 {returned_count}/{recognized_count} 个实体，"
            f"缺失 {recognized_count - returned_count} 个。当前一次请求的数据量过大，"
            "多指标或大范围查询可能触发接口返回上限，部分数据可能会有缺失，建议拆分 query 或分批查数。"
        )

    result.update({
        "ok": True,
        "files": [str(excel_path), str(md_path)],
        "csv_path": str(excel_path),
        "md_path": str(md_path),
        "description_path": str(md_path),
        "row_count": total_rows,
        "returned_entity_count": returned_count,
    })
    if completeness_warning:
        result["completeness_warning"] = completeness_warning
    return result


# ---------------------------------------------------------------------------
# Macro data
# ---------------------------------------------------------------------------


def _macro_fieldnames(rows: List[Dict[str, Any]]) -> List[str]:
    fieldnames_set: Dict[str, None] = {}
    for row in rows:
        for k in row:
            fieldnames_set[k] = None

    priority = ["entity_name", "indicator_name", "indicator_code", "frequency", "数据来源"]
    fieldnames = []
    for field in priority:
        if field in fieldnames_set:
            fieldnames.append(field)
            del fieldnames_set[field]

    date_fields = []
    other_fields = []
    for field in fieldnames_set.keys():
        if (field.isdigit() and len(field) == 4) or re.match(r"^\d{4}-\d{2}-\d{2}$", field):
            date_fields.append(field)
        else:
            other_fields.append(field)

    date_fields.sort(reverse=True)
    other_fields.sort()
    fieldnames.extend(other_fields)
    fieldnames.extend(date_fields)
    return fieldnames


async def _query_macro(query: str, output_dir: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "data_type": "macro",
        "query": query,
        "files": [],
        "row_count": 0,
    }

    body = {"query": query, "toolContext": _build_tool_context()}
    resp = await post(data_endpoint("macro"), json_body=body, timeout=60.0)
    payload = resp.json_data

    status_err = check_business_status(payload)
    if status_err:
        result["error_code"] = "API_ERROR"
        result["message"] = status_err
        return result

    frequency_groups = macro_parse_response(payload)
    if not frequency_groups:
        result["error_code"] = "PARSE_ERROR"
        result["message"] = extract_data_message(payload) or "无法解析表格数据"
        return result

    suffix = unique_suffix()
    csv_paths = []
    row_counts = {}
    description_parts = []
    for frequency, rows in frequency_groups.items():
        if not rows:
            continue
        fieldnames = _macro_fieldnames(rows)
        csv_path = output_dir / f"mx_data_macro_{suffix}_{frequency}.csv"
        write_csv(rows, csv_path, fieldnames=fieldnames)
        csv_paths.append(str(csv_path))
        row_counts[frequency] = len(rows)
        description_parts.append(f"频率 [{frequency}]: {len(rows)} 行")

    desc_path = output_dir / f"mx_data_macro_{suffix}_description.txt"
    description_lines = [
        "宏观数据查询结果说明",
        "=" * 40,
        f"查询内容: {query}",
        f"数据频率组数: {len(frequency_groups)}",
        "",
        "各频率数据统计:",
    ]
    for frequency, count in row_counts.items():
        description_lines.append(f"  - {frequency}: {count} 行")
    description_lines.extend(["", "生成的文件:"])
    for csv_path in csv_paths:
        description_lines.append(f"  - {Path(csv_path).name}")
    description_lines.extend(["", "详细说明:", *description_parts])
    write_text_file("\n".join(description_lines), desc_path)

    result.update({
        "ok": True,
        "files": csv_paths + [str(desc_path)],
        "csv_paths": csv_paths,
        "description_path": str(desc_path),
        "row_count": sum(row_counts.values()),
    })
    return result


# ---------------------------------------------------------------------------
# Screener data
# ---------------------------------------------------------------------------


async def _query_screener(
    query: str,
    select_type: str,
    output_dir: Path,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "data_type": "screener",
        "query": query,
        "selectType": select_type,
        "files": [],
        "row_count": 0,
    }

    body = {
        "query": query,
        "selectType": select_type,
        "toolContext": _build_tool_context(),
    }
    resp = await post(data_endpoint("screener"), json_body=body, timeout=60.0)
    payload = resp.json_data

    status_err = check_business_status(payload)
    if status_err:
        result["error_code"] = "API_ERROR"
        result["message"] = status_err
        return result

    rows = screener_parse_response(payload, select_type)
    if not rows:
        raw_message = payload.get("message")
        if isinstance(raw_message, str) and raw_message.strip():
            result["error_code"] = "API_ERROR"
            result["message"] = raw_message.strip()
            return result
        result["error_code"] = "NO_DATA"
        result["message"] = "无符合问句要求的数据"
        return result

    suffix = unique_suffix()
    csv_path = output_dir / f"mx_data_screener_{suffix}.csv"
    fieldnames = list(rows[0].keys())
    write_csv(rows, csv_path, fieldnames=fieldnames)

    desc_path = output_dir / f"mx_data_screener_{suffix}_description.txt"
    description_lines = [
        "选股/选板块/选基金 结果说明",
        "=" * 40,
        f"查询内容: {query}",
        f"筛选类型: {select_type}",
        f"数据行数: {len(rows)}",
        f"列名（中文）: {', '.join(fieldnames)}",
    ]
    write_text_file("\n".join(description_lines), desc_path)

    result.update({
        "ok": True,
        "files": [str(csv_path), str(desc_path)],
        "csv_path": str(csv_path),
        "description_path": str(desc_path),
        "row_count": len(rows),
    })
    return result


# ---------------------------------------------------------------------------
# Comparable data
# ---------------------------------------------------------------------------


async def _query_comparable(query: str, output_dir: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "data_type": "comparable",
        "query": query,
        "files": [],
        "row_count": 0,
    }

    resp = await post(data_endpoint("comparable"), json_body={"question": query}, timeout=120.0)
    payload = resp.json_data

    status_err = check_business_status(payload)
    if status_err:
        result["error_code"] = "API_ERROR"
        result["message"] = status_err
        return result

    records = comparable_parse_response(payload)
    if not records:
        result["error_code"] = "NO_DATA"
        result["message"] = "未获取到可比公司数据"
        return result

    suffix = unique_suffix()
    xlsx_path = output_dir / f"mx_data_comparable_{suffix}.xlsx"
    csv_path = output_dir / f"mx_data_comparable_{suffix}.csv"

    # Write each record as a sheet in Excel, and combine all into a single CSV.
    tables = []
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        rows = [record]
        fieldnames = list(record.keys())
        tables.append({"sheet_name": f"section_{i + 1}", "rows": rows, "fieldnames": fieldnames})
    write_excel(tables, xlsx_path)

    # Flatten all records to CSV.
    all_fieldnames = []
    seen = set()
    for record in records:
        if isinstance(record, dict):
            for k in record.keys():
                if k not in seen:
                    seen.add(k)
                    all_fieldnames.append(k)
    write_csv(records, csv_path, fieldnames=all_fieldnames)

    result.update({
        "ok": True,
        "files": [str(xlsx_path), str(csv_path)],
        "row_count": len(records),
    })
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def query_data(
    query: str,
    data_type: str,
    *,
    indicators: Optional[str] = None,
    select_type: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    out = ensure_output_dir("mx-data", output_dir)

    if data_type == "finance":
        return await _query_finance(query, indicators, out)
    elif data_type == "macro":
        return await _query_macro(query, out)
    elif data_type == "screener":
        if not select_type:
            return {
                "ok": False,
                "error_code": "MISSING_SELECT_TYPE",
                "message": "--data-type screener 时必须提供 --select-type",
            }
        return await _query_screener(query, select_type, out)
    elif data_type == "comparable":
        return await _query_comparable(query, out)
    else:
        return {
            "ok": False,
            "error_code": "UNSUPPORTED_DATA_TYPE",
            "message": f"不支持的数据类型: {data_type}",
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="结构化金融/宏观/筛选/可比数据查询")
    parser.add_argument("--query", type=str, default="", help="自然语言查询")
    parser.add_argument(
        "--data-type",
        type=str,
        required=True,
        choices=["finance", "macro", "screener", "comparable"],
        help="数据类型",
    )
    parser.add_argument("--indicators", type=str, default=None, help="finance 多实体时必填")
    parser.add_argument(
        "--select-type",
        type=str,
        default=None,
        choices=["A股", "港股", "美股", "基金", "ETF", "可转债", "板块"],
        help="screener 必填",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="输出目录（默认 miaoxiang/mx-data）",
    )
    return parser.parse_args()


def main() -> None:
    reconfigure_stdio()
    args = parse_args()
    query = parse_query(args)

    if not query:
        print(
            json.dumps(
                {"ok": False, "error_code": "BAD_REQUEST", "message": "缺少 query 参数"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    async def _main() -> None:
        try:
            result = await query_data(
                query=query,
                data_type=args.data_type,
                indicators=args.indicators,
                select_type=args.select_type,
                output_dir=args.output_dir,
            )
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0 if result.get("ok") else 2)
        except ApiCallError as e:
            err = {
                "ok": False,
                "error_code": e.code,
                "message": GENERAL_ERROR_MSG,
                "detail": e.detail,
            }
            print(json.dumps(err, ensure_ascii=False))
            sys.exit(2)
        except Exception as e:
            err = {
                "ok": False,
                "error_code": "UNEXPECTED_ERROR",
                "message": GENERAL_ERROR_MSG,
                "detail": _safe_str(e),
                "traceback": traceback.format_exc(limit=8),
            }
            print(json.dumps(err, ensure_ascii=False))
            sys.exit(2)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_main())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
