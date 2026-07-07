# .claude/skills/penetrate-narrative-stock-analysis/scripts/validators.py
"""Data validation utilities for narrative skill."""
from typing import Dict, Any


def validate_market_cap(price: float, shares: float, market_cap: float, tol: float = 0.05) -> bool:
    """Check market_cap = price * shares within tolerance."""
    if price <= 0 or shares <= 0:
        return False
    expected = price * shares
    return abs(expected - market_cap) / market_cap <= tol if market_cap > 0 else False


def validate_dcf_forward_backward(cap: float, e1: float, e2: float, e3: float,
                                   L: float, r: float, growth_years: int, tol: float = 0.05) -> bool:
    """Validate L can be forward-calculated back to cap."""
    from dcf_implied import fair_value
    fv = fair_value(L, e1, e2, e3, r, growth_years)
    return abs(fv - cap) / cap <= tol if cap > 0 else False


def format_yuan_yi(value: float | None) -> str:
    """Format a number as 亿元 string."""
    if value is None:
        return "—"
    return f"{value:,.2f}"
