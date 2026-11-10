#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段底部信号扫描器
====================
用途：
    当出现「宽基ETF放量拉升（疑似国家队）」这类事件时，用六组彼此独立的数据
    交叉验证该位置是否属于阶段性底部区域，而不是单日反抽。

六组数据（互为独立证据，避免同源污染）：
    A 量能出清   —— 卖盘是否已经衰竭（地量）/ 放量是否异常
    B 杠杆出清   —— 融资盘是否已经卸完
    C 估值分位   —— 价格是否已经便宜（中证指数 10 年口径）
    D 情绪极值   —— 恐慌是否已经到极端
    E 主力资金   —— 大单是否停止流出（东财口径，仅看方向）
    F 国家队痕迹 —— 放量是「尾盘集中吸筹」还是「普通换手」

数据源：
    腾讯财经  ifzq.gtimg.cn / qt.gtimg.cn   —— 日K、分钟线、实时行情（主源，稳定）
    中证指数  csindex.com.cn               —— 10 年 PE 序列（估值分位）
    东财     datacenter-web / push2ex      —— 融资融券、涨跌停
    东财     push2his                      —— 主力资金流（有频率限制，失败自动跳过）

用法：
    python3 bottom_signal.py              # 全量扫描
    python3 bottom_signal.py --no-cache   # 忽略缓存重抓

判读原则：
    1) 所有阈值是启发式参考，用途是「提高/降低概率」，不给二值答案。
    2) 单一维度极端值不构成买入理由；底部是「多重出清同时发生」的过程。
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
H_TX = {"User-Agent": UA, "Referer": "https://gu.qq.com/"}
H_EM = {"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}

NO_CACHE = "--no-cache" in sys.argv
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
_CACHE = {}


# ---------------------------------------------------------------- 网络

def http_get(url, headers, timeout=20, retries=3):
    if not NO_CACHE and url in _CACHE:
        return _CACHE[url]
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            text = raw.decode("gbk", "replace") if "gtimg.com/q=" in url \
                else raw.decode("utf-8", "replace")
            _CACHE[url] = text
            return text
        except Exception as e:
            last = e
            time.sleep(0.8 * (i + 1))
    raise RuntimeError("%s" % str(last)[:50])


def tx_json(url):
    return json.loads(http_get(url, H_TX))


def em_json(url):
    return json.loads(http_get(url, H_EM))


def chart_get(url):
    return _CACHE.setdefault(url, None) if False else _CACHE.get(url)


# ---------------------------------------------------------------- 腾讯行情

INDEX_CODES = {"000001", "000300", "000905", "000852", "000688", "000985",
               "000015", "000680", "000016", "000009",
               "399001", "399006", "399371", "399372", "399005"}


def tx_code(code):
    """6 位代码 -> 腾讯代码。指数需显式判定（000001 既是上证指数也是平安银行）"""
    if code.startswith("399"):
        return "sz" + code
    if code in INDEX_CODES:
        return "sh" + code
    return ("sh" if code[0] in "56" else "sz") + code


def tx_kline(code, days=120):
    """返回 [{date,open,close,high,low,vol(手),amt(元)}]
    腾讯 qfqday 字段: [date, open, close, high, low, volume(手)]
    腾讯日K不返回成交额；对 ETF 用 close*vol*100 估算（误差<3%，已验证）
    指数不能用此法（volume 不是股数），成交额另走 csindex。"""
    tx = tx_code(code)
    end = datetime.now().strftime("%Y-%m-%d")
    start = "%d-01-01" % (datetime.now().year - 1)
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           "param=%s,day,%s,%s,%d,qfq" % (tx, start, end, days))
    j = tx_json(url)
    node = (j.get("data") or {}).get(tx) or {}
    rows = node.get("qfqday") or node.get("day") or []
    out = []
    for r in rows:
        o, c, h, l, v = float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])
        out.append({"date": r[0], "open": o, "close": c, "high": h, "low": l,
                    "vol": v, "amt": c * v * 100})
    return out


def tx_intraday(code, days=5):
    """多日分时 -> {date: [(HHMM, price, cum_vol, cum_amt)]}"""
    tx = tx_code(code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/day/query?code=%s" % tx
    j = tx_json(url)
    node = (j.get("data") or {}).get(tx) or {}
    out = {}
    for day in node.get("data") or []:
        segs = []
        for r in day.get("data") or []:
            p = r.split(" ")
            if len(p) < 4:
                continue
            segs.append((p[0], float(p[1]), float(p[2]), float(p[3])))
        if segs:
            out[day.get("date")] = segs
    return out


def tx_quote(codes):
    """批量实时行情 -> {code: {...}}"""
    txs = [tx_code(c) for c in codes]
    text = http_get("https://qt.gtimg.cn/q=" + ",".join(txs), H_TX)
    out = {}
    for line in text.strip().split("\n"):
        if "=" not in line:
            continue
        body = line.split("=", 1)[1].strip().strip('";')
        p = body.split("~")
        if len(p) < 40:
            continue
        out[p[2]] = {
            "name": p[1], "price": float(p[3] or 0), "preclose": float(p[4] or 0),
            "open": float(p[5] or 0), "vol": float(p[6] or 0),
            "amt_wan": float(p[37] or 0),          # 成交额（万元）
            "high": float(p[33] or 0), "low": float(p[34] or 0),
        }
    return out


def tx_minute(code):
    """当日分钟线 -> [(HHMM, price, cum_vol, cum_amt)]"""
    tx = tx_code(code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=%s" % tx
    j = tx_json(url)
    node = ((j.get("data") or {}).get(tx) or {}).get("data") or {}
    rows = node.get("data") or []
    out = []
    prev_amt = 0.0
    for r in rows:
        p = r.split(" ")
        if len(p) < 4:
            continue
        cum_amt = float(p[3])
        out.append({"t": p[0], "price": float(p[1]),
                    "vol": float(p[2]), "amt": cum_amt})
        prev_amt = cum_amt
    return out


# ---------------------------------------------------------------- 工具

def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def pct_rank(series, value):
    s = [x for x in series if x is not None]
    if not s:
        return None
    return sum(1 for x in s if x < value) / len(s) * 100.0


LINE = "=" * 76


def title(t):
    print("\n" + LINE)
    print(" " + t)
    print(LINE)


def row(label, value, note="", flag=""):
    print("  %-24s %-20s %s %s" % (label, value, note, flag))


# ---------------------------------------------------------------- A 量能

CORE_ETF = [("510300", "沪深300ETF华泰柏瑞"), ("510050", "上证50ETF华夏"),
            ("510500", "中证500ETF南方"), ("588000", "科创50ETF华夏"),
            ("159915", "创业板ETF易方达"), ("159919", "沪深300ETF嘉实")]


def csindex_series(code, years=10):
    """中证指数官网历史序列 -> [{date, close, turnover(亿), pe}]"""
    today = datetime.now().strftime("%Y%m%d")
    start = "%d0101" % (datetime.now().year - years)
    url = ("https://www.csindex.com.cn/csindex-home/perf/index-perf?"
           "indexCode=%s&startDate=%s&endDate=%s" % (code, start, today))
    arr = em_json(url).get("data") or []
    return [{"date": a.get("tradeDate"), "close": a.get("close"),
             "turnover": a.get("tradingValue"), "pe": a.get("peg")}
            for a in arr]


def section_volume():
    title("A 量能出清 —— 卖盘是否衰竭 / 放量是否异常")
    res = {"etf_vol": {}}

    # A1 全市场成交额（中证全指，中证官方口径，单位亿元）
    try:
        ser = csindex_series("000985", 1)
        if len(ser) > 21:
            cur = ser[-1]["turnover"]
            avg20 = mean([r["turnover"] for r in ser[-21:-1]])
            ratio = cur / avg20 if avg20 else 0
            res["turnover"] = (ser[-1]["date"], cur, avg20, ratio)
            flag = "【地量】" if ratio < 0.75 else ("【放量】" if ratio > 1.3 else "")
            row("全市场成交额", "%.0f亿" % cur,
                "20日均值 %.0f亿 = %.2fx" % (avg20, ratio), flag)
    except Exception as e:
        print("  成交额获取失败：%s" % str(e)[:40])

    # A2 核心ETF放量倍数
    for code, label in CORE_ETF:
        try:
            eks = tx_kline(code, 60)
        except Exception:
            continue
        if len(eks) < 25:
            continue
        last = eks[-1]
        avg20 = mean([k["amt"] / 1e8 for k in eks[-21:-1]])
        r = last["amt"] / 1e8 / avg20 if avg20 else 0
        rng = last["high"] - last["low"]
        pos = (last["close"] - last["low"]) / rng * 100 if rng else 50
        flag = "【异动放量】" if r > 2.0 else ""
        row(label, "%.1f亿" % (last["amt"] / 1e8),
            "%.2fx / 收盘位置%.0f%% (%s)" % (r, pos, last["date"]), flag)
        res["etf_vol"][label] = r
    return res


# ---------------------------------------------------------------- B 杠杆

def section_leverage():
    title("B 杠杆出清 —— 融资盘是否已经卸完")
    res = {}
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
           "reportName=RPTA_RZRQ_LSHJ&columns=ALL&pageSize=100"
           "&sortColumns=DIM_DATE&sortTypes=-1")
    j = em_json(url)
    rows = list(reversed(((j.get("result") or {}).get("data") or [])))
    if not rows:
        print("  两融数据为空")
        return res

    latest = rows[-1]
    rzye = [r["RZYE"] / 1e8 for r in rows]
    peak, cur = max(rzye), rzye[-1]
    dd = (cur - peak) / peak * 100
    res["rzye"] = (latest["DIM_DATE"][:10], cur, peak, dd)
    flag = "【出清较充分】" if dd < -15 else ("【仍在高位】" if dd > -8 else "")
    row("融资余额", "%.0f亿" % cur,
        "区间峰值 %.0f亿，回撤 %.1f%% (%s)" % (peak, dd, latest["DIM_DATE"][:10]), flag)

    r20 = rzye[-1] - rzye[-21] if len(rzye) > 21 else 0
    row("融资余额20日变化", "%+.0f亿" % r20, "日均 %+.1f亿" % (r20 / 20),
        "【持续偿还】" if r20 < 0 else "")

    z5, z10 = latest["RZJME5D"] / 1e8, latest["RZJME10D"] / 1e8
    res["zjme"] = (z5, z10)
    row("融资净买入 5日/10日", "%+.0f / %+.0f亿" % (z5, z10),
        "正值=净买入(加杠杆)", "【全部偿还】" if z5 < 0 and z10 < 0 else "")

    zb = latest["RZYEZB"]
    p = pct_rank([r["RZYEZB"] for r in rows], zb)
    res["rzyezb"] = (zb, p)
    row("融资余额占流通市值", "%.2f%%" % zb,
        "近%d日分位 %.0f%%" % (len(rows), p), "【杠杆低位】" if p and p < 30 else "")

    row("当日融资买入额", "%.0f亿" % (latest["RZMRE"] / 1e8), "买入盘是否仍在抄底")
    return res


# ---------------------------------------------------------------- C 估值

def section_valuation():
    title("C 估值分位 —— 价格是否已经便宜（中证指数 10 年口径）")
    res = {}
    indices = [("000300", "沪深300"), ("000016", "上证50"), ("000905", "中证500"),
               ("000852", "中证1000"), ("000688", "科创50"), ("000985", "中证全指")]
    for code, label in indices:
        try:
            ser = csindex_series(code, 10)
        except Exception as e:
            row(label, "获取失败", str(e)[:35])
            continue
        pes = [r["pe"] for r in ser if r["pe"]]
        if not pes:
            row(label, "无数据")
            continue
        cur = pes[-1]
        p = pct_rank(pes, cur)
        res[label] = (cur, p)
        flag = "【极低】" if p < 20 else ("【偏低】" if p < 35 else
                                         ("【偏高】" if p > 70 else ""))
        row(label, "PE %.2f" % cur, "10年分位 %.1f%%（%d样本）" % (p, len(pes)), flag)
    return res


# ---------------------------------------------------------------- D 情绪

def section_sentiment():
    title("D 情绪极值 —— 恐慌是否已经极端")
    res = {}

    # D1 涨跌家数（东财，接口不稳时跳过）
    try:
        j = em_json("https://push2.eastmoney.com/api/qt/ulist.np/get"
                    "?fltt=2&invt=2&fields=f12,f14,f104,f105,f106"
                    "&secids=1.000985,1.000300")
        for d in (j.get("data") or {}).get("diff") or []:
            up, down = d.get("f104"), d.get("f105")
            if not down:
                continue
            ratio = up / down
            if d["f12"] == "000985":
                res["breadth"] = (up, down, ratio)
                row("涨跌家数(中证全指)", "%d涨 / %d跌" % (up, down),
                    "涨跌比 %.2f" % ratio,
                    "【恐慌】" if ratio < 0.5 else ("【强势】" if ratio > 2 else ""))
            elif d["f12"] == "000300":
                row("涨跌家数(沪深300)", "%d涨 / %d跌" % (up, down),
                    "涨跌比 %.2f（权重股强弱）" % ratio)
    except Exception:
        print("  涨跌家数：东财接口不可用，跳过")

    # D2 涨跌停
    try:
        d = datetime.now().strftime("%Y%m%d")
        z = em_json("https://push2ex.eastmoney.com/getTopicZTPool?"
                    "ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt"
                    "&Pageindex=0&pagesize=300&sort=fbt%3Aasc&date=" + d)
        zd = z.get("data") or {}
        zt_n = zd.get("tc") or 0
        lbc = [p.get("lbc") or 0 for p in (zd.get("pool") or [])]
        max_lbc = max(lbc) if lbc else 0
        dl = em_json("https://push2ex.eastmoney.com/getTopicDTPool?"
                     "ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt"
                     "&Pageindex=0&pagesize=300&sort=fund%3Aasc&date=" + d)
        dt_n = (dl.get("data") or {}).get("tc") or 0
        res["zt"] = (zt_n, dt_n, max_lbc)
        row("涨停 / 跌停家数", "%d / %d" % (zt_n, dt_n), "最高连板 %d 板" % max_lbc,
            "【恐慌出清】" if dt_n > 40 else "")
    except Exception:
        print("  涨跌停：东财接口不可用，跳过")

    # D3 指数位置（中证官方收盘序列）
    try:
        ser = csindex_series("000985", 1)
        closes = [r["close"] for r in ser if r.get("close")]
        if len(closes) > 60:
            hi, lo, cur = max(closes[-60:]), min(closes[-60:]), closes[-1]
            pos = (cur - lo) / (hi - lo) * 100 if hi > lo else 50
            res["position"] = pos
            row("中证全指位置", "%.0f" % cur,
                "近60日区间 %.0f~%.0f，位于 %.0f%%" % (lo, hi, pos),
                "【低位】" if pos < 25 else ("【高位】" if pos > 75 else ""))
            row("距区间高点", "%+.1f%%" % ((cur - hi) / hi * 100), "")

        # D4 波动：近5日日均波幅 vs 前20日
        if len(ser) > 30:
            def absmove(rows):
                v = [abs(rows[i]["close"] / rows[i - 1]["close"] - 1) * 100
                     for i in range(1, len(rows))
                     if rows[i - 1].get("close") and rows[i].get("close")]
                return mean(v)
            r5 = absmove(ser[-6:])
            r20 = absmove(ser[-26:-6])
            res["vol_expand"] = r5 / r20 if r20 else 1
            row("近5日日均波幅", "%.2f%%" % r5,
                "前20日 %.2f%%，放大 %.2fx" % (r20, res["vol_expand"]),
                "【恐慌放大】" if r20 and r5 / r20 > 1.5 else "")
    except Exception as e:
        print("  指数位置：%s" % str(e)[:40])
    return res


# ---------------------------------------------------------------- E 资金

def section_moneyflow():
    title("E 主力资金 —— 大单是否停止流出（东财口径，仅看方向）")
    res = {}
    targets = [("1.000985", "全A(中证全指)"), ("0.399371", "国证价值"),
               ("1.000680", "科创综指"), ("0.399372", "大盘成长")]
    failed = 0
    for sec, label in targets:
        try:
            j = em_json("https://push2his.eastmoney.com/api/qt/stock/fflow/kline/get"
                        "?lmt=21&klt=101&secid=%s&fields1=f1,f2,f3,f7"
                        "&fields2=f51,f52" % sec)
            kl = ((j.get("data") or {}).get("klines") or [])
        except Exception:
            failed += 1
            continue
        vals = [float(x.split(",")[1]) / 1e8 for x in kl]
        if not vals:
            failed += 1
            continue
        d5, d10, prev5 = sum(vals[-5:]), sum(vals[-10:]), sum(vals[-10:-5])
        res[label] = (d5, d10, vals[-1])
        flag = "【流出减速】" if d5 > prev5 and d5 < 0 else ("【转为流入】" if d5 > 0 else "")
        row(label, "5日%+.0f亿" % d5,
            "10日%+.0f亿；前5日%+.0f → 近5日%+.0f" % (d10, prev5, d5), flag)
    if failed:
        print("  （%d 个指数因东财限流跳过）× 该口径长期系统性偏负，只看相对变化"
              % failed)
    return res


# ---------------------------------------------------------------- F 国家队痕迹

def section_national_team():
    title("F 国家队痕迹 —— 放量是「尾盘集中吸筹」还是「普通换手」")
    print("  判读：国家队买入 → 尾盘集中发力、收在当日高位、收盘价高于全天均价")
    print("        普通换手 → 成交额放大但收盘位置中性、尾盘无异常")
    res = {}
    for code, label in CORE_ETF[:5]:
        try:
            eks = tx_kline(code, 60)
            intra = tx_intraday(code, 5)
        except Exception as e:
            print("  %s 数据获取失败：%s" % (label, str(e)[:40]))
            continue
        if len(eks) < 5 or not intra:
            continue

        last = eks[-1]
        # 用分时最后一天补齐真实成交额（腾讯日K无成交额字段）
        day_key = last["date"].replace("-", "")
        segs = intra.get(day_key) or (list(intra.values())[0] if intra else [])
        if segs:
            real_amt = segs[-1][3]
            if real_amt > 0:
                last["amt"] = real_amt

        avg20 = mean([k["amt"] / 1e8 for k in eks[-21:-1]])
        volx = last["amt"] / 1e8 / avg20 if avg20 else 0
        rng = last["high"] - last["low"]
        close_pos = (last["close"] - last["low"]) / rng * 100 if rng else 50
        chg = (last["close"] / eks[-2]["close"] - 1) * 100 if len(eks) > 1 else 0

        # 尾盘30分钟成交占比（分时给累计成交额，需差分）+ 收盘 vs 全天均价
        tail_share = vwap_dev = None
        if len(segs) > 60:
            diffs = [(segs[i][0], segs[i][3] - segs[i - 1][3])
                     for i in range(1, len(segs))]
            total = sum(a for _, a in diffs)
            tail = sum(a for t, a in diffs if t >= "1430")
            tail_share = tail / total * 100 if total else 0
            total_vol = segs[-1][2] * 100
            vwap = segs[-1][3] / total_vol if total_vol else 0
            vwap_dev = (segs[-1][1] - vwap) / vwap * 100 if vwap else 0

        res[label] = {"volx": volx, "close_pos": close_pos, "chg": chg,
                      "tail": tail_share, "vwap": vwap_dev}
        print("\n  ▸ %s  (%s)" % (label, last["date"]))
        row("  涨跌 / 放量", "%+.2f%% / %.2fx" % (chg, volx),
            "20日均额基准 %.1f亿" % avg20)
        row("  收盘位置", "%.0f%%" % close_pos, "100%=收最高",
            "【尾盘拉升】" if close_pos > 75 else ("【尾盘杀跌】" if close_pos < 25 else ""))
        if tail_share is not None:
            row("  尾盘30分钟成交占比", "%.1f%%" % tail_share, "均匀基准≈6.7%",
                "【尾盘异常放量】" if tail_share > 12 else "")
        if vwap_dev is not None:
            row("  收盘 vs 全天均价", "%+.2f%%" % vwap_dev, "正值=收在均价上方",
                "【买盘主导】" if vwap_dev > 0.3 else
                ("【卖压主导】" if vwap_dev < -0.3 else ""))
    return res


# ---------------------------------------------------------------- 打分卡

def scorecard(A, B, C, D, E, F):
    title("综合打分卡 —— 六组信号的底部证据强度")
    items = []

    if "turnover" in A:
        _, amt, avg, ratio = A["turnover"]
        items.append(("A 量能", ratio < 0.75,
                      "成交额 %.0f亿 = %.2fx 20日均值（地量需 <0.75x）" % (amt, ratio)))
    if A.get("etf_vol"):
        mx = max(A["etf_vol"].values())
        items.append(("A 量能", mx > 2.0,
                      "核心ETF最大放量 %.2fx（>2.0x 表示资金异动）" % mx))

    if "rzye" in B:
        _, cur, peak, dd = B["rzye"]
        items.append(("B 杠杆", dd < -15,
                      "融资余额距峰值 %.1f%%（<-15%% 算卸得干净）" % dd))
    if "zjme" in B:
        z5, z10 = B["zjme"]
        items.append(("B 杠杆", z5 > 0,
                      "近5日融资净买入 %+.0f亿（转正=杠杆回头）" % z5))
    if "rzyezb" in B:
        zb, p = B["rzyezb"]
        items.append(("B 杠杆", p is not None and p < 30,
                      "融资余额占流通市值 %.2f%%，历史分位 %.0f%%" % (zb, p or 0)))

    if C:
        ps = [p for _, p in C.values() if p is not None]
        if ps:
            items.append(("C 估值", max(ps) < 35,
                          "主要指数最高10年分位 %.0f%%（<35%% 整体不贵）" % max(ps)))
            items.append(("C 估值", sum(1 for p in ps if p < 20) >= 3,
                          "%d/%d 个指数处于10年20%%分位以下"
                          % (sum(1 for p in ps if p < 20), len(ps))))

    if "breadth" in D:
        _, _, ratio = D["breadth"]
        items.append(("D 情绪", ratio < 0.6, "涨跌比 %.2f（<0.6 为恐慌）" % ratio))
    if "zt" in D:
        zt, dt, lbc = D["zt"]
        items.append(("D 情绪", dt > 40, "跌停 %d 家（>40 为恐慌出清）" % dt))
        items.append(("D 情绪", lbc <= 3,
                      "最高连板 %d 板（<=3 板表示投机情绪已死）" % lbc))
    if "position" in D:
        items.append(("D 情绪", D["position"] < 30,
                      "指数位于60日区间 %.0f%% 分位（<30%% 为低位）" % D["position"]))

    if "全A(中证全指)" in E:
        d5, d10, _ = E["全A(中证全指)"]
        items.append(("E 资金", d5 > -200,
                      "全A近5日主力 %+.0f亿（>-200亿 为流出趋缓）" % d5))

    if F:
        hits = sum(1 for v in F.values() if v["close_pos"] > 70 and v["volx"] > 1.5)
        items.append(("F 痕迹", hits >= 2,
                      "%d/%d 只ETF出现「放量+收高位」组合" % (hits, len(F))))
        tails = [v["tail"] for v in F.values() if v["tail"] is not None]
        if tails:
            items.append(("F 痕迹", max(tails) > 12,
                          "最高尾盘30分钟成交占比 %.1f%%（>12%% 异常）" % max(tails)))

    groups = {}
    for g, ok, desc in items:
        groups.setdefault(g, []).append((ok, desc))

    print()
    total_ok = total_n = 0
    for g in sorted(groups):
        lst = groups[g]
        n_ok = sum(1 for ok, _ in lst if ok)
        total_ok += n_ok
        total_n += len(lst)
        print("  %s  %s  %d/%d" % (g, "■" * n_ok + "□" * (len(lst) - n_ok), n_ok, len(lst)))
        for ok, desc in lst:
            print("      %s %s" % ("✔" if ok else "✘", desc))

    print("\n  " + "─" * 62)
    pct = total_ok / total_n * 100 if total_n else 0
    print("  合计：%d/%d 项 = %.0f%%" % (total_ok, total_n, pct))
    if pct >= 70:
        v = "底部证据较强 —— 仍需「放量拉升后3日内不破前低」确认"
    elif pct >= 45:
        v = "底部证据中等 —— 「可能接近」而非「已经到」"
    else:
        v = "底部证据不足 —— 单日拉升更像反抽而非底部"
    print("  判读：%s" % v)
    print("\n  提醒：单一维度极端值（如PE分位极低）不构成买入理由；")
    print("        底部是「多重出清同时发生」的过程，不是某一天的形态。")


# ---------------------------------------------------------------- main

def main():
    print("=" * 76)
    print("  阶段底部信号扫描器   %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("  数据源：腾讯行情 / 中证指数官网 / 东方财富")
    print("=" * 76)

    def run(fn, label, empty):
        try:
            return fn()
        except Exception as e:
            print("\n  [%s] 数据源不可用：%s" % (label, str(e)[:60]))
            return empty

    A = run(section_volume, "A量能", {"etf_vol": {}})
    B = run(section_leverage, "B杠杆", {})
    C = run(section_valuation, "C估值", {})
    D = run(section_sentiment, "D情绪", {})
    E = run(section_moneyflow, "E资金", {})
    F = run(section_national_team, "F国家队", {})

    scorecard(A, B, C, D, E, F)


if __name__ == "__main__":
    main()
