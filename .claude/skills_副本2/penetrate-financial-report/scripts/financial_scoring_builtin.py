# -*- coding: utf-8 -*-
"""
【已废弃】财务打分模型数据读取（内置数据版）

自 v3.0 起，penetrate-financial-report skill 强制要求用户上传
「财务打分模型.xlsx」，全A样本数据（中位数规律、个股5大打分指标、分位数、
wind一致预期）全部从用户上传文件的「输出」sheet 提取，不再使用内置 JSON 数据，
也不从网络摘取。

内置 JSON 数据（data/全A样本分布数据.json）已删除。

请改用:
    python financial_scoring.py --model "用户上传的财务打分模型.xlsx"

公司简称获取方式（二选一）:
  1. 在「输出」sheet 的 B4 格填入公司简称，脚本自动读取；
  2. 通过 --company 参数显式指定。

若用户未上传有效的财务打分模型.xlsx，则不生成全A样本对比部分，并提示用户上传。
"""

import sys


def main():
    print("=" * 70, file=sys.stderr)
    print("【已废弃】financial_scoring_builtin.py 不再使用内置 JSON 数据。", file=sys.stderr)
    print("自 v3.0 起，全A样本数据强制来自用户上传的「财务打分模型.xlsx」。", file=sys.stderr)
    print("", file=sys.stderr)
    print("请上传「财务打分模型.xlsx」并改用:", file=sys.stderr)
    print("    python financial_scoring.py --model \"财务打分模型.xlsx\"", file=sys.stderr)
    print("", file=sys.stderr)
    print("使用方式:", file=sys.stderr)
    print("  1. 在「输出」sheet 的 B4 格填入公司简称，其余由 Excel 公式自动生成;", file=sys.stderr)
    print("  2. 脚本只提取「输出」sheet 的数据，不遍历年度/季度 sheet;", file=sys.stderr)
    print("  3. 也可通过 --company 参数显式指定公司简称。", file=sys.stderr)
    print("", file=sys.stderr)
    print("若未上传有效的财务打分模型.xlsx，将不生成全A样本对比部分。", file=sys.stderr)
    print("全A样本数据不从网络摘取，全部来自用户上传文件。", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
