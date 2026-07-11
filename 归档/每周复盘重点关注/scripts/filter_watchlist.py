#!/usr/bin/env python3
"""
关注池筛选脚本 - 稳健投资策略周报系统
遍历稳健投资策略分析报告，提取关键指标，计算优先级分数，
复制前30名到每周复盘重点关注目录。
"""

import os
import re
import shutil
from pathlib import Path
from datetime import datetime

# 配置
BASE_DIR = Path("/Users/apple/Documents/分析报告")
SOURCE_DIR = BASE_DIR / "稳健投资策略分析报告"
TARGET_DIR = BASE_DIR / "每周复盘重点关注"


def extract_from_table(content, field_name):
    """从markdown表格中提取字段值"""
    # 匹配 | 字段名 | **值** | 说明 |
    # 也处理 | 字段名 | 值 | 说明 | (无加粗)
    # 以及 | 字段名（xxx） | **值** | 说明 |
    patterns = [
        rf'\|\s*{re.escape(field_name)}(?:\([^)]*\))?\s*\|\s*\*\*(.*?)\*\*\s*\|',
        rf'\|\s*{re.escape(field_name)}(?:\([^)]*\))?\s*\|\s*([^|]*)\s*\|',
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
    return None


def extract_company_info(content, filename, dir_name):
    """提取公司名称和股票代码"""
    # 尝试从第一行提取: # 公司名（代码）...
    lines = content.split('\n')
    first_line = lines[0] if lines else ""
    
    # 模式1: # 公司名（代码）...
    m = re.search(r'#\s*[^—]*[—\s]*([^（(]+)[（(]([0-9]{4,6}(?:\.HK)?)[）)]', first_line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    
    # 模式2: # 稳健投资策略分析报告：公司名（代码）
    m = re.search(r'：\s*([^（(]+)[（(]([0-9]{4,6}(?:\.HK)?)[）)]', first_line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    
    # 模式3: # 公司名(代码)稳健投资策略分析报告
    m = re.search(r'#\s*([^（(]+)[（(]([0-9]{4,6}(?:\.HK)?)[）)]', first_line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    
    # 模式4: 从内容中找 **公司名** · 代码 ·
    m = re.search(r'\*\*([^*]+)\*\*\s*·\s*([0-9]{4,6}(?:\.HK)?)', content)
    if m:
        name = m.group(1).strip()
        code = m.group(2).strip()
        # 过滤掉过长的匹配（可能是段落）
        if len(name) < 50:
            return name, code
    
    # 模式5: 从文件名提取: 公司名_代码_分析报告.md
    m = re.search(r'^([^_]+)_([0-9]{4,6}(?:\.HK)?)_', filename)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    
    # 模式6: 从目录名提取代码
    # 目录名可能是 代码、代码_后缀、HK代码、中文名
    code = None
    if re.match(r'^[0-9]{4,6}(\.HK)?$', dir_name):
        code = dir_name
    elif re.match(r'^[0-9]{5}\.HK$', dir_name):
        code = dir_name
    elif re.match(r'^HK[0-9]{4}$', dir_name):
        code = dir_name.replace('HK', '') + '.HK'
    elif re.match(r'^[0-9]{4,5}HK$', dir_name):
        code = dir_name.replace('HK', '') + '.HK'
    elif re.match(r'^[0-9]{4,6}\.SH$', dir_name):
        code = dir_name.replace('.SH', '')
    elif re.match(r'^[0-9]{4,6}\.SZ$', dir_name):
        code = dir_name.replace('.SZ', '')
    
    # 尝试从文件名提取公司名
    name = None
    m = re.search(r'^([^_]+)_', filename)
    if m:
        name = m.group(1).strip()
    
    if name and code:
        return name, code
    
    return None, None


def parse_numeric_value(value_str):
    """解析数值，返回float或None"""
    if not value_str:
        return None
    # 清理字符串
    cleaned = value_str.replace(',', '').replace(' ', '')
    # 提取数字部分（包括负号和小数点）
    m = re.search(r'([-+]?[0-9]*\.?[0-9]+)', cleaned)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def calculate_score(position, distance, margin, return_rate):
    """计算优先级分数"""
    score = 0
    
    # 仓位建议分数
    if position:
        pos_lower = position.lower()
        if any(k in pos_lower for k in ['建仓', '配置', '可适度', '可逢低', '可建底仓']):
            score += 100
        elif '观察' in pos_lower:
            score += 50
        elif any(k in pos_lower for k in ['否决', '排除', '不建仓', '不建议']):
            score -= 50
    
    # 距离目标价分数
    if distance is not None:
        if distance < 0:
            score += 30
        elif distance < 5:
            score += 20
    
    # 安全边际分数
    if margin is not None:
        if margin > 1.5:
            score += 25
        elif margin > 0:
            score += 15
    
    return score


def find_main_report(directory):
    """找到目录中的主报告文件"""
    md_files = []
    for f in directory.iterdir():
        if f.is_file() and f.suffix == '.md':
            fname = f.name.lower()
            if 'data_pack' in fname or 'data_pact' in fname:
                continue
            md_files.append(f)
    
    if not md_files:
        return None
    
    # 优先选择文件名含 "投资分析" 或 "稳健投资" 的文件
    main_candidates = []
    for f in md_files:
        fname = f.name.lower()
        if '投资分析' in fname or '稳健投资' in fname:
            main_candidates.append(f)
    
    if main_candidates:
        # 如果有多份，选择修改时间最新的
        main_candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return main_candidates[0]
    
    # 如果没有含关键词的文件，选择修改时间最新的非data_pack文件
    md_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return md_files[0]


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始筛选关注池...")
    print(f"源目录: {SOURCE_DIR}")
    print(f"目标目录: {TARGET_DIR}")
    print()
    
    if not SOURCE_DIR.exists():
        print(f"错误: 源目录不存在: {SOURCE_DIR}")
        return
    
    # 收集所有报告数据
    reports = []
    skipped = []
    
    for subdir in SOURCE_DIR.iterdir():
        if not subdir.is_dir():
            continue
        
        dir_name = subdir.name
        
        # 跳过非报告目录
        if dir_name in ['归档', 'backup', '.git']:
            continue
        
        report_file = find_main_report(subdir)
        if not report_file:
            continue
        
        try:
            content = report_file.read_text(encoding='utf-8')
        except Exception as e:
            skipped.append((dir_name, f"读取失败: {e}"))
            continue
        
        # 提取公司信息
        name, code = extract_company_info(content, report_file.name, dir_name)
        if not code:
            # 尝试从目录名提取代码
            code = dir_name
            if not name:
                name = dir_name
        
        # 提取关键指标
        position = extract_from_table(content, '仓位建议')
        distance_str = extract_from_table(content, '距离目标价')
        margin_str = extract_from_table(content, '安全边际')
        return_str = extract_from_table(content, '精算穿透回报率')
        
        # 解析数值
        distance = parse_numeric_value(distance_str)
        margin = parse_numeric_value(margin_str)
        return_rate = parse_numeric_value(return_str)
        
        # 计算分数
        score = calculate_score(position, distance, margin, return_rate)
        
        reports.append({
            'code': code,
            'name': name or code,
            'position': position or '—',
            'distance': distance_str or '—',
            'margin': margin_str or '—',
            'return_rate': return_str or '—',
            'score': score,
            'source_dir': subdir,
            'source_file': report_file,
        })
    
    print(f"共扫描 {len(reports)} 份报告，跳过 {len(skipped)} 份")
    if skipped:
        for name, reason in skipped[:5]:
            print(f"  跳过 {name}: {reason}")
        if len(skipped) > 5:
            print(f"  ... 还有 {len(skipped) - 5} 份")
    print()
    
    # 按分数排序
    reports.sort(key=lambda x: x['score'], reverse=True)
    
    # 取前30名
    top30 = reports[:30]
    
    print(f"前30名公司（按优先级分数排序）:")
    print(f"{'排名':<4} {'代码':<10} {'公司名':<12} {'分数':<6} {'仓位建议':<20} {'距离目标价':<10} {'安全边际':<10}")
    print("-" * 90)
    for i, r in enumerate(top30, 1):
        name_display = r['name'][:10] if len(r['name']) > 10 else r['name']
        pos_display = r['position'][:18] if len(r['position']) > 18 else r['position']
        print(f"{i:<4} {r['code']:<10} {name_display:<12} {r['score']:<6} {pos_display:<20} {r['distance']:<10} {r['margin']:<10}")
    print()
    
    # 清空目标目录（保留scripts子目录）
    if TARGET_DIR.exists():
        for item in TARGET_DIR.iterdir():
            if item.name == 'scripts':
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    else:
        TARGET_DIR.mkdir(parents=True, exist_ok=True)
    
    # 复制前30名的目录
    copied = 0
    for r in top30:
        source = r['source_dir']
        dest = TARGET_DIR / source.name
        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest)
            copied += 1
            print(f"  [复制] {r['name']} ({r['code']}) -> {dest.name}")
        except Exception as e:
            print(f"  [错误] 复制 {r['name']} ({r['code']}) 失败: {e}")
    
    print(f"\n共复制 {copied} 个公司目录")
    
    # 生成 _watchlist.md
    watchlist_path = TARGET_DIR / '_watchlist.md'
    lines = [
        "# 每周复盘重点关注清单",
        "",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 筛选来源: 稳健投资策略分析报告 ({len(reports)} 份报告)",
        f"> 筛选规则: 按优先级分数排序，取前30名",
        "",
        "## 排名列表",
        "",
        "| 排名 | 代码 | 公司名 | 优先级分数 | 仓位建议 | 距离目标价 | 安全边际 | 精算穿透回报率 |",
        "|:---:|:---:|:---|:---:|:---|:---:|:---:|:---:|",
    ]
    
    for i, r in enumerate(top30, 1):
        lines.append(
            f"| {i} | {r['code']} | {r['name']} | **{r['score']}** | {r['position']} | {r['distance']} | {r['margin']} | {r['return_rate']} |"
        )
    
    lines.extend([
        "",
        "## 评分规则",
        "",
        "| 条件 | 分数 |",
        "|:---|:---:|",
        "| 仓位建议含'建仓'/'配置'/'可适度' | +100 |",
        "| 仓位建议含'观察' | +50 |",
        "| 仓位建议含'否决'/'排除'/'不建仓' | -50 |",
        "| 距离目标价 < 0% | +30 |",
        "| 距离目标价 < 5% | +20 |",
        "| 安全边际 > 1.5pct | +25 |",
        "| 安全边际 > 0pct | +15 |",
        "",
        "## 完整排名（前50名）",
        "",
        "| 排名 | 代码 | 公司名 | 分数 | 仓位建议 |",
        "|:---:|:---:|:---|:---:|:---|",
    ])
    
    for i, r in enumerate(reports[:50], 1):
        lines.append(f"| {i} | {r['code']} | {r['name']} | {r['score']} | {r['position']} |")
    
    watchlist_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"\n生成清单文件: {watchlist_path}")
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 筛选完成!")


if __name__ == '__main__':
    main()
