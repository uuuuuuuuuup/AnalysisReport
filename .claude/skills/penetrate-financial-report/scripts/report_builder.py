# .claude/skills/penetrate-financial-report/scripts/report_builder.py
"""Build financial report markdown."""
import os
from typing import Dict, Any


def heading(level: int, text: str) -> str:
    return "#" * level + " " + text + "\n\n"


def paragraph(text: str) -> str:
    return text + "\n\n"


def table(headers: list, rows: list) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines) + "\n\n"


def build_financial_report(company: str, code: str, narrative: Dict[str, Any],
                           financials: Dict[str, Any], output_dir: str) -> str:
    """Generate financial markdown report."""
    os.makedirs(output_dir, exist_ok=True)
    md = ""
    md += heading(1, f"{company} 穿透财报分析报告")
    md += heading(2, "封面信息")
    md += paragraph(f"- 公司：{company}（{code}）")
    md += paragraph(f"- 分析日期：{__import__('datetime').date.today()}")
    md += paragraph(f"- 分析框架：穿透叙事 + 三张表完整科目深度分析 v4.0")

    md += heading(2, "第一部分　叙事先行——反算股价隐含预期")
    md += heading(3, "1.2 DCF 反算隐含终局利润L")
    rows = []
    for r_key, s in narrative.get("dcf", {}).items():
        r = r_key.replace("r_", "") + "%"
        rows.append([r, f"{s['L']:,.1f}",
                     f"{s['L/E3']:.2f}x" if s.get("L/E3") is not None else "—",
                     f"{s['L/E0']:.2f}x" if s.get("L/E0") is not None else "—",
                     f"{s['g']:.1f}%"])
    md += table(["折现率 r", "隐含 L(亿元)", "L/E3", "L/E0", "隐含增速 g"], rows)
    md += paragraph(f"叙事分级：{narrative.get('narrative_class', '待判断')}")

    md += heading(2, "第二部分　资产负债表深度分析")
    md += paragraph("（待结合完整三张表数据填充）")

    md += heading(2, "第四部分　综合结论")
    md += heading(3, "4.2 财务质量五维评估")
    quality = financials.get("quality", {})
    rows = [[k, v] for k, v in quality.items()]
    md += table(["评估维度", "评级"], rows)

    md += heading(2, "附录")
    md += paragraph("【免责声明】本报告基于公开信息分析推演，不构成投资建议。")

    output_path = os.path.join(output_dir, f"{company}_穿透财报分析报告.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    return output_path
