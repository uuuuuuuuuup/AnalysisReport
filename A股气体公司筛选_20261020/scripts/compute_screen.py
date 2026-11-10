#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段1快筛计算：市值/PE/PB/TTM/回撤/硬伤初判。
数据源：raw_data.json（AI_Tools MCP 采集，2026-10-20）。
输出：data/screen_22.csv + data/screen_22.json
"""
import json, csv, os

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "data")

with open(os.path.join(DATA, "raw_data.json"), encoding="utf-8") as f:
    raw = json.load(f)

rows = []
for c in raw["companies"]:
    fy25, h1, bal = c.get("fy25"), c.get("h1_26"), c.get("bal")
    price = c.get("price")
    r = {"code": c["code"], "name": c["name"], "type": c["type"], "price": price,
         "note": c.get("layer_note", ""), "share_conflict": c.get("share_conflict", False)}

    if fy25 is None:
        r.update({"mcap": None, "pe_fy25": None, "pe_ttm": None, "pe_ded": None, "pb": None,
                  "ttm_np": None, "drawdown": None, "px_multiple_2y": None,
                  "cash_ratio": None, "ocf_flag": None, "hardflaw": "数据缺失(北交所)"})
        rows.append(r)
        continue

    # 股数（百万股）= FY25归母净利 / FY25 EPS
    shares = fy25["np"] / fy25["eps"] if fy25.get("eps") else None
    mcap = price * shares if (price and shares) else None  # 百万元

    # TTM = FY25 + H1_26 - H1_25(反推)
    ttm = None
    if h1 and h1.get("np") is not None and h1.get("np_yoy"):
        h1_25 = h1["np"] / (1 + h1["np_yoy"] / 100) if h1["np_yoy"] > -100 else None
        if h1_25 is not None:
            ttm = fy25["np"] + h1["np"] - h1_25

    r["shares_m"] = round(shares, 1) if shares else None
    r["mcap"] = round(mcap / 100, 2) if mcap else None          # 亿元
    r["pe_fy25"] = round(mcap / fy25["np"], 1) if mcap and fy25["np"] > 0 else None
    r["pe_ttm"] = round(mcap / ttm, 1) if mcap and ttm and ttm > 0 else None
    r["pe_ded_fy25"] = round(mcap / fy25["np_ded"], 1) if mcap and fy25.get("np_ded") and fy25["np_ded"] > 0 else None
    r["pb"] = round(price / fy25["bps"], 2) if price and fy25.get("bps") else None
    # H1_26 BPS：用最新资产负债表归母权益/股数重算
    if bal and shares:
        eq_p = bal["eq"] - bal.get("minority", 0)
        h1_bps = eq_p / shares
        r["pb"] = round(price / h1_bps, 2)
    r["ttm_np"] = round(ttm, 1) if ttm else None
    r["roe_fy25"] = fy25["roe"]
    r["gm_fy25"] = fy25["gm"]
    r["gm_h1_26"] = h1["gm"] if h1 else None
    r["debt_ratio"] = fy25["debt"]
    r["ocf_ps_fy25"] = fy25["ocf_ps"]

    # 2年价格行为
    if c.get("px24_high"):
        r["px24_high"] = c["px24_high"]
        r["drawdown_pct"] = round((price / c["px24_high"] - 1) * 100, 1)
        r["px_mult_24m_low"] = round(price / c["px24_low"], 2)

    # 货币资金/总资产
    if bal:
        r["cash_ratio"] = round(bal["cash"] / bal["ta"] * 100, 1)

    # 硬伤初判（可自动判定项）
    flaws = []
    if fy25["np"] < 0 and (h1 is None or h1["np"] < 0):
        flaws.append("FY25+H1_26连续亏损")
    if fy25["ocf_ps"] < 0 and (h1 is None or h1.get("ocf_ps", 1) >= 0):
        flaws.append("FY25经营现金流为负")
    if fy25["ocf_ps"] < 0 and h1 and h1.get("np") is not None and h1["np"] < 0:
        flaws.append("OCF与净利双负")
    r["hardflaw"] = "; ".join(flaws) if flaws else ""
    rows.append(r)

# 落盘
with open(os.path.join(DATA, "screen_22.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": raw["meta"], "rows": rows}, f, ensure_ascii=False, indent=1)

cols = ["code", "name", "type", "price", "shares_m", "mcap", "pe_fy25", "pe_ttm", "pe_ded_fy25",
        "pb", "ttm_np", "roe_fy25", "gm_fy25", "gm_h1_26", "debt_ratio", "ocf_ps_fy25",
        "px24_high", "drawdown_pct", "px_mult_24m_low", "cash_ratio", "hardflaw", "note"]
with open(os.path.join(DATA, "screen_22.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)

for r in rows:
    print(f"{r['code']} {r['name']:6s} {r['type']} 市值{r.get('mcap')}亿 PE_FY25={r.get('pe_fy25')} "
          f"PE_TTM={r.get('pe_ttm')} PB={r.get('pb')} 回撤{r.get('drawdown_pct')}% 硬伤[{r.get('hardflaw')}]")
