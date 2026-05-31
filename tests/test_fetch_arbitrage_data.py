import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_arbitrage_data.py"
spec = importlib.util.spec_from_file_location("fetch_arbitrage_data", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FetchArbitrageDataTests(unittest.TestCase):
    def test_fetch_price_map_uses_batch_result_without_http_fallback(self):
        funds = [
            {"code": "501018", "market": "sh"},
            {"code": "501021", "market": "sh"},
        ]
        batch_result = [
            {"code": "501018", "currentPrice": 1.23, "premiumRate": 4.5},
            {"code": "501021", "currentPrice": 2.34, "premiumRate": 1.5},
        ]

        with patch.object(module, "fetch_prices_via_mcp", return_value=batch_result), \
             patch.object(module, "fetch_prices_via_claude", return_value=None), \
             patch.object(module, "fetch_price_from_eastmoney") as fallback:
            price_map = module.fetch_price_map(funds)

        self.assertEqual(price_map["501018"]["currentPrice"], 1.23)
        self.assertEqual(price_map["501021"]["premiumRate"], 1.5)
        fallback.assert_not_called()

    def test_build_fund_data_keeps_core_success_when_enrich_calls_fail(self):
        fund = {"code": "501018", "market": "sh", "name": "南方原油LOF", "notes": ""}
        price_info = {
            "code": "501018",
            "name": "南方原油LOF",
            "currentPrice": 1.909,
            "changePercent": -2.4,
            "changeAmount": -0.047,
            "volume": 1270805,
            "turnover": 24288.0,
            "premiumRate": 5.84,
        }

        with patch.object(module, "fetch_kline", return_value=[]), \
             patch.object(module, "fetch_money_flow", side_effect=RuntimeError("money flow unavailable")), \
             patch.object(module, "fetch_news", side_effect=RuntimeError("news unavailable")):
            fund_data = module.build_fund_data(fund, price_info)

        self.assertEqual(fund_data["price"]["current"], 1.909)
        self.assertEqual(fund_data["premium_rate"], 5.84)
        self.assertEqual(fund_data["kline_5d"], [])
        self.assertEqual(fund_data["money_flow"], {})
        self.assertEqual(fund_data["news"], [])
        self.assertIsNone(fund_data["error"])

    def test_fetch_news_returns_empty_list_when_news_endpoint_fails(self):
        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        calls = [
            FakeResponse({
                "QuotationCodeTable": {
                    "Data": [{"SecurityCode": "501018"}]
                }
            }),
            RuntimeError("404 not found"),
        ]

        def fake_retry_request(*args, **kwargs):
            result = calls.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch.object(module, "retry_request", side_effect=fake_retry_request):
            news = module.fetch_news("sh", "501018")

        self.assertEqual(news, [])


if __name__ == "__main__":
    unittest.main()
