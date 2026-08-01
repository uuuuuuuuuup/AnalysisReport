"""
Output helpers: default directories, filename generation, and structured file writes.
"""

import csv
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def default_output_dir(skill_slug: str) -> Path:
    """
    Return the default output directory for a skill slug.

    Priority: {SKILL_SLUG}_OUTPUT_DIR environment variable > cwd/miaoxiang/{skill_slug}/.
    """
    env_key = f"{skill_slug.upper().replace('-', '_')}_OUTPUT_DIR"
    env = os.environ.get(env_key, "").strip()
    if env:
        return Path(env)
    return Path.cwd() / "miaoxiang" / skill_slug


def ensure_output_dir(skill_slug: str, output_dir: Optional[str] = None) -> Path:
    """Ensure the output directory exists and return its Path."""
    out = Path(output_dir) if output_dir else default_output_dir(skill_slug)
    out.mkdir(parents=True, exist_ok=True)
    return out


def unique_suffix(length: int = 8) -> str:
    return uuid.uuid4().hex[:length]


def safe_sheet_name(raw_name: Any, used_names: set) -> str:
    """Generate a legal, unique Excel sheet name."""
    name = _flatten_value(raw_name).strip() or "表"
    name = re.sub(r"[:\\/?*\[\]]", "_", name)
    if len(name) > 31:
        name = name[:31]
    base = name or "表"
    candidate = base
    idx = 2
    while candidate in used_names:
        suffix = f"_{idx}"
        if len(base) + len(suffix) > 31:
            candidate = base[: 31 - len(suffix)] + suffix
        else:
            candidate = base + suffix
        idx += 1
    used_names.add(candidate)
    return candidate


def _flatten_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def write_markdown_table(rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    """Convert rows into a Markdown table string."""
    if not fieldnames:
        return ""

    def escape_cell(value: Any) -> str:
        text = _flatten_value(value)
        return text.replace("|", "\\|").replace("\n", " ").strip()

    header = "| " + " | ".join(escape_cell(h) for h in fieldnames) + " |"
    separator = "| " + " | ".join("---" for _ in fieldnames) + " |"
    body_lines = [
        "| " + " | ".join(escape_cell(row.get(col, "")) for col in fieldnames) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body_lines])


def write_excel(
    tables: List[Dict[str, Any]],
    output_path: Path,
) -> Path:
    """
    Write a list of tables to an Excel workbook with one sheet per table.

    Each table is {"sheet_name": str, "rows": [dict, ...], "fieldnames": [str, ...]}.
    """
    used_names: set = set()
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for table in tables:
            sheet_name = safe_sheet_name(table.get("sheet_name"), used_names)
            df = pd.DataFrame(table["rows"], columns=table["fieldnames"])
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output_path


def write_csv(
    rows: List[Dict[str, Any]],
    output_path: Path,
    fieldnames: Optional[List[str]] = None,
) -> Path:
    """Write rows to a CSV file. If fieldnames is None, derive from the rows."""
    if not rows:
        output_path.write_text("", encoding="utf-8-sig")
        return output_path
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _flatten_value(v) for k, v in row.items()})
    return output_path


def write_markdown(
    tables: List[Dict[str, Any]],
    output_path: Path,
) -> Path:
    """Write multiple tables to a Markdown file, one section per table."""
    sections: List[str] = []
    for table in tables:
        sheet_name = _flatten_value(table.get("sheet_name") or "数据").strip()
        md_table = write_markdown_table(table["rows"], table["fieldnames"])
        if md_table:
            sections.append(f"## {sheet_name}\n\n{md_table}")
    output_path.write_text("\n\n".join(sections), encoding="utf-8")
    return output_path


def write_text_file(text: str, output_path: Path) -> Path:
    """Write plain text to a file."""
    output_path.write_text(text, encoding="utf-8")
    return output_path


def write_json(data: Any, output_path: Path) -> Path:
    """Write JSON data to a file."""
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


__all__ = [
    "default_output_dir",
    "ensure_output_dir",
    "unique_suffix",
    "safe_sheet_name",
    "write_markdown_table",
    "write_excel",
    "write_csv",
    "write_markdown",
    "write_text_file",
    "write_json",
]
