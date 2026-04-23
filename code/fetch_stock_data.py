import requests
import json
import os
from datetime import datetime


def fetch_stock_data():
    """
    调用雪球股票筛选接口，循环获取前 480 条数据（每次 60 条，共 8 次）
    将数据保存到 JSON 文件中
    """
    url = "https://stock.xueqiu.com/v5/stock/screener/quote/list.json"
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "origin": "https://xueqiu.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://xueqiu.com/",
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    }
    
    cookies = {
        "xq_is_login": "1",
        "u": "5406363485",
        "s": "c011mn0txk",
        "cookiesu": "381750641647951",
        "device_id": "ee6db4e96312a6fc761815db7bff20",
        "bid": "0c06fc3722048407de04c145db7bff20_mfurxmxp",
        "xq_a_token": "01389e8df6537ad0b66222179455b9969b4c8ef4",
        "xqat": "01389e8df6537ad0b66222179455b9969b4c8ef4",
        "xq_id_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ1aWQiOjU0MDYzNjM0ODUsImlzcyI6InVjIiwiZXhwIjoxNzc5NTIxNzIwLCJjdG0iOjE3NzY5Mjk3MjAwODksImNpZCI6ImQ5ZDBuNEFadXAifQ.JQdFmpqth3VBd79uitEFUEHkiAa8TWTCMw0GzYBQ9y3lSUp4qJzTk9LBdferAibDX1QI0U_BJqFU4IEr7hfqh6ZyAp7sreztf5CxhKVe4E_ARXVcEOnEF8piNyjWQxRBuHzY6CYaeMoCRJe3EpvwawfadG3_Jk7Ndnj-HYRDwfIQegsM_31XfaGGFL2Mcs_BGbR59rCQshd0RJ-6ZpnUONuBrK4xTf2JQbVJKm-1_kCk6LpRkSNrykFxZM0S-81F4BMGUGEFlU3vPPw1v4eYLNB0vQ9vULsRKpAR1HMPHySm_X1GLhzT8fYOUYNC1uUUgYV_xC65N_abrIEzyYVDQw",
        "xq_r_token": "c39b0596af7d2cbb0376691d019328745961cbe4",
        "Hm_lvt_1db88642e346389874251b5a1eded6e3": "1776674884,1776688204,1776776276,1776929721",
        "HMACCOUNT": "A3F7EC3F2D086C6B",
        "Hm_lpvt_1db88642e346389874251b5a1eded6e3": "1776929968"
    }
    
    all_data = []
    page_size = 60
    total_pages = 8
    
    print(f"开始获取数据，共获取 {total_pages} 页，每页 {page_size} 条...")
    
    for page in range(1, total_pages + 1):
        params = {
            "page": page,
            "size": page_size,
            "order": "desc",
            "order_by": "dividend_yield",
            "market": "CN",
            "type": "sh_sz"
        }
        
        try:
            response = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("data"):
                all_data.append(data["data"])
                print(f"第 {page} 页获取成功，数据条数：{len(data['data'])}")
            else:
                print(f"第 {page} 页数据为空")
                
        except requests.exceptions.RequestException as e:
            print(f"第 {page} 页请求失败：{e}")
        except json.JSONDecodeError as e:
            print(f"第 {page} 页 JSON 解析失败：{e}")
    
    if all_data:
        os.makedirs("/Users/apple/Documents/分析报告/code/data", exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"/Users/apple/Documents/分析报告/code/data/stock_data_{timestamp}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n数据保存成功！")
        print(f"保存路径：{output_file}")
        print(f"总共获取 {len(all_data)} 页数据")
        
        return all_data
    else:
        print("未获取到任何数据")
        return None


if __name__ == "__main__":
    fetch_stock_data()
