#!/usr/bin/env python3
"""
抓取 DeepSeek 分享对话内容（修复版）

修复说明：
  原脚本通过 Playwright 渲染页面 + CSS 选择器提取文本，存在以下缺陷：
    1. DeepSeek 是 SPA，HTML 仅含 <div id="root"></div>，所有数据通过 JS 动态加载
    2. 仅等待 3 秒且未滚动，255 轮对话无法全部渲染到 DOM
    3. 通用 CSS 选择器抓不全消息，且无法区分 USER/ASSISTANT/思考过程
    4. 仅能拿到渲染后可见文本，丢失 thinking、search 等结构化信息

  修复方案：
    主策略：直接调用 DeepSeek 公开 API
            GET https://chat.deepseek.com/api/v0/share/content?share_id={share_id}
            返回完整 JSON，包含所有消息（含 thinking、tool 调用等）
    兜底策略：Playwright 渲染并拦截 API 响应（应对直接请求被拦的情况）

输出：
    {prefix}.json       原始 API 响应（最完整数据）
    {prefix}.md         结构化 Markdown（按轮次渲染 USER/ASSISTANT/思考）
    {prefix}_meta.json  meta 标签摘要
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime

# ============ 配置 ============
SHARE_URL = "https://chat.deepseek.com/share/eon4dmm0bs0fy0ofib"
OUTPUT_DIR = "/Users/apple/Documents/分析报告/deepseek对话"
TIMEOUT_SECONDS = 30
MAX_RETRIES = 2
# =============================

# 从分享链接提取 share_id
def extract_share_id(url: str) -> str:
    """从分享 URL 提取 share_id，例如 https://chat.deepseek.com/share/eon4dmm0bs0fy0ofib -> eon4dmm0bs0fy0ofib"""
    match = re.search(r"/share/([A-Za-z0-9]+)", url)
    if not match:
        raise ValueError(f"无法从 URL 提取 share_id: {url}")
    return match.group(1)


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def build_api_url(share_id: str) -> str:
    """构建获取对话内容的 API URL"""
    return f"https://chat.deepseek.com/api/v0/share/content?share_id={share_id}"


def build_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": SHARE_URL,
        "Origin": "https://chat.deepseek.com",
    }


def fetch_api_directly(share_id: str, retries: int = 0) -> dict | None:
    """策略1：直接 HTTP 请求 API 获取对话 JSON 数据"""
    api_url = build_api_url(share_id)
    try:
        req = urllib.request.Request(api_url, headers=build_headers())
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
            print(f"  API 响应大小: {len(raw):,} bytes")
            return data
    except urllib.error.HTTPError as e:
        print(f"  HTTP 错误 {e.code}: {e.reason}")
        if retries < MAX_RETRIES:
            return fetch_api_directly(share_id, retries + 1)
        return None
    except Exception as e:
        print(f"  请求异常: {e}")
        if retries < MAX_RETRIES:
            return fetch_api_directly(share_id, retries + 1)
        return None


def fetch_api_via_playwright(share_id: str) -> dict | None:
    """策略2（兜底）：使用 Playwright 拦截 API 响应，应对直接请求被拦"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright 未安装，尝试安装...")
        os.system(f"{sys.executable} -m pip install playwright")
        os.system(f"{sys.executable} -m playwright install chromium")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None

    api_url = build_api_url(share_id)
    captured = {"data": None}

    print("  启动浏览器拦截 API 响应...")

    def handle_response(response):
        # 命中目标 API 时保存响应体
        if api_url.split("?")[0] in response.url:
            try:
                captured["data"] = response.json()
                print(f"  [命中] 拦截到 API 响应: {len(str(response.text())):,} bytes")
            except Exception:
                try:
                    text = response.text()
                    captured["data"] = json.loads(text)
                    print(f"  [命中] 拦截到 API 响应(text): {len(text):,} bytes")
                except Exception as e:
                    print(f"  [拦截失败] {e}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("response", handle_response)
            page.goto(SHARE_URL, wait_until="networkidle", timeout=60000)
            # 等待 API 响应到达
            page.wait_for_timeout(5000)
            browser.close()
    except Exception as e:
        print(f"  Playwright 异常: {e}")

    return captured["data"]


def fetch_html(url: str, retries: int = 0) -> str | None:
    """获取 HTML（仅用于提取 meta 信息）"""
    try:
        req = urllib.request.Request(url, headers=build_headers())
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


def extract_meta_info(html: str) -> dict:
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


def parse_messages(api_data: dict) -> tuple[str, list[dict]]:
    """
    解析 API 响应，返回 (title, messages)
    每条 message 结构：
        {
            "role": "USER" | "ASSISTANT",
            "inserted_at": float,
            "fragments": [
                {"type": "REQUEST"|"THINK"|"RESPONSE"|"TIP"|"TOOL_SEARCH"|"TOOL_OPEN"|"SEARCH"|"FILE", "content": str}
            ]
        }
    """
    biz_data = api_data.get("data", {}).get("biz_data", {})
    title = biz_data.get("title", "DeepSeek 对话")
    messages = biz_data.get("messages", [])
    return title, messages


# fragment 类型的中文名映射，便于阅读
FRAGMENT_TYPE_LABELS = {
    "REQUEST": "提问",
    "THINK": "思考过程",
    "RESPONSE": "回答",
    "TIP": "提示",
    "TOOL_SEARCH": "工具搜索",
    "TOOL_OPEN": "工具调用",
    "SEARCH": "联网搜索",
    "FILE": "文件",
}


def format_timestamp(ts) -> str:
    """将时间戳格式化为可读字符串"""
    try:
        if ts is None:
            return ""
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def render_markdown(title: str, messages: list[dict], share_url: str) -> str:
    """
    把消息渲染成结构化 Markdown
    支持两种数据结构：
      1. 扁平结构（直接 API 请求返回）：content / thinking_content / tips / search_results / files
      2. fragments 结构（Playwright 拦截到）：fragments: [{type, content}]
    """
    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- 来源: {share_url}")
    lines.append(f"- 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 消息总数: {len(messages)} 条（USER: {sum(1 for m in messages if m.get('role')=='USER')}，ASSISTANT: {sum(1 for m in messages if m.get('role')=='ASSISTANT')}）")
    lines.append("")
    lines.append("---")
    lines.append("")

    round_no = 0
    for msg in messages:
        role = msg.get("role", "UNKNOWN")
        ts_str = format_timestamp(msg.get("inserted_at"))
        # 判断数据结构：fragments 或扁平
        fragments = msg.get("fragments")

        if role == "USER":
            round_no += 1
            lines.append(f"## 第 {round_no} 轮对话")
            lines.append("")
            if ts_str:
                lines.append(f"**时间**: {ts_str}")
                lines.append("")
            lines.append("### 用户提问")
            lines.append("")

            if fragments:
                # fragments 结构
                for frag in fragments:
                    ftype = frag.get("type", "")
                    content = (frag.get("content") or "").strip()
                    if not content:
                        continue
                    if ftype == "REQUEST":
                        lines.append(content)
                        lines.append("")
                    else:
                        label = FRAGMENT_TYPE_LABELS.get(ftype, ftype)
                        lines.append(f"**[{label}]**")
                        lines.append("")
                        lines.append(content)
                        lines.append("")
            else:
                # 扁平结构：content + files
                content = (msg.get("content") or "").strip()
                if content:
                    lines.append(content)
                    lines.append("")
                files = msg.get("files") or []
                for f in files:
                    fname = f.get("name") or f.get("filename") or "file"
                    lines.append(f"**[附件]** {fname}")
                    lines.append("")

        elif role == "ASSISTANT":
            lines.append("### DeepSeek 回答")
            lines.append("")

            if fragments:
                # fragments 结构
                for frag in fragments:
                    ftype = frag.get("type", "")
                    content = (frag.get("content") or "").strip()
                    if not content:
                        continue
                    label = FRAGMENT_TYPE_LABELS.get(ftype, ftype)
                    if ftype == "THINK":
                        lines.append("<details><summary>思考过程（点击展开）</summary>")
                        lines.append("")
                        lines.append(content)
                        lines.append("")
                        lines.append("</details>")
                        lines.append("")
                    elif ftype == "RESPONSE":
                        lines.append(content)
                        lines.append("")
                    elif ftype == "TIP":
                        lines.append(f"> {content}")
                        lines.append("")
                    else:
                        lines.append(f"**[{label}]**")
                        lines.append("")
                        lines.append(content)
                        lines.append("")
            else:
                # 扁平结构：thinking_content -> content -> tips -> search_results
                thinking = (msg.get("thinking_content") or "").strip()
                if thinking:
                    lines.append("<details><summary>思考过程（点击展开）</summary>")
                    lines.append("")
                    lines.append(thinking)
                    lines.append("")
                    lines.append("</details>")
                    lines.append("")

                content = (msg.get("content") or "").strip()
                if content:
                    lines.append(content)
                    lines.append("")

                tips = msg.get("tips") or []
                for tip in tips:
                    if isinstance(tip, str):
                        lines.append(f"> {tip}")
                        lines.append("")
                    elif isinstance(tip, dict):
                        tip_text = (tip.get("content") or tip.get("text") or "").strip()
                        if tip_text:
                            lines.append(f"> {tip_text}")
                            lines.append("")

                search_results = msg.get("search_results") or []
                if search_results:
                    lines.append("**[联网搜索结果]**")
                    lines.append("")
                    for sr in search_results:
                        if isinstance(sr, dict):
                            title_ = sr.get("title") or ""
                            url_ = sr.get("url") or sr.get("link") or ""
                            snippet = (sr.get("content") or sr.get("snippet") or "").strip()
                            if title_:
                                lines.append(f"- **{title_}**")
                            if url_:
                                lines.append(f"  链接: {url_}")
                            if snippet:
                                lines.append(f"  摘要: {snippet[:300]}")
                            lines.append("")
        else:
            lines.append(f"### {role}")
            lines.append("")
            content = (msg.get("content") or "").strip()
            if content:
                lines.append(content)
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def save_json(data: dict, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON 已保存: {filepath}")


def save_markdown(content: str, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Markdown 已保存: {filepath}")


def main():
    print("=" * 60)
    print("DeepSeek 分享页面内容抓取工具（修复版）")
    print("=" * 60)
    print(f"分享链接: {SHARE_URL}")

    share_id = extract_share_id(SHARE_URL)
    print(f"Share ID: {share_id}")
    print("-" * 60)

    ensure_dir(OUTPUT_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"deepseek_chat_{timestamp}"

    # === 步骤1：获取 meta 信息（标题、摘要） ===
    print("\n[1/4] 获取 meta 信息...")
    html = fetch_html(SHARE_URL)
    meta = extract_meta_info(html) if html else {}
    if meta:
        print(f"  Meta 标题: {meta.get('title', 'N/A')}")
        desc = meta.get('description', '')
        print(f"  Meta 摘要: {desc[:100]}..." if len(desc) > 100 else f"  Meta 摘要: {desc}")
    else:
        print("  获取 meta 失败，继续后续步骤")
    if meta:
        save_json(meta, os.path.join(OUTPUT_DIR, f"{base_name}_meta.json"))

    # === 步骤2：直接调用 API 获取完整对话 JSON ===
    print("\n[2/4] 直接调用 API 获取完整对话数据...")
    api_data = fetch_api_directly(share_id)

    # === 步骤3：API 直接请求失败时，用 Playwright 兜底 ===
    if not api_data:
        print("\n[3/4] 直接请求失败，使用 Playwright 拦截 API 兜底...")
        api_data = fetch_api_via_playwright(share_id)
    else:
        print("\n[3/4] 跳过 Playwright 兜底（API 直接请求已成功）")

    if not api_data:
        print("\n❌ 所有抓取策略均失败，请检查网络或分享链接是否失效")
        return

    # === 步骤4：解析并保存 ===
    print("\n[4/4] 解析并保存结果...")
    title, messages = parse_messages(api_data)
    # 优先使用 meta 标签的标题（更友好），fallback 到 API 返回的 title
    if meta.get("title"):
        title = meta["title"]
    user_count = sum(1 for m in messages if m.get("role") == "USER")
    assistant_count = sum(1 for m in messages if m.get("role") == "ASSISTANT")
    print(f"  对话标题: {title}")
    print(f"  消息总数: {len(messages)} 条（USER: {user_count}，ASSISTANT: {assistant_count}）")

    # 保存原始 API JSON
    save_json(api_data, os.path.join(OUTPUT_DIR, f"{base_name}.json"))

    # 渲染并保存 Markdown
    md_content = render_markdown(title, messages, SHARE_URL)
    save_markdown(md_content, os.path.join(OUTPUT_DIR, f"{base_name}.md"))

    # === 摘要 ===
    print("\n" + "=" * 60)
    print("抓取结果")
    print("=" * 60)
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"文件前缀: {base_name}")
    print(f"对话标题: {title}")
    print(f"消息总数: {len(messages)} 条（共 {user_count} 轮对话）")
    print("=" * 60)


if __name__ == "__main__":
    main()
