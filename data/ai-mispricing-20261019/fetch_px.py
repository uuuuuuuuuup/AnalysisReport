#!/usr/bin/env python3
"""10-19 行情更新：批量拉 A股+港股+指数 日K，计算近1月/近3月/YTD/自年内高点回撤。
输出: px_20261019.json
"""
import json, re, subprocess

# 核心池（上次终审 8 家 + 否决/降档 2 家 + 港股 ASMPT）
CORE = ["300308","300502","002463","002916","601138","688183","688008","300476"]
HK = ["hk00522"]
# 扩散池：复检角度A（设备/材料/电源温控）+ 上次重点剔除但需登记的
EXT = ["688012","688072","300604","688200","300567","688082","688037",   # 设备
       "688019","300054","002409","300666","688126",                      # 材料
       "002851","301018","300499","300911","002837","603912",               # 电源温控
       "300394","300570","002130"]                                        # 光器件/连接（上次高估值剔除，需登记）
# 指数（westock 符号：科创50 在上交所 → sh000688）
IDX = [("sz","399006"),("sh","000688"),("sz","399673")]  # 创业板指、科创50、创业板50

ALL = CORE + EXT
def sym(c): return ("sh" if c.startswith("6") else "sz")+c

def kline(syms, start, end, fq="qfq"):
    """westock kline 批量; 返回 {code: [(date,close),...]} 按日期升序"""
    rows = {}
    for i in range(0, len(syms), 8):
        batch = syms[i:i+8]
        p = subprocess.run(["westock-data-skillhub","kline",",".join(batch),"--period","day",
                            "--start",start,"--end",end,"--fq",fq],
                           capture_output=True,text=True,timeout=300)
        for ln in p.stdout.splitlines():
            c=[x.strip() for x in ln.strip().strip('|').split('|')]
            if len(c)>=4 and re.match(r'^(sh|sz|hk)\w{4,6}$',c[0]) and re.match(r'^20\d\d-\d\d-\d\d$',c[1]):
                rows.setdefault(c[0],[]).append((c[1],float(c[3])))
    # westock 返回降序（最新在前），统一转为升序
    for k in rows: rows[k] = sorted(rows[k])
    return rows

out = {"asof":"2026-10-19"}
# A股前复权
data = kline([sym(c) for c in ALL]+[f"{pfx}{i}" for pfx,i in IDX]+HK, "2025-12-10","2026-10-19")
for c in ALL:
    r = data.get(sym(c),[])
    if not r: out[c]={"error":"no data"}; continue
    closes = {d:v for d,v in r}
    last_d, last = r[-1]
    y0 = [x for x in r if x[0] < "2026-01-01"]
    base_ytd = y0[-1][1] if y0 else None
    yr26 = [x for x in r if x[0] >= "2026-01-01"]
    hi_d, hi = max(yr26, key=lambda x:x[1]) if yr26 else (None,None)
    def ret(days):
        tgt = [x for x in r if x[0] <= days]
        return round((last/tgt[-1][1]-1)*100,1) if tgt else None
    out[c] = {"name":"","close":last,"date":last_d,
              "r20d": ret("2026-09-18"),   # 近1月
              "r60d": ret("2026-07-17"),   # 近3月
              "ytd": round((last/base_ytd-1)*100,1) if base_ytd else None,
              "r0630": ret("2026-06-30"),  # 6/30→10-19（下跌主段）
              "close1016": next((v for d,v in reversed(r) if d<="2026-10-16"), None),
              "hi2026": hi, "hi_date": hi_d,
              "dd_from_hi": round((last/hi-1)*100,1) if hi else None,
              "n_rows": len(r)}
for pfx,i in IDX:
    r = data.get(f"{pfx}{i}",[])
    if not r: out[f"idx_{i}"]={"error":"no data"}; continue
    last_d,last = r[-1]
    y0=[x for x in r if x[0]<"2026-01-01"]; yr26=[x for x in r if x[0]>="2026-01-01"]
    hi_d,hi=max(yr26,key=lambda x:x[1]) if yr26 else (None,None)
    def ret(days):
        tgt=[x for x in r if x[0]<=days]
        return round((last/tgt[-1][1]-1)*100,1) if tgt else None
    out[f"idx_{i}"]={"close":last,"date":last_d,"r20d":ret("2026-09-18"),"r60d":ret("2026-07-17"),
                     "ytd":round((last/y0[-1][1]-1)*100,1) if y0 else None,
                     "r0630":ret("2026-06-30"),
                     "hi2026":hi,"hi_date":hi_d,"dd_from_hi":round((last/hi-1)*100,1) if hi else None}
    print(f"idx_{i}", out[f"idx_{i}"])
# 港股 00522 (westock hk 前缀, 不复权)
hk = data.get("hk00522",[])
if hk:
    last_d,last=hk[-1]
    yr26=[x for x in hk if x[0]>="2026-01-01"]
    hi_d,hi=max(yr26,key=lambda x:x[1]) if yr26 else (None,None)
    def ret(days):
        tgt=[x for x in hk if x[0]<=days]
        return round((last/tgt[-1][1]-1)*100,1) if tgt else None
    out["hk00522"]={"close":last,"date":last_d,"r20d":ret("2026-09-18"),"r60d":ret("2026-07-17"),
                    "ytd":None,"r0630":ret("2026-06-30"),
                    "hi2026":hi,"hi_date":hi_d,"dd_from_hi":round((last/hi-1)*100,1) if hi else None}
json.dump(out,open("px_20261019.json","w"),ensure_ascii=False,indent=1)
for k,v in out.items(): print(k,v)
