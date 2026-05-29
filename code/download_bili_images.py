#!/usr/bin/env python3
"""
下载B站动态图片
从bilibili_dynamic JSON文件中提取图片链接并批量下载
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse

# ============ 配置 ============
JSON_FILE = "/Users/apple/Documents/分析报告/文档/战国时代姜汁汽水/bilibili_dynamic_1039025435_1779961723867.json"
OUTPUT_DIR = "/Users/apple/Documents/分析报告/文档/战国时代姜汁汽水/images"
DELAY_SECONDS = 0.5          # 下载间隔（秒）
TIMEOUT_SECONDS = 30         # 请求超时
MAX_RETRIES = 2              # 失败重试次数
# =============================


def ensure_dir(path):
    """创建目录（如果不存在）"""
    Path(path).mkdir(parents=True, exist_ok=True)


def get_ext_from_url(url):
    """从URL提取文件扩展名"""
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    if ext and len(ext) <= 5:
        return ext
    return ".jpg"


def safe_filename(name):
    """清理文件名中的非法字符"""
    invalid = '<>:"/\\|?*\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
    for ch in invalid:
        name = name.replace(ch, '_')
    return name.strip()


def download_image(url, save_path, retries=0):
    """下载单张图片，失败时重试"""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Referer": "https://t.bilibili.com/",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            }
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status == 200:
                data = resp.read()
                with open(save_path, "wb") as f:
                    f.write(data)
                return True, len(data)
            else:
                return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if retries < MAX_RETRIES:
            time.sleep(1)
            return download_image(url, save_path, retries + 1)
        return False, f"HTTPError {e.code}"
    except Exception as e:
        if retries < MAX_RETRIES:
            time.sleep(1)
            return download_image(url, save_path, retries + 1)
        return False, str(e)


def main():
    print("=" * 50)
    print("B站动态图片下载工具")
    print("=" * 50)

    # 读取JSON
    if not os.path.exists(JSON_FILE):
        print(f"错误：找不到数据文件 {JSON_FILE}")
        sys.exit(1)

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    dynamics = data.get("dynamics", [])
    scraper_info = data.get("scraper_info", {})

    total_dynamics = len(dynamics)
    total_images = scraper_info.get("total_images", 0)

    print(f"动态总数: {total_dynamics}")
    print(f"图片总数: {total_images}")
    print(f"输出目录: {OUTPUT_DIR}")
    print("-" * 50)

    ensure_dir(OUTPUT_DIR)

    # 统计
    success_count = 0
    fail_count = 0
    skipped_count = 0
    failed_items = []

    # 遍历动态
    for idx, dyn in enumerate(dynamics, 1):
        dynamic_id = str(dyn.get("dynamic_id", "unknown"))
        images = dyn.get("images", [])

        if not images:
            continue

        # 为每条动态创建子文件夹
        dyn_folder = os.path.join(OUTPUT_DIR, safe_filename(dynamic_id))
        ensure_dir(dyn_folder)

        print(f"\n[{idx}/{total_dynamics}] 动态 {dynamic_id} - {len(images)} 张图片")

        for img_idx, img in enumerate(images, 1):
            url = img.get("src", "")
            if not url:
                continue

            # 确保使用http（部分URL可能是http）
            if url.startswith("//"):
                url = "https:" + url

            ext = get_ext_from_url(url)
            filename = f"{img_idx:03d}{ext}"
            save_path = os.path.join(dyn_folder, filename)

            # 检查是否已存在（支持断点续传）
            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                print(f"  跳过已存在: {filename}")
                skipped_count += 1
                continue

            # 下载
            print(f"  下载中: {filename} ...", end=" ", flush=True)
            ok, info = download_image(url, save_path)

            if ok:
                size_kb = info / 1024
                print(f"成功 ({size_kb:.1f} KB)")
                success_count += 1
            else:
                print(f"失败 ({info})")
                fail_count += 1
                failed_items.append({
                    "dynamic_id": dynamic_id,
                    "url": url,
                    "error": info,
                    "filename": filename
                })

            # 延迟，避免触发风控
            if idx < total_dynamics or img_idx < len(images):
                time.sleep(DELAY_SECONDS)

    # 汇总
    print("\n" + "=" * 50)
    print("下载完成！")
    print("=" * 50)
    print(f"成功: {success_count}")
    print(f"跳过（已存在）: {skipped_count}")
    print(f"失败: {fail_count}")

    # 保存失败记录
    if failed_items:
        fail_log = os.path.join(OUTPUT_DIR, "_download_failed.json")
        with open(fail_log, "w", encoding="utf-8") as f:
            json.dump(failed_items, f, ensure_ascii=False, indent=2)
        print(f"\n失败记录已保存: {fail_log}")
        print("可稍后重新运行脚本，已下载的文件会自动跳过。")

    print(f"\n图片保存位置: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
