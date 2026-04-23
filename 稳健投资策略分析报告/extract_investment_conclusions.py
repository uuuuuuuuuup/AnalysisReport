#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投资结论数据提取脚本
提取所有公司分析报告中的投资结论部分
支持多种格式：## 投资结论 或 ## 指标摘要
"""

import os
import re
import glob
from pathlib import Path


def find_report_files(base_dir):
    """查找所有公司分析报告文件"""
    report_files = []

    # 遍历所有子文件夹
    for subdir in os.listdir(base_dir):
        subdir_path = os.path.join(base_dir, subdir)
        if os.path.isdir(subdir_path):
            # 查找匹配的报告文件
            for file in os.listdir(subdir_path):
                # 匹配 {公司名字}_稳健投资策略分析报告.md 或类似格式
                if file.endswith('.md') and ('分析报告' in file or '投资' in file):
                    report_files.append(os.path.join(subdir_path, file))

    return sorted(report_files)


def extract_investment_conclusion(file_path):
    """提取投资结论部分
    
    支持多种格式：
    1. ## 投资结论 - 标准格式（后面跟着指标摘要表格）
    2. ## 指标摘要 - 部分文件使用的格式
    3. 混合格式 - 投资结论后面直接是---分隔符
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"读取文件失败 {file_path}: {e}")
        return None

    # 策略：先找到"指标摘要"部分，因为它包含所有关键数据
    # 尝试1: 查找"## 指标摘要"
    pattern1 = r'## 指标摘要\n(.*?)(?=\n## [^#]|\Z)'
    match1 = re.search(pattern1, content, re.DOTALL)
    
    if match1:
        return match1.group(1).strip()
    
    # 尝试2: 查找"### 指标摘要"（三级标题格式）
    pattern2 = r'### 指标摘要\n(.*?)(?=\n## |\Z)'
    match2 = re.search(pattern2, content, re.DOTALL)
    
    if match2:
        return match2.group(2).strip()
    
    # 尝试3: 查找"## 投资结论"部分（到下一个二级标题或文件结束）
    pattern3 = r'## 投资结论\n(.*?)(?=\n## [^#]|\Z)'
    match3 = re.search(pattern3, content, re.DOTALL)
    
    if match3:
        return match3.group(1).strip()

    return None


def extract_key_metrics(conclusion_text, file_path):
    """从投资结论中提取关键指标"""
    metrics = {
        '股票名称': '',
        '当前股价': '',
        '买入目标价': '',
        '投资建议': '',
        '优先级': ''
    }

    if not conclusion_text:
        return metrics

    # 提取当前股价
    price_match = re.search(r'当前股价\s*\|\s*([^|]+)', conclusion_text)
    if price_match:
        metrics['当前股价'] = price_match.group(1).strip()

    # 提取目标买入价
    target_match = re.search(r'目标买入价\s*\|\s*([^|]+)', conclusion_text)
    if target_match:
        metrics['买入目标价'] = target_match.group(1).strip()

    # 提取仓位建议/投资建议
    advice_match = re.search(r'仓位建议\s*\|\s*([^|]+)', conclusion_text)
    if advice_match:
        advice = advice_match.group(1).strip()
        metrics['投资建议'] = advice

        # 从仓位建议中提取优先级
        if '高优先级' in advice or '高优' in advice:
            metrics['优先级'] = '高'
        elif '中优先级' in advice or '中优' in advice:
            metrics['优先级'] = '中'
        elif '低优先级' in advice or '低优' in advice:
            metrics['优先级'] = '低'
        elif '优先' in advice:
            # 提取第一个出现的优先级关键词
            if '高' in advice[:10]:
                metrics['优先级'] = '高'
            elif '中' in advice[:10]:
                metrics['优先级'] = '中'
            elif '低' in advice[:10]:
                metrics['优先级'] = '低'

    return metrics


def get_stock_name(file_path):
    """从文件路径中提取股票名称"""
    filename = os.path.basename(file_path)
    # 移除后缀
    name = filename.replace('.md', '')
    # 移除后缀部分
    name = re.sub(r'_.*', '', name)
    return name


def main():
    base_dir = '/Users/apple/Documents/分析报告/稳健投资策略分析报告'

    # 查找所有报告文件
    print("正在查找报告文件...")
    report_files = find_report_files(base_dir)
    print(f"找到 {len(report_files)} 个报告文件")

    # 存储所有结果
    all_conclusions = []
    all_metrics = []
    failed_files = []
    empty_data_files = []

    # 处理每个文件
    for file_path in report_files:
        stock_name = get_stock_name(file_path)

        conclusion = extract_investment_conclusion(file_path)
        if conclusion:
            # 提取关键指标
            metrics = extract_key_metrics(conclusion, file_path)
            metrics['股票名称'] = stock_name
            
            # 检查是否提取到了有效数据
            if not metrics['当前股价'] and not metrics['买入目标价'] and not metrics['投资建议']:
                empty_data_files.append(stock_name)
            
            all_conclusions.append({
                'stock_name': stock_name,
                'file_path': file_path,
                'conclusion': conclusion
            })
            all_metrics.append(metrics)
            
            if metrics['当前股价']:
                print(f"✅ 处理成功: {stock_name} (股价: {metrics['当前股价']})")
            else:
                print(f"⚠️  处理成功但数据为空: {stock_name}")
        else:
            failed_files.append(file_path)
            print(f"❌ 未找到投资结论: {stock_name}")

    # 生成投资结论汇总文档
    print("\n生成投资结论汇总文档...")
    with open(os.path.join(base_dir, '所有公司投资结论汇总.md'), 'w', encoding='utf-8') as f:
        f.write('# 所有公司投资结论汇总\n\n')
        f.write(f'**生成时间**: {os.popen("date").read().strip()}\n\n')
        f.write(f'**公司总数**: {len(all_conclusions)}\n\n')
        if failed_files:
            f.write(f'**提取失败**: {len(failed_files)} 家\n\n')
        if empty_data_files:
            empty_list = ', '.join(empty_data_files)
            f.write(f'**数据为空**: {len(empty_data_files)} 家 ({empty_list})\n\n')
        f.write('---\n\n')

        for item in all_conclusions:
            f.write(f"## {item['stock_name']}\n\n")
            f.write(f"**文件路径**: `{item['file_path']}`\n\n")
            f.write("### 投资结论\n\n")
            f.write(item['conclusion'])
            f.write('\n\n---\n\n')
        
        # 记录失败的文件
        if failed_files:
            f.write("\n## 提取失败的文件\n\n")
            for failed in failed_files:
                f.write(f"- `{failed}`\n")

    print(f"投资结论汇总已保存: {os.path.join(base_dir, '所有公司投资结论汇总.md')}")

    # 生成公司总结列表
    print("\n生成公司总结列表...")
    with open(os.path.join(base_dir, '公司总结列表.md'), 'w', encoding='utf-8') as f:
        f.write('# 公司投资总结列表\n\n')
        f.write(f'**生成时间**: {os.popen("date").read().strip()}\n\n')
        f.write(f'**公司总数**: {len(all_metrics)}\n\n')
        if empty_data_files:
            empty_list = ', '.join(empty_data_files)
            f.write(f'**注意**: 以下公司数据提取可能不完整: {empty_list}\n\n')

        # 写入表格
        f.write('| 股票名称 | 当前股价 | 买入目标价 | 投资建议 | 优先级 |\n')
        f.write('|:---|:---|:---|:---|:---|\n')

        for metrics in all_metrics:
            f.write(f"| {metrics['股票名称']} | {metrics['当前股价']} | {metrics['买入目标价']} | {metrics['投资建议']} | {metrics['优先级']} |\n")

        # 添加详细数据
        f.write('\n\n## 详细数据\n\n')
        for metrics in all_metrics:
            f.write(f"### {metrics['股票名称']}\n\n")
            f.write(f"- **当前股价**: {metrics['当前股价']}\n")
            f.write(f"- **买入目标价**: {metrics['买入目标价']}\n")
            f.write(f"- **投资建议**: {metrics['投资建议']}\n")
            f.write(f"- **优先级**: {metrics['优先级']}\n\n")

    print(f"公司总结列表已保存: {os.path.join(base_dir, '公司总结列表.md')}")

    print("\n✅ 数据整理完成!")
    print(f"   - 成功处理: {len(all_conclusions)} 家公司")
    print(f"   - 提取失败: {len(failed_files)} 家公司")
    print(f"   - 数据为空: {len(empty_data_files)} 家公司")
    print(f"   - 投资结论汇总: 所有公司投资结论汇总.md")
    print(f"   - 公司总结列表: 公司总结列表.md")
    
    if failed_files:
        print("\n⚠️ 以下文件未能提取投资结论:")
        for f in failed_files[:10]:
            print(f"   - {os.path.basename(f)}")
        if len(failed_files) > 10:
            print(f"   ... 还有 {len(failed_files) - 10} 个")
    
    if empty_data_files:
        print("\n⚠️ 以下公司数据提取为空:")
        for name in empty_data_files:
            print(f"   - {name}")


if __name__ == '__main__':
    main()
