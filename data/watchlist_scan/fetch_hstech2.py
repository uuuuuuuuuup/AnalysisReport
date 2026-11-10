#!/usr/bin/env python3
import subprocess, re
CMD = ["npx", "-y", "westock-data-skillhub@1.0.5"]
def run(args):
    r = subprocess.run(CMD + args, capture_output=True, text=True, timeout=120)
    return r.stdout

# 恒生科技指数K线（近60日，看趋势+关键位）
k = run(["kline", "hkHSTECH", "--period", "day", "--limit", "60"])
rows = []
for line in k.splitlines():
    if line.strip().startswith("|") and re.match(r'^\d{4}-\d{2}-\d{2}', line.strip("|").split("|")[0].strip()):
        c = [x.strip() for x in line.strip("|").split("|")]
        rows.append((c[0], float(c[1]), float(c[2]), float(c[4])))  # date,open,last,low
rows.sort(reverse=True)
print(f"=== 恒生科技指数 近60日 ===")
print(f"最新: {rows[0][0]} 收{rows[0][2]}")
print(f"60日高: {max(r[2] for r in rows):.1f} | 60日低: {min(r[3] for r in rows):.1f}")
# 近10日走势
print("近10日收盘:", [f"{r[2]:.0f}" for r in rows[:10]][::-1])
# 年初至今参考：查月线
km = run(["kline", "hkHSTECH", "--period", "month", "--limit", "14"])
mrows = []
for line in km.splitlines():
    if line.strip().startswith("|") and re.match(r'^\d{4}-\d{2}', line.strip("|").split("|")[0].strip()):
        c = [x.strip() for x in line.strip("|").split("|")]
        mrows.append((c[0], float(c[1]), float(c[2])))
mrows.sort(reverse=True)
print("近14月(月线, 旧→新):", [(r[0][:7], round(r[2])) for r in mrows[::-1]])
