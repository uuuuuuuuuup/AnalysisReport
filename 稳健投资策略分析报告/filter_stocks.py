#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
筛选当前股价距离买入目标价在±10%以内的公司
"""

import re
from datetime import datetime


def parse_price(price_str):
    """解析价格字符串，返回数值"""
    if not price_str or price_str.strip() == '':
        return None

    # 处理范围价格，如 "¥14.65-15.04" 或 "¥35.00-38.00"
    range_match = re.search(r'[¥HK\$]*\s*([\d,]+\.?\d*)\s*[-~]\s*([\d,]+\.?\d*)', price_str)
    if range_match:
        # 对于范围价格，取平均值
        low = float(range_match.group(1).replace(',', ''))
        high = float(range_match.group(2).replace(',', ''))
        return (low + high) / 2

    # 处理普通价格
    match = re.search(r'[¥HK\$]*\s*([\d,]+\.?\d*)', price_str)
    if match:
        return float(match.group(1).replace(',', ''))

    return None


def calculate_diff_percent(current, target):
    """计算当前价格与目标价格的差异百分比"""
    if current is None or target is None or target == 0:
        return None
    return ((current - target) / target) * 100


def parse_markdown_table(content):
    """解析Markdown表格数据"""
    stocks = []

    # 找到表格部分
    table_pattern = r'\| 股票名称 \| 当前股价 \| 买入目标价 \| 投资建议 \| 优先级 \|\n\|[-:|\s]+\|\n((?:\|[^\n]+\|\n?)+)'
    table_match = re.search(table_pattern, content)

    if table_match:
        table_content = table_match.group(1)
        lines = table_content.strip().split('\n')

        for line in lines:
            if not line.strip() or not line.startswith('|'):
                continue

            parts = [p.strip() for p in line.split('|')]
            # 过滤空字符串
            parts = [p for p in parts if p]

            if len(parts) >= 4:
                stock_name = parts[0]
                current_price_str = parts[1]
                target_price_str = parts[2]
                advice = parts[3] if len(parts) > 3 else ''
                priority = parts[4] if len(parts) > 4 else ''

                current_price = parse_price(current_price_str)
                target_price = parse_price(target_price_str)

                if current_price is not None and target_price is not None:
                    diff_percent = calculate_diff_percent(current_price, target_price)
                    stocks.append({
                        'name': stock_name,
                        'current_price': current_price,
                        'current_price_str': current_price_str,
                        'target_price': target_price,
                        'target_price_str': target_price_str,
                        'advice': advice,
                        'priority': priority,
                        'diff_percent': diff_percent
                    })

    return stocks


def filter_stocks_by_threshold(stocks, threshold=10):
    """筛选价格差异在阈值范围内的股票"""
    filtered = []
    for stock in stocks:
        if stock['diff_percent'] is not None:
            # 检查是否在 ±threshold% 范围内
            if abs(stock['diff_percent']) <= threshold:
                filtered.append(stock)

    # 按差异百分比绝对值排序（从小到大）
    filtered.sort(key=lambda x: abs(x['diff_percent']))
    return filtered


def generate_markdown_report(filtered_stocks, all_stocks_count, threshold):
    """生成Markdown报告"""
    now = datetime.now().strftime('%Y年%m月%d日 %H时%M分%S秒')

    md_content = f"""# 高度观察标的列表（价格接近目标价 ±{threshold}%）

**生成时间**: {now} CST

**筛选条件**: 当前股价距离买入目标价在 ±{threshold}% 以内

**原始公司总数**: {all_stocks_count}

**符合筛选条件**: {len(filtered_stocks)}

---

## 筛选结果汇总表

| 股票名称 | 当前股价 | 买入目标价 | 价格差异 | 差异百分比 | 投资建议 | 优先级 |
|:---|:---|:---|:---:|:---:|:---|:---:|
"""

    for stock in filtered_stocks:
        diff_sign = '+' if stock['diff_percent'] >= 0 else ''
        diff_str = f"{diff_sign}{stock['diff_percent']:.2f}%"
        diff_amount = stock['current_price'] - stock['target_price']
        diff_amount_str = f"+{diff_amount:.2f}" if diff_amount >= 0 else f"{diff_amount:.2f}"

        md_content += f"| {stock['name']} | {stock['current_price_str']} | {stock['target_price_str']} | {diff_amount_str} | {diff_str} | {stock['advice']} | {stock['priority']} |\n"

    md_content += """

---

## 详细数据

"""

    for stock in filtered_stocks:
        diff_sign = '+' if stock['diff_percent'] >= 0 else ''
        diff_str = f"{diff_sign}{stock['diff_percent']:.2f}%"
        diff_amount = stock['current_price'] - stock['target_price']
        diff_amount_str = f"+{diff_amount:.2f}" if diff_amount >= 0 else f"{diff_amount:.2f}"

        status = "🟢 低于目标价（可买入）" if stock['diff_percent'] <= 0 else "🔴 高于目标价（等待回调）"

        md_content += f"""### {stock['name']}

- **当前股价**: {stock['current_price_str']}
- **买入目标价**: {stock['target_price_str']}
- **价格差异**: {diff_amount_str} 元
- **差异百分比**: {diff_str}
- **投资建议**: {stock['advice']}
- **优先级**: {stock['priority']}
- **状态**: {status}

"""

    md_content += """---

## 说明

- **价格差异**: 当前股价 - 买入目标价（负值表示当前价格低于目标价，适合买入）
- **差异百分比**: (当前股价 - 买入目标价) / 买入目标价 × 100%
- **筛选逻辑**: 仅保留当前股价与买入目标价差异在 ±10% 范围内的标的
- **投资建议**: 差异为负或接近0的标的更具买入价值

---

**免责声明**: 本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。
"""

    return md_content


def main():
    # 读取原始文件
    input_file = '/Users/apple/Documents/分析报告/稳健投资策略分析报告/公司总结列表.md'
    output_file = '/Users/apple/Documents/分析报告/稳健投资策略分析报告/高度观察标的列表.md'

    threshold = 10  # 筛选阈值 ±10%

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析数据
        stocks = parse_markdown_table(content)
        print(f"成功解析 {len(stocks)} 家公司数据")

        # 筛选
        filtered_stocks = filter_stocks_by_threshold(stocks, threshold)
        print(f"符合 ±{threshold}% 筛选条件的公司: {len(filtered_stocks)} 家")

        # 生成报告
        report = generate_markdown_report(filtered_stocks, len(stocks), threshold)

        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"报告已生成: {output_file}")

        # 打印筛选结果
        if filtered_stocks:
            print("\n筛选结果:")
            print("-" * 80)
            for stock in filtered_stocks:
                diff_sign = '+' if stock['diff_percent'] >= 0 else ''
                print(f"{stock['name']}: 当前 {stock['current_price']:.2f}, 目标 {stock['target_price']:.2f}, "
                      f"差异 {diff_sign}{stock['diff_percent']:.2f}%")
        else:
            print("\n没有符合筛选条件的公司")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
