"""
mx-assistant: Financial Q&A skill.

Calls the Eastmoney assistant/ask endpoint and prints a JSON result.
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
from mx_common.content import check_business_status, extract_references, extract_text
from mx_common.endpoints import get_endpoint


TOOL_NAME = "金融问答"
GENERAL_ERROR_MSG = "金融问答服务暂时不可用，请稍后重试。"


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


async def _call_assistant(question: str, deep_think: bool = False) -> Dict[str, Any]:
    body = {"question": question}
    if deep_think:
        body["deepThink"] = True

    resp = await post(
        get_endpoint("assistant"),
        json_body=body,
        timeout=600.0,
    )
    return resp.json_data


def build_output(
    question: str,
    deep_think: bool,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    status_err = check_business_status(payload)
    if status_err:
        return {
            "ok": False,
            "error_code": "API_ERROR",
            "message": _safe_str(payload.get("message")) or status_err,
        }

    answer = extract_text(payload)
    if not answer:
        return {
            "ok": False,
            "error_code": "EMPTY_RESPONSE",
            "message": "未获取到有效回答，请稍后重试。",
        }

    return {
        "ok": True,
        "tool": TOOL_NAME,
        "question": question,
        "deep_think": deep_think,
        "answer": answer,
        "references": extract_references(payload),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="金融问答")
    parser.add_argument("--query", type=str, default="", help="用户问题文本")
    parser.add_argument("--deep-think", action="store_true", default=False, help="开启深度思考模式")
    return parser.parse_args()


def main() -> None:
    reconfigure_stdio()
    args = parse_args()
    question = parse_query(args)

    if not question:
        print(
            json.dumps(
                {"ok": False, "error_code": "BAD_REQUEST", "message": "请输入您想问的问题。"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    async def _main() -> None:
        try:
            payload = await _call_assistant(question=question, deep_think=args.deep_think)
            output = build_output(question=question, deep_think=args.deep_think, payload=payload)
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(0 if output.get("ok") else 2)
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
