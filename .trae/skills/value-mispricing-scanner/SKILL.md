---
name: value-mispricing-scanner
description: 错杀好股扫描器。当用户想从A股+港股通全市场系统性找出"近期被错杀的低估值高质量公司"时调用此技能。通过L1价值+回撤初筛→L2综合评分→L3个股诊断（A股Top20），输出带评分的候选清单与诊断摘要。适用语句：帮我找被错杀的好公司、扫描低估值好股票、找非科技价值股候选、运行错杀扫描。
---

# 错杀好股扫描器 (Value Mispricing Scanner)

从 A股 + 港股通全市场自动扫描"被科技虹吸效应错杀的低估值高质量公司"，输出可直接复筛的候选清单。

## 触发条件

满足以下任意一条即触发本技能：
- 用户说"找被错杀的好公司""扫描低估值好股票""非科技价值股""运行错杀扫描"
- 用户提到"低PE/低PB + 近期大跌 + 质量好的标的"
- 用户希望系统性筛选 A股/港股通 中被市场冷落的价值候选

## 使用限制

- 每次扫描约需 **5~15 分钟**（主要耗时在 L2 批量财务查询和 L3 逐票诊断）
- L3 单票诊断**仅支持 A股**，港股候选无诊断摘要（仅有评分）
- 本工具不做历史回测，不预测涨跌；结果供人工复筛参考，不构成投资建议

## 运行方式

**必须在 skill 目录下用模块方式运行**（脚本用 `from scripts.xxx import` 相对导入）：

```bash
cd .claude/skills/value-mispricing-scanner
python3 -m scripts.scanner
```

可选参数：
```bash
python3 -m scripts.scanner --no-diagnosis   # 跳过L3诊断，加快速度（约2-3分钟）
python3 -m scripts.scanner --top N          # 只诊断Top N只A股（默认15）
python3 -m scripts.scanner --output DIR     # 指定输出目录
```

## 输出

结果保存至 `miaoxiang/value_mispricing_scanner/scan_{日期时间}.md`，格式：
- 汇总统计（各层漏斗数量）
- Top候选清单（按综合评分排序，含关键指标）
- A股Top候选的单票诊断摘要

## 注意事项

- **L1筛选器（selectSecurity）不支持**：PE历史分位、52周最高点回撤、ROE、资产负债率——这些留给人工复筛
- 近一年涨跌幅作为"近期被错杀"的代理指标（API支持），非精确52周回撤
- **科技行业排除**：selectSecurity 多条件叠加时行业排除易失效，脚本已在 Python 端用行业关键词兜底再过滤一遍
- **港股行业字段常返回"未知"**：港股 screener 不稳定返回行业，故港股的科技过滤较弱，且报告中港股行业列多为"未知"——港股候选建议人工核查行业与基本面
- **单季ROE**：L2 财务接口返回的 ROE 为单季度/混合口径值，仅作参考展示、不参与打分；年化ROE需人工复核
- L2财务健康检查仅覆盖A股（港股searchData解析不稳定，直接透传不做陷阱过滤）

## 示例调用（在对话中触发）

```
用法示例：
- "帮我跑一次错杀扫描"
- "用value-mispricing-scanner找一下被错杀的好公司"
- "扫描A股港股通里低估值高质量的股票"
```

触发后，Claude 应：
1. 告知用户开始扫描并预估耗时
2. 运行 `scripts/scanner.py`
3. 将输出文件内容展示给用户
4. 建议用户结合龟龟因子1A快筛进行人工复筛

---

## 脚本示例（供 Claude 直接调用）

```python
import asyncio
from pathlib import Path
from scripts.scanner import run_scan

async def main():
    output_path = await run_scan(
        output_dir=Path("miaoxiang/value_mispricing_scanner"),
        top_diagnosis=15,
        run_diagnosis=True,
    )
    print(f"扫描完成，结果保存至: {output_path}")

asyncio.run(main())
```
