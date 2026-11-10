#!/usr/bin/env python3
# 恒生科技指数+腾讯估值数据抓取（落盘不走上下文）
import subprocess, re, json

CMD = ["npx", "-y", "westock-data-skillhub@1.0.5"]

def run(args):
    r = subprocess.run(CMD + args, capture_output=True, text=True, timeout=120)
    return r.stdout

out = {}
# 1. 找恒生科技指数代码
s = run(["search", "恒生科技", "--type", "index"])
out["search_index"] = "\n".join(s.splitlines()[:12])
print(out["search_index"])
