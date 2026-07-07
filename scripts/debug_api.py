"""Debug: 测试 API 数据拉取，找到正确的解析方式"""
import asyncio, json, sys, uuid
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "skills" / "mx-finance-data" / "scripts"))
from get_data import query_mx_finance_data

async def main():
    # 使用已有的成熟函数测试
    result = await query_mx_finance_data(
        query="贵州茅台 600519 近5年 净资产收益率ROE 销售毛利率 资产负债率 营业收入 归属母公司股东的净利润",
    )
    print("=== RESULT KEYS ===")
    for k, v in result.items():
        if k not in ("raw_response", "raw_preview"):
            print(f"  {k}: {str(v)[:200]}")

    # 如果有文件输出
    if result.get("csv_path"):
        csv_content = Path(result["csv_path"]).read_text(encoding="utf-8")[:1000]
        print(f"\n=== CSV PREVIEW ===")
        print(csv_content)

    if result.get("md_path"):
        md_content = Path(result["md_path"]).read_text(encoding="utf-8")[:1000]
        print(f"\n=== MD PREVIEW ===")
        print(md_content)

asyncio.run(main())
