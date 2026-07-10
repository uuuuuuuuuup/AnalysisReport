# .claude/skills/penetrate-financial-report/scripts/validators.py
"""Validation utilities for financial report skill."""


def format_yi(value):
    """Convert raw number to 亿元 string."""
    if value is None:
        return "—"
    return f"{value:,.2f}"


def highlight_if_large(value: float, threshold: float = 0.2) -> str:
    """Return a markdown string with emphasis if change > threshold."""
    if abs(value) > threshold:
        return f"**{value:+.1%}**"
    return f"{value:+.1%}"
