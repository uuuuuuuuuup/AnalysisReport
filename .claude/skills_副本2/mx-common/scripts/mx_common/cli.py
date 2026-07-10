"""
Common CLI helpers for mx-* skills.

- Read --query from arguments or stdin.
- Default output directory override via environment variables.
- Reconfigure stdout/stderr to UTF-8 when available.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


def reconfigure_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 if the method is available."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def read_query_from_stdin() -> str:
    """Read query from stdin, supporting both plain text and JSON payloads."""
    raw = sys.stdin.read().strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return _safe_str(payload.get("query") or payload.get("question") or "")
        if isinstance(payload, str):
            return payload.strip()
    except Exception:
        return raw
    return ""


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def parse_query(args: argparse.Namespace) -> str:
    """Return a non-empty query string from args or stdin."""
    query = _safe_str(getattr(args, "query", None))
    if not query:
        query = read_query_from_stdin()
    return query


def output_dir_env(skill_slug: str) -> Optional[str]:
    """Return an environment-variable override for the output directory, if set."""
    env_key = f"{skill_slug.upper().replace('-', '_')}_OUTPUT_DIR"
    return os.environ.get(env_key, "").strip() or None


__all__ = [
    "reconfigure_stdio",
    "read_query_from_stdin",
    "parse_query",
    "output_dir_env",
]
