"""Data acquisition layer for narrative skill."""
import subprocess
import json
import os
from typing import Optional, Dict, Any


def _run_skill_cli(command: list, cwd: Optional[str] = None) -> dict:
    """Run an external skill CLI and parse JSON stdout."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, cwd=cwd, timeout=60)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr}
        return json.loads(result.stdout)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_market_data_mx(stock_name: str) -> Optional[Dict[str, Any]]:
    """Use mx-data to get market cap and price."""
    base_dir = os.path.expanduser("~/.claude/skills/mx-data")
    script = os.path.join(base_dir, "scripts/query_data.py")
    if not os.path.exists(script):
        return None
    command = [
        "python3", script,
        "--query", f"{stock_name} 市值 股价",
        "--data-type", "finance",
        "--indicators", "总市值,最新价"
    ]
    data = _run_skill_cli(command, cwd=base_dir)
    if data.get("ok") and data.get("csv_path"):
        # Parse CSV for the requested values
        import pandas as pd
        df = pd.read_csv(data["csv_path"])
        if not df.empty:
            return {
                "price": float(df.iloc[0].get("最新价", 0)),
                "market_cap": float(df.iloc[0].get("总市值", 0)) / 1e8,  # convert to 亿元
                "source": "mx-data"
            }
    return None


def get_market_data_lingxi(stock_name: str) -> Optional[Dict[str, Any]]:
    """Use gtht-lingxi-unified marketdata to get price and market cap."""
    base_dir = os.path.expanduser("~/.claude/skills/gtht-lingxi-unified")
    script = os.path.join(base_dir, "skill-entry.js")
    if not os.path.exists(script):
        return None
    command = ["node", script, "marketdata", stock_name]
    data = _run_skill_cli(command, cwd=base_dir)
    if data.get("ok") and data.get("data"):
        item = data["data"]
        return {
            "price": float(item.get("最新价", 0)),
            "market_cap": float(item.get("总市值", 0)) / 1e8,
            "total_shares": float(item.get("总股本", 0)) / 1e8,
            "source": "gtht-lingxi-unified"
        }
    return None


def get_consensus_earnings(stock_name: str) -> Optional[Dict[str, float]]:
    """Try to get E1/E2/E3 from research reports or mx-data."""
    # First try lingxi research
    base_dir = os.path.expanduser("~/.claude/skills/gtht-lingxi-unified")
    script = os.path.join(base_dir, "skill-entry.js")
    if os.path.exists(script):
        command = ["node", script, "research", f"{stock_name} 一致预期净利润"]
        data = _run_skill_cli(command, cwd=base_dir)
        if data.get("ok"):
            # Placeholder: actual parsing depends on research output format
            return None
    return None
