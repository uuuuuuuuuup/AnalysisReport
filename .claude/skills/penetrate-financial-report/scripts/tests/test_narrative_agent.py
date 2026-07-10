import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from narrative_agent import build_narrative_input, parse_narrative_output


def test_build_narrative_input():
    text = build_narrative_input("中际旭创", "300308.SZ", 13900, 11.15, 1247,
                                  107.97, 299.76, 520.88, 766.80)
    assert "financial-support" in text
    assert "299.76" in text


def test_parse_narrative_output():
    output = """## DCF 反算结果
| 折现率 r | 隐含 L(亿元) | L/E3 | L/E0 | 隐含增速 g |
|---------|-------------|------|------|-----------|
| 10% | 1,900.0 | 2.48x | 17.60x | 19.9% |

## 叙事判断
- 分级：极高增长（透支风险大）
- 阶段：流动性冲击期末段→回调期
"""
    result = parse_narrative_output(output)
    assert result["dcf"]["r_10"]["L"] == 1900.0
    assert "透支" in result["narrative_class"]
