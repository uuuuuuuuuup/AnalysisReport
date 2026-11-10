#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
步骤2: 全市场统一过滤
输入: step1_market_snapshot.csv + aitools.db (月K/财务指标)
输出: step2_candidates.csv (通过双条件的候选池，含分位/财务质量)
"""
import csv, sqlite3, os, re, json

OUT = os.path.dirname(os.path.abspath(__file__))
DB = '/Users/apple/Documents/code/AI-Tools/src/main/resources/aitools.db'

# ---------- 剔除规则 ----------
EXCLUDE_INDUSTRY_KW = [
    '半导体', '元件', '光学光电子', '通信设备', '计算机', '软件', 'IT服务',
    '消费电子', '电子化学品', '游戏', '影视', '传媒', '数字媒体', '广告营销',
    '电池', '光伏', '风电设备', '电源设备', '电机', '电网设备',
    '自动化设备', '航天装备', '航空装备', '军工电子', '机器人',
    '生物制品', '医疗服务', '医疗器械', '化学制药',
    '林业', '渔业', '动物保健',
    '教育', '酒店餐饮', '旅游景区', '体育',
]
# 注：化学制药/医疗器械等医药细分在"老登股"语境里保留中药/医药商业，剔除创新药产业链
EXCLUDE_SW_KW = ['半导体', '消费电子', '光学光电子', '元件', '通信设备', '计算机设备',
                 '软件开发', 'IT服务', '游戏', '影视院线', '数字媒体', '广告营销',
                 '电池', '光伏设备', '风电设备', '电网设备', '航天装备', '航空装备',
                 '军工电子', '机器人', '电子化学品', '医疗器械', '生物制品',
                 '能源金属', '小金属', '教育', '旅游及景区']

INCLUDE_SW_KW = ['中药', '医药商业', '化学制药']  # 医药只留这三类
MIN_MKT_CAP = 100e8          # 100亿
MIN_DROP_1Y = -25.0          # 近1年跌幅≥25%
MIN_DRAWDOWN = -30.0         # 距52周高点回撤≥30%
MAX_PRICE_PCTL = 40.0        # 价格10年分位≤40% (框架v1.1建议加入的硬条件)

# 低估特征三选一
PB_LOW = 1.0
PE_TTM_LOW = 12.0
DIV_HIGH = 4.0

def f(v):
    try:
        return float(v) if v not in ('', None, 'None', '-') else None
    except (ValueError, TypeError):
        return None

def load_monthly(db):
    """加载月K收盘价: {code6: [(date, close), ...]} 按时间升序"""
    cur = db.cursor()
    data = {}
    for code, d, c in cur.execute(
            "SELECT stock_code, trade_date, close_price FROM monthly_k_line_data ORDER BY stock_code, trade_date"):
        c6 = code[-6:]
        data.setdefault(c6, []).append((d, c))
    return data

def load_financials(db):
    """加载财务指标: {code6: [ {report_date, ...}, ... ]} 按报告期降序"""
    cur = db.cursor()
    data = {}
    q = """SELECT stock_code, report_date, net_profit, net_profit_excl_nr, net_profit_yoy,
                  roe, operating_cash_flow_per_share, eps, asset_liability_ratio, gross_margin,
                  operating_revenue, operating_revenue_yoy
           FROM financial_report_indicator ORDER BY stock_code, report_date DESC"""
    for row in cur.execute(q):
        code, rd = row[0], row[1]
        c6 = code[-6:]
        data.setdefault(c6, []).append({
            'rd': rd, 'ni': row[2], 'ni_ex': row[3], 'ni_yoy': row[4], 'roe': row[5],
            'ocfps': row[6], 'eps': row[7], 'debt': row[8], 'gm': row[9],
            'rev': row[10], 'rev_yoy': row[11],
        })
    return data

def pctl_10y(closes, cur_price, months=120):
    """10年价格分位 = 最近N个月收盘价中低于现价的占比"""
    if not closes or cur_price is None:
        return None, None
    recent = [c for _, c in closes[-months:] if c is not None]
    if len(recent) < 24:
        return None, len(recent)
    below = sum(1 for c in recent if c < cur_price)
    return round(below / len(recent) * 100, 1), len(recent)

def fin_quality(fins):
    """财务质量: OCF/NI三年累计(总额口径), ROE趋势, 扣非背离, 负债率, 营收CAGR"""
    if not fins:
        return {}
    annual = [x for x in fins if x['rd'].endswith('12-31')][:3]
    # OCF/NI 三年累计: sum(OCF总额)/sum(净利), OCF总额 = OCFPS × 股本, 股本 = NI/EPS
    sum_ocf, sum_ni = 0.0, 0.0
    valid = 0
    for x in annual:
        ocfps, eps, ni = x.get('ocfps'), x.get('eps'), x.get('ni')
        if ocfps is not None and eps and ni is not None and abs(eps) > 0.01:
            shares = ni / eps              # 反推股本(股)
            sum_ocf += ocfps * shares      # OCF 总额(元)
            sum_ni += ni                   # 净利总额(元)
            valid += 1
    ocf_ni = round(sum_ocf / sum_ni, 2) if valid >= 2 and abs(sum_ni) > 1e8 else None

    # ROE 趋势 (最近几个年报)
    roes = [(x['rd'][:4], x.get('roe')) for x in annual if x.get('roe') is not None]
    roe_trend = None
    if len(roes) >= 3:
        roe_trend = 'down' if roes[0][1] < roes[-1][1] else 'up'

    latest = fins[0]
    # 扣非 vs 归母 背离
    ni, ni_ex = latest.get('ni'), latest.get('ni_ex')
    div_ratio = None
    if ni and ni_ex is not None and abs(ni) > 1e7:
        div_ratio = round(abs(ni - ni_ex) / abs(ni) * 100, 1)

    # 5年营收 CAGR
    revs = [(x['rd'][:4], x.get('rev')) for x in fins if x['rd'].endswith('12-31') and x.get('rev')]
    rev_cagr = None
    if len(revs) >= 2:
        newest, oldest = revs[0], revs[-1]
        try:
            yrs = int(newest[0]) - int(oldest[0])
            if yrs > 0 and oldest[1] > 0:
                rev_cagr = round(((newest[1]/oldest[1]) ** (1/yrs) - 1) * 100, 1)
        except Exception:
            pass

    return {
        'ocf_ni': ocf_ni, 'roe_latest': latest.get('roe'), 'roe_trend': roe_trend,
        'ni_yoy': latest.get('ni_yoy'), 'div_ratio': div_ratio,
        'debt': latest.get('debt'), 'rev_cagr': rev_cagr,
        'latest_rd': latest.get('rd'),
    }

def main():
    rows = list(csv.DictReader(open(os.path.join(OUT, 'step1_market_snapshot.csv'), encoding='utf-8-sig')))
    print(f"全市场 {len(rows)} 只")

    db = sqlite3.connect(DB)
    monthly = load_monthly(db)
    fins = load_financials(db)
    print(f"本地库: 月K {len(monthly)} 只, 财务 {len(fins)} 只")

    stats = {'industry_excl': 0, 'cap_excl': 0, 'no_data': 0,
             'no_cheap': 0, 'no_beaten': 0, 'pctl_excl': 0, 'pass': 0}
    candidates = []

    for r in rows:
        code, name = r['code'], r['name']
        ind, sw = r.get('industry', ''), r.get('sw_industry', '')

        # 1. 行业剔除
        if any(k in ind for k in EXCLUDE_INDUSTRY_KW) or any(k in sw for k in EXCLUDE_SW_KW):
            # 医药豁免：中药/医药商业保留
            if not any(k in sw for k in INCLUDE_SW_KW):
                stats['industry_excl'] += 1
                continue
        # ST 已在问财查询隐含（后面可以复查名字含ST直接剔）
        if 'ST' in name or name.startswith('N') or name.startswith('C'):
            stats['industry_excl'] += 1
            continue

        # 2. 市值
        cap = f(r.get('mkt_cap'))
        if not cap or cap < MIN_MKT_CAP:
            stats['cap_excl'] += 1
            continue

        pb, pe, price = f(r.get('pb')), f(r.get('pe_ttm')), f(r.get('price'))
        chg1y, div, peak = f(r.get('chg_1y_pct')), f(r.get('dividend_yield')), f(r.get('peak_1y'))

        # 3. 数据完整性
        if price is None or chg1y is None:
            stats['no_data'] += 1
            continue

        # 4. 错杀特征: 近1年跌幅≥25% OR 距52周高点回撤≥30%
        drawdown = None
        if peak and peak > 0 and price:
            drawdown = (price - peak) / peak * 100
        beaten = (chg1y <= MIN_DROP_1Y) or (drawdown is not None and drawdown <= MIN_DRAWDOWN)
        if not beaten:
            stats['no_beaten'] += 1
            continue

        # 5. 低估特征三选一
        cheap = False; cheap_by = []
        if pb is not None and 0 < pb <= PB_LOW: cheap = True; cheap_by.append(f'PB{pb}')
        if pe is not None and 0 < pe <= PE_TTM_LOW: cheap = True; cheap_by.append(f'PE{pe}')
        if div is not None and div >= DIV_HIGH: cheap = True; cheap_by.append(f'股息{div}')
        if not cheap:
            stats['no_cheap'] += 1
            continue

        # 6. 价格10年分位
        pctl, n_months = pctl_10y(monthly.get(code), price)
        if pctl is not None and pctl > MAX_PRICE_PCTL:
            stats['pctl_excl'] += 1
            continue

        # 7. 财务质量
        fq = fin_quality(fins.get(code, []))

        stats['pass'] += 1
        candidates.append({
            'code': code, 'name': name, 'industry': ind, 'sw_industry': sw,
            'price': price, 'chg_1y': chg1y, 'drawdown_52w': round(drawdown, 1) if drawdown else '',
            'pb': pb, 'pe_ttm': pe, 'div_yield': div,
            'mkt_cap_yi': round(cap/1e8, 1), 'price_pctl_10y': pctl, 'months_data': n_months,
            'cheap_by': '|'.join(cheap_by),
            **{f'fin_{k}': v for k, v in fq.items()},
        })

    print("\n== 过滤统计 ==")
    for k, v in stats.items(): print(f"  {k}: {v}")

    # 排序: 价格分位升序(越低估越前)
    candidates.sort(key=lambda x: (x['price_pctl_10y'] if x['price_pctl_10y'] is not None else 999))

    out = os.path.join(OUT, 'step2_candidates.csv')
    fields = ['code','name','industry','sw_industry','price','chg_1y','drawdown_52w',
              'pb','pe_ttm','div_yield','mkt_cap_yi','price_pctl_10y','months_data','cheap_by',
              'fin_ocf_ni','fin_roe_latest','fin_roe_trend','fin_ni_yoy','fin_div_ratio','fin_debt','fin_rev_cagr','fin_latest_rd']
    with open(out, 'w', newline='', encoding='utf-8-sig') as fp:
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for c in candidates: w.writerow(c)
    print(f"\n候选池 {len(candidates)} 只 -> {out}")

    # 打印 top 30
    print("\n== Top 30 (价格分位升序) ==")
    print(f"{'代码':<8}{'名称':<10}{'行业':<10}{'PB':>5}{'PE':>7}{'股息':>5}{'1y跌幅':>8}{'回撤':>7}{'分位':>6}{'市值':>8}{'OCF/NI':>7}")
    for c in candidates[:30]:
        print(f"{c['code']:<8}{c['name']:<10}{c['industry'][:8]:<10}{str(c['pb']):>5}{str(c['pe_ttm']):>7}"
              f"{str(c['div_yield']):>5}{c['chg_1y']:>8}{str(c['drawdown_52w']):>7}{str(c['price_pctl_10y']):>6}"
              f"{c['mkt_cap_yi']:>8}{str(c['fin_ocf_ni']):>7}")

if __name__ == '__main__':
    main()
