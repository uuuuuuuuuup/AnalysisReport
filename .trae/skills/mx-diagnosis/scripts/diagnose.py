"""
mx-diagnosis: Stock, fund, and market hotspot diagnosis.

Calls the Eastmoney analysis endpoints and returns Markdown content as JSON.
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
from mx_common.endpoints import diagnosis_endpoint
from mx_common.output import default_output_dir, ensure_output_dir, unique_suffix, write_text_file


GENERAL_ERROR_MSG = "诊断服务暂时不可用，请稍后重试。"


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


async def diagnose(question: str, asset_type: str, output_dir: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "asset_type": asset_type,
        "question": question,
        "content": "",
        "output_path": None,
    }

    url = diagnosis_endpoint(asset_type)
    resp = await post(url, json_body={"question": question}, timeout=120.0)
    payload = resp.json_data

    status_err = check_business_status(payload)
    if status_err:
        result["error_code"] = "API_ERROR"
        result["message"] = status_err
        return result

    content = extract_text(payload)
    if not content:
        result["error_code"] = "EMPTY_RESPONSE"
        result["message"] = "未获取到有效诊断内容，请稍后重试。"
        return result

    out = ensure_output_dir("mx-diagnosis", output_dir)
    suffix = unique_suffix()
    output_path = out / f"mx_diagnosis_{asset_type}_{suffix}.md"
    write_text_file(content, output_path)

    result.update({
        "ok": True,
        "content": content,
        "output_path": str(output_path),
    })
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="股票/基金/市场热点诊断")
    parser.add_argument("--query", type=str, default="", help="自然语言诊断问句")
    parser.add_argument(
        "--asset-type",
        type=str,
        required=True,
        choices=["stock", "fund", "hotspot"],
        help="诊断对象类型",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="输出目录（默认 miaoxiang/mx-diagnosis）",
    )
    return parser.parse_args()


def main() -> None:
    reconfigure_stdio()
    args = parse_args()
    question = parse_query(args)

    if not question:
        print(
            json.dumps(
                {"ok": False, "error_code": "BAD_REQUEST", "message": "缺少 query 参数"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    async def _main() -> None:
        try:
            result = await diagnose(
                question=question,
                asset_type=args.asset_type,
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
