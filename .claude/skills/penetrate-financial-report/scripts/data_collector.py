# .claude/skills/penetrate-financial-report/scripts/data_collector.py
"""Collect all required inputs for financial report."""
from typing import Dict, Any
import os
import importlib.util

# Load narrative skill market data sources without colliding with local data_sources module.
_narrative_script = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "penetrate-narrative-stock-analysis",
    "scripts",
    "data_sources.py"
)
_narrative_spec = importlib.util.spec_from_file_location("narrative_data_sources", _narrative_script)
_narrative_data_sources = importlib.util.module_from_spec(_narrative_spec)
_narrative_spec.loader.exec_module(_narrative_data_sources)
get_market_data_mx = _narrative_data_sources.get_market_data_mx
get_market_data_lingxi = _narrative_data_sources.get_market_data_lingxi
get_consensus_earnings = _narrative_data_sources.get_consensus_earnings

# Local financial statement data sources
from data_sources import get_balance_sheet, get_income_statement, get_cash_flow_statement


def collect_financial_inputs(company_name: str, code: str) -> Dict[str, Any]:
    """Collect market data, earnings, and financial statements."""
    data = get_market_data_mx(company_name) or get_market_data_lingxi(company_name)
    if not data:
        raise RuntimeError(f"无法获取 {company_name} 的市场数据。")

    earnings = get_consensus_earnings(company_name) or {}

    inputs = {
        "company": company_name,
        "code": code,
        "market_cap": data["market_cap"],
        "price": data["price"],
        "total_shares": data.get("total_shares", data["market_cap"] / data["price"]),
        "e0": earnings.get("e0", 0),
        "e1": earnings.get("e1", 0),
        "e2": earnings.get("e2", 0),
        "e3": earnings.get("e3", 0),
        "balance_sheet": get_balance_sheet(code) or {},
        "income_statement": get_income_statement(code) or {},
        "cash_flow": get_cash_flow_statement(code) or {},
    }
    return inputs
