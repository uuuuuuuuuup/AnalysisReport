import ast
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


STRATEGY = Path(__file__).with_name("multi_factor_selection.py")


def load_functions(*names):
    tree = ast.parse(STRATEGY.read_text(encoding="utf-8"))
    dependencies = {"winsorize_mad", "zscore", "neutralize"}
    wanted = set(names) | dependencies
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    found = {node.name for node in nodes}
    missing = set(names) - found
    if missing:
        raise AssertionError("missing functions: %s" % sorted(missing))

    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {"np": np, "pd": pd}
    exec(compile(module, str(STRATEGY), "exec"), namespace)
    return [namespace[name] for name in names]


class StrategyCoreTest(unittest.TestCase):
    def test_score_factors_uses_only_common_valid_rows(self):
        score_factors, = load_functions(
            "score_factors",
        )
        raw = pd.DataFrame({
            "bp": [1.0, 2.0, 3.0, np.nan],
            "roe": [3.0, 2.0, 1.0, 4.0],
            "ln_mcap": [4.0, 4.1, 4.2, 4.3],
            "industry": ["A", "A", "B", "B"],
        }, index=["A", "B", "C", "D"])

        score = score_factors(raw, mad_scale=5)

        self.assertEqual(set(score.index), {"A", "B", "C"})
        self.assertTrue(np.isfinite(score.values).all())

    def test_market_item_returns_none_for_missing_stock(self):
        market_item, = load_functions("market_item")

        self.assertIsNone(market_item({"A": object()}, "B"))

    def test_pick_affordable_targets_skips_expensive_stocks(self):
        pick_affordable_targets, = load_functions(
            "pick_affordable_targets",
        )
        ranked = ["A", "B", "C", "D"]
        prices = {"A": 50.0, "B": 20.0, "C": 10.0, "D": np.nan}

        targets = pick_affordable_targets(
            ranked, prices, target_value=2500.0, n_hold=2,
        )

        self.assertEqual(targets, ["B", "C"])


if __name__ == "__main__":
    unittest.main()
