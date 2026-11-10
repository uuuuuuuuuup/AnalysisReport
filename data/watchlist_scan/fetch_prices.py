#!/usr/bin/env python3
# 关注池全量行情抓取 v2：westock kline（延时K线，非实时；部分标的为09-25收盘、部分09-24）
import subprocess, re, csv
from collections import defaultdict

BASE = "/Users/apple/Documents/分析报告/data/watchlist_scan"
STOCKS, PRICES = f"{BASE}/stocks_20260926.tsv", f"{BASE}/prices_full.tsv"
CMD = ["npx", "-y", "westock-data-skillhub@1.0.5"]

def parse_code(name_code, market):
    m = re.search(r'\s+([0-9]{6})(?:\s*/.*)?$', name_code)
    if m and (market == "A股" or re.search(r'[0-9]{6}', name_code.split('/')[-1] or '')):
        if market == "A股": return ("sh" if m.group(1)[0]=='6' else "bj" if m.group(1)[0] in '48' else "sz") + m.group(1)
    m = re.search(r'\s+([0-9]{1,5})\.HK$', name_code.split('/')[0].strip())
    if m: return "hk" + m.group(1).zfill(5)
    m = re.search(r'\s+([A-Z][A-Za-z]{0,5})(?:\.US)?$', name_code)
    if m: return "us" + m.group(1).upper()
    return None

stocks = []
for r in csv.DictReader(open(STOCKS), delimiter='\t'):
    r["req"] = parse_code(r["name_code"], r["market"])
    stocks.append(r)

prices = {}
def run_kline(codes):
    r = subprocess.run(CMD + ["kline", ",".join(codes), "--period", "day", "--limit", "6"],
                       capture_output=True, text=True, timeout=120, cwd=BASE)
    bars = defaultdict(list)
    sym_re = re.compile(r'^(sh|sz|bj)[0-9]{6}$|^hk[0-9]{5}$|^us[A-Z]+$|^[A-Z]{1,6}$')
    for line in r.stdout.splitlines():
        if not line.strip().startswith("|"): continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # A股/港股表: symbol,date,open,last,...  美股表: date,open,last,...(无symbol列)
        if sym_re.match(cells[0]) and len(cells) >= 5 and re.match(r'^\d{4}-\d{2}-\d{2}$', cells[1]):
            try: bars[cells[0]].append((cells[1], float(cells[3])))
            except ValueError: pass
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', cells[0]) and len(cells) >= 3:
            try: bars["__us"].append((cells[0], float(cells[2])))
            except ValueError: pass
    return bars

all_reqs = [s["req"] for s in stocks if s["req"]]
# 按市场分批（美股表无symbol列只能单只查）
def chunks(lst, n):
    for i in range(0, len(lst), n): yield lst[i:i+n]
a_codes = [c for c in all_reqs if c[:2] in ("sh","sz","bj")]
h_codes = [c for c in all_reqs if c[:2] == "hk"]
u_codes = [c[2:] for c in all_reqs if c[:2] == "us"]
fails = []
for codes, size in [(a_codes, 30), (h_codes, 25)]:
    for grp in chunks(codes, size):
        try: bars = run_kline(grp)
        except Exception as e:
            fails += [(c, str(e)[:40]) for c in grp]; continue
        for c in grp:
            if bars.get(c): prices[c] = sorted(bars[c], reverse=True)
            else: fails.append((c, "no data"))
for t in u_codes:
    try: bars = run_kline(["us"+t])
    except Exception: bars = {}
    if bars.get("__us"): prices["us"+t] = sorted(bars["__us"], reverse=True)
    else: fails.append(("us"+t, "no data"))

with open(PRICES, "w") as f:
    f.write("name_code\tmarket\treq\tdate\tclose\tprev_close\tchg1d\tclose5d\tchg5d\n")
    for s in stocks:
        b = prices.get(s["req"])
        if b:
            d, c = b[0]; pc = b[1][1] if len(b)>1 else ""; c5 = b[5][1] if len(b)>5 else ""
            chg1 = round((c/pc-1)*100,2) if pc else ""; chg5 = round((c/c5-1)*100,2) if c5 else ""
            f.write(f"{s['name_code']}\t{s['market']}\t{s['req']}\t{d}\t{c}\t{pc}\t{chg1}\t{c5}\t{chg5}\n")
        else:
            f.write(f"{s['name_code']}\t{s['market']}\t{s['req']}\t\t\t\t\t\t\n")

dates = sorted({b[0][0] for b in prices.values()})
print(f"总数:{len(stocks)} 成功:{len(prices)} 失败:{len(fails)} 日期:{dates[0]}~{dates[-1]}")
if fails: print("失败:", fails)
