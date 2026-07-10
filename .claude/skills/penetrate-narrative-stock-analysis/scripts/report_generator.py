# .claude/skills/penetrate-narrative-stock-analysis/scripts/report_generator.py
"""Generate Markdown narrative report."""
import os
from typing import Dict, Any
from markdown_writer import heading, paragraph, table, quote_box, image
from chart_generator import save_dcf_sensitivity_chart


def generate_narrative_markdown(result: Dict[str, Any], output_dir: str) -> str:
    """Generate narrative Markdown report and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    company = result["company"]
    code = result["code"]

    # Generate charts
    dcf = result["dcf"]
    ratios = [0.3, 0.5, 1.0, 1.5, 2.0, 2.48, 3.0, 5.0, 10.0]
    from dcf_implied import fair_value
    caps = [fair_value(r * result["e3"], result["e1"], result["e2"], result["e3"], 10,
                       dcf["growth_years"]) for r in ratios]
    chart_path = os.path.join(output_dir, f"{code.replace('.', '_')}_dcf_sensitivity.png")
    save_dcf_sensitivity_chart(ratios, caps, result["market_cap"], chart_path)

    md = ""
    md += heading(1, f"{company} 穿透叙事投资分析报告")
    md += heading(2, "摘要")
    md += paragraph(f"本报告基于 DCF 第一性原理，对 {company}（{code}）的股价隐含叙事进行分析。")

    md += heading(2, "一、核心结论")
    md += paragraph(
        f"当前市值 {result['market_cap']:,.0f} 亿元，"
        f"r=10% 隐含终局利润 L = {dcf['scenarios']['r_10']['L']:,.1f} 亿元，"
        f"叙事分级：{result['narrative_class']}。"
    )

    md += heading(2, "二、DCF 反算结果")
    rows = []
    for r_key, s in dcf["scenarios"].items():
        r = r_key.replace("r_", "") + "%"
        rows.append([r, f"{s['L']:,.1f}",
                     f"{s['L/E3']:.2f}x" if s["L/E3"] is not None else "—",
                     f"{s['L/E0']:.2f}x" if s["L/E0"] is not None else "—",
                     f"{s['g']:.1f}%",
                     f"{s['pe1']:.1f}x" if s["pe1"] is not None else "—"])
    md += table(["折现率 r", "隐含 L(亿元)", "L/E3", "L/E0", "隐含增速 g", "动态 PE(E1)"], rows)
    md += image("DCF 敏感性分析", os.path.basename(chart_path))

    md += heading(2, "三、投资结论")
    md += paragraph("待后续补充完整阶段判断、叙事概率、护城河分析。")

    md += heading(2, "九、附录")
    md += paragraph("数据来源：公司年报/季报、公开研报、行业研究报告。")
    md += paragraph("【免责声明】本报告基于公开信息分析推演，不构成投资建议。")

    output_path = os.path.join(output_dir, f"{company}_穿透叙事分析报告.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    return output_path
