#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd
import json
from datetime import datetime

# 读取所有数据文件
files = {
    "资产负债表": "/Users/apple/Documents/分析报告/miaoxiang/mx_finance_data/mx_finance_data_53d99158.xlsx",
    "现金流量表": "/Users/apple/Documents/分析报告/miaoxiang/mx_finance_data/mx_finance_data_a8133580.xlsx",
    "财务指标": "/Users/apple/Documents/分析报告/miaoxiang/mx_finance_data/mx_finance_data_46f606e8.xlsx",
    "股息数据": "/Users/apple/Documents/分析报告/miaoxiang/mx_finance_data/mx_finance_data_940f236e.xlsx",
    "有息负债": "/Users/apple/Documents/分析报告/miaoxiang/mx_finance_data/mx_finance_data_38d03aca.xlsx",
    "非经常性损益": "/Users/apple/Documents/分析报告/miaoxiang/mx_finance_data/mx_finance_data_6e56a7d7.xlsx"
}

for name, file_path in files.items():
    print(f"\n{'='*60}")
    print(f"{name}数据:")
    print('='*60)
    try:
        # 读取所有sheet
        xl = pd.ExcelFile(file_path)
        for sheet_name in xl.sheet_names:
            print(f"\nSheet: {sheet_name}")
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            print(df.head(30).to_string())
    except Exception as e:
        print(f"读取失败: {e}")
