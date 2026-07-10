import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runner import parse_input_markdown, format_output


def test_parse_input_markdown():
    text = """## 公司信息
- 公司：中际旭创
- 代码：300308.SZ
- 市值：13,900 亿元
- 总股本：11.15 亿股
- 当前股价：1,247 元
- E0：107.97
- E1：299.76
- E2：520.88
- E3：766.80
"""
    inputs = parse_input_markdown(text)
    assert inputs["company"] == "中际旭创"
    assert inputs["code"] == "300308.SZ"
    assert inputs["market_cap"] == 13900.0
    assert inputs["e1"] == 299.76
