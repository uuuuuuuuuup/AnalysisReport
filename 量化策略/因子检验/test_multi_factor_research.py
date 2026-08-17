import ast
import datetime
import unittest
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).with_name("multi_factor_research.py")


def load_function(name):
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    node = next(
        (item for item in tree.body
         if isinstance(item, ast.FunctionDef) and item.name == name),
        None,
    )
    if node is None:
        raise AssertionError("missing function: %s" % name)

    module = ast.Module(body=[node], type_ignores=[])
    namespace = {"pd": pd}
    exec(compile(module, str(SCRIPT), "exec"), namespace)
    return namespace[name]


class NormalizeDateColumnTest(unittest.TestCase):
    def test_converts_python_dates_for_string_range_filtering(self):
        normalize_date_column = load_function("normalize_date_column")
        raw = pd.DataFrame({
            "date": [datetime.date(2021, 12, 31), datetime.date(2022, 1, 31)],
            "value": [1, 2],
        })

        result = normalize_date_column(raw)
        selected = result[
            (result["date"] >= "2022-01-01")
            & (result["date"] <= "2022-12-31")
        ]

        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["date"]))
        self.assertEqual(selected["value"].tolist(), [2])


if __name__ == "__main__":
    unittest.main()
