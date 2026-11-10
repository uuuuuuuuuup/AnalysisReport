#!/usr/bin/env python3
"""同券商前后预测修正 + 跨券商中位数 (零 LLM)。
来源: 东财 F10 ProfitForecast.ycmx (券商明细, 含 NP/EPS) + reportapi.eastmoney.com/report/list (研报列表, 仅 EPS)。
对每家公司, 按"券商(规范化名称)"建时间序列, 取:
  before = 该券商在 <=2026-06-30 的最近一次预测;  after = 该券商在 >=2026-08-25 的最近一次预测
  同券商修正 = after/before - 1  (2026E / 2027E 的 EPS)
并给跨券商中位数: W0=[2026-04-01,06-30] 对 W1=[2026-08-25, 10-17]。
用法: python3 -I rev2.py <codes.txt|c1,c2,..> <out.json>
"""
import json
import re
import statistics as st
import sys
import time
import urllib.parse
import urllib.request

H = {"User-Agent": "Mozilla/5.0", "Referer": "https://emweb.securities.eastmoney.com/"}
CUT0, CUT1 = "2026-06-30", "2026-08-25"
W0 = ("2026-04-01", "2026-06-30")
W1 = ("2026-08-25", "2026-10-19")


def mk(c):
    return ("SH" if c.startswith("6") else "SZ") + c


def getj(url, tries=3):
    err = ""
    for i in range(tries):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30).read()
            try:
                return json.loads(raw.decode())
            except UnicodeDecodeError:
                import gzip
                return json.loads(gzip.decompress(raw).decode())
        except Exception as e:  # noqa
            err = repr(e)[:80]
            time.sleep(1.5 + 2 * i)
    return {"_error": err}


def norm(org):
    o = org or ""
    for s in ("有限责任公司", "股份有限公司", "有限公司", "（中国）", "(中国)", "证券", "国际", "研究所", "研究"):
        o = o.replace(s, "")
    return o.strip()


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def collect(code):
    rows = []  # (date, org, eps26, eps27, np26, np27, src)
    d = getj(f"https://emweb.securities.eastmoney.com/PC_HSF10/ProfitForecast/PageAjax?code={mk(code)}")
    for r in (d.get("ycmx") or []) if "_error" not in d else []:
        e = {}
        n = {}
        for i in (1, 2, 3, 4):
            y, mkk = r.get(f"YEAR{i}"), r.get(f"YEAR_MARK{i}")
            if mkk == "E":
                e[str(y)] = fnum(r.get(f"EPS{i}"))
                v = fnum(r.get(f"PARENT_NETPROFIT{i}"))
                n[str(y)] = v / 1e8 if v is not None else None
        rows.append(((r.get("PUBLISH_DATE") or "")[:10], norm(r.get("ORG_NAME_ABBR")), e.get("2026"), e.get("2027"), n.get("2026"), n.get("2027"), "ycmx"))
    q = dict(industryCode="*", pageSize=100, industry="*", rating="", ratingChange="", beginTime="2026-01-01", endTime="2026-10-17", pageNo=1,
             fields="", qType=0, orgCode="", code=code, rcode="", p=1, pageNum=1, pageNumber=1)
    d2 = getj("https://reportapi.eastmoney.com/report/list?" + urllib.parse.urlencode(q))
    for r in (d2.get("data") or []) if "_error" not in d2 else []:
        rows.append(((r.get("publishDate") or "")[:10], norm(r.get("orgSName")), fnum(r.get("predictThisYearEps")), fnum(r.get("predictNextYearEps")), None, None, "rpt"))
    # 去重 (date, org)
    seen, out = set(), []
    for x in sorted(rows, key=lambda z: (z[0], z[6])):
        k = (x[0], x[1])
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out, d


def analyze(code):
    rows, raw = collect(code)
    by = {}
    for x in rows:
        by.setdefault(x[1], []).append(x)
    pair27, pair26, det = [], [], []
    for org, lst in by.items():
        lst.sort()
        b = [x for x in lst if x[0] <= CUT0]
        a = [x for x in lst if x[0] >= CUT1]
        if b and a:
            bb, aa = b[-1], a[-1]
            if bb[3] and aa[3]:
                pair27.append(aa[3] / bb[3] - 1)
                det.append(f"{org}:{bb[0]}→{aa[0]} 27E {bb[3]:.2f}→{aa[3]:.2f}")
            if bb[2] and aa[2]:
                pair26.append(aa[2] / bb[2] - 1)

    def win(lo, hi, idx):
        v = [x[idx] for x in rows if lo <= x[0] <= hi and x[idx]]
        return (round(st.median(v), 3), len(v)) if v else (None, 0)
    m27_0, n27_0 = win(*W0, 3)
    m27_1, n27_1 = win(*W1, 3)
    m26_0, n26_0 = win(*W0, 2)
    m26_1, n26_1 = win(*W1, 2)
    cons = {}
    for r in (raw.get("yctj_list") or []) if "_error" not in raw else []:
        if r.get("YEAR_MARK") == "E":
            cons[str(r["YEAR"])] = {"eps": r.get("EPS"), "eps_1m": r.get("EPS_LASTMONTHS"), "np_yi": (r.get("PARENT_NETPROFIT") or 0) / 1e8 or None, "n": r.get("EPS_COUNT")}
    o = {"n_rows": len(rows), "pair27_n": len(pair27), "pair27_med_pct": round(st.median(pair27) * 100, 1) if pair27 else None,
         "pair26_n": len(pair26), "pair26_med_pct": round(st.median(pair26) * 100, 1) if pair26 else None,
         "x27": {"w0": [m27_0, n27_0], "w1": [m27_1, n27_1], "chg_pct": round((m27_1 / m27_0 - 1) * 100, 1) if (m27_0 and m27_1 and n27_0 >= 2 and n27_1 >= 2) else None},
         "x26": {"w0": [m26_0, n26_0], "w1": [m26_1, n26_1], "chg_pct": round((m26_1 / m26_0 - 1) * 100, 1) if (m26_0 and m26_1 and n26_0 >= 2 and n26_1 >= 2) else None},
         "cons": cons, "pair_detail": det[:8]}
    return o


def main():
    arg = sys.argv[1]
    codes = open(arg).read().split() if arg.endswith(".txt") else arg.split(",")
    out = {}
    for c in codes:
        try:
            out[c] = analyze(c)
        except Exception as e:  # noqa
            out[c] = {"error": repr(e)[:100]}
        time.sleep(0.25)
        print(c, out[c].get("pair27_n"), out[c].get("pair27_med_pct"), out[c].get("x27", {}).get("chg_pct"), flush=True)
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
