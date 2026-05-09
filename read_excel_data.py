#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取中国移动财务数据Excel文件并提取关键信息
"""

import pandas as pd
import json
from pathlib import Path

def read_excel_data(file_path):
    """读取Excel文件并返回所有sheet的数据"""
    try:
        excel_file = pd.ExcelFile(file_path)
        data = {}
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            data[sheet_name] = df.to_dict(orient='records')
        return data
    except Exception as e:
        return {"error": str(e)}

# 文件路径
base_path = Path("/Users/apple/Documents/分析报告/miaoxiang/mx_finance_data")

files = {
    "资产负债表": "mx_finance_data_6c2acda9.xlsx",
    "现金流量表": "mx_finance_data_dd562a54.xlsx",
    "利润表": "mx_finance_data_752aff2b.xlsx",
    "财务指标": "mx_finance_data_a528792b.xlsx",
    "股息分配": "mx_finance_data_853c9b09.xlsx",
    "有息负债": "mx_finance_data_0badea64.xlsx"
}

# 读取所有文件
all_data = {}
for name, filename in files.items():
    file_path = base_path / filename
    if file_path.exists():
        all_data[name] = read_excel_data(file_path)
        print(f"\n{'='*60}")
        print(f"{name}:")
        print(f"{'='*60}")
        for sheet_name, data in all_data[name].items():
            if sheet_name != "error":
                print(f"\nSheet: {sheet_name}")
                if isinstance(data, list) and len(data) > 0:
                    # 只打印前5条记录
                    for i, record in enumerate(data[:10]):
                        print(f"记录 {i+1}: {record}")
