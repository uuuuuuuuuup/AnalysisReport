#!/usr/bin/env python3
"""东财 push2 快照: 最新价/总市值/PE_TTM/PB, 用于 10-19 估值更新"""
import json, urllib.request

CORE = ["300308","300502","002463","002916","601138","688183","688008","300476",
        "688012","688072","300604","688200","300567","688082","688037",
        "688019","300054","002409","300666","688126","002851","301018","300499","300911","002837",
        "300394","300570","002130"]
def secid(c):
    return ("1." if c.startswith(("6","9")) else "0.")+c
ids = ",".join(secid(c) for c in CORE)
url = (f"https://push2.eastmoney.com/api/qt/ulist.np/get?secids={ids}"
       "&fields=f2,f3,f9,f12,f14,f20,f21,f23,f115&fltt=2&pn=1&np=1&po=1")
req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
d = json.load(urllib.request.urlopen(req, timeout=30))
out = {}
for it in d.get("data",{}).get("diff",[]):
    c = it.get("f12")
    # f2 最新价 f9 PE动 f14名称 f20总市值 f21流通市值 f23 PB f115 PE_TTM (单位: 元/元/亿元?)
    out[c] = {"name":it.get("f14"),"price":it.get("f2"),"pe_ttm":it.get("f115"),"pe_lyr":it.get("f9"),
              "pb":it.get("f23"),"mcap_total":(it.get("f20") or 0)/1e8 if isinstance(it.get("f20"),(int,float)) else None,
              "mcap_float":(it.get("f21") or 0)/1e8 if isinstance(it.get("f21"),(int,float)) else None}
json.dump(out, open("snapshot_20261019.json","w"), ensure_ascii=False, indent=1)
for c,v in out.items(): print(c, v)
