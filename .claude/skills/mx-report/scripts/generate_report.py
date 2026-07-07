"""
mx-report: Generate Eastmoney research reports (industry, topic, coverage, tracker, earnings).

Outputs a JSON result with title, content, attachments, and share_url.
"""

import argparse
import asyncio
import json
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
from mx_common.attachments import decode_attachments
from mx_common.cli import parse_query, reconfigure_stdio
from mx_common.content import (
    check_business_status,
    extract_article_id,
    extract_docx_text,
    extract_share_url,
    extract_text,
    extract_title,
)
from mx_common.endpoints import get_endpoint, report_endpoint
from mx_common.entity import EntityInfo, recognize_entity
from mx_common.output import default_output_dir, ensure_output_dir, unique_suffix


TOOL_NAME = "研究报告生成"
GENERAL_ERROR_MSG = "报告生成服务暂时不可用，请稍后重试。"
ERROR_ENTITY_MSG = "目前暂不支持此类实体进行分析。"
SUPPORTED_EARNINGS_CLASS_CODES = {"002001", "002003", "002004"}


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _safe_article_id(value: Any) -> str:
    article_id = _safe_str(value)
    if not article_id:
        article_id = uuid.uuid4().hex
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", article_id)


def _clean_report_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    cleaned = re.sub(r"\[[^\]]*\]\((?:blockTitle|table)://[^)]*\)", "", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = cleaned.replace("\\n", "\n")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _build_tracker_content(entity_type: str, summary_content: str) -> str:
    return (
        f"已生成{entity_type}跟踪报告，包括行业和个股的多种信源摘要。"
        "此处省略正文内容，仅展示总结章节，如需查看完整内容，请查看附件获取报告详情。\n\n"
        f"{summary_content}"
    )


async def _call_report_api(report_type: str, query: str) -> Dict[str, Any]:
    url = report_endpoint(report_type)
    body = {"query": query}
    resp = await post(url, json_body=body, timeout=1200.0)
    return resp.json_data


async def _fetch_report_periods(entity: EntityInfo) -> List[str]:
    url = get_endpoint("report_earnings_report_list")
    resp = await post(url, json_body={"emCode": entity.em_code}, timeout=60.0)
    data = resp.json_data.get("data") if isinstance(resp.json_data, dict) else {}
    if not isinstance(data, dict):
        return []
    src = data.get("reportDateList", [])
    if not isinstance(src, list):
        return []
    periods: List[str] = []
    for item in src:
        if isinstance(item, str):
            periods.append(item)
        elif isinstance(item, dict):
            report_date = item.get("reportDate") or item.get("report_date") or item.get("date")
            if report_date:
                periods.append(str(report_date))
    return periods


def _choose_report_date(periods: List[str], query: str) -> Optional[str]:
    if not periods:
        return None
    # If the query contains a date like YYYY-MM-DD, try to match it.
    date_re = re.search(r"(\d{4}-\d{2}-\d{2})", query)
    if date_re:
        candidate = date_re.group(1)
        if candidate in periods:
            return candidate
    # Default to the latest period.
    return periods[0]


async def _generate_earnings_report(query: str, output_dir: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "report_type": "earnings",
        "query": query,
        "title": "",
        "content": "",
        "share_url": "",
        "article_id": "",
        "report_date": "",
        "attachments": [],
    }

    try:
        entity = await recognize_entity(query, api_type="dialog")
    except ApiCallError as e:
        return {**result, "ok": False, "error_code": e.code, "message": e.detail}
    except Exception as e:
        return {**result, "ok": False, "error_code": "ERROR_ENTITY", "message": ERROR_ENTITY_MSG}

    if entity.class_code not in SUPPORTED_EARNINGS_CLASS_CODES:
        return {**result, "ok": False, "error_code": "ERROR_ENTITY", "message": "目前仅支持沪深京港美实体进行业绩点评"}

    periods = await _fetch_report_periods(entity)
    if not periods:
        return {**result, "ok": False, "error_code": "NO_REPORT_PERIOD", "message": "暂无该实体的可用报告期数据"}

    report_date = _choose_report_date(periods, query)
    result["report_date"] = report_date

    url = get_endpoint("report_earnings")
    resp = await post(url, json_body={"query": entity.em_code, "reportDate": report_date}, timeout=1200.0)
    payload = resp.json_data

    status_err = check_business_status(payload)
    if status_err:
        return {**result, "ok": False, "error_code": "API_ERROR", "message": status_err}

    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return {**result, "ok": False, "error_code": "API_ERROR", "message": "接口返回数据为空"}

    title = _safe_str(data.get("title"), default="业绩点评报告")
    content = _safe_str(data.get("content"))
    share_url = _safe_str(data.get("shareUrl"))
    article_id = _safe_article_id(data.get("articleId"))

    output_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir = output_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    attachments = decode_attachments(
        data,
        str(attachments_dir),
        article_id=article_id,
        file_map=[
            ("pdfBase64", "pdf", "PDF"),
            ("wordBase64", "doc", "DOC"),
            ("dataSheetBase64", "xlsx", "Excel"),
        ],
    )

    result.update({
        "ok": True,
        "title": title,
        "content": content,
        "share_url": share_url,
        "article_id": article_id,
        "attachments": attachments,
    })
    return result


async def _generate_standard_report(
    report_type: str,
    query: str,
    output_dir: Path,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "report_type": report_type,
        "query": query,
        "title": "",
        "content": "",
        "share_url": "",
        "article_id": "",
        "entity_type": "",
        "attachments": [],
    }

    if len(query) > 500:
        return {**result, "ok": False, "error_code": "ERROR_TOPIC_TOO_LONG", "message": "字数超出限制，请尝试其它主体。"}

    payload = await _call_report_api(report_type, query)
    status_err = check_business_status(payload)
    if status_err:
        return {**result, "ok": False, "error_code": "API_ERROR", "message": status_err}

    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return {**result, "ok": False, "error_code": "API_ERROR", "message": "接口返回数据为空"}

    title = extract_title(payload)
    content = extract_text(payload)
    if report_type == "topic":
        content = extract_text(payload, priority=["content", "displayData", "answer", "summary"])
    content = _clean_report_text(content)

    share_url = extract_share_url(payload)
    article_id = _safe_article_id(extract_article_id(payload))
    entity_type = _safe_str(data.get("entityType") or data.get("entity_type"))

    if report_type == "tracker":
        content = _build_tracker_content(entity_type or "行业/个股", content or "暂无总结内容，请查看附件获取报告详情。")

    output_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir = output_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    attachments = decode_attachments(
        data,
        str(attachments_dir),
        article_id=article_id,
        file_map=[
            ("pdfBase64", "pdf", "PDF"),
            ("wordBase64", "docx", "DOCX"),
        ],
    )

    # Industry fallback: if content is empty and we saved a DOCX, extract text from it.
    if report_type == "industry" and not content and attachments:
        for att in attachments:
            if att.get("type") == "DOCX":
                docx_text = extract_docx_text(att["path"])
                if docx_text:
                    content = docx_text
                    break

    result.update({
        "ok": True,
        "title": title or "研究报告",
        "content": content,
        "share_url": share_url,
        "article_id": article_id,
        "entity_type": entity_type,
        "attachments": attachments,
    })
    return result


async def generate_report(
    query: str,
    report_type: str,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    out = ensure_output_dir("mx-report", output_dir)

    if report_type == "earnings":
        return await _generate_earnings_report(query, out)
    return await _generate_standard_report(report_type, query, out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成研究报告")
    parser.add_argument("--query", type=str, default="", help="用户查询文本")
    parser.add_argument(
        "--report-type",
        type=str,
        required=True,
        choices=["industry", "topic", "coverage", "tracker", "earnings"],
        help="报告类型",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="附件保存目录（默认 miaoxiang/mx-report）",
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
            result = await generate_report(
                query=query,
                report_type=args.report_type,
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
