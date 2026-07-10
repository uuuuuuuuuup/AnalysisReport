import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from financial_analyzer import analyze_balance_sheet, compute_financial_quality


def test_analyze_balance_sheet():
    bs = {"流动资产": [{"货币资金": 100}], "非流动资产": []}
    result = analyze_balance_sheet(bs)
    assert result["current_assets"][0]["货币资金"] == 100


def test_compute_financial_quality():
    result = compute_financial_quality({})
    assert result["盈利质量"] == "待评估"
