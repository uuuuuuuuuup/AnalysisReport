"""
Decode and save base64-encoded attachments (PDF, DOCX, Excel, etc.).
"""

import base64
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_filename(name: str, fallback: str) -> str:
    """Turn an untrusted string into a safe filename."""
    base = Path(str(name or "")).name.strip() or fallback
    invalid = '<>:"/\\|?*'
    out = "".join("_" if ch in invalid else ch for ch in base).strip(" .")
    return out or fallback


def _pick_base64(data: Dict[str, Any]) -> Optional[str]:
    """Pick the first non-empty base64 string from common payload shapes."""
    if not isinstance(data, dict):
        return None
    for key in (
        "base64",
        "dataSheetBase64",
        "excelBase64",
        "dataBase64",
        "sheetBase64",
        "dataBase64Str",
        "attachDataBase64",
        "pdfBase64",
        "wordBase64",
    ):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def save_attachment(
    payload: Any,
    output_dir: str,
    default_name: str,
) -> Optional[str]:
    """
    Save an attachment payload to a local path.

    Supported inputs:
    - {"base64": "...", "filename": "..."}
    - {"bytes": [1,2,3], "filename": "..."}
    - {"binary": [1,2,3], "filename": "..."}
    - A plain base64 string.

    Returns the saved path or None.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if isinstance(payload, str) and payload.strip():
        b64 = payload.strip()
    else:
        if not isinstance(payload, dict):
            return None
        b64 = _pick_base64(payload)
        if b64 is None:
            for key in ("bytes", "binary"):
                arr = payload.get(key)
                if isinstance(arr, list):
                    name = str(payload.get("filename") or default_name)
                    path = out / _safe_filename(name, default_name)
                    try:
                        path.write_bytes(bytes(int(x) & 0xFF for x in arr))
                        return str(path)
                    except Exception:
                        return None
            return None

    name = payload.get("filename") if isinstance(payload, dict) else default_name
    name = str(name or default_name)
    path = out / _safe_filename(name, default_name)
    try:
        raw = base64.b64decode(b64)
        path.write_bytes(raw)
        return str(path)
    except Exception:
        return None


def decode_attachments(
    data: Dict[str, Any],
    output_dir: str,
    *,
    article_id: Optional[str] = None,
    file_map: Optional[List[tuple]] = None,
) -> List[Dict[str, str]]:
    """
    Decode standard PDF/DOCX/Excel base64 attachments from a data dict.

    file_map is a list of (field, extension, type_label).
    Default: pdfBase64, wordBase64.
    """
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    if file_map is None:
        file_map = [
            ("pdfBase64", "pdf", "PDF"),
            ("wordBase64", "docx", "DOCX"),
        ]

    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", article_id or uuid.uuid4().hex)
    attachments: List[Dict[str, str]] = []

    for key, ext, label in file_map:
        value = data.get(key)
        b64_str = value.strip() if isinstance(value, str) else ""
        if not b64_str:
            continue
        try:
            raw = base64.b64decode(b64_str)
        except Exception:
            continue
        file_name = f"{safe_id}_{label.lower()}.{ext}"
        file_path = output_dir_path / file_name
        file_path.write_bytes(raw)
        attachments.append({"type": label, "path": str(file_path)})

    return attachments


def attachment_local_status(saved_path: Optional[str]) -> Dict[str, Any]:
    """Return whether an attachment was saved locally and its size."""
    if not saved_path:
        return {"path": None, "saved": False, "sizeBytes": None}
    p = Path(saved_path)
    try:
        if p.is_file():
            return {"path": str(p.resolve()), "saved": True, "sizeBytes": p.stat().st_size}
    except OSError:
        pass
    return {"path": str(p), "saved": False, "sizeBytes": None}


def build_attachment_report(
    attachment_candidates: Dict[str, Any],
    saved_attachments: Dict[str, str],
) -> Dict[str, Any]:
    """Summarize which attachments had base64 and which were saved."""
    report: Dict[str, Any] = {}
    for name, payload in attachment_candidates.items():
        has_b64 = False
        if isinstance(payload, dict) and isinstance(payload.get("base64"), str):
            has_b64 = bool(payload["base64"].strip())
        st = attachment_local_status(saved_attachments.get(name))
        report[name] = {**st, "hadBase64InResponse": has_b64}
    return report
