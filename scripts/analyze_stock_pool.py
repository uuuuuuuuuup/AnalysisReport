"""
股票池深度分析脚本 v2
=====================
使用已验证的 mx-finance-data API + Markdown 解析。

用法：
    python3 scripts/analyze_stock_pool.py
"""

import asyncio
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加 mx-finance-data 脚本路径
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / ".claude" / "skills" / "mx-finance-data" / "scripts"),
)
from get_data import query_mx_finance_data

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# ── 待分析股票池 ──────────────────────────────────────
STOCK_POOL: List[Dict[str, str]] = [
    {"code": "600519", "name": "贵州茅台", "market": "A股", "type": "价值底仓", "sector": "白酒"},
    {"code": "000858", "name": "五粮液",   "market": "A股", "type": "价值底仓", "sector": "白酒"},
    {"code": "000568", "name": "泸州老窖", "market": "A股", "type": "价值底仓", "sector": "白酒"},
    {"code": "600809", "name": "山西汾酒", "market": "A股", "type": "价值底仓", "sector": "白酒"},
    {"code": "600887", "name": "伊利股份", "market": "A股", "type": "价值底仓", "sector": "乳业"},
    {"code": "02020", "name": "安踏体育", "market": "港股", "type": "价值底仓", "sector": "运动服饰"},
    {"code": "06862", "name": "海底捞",   "market": "港股", "type": "价值底仓", "sector": "餐饮"},
    {"code": "00151", "name": "中国旺旺", "market": "港股", "type": "价值底仓", "sector": "食品"},
    {"code": "688111", "name": "金山办公", "market": "A股", "type": "成长弹性", "sector": "SaaS"},
    {"code": "600132", "name": "重庆啤酒",   "market": "A股", "type": "价值底仓", "sector": "啤酒"},
    {"code": "603369", "name": "今世缘",     "market": "A股", "type": "价值底仓", "sector": "白酒"},
    {"code": "000333", "name": "美的集团",   "market": "A股", "type": "价值底仓", "sector": "家电"},
    {"code": "000651", "name": "格力电器",   "market": "A股", "type": "价值底仓", "sector": "家电"},
    {"code": "600690", "name": "海尔智家",   "market": "A股", "type": "价值底仓", "sector": "家电"},
    {"code": "300760", "name": "迈瑞医疗",   "market": "A股", "type": "成长弹性", "sector": "医疗器械"},
    {"code": "002653", "name": "海思科",     "market": "A股", "type": "成长弹性", "sector": "创新药"},
    {"code": "688266", "name": "泽璟制药",   "market": "A股", "type": "成长弹性", "sector": "创新药"},
    {"code": "300199", "name": "翰宇药业",   "market": "A股", "type": "成长弹性", "sector": "医药"},
    {"code": "002027", "name": "分众传媒",   "market": "A股", "type": "成长弹性", "sector": "广告传媒"},
    {"code": "603444", "name": "吉比特",     "market": "A股", "type": "成长弹性", "sector": "游戏"},
    {"code": "03998", "name": "波司登",         "market": "港股", "type": "价值底仓", "sector": "服装"},
    {"code": "06181", "name": "老铺黄金",       "market": "港股", "type": "价值底仓", "sector": "黄金珠宝"},
    {"code": "01209", "name": "华润万象生活",   "market": "港股", "type": "价值底仓", "sector": "物业管理"},
    {"code": "00220", "name": "统一企业中国",   "market": "港股", "type": "价值底仓", "sector": "食品饮料"},
    {"code": "01044", "name": "恒安国际",       "market": "港股", "type": "价值底仓", "sector": "卫生用品"},
    {"code": "00836", "name": "华润电力",       "market": "港股", "type": "价值底仓", "sector": "电力"},
    {"code": "02688", "name": "新奥能源",       "market": "港股", "type": "价值底仓", "sector": "燃气"},
    {"code": "00270", "name": "粤海投资",       "market": "港股", "type": "价值底仓", "sector": "水务"},
    {"code": "06823", "name": "香港电讯-SS",    "market": "港股", "type": "价值底仓", "sector": "电信"},
    {"code": "01882", "name": "海天国际",       "market": "港股", "type": "价值底仓", "sector": "工业"},
    {"code": "09896", "name": "名创优品",       "market": "港股", "type": "成长弹性", "sector": "零售"},
    {"code": "00700", "name": "腾讯控股",       "market": "港股", "type": "成长弹性", "sector": "互联网"},
    {"code": "09999", "name": "网易",           "market": "港股", "type": "成长弹性", "sector": "互联网"},
    {"code": "02400", "name": "心动公司",       "market": "港股", "type": "成长弹性", "sector": "游戏"},
    {"code": "03692", "name": "翰森制药",       "market": "港股", "type": "成长弹性", "sector": "创新药"},
    {"code": "02096", "name": "先声药业",       "market": "港股", "type": "成长弹性", "sector": "制药"},
    {"code": "01928", "name": "金沙中国",       "market": "港股", "type": "特殊",     "sector": "博彩"},
    {"code": "00027", "name": "银河娱乐",       "market": "港股", "type": "特殊",     "sector": "博彩"},
]


# ── Markdown 解析 ─────────────────────────────────────
def _safe_float(val: str) -> Optional[float]:
    """安全转换为浮点数，处理百分号、亿、万等"""
    if not val:
        return None
    s = val.strip().replace(",", "").replace("%", "").replace("+", "")
    # 处理 "1.23亿" "4567万"
    multiplier = 1.0
    if "万亿" in s:
        multiplier = 1e8
        s = s.replace("万亿", "")
    elif "亿" in s:
        multiplier = 1e8
        s = s.replace("亿", "")
    elif "万" in s:
        multiplier = 1e4
        s = s.replace("万", "")
    try:
        return float(s) * multiplier
    except ValueError:
        return None


def parse_md_table(md_text: str) -> Dict[str, List[float]]:
    """
    解析 get_data.py 输出的 markdown 表格。
    返回 {'指标名': [值列表按时间从近到远], ...}
    """
    result: Dict[str, List[float]] = {}
    lines = md_text.strip().split("\n")

    # 找表头行（第二行是列标题）
    header_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("|") and "---" not in line and i > 0:
            # 检查前一行是否是 ## 标题或空行
            header_idx = i
            break

    if header_idx < 0:
        return result

    # 解析列标题
    headers = [h.strip() for h in lines[header_idx].split("|")[1:-1]]
    # 第一列是股票标识，跳过
    period_headers = headers[1:]  # ['2026一季报', '2025年报', ...]

    # 解析数据行
    for i in range(header_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        if "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 2:
            continue

        metric_name = cells[0]
        values = []
        for v in cells[1:]:
            fv = _safe_float(v)
            if fv is not None:
                values.append(fv)

        if values:
            result[metric_name] = values

    return result


# ── 数据拉取 ──────────────────────────────────────────
async def fetch_stock_data(stock: dict) -> Dict[str, Any]:
    """拉取单只股票的财务数据并解析，含重试逻辑"""
    name = stock["name"]
    code = stock["code"]
    market = stock["market"]

    stock_ref = f"{name} {code}"
    if market == "港股":
        stock_ref = f"{name} HK{code}"

    result = {"code": code, "name": name, "market": market,
              "type": stock["type"], "sector": stock["sector"],
              "error": None, "data": {}}

    query = f"{stock_ref} 近3年 净资产收益率ROE 销售毛利率 资产负债率 营业收入 归属母公司股东的净利润 营业收入同比增长率 归属母公司股东的净利润同比增长率 经营活动现金流量净额"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            api_result = await query_mx_finance_data(query=query)

            if api_result.get("error"):
                err_msg = api_result["error"]
                # 503 限流 → 重试
                if "503" in err_msg or "频繁" in err_msg:
                    if attempt < max_retries - 1:
                        wait = (attempt + 1) * 3
                        time.sleep(wait)
                        continue
                result["error"] = err_msg[:150]
                return result

            md_path = api_result.get("md_path")
            if md_path and Path(md_path).exists():
                md_text = Path(md_path).read_text(encoding="utf-8")
                result["data"] = parse_md_table(md_text)
            else:
                result["error"] = "无 md 输出"
            return result

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 2)
                continue
            result["error"] = str(e)[:150]
            return result

    return result


# ── 评分引擎 ──────────────────────────────────────────
def score_stock(raw: Dict[str, Any]) -> Dict[str, Any]:
    """6维度评分"""
    data = raw.get("data", {})
    scores = {
        "code": raw["code"], "name": raw["name"],
        "market": raw["market"], "type": raw["type"], "sector": raw["sector"],
        "roe_score": 0, "quality_score": 0, "safety_score": 0,
        "growth_score": 0, "pricing_score": 0, "value_score": 0,
        "total": 0, "flags": [], "risk_flags": [], "error": raw.get("error"),
    }

    if raw.get("error"):
        return scores

    # ── 1. ROE 持续性 (0-10) ──
    roe_keys = [k for k in data if "ROE" in k.upper() or "净资产收益率" in k]
    roe_vals = []
    for k in roe_keys:
        for v in data[k]:
            if 0 < v < 500:  # ROE正常范围
                roe_vals.append(v)

    if roe_vals:
        # 去掉Q1单季数据偏差（如果第一个值明显小于后面的年度值）
        annual_roe = [v for v in roe_vals if v > 5]  # 年度ROE通常>5%
        if not annual_roe:
            annual_roe = roe_vals
        avg_roe = sum(annual_roe) / len(annual_roe)

        if avg_roe >= 25:
            scores["roe_score"] = 10
        elif avg_roe >= 20:
            scores["roe_score"] = 9
        elif avg_roe >= 15:
            scores["roe_score"] = 7
        elif avg_roe >= 12:
            scores["roe_score"] = 5
        elif avg_roe >= 10:
            scores["roe_score"] = 3
        else:
            scores["roe_score"] = 1

        # 趋势
        if len(annual_roe) >= 2:
            recent, older = annual_roe[0], annual_roe[-1]
            if older > 0:
                ratio = recent / older
                if ratio > 1.1:
                    scores["roe_score"] = min(10, scores["roe_score"] + 1)
                    scores["flags"].append(f"ROE↑({avg_roe:.0f}%)")
                elif ratio < 0.85:
                    scores["roe_score"] = max(1, scores["roe_score"] - 1)
                    scores["risk_flags"].append(f"ROE↓({avg_roe:.0f}%)")
    else:
        scores["roe_score"] = 5  # 无数据

    # ── 2. 盈利质量 (0-10) ──
    cf_keys = [k for k in data if "经营" in k and "现金流" in k]
    profit_keys = [k for k in data if ("净利润" in k and "归属" in k and "同比" not in k)]

    cf_vals = []
    for k in cf_keys:
        cf_vals.extend(data[k])
    profit_vals = []
    for k in profit_keys:
        profit_vals.extend(data[k])

    if cf_vals and profit_vals:
        # 对比相同时期的现金流和净利润
        ratios = []
        for i, (cf, pr) in enumerate(zip(cf_vals, profit_vals)):
            if pr and abs(pr) > 0:
                ratios.append(abs(cf) / abs(pr))

        if ratios:
            avg_ratio = sum(ratios) / len(ratios)
            if avg_ratio >= 1.2:
                scores["quality_score"] = 10
            elif avg_ratio >= 1.0:
                scores["quality_score"] = 8
            elif avg_ratio >= 0.8:
                scores["quality_score"] = 6
            elif avg_ratio >= 0.5:
                scores["quality_score"] = 4
            else:
                scores["quality_score"] = 2
        else:
            scores["quality_score"] = 5
    else:
        scores["quality_score"] = 5

    # ── 3. 财务安全 (0-10) ──
    debt_keys = [k for k in data if "资产负债率" in k]
    debt_vals = []
    for k in debt_keys:
        for v in data[k]:
            if 0 < v < 100:
                debt_vals.append(v)

    if debt_vals:
        avg_debt = sum(debt_vals) / len(debt_vals)
        if avg_debt < 15:
            scores["safety_score"] = 10
        elif avg_debt < 25:
            scores["safety_score"] = 9
        elif avg_debt < 35:
            scores["safety_score"] = 7
        elif avg_debt < 50:
            scores["safety_score"] = 5
        elif avg_debt < 65:
            scores["safety_score"] = 3
        else:
            scores["safety_score"] = 1
            scores["risk_flags"].append(f"高负债({avg_debt:.0f}%)")
    else:
        scores["safety_score"] = 5

    # ── 4. 增长记录 (0-10) ──
    rev_growth_keys = [k for k in data if "营收" in k and "同比" in k and "单季度" not in k]
    profit_growth_keys = [k for k in data if "净利" in k and "同比" in k and "单季度" not in k and "扣非" not in k]

    rev_growth_vals = []
    for k in rev_growth_keys:
        for v in data[k]:
            rev_growth_vals.append(v)

    profit_growth_vals = []
    for k in profit_growth_keys:
        for v in data[k]:
            profit_growth_vals.append(v)

    growth_score = 5
    if rev_growth_vals:
        avg_rev_g = sum(rev_growth_vals) / len(rev_growth_vals)
        if avg_rev_g > 25:
            growth_score += 2
        elif avg_rev_g > 15:
            growth_score += 1
        elif avg_rev_g < 0:
            growth_score -= 2

    if profit_growth_vals:
        avg_p_g = sum(profit_growth_vals) / len(profit_growth_vals)
        if avg_p_g > 25:
            growth_score += 3
        elif avg_p_g > 15:
            growth_score += 2
        elif avg_p_g > 10:
            growth_score += 1
        elif avg_p_g < 0:
            growth_score -= 2

    scores["growth_score"] = max(0, min(10, growth_score))
    if growth_score >= 8:
        scores["flags"].append("高增长")
    elif growth_score <= 3:
        scores["risk_flags"].append("增长弱")

    # ── 5. 定价权 (0-10) ──
    margin_keys = [k for k in data if "毛利率" in k and "净利率" not in k]
    margin_vals = []
    for k in margin_keys:
        for v in data[k]:
            if 0 < v < 100:
                margin_vals.append(v)

    if margin_vals:
        avg_margin = sum(margin_vals) / len(margin_vals)
        if avg_margin >= 80:
            scores["pricing_score"] = 10
        elif avg_margin >= 60:
            scores["pricing_score"] = 8
        elif avg_margin >= 45:
            scores["pricing_score"] = 7
        elif avg_margin >= 35:
            scores["pricing_score"] = 5
        elif avg_margin >= 25:
            scores["pricing_score"] = 3
        else:
            scores["pricing_score"] = 1

        # 稳定性
        if len(margin_vals) >= 2:
            if margin_vals[0] >= margin_vals[-1] * 0.98:
                scores["pricing_score"] = min(10, scores["pricing_score"] + 1)
                scores["flags"].append("毛利稳")
    else:
        scores["pricing_score"] = 5

    # ── 6. 估值 —— 用之前筛选时的PE数据，没有则给中性分 ──
    # 这里我们无法直接从指标数据中拿到PE，给之前手动查的PE做填充
    scores["value_score"] = 5  # 默认中性

    # ── 总分 ──
    scores["total"] = (
        scores["roe_score"]
        + scores["quality_score"]
        + scores["safety_score"]
        + scores["growth_score"]
        + scores["pricing_score"]
        + scores["value_score"]
    )
    return scores


# ── 主流程 ─────────────────────────────────────────────
async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"🔬 分析 {len(STOCK_POOL)} 只股票 (6维度评分) ...")
    print("=" * 75)

    # 分批并发（每批4只，间隔2秒，避免限流）
    batch_size = 4
    all_results = []
    errors = []

    for i in range(0, len(STOCK_POOL), batch_size):
        batch = STOCK_POOL[i : i + batch_size]
        tasks = [fetch_stock_data(s) for s in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, result in enumerate(results):
            stock = batch[j]
            if isinstance(result, Exception):
                err_entry = {"code": stock["code"], "name": stock["name"],
                             "market": stock["market"], "type": stock["type"],
                             "sector": stock["sector"], "error": str(result)}
                errors.append(err_entry)
                all_results.append(err_entry)
            else:
                all_results.append(result)

        done = min(i + batch_size, len(STOCK_POOL))
        print(f"  📡 {done}/{len(STOCK_POOL)}", flush=True)

        # 批次间延迟，避免限流
        if done < len(STOCK_POOL):
            time.sleep(2)

    # 评分
    print("\n📊 评分中 ...\n")
    scored = [score_stock(r) for r in all_results]
    scored.sort(key=lambda x: x["total"], reverse=True)

    # 输出结果表
    header = f"{'排名':<4} {'名称':<10} {'市场':<4} {'行业':<10} {'ROE':<4} {'质量':<4} {'安全':<4} {'增长':<4} {'定价':<4} {'估值':<4} {'总分':<5} {'亮点/风险'}"
    print(header)
    print("-" * 90)

    for rank, s in enumerate(scored, 1):
        total = s["total"]
        grade = "A" if total >= 35 else "B" if total >= 28 else "C" if total >= 20 else "D"

        extras = ""
        if s.get("flags"):
            extras += "+" + ",".join(s["flags"][:2])
        if s.get("risk_flags"):
            extras += " ⚠" + ",".join(s["risk_flags"][:2])
        if s.get("error") and not s.get("flags") and not s.get("risk_flags"):
            extras = f"❌{s['error'][:30]}"

        print(f"{rank:<4} {s['name']:<10} {s.get('market',''):<4} {s.get('sector',''):<10} "
              f"{s['roe_score']:<4} {s['quality_score']:<4} {s['safety_score']:<4} "
              f"{s['growth_score']:<4} {s['pricing_score']:<4} {s['value_score']:<4} "
              f"{total:<5} {grade:<2} {extras}")

    # 分类精选
    print("\n" + "=" * 75)
    print("🏆 精选推荐 (按 70%价值+30%成长 配比)")
    print("=" * 75)

    value_top = [s for s in scored if s.get("type") == "价值底仓" and s["total"] >= 25]
    growth_top = [s for s in scored if s.get("type") == "成长弹性" and s["total"] >= 25]
    special = [s for s in scored if s.get("type") == "特殊" and s["total"] >= 25]

    print(f"\n🔵 价值底仓 TOP 8:")
    for s in value_top[:8]:
        print(f"  {s['name']:<10} [{s['total']}分] {s.get('sector','')}")

    print(f"\n🟢 成长弹性 TOP 4:")
    for s in growth_top[:4]:
        print(f"  {s['name']:<10} [{s['total']}分] {s.get('sector','')}")

    if special:
        print(f"\n🟡 特殊行业:")
        for s in special:
            print(f"  {s['name']:<10} [{s['total']}分] {s.get('sector','')}")

    # 错误列表
    failed = [s for s in scored if s.get("error") and s["total"] == 0]
    if failed:
        print(f"\n⚠️ 数据拉取失败 ({len(failed)}只):")
        for s in failed:
            print(f"  {s['name']:<10} {s['error']}")

    # CSV 输出
    csv_path = OUTPUT_DIR / f"stock_analysis_{uuid.uuid4().hex[:8]}.csv"
    with open(csv_path, "w", encoding="utf-8-sig") as f:
        f.write("排名,代码,名称,市场,类型,行业,ROE持续性,盈利质量,财务安全,增长记录,定价权,估值,总分,亮点,风险,错误\n")
        for rank, s in enumerate(scored, 1):
            row = [
                str(rank), s["code"], s["name"], s.get("market", ""), s.get("type", ""),
                s.get("sector", ""),
                str(s["roe_score"]), str(s["quality_score"]), str(s["safety_score"]),
                str(s["growth_score"]), str(s["pricing_score"]), str(s["value_score"]),
                str(s["total"]),
                ";".join(s.get("flags", [])),
                ";".join(s.get("risk_flags", [])),
                s.get("error", ""),
            ]
            f.write(",".join(f'"{c}"' for c in row) + "\n")

    print(f"\n✅ CSV: {csv_path}")
    return scored


if __name__ == "__main__":
    asyncio.run(main())
