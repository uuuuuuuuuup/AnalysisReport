#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取 稳健投资策略分析报告 中各报告文件的分析日期。

优先级：
1. 报告内容中的明确日期（数据采集时间、分析基准日、数据截止）
2. 报告文件名中的日期
3. 文件创建时间（birthtime）

输出：CSV 文件，包含每个报告文件的推断日期及来源。
"""

import os
import re
import csv
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("稳健投资策略分析报告")
OUTPUT_CSV = BASE_DIR / "scripts" / "report_dates.csv"

# 根目录下的汇总文件/脚本，不参与分析
ROOT_FILES_TO_IGNORE = {
    "公司总结列表.md",
    "所有公司投资结论汇总.md",
    "高度观察标的列表.md",
    "高度观察标的验证报告.md",
    "投资组合精简配置方案.md",
    "投资组合配置报告.md",
    "科技ETF分析.md",
    "extract_investment_conclusions.py",
    "filter_stocks.py",
    ".DS_Store",
}


def get_file_birthtime(path):
    """获取文件创建时间（兼容 macOS 的 st_birthtime）。"""
    stat = os.stat(path)
    if hasattr(stat, "st_birthtime"):
        return datetime.fromtimestamp(stat.st_birthtime)
    else:
        # Linux 通常没有真正的 birthtime，用 ctime 兜底
        return datetime.fromtimestamp(stat.st_ctime)


def parse_full_date(text):
    """从文本中提取 YYYY-MM-DD 格式的日期。"""
    if not text:
        return None
    patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{4}年\d{1,2}月\d{1,2}日)",
        r"(\d{4}/\d{2}/\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            raw = match.group(1)
            # 统一转成 YYYY-MM-DD
            for fmt in ("%Y-%m-%d", "%Y年%m月%d日", "%Y/%m/%d"):
                try:
                    return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
    return None


def extract_year(text):
    """从文本中提取 4 位年份，优先匹配报告年份上下文。"""
    if not text:
        return None
    # 优先匹配年度报告、季度报告等上下文
    patterns = [
        r"(20\d{2})年度",
        r"(20\d{2})\s*年报",
        r"(20\d{2})\s*一季报",
        r"(20\d{2})\s*三季报",
        r"(20\d{2})\s*半年报",
        r"(20\d{2})\s*年",
        r"FY(20\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    # 兜底：任意 20xx（可能误匹配股票代码，慎用）
    match = re.search(r"(20\d{2})", text)
    return match.group(1) if match else None


def infer_report_period_from_content(content):
    """
    推断报告覆盖的财务期间，用于在仅有年份时补充默认月日。
    返回 ('年报', '12-31')、('三季报', '09-30') 等。
    """
    content_lower = content.lower()
    if re.search(r"(?<!半)年报", content):
        return "年报", "12-31"
    if re.search(r"三季度报告|三季报|三季度", content):
        return "三季报", "09-30"
    if re.search(r"半年报告|半年报|半年", content):
        return "半年报", "06-30"
    if re.search(r"一季度报告|一季报|一季度", content):
        return "一季报", "03-31"
    return None, None


def extract_date_from_content_meta(content):
    """
    从报告内容中提取元数据里的明确日期（如数据采集时间、分析基准日、数据截止）。
    返回 (date_str, source, confidence)。
    """
    # 优先找元数据中的完整日期（支持表格、加粗、普通文本格式）
    meta_patterns = [
        r"数据采集时间\s*[:：|]?\s*([^\n|]+)",
        r"分析基准日\s*[:：|]?\s*([^\n|]+)",
        r"数据截止\s*[:：|]?\s*([^\n|]+)",
    ]
    for pattern in meta_patterns:
        match = re.search(pattern, content)
        if match:
            meta_value = match.group(1)
            date_str = parse_full_date(meta_value)
            if date_str:
                return date_str, "内容-元数据完整日期", "high"
            # 元数据字段没有完整日期，但可能有年份和报告类型
            year = extract_year(meta_value)
            if year:
                report_type, default_month_day = infer_report_period_from_content(meta_value)
                if not default_month_day:
                    report_type, default_month_day = infer_report_period_from_content(content)
                if default_month_day:
                    return f"{year}-{default_month_day}", f"内容-{year}{report_type}默认月日", "medium"

    return None, None, None


def extract_date_from_filename(filename):
    """从文件名中推断日期。"""
    # 1. 完整日期
    patterns_full = [
        r"(\d{4})(\d{2})(\d{2})",  # 20260423
        r"(\d{4})-(\d{2})-(\d{2})",  # 2026-04-23
        r"(\d{4})_(\d{2})_(\d{2})",  # 2026_04_23
    ]
    for pattern in patterns_full:
        match = re.search(pattern, filename)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month}-{day}", "文件名-完整日期", "high"

    # 2. 年份 + 季度/报告类型
    year = extract_year(filename)
    if year:
        if "年报" in filename or "Q4" in filename.upper():
            return f"{year}-12-31", "文件名-年报/Q4", "medium"
        if re.search(r"三季报|三季度|Q3", filename, re.IGNORECASE):
            return f"{year}-09-30", "文件名-三季报/Q3", "medium"
        if re.search(r"半年报|半年|Q2", filename, re.IGNORECASE):
            return f"{year}-06-30", "文件名-半年报/Q2", "medium"
        if re.search(r"一季报|一季度|Q1", filename, re.IGNORECASE):
            return f"{year}-03-31", "文件名-一季报/Q1", "medium"
        return f"{year}-01-01", "文件名-仅年份", "low"

    return None, None, None


def is_report_file(filename):
    """判断是否为需要推断日期的报告文件。"""
    if not filename.endswith(".md"):
        return False
    if filename in ("data_pack_market.md", "data_pack_report.md",
                    "data_pact_market.md", "data_pact_report.md"):
        return False
    # 只要包含“分析报告”或“投资”即视为报告文件
    if "分析报告" in filename or "投资" in filename:
        return True
    return False


def find_report_files(base_dir):
    """遍历 base_dir 下的股票子目录，收集所有报告文件。"""
    reports = []
    for symbol_dir in sorted(base_dir.iterdir()):
        if not symbol_dir.is_dir():
            continue
        if symbol_dir.name == "scripts":
            continue
        for file_path in symbol_dir.rglob("*.md"):
            if not file_path.is_file():
                continue
            if file_path.name in ROOT_FILES_TO_IGNORE:
                continue
            if not is_report_file(file_path.name):
                continue
            # 计算相对 BASE_DIR 的路径
            rel_path = file_path.relative_to(base_dir)
            reports.append({
                "symbol_dir": symbol_dir.name,
                "rel_path": rel_path.as_posix(),
                "file_path": file_path,
                "filename": file_path.name,
            })
    return reports


def infer_date_for_report(report):
    """综合文件名、内容、创建时间推断日期。"""
    file_path = report["file_path"]
    filename = report["filename"]

    # 读取内容
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        content = ""
        print(f"⚠️ 读取失败: {file_path} ({e})")

    # 1. 文件名中的完整日期（最可靠，不会被正文里的股价日期干扰）
    date_str, source, confidence = extract_date_from_filename(filename)
    if date_str and confidence == "high":
        return date_str, source, confidence

    # 2. 内容中的元数据完整日期（如数据采集时间、分析基准日、数据截止）
    date_str, source, confidence = extract_date_from_content_meta(content)
    if date_str:
        return date_str, source, confidence

    # 3. 文件名中的年份/报告类型（如 2025年报）
    date_str, source, confidence = extract_date_from_filename(filename)
    if date_str:
        return date_str, source, confidence

    # 4. 文件创建时间
    birth = get_file_birthtime(file_path)
    return birth.strftime("%Y-%m-%d"), "文件创建时间", "low"


def main():
    if not BASE_DIR.exists():
        print(f"错误：目录不存在 {BASE_DIR}")
        return

    reports = find_report_files(BASE_DIR)
    print(f"共找到 {len(reports)} 个报告文件")

    rows = []
    for report in reports:
        date_str, source, confidence = infer_date_for_report(report)
        birth = get_file_birthtime(report["file_path"])
        rows.append({
            "symbol_dir": report["symbol_dir"],
            "report_file": report["filename"],
            "rel_path": report["rel_path"],
            "inferred_date": date_str,
            "date_source": source,
            "confidence": confidence,
            "file_birthtime": birth.strftime("%Y-%m-%d %H:%M:%S"),
        })

    # 按 symbol_dir 和 inferred_date 排序
    rows.sort(key=lambda x: (x["symbol_dir"], x["inferred_date"]))

    # 写入 CSV
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "symbol_dir", "report_file", "rel_path",
            "inferred_date", "date_source", "confidence", "file_birthtime"
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"结果已写入: {OUTPUT_CSV}")
    print(f"高置信度: {sum(1 for r in rows if r['confidence'] == 'high')}")
    print(f"中置信度: {sum(1 for r in rows if r['confidence'] == 'medium')}")
    print(f"低置信度: {sum(1 for r in rows if r['confidence'] == 'low')}")


if __name__ == "__main__":
    main()
