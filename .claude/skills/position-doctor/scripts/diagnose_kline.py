#!/usr/bin/env python3
"""
position-doctor 趋势/量价计算脚本（零依赖，仅标准库）

【模型使用方式】把 K 线工具返回的原始内容【原样】写入文件，不要手工整理格式：
    python3 diagnose_kline.py <kline文件>

脚本自动适配以下格式（按顺序尝试）：
  1. {"bars": [{date,open,high,low,close,volume}, ...]}      标准格式
  2. [{...}, ...]                                             纯数组
  3. {"data": ...} / {"result": ...} / {"klines": ...} 等包装壳
  4. 东方财富 CSV 行: {"klines": ["2026-01-01,14.5,14.8,14.3,14.7,123456", ...]}
     （东财列序: date,open,close,high,low,volume —— 脚本自动检测并校正）
  5. 混在说明文字中的 JSON（自动提取 [...] 段）
  字段名自动识别中/英/缩写别名；自动按日期排序、去重、清洗坏行。

输出：stdout JSON，全部为"事实层"指标（判断由 AI 在 skill 规则下完成）。
解析失败时输出 {"error": ..., "hint": ..., "raw_head": ...}，照 hint 修正后重试。
"""
import json
import re
import sys

FIELD_ALIASES = {
    "date": ["date", "day", "time", "trade_date", "datetime", "日期", "交易日期"],
    "open": ["open", "o", "开盘", "开盘价"],
    "high": ["high", "h", "最高", "最高价"],
    "low": ["low", "l", "最低", "最低价"],
    "close": ["close", "c", "last", "收盘", "收盘价", "最新价"],
    "volume": ["volume", "vol", "v", "成交量"],
}


def parse_markdown_table(raw):
    """解析 Markdown 表格（westock-data CLI 的输出格式）：
    | date | open | last | high | low | volume | ...
    返回字典行列表，失败返回 None。"""
    lines = [l.strip() for l in raw.splitlines() if l.strip().startswith("|")]
    if len(lines) < 3:
        return None
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    rows = []
    for l in lines[1:]:
        cells = [c.strip() for c in l.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):  # 分隔行
            continue
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows or None


def err(msg, hint, raw):
    print(json.dumps({
        "error": msg,
        "hint": hint,
        "raw_head": raw[:300],
    }, ensure_ascii=False, indent=2))
    sys.exit(1)


def extract_json(raw):
    """从原始文本中提取 JSON：先整体解析，失败则提取最长的 [...] 或 {...} 段。"""
    raw = raw.strip()
    for candidate in (raw,):
        try:
            return json.loads(candidate)
        except Exception:
            pass
    # 提取文本中嵌套的 JSON 段（贪婪匹配最长的 [ ... ] 或 { ... }）
    best = None
    for m in re.finditer(r"[\[{]", raw):
        open_ch = m.group()
        close_ch = "]" if open_ch == "[" else "}"
        depth = 0
        for j in range(m.start(), len(raw)):
            if raw[j] == open_ch:
                depth += 1
            elif raw[j] == close_ch:
                depth -= 1
                if depth == 0:
                    chunk = raw[m.start(): j + 1]
                    try:
                        obj = json.loads(chunk)
                        if best is None or len(chunk) > len(json.dumps(best)):
                            best = obj
                    except Exception:
                        pass
                    break
    return best


def unwrap(obj):
    """剥包装壳：{"data": ...} / {"result": ...} / {"bars": ...} / {"klines": ...}。"""
    for _ in range(4):
        if isinstance(obj, dict):
            for key in ("bars", "klines", "data", "result", "list", "items", "rows"):
                if key in obj and isinstance(obj[key], (list, dict)):
                    obj = obj[key]
                    break
            else:
                # 字典里没有已知列表键：若唯一值是列表则取之
                lists = [v for v in obj.values() if isinstance(v, list) and v]
                if len(lists) == 1:
                    obj = lists[0]
                else:
                    return obj
        else:
            return obj
    return obj


def norm_number(x):
    if x is None or x == "" or x == "-":
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(",", "").replace("%", ""))
    except Exception:
        return None


def bar_from_dict(d):
    lower = {str(k).lower(): v for k, v in d.items()}
    bar = {}
    for field, names in FIELD_ALIASES.items():
        for name in names:
            if name.lower() in lower:
                bar[field] = lower[name.lower()]
                break
    if "date" not in bar:
        return None
    for f in ("open", "high", "low", "close", "volume"):
        bar[f] = norm_number(bar.get(f))
    bar["date"] = str(bar["date"])[:10]
    return bar


def bar_from_csv_line(s):
    """字符串行，如东方财富风格 "date,open,close,high,low,volume[,amount,...]"。
    返回两种候选列序，物理校验在 normalize() 里统一做。"""
    parts = [p.strip() for p in str(s).split(",")]
    if len(parts) < 6:
        return None

    def build(i_open, i_high, i_low, i_close, i_vol):
        return {
            "date": parts[0][:10],
            "open": norm_number(parts[i_open]),
            "high": norm_number(parts[i_high]),
            "low": norm_number(parts[i_low]),
            "close": norm_number(parts[i_close]),
            "volume": norm_number(parts[i_vol]),
        }

    # 东财序: date,open,close,high,low,volume | 自然序: date,open,high,low,close,volume
    return {"eastmoney": build(1, 3, 4, 2, 5), "natural": build(1, 2, 3, 4, 5)}


def physically_valid(bar):
    """K线物理约束：high>=low、high>=open/close、low<=open/close、价格非负。"""
    o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
    if None in (o, h, l, c):
        return False
    if min(o, h, l, c) < 0:
        return False
    return h >= l and h >= max(o, c) * 0.995 and l <= min(o, c) * 1.005


def normalize(items):
    """把解析出的列表规整为干净 bars，返回 (bars, stats)。"""
    dict_items = [it for it in items if isinstance(it, dict)]
    str_items = [it for it in items if isinstance(it, str) and "," in it]

    bars, dropped = [], 0
    if dict_items:
        for it in dict_items:
            b = bar_from_dict(it)
            if b is None:
                dropped += 1
                continue
            if not physically_valid(b):
                dropped += 1
                continue
            bars.append(b)
    elif str_items:
        # 先试东财列序，物理校验通过率 <80% 则换自然序
        candidates = [bar_from_csv_line(s) for s in str_items]
        candidates = [c for c in candidates if c]
        if candidates:
            for order in ("eastmoney", "natural"):
                trial = [c[order] for c in candidates]
                valid = sum(1 for b in trial if physically_valid(b))
                if valid >= max(1, int(len(trial) * 0.8)):
                    bars = [b for b in trial if physically_valid(b)]
                    dropped = len(trial) - len(bars)
                    break
            else:
                dropped = len(candidates)
    # 排序去重
    bars.sort(key=lambda b: b["date"])
    deduped = []
    for b in bars:
        if deduped and deduped[-1]["date"] == b["date"]:
            deduped[-1] = b  # 重复日期取后者
        else:
            deduped.append(b)
    return deduped, {"parsed": len(deduped), "dropped": dropped}


def load_bars(path):
    raw = open(path, encoding="utf-8").read()
    if not raw.strip():
        err("文件为空", "请把K线工具返回的内容写入文件后再运行", raw)
    obj = extract_json(raw)
    if obj is None:
        # JSON 提取失败 → 尝试 Markdown 表格（westock-data CLI 的输出格式）
        obj = parse_markdown_table(raw)
    if obj is None:
        err("无法从文件中提取JSON或Markdown表格",
            "文件应包含: JSON数组/对象、或 Markdown 表格（| date | open | ... |）。"
            "若是纯文本表格，请改用支持JSON输出的工具重新取数",
            raw)
    items = unwrap(obj)
    if isinstance(items, dict):
        # 字典形态：可能是 {date: {open:...}} 或 {date: [o,h,l,c,v]}
        if items and all(isinstance(v, (dict, list)) for v in items.values()):
            rows = []
            for k, v in items.items():
                if isinstance(v, dict):
                    row = dict(v)
                    row.setdefault("date", k)
                    rows.append(row)
                elif isinstance(v, list) and len(v) >= 5:
                    row = {"date": k, "open": v[0], "high": v[1], "low": v[2], "close": v[3]}
                    if len(v) > 5:
                        row["volume"] = v[5]
                    rows.append(row)
            items = rows
    if not isinstance(items, list) or not items:
        err("JSON中未找到K线列表",
            "期望: 数组，或含 bars/klines/data/result 键的对象。键名示例: "
            + (", ".join(list(obj.keys())[:8]) if isinstance(obj, dict) else "N/A"),
            raw)
    bars, stats = normalize(items)
    if len(bars) < 10:
        err(f"有效K线不足10根（解析出{len(bars)}根）",
            "请检查: 1)字段是否含 date/open/high/low/close; 2)数值是否为数字; "
            f"3)原始样本: {json.dumps(items[0], ensure_ascii=False)[:200]}",
            raw)
    return bars, stats


# ---------- 指标计算 ----------

def sma(vals, n):
    return round(sum(vals[-n:]) / n, 4) if len(vals) >= n else None


def macd(closes):
    """标准 MACD(12,26,9)。需要 >=35 根K线。"""
    if len(closes) < 35:
        return None
    k12, k26, k9 = 2 / 13, 2 / 27, 2 / 10
    e12 = sum(closes[:12]) / 12
    e26 = sum(closes[:26]) / 26
    difs = []
    for i, c in enumerate(closes):
        if i >= 12:
            e12 = c * k12 + e12 * (1 - k12)
        if i >= 26:
            e26 = c * k26 + e26 * (1 - k26)
        if i >= 26:
            difs.append(e12 - e26)
    if len(difs) < 9:
        return None
    dea = sum(difs[:9]) / 9
    dea_series = [dea]
    for d in difs[9:]:
        dea = d * k9 + dea * (1 - k9)
        dea_series.append(dea)
    dif_now = difs[-1]
    hist_now = round((dif_now - dea_series[-1]) * 2, 4)
    hist_prev = round((difs[-2] - dea_series[-2]) * 2, 4) if len(difs) >= 2 else None
    return {
        "dif": round(dif_now, 4),
        "dea": round(dea_series[-1], 4),
        "hist": hist_now,
        "above_zero": dif_now > 0,
        "hist_shrinking": (abs(hist_now) < abs(hist_prev)) if hist_prev is not None else None,
    }


def atr(bars, n=14):
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return round(sum(trs[-n:]) / n, 4)


def swings(bars, w=5):
    """局部极值摆动点。大窗口找不到足够点时自动降级到小窗口。
    最后 window 根内若出现更极端的价格，记为未确认候选点（forming=True）。"""
    highs, lows = [], []
    window = w
    for window in (w, 3, 2):
        highs, lows = [], []
        for i in range(window, len(bars) - window):
            win = bars[i - window : i + window + 1]
            if bars[i]["high"] == max(b["high"] for b in win):
                if not highs or highs[-1]["price"] != bars[i]["high"]:
                    highs.append({"date": bars[i]["date"], "price": bars[i]["high"]})
            if bars[i]["low"] == min(b["low"] for b in win):
                if not lows or lows[-1]["price"] != bars[i]["low"]:
                    lows.append({"date": bars[i]["date"], "price": bars[i]["low"]})
        if len(highs) >= 2 and len(lows) >= 2:
            break
    tail = bars[-window:]
    th = max(tail, key=lambda b: b["high"])
    tl = min(tail, key=lambda b: b["low"])
    if not highs or (th["high"] >= highs[-1]["price"] and th["date"] != highs[-1]["date"]):
        highs.append({"date": th["date"], "price": th["high"], "forming": True})
    if not lows or (tl["low"] <= lows[-1]["price"] and tl["date"] != lows[-1]["date"]):
        lows.append({"date": tl["date"], "price": tl["low"], "forming": True})
    return highs, lows


def trend_structure(highs, lows, bars):
    """道氏结构：最近摆动点的递升/递降。摆动点不足时用60日极值位置做单边兜底。"""
    h, l = highs[-3:], lows[-3:]
    if len(h) >= 2 and len(l) >= 2:
        h_up = all(h[i]["price"] < h[i + 1]["price"] for i in range(len(h) - 1))
        h_dn = all(h[i]["price"] > h[i + 1]["price"] for i in range(len(h) - 1))
        l_up = all(l[i]["price"] < l[i + 1]["price"] for i in range(len(l) - 1))
        l_dn = all(l[i]["price"] > l[i + 1]["price"] for i in range(len(l) - 1))
        if h_up and l_up:
            return "up", "高点递升+低点递升，上升结构"
        if h_dn and l_dn:
            return "down", "高点递降+低点递降，下降结构"
        parts = []
        parts.append("高点递升" if h_up else ("高点递降" if h_dn else "高点无方向"))
        parts.append("低点递升" if l_up else ("低点递降" if l_dn else "低点无方向"))
        return "range", "，".join(parts) + "，结构混合/震荡"
    # 单边行情兜底：近期是否处于60日极值区域
    if len(bars) >= 20:
        recent = bars[-5:]
        lo60 = min(b["low"] for b in bars[-60:])
        hi60 = max(b["high"] for b in bars[-60:])
        if any(b["low"] <= lo60 * 1.005 for b in recent):
            return "down", "摆动点不足，但当前处于60日新低区域：单边下跌结构，期间无有效反弹"
        if any(b["high"] >= hi60 * 0.995 for b in recent):
            return "up", "摆动点不足，但当前处于60日新高区域：单边上涨结构"
    return "unknown", "摆动点不足，无法判断结构（请结合更长的周K线人工判断）"


def volume_profile(bars):
    """回调量比：近5日均量 / 过去60日最高5日均量。缩量回调时该值显著 <1。"""
    vols = [b["volume"] for b in bars if b.get("volume")]
    if len(vols) < 25:
        return None
    recent5 = sum(vols[-5:]) / 5
    window = vols[-60:] if len(vols) >= 60 else vols
    peak5 = max(sum(window[i : i + 5]) / 5 for i in range(len(window) - 4))
    ratio = round(recent5 / peak5, 3) if peak5 > 0 else None
    last = vols[-1]
    avg20 = sum(vols[-20:]) / 20
    return {
        "pullback_vol_ratio": ratio,
        "last_vol_vs_20d_avg": round(last / avg20, 3) if avg20 > 0 else None,
        "detail": f"近5日均量为近{len(window)}日峰值5日均量的 {ratio * 100:.0f}%（<50% 为明显缩量）",
    }


def returns(closes):
    out = {}
    for n in (5, 10, 20, 60):
        out[f"d{n}"] = round((closes[-1] / closes[-1 - n] - 1) * 100, 2) if len(closes) > n else None
    return out


def breakdown_check(bars):
    """破位事实检测：收盘 < 前20日最低价 = 破位；收盘贴线(±0.5%) = 临界踩线；
    最新量 > 1.5×20日均量 = 放量。"""
    if len(bars) < 21:
        return None
    last = bars[-1]
    prev20_low = min(b["low"] for b in bars[-21:-1])
    vols = [b["volume"] for b in bars[-21:-1] if b.get("volume")]
    avg20_vol = sum(vols) / len(vols) if vols else None
    price_break = last["close"] < prev20_low
    at_edge = (not price_break) and prev20_low > 0 and abs(last["close"] - prev20_low) / prev20_low < 0.005
    vol_surge = bool(avg20_vol and last.get("volume") and last["volume"] > 1.5 * avg20_vol)
    return {
        "price_below_20d_low": price_break,
        "at_20d_low_edge": bool(at_edge),
        "volume_surge_1_5x": vol_surge,
        "breakdown_confirmed": bool(price_break and vol_surge),
        "prev20_low": round(prev20_low, 4),
    }


def ma_status(closes):
    out = {}
    for n in (5, 10, 20, 60):
        out[f"ma{n}"] = sma(closes, n)
    if all(out[f"ma{n}"] is not None for n in (5, 10, 20, 60)):
        out["bullish_alignment"] = out["ma5"] > out["ma10"] > out["ma20"] > out["ma60"]
        out["price_above_ma20"] = closes[-1] > out["ma20"]
        if len(closes) >= 23:
            prev_diff = sma(closes[:-3], 5) - sma(closes[:-3], 20)
            curr_diff = out["ma5"] - out["ma20"]
            if prev_diff >= 0 and curr_diff < 0:
                out["cross_5_20"] = "death_cross_recent"
            elif prev_diff <= 0 and curr_diff > 0:
                out["cross_5_20"] = "golden_cross_recent"
            else:
                out["cross_5_20"] = "none"
    return out


def main():
    if len(sys.argv) != 2:
        print("用法: python3 diagnose_kline.py <kline文件>", file=sys.stderr)
        sys.exit(1)
    bars, stats = load_bars(sys.argv[1])
    closes = [b["close"] for b in bars]
    highs, lows = swings(bars)
    trend, trend_detail = trend_structure(highs, lows, bars)

    result = {
        "as_of": bars[-1]["date"],
        "last_close": closes[-1],
        "data_quality": {
            "bars_used": stats["parsed"],
            "bars_dropped": stats["dropped"],
            "date_range": [bars[0]["date"], bars[-1]["date"]],
        },
        "returns_pct": returns(closes),
        "structure": {
            "trend": trend,
            "detail": trend_detail,
            "recent_swing_highs": highs[-3:],
            "recent_swing_lows": lows[-3:],
        },
        "ma": ma_status(closes),
        "volume": volume_profile(bars),
        "macd": macd(closes),
        "atr14": atr(bars),
        "breakdown": breakdown_check(bars),
        "range_60d": {
            "high": round(max(b["high"] for b in bars[-60:]), 4),
            "low": round(min(b["low"] for b in bars[-60:]), 4),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
