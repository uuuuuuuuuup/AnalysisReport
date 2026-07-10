#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone entry for narrative analysis."""
import argparse
import os
import sys
from data_sources import get_market_data_mx, get_market_data_lingxi, get_consensus_earnings
from narrative_core import run_narrative_analysis
from report_generator import generate_narrative_markdown


def collect_inputs(company_name: str, code: str | None = None) -> dict:
    """Collect required inputs from data sources."""
    # Try mx-data first, then lingxi
    data = get_market_data_mx(company_name) or get_market_data_lingxi(company_name)
    if not data:
        raise RuntimeError(f"无法获取 {company_name} 的市场数据，请手动提供。")

    earnings = get_consensus_earnings(company_name) or {}
    return {
        "company": company_name,
        "code": code or "未知",
        "market_cap": data["market_cap"],
        "price": data["price"],
        "total_shares": data.get("total_shares", data["market_cap"] / data["price"]),
        "e0": earnings.get("e0", 0),
        "e1": earnings.get("e1", 0),
        "e2": earnings.get("e2", 0),
        "e3": earnings.get("e3", 0),
    }


def main():
    parser = argparse.ArgumentParser(description="穿透叙事分析报告生成器")
    parser.add_argument("--company", required=True, help="公司简称")
    parser.add_argument("--code", default=None, help="股票代码")
    parser.add_argument("--output-dir", default="reports", help="输出目录")
    parser.add_argument("--format", default="markdown", choices=["markdown", "docx", "html"])
    args = parser.parse_args()

    inputs = collect_inputs(args.company, args.code)
    result = run_narrative_analysis(inputs, mode="standalone")
    report_path = generate_narrative_markdown(result, os.path.join(args.output_dir, f"{args.company}"))
    print(f"报告已生成: {report_path}")


if __name__ == "__main__":
    main()
