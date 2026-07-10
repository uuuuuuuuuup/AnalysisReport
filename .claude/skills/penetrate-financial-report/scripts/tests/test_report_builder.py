import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from report_builder import build_financial_report
import tempfile


def test_build_financial_report():
    narrative = {
        "dcf": {
            "r_10": {"L": 1900, "L/E3": 2.48, "L/E0": 17.6, "g": 19.9}
        },
        "narrative_class": "极高增长"
    }
    financials = {
        "quality": {"盈利质量": "中等", "资产质量": "良好"}
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = build_financial_report("测试公司", "000001.SZ", narrative, financials, tmpdir)
        assert os.path.exists(path)
