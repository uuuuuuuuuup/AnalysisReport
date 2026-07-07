# .claude/skills/penetrate-narrative-stock-analysis/scripts/markdown_writer.py
"""Markdown report writing helpers."""
from typing import List, Any


def heading(level: int, text: str) -> str:
    return "#" * level + " " + text + "\n\n"


def paragraph(text: str) -> str:
    return text + "\n\n"


def quote_box(text: str) -> str:
    return "> " + text.replace("\n", "\n> ") + "\n\n"


def table(headers: List[str], rows: List[List[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines) + "\n\n"


def image(title: str, path: str) -> str:
    return f"![{title}]({path})\n\n"
