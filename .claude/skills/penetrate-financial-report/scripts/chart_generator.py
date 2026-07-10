# .claude/skills/penetrate-financial-report/scripts/chart_generator.py
"""Chart generation using matplotlib for financial report."""
import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# China stock convention: up=red, down=green
COLOR_UP = "#C00000"
COLOR_DOWN = "#007000"
COLOR_COMPANY = "#C00000"
COLOR_INDUSTRY = "#007000"
COLOR_TREND = "#1F3A5F"

CHINESE_FONT_CANDIDATES = [
    "PingFang SC",
    "Microsoft YaHei",
    "SimHei",
    "Heiti SC",
    "Hiragino Sans GB",
    "Arial Unicode MS",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "Songti SC",
    "STHeiti",
]


def setup_chinese_font():
    """Configure matplotlib to use a system Chinese font for CJK text."""
    available = {f.name for f in fm.fontManager.ttflist}
    for name in CHINESE_FONT_CANDIDATES:
        if name in available:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [name] + [
                f for f in plt.rcParams["font.sans-serif"] if f != name
            ]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    return None


_CHINESE_FONT = setup_chinese_font()


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


def save_bar_chart(labels: list, values: list, output_path: str, title: str,
                   ylabel: str) -> str:
    """Generate a bar chart with China color convention."""
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = [COLOR_UP if v >= 0 else COLOR_DOWN for v in values]
    ax.bar(labels, values, color=colors)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path
