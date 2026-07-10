# .claude/skills/penetrate-financial-report/scripts/financial_analyzer.py
"""Analyze balance sheet, income statement, and cash flow statement."""
from typing import Dict, Any, List


def analyze_balance_sheet(bs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze balance sheet and return key findings."""
    return {
        "current_assets": bs_data.get("流动资产", []),
        "non_current_assets": bs_data.get("非流动资产", []),
        "current_liabilities": bs_data.get("流动负债", []),
        "non_current_liabilities": bs_data.get("非流动负债", []),
        "equity": bs_data.get("所有者权益", []),
    }


def analyze_income_statement(is_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze income statement and return key findings."""
    return {
        "revenue": is_data.get("营业收入", 0),
        "gross_profit": is_data.get("毛利润", 0),
        "net_profit": is_data.get("归母净利润", 0),
    }


def analyze_cash_flow(cf_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze cash flow statement."""
    return {
        "operating_cf": cf_data.get("经营活动现金流量净额", 0),
        "investing_cf": cf_data.get("投资活动现金流量净额", 0),
        "financing_cf": cf_data.get("筹资活动现金流量净额", 0),
    }


def compute_financial_quality(financials: Dict[str, Any]) -> Dict[str, str]:
    """Compute five-dimension financial quality assessment."""
    return {
        "盈利质量": "待评估",
        "资产质量": "待评估",
        "现金流质量": "待评估",
        "产业链地位": "待评估",
        "再投资效率": "待评估",
    }
