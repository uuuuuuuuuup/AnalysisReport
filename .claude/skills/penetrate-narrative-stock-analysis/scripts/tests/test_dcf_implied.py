import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dcf_implied import get_dcf_result, fair_value


def test_get_dcf_result_structure():
    result = get_dcf_result(cap=1000, e1=10, e2=11, e3=12, e0=5)
    assert "scenarios" in result
    assert "r_10" in result["scenarios"]
    assert "L" in result["scenarios"]["r_10"]


def test_forward_backward_error():
    result = get_dcf_result(cap=1000, e1=10, e2=11, e3=12, e0=5)
    L = result["scenarios"]["r_10"]["L"]
    fv = fair_value(L, 10, 11, 12, 10, result["growth_years"])
    assert abs(fv - 1000) / 1000 < 0.05