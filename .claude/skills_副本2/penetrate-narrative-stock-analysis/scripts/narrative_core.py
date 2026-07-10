# .claude/skills/penetrate-narrative-stock-analysis/scripts/narrative_core.py
"""Core narrative analysis engine. Supports standalone and financial-support modes."""
from typing import Dict, Any, Optional
from dcf_implied import get_dcf_result
from validators import validate_market_cap


def classify_narrative(L_E3: float) -> str:
    """Classify narrative based on L/E3 ratio."""
    if L_E3 < 0.5:
        return "深度下滑叙事"
    if L_E3 < 1:
        return "下滑叙事"
    if L_E3 < 2:
        return "温和增长叙事"
    if L_E3 < 5:
        return "较高增长叙事"
    if L_E3 < 10:
        return "高增长叙事（较饱满）"
    return "极高增长叙事（透支风险大）"


def run_narrative_analysis(inputs: Dict[str, Any],
                           mode: str = "standalone") -> Dict[str, Any]:
    """Run narrative analysis.

    Args:
        inputs: dict with company, code, market_cap, total_shares, e0, e1, e2, e3, etc.
        mode: "standalone" or "financial-support"

    Returns:
        dict with DCF results, narrative classification, and optionally full report sections.
    """
    cap = float(inputs["market_cap"])
    e1 = float(inputs["e1"])
    e2 = float(inputs["e2"])
    e3 = float(inputs["e3"])
    e0 = float(inputs.get("e0", 0))

    dcf = get_dcf_result(cap, e1, e2, e3, e0=e0)
    r10 = dcf["scenarios"]["r_10"]
    narrative_class = classify_narrative(r10["L/E3"])

    result = {
        "company": inputs.get("company"),
        "code": inputs.get("code"),
        "market_cap": cap,
        "total_shares": inputs.get("total_shares"),
        "price": inputs.get("price"),
        "e0": e0,
        "e1": e1,
        "e2": e2,
        "e3": e3,
        "dcf": dcf,
        "narrative_class": narrative_class,
    }

    if mode == "financial-support":
        # In financial-support mode, return minimal structured output.
        result["mode"] = "financial-support"
        result["stage"] = inputs.get("stage", "待判断")
        result["scenario_probability"] = inputs.get("scenario_probability", {})
        result["moat_summary"] = inputs.get("moat_summary", "")
        result["key_risks"] = inputs.get("key_risks", [])
        return result

    # Standalone mode: include full analysis sections
    result["mode"] = "standalone"
    result["stage"] = "展望期"  # placeholder for future stage logic
    result["scenario_probability"] = {"up": 0.15, "maintain": 0.35, "down": 0.35, "deep_down": 0.15}
    result["moat_summary"] = "待填充"
    result["key_risks"] = ["待填充"]
    return result