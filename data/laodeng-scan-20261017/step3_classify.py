#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
步骤3: 对 58 只候选池做八类框架的机械预判（决策树顺序）
+ T3一票否决/T4硬条件/T1周期嫌疑 自动标注
输出: step3_classified.csv
"""
import csv, os

OUT = os.path.dirname(os.path.abspath(__file__))

def nf(v):
    try: return float(v) if v not in ('', None, 'None', '-') else None
    except (ValueError, TypeError): return None

def classify(r):
    """按决策树: ①T3一票否决 → ②T2扣非背离 → ③T4硬条件 → ④T1周期嫌疑 → ⑤归因"""
    pb, pe = nf(r['pb']), nf(r['pe_ttm'])
    ocf_ni = nf(r.get('fin_ocf_ni'))
    roe = nf(r.get('fin_roe_latest'))
    debt = nf(r.get('fin_debt'))
    div_ratio = nf(r.get('fin_div_ratio'))
    rev_cagr = nf(r.get('fin_rev_cagr'))
    pctl = nf(r.get('price_pctl_10y'))
    roe_trend = r.get('fin_roe_trend', '')
    ni_yoy = nf(r.get('fin_ni_yoy'))

    flags = []
    verdict = '待判别'

    # ① T3 财务质量一票否决
    t3_hits = []
    if ocf_ni is not None and ocf_ni < 0.7: t3_hits.append(f'OCF/NI={ocf_ni}')
    if ocf_ni is None: t3_hits.append('OCF/NI缺数据')
    if debt is not None and debt > 0.75: t3_hits.append(f'负债率{debt*100:.0f}%')
    if len([h for h in t3_hits if '缺数据' not in h]) >= 2:
        verdict = '禁区(T3)'
    elif ocf_ni is not None and ocf_ni < 0.7:
        flags.append('T3边缘')

    # ② T2 扣非背离
    if div_ratio is not None and div_ratio > 50:
        flags.append(f'T2嫌疑(扣非背离{div_ratio}%)')

    # ③ T4 价值陷阱硬条件 (营收CAGR≤0 且 ROE<5%)
    if rev_cagr is not None and rev_cagr <= 0 and roe is not None and roe < 0.05:
        flags.append(f'T4嫌疑(营收CAGR{rev_cagr}%+ROE{roe*100:.1f}%)')
    if roe_trend == 'down' and rev_cagr is not None and rev_cagr <= 0:
        flags.append('T4嫌疑(ROE逐级下移+营收零增)')

    # ④ T1 周期顶嫌疑 (价格分位高但被跌幅筛进来, 或PB分位显著低于PE暗示)
    if pctl is not None and pctl > 60:
        flags.append(f'T1嫌疑(价格分位{pctl}%)')

    # ⑤ 归因提示
    if verdict == '待判别':
        if ocf_ni is not None and ocf_ni >= 1.0 and (pctl or 100) <= 15:
            verdict = '准猎物候选(T5/T6, 低分位+现金流健康)'
        elif ocf_ni is not None and ocf_ni >= 1.0 and pctl is not None and pctl <= 30:
            verdict = '拐点跟踪候选(现金流健康, 分位中低)'
        elif pctl is not None and pctl <= 15:
            verdict = '血统待查(极低分位但现金流存疑)'
        else:
            verdict = '观察'

    return verdict, '; '.join(flags)

def main():
    rows = list(csv.DictReader(open(os.path.join(OUT, 'step2_candidates.csv'), encoding='utf-8-sig')))
    out_rows = []
    for r in rows:
        verdict, flags = classify(r)
        r['verdict'] = verdict
        r['flags'] = flags
        out_rows.append(r)

    # 排序: 先按档位优先级
    prio = {'准猎物候选': 0, '拐点跟踪候选': 1, '血统待查': 2, '观察': 3, '待判别': 4, '禁区': 5}
    def key(x):
        v = x['verdict'].split('(')[0]
        return (prio.get(v, 9), nf(x.get('price_pctl_10y')) if nf(x.get('price_pctl_10y')) is not None else 999)
    out_rows.sort(key=key)

    out = os.path.join(OUT, 'step3_classified.csv')
    with open(out, 'w', newline='', encoding='utf-8-sig') as fp:
        w = csv.DictWriter(fp, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows: w.writerow(r)

    print(f"{'档位':<24}{'代码':<8}{'名称':<10}{'PB':>5}{'分位':>6}{'OCF/NI':>8}{'ROE':>7}{'负债':>6}  标注")
    for r in out_rows:
        print(f"{r['verdict'][:22]:<24}{r['code']:<8}{r['name']:<10}{r['pb']:>5}"
              f"{str(r.get('price_pctl_10y') or ''):>6}{str(r.get('fin_ocf_ni') or ''):>8}"
              f"{str(r.get('fin_roe_latest') or ''):>7}{str(r.get('fin_debt') or ''):>6}  {r['flags']}")

    # 统计
    from collections import Counter
    c = Counter(r['verdict'].split('(')[0] for r in out_rows)
    print("\n== 预判分布 ==")
    for k, v in c.most_common(): print(f"  {k}: {v}")

if __name__ == '__main__':
    main()
