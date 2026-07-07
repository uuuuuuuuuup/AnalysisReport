"""
Data parsing and normalization helpers for mx-data skill.

Covers finance searchData, macro searchMacroData, screener selectSecurity,
and comparable company analysis responses.
"""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def flatten_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


# ---------------------------------------------------------------------------
# Finance data parsing
# ---------------------------------------------------------------------------


def _ordered_keys(table: Dict[str, Any], indicator_order: List[Any]) -> List[Any]:
    data_keys = [k for k in table.keys() if k != "headName"]
    key_map = {str(k): k for k in data_keys}
    preferred: List[Any] = []
    seen: Set[str] = set()
    for key in indicator_order:
        key_str = str(key)
        if key_str in key_map and key_str not in seen:
            preferred.append(key_map[key_str])
            seen.add(key_str)
    for key in data_keys:
        key_str = str(key)
        if key_str not in seen:
            preferred.append(key)
            seen.add(key_str)
    return preferred


def _normalize_values(raw_values: List[Any], expected_len: int) -> List[str]:
    values = [flatten_value(v) for v in raw_values]
    if len(values) < expected_len:
        values.extend([""] * (expected_len - len(values)))
    return values[:expected_len]


def _return_code_map(block: Dict[str, Any]) -> Dict[str, str]:
    for key in ("returnCodeMap", "returnCodeNameMap", "codeMap"):
        data = block.get(key)
        if isinstance(data, dict):
            return {str(k): flatten_value(v) for k, v in data.items()}
    return {}


def _format_indicator_label(key: str, name_map: Dict[str, Any], code_map: Dict[str, str]) -> str:
    mapped = name_map.get(key)
    if mapped is None and key.isdigit():
        mapped = name_map.get(int(key))
    if mapped not in (None, ""):
        return flatten_value(mapped)
    mapped_code = code_map.get(key)
    if mapped_code not in (None, ""):
        return flatten_value(mapped_code)
    if key.isdigit():
        return ""
    return key


def _table_to_rows_generic(table: Any, name_map: Optional[Dict[str, str]]) -> List[Dict[str, Any]]:
    name_map = name_map or {}
    if isinstance(table, list):
        if not table:
            return []
        if isinstance(table[0], dict):
            rows = table
        else:
            rows = [
                dict(zip([f"column_{i}" for i in range(len(table[0]))], row))
                for row in table
            ]
    elif isinstance(table, dict):
        vals = [v for v in table.values() if isinstance(v, list)]
        if vals and all(isinstance(v, list) for v in table.values()):
            n = len(vals[0])
            if all(len(v) == n for v in vals):
                cols = list(table.keys())
                rows = [dict(zip(cols, [v[i] for v in table.values()])) for i in range(n)]
            else:
                rows = []
        else:
            cols = table.get("columns") or table.get("fields") or []
            rows_data = table.get("rows") or table.get("data") or []
            if not cols and rows_data:
                cols = [f"column_{i}" for i in range(len(rows_data[0]))]
            rows = [dict(zip(cols, r)) for r in rows_data]
    else:
        return []
    return [{name_map.get(k, k): flatten_value(v) for k, v in row.items()} for row in rows]


def finance_table_to_rows(block: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    table = block.get("table") or {}
    name_map = block.get("nameMap") or {}
    if isinstance(name_map, list):
        name_map = {str(i): v for i, v in enumerate(name_map)}
    elif not isinstance(name_map, dict):
        name_map = {}

    if not isinstance(table, dict):
        rows = _table_to_rows_generic(table, name_map)
        fieldnames = list(rows[0].keys()) if rows else []
        return rows, fieldnames

    headers = table.get("headName") or []
    if not isinstance(headers, list):
        headers = []
    order = _ordered_keys(table, block.get("indicatorOrder") or [])
    entity_name = flatten_value(block.get("entityName") or "") or "指标"
    code_map = _return_code_map(block)

    rows: List[Dict[str, Any]] = []
    data_key_count = len([key for key in table.keys() if key != "headName"])

    if len(headers) > 1 and data_key_count >= 1:
        fieldnames = [entity_name] + [flatten_value(h) for h in headers]
        for key in order:
            raw_values = table.get(key, [])
            if not isinstance(raw_values, list):
                raw_values = [raw_values]
            values = _normalize_values(raw_values, len(headers))
            label = _format_indicator_label(str(key), name_map, code_map)
            rows.append(dict(zip(fieldnames, [label] + values)))
        return rows, fieldnames

    if len(headers) == 1 and data_key_count >= 1:
        fieldnames = [entity_name, flatten_value(headers[0])]
        for key in order:
            raw_values = table.get(key, [])
            value = raw_values[0] if isinstance(raw_values, list) and raw_values else raw_values
            label = _format_indicator_label(str(key), name_map, code_map)
            rows.append({fieldnames[0]: label, fieldnames[1]: flatten_value(value)})
        return rows, fieldnames

    fallback_rows = _table_to_rows_generic(table, name_map)
    if fallback_rows:
        return fallback_rows, list(fallback_rows[0].keys())
    return [], []


def finance_extract_dto_list(api_result: Any) -> Tuple[Optional[List[Any]], Optional[str]]:
    if not isinstance(api_result, dict):
        return None, "接口返回不是 JSON 对象"

    dto_list = api_result.get("dataTableDTOList")
    if isinstance(dto_list, list):
        return dto_list, None

    data_node = api_result.get("data")
    if isinstance(data_node, dict):
        search_result = data_node.get("searchDataResultDTO")
        if isinstance(search_result, dict):
            dto_list = search_result.get("dataTableDTOList")
            if isinstance(dto_list, list):
                return dto_list, None
        dto_list = data_node.get("dataTableDTOList")
        if isinstance(dto_list, list):
            return dto_list, None

    return None, "接口返回中无 dataTableDTOList"


_ENTITY_CODE_RE = re.compile(r"\(([0-9A-Z.]+\.[A-Z]+)\)")


def finance_extract_entity_code(text: Any) -> Optional[str]:
    match = _ENTITY_CODE_RE.search(flatten_value(text))
    return match.group(1) if match else None


def finance_count_entities(tables: List[Dict[str, Any]]) -> int:
    codes: Set[str] = set()
    for table in tables:
        code = finance_extract_entity_code(table.get("sheet_name"))
        if code:
            codes.add(code)
        for field in table.get("fieldnames") or []:
            code = finance_extract_entity_code(field)
            if code:
                codes.add(code)
        fieldnames = table.get("fieldnames") or []
        rows = table.get("rows") or []
        if fieldnames and rows:
            first_col = fieldnames[0]
            for row in rows:
                code = finance_extract_entity_code(row.get(first_col, ""))
                if code:
                    codes.add(code)
    return len(codes)


def finance_parse_tables(api_result: Any) -> Tuple[List[Dict[str, Any]], List[str], int, Optional[str]]:
    dto_list, extract_err = finance_extract_dto_list(api_result)
    if extract_err:
        return [], [], 0, extract_err
    if not dto_list:
        return [], [], 0, "接口返回的 dataTableDTOList 为空"

    condition_parts: List[str] = []
    tables: List[Dict[str, Any]] = []
    total_rows = 0
    used_sheet_names: Set[str] = set()

    for i, dto in enumerate(dto_list):
        if not isinstance(dto, dict):
            continue
        sheet_name = dto.get("title") or dto.get("inputTitle") or dto.get("entityName") or f"表{i + 1}"
        sheet_name = re.sub(r"[:\\/?*\[\]]", "_", str(sheet_name))[:31]
        base = sheet_name or "表"
        candidate = base
        idx = 2
        while candidate in used_sheet_names:
            suffix = f"_{idx}"
            if len(base) + len(suffix) > 31:
                candidate = base[: 31 - len(suffix)] + suffix
            else:
                candidate = base + suffix
            idx += 1
        used_sheet_names.add(candidate)
        sheet_name = candidate

        condition = dto.get("condition")
        if condition is not None and condition != "":
            entity = dto.get("entityName") or sheet_name
            condition_parts.append(f"[{entity}]\n{condition}")

        rows, fieldnames = finance_table_to_rows(dto)
        if not rows:
            continue
        tables.append({"sheet_name": sheet_name, "rows": rows, "fieldnames": fieldnames})
        total_rows += len(rows)

    if not tables:
        return [], condition_parts, 0, "dataTableDTOList 中无有效 table 数据"
    return tables, condition_parts, total_rows, None


# ---------------------------------------------------------------------------
# Macro data parsing
# ---------------------------------------------------------------------------


def _extract_frequency(entity_name: str) -> str:
    frequency_map = {
        "年": "yearly",
        "年度": "yearly",
        "季度": "quarterly",
        "季": "quarterly",
        "月": "monthly",
        "月度": "monthly",
        "周": "weekly",
        "周度": "weekly",
        "日": "daily",
        "日度": "daily",
        "天": "daily",
    }
    match = re.search(r"[（(]([^）)]+)[）)]", entity_name)
    if match:
        freq_chinese = match.group(1)
        return frequency_map.get(freq_chinese, freq_chinese)
    return "unknown"


def macro_parse_table(data_item: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    rows = []
    table = data_item.get("table", {})
    name_map = data_item.get("nameMap", {})
    entity_name = data_item.get("entityName", "")
    frequency = _extract_frequency(entity_name)

    if not table or not isinstance(table, dict):
        return rows, frequency

    headers = table.get("headName", [])
    if not headers:
        headers = table.get("date", [])
        if not headers:
            return rows, frequency

    exclude_keys = {"headName", "headNameSub", "date"}
    metric_keys = [k for k in table.keys() if k not in exclude_keys]

    for metric_key in metric_keys:
        values = table.get(metric_key, [])
        if not values:
            continue
        metric_name = name_map.get(metric_key, metric_key)
        row = {
            "entity_name": entity_name,
            "indicator_code": metric_key,
            "indicator_name": metric_name,
            "frequency": frequency,
        }
        for i, header in enumerate(headers):
            if i < len(values):
                value = values[i]
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value) if value else ""
                row[header] = value
        rows.append(row)

    return rows, frequency


def macro_parse_response(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Return {frequency: rows}."""
    result: Dict[str, List[Dict[str, Any]]] = {}
    if not isinstance(payload, dict):
        return result
    data = payload.get("data")
    if not isinstance(data, dict):
        return result
    data_list = data.get("dataTables", [])
    if not isinstance(data_list, list):
        return result
    for item_list in data_list:
        if not isinstance(item_list, dict):
            continue
        rows, frequency = macro_parse_table(item_list)
        if rows:
            if frequency not in result:
                result[frequency] = []
            result[frequency].extend(rows)
    return result


# ---------------------------------------------------------------------------
# Screener data parsing
# ---------------------------------------------------------------------------


def screener_build_column_map(columns: List[Dict]) -> Dict[str, str]:
    name_map = {}
    for col in columns or []:
        if not isinstance(col, dict):
            continue
        en_key = col.get("field", "") or col.get("name", "") or col.get("key", "")
        cn_name = col.get("displayName", "") or col.get("title", "") or col.get("label", "")
        if col.get("dateMsg"):
            cn_name = f"{cn_name} {col.get('dateMsg')}"
        if en_key is not None and cn_name is not None:
            name_map[str(en_key)] = str(cn_name)
    return name_map


def screener_columns_order(columns: List[Dict]) -> List[str]:
    order = []
    for col in columns or []:
        if not isinstance(col, dict):
            continue
        en_key = col.get("field") or col.get("name") or col.get("key")
        if en_key is not None:
            order.append(str(en_key))
    return order


def _parse_partial_results_markdown(partial_results: str) -> List[Dict[str, Any]]:
    if not partial_results or not isinstance(partial_results, str):
        return []
    lines = [ln.strip() for ln in partial_results.strip().splitlines() if ln.strip()]
    if not lines:
        return []

    def split_cells(line: str) -> List[str]:
        return [c.strip() for c in line.split("|") if c.strip() != ""]

    header_cells = split_cells(lines[0])
    if not header_cells:
        return []
    data_start = 1
    if data_start < len(lines) and re.match(r"^[\s\|\-]+$", lines[data_start]):
        data_start = 2
    rows = []
    for i in range(data_start, len(lines)):
        cells = split_cells(lines[i])
        if len(cells) < len(header_cells):
            cells.extend([""] * (len(header_cells) - len(cells)))
        cells = cells[: len(header_cells)]
        rows.append(dict(zip(header_cells, cells)))
    return rows


def screener_datalist_to_rows(
    datalist: List[Dict],
    column_map: Dict[str, str],
    column_order: List[str],
) -> List[Dict[str, Any]]:
    if not datalist:
        return []
    rows = []
    for row in datalist:
        if not isinstance(row, dict):
            continue
        cn_row = {}
        for en_key in column_order:
            if en_key not in row:
                continue
            cn_name = column_map.get(en_key, en_key)
            val = row[en_key]
            if val is None:
                cn_row[cn_name] = ""
            elif isinstance(val, (dict, list)):
                cn_row[cn_name] = json.dumps(val, ensure_ascii=False)
            else:
                cn_row[cn_name] = str(val)
        rows.append(cn_row)
    return rows


def screener_drop_sector_columns(rows: List[Dict], select_type: str) -> List[Dict[str, Any]]:
    if select_type != "板块" or not rows:
        return rows
    blocked = {"板块编码", "指数内码"}
    return [{k: v for k, v in row.items() if str(k).strip() not in blocked} for row in rows]


def screener_parse_response(raw: Dict[str, Any], select_type: str) -> List[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return []

    all_results = raw.get("allResults")
    if not isinstance(all_results, dict):
        all_results = {}
    result_node = all_results.get("result")
    if not isinstance(result_node, dict):
        result_node = {}

    data_list = result_node.get("dataList", [])
    columns = result_node.get("columns", [])

    if isinstance(data_list, list) and data_list:
        column_map = screener_build_column_map(columns)
        column_order = screener_columns_order(columns)
        rows = screener_datalist_to_rows(data_list, column_map, column_order)
    else:
        rows = _parse_partial_results_markdown(raw.get("partialResults", ""))

    return screener_drop_sector_columns(rows, select_type)


# ---------------------------------------------------------------------------
# Comparable data parsing
# ---------------------------------------------------------------------------


def comparable_parse_response(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the list of records from the comparable-company-analysis response."""
    if not isinstance(raw, dict):
        return []
    data = raw.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []
