import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parent / "strategy_tools.py"
)


class StrategyToolsCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_rf_cache_reports_fresh_market_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "risk_free_rate.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "CN_10Y": {
                            "value": 1.73,
                            "date": "2026-07-10",
                            "expiry_days": 30,
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_cli(
                "rf-cache",
                "--cache",
                str(cache_path),
                "--market",
                "CN",
                "--as-of",
                "2026-07-20",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["usable"])
        self.assertEqual(payload["key"], "CN_10Y")
        self.assertEqual(payload["value"], 1.73)

    def test_calculate_returns_conservative_valuation_metrics(self):
        input_payload = {
            "market": "CN",
            "market_cap": 1000,
            "net_income": 100,
            "depreciation_amortization": 20,
            "maintenance_capex_ratio": 0.7,
            "payout_ratio": 0.5,
            "dividend_tax_rate": 0.1,
            "annual_buybacks": 10,
            "disposable_cash_surplus": 80,
            "risk_free_rate": 1.73,
            "net_cash": 450,
            "cyclical_adjustment_pct": 0,
            "cash_protection_discount": 0.2,
            "current_price": 10,
        }

        result = self.run_cli("calculate", "--input-json", json.dumps(input_payload))

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertAlmostEqual(payload["owner_earnings"], 106.0)
        self.assertAlmostEqual(payload["rough_penetration_return_pct"], 5.77, places=2)
        self.assertAlmostEqual(payload["precise_penetration_return_pct"], 4.6, places=2)
        self.assertAlmostEqual(payload["threshold_pct"], 3.73, places=2)
        self.assertEqual(payload["cash_protection_level"], "强")
        self.assertAlmostEqual(payload["target_buy_price"], 9.87, places=2)

    def test_prepare_sets_target_year_and_finalizes_latest_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "reports"
            prepared = self.run_cli(
                "prepare",
                "--symbol",
                "000001",
                "--company",
                "示例公司",
                "--output-root",
                str(root),
                "--as-of",
                "2026-03-15",
            )

            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            prepared_payload = json.loads(prepared.stdout)
            self.assertEqual(prepared_payload["target_year"], 2024)
            version_dir = Path(prepared_payload["version_dir"])
            self.assertTrue(version_dir.is_dir())
            report = version_dir / "示例公司_000001_稳健投资策略分析报告.md"
            report.write_text("# report\n", encoding="utf-8")

            version = {
                "symbol": "000001",
                "company": "示例公司",
                "record": {"date": "2026-03-15", "dir": version_dir.name},
            }
            finalized = self.run_cli(
                "finalize",
                "--index",
                str(root / "000001" / "index.json"),
                "--latest-dir",
                str(version_dir),
                "--version-json",
                json.dumps(version, ensure_ascii=False),
            )

            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            index = json.loads((root / "000001" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["versions"], [version["record"]])
            self.assertTrue((root / "000001" / "latest").is_symlink())
            self.assertEqual(
                (root / "000001" / "latest").resolve(),
                version_dir.resolve(),
            )

    def test_validate_reports_missing_financial_fields_and_unit(self):
        result = self.run_cli(
            "validate",
            "--input-json",
            json.dumps({"currency": "CNY", "unit": "亿元", "net_income": 100}),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertIn("market_cap", payload["missing_fields"])
        self.assertIn("unit must be one", payload["issues"][0])


if __name__ == "__main__":
    unittest.main()
