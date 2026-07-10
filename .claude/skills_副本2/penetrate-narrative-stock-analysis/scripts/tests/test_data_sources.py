import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_sources import get_market_data_mx, get_market_data_lingxi


def test_data_sources_return_optional():
    mx = get_market_data_mx("贵州茅台")
    if mx:
        assert "price" in mx
        assert "market_cap" in mx
    lingxi = get_market_data_lingxi("贵州茅台")
    if lingxi:
        assert "price" in lingxi
        assert "market_cap" in lingxi
