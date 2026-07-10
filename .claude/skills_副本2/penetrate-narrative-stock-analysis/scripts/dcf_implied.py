#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
穿透叙事 DCF 隐含天花板反算工具 (v2.4.0 — 2035稳态期默认版)

模型假设（v2.4.0变更：稳态期默认2035年）：
  - 前3年（t=1,2,3）：直接使用分析师一致预期业绩 E1, E2, E3
  - 第4年至稳态年：从 E3 起匀速（等比）增长至终局利润 L
    · 增长年数 = steady_year - (base_year + 3)
    · 默认 base_year=2025, steady_year=2035 → 增长年数=7（2029-2035）
  - 稳态年+1起：L 永续稳定，不给予永续增长率（g=0）
  - 折现率三档：r = 8%、10%、12%
  - 根据当前市值，反算股价隐含的终局利润 L

DCF 公式（净利润 ≈ 权益现金流，忽略营运资本变动）：
    市值 = Σ_{t=1}^{3} E_t / (1+r)^t
         + Σ_{t=4}^{3+N} E_3·(1+g)^(t-3) / (1+r)^t   其中 g = (L/E3)^(1/N) - 1, N=增长年数
         + (L / r) / (1+r)^(3+N)                       永续期现值

当 L < E3 时（隐含业绩下滑），g < 0，公式仍成立（匀速衰减至 L）。

用法:
    # 核心：反算隐含终局利润（三档折现率同时输出，默认2035稳态）
    python dcf_implied.py implied --cap 1000 --e1 10 --e2 11 --e3 12

    # 指定稳态年（如用户要求2040稳态）
    python dcf_implied.py implied --cap 1000 --e1 10 --e2 11 --e3 12 --steady-year 2040

    # 正算：给定终局利润，算合理市值与动态PE
    python dcf_implied.py calc --l 50 --e1 10 --e2 11 --e3 12 --r 10

    # 交互式：仅给市值和三年业绩，输出完整分析表
    python dcf_implied.py analyze --cap 1000 --e1 10 --e2 11 --e3 12

    # 敏感性分析：不同终局利润对应的市值
    python dcf_implied.py sensitivity --e1 10 --e2 11 --e3 12 --r 10

    # 券商目标价反算：批量反算多个目标价隐含的L（v2.4.0新增）
    python dcf_implied.py brokers --e1 10 --e2 11 --e3 12 --shares 66.37 \
        --prices 48.67,64.86,72.8,73.4,79.76,83,87.21,88 \
        --names "当前股价,最低目标,高盛,中金,机构均值,摩根士丹利,国泰海通,瑞银"
"""
import argparse

# 三档折现率
R_GRID = [8, 10, 12]

# v2.4.0 默认参数
DEFAULT_BASE_YEAR = 2025   # E0对应年份（最近已完成财年）
DEFAULT_STEADY_YEAR = 2035 # 稳态期起始年（用户要求默认2035）


def get_growth_years(base_year: int = DEFAULT_BASE_YEAR,
                     steady_year: int = DEFAULT_STEADY_YEAR) -> int:
    """计算增长年数 = 稳态年 - (基准年 + 3)。

    例：base_year=2025, steady_year=2035 → 增长年数=7（2029-2035共7年）
    """
    n = steady_year - (base_year + 3)
    if n < 1:
        raise ValueError(f"增长年数={n}，必须≥1。请检查 base_year={base_year}, steady_year={steady_year}")
    return n


def fair_value(L: float, e1: float, e2: float, e3: float, r_pct: float,
               growth_years: int = None) -> float:
    """正算：给定终局利润 L、前3年业绩、折现率 r(%)，返回合理市值。

    假设净利润 ≈ 权益现金流。第4年至第(3+N)年从 E3 等比增长至 L，之后永续稳定。
    N=growth_years，默认按2035稳态计算（base_year=2025时N=7）。
    """
    if r_pct <= 0:
        raise ValueError("折现率必须为正")
    if growth_years is None:
        growth_years = get_growth_years()
    r = r_pct / 100.0
    pv = 0.0
    # 前3年
    pv += e1 / (1 + r) ** 1
    pv += e2 / (1 + r) ** 2
    pv += e3 / (1 + r) ** 3
    # 第4年至第(3+N)年：从E3等比增长至L
    if e3 > 0 and L > 0 and abs(L - e3) > 1e-9:
        g = (L / e3) ** (1.0 / growth_years) - 1.0
        for t in range(4, 4 + growth_years):
            profit_t = e3 * (1 + g) ** (t - 3)
            pv += profit_t / (1 + r) ** t
    elif e3 > 0 and L > 0:  # L == E3，g=0
        for t in range(4, 4 + growth_years):
            pv += e3 / (1 + r) ** t
    # 永续期（第(3+N+1)年起，L稳定不变）
    pv += (L / r) / (1 + r) ** (3 + growth_years)
    return pv


def implied_ceiling(cap: float, e1: float, e2: float, e3: float, r_pct: float,
                    growth_years: int = None) -> float:
    """反算：给定市值、前3年业绩、折现率 r(%)，返回隐含终局利润 L。

    用二分法求解。L 的范围 [0, 上界]，上界取一个足够大的值。
    """
    if growth_years is None:
        growth_years = get_growth_years()
    r = r_pct / 100.0
    # 上界估计：仅永续期就支撑市值时 L = cap * r * (1+r)^(3+N)，放大10倍确保覆盖
    hi = max(cap * r * (1 + r) ** (3 + growth_years) * 10, e3 * 100, 1000.0)
    lo = 0.0
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if fair_value(mid, e1, e2, e3, r_pct, growth_years) < cap:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def implied_growth_rate(L: float, e3: float, growth_years: int = None) -> float:
    """计算第4年至稳态年的隐含复合增速 g(%)。"""
    if growth_years is None:
        growth_years = get_growth_years()
    if e3 <= 0 or L <= 0:
        return float('nan')
    return ((L / e3) ** (1.0 / growth_years) - 1.0) * 100.0


def verify_forward_backward(cap, e1, e2, e3, growth_years=None):
    """v2.4.0新增：反算-正算反向验证，误差应<5%。

    这是数据质量红线：反算出的L必须能正算回原市值。
    """
    if growth_years is None:
        growth_years = get_growth_years()
    print("反向验证（反算L → 正算市值，误差应<5%）:")
    for r in R_GRID:
        L = implied_ceiling(cap, e1, e2, e3, r, growth_years)
        fv = fair_value(L, e1, e2, e3, r, growth_years)
        err = abs(fv - cap) / cap * 100 if cap > 0 else 0
        status = "[通过]" if err < 5 else "[未通过]"
        print(f"  r={r}%: 反算L={L:.2f}亿 → 正算市值={fv:.1f}亿 vs 实际{cap:.1f}亿, 误差={err:.3f}% {status}")
    print()


def verify_L_vs_scenario(L_dict, scenario_L_list, scenario_names=None):
    """v2.4.0新增：验证反算/正算所用L值是否在情景表四档L区间内。

    防止"把L=820亿的正算结果误当成L=539亿的结果"这类错误。
    L_dict: {"r=10%": 490.6, "券商均值": 897, ...}
    scenario_L_list: [172, 360, 755, 1344] 四档情景L
    """
    if scenario_names is None:
        scenario_names = ["保守", "基准", "乐观", "极乐观"]
    print("L值与情景表交叉验证（v2.4.0数据质量红线）:")
    print(f"  情景表四档L: {dict(zip(scenario_names, scenario_L_list))}")
    min_L, max_L = min(scenario_L_list), max(scenario_L_list)
    for label, L in L_dict.items():
        if min_L <= L <= max_L:
            # 找到最接近的情景档
            closest = min(scenario_L_list, key=lambda x: abs(x - L))
            closest_name = scenario_names[scenario_L_list.index(closest)]
            print(f"  {label}: L={L:.1f}亿 -> 在区间[{min_L}, {max_L}]内, 最接近{closest_name}档({closest}亿) [OK]")
        else:
            print(f"  {label}: L={L:.1f}亿 -> 超出情景区间[{min_L}, {max_L}] [WARN] 需检查正算L是否对应加权L")
    print()


def fmt(x, suffix="", width=10, prec=1):
    if x is None or (isinstance(x, float) and x != x):  # NaN
        return f"{'N/A':>{width}}"
    return f"{x:> {width}.{prec}f}{suffix}"


def cmd_implied(args):
    """反算隐含终局利润（核心功能，三档折现率同时输出）。"""
    gy = get_growth_years(args.base_year, args.steady_year)
    print("=" * 80)
    print("DCF 反算：股价隐含的终局利润预期")
    print("=" * 80)
    print(f"当前市值: {args.cap:.1f} 亿")
    print(f"未来3年一致预期: E1={args.e1}, E2={args.e2}, E3={args.e3} 亿")
    print(f"稳态年: {args.steady_year} (基准年{args.base_year}+3={args.base_year+3}, 增长{gy}年)")
    print(f"假设: 第4-{3+gy}年从E3匀速增长至终局L，第{4+gy}年起永续稳定(g=0)")
    print("-" * 80)
    print(f"{'折现率r':>10} | {'隐含终局L':>12} | {'L/E3倍数':>10} | {'隐含增速g':>10} | {'动态PE(E1)':>12}")
    print("-" * 80)
    for r in R_GRID:
        L = implied_ceiling(args.cap, args.e1, args.e2, args.e3, r, gy)
        ratio = L / args.e3 if args.e3 > 0 else float('nan')
        g = implied_growth_rate(L, args.e3, gy)
        pe1 = args.cap / args.e1 if args.e1 > 0 else float('nan')
        print(f"{r:>8}%  | {L:>10.1f} 亿 | {ratio:>8.2f}x | {g:>8.1f}% | {pe1:>10.1f}x")
    print("-" * 80)
    # v2.4.0 反向验证
    verify_forward_backward(args.cap, args.e1, args.e2, args.e3, gy)
    print("解读要点:")
    print("  1. 隐含终局L vs 公司能够触达的理论业绩空间测算 → 判断高估/低估")
    print("  2. L/E3倍数 > 1 表示市场预期增长，< 1 表示预期下滑")
    print("  3. 三档折现率给出区间，r=8%偏乐观(低协方差资产)，r=12%偏谨慎(高风险)")
    print("  4. 与公司历史业绩增速、行业增速对照，判断隐含预期是否合理")


def cmd_calc(args):
    """正算：给定终局利润L，算合理市值与动态PE。"""
    gy = get_growth_years(args.base_year, args.steady_year)
    fv = fair_value(args.l, args.e1, args.e2, args.e3, args.r, gy)
    g = implied_growth_rate(args.l, args.e3, gy)
    pe1 = fv / args.e1 if args.e1 > 0 else float('nan')
    print(f"输入: 终局L={args.l}亿, E1={args.e1}, E2={args.e2}, E3={args.e3}, r={args.r}%")
    print(f"  稳态年={args.steady_year}, 增长{gy}年")
    print(f"  → 合理市值 = {fv:.1f} 亿")
    print(f"  → 对应动态PE(E1) = {pe1:.1f}x")
    print(f"  → 第4-{3+gy}年隐含复合增速 g = {g:.1f}%/年")
    # v2.4.0 提醒：正算所用L须与情景表对应
    print(f"  [提醒] 请核验L={args.l}亿是否为情景表四档L之一或加权L，避免正算-反算L不匹配")


def cmd_analyze(args):
    """完整分析：反算+解读。"""
    cmd_implied(args)
    gy = get_growth_years(args.base_year, args.steady_year)
    print()
    print("=" * 80)
    print("进一步分析指引")
    print("=" * 80)
    for r in R_GRID:
        L = implied_ceiling(args.cap, args.e1, args.e2, args.e3, r, gy)
        ratio = L / args.e3 if args.e3 > 0 else 0
        print(f"  [r={r}%] 隐含终局L={L:.1f}亿 (E3的{ratio:.2f}倍)")
        if ratio < 0.5:
            print(f"         ⚠ L<E3×0.5，市场预期业绩深度下滑，若理论业绩空间支撑则可能低估")
        elif ratio < 1:
            print(f"         ℹ L<E3，市场预期业绩下滑，需判断下滑幅度是否过度")
        elif ratio < 2:
            print(f"         ℹ L≈E3~2×E3，市场预期温和增长")
        elif ratio < 5:
            print(f"         ℹ L=2~5×E3，市场预期较高增长，需验证天花板可达性")
        elif ratio < 10:
            print(f"         ⚠ L=5~10×E3，市场预期高增长，叙事已较饱满")
        else:
            print(f"         ⚠ L>10×E3，市场预期极高增长，叙事打满，透支风险大")


def cmd_sensitivity(args):
    """敏感性分析：不同终局利润对应的市值。"""
    gy = get_growth_years(args.base_year, args.steady_year)
    print(f"敏感性分析：不同终局利润L对应的合理市值 (r={args.r}%, 稳态{args.steady_year}, 增长{gy}年)")
    print(f"输入: E1={args.e1}, E2={args.e2}, E3={args.e3}")
    print("-" * 60)
    print(f"{'终局L(亿)':>10} | {'L/E3':>8} | {'市值(亿)':>10} | {'动态PE':>8}")
    print("-" * 60)
    ratios = [0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0]
    for ratio in ratios:
        L = args.e3 * ratio
        fv = fair_value(L, args.e1, args.e2, args.e3, args.r, gy)
        pe1 = fv / args.e1 if args.e1 > 0 else 0
        print(f"{L:>10.1f} | {ratio:>6.1f}x | {fv:>10.1f} | {pe1:>6.1f}x")


def cmd_brokers(args):
    """v2.4.0新增：批量反算各券商目标价隐含的终局利润L。

    回答用户核心需求：对比各券商目标价隐含的市场空间预期。
    """
    gy = get_growth_years(args.base_year, args.steady_year)
    prices = [float(x) for x in args.prices.split(',')]
    names = args.names.split(',') if args.names else [f"目标价{i+1}" for i in range(len(prices))]
    if len(names) != len(prices):
        names = names[:len(prices)] if len(names) > len(prices) else names + [f"目标价{i+1}" for i in range(len(names), len(prices))]

    print("=" * 110)
    print(f"各券商目标价隐含终局利润L对比（稳态{args.steady_year}, 增长{gy}年）")
    print(f"输入: E1={args.e1}, E2={args.e2}, E3={args.e3}, 总股本={args.shares}亿股")
    print("=" * 110)
    print(f"{'券商/场景':<20} | {'目标价':>8} | {'市值(亿)':>8} | {'r=8% L':>8} | {'r=10% L':>8} | {'r=12% L':>8} | {'L/E3(10%)':>9}")
    print("-" * 110)
    for name, price in zip(names, prices):
        cap = price * args.shares
        L8 = implied_ceiling(cap, args.e1, args.e2, args.e3, 8, gy)
        L10 = implied_ceiling(cap, args.e1, args.e2, args.e3, 10, gy)
        L12 = implied_ceiling(cap, args.e1, args.e2, args.e3, 12, gy)
        ratio10 = L10 / args.e3 if args.e3 > 0 else 0
        print(f"{name:<20} | {price:>6.2f}元 | {cap:>6.0f} | {L8:>6.1f}亿 | {L10:>6.1f}亿 | {L12:>6.1f}亿 | {ratio10:>7.2f}x")
    print("-" * 110)
    print("解读要点:")
    print("  1. 对比各券商目标价隐含L与公司能够触达的理论业绩空间加权L → 判断券商预期合理性")
    print("  2. L/E3(10%) > 5 表示券商目标价隐含「叙事打满」预期，需重大催化剂方能支撑")
    print("  3. 外资投行 vs 国内券商目标价差异 → 反映对出海空间与集采压力的不同假设")


def main():
    parser = argparse.ArgumentParser(
        description="穿透叙事 DCF 隐含天花板反算工具 (v2.4.0 — 2035稳态期默认版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    # 公共参数
    common_base = lambda p: (
        p.add_argument("--base-year", type=int, default=DEFAULT_BASE_YEAR,
                       help=f"E0对应年份（默认{DEFAULT_BASE_YEAR}）"),
        p.add_argument("--steady-year", type=int, default=DEFAULT_STEADY_YEAR,
                       help=f"稳态期起始年（默认{DEFAULT_STEADY_YEAR}，v2.4.0变更）"),
        p
    )[-1]

    # implied: 反算隐含终局利润
    p1 = common_base(sub.add_parser("implied", help="反算：由市值+前3年业绩 → 隐含终局利润L（三档r）"))
    p1.add_argument("--cap", type=float, required=True, help="当前市值（亿元）")
    p1.add_argument("--e1", type=float, required=True, help="第1年一致预期净利润（亿元）")
    p1.add_argument("--e2", type=float, required=True, help="第2年一致预期净利润（亿元）")
    p1.add_argument("--e3", type=float, required=True, help="第3年一致预期净利润（亿元）")
    p1.set_defaults(func=cmd_implied)

    # calc: 正算
    p2 = common_base(sub.add_parser("calc", help="正算：由终局L+前3年业绩+r → 合理市值"))
    p2.add_argument("--l", type=float, required=True, help="终局利润L（亿元）")
    p2.add_argument("--e1", type=float, required=True, help="第1年一致预期净利润")
    p2.add_argument("--e2", type=float, required=True, help="第2年一致预期净利润")
    p2.add_argument("--e3", type=float, required=True, help="第3年一致预期净利润")
    p2.add_argument("--r", type=float, required=True, help="折现率(%)，如10表示10%")
    p2.set_defaults(func=cmd_calc)

    # analyze: 完整分析
    p3 = common_base(sub.add_parser("analyze", help="完整分析：反算+解读"))
    p3.add_argument("--cap", type=float, required=True, help="当前市值（亿元）")
    p3.add_argument("--e1", type=float, required=True, help="第1年一致预期净利润")
    p3.add_argument("--e2", type=float, required=True, help="第2年一致预期净利润")
    p3.add_argument("--e3", type=float, required=True, help="第3年一致预期净利润")
    p3.set_defaults(func=cmd_analyze)

    # sensitivity: 敏感性分析
    p4 = common_base(sub.add_parser("sensitivity", help="不同终局利润对应的市值"))
    p4.add_argument("--e1", type=float, required=True, help="第1年一致预期净利润")
    p4.add_argument("--e2", type=float, required=True, help="第2年一致预期净利润")
    p4.add_argument("--e3", type=float, required=True, help="第3年一致预期净利润")
    p4.add_argument("--r", type=float, default=10, help="折现率(%)，默认10%")
    p4.set_defaults(func=cmd_sensitivity)

    # brokers: v2.4.0新增 — 券商目标价批量反算
    p5 = common_base(sub.add_parser("brokers", help="批量反算各券商目标价隐含的终局利润L（v2.4.0新增）"))
    p5.add_argument("--e1", type=float, required=True, help="第1年一致预期净利润")
    p5.add_argument("--e2", type=float, required=True, help="第2年一致预期净利润")
    p5.add_argument("--e3", type=float, required=True, help="第3年一致预期净利润")
    p5.add_argument("--shares", type=float, required=True, help="总股本（亿股）")
    p5.add_argument("--prices", type=str, required=True, help="目标价列表，逗号分隔，如 48.67,64.86,72.8")
    p5.add_argument("--names", type=str, default=None, help="场景名称列表，逗号分隔，如 当前股价,高盛,中金")
    p5.set_defaults(func=cmd_brokers)

    args = parser.parse_args()
    args.func(args)


def get_dcf_result(cap: float, e1: float, e2: float, e3: float,
                   e0: float = 0,
                   base_year: int = DEFAULT_BASE_YEAR,
                   steady_year: int = DEFAULT_STEADY_YEAR) -> dict:
    """Return a structured DCF result for downstream use.

    Returns dict with keys:
    - growth_years
    - scenarios: dict of r -> {L, L/E3, L/E0, g, pe1}
    """
    gy = get_growth_years(base_year, steady_year)
    scenarios = {}
    for r in R_GRID:
        L = implied_ceiling(cap, e1, e2, e3, r, gy)
        scenarios[f"r_{r}"] = {
            "L": round(L, 1),
            "L/E3": round(L / e3, 2) if e3 > 0 else None,
            "L/E0": round(L / e0, 2) if e0 and e0 > 0 else None,
            "g": round(implied_growth_rate(L, e3, gy), 1),
            "pe1": round(cap / e1, 1) if e1 > 0 else None,
        }
    return {
        "base_year": base_year,
        "steady_year": steady_year,
        "growth_years": gy,
        "scenarios": scenarios,
    }


if __name__ == "__main__":
    main()
