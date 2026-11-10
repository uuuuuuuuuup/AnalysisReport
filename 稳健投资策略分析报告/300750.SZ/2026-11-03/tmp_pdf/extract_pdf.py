#!/usr/bin/env python3
"""提取宁德时代2025年审计报告PDF全文文本，供后续检索附注关键数据。"""
import sys
import time
from pypdf import PdfReader

SRC = "/Users/apple/Documents/分析报告/稳健投资策略分析报告/300750.SZ/2026-11-03/tmp_pdf/audit_report_2025.pdf"
DST = "/Users/apple/Documents/分析报告/稳健投资策略分析报告/300750.SZ/2026-11-03/tmp_pdf/audit_report_2025.txt"

start = time.time()
reader = PdfReader(SRC)
total = len(reader.pages)
print(f"总页数: {total}", flush=True)

parts = []
empty_pages = 0
for i, page in enumerate(reader.pages):
    try:
        text = page.extract_text() or ""
    except Exception as exc:  # 单页失败不阻塞整体
        text = f"[第{i+1}页提取失败: {exc}]"
        empty_pages += 1
    if not text.strip():
        empty_pages += 1
    parts.append(f"\n===== PAGE {i+1} =====\n{text}")

with open(DST, "w", encoding="utf-8") as f:
    f.write("".join(parts))

print(f"完成: 写出 {DST}, 耗时 {time.time()-start:.1f}s, 空/失败页 {empty_pages}", flush=True)
