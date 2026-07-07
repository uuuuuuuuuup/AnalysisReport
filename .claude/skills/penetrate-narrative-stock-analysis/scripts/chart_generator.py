# .claude/skills/penetrate-narrative-stock-analysis/scripts/chart_generator.py
"""Chart generation using matplotlib."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# China stock convention: up=red, down=green
COLOR_UP = "#C00000"
COLOR_DOWN = "#007000"
COLOR_COMPANY = "#C00000"
COLOR_INDUSTRY = "#007000"
COLOR_TREND = "#1F3A5F"


def save_dcf_sensitivity_chart(ratios: list, market_caps: list, current_cap: float,
                                output_path: str) -> str:
    """Generate DCF sensitivity chart: L/E3 vs market cap."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = [COLOR_UP if m >= current_cap else COLOR_DOWN for m in market_caps]
    ax.bar([f"{r:.1f}x" for r in ratios], market_caps, color=colors)
    ax.axhline(current_cap, color=COLOR_TREND, linestyle="--", label="Current Market Cap")
    ax.set_xlabel("L/E3")
    ax.set_ylabel("Market Cap (亿元)")
    ax.set_title("DCF Sensitivity Analysis")
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def save_trend_chart(years: list, values: list, output_path: str, title: str,
                       ylabel: str) -> str:
    """Generate a simple line chart for revenue/profit trend."""
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(years, values, marker="o", color=COLOR_COMPANY, linewidth=2)
    ax.set_xlabel("Year")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path
