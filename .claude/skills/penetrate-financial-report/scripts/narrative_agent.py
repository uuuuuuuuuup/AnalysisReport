# .claude/skills/penetrate-financial-report/scripts/narrative_agent.py
"""Call Narrative Agent and parse structured markdown response."""
import subprocess
import tempfile
import os
import re
from typing import Dict, Any


def build_narrative_input(company: str, code: str, market_cap: float,
                          total_shares: float, price: float,
                          e0: float, e1: float, e2: float, e3: float,
                          industry: str = "") -> str:
    """Build the structured markdown input for the Narrative Agent."""
    return f"""## 任务
为 financial 财报分析提供 narrative DCF 与叙事结论。

## 公司信息
- 公司：{company}
- 代码：{code}
- 市值：{market_cap:,.2f} 亿元
- 总股本：{total_shares:,.2f} 亿股
- 当前股价：{price:,.2f} 元
- E0：{e0:,.2f}
- E1：{e1:,.2f}
- E2：{e2:,.2f}
- E3：{e3:,.2f}
- 行业：{industry}

## 模式
- mode: `financial-support`
- 说明：不重新获取数据，不生成完整报告，只返回 DCF 结果和关键叙事结论。
"""


def parse_narrative_output(text: str) -> Dict[str, Any]:
    """Parse structured markdown output from Narrative Agent."""
    result = {"dcf": {}, "narrative_class": "", "stage": "", "scenario_probability": {}}
    # Parse DCF table
    dcf_table = re.search(r"## DCF 反算结果\n\s*\|(.+?)\n\n", text, re.S)
    if dcf_table:
        lines = dcf_table.group(1).strip().splitlines()
        for line in lines[2:]:
            cells = [c.strip() for c in line.split("|")][1:-1]
            if len(cells) >= 5:
                r = cells[0].replace("%", "")
                try:
                    l_e0 = float(cells[3].replace("x", "")) if cells[3] not in ("—", "N/A", "") else None
                except ValueError:
                    l_e0 = None
                result["dcf"][f"r_{r}"] = {
                    "L": float(cells[1].replace(",", "")),
                    "L/E3": float(cells[2].replace("x", "")),
                    "L/E0": l_e0,
                    "g": float(cells[4].replace("%", ""))
                }
    # Parse narrative class
    m = re.search(r"- 分级：(.+)", text)
    if m:
        result["narrative_class"] = m.group(1).strip()
    return result


def call_narrative_agent(markdown_input: str, narrative_skill_dir: str = None) -> Dict[str, Any]:
    """Call the Narrative Agent via subprocess."""
    if narrative_skill_dir is None:
        narrative_skill_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "penetrate-narrative-stock-analysis"
        )
    agent_script = os.path.join(narrative_skill_dir, "scripts/agent_runner.py")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(markdown_input)
        input_path = f.name
    try:
        result = subprocess.run(
            ["python3", agent_script, "--input-file", input_path],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(f"Narrative agent failed: {result.stderr}")
        return parse_narrative_output(result.stdout)
    finally:
        os.unlink(input_path)
