#!/usr/bin/env python3
"""
将 cb_api_verify.py 转换为可在聚宽研究环境中运行的 .ipynb 文件。
用 # %% 标记 cell 边界，通过 jqdata SDK 可直接执行。
"""
import json

cells = []
current_cell = []
current_is_md = False

with open('/Users/apple/Documents/分析报告/量化策略/因子检验/cb_api_verify.py', 'r') as f:
    for line in f:
        stripped = line.rstrip()
        if stripped.startswith('# %% [markdown]'):
            if current_cell:
                cells.append(('markdown' if current_is_md else 'code', '\n'.join(current_cell)))
            current_cell = []
            current_is_md = True
            continue
        elif stripped.startswith('# %%'):
            if current_cell:
                cells.append(('markdown' if current_is_md else 'code', '\n'.join(current_cell)))
            current_cell = []
            current_is_md = False
            continue
        current_cell.append(line.rstrip('\n'))

if current_cell:
    cells.append(('markdown' if current_is_md else 'code', '\n'.join(current_cell)))

nb_cells = []
for i, (ct, src) in enumerate(cells):
    nb_cells.append({
        "cell_type": ct,
        "metadata": {},
        "source": src.split('\n'),
        "id": f"cell{i}"
    })

notebook = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.8.0"}
    },
    "cells": nb_cells
}

out = '/Users/apple/Documents/分析报告/量化策略/因子检验/cb_api_verify.ipynb'
with open(out, 'w') as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f"已生成: {out}")
