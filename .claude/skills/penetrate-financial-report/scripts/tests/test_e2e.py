import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from narrative_agent import build_narrative_input, parse_narrative_output
from financial_analyzer import compute_financial_quality
from report_builder import build_financial_report
import tempfile


def test_financial_e2e():
    narrative_md = build_narrative_input("测试", "000001.SZ", 1000, 100, 10, 50, 60, 70, 80)
    assert "financial-support" in narrative_md
    # Simulate parsed narrative
    narrative = parse_narrative_output("""## DCF 反算结果
| 折现率 r | 隐含 L(亿元) | L/E3 | L/E0 | 隐含增速 g |
|---------|-------------|------|------|-----------|
| 10% | 100.0 | 1.25x | 2.00x | 5.0% |

## 叙事判断
- 分级：温和增长叙事
- 阶段：展望期
""")
    financials = {"quality": compute_financial_quality({})}
    with tempfile.TemporaryDirectory() as tmpdir:
        path = build_financial_report("测试", "000001.SZ", narrative, financials, tmpdir)
        assert os.path.exists(path)
