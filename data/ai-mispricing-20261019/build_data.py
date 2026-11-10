#!/usr/bin/env python3
"""生成 8 个 CSV 到交付目录 data/。
数据源:
- 归档 /Users/apple/Documents/AI产业链错杀挖掘-20261017/数据/ (stage0/1/2, 2026-10-17 版)
- 本次更新: px_20261019.json (westock 10-19), snapshot_20261019.json (东财快照 10-19),
            rev2_20261019.json (一致预期 W1 至 10-19), 公告增量 (东财 np-anotice)
"""
import csv, json, os

ARC = "/Users/apple/Documents/AI产业链错杀挖掘-20261017/数据"
CUR = "/Users/apple/Documents/分析报告/data/ai-mispricing-20261019"
OUT = "/Users/apple/Downloads/AI产业链错杀挖掘-20261019/data"
os.makedirs(OUT, exist_ok=True)

uni = json.load(open(f"{ARC}/stage1/u/universe.json"))
scr = {x["code"]: x for x in json.load(open(f"{ARC}/stage1/u/screen.json"))}
c3 = json.load(open(f"{ARC}/stage2/c3_ext.json"))
cls = json.load(open(f"{ARC}/stage2/classify50.json"))
hkai = json.load(open(f"{ARC}/stage0/hk_ai.json"))
ff = json.load(open(f"{ARC}/stage2/final_facts.json"))
ucf = json.load(open(f"{ARC}/stage1/u/u_cf.json"))
px = json.load(open(f"{CUR}/px_20261019.json"))
snap = json.load(open(f"{CUR}/snapshot_20261019.json"))
rev = json.load(open(f"{CUR}/rev2_20261019.json"))

def wcsv(name, header, rows):
    with open(f"{OUT}/{name}", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        wr.writerows(rows)
    print(f"{name}: {len(rows)} rows")

# ============ 1. scan_universe.csv ============
# 231 家 A 股机械漏斗 + 39 家先天剔除登记 + 55 家港股登记
SEG_NAME = {"S1":"算力芯片","S2":"互联芯片","S3":"存储","S4":"晶圆制造","S5":"半导体设备",
    "S6":"半导体材料","S7":"光互联","S8":"电互联/线缆","S9":"光纤光缆","S10":"PCB/CCL",
    "S11":"服务器/ODM","S12":"液冷温控","S13":"电源/备电","S14":"电网设备","S15":"备电发电",
    "S16":"机柜/IDC","S17":"端侧模组","S18":"云/算力服务","S19":"应用/数据","S20":"具身智能",
    "S21":"自动驾驶","S0":"非AI环节(指数成分)"}
def ai_layer(seg):
    m = {"S1":"算力层","S2":"算力层","S3":"算力层","S4":"算力层","S5":"算力层","S6":"算力层",
         "S7":"算力层","S8":"算力层","S9":"算力层","S10":"算力层","S11":"算力层","S12":"算力层",
         "S13":"算力层","S14":"算力层","S15":"算力层","S16":"算力层","S17":"端侧/应用层",
         "S18":"模型/云层","S19":"应用层","S20":"具身智能层","S21":"自动驾驶层","S0":"非AI"}
    return m.get(seg, "未知")
def cls_cat(c):
    v = cls.get(c, {})
    return v.get("cat", "") if isinstance(v, dict) else ""
rows1 = []
for c, u in uni.items():
    s = scr.get(c, {})
    e3 = c3.get(c, {})
    mcap16 = s.get("mcap")
    sn = snap.get(c, {})
    mcap19 = sn.get("mcap_total")
    rows1.append([c, s.get("name", u.get("name", "")), "A股",
        ai_layer(s.get("seg")), SEG_NAME.get(s.get("seg"), s.get("seg", "")),
        "",  # 主营详见归档 u_merged
        cls_cat(c)[:60] or ("c3_ext:" + e3.get("status", "")),
        round(mcap19, 1) if mcap19 else (mcap16 or ""),
        "",  # 成交额未采集（登记为未获取）
        "10-19快照" if mcap19 else "10-16"])
# 港股 55 家（纯 H 股 35 + AH 20，AH 已随 A 股计，此处登记全部）
for h in hkai:
    ah = h.get("a_code")
    rows1.append([f"hk{h['hk_code']}", "", "港股通" if h.get("connect") in ("双", "沪", "深") else "港股非通",
        "", h.get("segment", ""), (h.get("segment_note") or "")[:60],
        "AH随A股计" if ah else ("concept_only" if h.get("concept_only") else "纯H股"),
        h.get("mcap_hkd_yi") or "", "", "10-16"])
wcsv("scan_universe.csv",
     ["代码", "名称", "市场", "AI层", "子环节", "主营摘要", "机械筛查/分类状态", "市值(亿元)", "成交额", "市值日期"], rows1)

# ============ 2. financials.csv ============
# 深研池: A/B/C 档 + 扩散重点 (从 screen/c3_ext/ff 提取)
DEEP = ["300308","300502","002463","601138","hk00522",
        "002916","688183","688008","300476","688012","688072","300394","002130","300054",
        "688200","688019","300666","002409","300604","688126"]
rows2 = []
for c in DEEP:
    s = scr.get(c, {})
    e3 = c3.get(c, {})
    fin = s  # screen 内含 ocf23/24/25/h1_26, rev25, np25, capex3y, fcf3y
    cl = cls.get(c, {})
    # 单期 H1_26 FCF
    cfv = ucf.get(c, {}).get("cf", {}).get("2026-06-30", {})
    h1_fcf = (cfv.get("ocf", 0) - cfv.get("capex", 0)) if cfv else None
    rows2.append([c, s.get("name", ""), s.get("seg", ""),
        s.get("rev25"), s.get("np25"),
        snap.get(c, {}).get("pe_ttm") or cl.get("pe_ttm"),
        s.get("ocf23"), s.get("ocf24"), s.get("ocf25"), s.get("ocf_h1_26"),
        e3.get("fcf35"), e3.get("eq35"), e3.get("eq_pct_mcap"), e3.get("cover35"),
        e3.get("netdebt35"), e3.get("status"), (e3.get("post_h1") or "")[:70],
        round(h1_fcf, 2) if h1_fcf is not None else "",
        round(e3.get("fcf35", 0) / e3.get("eq35", 1), 1) if e3.get("eq35") else ""])
wcsv("financials.csv",
     ["代码", "名称", "环节", "FY25营收(亿)", "FY25归母(亿)", "PE_TTM",
      "OCF23", "OCF24", "OCF25", "OCF_H1_26", "FCF_3.5y(亿)", "股权融资3.5y(亿)",
      "融资占市值%", "OCF覆盖capex", "净借款3.5y(亿)", "第3条延长窗口判定", "期后融资",
      "H1_26单期FCF(亿)", "融资额/FCF(倍)"], rows2)
# ASMPT 手工行(业绩公告原文核验, 10-17归档)
rows2.append(["hk00522", "ASMPT", "S5", "137.4(港元)", "9.02(经调整5.01)", "46(报告)/55(经调整)",
    "未核", "10.2", "2.4", "7.3", "约+11(24FY起, 港元)", "0(未见股权融资)", "0.0", "FY25覆盖0.59",
    "", "港股B", "派息政策约50%: 2025全年1.39港元/股(含特别0.79), 2026中期0.97港元/股", "", ""])
with open(f"{OUT}/financials.csv", "w", newline="", encoding="utf-8-sig") as f:
    wr = csv.writer(f)
    wr.writerow(["代码", "名称", "环节", "FY25营收(亿)", "FY25归母(亿)", "PE_TTM",
      "OCF23", "OCF24", "OCF25", "OCF_H1_26", "FCF_3.5y(亿)", "股权融资3.5y(亿)",
      "融资占市值%", "OCF覆盖capex", "净借款3.5y(亿)", "第3条延长窗口判定", "期后融资",
      "H1_26单期FCF(亿)", "融资额/FCF(倍)"])
    wr.writerows(rows2)
print(f"financials.csv updated: {len(rows2)} rows")

# ============ 4. drawdown.csv ============
# 回撤归因: r = 6/30 → 10-19 (K线重算); dE = rev2 (同券商优先); dPE = (1+r)/(1+dE)-1
# r0630 从 px 的 K 线重算需要原始数据; 这里用 10-16 版 r0630 (screen.dd/r0630) 加 10-16→10-19 增量
rows4 = []
DD_NOTE = {
 "300308": "光模块/PCB 板块性估值压缩; 2027E 同券商 +5.6%(n=1) 跨券商 +27.1%(样本变动大), E 未降",
 "300502": "同券商 -12.5%(n=3) 明确下修, 跨券商 -31.7% 被样本变动污染; 估值杀为主, 预期中度下修",
 "002463": "2027E 同券商 +30.6%(n=2), E 在上修; 纯估值杀",
 "002916": "2027E 同券商 +21.8%, E 上修; 估值杀, 但 FCF/存货/定增为质量裂缝",
 "601138": "2027E 同券商 -2.3% 基本持平; 估值杀",
 "688183": "2027E 无券商覆盖, 无法数值拆解; 业绩预告 +68%~75% 强劲 → 推断估值杀",
 "688008": "2027E 同券商 +16.1%, E 上修; 估值杀但不便宜(PE65.6)",
 "300476": "跨券商 -20.6%(6→2 家, 污染); 归母/扣非裂缝(33.3%/12.5%) → 估值杀为主+E质量裂缝",
 "688012": "2027E 同券商 -26.0% 跨券商 -23.4%: E 真下修 → 逻辑杀(行业性, 设备 capex 放缓预期)",
 "688072": "2027E 同券商 +18.1% 上修; 估值杀, 但 FCF 为负是自身缺陷",
 "688200": "2027E 同券商 -12.6%: 逻辑杀(行业性) + 估值杀, 双杀",
 "688019": "2027E 同券商 -24.1%: 逻辑杀(行业性, CMP 材料预期下修)",
 "300394": "2027E 同券商 -0.4% 持平; 纯估值杀",
 "002130": "2027E 无券商覆盖; 1月高点早于板块(1-26), 回撤与 AI 叙事弱相关 → 行业性误伤+自身份额问题",
 "300054": "2027E 同券商 +4.0%(n=4 样本最厚); 纯估值杀",
 "300666": "2027E 同券商 +8.2% 上修; 估值杀, 但 FCF 为负",
 "002409": "2027E 同券商 0.0% 持平; 估值杀, FCF 为负是缺陷",
 "300604": "2027E 同券商 +12.7% 上修; 估值杀, FCF 为负",
 "688126": "2027E 同券商 -37.5% 跨券商 -50.0%: 逻辑杀(硅片价格+产能过剩)",
}
for c in ["300308","300502","002463","002916","601138","688183","688008","300476",
          "688012","688072","688200","688019","300394","002130","300054","300666","002409","300604","688126"]:
    p = px.get(c, {})
    s = scr.get(c, {})
    rv = rev.get(c, {})
    d_same = rv.get("pair27_med_pct"); d_cross = (rv.get("x27") or {}).get("chg_pct")
    n_same = rv.get("pair27_n")
    # r = 6/30 → 10-19 (westock 前复权, px.r0630)
    r_new = p.get("r0630")
    # dPE
    def dpe(de):
        if de is None or r_new is None: return None
        return round(((1 + r_new / 100) / (1 + de / 100) - 1) * 100, 1)
    dpe_s, dpe_c = dpe(d_same), dpe(d_cross)
    # 结论
    if d_same is None and d_cross is None: concl = "无法判定(数据不足)"
    elif (d_same or 0) <= -10 and (d_cross or 0) <= -10: concl = "逻辑杀(行业性)"
    elif (d_same or 0) >= 0 and (d_cross or 0) >= 0: concl = "估值杀"
    elif (d_same or 0) < -5: concl = "混合(估值杀为主,E 中度下修)"
    else: concl = "估值杀(E 持平或上修)"
    rows4.append([c, s.get("name", ""), p.get("close"),
        f"{p.get('hi_date','')}" if p.get("hi_date") else s.get("dd"),
        p.get("hi2026"), p.get("dd_from_hi"), p.get("r20d"), p.get("r60d"), p.get("ytd"),
        round(r_new, 1) if r_new is not None else "",
        d_same, n_same, d_cross, dpe_s, dpe_c, concl, DD_NOTE.get(c, "")])
# ASMPT (港股: 无同券商数据)
p52 = px.get("hk00522", {})
rows4.append(["hk00522", "ASMPT", p52.get("close"), "2026-06-30", p52.get("hi2026"),
    p52.get("dd_from_hi"), p52.get("r20d"), p52.get("r60d"), None, -42.0, None, None, None, None, None,
    "估值杀(推断)", "缺 2027E 一致预期, 无法数值拆解; H1 业绩公告称收入与经调整EPS胜市场预期"])
wcsv("drawdown.csv",
     ["代码", "名称", "现价(10-19)", "年内高点日", "年内高点", "自高点回撤%", "近1月%", "近3月%", "YTD%",
      "6/30→10-19%", "2027E同券商修正%", "同券商n", "2027E跨券商修正%", "PE贡献(同)%", "PE贡献(跨)%",
      "回撤结论", "归因说明"], rows4)

# ============ 8. sources.csv ============
rows8 = [
 ["1", "东财 F10 三大表(AjaxNew)", "231家财务卡", "2026-10-17版归档", "stage1/u/u_merged.json", "源1"],
 ["2", "腾讯 westock(独立后端)", "财务交叉验证+K线", "10-16版+10-19更新", "westock-data-skillhub kline", "源2"],
 ["3", "东财 push2 快照", "10-19收盘价/市值/PE_TTM/PB", "2026-10-19", "snapshot_20261019.json", "本次更新"],
 ["4", "westock K线(前复权)", "205交易日: 近1月/3月/YTD/年内高点", "2026-10-19", "px_20261019.json", "本次更新"],
 ["5", "东财 F10 ProfitForecast.ycmx + reportapi", "一致预期修正(同券商配对+跨券商)", "W1至2026-10-19", "rev2_20261019.json", "本次重跑"],
 ["6", "东财 np-anotice 公告接口", "10-17~10-20 增量公告(生益回购/澜起回购提议等)", "2026-10-19拉取", "会话记录", "本次新增"],
 ["7", "中债收益率曲线日评", "中国10Y国债 1.65%", "2026-10-19", "chinabond.com.cn", "本次新增"],
 ["8", "新华财经/美财政部", "美债10Y 约5.2-5.3%(10-01曾达5.33%,2002年来新高)", "2026-09-29~10-07", "cnfin.com/treasury.gov", "本次新增"],
 ["9", "AI_Tools QueryStockPriceInfo", "ASMPT 138.0港元(与东财K线10-16一致)", "2026-10-19查询", "MCP", "交叉验证"],
 ["10", "巨潮公告原文 111条 + 年报/半年报原文 55家", "终审证据(客户集中度/分部/订单/融资)", "2026-10-17版归档", "stage2/events.json + evidence/", "归档复用"],
 ["11", "H股招股书3份(旭创/澜起/胜宏) + ASMPT/鸿腾业绩公告", "份额数据/募资额/订单", "2026-10-17版归档", "dl/prosp/ + dl/hkv/", "归档复用"],
 ["12", "港交所港股通名单+深交所API", "港股通资格(51/55通过)", "2026-10-16", "stage0/connect_status.json", "归档复用"],
]
wcsv("sources.csv", ["序号", "来源", "内容", "时间戳", "落盘位置", "性质"], rows8)
print("Part 1 done: scan_universe / financials / drawdown / sources")
