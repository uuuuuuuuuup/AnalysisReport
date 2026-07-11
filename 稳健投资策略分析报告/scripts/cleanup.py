#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理脚本：修复迁移后的残留问题
1. 修复文件名中的 "稳健投资策略分析报告：" 前缀
2. 修复文件名中的日期后缀（如 _20260423）
3. 处理重复的 data_pack_1 文件
4. 合并非标准 symbol 目录到标准目录
"""

import os, re, shutil
from pathlib import Path

BASE_DIR = Path("稳健投资策略分析报告")

def fix_filename_prefixes():
    """修复文件名中残留的 '稳健投资策略分析报告：' 前缀和日期后缀"""
    fixed = 0
    for fp in sorted(BASE_DIR.rglob("*.md")):
        if fp.parent.name == "scripts": continue
        name = fp.name
        new_name = name

        # 去掉 "稳健投资策略分析报告：" 前缀
        new_name = re.sub(r"^稳健投资策略分析报告[：:]", "", new_name)

        # 去掉日期后缀 _20260423, _20260508 等
        new_name = re.sub(r"_\d{8}(?=_|\.)", "", new_name)
        new_name = re.sub(r"_\d{4}-\d{2}-\d{2}(?=_|\.)", "", new_name)
        new_name = re.sub(r"_\d{4}_\d{2}_\d{2}(?=_|\.)", "", new_name)
        # 去掉 _2025, _2026 等纯年份后缀（但要小心别去掉 symbol 中的年份）
        # 只在文件名末尾附近处理
        new_name = re.sub(r"_\d{4}(?=\.md$)", "", new_name)

        if new_name != name:
            new_path = fp.parent / new_name
            if new_path.exists():
                # 如果目标已存在，比较内容
                if fp.read_text(encoding="utf-8") == new_path.read_text(encoding="utf-8"):
                    fp.unlink()  # 内容相同，删除重复
                    print(f"DEL (重复): {fp.relative_to(BASE_DIR)}")
                    fixed += 1
                    continue
                else:
                    # 内容不同，加序号
                    c = 1
                    while (fp.parent / f"{new_path.stem}_{c}{new_path.suffix}").exists():
                        c += 1
                    new_path = fp.parent / f"{new_path.stem}_{c}{new_path.suffix}"
            fp.rename(new_path)
            print(f"RENAME: {fp.relative_to(BASE_DIR)} -> {new_path.relative_to(BASE_DIR)}")
            fixed += 1
    print(f"文件名修复: {fixed} 个")

def fix_duplicate_datapacks():
    """处理 _1 重复数据包"""
    fixed = 0
    for fp in sorted(BASE_DIR.rglob("data_pack_*_1.md")):
        # 找到对应的原始文件
        orig = fp.parent / fp.name.replace("_1.md", ".md")
        if orig.exists():
            # 比较内容
            if fp.read_text(encoding="utf-8") == orig.read_text(encoding="utf-8"):
                fp.unlink()
                print(f"DEL (重复): {fp.relative_to(BASE_DIR)}")
                fixed += 1
            else:
                print(f"KEEP (内容不同): {fp.relative_to(BASE_DIR)}")
        else:
            # 原始不存在，重命名
            fp.rename(orig)
            print(f"RENAME: {fp.relative_to(BASE_DIR)} -> {orig.relative_to(BASE_DIR)}")
            fixed += 1
    print(f"数据包去重: {fixed} 个")

# 非标准 symbol 目录→标准 symbol 映射
SYMBOL_MERGE_MAP = {
    "000568_2025年报": "000568",
    "000651_2025年报": "000651",
    "000858_2025年3季报": "000858",
    "002508_2025年三季报": "002508",
    "01066.HK_2026_05_21": "01066.HK",
    "02313.HK_2026-05-21": "02313.HK",
    "02367.HK_4.20分析": "02367.HK",
    "06862.HK_2026_04_21": "06862.HK",
    "09987.HK_2026_05_20": "09987.HK",
    "300979_2026Q1": "300979",
    "603816_2026-04-23": "603816",
    "2367HK": "02367.HK",
    "HK0883": "00883.HK",
    "00270HK": "00270.HK",
    "00855HK": "00855.HK",
    "01193HK": "01193.HK",
    "03918": "03918.HK",
    "华润电力": "00836.HK",
    "城投控股": "600649",
    "周大生": "002867",
    "欧派家居": "603833",
    "首创环保": "600008",
    "600546.SH": "600546",
    "600489.SH": "600489",
    "601088.SH": "601088",
    "603816.SH": "603816",
}

def merge_symbol_dirs():
    """合并非标准 symbol 目录到标准目录"""
    merged = 0
    for old_name, new_name in SYMBOL_MERGE_MAP.items():
        old_dir = BASE_DIR / old_name
        new_dir = BASE_DIR / new_name
        if not old_dir.exists():
            # 可能已经处理过了
            continue
        if old_dir == new_dir:
            continue

        new_dir.mkdir(parents=True, exist_ok=True)

        # 移动所有版本目录
        for item in old_dir.iterdir():
            if item.name == "index.json" or item.name == "latest":
                continue
            if item.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", item.name):
                target = new_dir / item.name
                if target.exists():
                    # 同名版本目录，合并内容
                    for f in item.iterdir():
                        tf = target / f.name
                        if tf.exists():
                            c = 1
                            while (target / f"{f.stem}_{c}{f.suffix}").exists():
                                c += 1
                            tf = target / f"{f.stem}_{c}{f.suffix}"
                        shutil.move(str(f), str(tf))
                        print(f"MERGE: {f.relative_to(BASE_DIR)} -> {tf.relative_to(BASE_DIR)}")
                    item.rmdir()
                else:
                    shutil.move(str(item), str(target))
                    print(f"MERGE: {item.relative_to(BASE_DIR)} -> {target.relative_to(BASE_DIR)}")
                merged += 1

        # 清理旧目录
        remaining = list(old_dir.iterdir())
        if not remaining:
            old_dir.rmdir()
            print(f"RMDIR: {old_dir.relative_to(BASE_DIR)}")
        else:
            print(f"⚠️ 旧目录仍有残留: {old_dir} -> {[x.name for x in remaining]}")

    # 重建所有受影响目录的 index.json
    for new_name in set(SYMBOL_MERGE_MAP.values()):
        rebuild_index(BASE_DIR / new_name)

    print(f"symbol 合并: {merged} 个版本目录")

def rebuild_index(sym_dir):
    """重建单个 symbol 的 index.json"""
    if not sym_dir.exists(): return
    import json
    versions = []
    for vd in sorted(sym_dir.iterdir()):
        if not vd.is_dir(): continue
        if not re.match(r"\d{4}-\d{2}-\d{2}", vd.name): continue
        reports = [f.name for f in vd.iterdir() if f.is_file() and ("分析报告" in f.name or "投资" in f.name)]
        dp_m = vd / "data_pack_market.md"
        dp_r = vd / "data_pack_report.md"
        versions.append({
            "date": vd.name, "dir": vd.name,
            "report": reports,
            "data_pack_market": dp_m.name if dp_m.exists() else None,
            "data_pack_report": dp_r.name if dp_r.exists() else None,
        })
    if not versions: return
    versions.sort(key=lambda v: v["date"])
    latest = versions[-1]
    company = versions[-1]["report"][0].split("_")[0] if versions[-1]["report"] else None
    index = {"symbol": sym_dir.name, "company": company, "latest": latest["date"], "versions": versions}
    with open(sym_dir / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    # 更新 latest
    link = sym_dir / "latest"
    if link.exists():
        if link.is_symlink(): link.unlink()
        elif link.is_dir(): shutil.rmtree(link)
    try:
        os.symlink(latest["dir"], str(link))
    except OSError: pass

def main():
    print("=== 1. 修复文件名 ===")
    fix_filename_prefixes()

    print("\n=== 2. 数据包去重 ===")
    fix_duplicate_datapacks()

    print("\n=== 3. 合并非标准 symbol 目录 ===")
    merge_symbol_dirs()

    print("\n=== 清理完成 ===")

if __name__ == "__main__":
    main()