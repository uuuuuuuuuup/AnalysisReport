"""
mx-search: Search financial news and reports.

Calls the Eastmoney searchNews endpoint and returns text content.
"""

import argparse
import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

# Add mx-common package to path.
_COMMON = Path(__file__).resolve().parents[2] / "mx-common" / "scripts"
if str(_COMMON) not in sys.path:
    sys.path.insert(0, str(_COMMON))

from mx_common.api_client import ApiCallError, post
from mx_common.cli import parse_query, reconfigure_stdio
from mx_common.content import check_business_status, extract_text
from mx_common.endpoints import search_endpoint
from mx_common.output import default_output_dir, ensure_output_dir, unique_suffix, write_text_file


GENERAL_ERROR_MSG = "资讯搜索服务暂时不可用，请稍后重试。"


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _build_tool_context() -> Dict[str, Any]:
    import uuid

    return {"callId": f"call_{uuid.uuid4().hex[:8]}"}


async def search_news(query: str, output_dir: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "query": query,
        "content": "",
        "output_path": None,
    }

    body = {"query": query, "toolContext": _build_tool_context()}
    resp = await post(search_endpoint(), json_body=body, timeout=30.0)
    payload = resp.json_data

    status_err = check_business_status(payload)
    if status_err:
        result["error_code"] = "API_ERROR"
        result["message"] = status_err
        return result

    content = extract_text(payload)
    if not content:
        result["error_code"] = "EMPTY_RESPONSE"
        result["message"] = "未获取到有效资讯内容。"
        return result

    out = ensure_output_dir("mx-search", output_dir)
    suffix = unique_suffix()
    output_path = out / f"mx_search_{suffix}.txt"
    write_text_file(content, output_path)

    result.update({
        "ok": True,
        "content": content,
        "output_path": str(output_path),
    })
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="金融资讯搜索")
    parser.add_argument("--query", type=str, default="", help="搜索关键词")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="输出目录（默认 miaoxiang/mx-search）",
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
            result = await search_news(query=query, output_dir=args.output_dir)
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
