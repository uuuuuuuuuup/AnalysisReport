#!/usr/bin/env python3
# 锚距分析：现价 vs 击球锚 × 池子规则 → 机会分层
import csv, re

def load(f):
    return list(csv.DictReader(open(f), delimiter='\t'))

stocks = {s["name_code"]: s for s in load("stocks_20260926.tsv")}
rows = []
for p in load("prices_full.tsv"):
    s = stocks.get(p["name_code"])
    if not s or not p["close"]: continue
    anchor_txt = s["anchor"]
    # 提取锚定价：优先区间"X-Y元"，再取首个"X元"（排除 X倍/X%/X分位）
    a = None
    m = re.search(r'(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)\s*元', anchor_txt)
    if m: a = (float(m.group(1)) + float(m.group(2))) / 2
    if a is None:
        for m in re.finditer(r'(\d+(?:\.\d+)?)(?!\.?\d)\s*(元|港元|美元)', anchor_txt):
            a = float(m.group(1)); break
    close = float(p["close"])
    dist = round((close/a - 1)*100, 1) if a else None
    rows.append({
        "name": p["name_code"], "mkt": p["market"], "pool": s["pool"], "tag": s["tag"],
        "date": p["date"], "close": close,
        "chg1": float(p["chg1d"]) if p["chg1d"] else 0.0,
        "chg5": float(p["chg5d"]) if p["chg5d"] else 0.0,
        "anchor": a, "dist": dist,
    })

from collections import Counter
print("=== 池子分布 ===", dict(Counter(r["pool"] for r in rows)))
print("=== 标签分布 ===", dict(Counter(r["tag"] for r in rows)))
print(f"有数字锚: {sum(1 for r in rows if r['anchor'])}/{len(rows)}")

def line(r):
    a = f"{r['anchor']:.2f}" if r["anchor"] else "-"
    d = f"{r['dist']:+.1f}%" if r["dist"] is not None else "-"
    return f"{r['name']} | {r['pool'][:4]} | {r['tag'][:6]} | {r['close']} ({r['chg1']:+.1f}%/5d{r['chg5']:+.1f}%) | 锚{a} 距{d}"

print("\n=== A. 暴风雨优先池（可参与层）===")
for r in rows:
    if r["pool"] == "暴风雨优先": print(line(r))

print("\n=== B. 破锚/临锚（-10%≤dist≤+3%，排除🚨雷）按距锚排序 ===")
cand = [r for r in rows if r["dist"] is not None and "🚨" not in r["tag"] and -10 <= r["dist"] <= 3]
cand.sort(key=lambda r: r["dist"])
for r in cand[:20]: print(line(r))
print(f"(共{len(cand)}只)")

print("\n=== C. 近期异动（1日≤-3% 或 5日≤-8%，排除🚨）===")
movers = [r for r in rows if "🚨" not in r["tag"] and (r["chg1"] <= -3 or r["chg5"] <= -8)]
movers.sort(key=lambda r: min(r["chg1"], r["chg5"]))
for r in movers[:15]: print(line(r))
print(f"(共{len(movers)}只)")

print("\n=== D. 🚨雷标签标的现价（回避区，仅核对）===")
for r in rows:
    if "🚨" in r["tag"]: print(f"{r['name']} | {r['close']} ({r['chg5']:+.1f}%)")
