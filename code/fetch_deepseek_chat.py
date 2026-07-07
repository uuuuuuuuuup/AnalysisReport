#!/usr/bin/env python3
"""
抓取 DeepSeek 分享对话内容
策略1: 直接请求 HTML（静态内容，含 meta 信息）
策略2: 使用 Playwright 渲染 JS 后提取完整对话（推荐）
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ============ 配置 ============
SHARE_URL = "https://chat.deepseek.com/share/k9209j8ns7w3jnnxxd"
OUTPUT_DIR = "/Users/apple/Documents/分析报告/code/data"
TIMEOUT_SECONDS = 30
MAX_RETRIES = 2
# =============================


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def fetch_html(url, retries=0):
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
            for enc in ["utf-8", "gbk", "latin-1"]:
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="ignore")
    except Exception:
        if retries < MAX_RETRIES:
            return fetch_html(url, retries + 1)
        return None


def extract_meta_info(html):
    """从 meta 标签提取对话标题和摘要"""
    info = {}
    patterns = {
        "title": r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"',
        "description": r'<meta[^>]*property="og:description"[^>]*content="([^"]*)"',
        "url": r'<meta[^>]*property="og:url"[^>]*content="([^"]*)"',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            info[key] = match.group(1)
    return info


def extract_json_from_script(html):
    """尝试从 <script> 标签中提取 JSON 数据"""
    patterns = [
        r'<script[^>]*>\s*window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>',
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>',
        r'<script[^>]*>\s*(\{[\s\S]{1000,50000}\})\s*</script>',
    ]
    results = []
    for pattern in patterns:
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        for match in matches:
            try:
                data = json.loads(match.strip().rstrip(';'))
                results.append(data)
            except json.JSONDecodeError:
                pass
    return results


def fetch_with_playwright(url):
    """使用 Playwright 渲染页面并提取内容"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n⚠️  Playwright 未安装，尝试安装...")
        os.system(f"{sys.executable} -m pip install playwright")
        os.system(f"{sys.executable} -m playwright install chromium")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None, "Playwright 安装失败"

    print("  启动浏览器（首次运行可能需要下载 Chromium）...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)

        # 等待对话内容加载
        print("  等待页面渲染...")
        page.wait_for_timeout(3000)

        # 尝试多种选择器提取内容
        selectors = [
            '[class*="message"]',
            '[class*="chat"]',
            '[class*="bubble"]',
            '[class*="markdown"]',
            'article',
            '.ds-markdown',
            '.ds-chat-message',
        ]

        all_texts = []
        for selector in selectors:
            elements = page.query_selector_all(selector)
            if elements:
                print(f"  找到元素: {selector} ({len(elements)} 个)")
                for el in elements:
                    text = el.inner_text()
                    if text and len(text.strip()) > 5:
                        all_texts.append(text.strip())

        # 也获取完整的页面文本
        full_text = page.inner_text("body")

        # 尝试获取 API 响应（如果页面通过 fetch 加载）
        console_logs = []
        # 注：Playwright 可以拦截网络请求，但需要更复杂的设置

        browser.close()
        return {
            "texts": all_texts,
            "full_text": full_text,
        }, None


def save_raw_html(html, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  原始 HTML 已保存: {filepath}")


def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON 已保存: {filepath}")


def save_markdown(meta, texts, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {meta.get('title', 'DeepSeek 对话')}\n\n")
        f.write(f"来源: {SHARE_URL}\n\n")
        f.write(f"抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        if meta.get('description'):
            f.write("## 摘要\n\n")
            f.write(meta['description'])
            f.write("\n\n---\n\n")

        if texts:
            f.write("## 对话内容\n\n")
            for i, text in enumerate(texts, 1):
                f.write(f"### 消息 {i}\n\n")
                f.write(text)
                f.write("\n\n---\n\n")

    print(f"  Markdown 已保存: {filepath}")


def main():
    print("=" * 50)
    print("DeepSeek 分享页面内容抓取工具")
    print("=" * 50)
    print(f"目标 URL: {SHARE_URL}")
    print("-" * 50)

    ensure_dir(OUTPUT_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"deepseek_chat_{timestamp}"

    # === 策略1: 直接请求 HTML ===
    print("\n[1/3] 直接请求 HTML...")
    html = fetch_html(SHARE_URL)
    if html:
        html_path = os.path.join(OUTPUT_DIR, f"{base_name}.html")
        save_raw_html(html, html_path)

        meta = extract_meta_info(html)
        if meta:
            print(f"  Meta 标题: {meta.get('title', 'N/A')}")
            desc = meta.get('description', '')
            print(f"  Meta 摘要: {desc[:100]}..." if len(desc) > 100 else f"  Meta 摘要: {desc}")

        json_data = extract_json_from_script(html)
        if json_data:
            print(f"  提取到 {len(json_data)} 个 JSON 块")
            save_json(json_data, os.path.join(OUTPUT_DIR, f"{base_name}_json.json"))
    else:
        print("  获取 HTML 失败")
        meta = {}

    # === 策略2: Playwright 渲染 ===
    print("\n[2/3] 使用 Playwright 渲染页面（获取完整对话）...")
    print("  提示: 首次运行会自动下载 Chromium（约 100MB）")

    result, error = fetch_with_playwright(SHARE_URL)
    if result:
        texts = result.get("texts", [])
        full_text = result.get("full_text", "")

        print(f"  提取到 {len(texts)} 个内容块")

        # 保存完整文本
        if full_text:
            text_path = os.path.join(OUTPUT_DIR, f"{base_name}_full.txt")
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(full_text)
            print(f"  完整文本已保存: {text_path}")

        # 保存 Markdown
        save_markdown(meta, texts, os.path.join(OUTPUT_DIR, f"{base_name}.md"))
    else:
        print(f"  Playwright 失败: {error}")
        print("  已保存 meta 信息，但无法获取完整对话")

        # 即使没有 Playwright，也保存 meta 信息
        if meta:
            save_markdown(meta, [], os.path.join(OUTPUT_DIR, f"{base_name}_meta.md"))

    # === 摘要 ===
    print("\n" + "=" * 50)
    print("抓取结果")
    print("=" * 50)
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"文件前缀: {base_name}")
    if meta:
        print(f"\n对话标题: {meta.get('title', 'N/A')}")
        print(f"对话摘要:\n  {meta.get('description', 'N/A')[:200]}...")
    print("=" * 50)


if __name__ == "__main__":
    main()
