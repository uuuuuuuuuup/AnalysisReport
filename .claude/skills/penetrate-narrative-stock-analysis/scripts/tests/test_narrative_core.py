import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from narrative_core import run_narrative_analysis, classify_narrative


def test_classify_narrative():
    assert classify_narrative(0.3) == "深度下滑叙事"
    assert classify_narrative(1.5) == "温和增长叙事"
    assert classify_narrative(12) == "极高增长叙事（透支风险大）"


def test_financial_support_mode():
    inputs = {
        "company": "中际旭创", "code": "300308.SZ",
        "market_cap": 13900, "total_shares": 11.15, "price": 1247,
        "e0": 107.97, "e1": 299.76, "e2": 520.88, "e3": 766.80,
    }
    result = run_narrative_analysis(inputs, mode="financial-support")
    assert result["mode"] == "financial-support"
    assert "dcf" in result
    assert "r_10" in result["dcf"]["scenarios"]