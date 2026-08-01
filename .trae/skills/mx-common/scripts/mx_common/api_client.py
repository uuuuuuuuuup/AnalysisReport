"""
Unified async HTTP client for Eastmoney MCP APIs.

Responsibilities:
- Inject EM_API_KEY (env var, single fallback default in this module only).
- Provide standard headers: Content-Type + em_base_info.
- Wrap httpx.AsyncClient with configurable timeout, retries, and error classification.
- Never leak the API key in exception messages.
"""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

# No fallback key in source.  Prefer the EM_API_KEY environment variable.
_FALLBACK_API_KEY = None

_API_KEY_PLACEHOLDER = "<EM_API_KEY_PLACEHOLDER>"

DEFAULT_TIMEOUT = 120.0
MAX_RETRIES = 3
RETRY_DELAY = 1.0


class ApiCallError(Exception):
    """Structured API call error that does not include the API key."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def get_api_key() -> str:
    """Return the configured EM API key from environment, or a placeholder."""
    key = (os.environ.get("EM_API_KEY") or "").strip()
    if not key:
        return _API_KEY_PLACEHOLDER
    return key


def require_api_key() -> str:
    """Return the API key if configured; raise ApiCallError otherwise."""
    key = get_api_key()
    if key == _API_KEY_PLACEHOLDER:
        raise ApiCallError("MISSING_CREDENTIAL", "请先设置 EM_API_KEY 环境变量。")
    return key


def base_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Standard headers used by most Eastmoney MCP endpoints."""
    headers = {
        "Content-Type": "application/json",
        "em_base_info": json.dumps({"productType": "mx"}, ensure_ascii=False, separators=(",", ":")),
        "em_api_key": require_api_key(),
    }
    if extra:
        headers.update(extra)
    return headers


def _safe_body_preview(body: Any) -> str:
    """Serialize a request/response body for logging, scrubbing the API key."""
    try:
        text = json.dumps(body, ensure_ascii=False)
    except Exception:
        text = str(body)
    key = get_api_key()
    if key and key != _API_KEY_PLACEHOLDER:
        text = text.replace(key, "***")
    if len(text) > 500:
        text = text[:500] + "..."
    return text


def _is_retryable(exc: Exception) -> bool:
    """Determine whether an exception is worth retrying."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (408, 429, 500, 502, 503, 504)
    return False


@dataclass
class ApiResponse:
    """Normalized wrapper around an API response."""

    status_code: int
    headers: httpx.Headers
    json_data: Dict[str, Any]
    text: str


async def request(
    method: str,
    url: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY,
) -> ApiResponse:
    """
    Make an async HTTP request with retries and structured error handling.

    Raises:
        ApiCallError: Classified error without exposing the API key.
    """
    timeout = timeout or DEFAULT_TIMEOUT
    request_headers = base_headers(headers)
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    json=json_body,
                )
                resp.raise_for_status()
                text = resp.text
                try:
                    data = resp.json() if text else {}
                except Exception as exc:
                    raise ApiCallError(
                        "INVALID_JSON",
                        f"无法解析响应 JSON: {exc}",
                    ) from exc
                if not isinstance(data, dict):
                    data = {"data": data}
                return ApiResponse(
                    status_code=resp.status_code,
                    headers=resp.headers,
                    json_data=data,
                    text=text,
                )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt < retries and _is_retryable(exc):
                await asyncio.sleep(retry_delay * (2 ** attempt))
                continue
            raise ApiCallError(
                "NETWORK_ERROR" if isinstance(exc, httpx.NetworkError) else "TIMEOUT",
                "网络请求失败或超时，请稍后重试。",
            ) from exc
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if attempt < retries and _is_retryable(exc):
                await asyncio.sleep(retry_delay * (2 ** attempt))
                continue
            snippet = (exc.response.text or "")[:500]
            raise ApiCallError(
                "HTTP_ERROR",
                f"HTTP {exc.response.status_code}: {snippet}",
            ) from exc

    # Defensive fallback; should normally be unreachable.
    raise ApiCallError(
        "UNEXPECTED_ERROR",
        f"请求最终失败: {last_exc}",
    )


async def post(
    url: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY,
) -> ApiResponse:
    """Convenience wrapper for POST requests."""
    return await request(
        "POST",
        url,
        json_body=json_body,
        headers=headers,
        timeout=timeout,
        retries=retries,
        retry_delay=retry_delay,
    )
