#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
老登股全市场统一初筛 - 步骤1：问财直连拉取全市场快照
输出：data/laodeng-scan-20261017/step1_market_snapshot.csv
"""
import requests, time, csv, json, sys, os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
s = requests.Session()
s.trust_env = False
HEADERS = {
    "Host": "np-tjxg-g.eastmoney.com",
    "Origin": "https://xuangu.eastmoney.com",
    "Referer": "https://xuangu.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
    "Content-Type": "application/json",
}

def wencai(words, page_no=1, page_size=100, retries=3):
    body = {
        "keyWord": words, "pageSize": page_size, "pageNo": page_no,
        "fingerprint": "02efa8944b1f90fbfe050e1e695a480d",
        "gids": [], "matchWord": "", "timestamp": int(time.time()),
        "shareToGuba": False, "requestId": f"req-{int(time.time()*1000)}-{page_no}",
        "needCorrect": True, "removedConditionIdList": [], "xcId": "xc0d61279aad33008260",
        "ownSelectAll": False, "dxInfo": [], "extraCondition": ""
    }
    for attempt in range(retries):
        try:
            r = s.post("https://np-tjxg-g.eastmoney.com/api/smart-tag/stock/v3/pw/search-code",
                       json=body, headers=HEADERS, timeout=25)
            d = r.json()
            rd = d.get("data", {}).get("result", {})
            return rd.get("dataList", []), rd.get("columns", [])
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [warn] page {page_no} failed: {e}", file=sys.stderr)
                return [], []
            time.sleep(2)

def fetch_all_market(max_pages=80):
    """翻页拉全市场，问财单页最多100条"""
    all_rows = {}
    for p in range(1, max_pages + 1):
        dl, cols = wencai("全部A股 所属东财行业 市净率 市盈率TTM 总市值 股息率", page_no=p, page_size=100)
        if not dl:
            print(f"page {p}: empty, stop.")
            break
        n_new = 0
        for row in dl:
            code = row.get('SECURITY_CODE')
            if code and code not in all_rows:
                all_rows[code] = row
                n_new += 1
        print(f"page {p}: got {len(dl)}, new {n_new}, total {len(all_rows)}")
        if n_new == 0:
            break
        time.sleep(0.7)
    return all_rows

def parse_amount(s):
    """'3.06万亿' / '2027.27亿' / '1234.5万' -> float 元"""
    if s is None: return None
    s = str(s).strip()
    if not s or s in ('-', '--', 'null'): return None
    try:
        if s.endswith('万亿'): return float(s[:-2]) * 1e12
        if s.endswith('亿'):  return float(s[:-1]) * 1e8
        if s.endswith('万'):  return float(s[:-1]) * 1e4
        return float(s)
    except ValueError:
        return None

def main():
    print("== 拉取全市场快照 ==")
    rows = fetch_all_market()
    print(f"\n合计: {len(rows)} 只")

    fields = ['SECURITY_CODE','SECURITY_SHORT_NAME','INDUSTRY','INDUSTRY_ALL','SW_INDUSTRY',
              'NEWEST_PRICE','CHG','PB','PETTM','PE_DYNAMIC','TOAL_MARKET_VALUE','CIRCULATION_MARKET_VALUE',
              'PEAK_PRICE','BOTTOM_PRICE','STYLE_CONCEPT','SECURITYTYPE']
    out = os.path.join(OUT_DIR, 'step1_market_snapshot.csv')
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['code','name','industry','sw_industry','price','chg_pct','pb','pe_ttm','pe_dyn',
                    'mkt_cap','float_cap','peak52w','bottom52w','concepts'])
        for code, row in rows.items():
            def g(*keys):
                for k in keys:
                    for kk in row:
                        if kk.startswith(k):
                            return row[kk]
                return None
            w.writerow([
                code, row.get('SECURITY_SHORT_NAME'), row.get('INDUSTRY'),
                row.get('SW_INDUSTRY'), row.get('NEWEST_PRICE'), row.get('CHG'),
                row.get('PB'), g('PETTM'), row.get('PE_DYNAMIC'),
                g('TOAL_MARKET_VALUE'), g('CIRCULATION_MARKET_VALUE'),
                g('PEAK_PRICE'), g('BOTTOM_PRICE'),
                (row.get('STYLE_CONCEPT') or '')[:200],
            ])
    print(f"已写出: {out}")

    # 同时保存原始JSON备查
    raw_out = os.path.join(OUT_DIR, 'step1_raw.json')
    with open(raw_out, 'w', encoding='utf-8') as f:
        json.dump(list(rows.values()), f, ensure_ascii=False)
    print(f"原始JSON: {raw_out}")

if __name__ == '__main__':
    main()
