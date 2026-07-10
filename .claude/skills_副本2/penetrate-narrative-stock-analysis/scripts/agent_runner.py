#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point when called by Financial skill Agent.

Reads structured markdown input from stdin or file, runs narrative core in
financial-support mode, prints structured markdown output to stdout.
"""
import argparse
import sys
import re
from narrative_core import run_narrative_analysis
from markdown_writer import heading, paragraph, table


def parse_input_markdown(text: str) -> dict:
    """Parse structured markdown input from Financial skill."""
    inputs = {}
    for line in text.splitlines():
        m = re.match(r"^-\s*(\w+)\s*[：:]\s*(.+)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if key in ["市值", "总股本", "当前股价", "E0", "E1", "E2", "E3"]:
                value = value.replace(",", "").replace("亿元", "").replace("亿股", "").replace("元", "")
                try:
                    value = float(value)
                except ValueError:
                    pass
            inputs[key] = value
    mapping = {
        "公司": "company", "代码": "code", "基准日": "base_date",
        "市值": "market_cap", "总股本": "total_shares", "当前股价": "price",
        "E0": "e0", "E1": "e1", "E2": "e2", "E3": "e3"
    }
    return {mapping.get(k, k): v for k, v in inputs.items() if k in mapping}


def format_output(result: dict) -> str:
    """Format narrative result as structured markdown for Financial skill."""
    dcf = result["dcf"]
    md = ""
    md += heading(2, "DCF 反算结果")
    rows = []
    for r_key, s in dcf["scenarios"].items():
        r = r_key.replace("r_", "") + "%"
        rows.append([r, f"{s['L']:,.1f}", f"{s['L/E3']:.2f}x",
                     f"{s['L/E0']:.2f}x", f"{s['g']:.1f}%"])
    md += table(["折现率 r", "隐含 L(亿元)", "L/E3", "L/E0", "隐含增速 g"], rows)
    md += heading(2, "叙事判断")
    md += paragraph(f"- 分级：{result['narrative_class']}")
    md += paragraph(f"- 阶段：{result['stage']}")
    prob = result.get("scenario_probability", {})
    md += paragraph(
        f"- 上修概率：{prob.get('up', 0)*100:.0f}% | "
        f"维持：{prob.get('maintain', 0)*100:.0f}% | "
        f"下修：{prob.get('down', 0)*100:.0f}% | "
        f"深度下修：{prob.get('deep_down', 0)*100:.0f}%"
    )
    md += heading(2, "护城河与风险")
    md += paragraph(f"- 护城河：{result.get('moat_summary', '待填充')}")
    md += paragraph(f"- 关键风险：{', '.join(result.get('key_risks', ['待填充']))}")
    return md


def main():
    parser = argparse.ArgumentParser(description="Narrative Agent runner for Financial skill")
    parser.add_argument("--input-file", default=None, help="Input markdown file")
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    inputs = parse_input_markdown(text)
    result = run_narrative_analysis(inputs, mode="financial-support")
    print(format_output(result))


if __name__ == "__main__":
    main()
