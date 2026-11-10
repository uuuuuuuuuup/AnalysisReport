"""
value-mispricing-scanner: 主扫描逻辑

流程：
  L1 → selectSecurity 初筛（A股 + 港股通）
  L2 → searchData 批量财务健康检查（每批5只，并发3）
  L3 → 综合评分排序 + stock-analysis Top A股诊断
  输出 → Markdown 候选清单
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.get_data import (
    screen_stocks,
    get_financial_health_batch,
    diagnose_stock,
    _find_val,
    _to_float,
)

# ─────────────────────────────────────────────
# L1 选股 Query
# ─────────────────────────────────────────────

A_STOCK_QUERY = (
    "筛选A股，市净率低于2，市盈率TTM在3到50之间，近一年涨跌幅低于-20%，"
    "总市值大于50亿元，排除ST和*ST股票，"
    "排除半导体、集成电路、消费电子、计算机软件、互联网、人工智能、通信设备、游戏行业"
)

HK_STOCK_QUERY = (
    "筛选港股通标的，市净率低于2，市盈率TTM在3到40之间，近一年涨跌幅低于-20%，"
    "总市值大于30亿港元"
)

# Python 端兜底：科技行业关键词（selectSecurity 多条件叠加时行业排除易失效，故本地再过滤一遍）
TECH_SECTOR_KEYWORDS = [
    "半导体", "集成电路", "芯片", "消费电子", "电子元件", "软件", "计算机",
    "互联网", "人工智能", "通信设备", "游戏", "光学光电", "元件", "电子化学品",
]


def _is_tech_sector(sector: str) -> bool:
    """按行业名判断是否属于要排除的纯科技板块。"""
    if not sector:
        return False
    return any(kw in sector for kw in TECH_SECTOR_KEYWORDS)


# ─────────────────────────────────────────────
# 标准化与字段提取
# ─────────────────────────────────────────────

def _normalize_stock(row: Dict[str, str], market: str) -> Optional[Dict[str, Any]]:
    """
    将 selectSecurity 返回的一行标准化为内部 stock dict。
    使用模糊匹配处理带日期后缀的列名（如"市净率(倍) 2026.07.02"）。
    如果必要字段缺失则返回 None。
    """
    code = _find_val(row, "代码", "股票代码", "证券代码", "stockCode", "secCode")
    name = _find_val(row, "名称", "股票名称", "证券名称", "股票简称", "stockName")
    if not code or not name:
        return None

    sector = _find_val(row, "申万行业分类", "所属行业", "行业", "行业名称", "industry") or "未知"
    # PE：优先 TTM，再动态
    pe = _to_float(_find_val(row, "市盈率(TTM)", "PE(TTM)", "市盈率TTM"))
    if pe is None:
        pe = _to_float(_find_val(row, "市盈率(动)", "动态市盈率"))
    pb = _to_float(_find_val(row, "市净率"))
    cap = _to_float(_find_val(row, "总市值"))
    div = _to_float(_find_val(row, "股息率", "股利收益率"))
    # 1年涨跌幅：关键词匹配"区间涨跌幅"或"年涨跌幅"
    ytd = _to_float(_find_val(row, "区间涨跌幅", "近一年涨跌幅", "52周涨跌幅", "年涨跌幅"))

    if pe is None and pb is None:
        return None

    return {
        "code": code.strip(),
        "name": name.strip(),
        "market": market,
        "sector": sector,
        "pe": pe,
        "pb": pb,
        "cap_billion": cap,
        "dividend_yield": div,
        "ytd_change": ytd,
        "roe": None,
        "is_trap": False,
        "trap_reasons": [],
        "score": 0.0,
        "diagnosis": "",
    }


# ─────────────────────────────────────────────
# 评分逻辑
# ─────────────────────────────────────────────

def _score_stock(stock: Dict[str, Any]) -> float:
    """
    三维综合评分（0-10 分）：
    - 估值便宜度 45%：PB 越低得分越高
    - 盈利质量  25%：PE 越低得分越高（ROE 因接口口径不稳定，不参与打分）
    - 错杀深度  30%：近一年跌幅越大得分越高（L1 已确保基本面未彻底崩溃）
    """
    pb = stock.get("pb")
    pe = stock.get("pe")
    ytd = stock.get("ytd_change")  # 负值

    # 估值便宜度（PB）：PB=0→10, PB=1→7.5, PB=2→0（线性截断）
    if pb is not None and pb > 0:
        pb_score = max(0.0, 10.0 - pb * 5.0)
    else:
        pb_score = 5.0  # 未知时给中间分

    # 盈利质量（PE）：PE=5→9, PE=15→7, PE=30→4, PE=50→0
    if pe is not None and pe > 0:
        quality_score = max(0.0, 10.0 - pe * 0.2)
    else:
        quality_score = 3.0

    # 错杀深度（近一年跌幅）：跌 20%→4, 跌 35%→7, 跌 50%→10
    drawdown_score = 0.0
    if ytd is not None:
        drawdown_pct = abs(min(0.0, ytd))  # 只取下跌部分
        drawdown_score = min(10.0, drawdown_pct * 0.2)

    total = pb_score * 0.45 + quality_score * 0.25 + drawdown_score * 0.30
    return round(total, 2)


# ─────────────────────────────────────────────
# L2 批量财务健康过滤
# ─────────────────────────────────────────────

BATCH_SIZE = 5
L2_CONCURRENCY = 2  # 同时发出的批次数（searchData 较重，过高会被限频）


async def run_l2_filter(
    stocks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    对 L1 结果批量查询财务健康，回填 roe / is_trap / trap_reasons，
    过滤掉确定的价值陷阱。
    """
    # 只对 A股 做 L2（港股 searchData 解析不稳定）
    a_stocks = [s for s in stocks if s["market"] == "A股"]
    hk_stocks = [s for s in stocks if s["market"] != "A股"]

    print(f"\n[L2] 对 {len(a_stocks)} 只A股进行财务健康检查（每批{BATCH_SIZE}只，并发{L2_CONCURRENCY}）...")

    semaphore = asyncio.Semaphore(L2_CONCURRENCY)

    async def process_batch(batch: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        async with semaphore:
            simple_batch = [{"code": s["code"], "name": s["name"]} for s in batch]
            r = await get_financial_health_batch(simple_batch)
            # 空结果重试一次（应对偶发限频/超时）
            if not r:
                await asyncio.sleep(1.5)
                r = await get_financial_health_batch(simple_batch)
            return r

    batches = [a_stocks[i: i + BATCH_SIZE] for i in range(0, len(a_stocks), BATCH_SIZE)]
    tasks = [process_batch(b) for b in batches]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    health_map: Dict[str, Dict[str, Any]] = {}
    for r in results:
        if isinstance(r, dict):
            health_map.update(r)

    # 回填财务健康数据
    for s in a_stocks:
        h = health_map.get(s["code"])
        if h:
            s["roe"] = h.get("roe")
            s["is_trap"] = h.get("is_trap", False)
            s["trap_reasons"] = h.get("trap_reasons", [])

    # 过滤确定陷阱
    passed_a = [s for s in a_stocks if not s["is_trap"]]
    filtered_count = len(a_stocks) - len(passed_a)
    matched = len(health_map)
    print(f"[L2] 财务数据匹配 {matched}/{len(a_stocks)} 只，过滤 {filtered_count} 只价值陷阱，A股剩余 {len(passed_a)} 只")

    # 港股直接透传（不过滤）
    return passed_a + hk_stocks


# ─────────────────────────────────────────────
# L3 评分 + 诊断
# ─────────────────────────────────────────────

DIAGNOSIS_CONCURRENCY = 3
DIAGNOSIS_DELAY = 1.0  # 每次诊断请求间隔（秒），避免限频


async def run_l3(
    stocks: List[Dict[str, Any]],
    top_n: int = 15,
    run_diagnosis: bool = True,
) -> List[Dict[str, Any]]:
    """评分排序，对 Top A股做单票诊断。"""
    # 评分
    for s in stocks:
        s["score"] = _score_stock(s)
    stocks.sort(key=lambda x: x["score"], reverse=True)

    if not run_diagnosis:
        return stocks

    # 仅对 Top N 的 A股做诊断
    a_top = [s for s in stocks if s["market"] == "A股"][:top_n]
    print(f"\n[L3] 对 Top {len(a_top)} 只A股进行单票诊断...")

    semaphore = asyncio.Semaphore(DIAGNOSIS_CONCURRENCY)

    async def diagnose_one(stock: Dict[str, Any], idx: int) -> None:
        async with semaphore:
            if idx > 0:
                await asyncio.sleep(DIAGNOSIS_DELAY)
            print(f"  诊断 [{idx+1}/{len(a_top)}] {stock['name']} ({stock['code']})")
            text = await diagnose_stock(stock["name"], stock["code"])
            stock["diagnosis"] = text[:800] if len(text) > 800 else text  # 截取前 800 字

    tasks = [diagnose_one(s, i) for i, s in enumerate(a_top)]
    await asyncio.gather(*tasks)

    return stocks


# ─────────────────────────────────────────────
# 报告生成
# ─────────────────────────────────────────────

def _fmt_val(v: Optional[float], suffix: str = "", decimals: int = 1) -> str:
    if v is None:
        return "--"
    return f"{v:.{decimals}f}{suffix}"


def generate_report(
    stocks: List[Dict[str, Any]],
    l1_count: int,
    l2_count: int,
    scan_time: str,
) -> str:
    total = len(stocks)
    a_count = sum(1 for s in stocks if s["market"] == "A股")
    hk_count = total - a_count

    lines = [
        f"# 错杀好股扫描报告",
        f"",
        f"**扫描时间**: {scan_time}",
        f"**免责声明**: 本报告仅供参考，不构成投资建议，请结合自身判断使用",
        f"",
        f"---",
        f"",
        f"## 漏斗汇总",
        f"",
        f"| 阶段 | 数量 | 说明 |",
        f"|------|------|------|",
        f"| L1 初筛 | {l1_count} 只 | PB<2 + PE 3~50 + 近一年跌幅>20% + 非科技 + 非ST |",
        f"| L2 财务过滤 | {l2_count} 只 | 排除A股价值陷阱（港股直接透传）|",
        f"| 最终候选 | {total} 只 | A股 {a_count} 只 + 港股通 {hk_count} 只 |",
        f"",
        f"---",
        f"",
        f"## 候选清单（按综合评分排序）",
        f"",
        f"| 排名 | 市场 | 代码 | 名称 | 行业 | 综合分 | PB | PE(TTM) | 近1年跌幅 | 单季ROE* | 股息率 | 市值(亿) |",
        f"|------|------|------|------|------|--------|-----|---------|-----------|----------|--------|---------|",
    ]

    for i, s in enumerate(stocks, 1):
        ytd = s.get("ytd_change")
        ytd_str = f"{ytd:.1f}%" if ytd is not None else "--"
        roe_str = _fmt_val(s.get("roe"), "%")
        div_str = _fmt_val(s.get("dividend_yield"), "%")
        cap_str = _fmt_val(s.get("cap_billion"), decimals=0)
        lines.append(
            f"| {i} | {s['market']} | {s['code']} | {s['name']} | {s['sector']} "
            f"| {_fmt_val(s.get('score'), decimals=2)} "
            f"| {_fmt_val(s.get('pb'))} "
            f"| {_fmt_val(s.get('pe'))} "
            f"| {ytd_str} "
            f"| {roe_str} "
            f"| {div_str} "
            f"| {cap_str} |"
        )

    lines.append("")
    lines.append("> \\* 单季ROE 为最新单季度净资产收益率（接口口径），仅供参考、不参与打分；年化 ROE 请人工复核。")

    # 价值陷阱备注
    trapped = [s for s in stocks if s.get("trap_reasons")]
    if trapped:
        lines += [
            f"",
            f"> **备注**：以下股票被标记为有陷阱风险但仍在列（触发条件 < 2条）：",
        ]
        for s in trapped:
            if not s["is_trap"]:
                lines.append(f"> - {s['name']}（{s['code']}）：{', '.join(s['trap_reasons'])}")

    # A股个股诊断
    diag_stocks = [s for s in stocks if s.get("diagnosis")]
    if diag_stocks:
        lines += [
            f"",
            f"---",
            f"",
            f"## A股候选单票诊断摘要",
            f"",
            f"*（由东方财富 AI 诊断生成，仅供参考，不构成投资建议）*",
            f"",
        ]
        for s in diag_stocks:
            rank = next((i + 1 for i, x in enumerate(stocks) if x["code"] == s["code"]), "?")
            lines += [
                f"### {rank}. {s['name']}（{s['code']}）",
                f"**综合得分**: {_fmt_val(s.get('score'), decimals=2)} | **PB**: {_fmt_val(s.get('pb'))} | "
                f"**PE**: {_fmt_val(s.get('pe'))} | **近1年涨跌**: {_fmt_val(s.get('ytd_change'), '%')}",
                f"",
                s["diagnosis"],
                f"",
                f"---",
                f"",
            ]

    lines += [
        f"## 下一步建议",
        f"",
        f"1. **人工快筛**：对候选清单逐一做龟龟因子1A快筛（五分钟一票否决）",
        f'2. **确认近期走势**：验证是否真的是"近期被错杀"而非长期价值陷阱（查周/月K线）',
        f"3. **财务复核**：重点看ROE趋势、经营现金流、商誉规模（尤其港股候选）",
        f"4. **深度研究**：通过 initiation-of-coverage-or-deep-dive 对Top标的出完整研报",
        f"",
        f"*扫描工具版本 v1.0 | 数据来源：东方财富*",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

async def run_scan(
    output_dir: Path = Path("miaoxiang/value_mispricing_scanner"),
    top_diagnosis: int = 15,
    run_diagnosis: bool = True,
) -> str:
    """
    完整扫描流程。

    Returns:
        输出 Markdown 文件路径
    """
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── L1 ──
    print("=" * 50)
    print("L1: 开始初筛（A股 + 港股通）")
    print("=" * 50)

    a_rows, hk_rows = await asyncio.gather(
        screen_stocks(A_STOCK_QUERY, "A股"),
        screen_stocks(HK_STOCK_QUERY, "港股"),
    )

    a_stocks_raw = [_normalize_stock(r, "A股") for r in a_rows]
    hk_stocks_raw = [_normalize_stock(r, "港股通") for r in hk_rows]
    all_raw = [s for s in a_stocks_raw + hk_stocks_raw if s is not None]

    # Python 端兜底过滤科技行业
    all_l1 = [s for s in all_raw if not _is_tech_sector(s["sector"])]
    tech_removed = len(all_raw) - len(all_l1)
    if tech_removed:
        print(f"[L1] Python兜底过滤掉 {tech_removed} 只科技行业股票")
    l1_count = len(all_l1)
    print(f"\n[L1] 合并后共 {l1_count} 只候选（A股 {len([s for s in all_l1 if s['market']=='A股'])} + 港股通 {len([s for s in all_l1 if s['market']!='A股'])}）")

    if l1_count == 0:
        print("[警告] L1 未获得任何候选股，请检查 API 或网络")
        return ""

    # ── L2 ──
    print("\n" + "=" * 50)
    print("L2: 财务健康过滤")
    print("=" * 50)

    l2_stocks = await run_l2_filter(all_l1)
    l2_count = len(l2_stocks)

    # ── L3 ──
    print("\n" + "=" * 50)
    print(f"L3: 综合评分 + Top{top_diagnosis} A股诊断")
    print("=" * 50)

    final_stocks = await run_l3(l2_stocks, top_n=top_diagnosis, run_diagnosis=run_diagnosis)

    # ── 生成报告 ──
    report = generate_report(final_stocks, l1_count, l2_count, scan_time)

    filename = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    output_path = output_dir / filename
    output_path.write_text(report, encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"扫描完成！结果保存至: {output_path}")
    print(f"共 {len(final_stocks)} 只候选（A股 {len([s for s in final_stocks if s['market']=='A股'])} + 港股通 {len([s for s in final_stocks if s['market']!='A股'])}）")
    print(f"{'='*50}")

    return str(output_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="错杀好股扫描器")
    parser.add_argument("--no-diagnosis", action="store_true", help="跳过L3单票诊断（加快速度）")
    parser.add_argument("--top", type=int, default=15, help="诊断Top N只A股（默认15）")
    parser.add_argument("--output", type=str, default="miaoxiang/value_mispricing_scanner", help="输出目录")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        run_scan(
            output_dir=Path(args.output),
            top_diagnosis=args.top,
            run_diagnosis=not args.no_diagnosis,
        )
    )
