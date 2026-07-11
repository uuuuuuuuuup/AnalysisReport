#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整理迁移脚本 v2 —— 分步执行，每步可验证。

步骤:
1. 收集所有 symbol 根目录下的报告文件
2. 推断每个报告的目标版本目录
3. 移动文件 + 重命名
4. 创建 index.json + latest
5. 归档根目录杂物
"""

import os, re, json, shutil, csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path("稳健投资策略分析报告")
CSV = BASE_DIR / "scripts" / "report_dates.csv"

ROOT_ARCHIVE = {
    "公司总结列表.md", "所有公司投资结论汇总.md", "高度观察标的列表.md",
    "高度观察标的验证报告.md", "投资组合精简配置方案.md", "投资组合配置报告.md",
    "科技ETF分析.md", "extract_investment_conclusions.py", "filter_stocks.py",
}

DATA_PACK_NAMES = {"data_pack_market.md", "data_pack_report.md",
                   "data_pact_market.md", "data_pact_report.md"}

# ============================================================
# 工具函数
# ============================================================

def fix_pact(name):
    return name.replace("data_pact_", "data_pack_")

def get_birthtime(path):
    s = os.stat(path)
    return datetime.fromtimestamp(s.st_birthtime if hasattr(s, "st_birthtime") else s.st_ctime)

def parse_date(text):
    if not text: return None
    for m in re.finditer(r"(\d{4}-\d{2}-\d{2})", text):
        try: return datetime.strptime(m.group(1), "%Y-%m-%d").strftime("%Y-%m-%d")
        except: pass
    return None

def company_from_content(content):
    for line in content.strip().split("\n")[:5]:
        for pat in [r"#\s*(.+?)\s*（\s*\d+\s*）", r"#\s*(.+?)\s*·\s*\d+",
                     r"\*\*(.+?)\*\*\s*（\s*\d+\s*）", r"\*\*(.+?)\*\*\s*·\s*\d+"]:
            m = re.search(pat, line)
            if m: return m.group(1).strip().replace("**", "").strip()
    return None

def company_from_fname(fname):
    for suf in ["_稳健投资策略分析报告.md", "_投资分析报告.md", "_分析报告.md"]:
        if fname.endswith(suf):
            p = fname[:-len(suf)]
            parts = p.split("_")
            # 去掉末尾的日期和可能的 symbol
            clean = [x for x in parts if not re.match(r"\d{8}$|\d{4}-\d{2}-\d{2}$|\d{4}_\d{2}_\d{2}$", x)]
            if clean: return "_".join(clean)
    return fname[:-3] if fname.endswith(".md") else fname

def report_date_from_dir(file_path):
    """如果文件在 YYYY-MM-DD 子目录中，返回目录名"""
    parent = file_path.parent
    if parent != BASE_DIR and re.match(r"\d{4}-\d{2}-\d{2}", parent.name):
        return parent.name
    return None

def report_date_from_content(content):
    """从内容元数据提取日期"""
    for pat in [r"分析基准日\s*[:：|]?\s*(\d{4}-\d{2}-\d{2})",
                r"数据采集时间\s*[:：|]?\s*(\d{4}-\d{2}-\d{2})",
                r"数据截止\s*[:：|]?\s*(\d{4}-\d{2}-\d{2})"]:
        m = re.search(pat, content)
        if m: return m.group(1)
    return None

def report_date_from_fname(fname):
    """从文件名提取日期"""
    m = re.search(r"(\d{4})(\d{2})(\d{2})", fname)  # 20260423
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{4})_(\d{2})_(\d{2})", fname)  # 2026_04_21
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None

def is_report_file(fname):
    if not fname.endswith(".md"): return False
    if fname in DATA_PACK_NAMES: return False
    return "分析报告" in fname or "投资" in fname

# ============================================================
# 步骤 1: 收集
# ============================================================

def collect():
    """收集所有需要处理的文件。返回 [(symbol_dir, file_path, kind)]"""
    items = []
    for sym_dir in sorted(BASE_DIR.iterdir()):
        if not sym_dir.is_dir(): continue
        if sym_dir.name == "scripts": continue

        # 根目录下的文件
        for fp in sym_dir.iterdir():
            if not fp.is_file(): continue
            kind = "report" if is_report_file(fp.name) else ("datapack" if fp.name in DATA_PACK_NAMES else None)
            if kind:
                items.append((sym_dir.name, fp, kind))

    return items

# ============================================================
# 步骤 2: 推断目标版本目录
# ============================================================

def infer_date_for_report(fp):
    """推断报告文件的分析日期。按优先级：目录名 > 内容元数据 > 文件名 > 创建时间"""
    # 1. 已在日期子目录中
    d = report_date_from_dir(fp)
    if d: return d

    # 2. 内容元数据
    try:
        content = fp.read_text(encoding="utf-8")
    except:
        content = ""
    d = report_date_from_content(content)
    if d: return d

    # 3. 文件名
    d = report_date_from_fname(fp.name)
    if d: return d

    # 4. 创建时间
    return get_birthtime(fp).strftime("%Y-%m-%d")

def build_plan(items):
    """
    构建迁移计划。
    返回 {symbol: [(src_path, target_dir, target_name, kind), ...]}
    """
    # 先按 symbol 分组，找出每个 symbol 下有哪些报告和它们的目标日期
    sym_reports = defaultdict(list)
    sym_packs = defaultdict(list)

    for sym, fp, kind in items:
        if kind == "report":
            date = infer_date_for_report(fp)
            sym_reports[sym].append((fp, date))
        elif kind == "datapack":
            sym_packs[sym].append(fp)

    plan = defaultdict(list)

    for sym in set(list(sym_reports.keys()) + list(sym_packs.keys())):
        sym_root = BASE_DIR / sym
        reports = sym_reports.get(sym, [])
        packs = sym_packs.get(sym, [])

        # 如果只有一个报告版本，所有数据包归该版本
        if len(reports) == 1:
            fp, date = reports[0]
            company = company_from_fname(fp.name)
            # 尝试从内容提取更准确的公司名
            try:
                c = company_from_content(fp.read_text(encoding="utf-8"))
                if c: company = c
            except: pass
            target_name = f"{company}_{sym}_稳健投资策略分析报告.md"
            target_name = re.sub(r"[\\/:*?\"<>|]", "", target_name)
            target_dir = sym_root / date
            plan[sym].append((fp, target_dir, target_name, "report"))
            # 数据包归同一版本
            for p in packs:
                plan[sym].append((p, target_dir, fix_pact(p.name), "datapack"))

        elif len(reports) > 1:
            # 多个报告版本，数据包按文件修改时间就近归属
            for fp, date in reports:
                company = company_from_fname(fp.name)
                try:
                    c = company_from_content(fp.read_text(encoding="utf-8"))
                    if c: company = c
                except: pass
                target_name = f"{company}_{sym}_稳健投资策略分析报告.md"
                target_name = re.sub(r"[\\/:*?\"<>|]", "", target_name)
                target_dir = sym_root / date
                plan[sym].append((fp, target_dir, target_name, "report"))

            # 数据包按 mtime 就近归属到报告版本
            for p in packs:
                pmt = p.stat().st_mtime
                best = min(reports, key=lambda r: abs(pmt - datetime.strptime(r[1], "%Y-%m-%d").timestamp()))
                _, bdate = best
                plan[sym].append((p, sym_root / bdate, fix_pact(p.name), "datapack"))

        else:
            # 只有数据包没有报告（异常情况），按创建时间创建版本
            print(f"⚠️ {sym}: 只有数据包无报告，跳过")
            continue

    return plan

# ============================================================
# 步骤 3: 执行迁移
# ============================================================

def execute(plan):
    created = set()
    stats = {"moved": 0, "skipped": 0, "renamed": 0}

    for sym, actions in plan.items():
        for src, tdir, tname, kind in actions:
            tpath = tdir / tname

            # 已经就位
            if src == tpath:
                stats["skipped"] += 1
                continue

            # 目标目录
            if tdir not in created:
                tdir.mkdir(parents=True, exist_ok=True)
                created.add(tdir)

            # 避免覆盖
            final = tpath
            c = 1
            while final.exists():
                final = tdir / f"{tpath.stem}_{c}{tpath.suffix}"
                c += 1

            if src.parent == tdir:
                src.rename(final)
                stats["renamed"] += 1
            else:
                shutil.move(str(src), str(final))
                stats["moved"] += 1

    # 清理空目录
    cleaned = 0
    for root, dirs, files in os.walk(str(BASE_DIR), topdown=False):
        rp = Path(root)
        if "scripts" in rp.parts: continue
        if rp == BASE_DIR: continue
        if not any(rp.iterdir()):
            rp.rmdir()
            cleaned += 1

    print(f"移动: {stats['moved']}, 重命名: {stats['renamed']}, 跳过: {stats['skipped']}, 清理空目录: {cleaned}")

# ============================================================
# 步骤 4: 创建 index.json 和 latest
# ============================================================

def create_indexes():
    for sym_dir in sorted(BASE_DIR.iterdir()):
        if not sym_dir.is_dir(): continue
        if sym_dir.name == "scripts": continue

        versions = []
        for vd in sorted(sym_dir.iterdir()):
            if not vd.is_dir(): continue
            if not re.match(r"\d{4}-\d{2}-\d{2}", vd.name): continue
            reports = [f.name for f in vd.iterdir() if f.is_file() and is_report_file(f.name)]
            dp_m = vd / "data_pack_market.md"
            dp_r = vd / "data_pack_report.md"
            versions.append({
                "date": vd.name, "dir": vd.name,
                "report": reports,
                "data_pack_market": dp_m.name if dp_m.exists() else None,
                "data_pack_report": dp_r.name if dp_r.exists() else None,
            })

        if not versions: continue
        versions.sort(key=lambda v: v["date"])
        latest = versions[-1]

        company = versions[-1]["report"][0].split("_")[0] if versions[-1]["report"] else None
        index = {
            "symbol": sym_dir.name,
            "company": company,
            "latest": latest["date"],
            "versions": versions,
        }
        with open(sym_dir / "index.json", "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

        # latest 软链接
        link = sym_dir / "latest"
        if link.exists():
            if link.is_symlink(): link.unlink()
            elif link.is_dir(): shutil.rmtree(link)
        try:
            os.symlink(latest["dir"], str(link))
        except OSError:
            pass

    print(f"index.json + latest 已创建")

# ============================================================
# 步骤 5: 归档根目录杂物
# ============================================================

def archive_root():
    summary_dir = BASE_DIR / "汇总"
    scripts_dir = BASE_DIR / "scripts"
    summary_dir.mkdir(exist_ok=True)
    scripts_dir.mkdir(exist_ok=True)

    for fname in ROOT_ARCHIVE:
        src = BASE_DIR / fname
        if not src.exists(): continue
        dst = (scripts_dir if fname.endswith(".py") else summary_dir) / fname
        shutil.move(str(src), str(dst))
        print(f"归档: {src.name} -> {dst.parent.name}/")

    # 删除 .DS_Store
    ds = BASE_DIR / ".DS_Store"
    if ds.exists(): ds.unlink()

# ============================================================
# main
# ============================================================

def main():
    print("=== 步骤 1: 收集文件 ===")
    items = collect()
    print(f"  共 {len(items)} 个文件")

    print("=== 步骤 2: 构建迁移计划 ===")
    plan = build_plan(items)
    total = sum(len(v) for v in plan.values())
    print(f"  共 {len(plan)} 个 symbol, {total} 个迁移操作")

    print("=== 步骤 3: 执行迁移 ===")
    execute(plan)

    print("=== 步骤 4: 创建索引和 latest ===")
    create_indexes()

    print("=== 步骤 5: 归档根目录杂物 ===")
    archive_root()

    print("=== 完成 ===")

if __name__ == "__main__":
    main()