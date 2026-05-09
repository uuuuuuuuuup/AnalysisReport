#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国神华深度财务数据采集脚本
用于提取并整合各项财务数据
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

# 数据文件路径
DATA_DIR = Path("/Users/apple/Documents/分析报告/miaoxiang/mx_finance_data")
OUTPUT_DIR = Path("/Users/apple/Documents/分析报告/稳健投资策略分析报告/601088.SH")

def read_excel_sheets(file_path):
    """读取Excel文件的所有sheet"""
    try:
        excel_file = pd.ExcelFile(file_path)
        sheets = {}
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            sheets[sheet_name] = df
        return sheets
    except Exception as e:
        print(f"读取文件 {file_path} 失败: {e}")
        return {}

def extract_balance_sheet_data():
    """提取资产负债表数据"""
    file_path = DATA_DIR / "mx_finance_data_b206e822.xlsx"
    sheets = read_excel_sheets(file_path)

    data = {
        "母公司资产负债表": {},
        "合并资产负债表": {}
    }

    for sheet_name, df in sheets.items():
        if "601088.SH" in sheet_name and "合并" not in sheet_name:
            # 母公司报表
            print(f"\n母公司资产负债表 - {sheet_name}:")
            print(df.head(20))
        elif "合并" in sheet_name:
            # 合并报表
            print(f"\n合并资产负债表 - {sheet_name}:")
            print(df.head(20))

    return data

def extract_cashflow_data():
    """提取现金流量表数据"""
    file_path = DATA_DIR / "mx_finance_data_ccbce19f.xlsx"
    sheets = read_excel_sheets(file_path)

    print("\n现金流量表数据:")
    for sheet_name, df in sheets.items():
        print(f"\n{sheet_name}:")
        print(df.head(20))

def extract_financial_indicators():
    """提取财务指标数据"""
    file_path = DATA_DIR / "mx_finance_data_213fbb4b.xlsx"
    sheets = read_excel_sheets(file_path)

    print("\n财务指标数据:")
    for sheet_name, df in sheets.items():
        print(f"\n{sheet_name}:")
        print(df)

def extract_income_statement():
    """提取利润表和非经常性损益数据"""
    file_path = DATA_DIR / "mx_finance_data_cedf7444.xlsx"
    sheets = read_excel_sheets(file_path)

    print("\n利润表和非经常性损益数据:")
    for sheet_name, df in sheets.items():
        print(f"\n{sheet_name}:")
        print(df.head(30))

def extract_dividend_data():
    """提取股息分配数据"""
    file_path = DATA_DIR / "mx_finance_data_3b1deab7.xlsx"
    sheets = read_excel_sheets(file_path)

    print("\n股息分配数据:")
    for sheet_name, df in sheets.items():
        print(f"\n{sheet_name}:")
        print(df)

def extract_debt_data():
    """提取有息负债数据"""
    file_path = DATA_DIR / "mx_finance_data_e7fa897f.xlsx"
    sheets = read_excel_sheets(file_path)

    print("\n有息负债数据:")
    for sheet_name, df in sheets.items():
        print(f"\n{sheet_name}:")
        print(df)

if __name__ == "__main__":
    print("=" * 80)
    print("中国神华深度财务数据采集")
    print("=" * 80)

    # 提取各类数据
    extract_balance_sheet_data()
    extract_cashflow_data()
    extract_financial_indicators()
    extract_income_statement()
    extract_dividend_data()
    extract_debt_data()

    print("\n" + "=" * 80)
    print("数据提取完成")
    print("=" * 80)
