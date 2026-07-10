"""
Extract readable text from Eastmoney API response JSON.

Handles the common envelope shapes and field priority used across
report, diagnosis, search, and assistant APIs.
"""

import json
import re
import zipfile
from typing import Any, Dict, List, Optional


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def extract_text(payload: Dict[str, Any], priority: Optional[List[str]] = None) -> str:
    """
    Extract readable text from a JSON payload.

    Priority:
    1. data.displayData
    2. data.content
    3. data.answer
    4. data.summary
    5. llmSearchResponse
    6. searchResponse
    7. displayData / content / answer / summary at the top level
    """
    if not isinstance(payload, dict):
        return ""

    default_priority = [
        "displayData",
        "content",
        "answer",
        "summary",
        "llmSearchResponse",
        "searchResponse",
    ]
    keys = priority or default_priority

    # Try inside data first.
    data = payload.get("data")
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (list, dict)):
                return json.dumps(value, ensure_ascii=False, indent=2)

    # Fallback to top-level fields.
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False, indent=2)

    # If nothing matched, return a compact JSON representation of the payload.
    return json.dumps(payload, ensure_ascii=False, indent=2)


def extract_title(payload: Dict[str, Any]) -> str:
    """Extract title from data.title or top-level title."""
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data")
    if isinstance(data, dict):
        title = data.get("title")
        if isinstance(title, str):
            return title.strip()
    title = payload.get("title")
    if isinstance(title, str):
        return title.strip()
    return ""


def extract_share_url(payload: Dict[str, Any]) -> str:
    """Extract shareUrl from data.shareUrl or top-level shareUrl."""
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data")
    if isinstance(data, dict):
        url = data.get("shareUrl")
        if isinstance(url, str):
            return url.strip()
    url = payload.get("shareUrl")
    if isinstance(url, str):
        return url.strip()
    return ""


def extract_article_id(payload: Dict[str, Any]) -> str:
    """Extract articleId from data.articleId or top-level articleId."""
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data")
    if isinstance(data, dict):
        aid = data.get("articleId")
        if isinstance(aid, str):
            return aid.strip()
    aid = payload.get("articleId")
    if isinstance(aid, str):
        return aid.strip()
    return ""


def extract_references(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract reference list from data.refIndexList.

    Each reference normalizes the common fields: refId, type, referenceType,
    markdown, title, jumpUrl, source.
    """
    refs: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return refs

    data = payload.get("data")
    if not isinstance(data, dict):
        return refs

    ref_list = data.get("refIndexList")
    if not isinstance(ref_list, list):
        return refs

    for item in ref_list:
        if not isinstance(item, dict):
            continue
        ref: Dict[str, Any] = {
            "refId": item.get("refId"),
            "type": _safe_str(item.get("type")),
            "referenceType": _safe_str(item.get("referenceType")),
        }
        for key in ("markdown", "title", "jumpUrl"):
            value = item.get(key)
            if value is not None:
                ref[key] = _safe_str(value)

        source = item.get("source")
        if source is None:
            nested = item.get("data")
            if isinstance(nested, dict):
                source = nested.get("source")
        if source is not None:
            ref["source"] = _safe_str(source)

        refs.append(ref)

    return refs


def extract_data_table_dto_list(payload: Dict[str, Any]) -> List[Any]:
    """Extract dataTableDTOList from the various known response shapes."""
    if not isinstance(payload, dict):
        return []

    dto_list = payload.get("dataTableDTOList")
    if isinstance(dto_list, list):
        return dto_list

    data = payload.get("data")
    if isinstance(data, dict):
        search_result = data.get("searchDataResultDTO")
        if isinstance(search_result, dict):
            dto_list = search_result.get("dataTableDTOList")
            if isinstance(dto_list, list):
                return dto_list
        dto_list = data.get("dataTableDTOList")
        if isinstance(dto_list, list):
            return dto_list

    return []


def check_business_status(payload: Dict[str, Any]) -> Optional[str]:
    """Return an error message if the business status is non-successful."""
    if not isinstance(payload, dict):
        return "接口返回不是 JSON 对象"

    code = payload.get("code")
    status = payload.get("status")
    success_values = (None, 0, 200, "0", "200")
    if code not in success_values or status not in success_values:
        message = _safe_str(payload.get("message") or "业务状态非成功")
        return f"接口业务错误: code={code}, status={status}, message={message}"
    return None


def extract_data_message(payload: Dict[str, Any]) -> Optional[str]:
    """Extract a user-facing message from data.message (for quota/truncation hints)."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict):
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


def extract_docx_text(docx_path: str) -> str:
    """Best-effort plain text extraction from a DOCX file without extra dependencies."""
    try:
        import zipfile

        with zipfile.ZipFile(docx_path, "r") as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        return ""
    text = re.sub(r"(?s)<w:t[^>]*>(.*?)</w:t>", r"\1\n", xml)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
