#!/usr/bin/env python3
"""
将 .claude/skills/ 下的 skill 文件批量迁移到思源笔记「规划/Skill库/」目录
通过 siyuan-sisyphus CLI 调用
"""

import subprocess
import json
import os

# 规划笔记本 ID
NOTEBOOK_ID = "20260502202849-uosjhi9"

# skill 分类映射
SKILL_CATEGORIES = {
    # 投资分析
    "turtle-investment-strategy": "投资分析",
    "fund-arbitrage": "投资分析",
    "bottom-trend-hunter": "投资分析",
    "earnings-hunter": "投资分析",
    "growth-stock-valuation": "投资分析",
    "industry-research-report": "投资分析",
    "industry-rotation-radar": "投资分析",
    "industry-stock-tracker": "投资分析",
    "initiation-of-coverage-or-deep-dive": "投资分析",
    "position-doctor": "投资分析",
    "short-term-trading": "投资分析",
    "st-stock-strategy": "投资分析",
    "stock-earnings-review": "投资分析",
    # 技术工具
    "mx-finance-data": "技术工具",
    "mx-finance-search": "技术工具",
    "mx-financial-assistant": "技术工具",
    "mx-macro-data": "技术工具",
    "mx-stocks-screener": "技术工具",
}

# 特殊处理：turtle-investment-strategy 有多个版本
TURTLE_VERSIONS = ["V1.0", "V1.1", "V1.2", "V1.3", "V1.4-legacy", "V2.0"]

SKILLS_DIR = "/Users/apple/Documents/分析报告/.claude/skills"


def run_cli(args_list):
    """运行 siyuan-sisyphus CLI 命令（不使用 shell）"""
    result = subprocess.run(args_list, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip()
        print(f"  ❌ Error: {err}")
        return None
    try:
        return json.loads(result.stdout)
    except:
        return {"raw": result.stdout}


def create_parent_doc(category, skill_name, description=""):
    """创建 skill 父文档（作为目录）"""
    path = f"/Skill库/{category}/{skill_name}"
    markdown = f"# {skill_name}\n\n{description}"
    args = [
        "siyuan-sisyphus", "document", "create",
        "--notebook", NOTEBOOK_ID,
        "--path", path,
        "--markdown", markdown,
        "--json"
    ]
    return run_cli(args)


def write_skill_doc(category, skill_name, version, content):
    """写入 skill 版本文档"""
    path = f"/规划/Skill库/{category}/{skill_name}/{version}"
    args = [
        "siyuan-sisyphus", "fs", "write",
        "--path", path,
        "--markdown", content,
        "--json"
    ]
    return run_cli(args)


def migrate_skill(skill_name, category, skill_file="SKILL.md", extra_files=None):
    """迁移单个 skill"""
    print(f"\n📦 Migrating: {skill_name} → {category}")

    # 创建父文档
    parent = create_parent_doc(category, skill_name)
    if not parent or not parent.get("success"):
        print(f"  ⚠️  Parent doc may already exist, continuing...")

    skill_path = os.path.join(SKILLS_DIR, skill_name, skill_file)
    if not os.path.exists(skill_path):
        print(f"  ❌ File not found: {skill_path}")
        return False

    with open(skill_path, 'r') as f:
        content = f.read()

    # 写入主版本
    result = write_skill_doc(category, skill_name, "V1.0", content)
    if result and result.get("success"):
        print(f"  ✅ V1.0 written ({len(content)} bytes)")
    else:
        print(f"  ❌ Failed to write V1.0")
        return False

    # 处理额外文件
    if extra_files:
        for extra_name, extra_file in extra_files.items():
            extra_path = os.path.join(SKILLS_DIR, skill_name, extra_file)
            if os.path.exists(extra_path):
                with open(extra_path, 'r') as f:
                    extra_content = f.read()
                result = write_skill_doc(category, skill_name, extra_name, extra_content)
                if result and result.get("success"):
                    print(f"  ✅ {extra_name} written ({len(extra_content)} bytes)")
                else:
                    print(f"  ⚠️  {extra_name} failed")

    return True


def migrate_turtle_strategy():
    """特殊处理 turtle-investment-strategy（多版本）"""
    skill_name = "turtle-investment-strategy"
    category = "投资分析"
    print(f"\n📦 Migrating: {skill_name} (multi-version) → {category}")

    # 父文档应该已创建
    for version in TURTLE_VERSIONS:
        version_file = f"{version}.md"
        version_path = os.path.join(SKILLS_DIR, skill_name, version_file)

        if not os.path.exists(version_path):
            print(f"  ⚠️  {version_file} not found, skipping")
            continue

        with open(version_path, 'r') as f:
            content = f.read()

        # 清理版本号中的特殊字符作为路径名
        doc_version = version.replace("-legacy", "")
        result = write_skill_doc(category, skill_name, doc_version, content)
        if result and result.get("success"):
            print(f"  ✅ {version} written ({len(content)} bytes)")
        else:
            print(f"  ❌ {version} failed")

    # 同时写入当前活跃版本 SKILL.md
    skill_path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    if os.path.exists(skill_path):
        with open(skill_path, 'r') as f:
            content = f.read()
        result = write_skill_doc(category, skill_name, "README", content)
        if result and result.get("success"):
            print(f"  ✅ README (SKILL.md) written ({len(content)} bytes)")


def migrate_top_level_skill():
    """迁移顶层 SKILL.md"""
    skill_path = os.path.join(SKILLS_DIR, "SKILL.md")
    if not os.path.exists(skill_path):
        print(f"\n⚠️  Top-level SKILL.md not found")
        return

    print(f"\n📦 Migrating: 基础策略 (top-level SKILL.md) → 通用")

    parent = create_parent_doc("通用", "基础策略")
    if not parent or not parent.get("success"):
        print(f"  ⚠️  Parent doc may already exist, continuing...")

    with open(skill_path, 'r') as f:
        content = f.read()

    result = write_skill_doc("通用", "基础策略", "V1.0", content)
    if result and result.get("success"):
        print(f"  ✅ V1.0 written ({len(content)} bytes)")
    else:
        print(f"  ❌ Failed to write V1.0")


def main():
    print("=" * 60)
    print("Skill 迁移脚本 - 从本地 .claude/skills/ 到思源笔记")
    print("=" * 60)

    # 1. 先处理 turtle-investment-strategy（多版本）
    migrate_turtle_strategy()

    # 2. 批量处理其他 skill
    for skill_name, category in SKILL_CATEGORIES.items():
        if skill_name == "turtle-investment-strategy":
            continue  # 已单独处理

        # 确定 skill 文件名（fund-arbitrage 是 skill.md，其他是 SKILL.md）
        skill_file = "skill.md" if skill_name == "fund-arbitrage" else "SKILL.md"

        # 检查是否有额外文件
        extra_files = {}
        if skill_name == "stock-earnings-review":
            extra_files = {"BUSINESS_LOGIC": "BUSINESS_LOGIC.md"}

        migrate_skill(skill_name, category, skill_file, extra_files)

    # 3. 迁移顶层 SKILL.md
    migrate_top_level_skill()

    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
