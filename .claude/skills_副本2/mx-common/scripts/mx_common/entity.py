"""
Entity recognition and normalization for Eastmoney APIs.

Supports both the saas/dialogTagsV2 entity endpoints and builds the emCode
used by the earnings-review report-list/comment APIs.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from .api_client import ApiCallError, base_headers
from .endpoints import get_endpoint


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


@dataclass
class EntityInfo:
    """Normalized entity information."""

    class_code: str
    secu_code: str
    market_char: str
    secu_name: str = ""

    @property
    def em_code(self) -> str:
        """Construct emCode like 300059.SZ from secu_code and market_char."""
        if "." in self.secu_code:
            return self.secu_code
        suffix = (self.market_char or "").strip()
        if not suffix:
            raise RuntimeError("实体识别缺少 marketChar，无法拼接 emCode")
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        return f"{self.secu_code}{suffix}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classCode": self.class_code,
            "secuCode": self.secu_code,
            "marketChar": self.market_char,
            "secuName": self.secu_name,
            "emCode": self.em_code,
        }


def _first_entity_from_response(data: Any) -> Optional[Dict[str, Any]]:
    """Extract the first entity candidate from a dialogTagsV2/saas response."""
    if not isinstance(data, dict):
        return None

    d = data.get("data")
    if isinstance(d, dict):
        entity_metric_list = d.get("entityMetricList")
        if isinstance(entity_metric_list, list) and entity_metric_list:
            group = entity_metric_list[0]
            if isinstance(group, list) and group:
                return group[0] if isinstance(group[0], dict) else None
        entity_list = d.get("entityList")
        if isinstance(entity_list, list) and entity_list:
            return entity_list[0] if isinstance(entity_list[0], dict) else None
    elif isinstance(d, list) and d and isinstance(d[0], dict):
        return d[0]
    return None


def parse_entity_info(data: Dict[str, Any]) -> EntityInfo:
    """Parse EntityInfo from the first entity candidate in a response."""
    first = _first_entity_from_response(data)
    if not isinstance(first, dict):
        raise RuntimeError("实体识别未找到有效实体")

    class_code = _safe_str(first.get("classCode") or first.get("class_code"))
    secu_code = _safe_str(first.get("secuCode") or first.get("secu_code"))
    market_char = _safe_str(first.get("marketChar") or first.get("market_char"))
    secu_name = _safe_str(first.get("shortName") or first.get("secuName") or first.get("secu_name"))

    if not secu_code:
        raise RuntimeError("实体识别缺少 secuCode")

    return EntityInfo(
        class_code=class_code,
        secu_code=secu_code,
        market_char=market_char,
        secu_name=secu_name,
    )


def normalize_saas_tag(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a saas entity tag for use in finance-data batch queries."""
    entity_id = _safe_str(raw.get("entityId")).strip()
    if not entity_id:
        raise ValueError("实体识别结果缺少 entityId")
    tag: Dict[str, Any] = {"entityId": entity_id}
    for field in ("entityId", "secuCode", "marketChar", "fullName", "market", "classCode"):
        if field == "entityId":
            continue
        value = raw.get(field)
        if value not in (None, ""):
            tag[field] = _safe_str(value)
    return tag


def extract_saas_tags(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract normalized saas entity tags from a searchData response."""
    if not isinstance(data, dict):
        return []

    d = data.get("data")
    if not isinstance(d, dict):
        return []

    raw_items: List[Dict[str, Any]] = []
    entity_metric_list = d.get("entityMetricList")
    if isinstance(entity_metric_list, list):
        for group in entity_metric_list:
            if isinstance(group, list) and group and isinstance(group[0], dict):
                raw_items.append(group[0])
    else:
        entity_list = d.get("entityList")
        if isinstance(entity_list, list):
            for item in entity_list:
                if isinstance(item, dict):
                    raw_items.append(item)

    tags: List[Dict[str, Any]] = []
    seen: set = set()
    for item in raw_items:
        try:
            tag = normalize_saas_tag(item)
            entity_id = tag["entityId"]
            if entity_id not in seen:
                tags.append(tag)
                seen.add(entity_id)
        except ValueError:
            continue
    return tags


async def recognize_entity(query: str, *, api_type: str = "dialog") -> EntityInfo:
    """
    Recognize a single entity from a natural language query.

    api_type: "dialog" uses dialogTagsV2; "saas" uses the saas entity endpoint.
    """
    if api_type == "dialog":
        url = get_endpoint("entity_dialog")
        payload: Dict[str, Any] = {"content": query}
    elif api_type == "saas":
        url = get_endpoint("entity_saas")
        payload = {
            "content": query,
            "typeCodes": "002,006005,006006,006007,006001,006002,006009,006010,006011,006012,005101,005201,005202,005203,005204,016,001001,001002,003007,003005,003002,003003,003008,003006,003004,003001,003200,003100,007,008,004,010,003300,003400,003500,003600,003700",
        }
    else:
        raise ValueError(f"Unsupported entity API type: {api_type}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers=base_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ApiCallError(
            "HTTP_ERROR",
            f"HTTP {exc.response.status_code}",
        ) from exc
    except Exception as exc:
        raise ApiCallError("NETWORK_ERROR", str(exc)) from exc

    return parse_entity_info(data)


async def recognize_entities_saas(query: str) -> List[Dict[str, Any]]:
    """Recognize multiple entities using the saas endpoint and return normalized tags."""
    url = get_endpoint("entity_saas")
    payload = {
        "content": query,
        "typeCodes": "002,006005,006006,006007,006001,006002,006009,006010,006011,006012,005101,005201,005202,005203,005204,016,001001,001002,003007,003005,003002,003003,003008,003006,003004,003001,003200,003100,007,008,004,010,003300,003400,003500,003600,003700",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers=base_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ApiCallError("HTTP_ERROR", f"HTTP {exc.response.status_code}") from exc
    except Exception as exc:
        raise ApiCallError("NETWORK_ERROR", str(exc)) from exc

    tags = extract_saas_tags(data)
    if not tags:
        # Fallback: return the single entity if no multi-entity tags were found.
        entity = parse_entity_info(data)
        return [normalize_saas_tag(entity.to_dict())]
    return tags


__all__ = [
    "EntityInfo",
    "parse_entity_info",
    "normalize_saas_tag",
    "extract_saas_tags",
    "recognize_entity",
    "recognize_entities_saas",
]
