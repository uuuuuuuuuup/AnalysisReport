#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
步骤1(升级): 问财直连拉取全市场快照 — 含近1年涨跌幅/股息率/区间最高价
输出: step1_market_snapshot.csv (全字段)
"""
import requests, time, csv, json, sys, os

OUT = os.path.dirname(os.path.abspath(__file__))
s = requests.Session(); s.trust_env = False
H = {"Host": "np-tjxg-g.eastmoney.com", "Origin": "https://xuangu.eastmoney.com",
     "Referer": "https://xuangu.eastmoney.com/",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
     "Content-Type": "application/json"}

def wencai(words, page_no=1, page_size=100, retries=3):
    body = {"keyWord": words, "pageSize": page_size, "pageNo": page_no,
        "fingerprint": "02efa8944b1f90fbfe050e1e695a480d", "gids": [], "matchWord": "",
        "timestamp": int(time.time()), "shareToGuba": False,
        "requestId": f"req-{int(time.time()*1000)}-{page_no}", "needCorrect": True,
        "removedConditionIdList": [], "xcId": "xc0d61279aad33008260",
        "ownSelectAll": False, "dxInfo": [], "extraCondition": ""}
    for a in range(retries):
        try:
            r = s.post("https://np-tjxg-g.eastmoney.com/api/smart-tag/stock/v3/pw/search-code",
                       json=body, headers=H, timeout=25)
            d = r.json()
            rd = d.get("data", {}).get("result", {})
            return rd.get("dataList", [])
        except Exception as e:
            if a == retries-1:
                print(f"  [warn] p{page_no} fail {e}", file=sys.stderr); return []
            time.sleep(2)

def get_prefix(row, *prefixes):
    for p in prefixes:
        for k, v in row.items():
            if k.startswith(p):
                return v
    return None

def main():
    all_rows = {}
    QUERY = "全部A股 近一年涨跌幅 最新股息率 52周最高价 所属东财行业 市净率 市盈率TTM 总市值"
    for p in range(1, 80):
        dl = wencai(QUERY, page_no=p)
        if not dl:
            print(f"page {p}: empty stop"); break
        n_new = 0
        for row in dl:
            code = row.get('SECURITY_CODE')
            if code and code not in all_rows:
                all_rows[code] = row; n_new += 1
        print(f"page {p}: {len(dl)} rows, new {n_new}, total {len(all_rows)}")
        if n_new == 0: break
        time.sleep(0.6)

    out = os.path.join(OUT, 'step1_market_snapshot.csv')
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['code','name','industry','sw_industry','price','chg_1y_pct','dividend_yield',
                    'pb','pe_ttm','pe_dyn','mkt_cap','float_cap','peak_1y','bottom_1y','concepts'])
        for code, row in all_rows.items():
            def num(v):
                if v is None: return ''
                s2 = str(v).strip()
                if s2.endswith('万亿'): return float(s2[:-2])*1e12
                if s2.endswith('亿'): return float(s2[:-1])*1e8
                if s2.endswith('万'): return float(s2[:-1])*1e4
                if s2.endswith('%'): return float(s2[:-1])
                return s2
            w.writerow([code, row.get('SECURITY_SHORT_NAME'), row.get('INDUSTRY'),
                row.get('SW_INDUSTRY'), row.get('NEWEST_PRICE'),
                num(get_prefix(row, 'INTERVAL_CHG')),
                num(get_prefix(row, 'DIVIDEND_NEWRATIO', 'DIVIDEND')),
                row.get('PB'), num(get_prefix(row, 'PETTM')), row.get('PE_DYNAMIC'),
                num(get_prefix(row, 'TOAL_MARKET_VALUE')), num(get_prefix(row, 'CIRCULATION_MARKET_VALUE')),
                num(get_prefix(row, 'INTERVAL_PEEK_PRICE', 'PEAK_PRICE')),
                num(get_prefix(row, 'INTERVAL_BOTTOM_PRICE', 'BOTTOM_PRICE')),
                (row.get('STYLE_CONCEPT') or '')[:200]])
    print(f"\n写出 {len(all_rows)} 只 -> {out}")

if __name__ == '__main__':
    main()
