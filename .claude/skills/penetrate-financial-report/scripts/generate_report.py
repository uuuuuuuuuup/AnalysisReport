#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main entry for financial report generation."""
import argparse
import os
import sys
from data_collector import collect_financial_inputs
from narrative_agent import build_narrative_input, call_narrative_agent
from financial_analyzer import analyze_balance_sheet, analyze_income_statement, analyze_cash_flow, compute_financial_quality
from report_builder import build_financial_report


def main():
    parser = argparse.ArgumentParser(description="穿透财报分析报告生成器")
    parser.add_argument("--company", required=True, help="公司简称")
    parser.add_argument("--code", required=True, help="股票代码（如 300308.SZ）")
    parser.add_argument("--output-dir", default="reports", help="输出目录")
    parser.add_argument("--format", default="markdown", choices=["markdown", "docx", "html"])
    args = parser.parse_args()

    inputs = collect_financial_inputs(args.company, args.code)

    # Call Narrative Agent
    narrative_input = build_narrative_input(
        company=args.company,
        code=args.code,
        market_cap=inputs["market_cap"],
        total_shares=inputs["total_shares"],
        price=inputs["price"],
        e0=inputs["e0"],
        e1=inputs["e1"],
        e2=inputs["e2"],
        e3=inputs["e3"],
        industry=inputs.get("industry", "")
    )
    narrative = call_narrative_agent(narrative_input)

    # Analyze financial statements
    financials = {
        "balance_sheet": analyze_balance_sheet(inputs.get("balance_sheet", {})),
        "income_statement": analyze_income_statement(inputs.get("income_statement", {})),
        "cash_flow": analyze_cash_flow(inputs.get("cash_flow", {})),
        "quality": compute_financial_quality({}),
    }

    output_dir = os.path.join(args.output_dir, f"{args.company}_{args.code.replace('.', '_')}")
    report_path = build_financial_report(args.company, args.code, narrative, financials, output_dir)
    print(f"报告已生成: {report_path}")


if __name__ == "__main__":
    main()
