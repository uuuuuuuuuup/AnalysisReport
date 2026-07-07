"""
Eastmoney MCP endpoint registry.

Maps skill/report/diagnosis/data/search types to their API URLs.
"""

from enum import Enum
from typing import Dict


class SkillType(str, Enum):
    """Top-level skill categories."""

    ASSISTANT = "assistant"
    REPORT = "report"
    DIAGNOSIS = "diagnosis"
    DATA = "data"
    SEARCH = "search"


class ReportType(str, Enum):
    """Report sub-types for mx-report."""

    INDUSTRY = "industry"
    TOPIC = "topic"
    COVERAGE = "coverage"
    EARNINGS = "earnings"
    TRACKER = "tracker"


class DiagnosisType(str, Enum):
    """Diagnosis sub-types for mx-diagnosis."""

    STOCK = "stock"
    FUND = "fund"
    HOTSPOT = "hotspot"


class DataType(str, Enum):
    """Data sub-types for mx-data."""

    FINANCE = "finance"
    MACRO = "macro"
    SCREENER = "screener"
    COMPARABLE = "comparable"


class SearchType(str, Enum):
    """Search sub-types for mx-search."""

    NEWS = "news"


BASE_URL = "https://ai-saas.eastmoney.com"


ENDPOINTS: Dict[str, str] = {
    # assistant
    "assistant": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/ask",
    # report
    "report_industry": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/write/industry/research",
    "report_topic": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/write/thematic/research",
    "report_coverage": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/write/initial-coverage",
    "report_tracker": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/write/tracking/report",
    "report_earnings": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/write/performance/comment",
    "report_earnings_report_list": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/write/choice/reportList",
    # diagnosis
    "diagnosis_stock": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/stock-analysis",
    "diagnosis_fund": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/fund-analysis",
    "diagnosis_hotspot": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/hotspot-discovery",
    # data
    "data_finance": f"{BASE_URL}/proxy/b/mcp/tool/searchData",
    "data_macro": f"{BASE_URL}/proxy/b/mcp/tool/searchMacroData",
    "data_screener": f"{BASE_URL}/proxy/b/mcp/tool/selectSecurity",
    "data_comparable": f"{BASE_URL}/proxy/app-robo-advisor-api/assistant/comparable-company-analysis",
    # search
    "search_news": f"{BASE_URL}/proxy/b/mcp/tool/searchNews",
    # entity
    "entity_saas": f"{BASE_URL}/proxy/entity/saas",
    "entity_dialog": f"{BASE_URL}/proxy/entity/dialogTagsV2",
}


def get_endpoint(key: str) -> str:
    """Return the URL for a registered endpoint key."""
    if key not in ENDPOINTS:
        raise KeyError(f"Unknown endpoint: {key}")
    return ENDPOINTS[key]


def report_endpoint(report_type: str) -> str:
    """Return the report endpoint for a given report type."""
    mapping = {
        ReportType.INDUSTRY.value: "report_industry",
        ReportType.TOPIC.value: "report_topic",
        ReportType.COVERAGE.value: "report_coverage",
        ReportType.EARNINGS.value: "report_earnings",
        ReportType.TRACKER.value: "report_tracker",
    }
    key = mapping.get(report_type)
    if not key:
        raise ValueError(f"Unsupported report type: {report_type}")
    return get_endpoint(key)


def diagnosis_endpoint(diagnosis_type: str) -> str:
    """Return the diagnosis endpoint for a given diagnosis type."""
    mapping = {
        DiagnosisType.STOCK.value: "diagnosis_stock",
        DiagnosisType.FUND.value: "diagnosis_fund",
        DiagnosisType.HOTSPOT.value: "diagnosis_hotspot",
    }
    key = mapping.get(diagnosis_type)
    if not key:
        raise ValueError(f"Unsupported diagnosis type: {diagnosis_type}")
    return get_endpoint(key)


def data_endpoint(data_type: str) -> str:
    """Return the data endpoint for a given data type."""
    mapping = {
        DataType.FINANCE.value: "data_finance",
        DataType.MACRO.value: "data_macro",
        DataType.SCREENER.value: "data_screener",
        DataType.COMPARABLE.value: "data_comparable",
    }
    key = mapping.get(data_type)
    if not key:
        raise ValueError(f"Unsupported data type: {data_type}")
    return get_endpoint(key)


def search_endpoint(search_type: str = "news") -> str:
    """Return the search endpoint for a given search type."""
    if search_type != SearchType.NEWS.value:
        raise ValueError(f"Unsupported search type: {search_type}")
    return get_endpoint("search_news")
