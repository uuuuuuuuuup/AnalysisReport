import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from narrative_core import run_narrative_analysis
from report_generator import generate_narrative_markdown
import tempfile


def test_narrative_e2e():
    inputs = {
        "company": "测试公司", "code": "000001.SZ",
        "market_cap": 1000, "price": 10, "total_shares": 100,
        "e0": 50, "e1": 60, "e2": 70, "e3": 80
    }
    result = run_narrative_analysis(inputs, mode="standalone")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = generate_narrative_markdown(result, tmpdir)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "核心结论" in content
        assert "免责声明" in content
