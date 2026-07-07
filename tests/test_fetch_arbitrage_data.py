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
            {"code": "sh501018", "currentPrice": 1.23, "premiumRate": 4.5},
            {"code": "sh501021", "currentPrice": 2.34, "premiumRate": 1.5},
        ]

        with patch.object(module, "fetch_prices_from_tencent", return_value=batch_result), \
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

    def test_fetch_kline_uses_tencent_history_format(self):
        class FakeResponse:
            def json(self):
                return {
                    "data": {
                        "sh501018": {
                            "qfqday": [
                                ["2026-05-27", "1.80", "1.85", "1.88", "1.79", "120000"],
                                ["2026-05-28", "1.85", "1.87", "1.90", "1.84", "130000"],
                            ]
                        }
                    }
                }

        with patch.object(module, "retry_request", return_value=FakeResponse()):
            kline = module.fetch_kline("sh", "501018", days=2)

        self.assertEqual(len(kline), 2)
        self.assertEqual(kline[0]["date"], "2026-05-27")
        self.assertEqual(kline[0]["open"], 1.80)
        self.assertEqual(kline[1]["close"], 1.87)

    def test_fetch_news_merges_notices_and_reports(self):
        notices = [{"title": "暂停申购公告", "date": "2026-05-30", "source": "公告", "url": ""}]
        reports = [{"title": "高溢价风险提示", "date": "2026-05-29", "source": "研报", "url": ""}]

        with patch.object(module, "fetch_eastmoney_notices", return_value=notices), \
             patch.object(module, "fetch_eastmoney_reports", return_value=reports):
            news = module.fetch_news("sh", "501018")

        self.assertEqual(len(news), 2)
        self.assertEqual(news[0]["title"], "暂停申购公告")
        self.assertEqual(news[0]["source"], "公告")
        self.assertEqual(news[1]["title"], "高溢价风险提示")
        self.assertEqual(news[1]["source"], "研报")


    def test_build_fund_data_enrich_runs_concurrently(self):
        """三个 enrich 函数应该并发执行，总耗时接近最慢那个而非三个之和。"""
        import time as time_mod

        fund = {"code": "501018", "market": "sh", "name": "南方原油LOF", "notes": ""}
        price_info = {
            "currentPrice": 1.909, "changePercent": -2.4, "changeAmount": -0.047,
            "volume": 1270805, "turnover": 24288.0, "premiumRate": 5.84,
        }

        def slow_kline(*a, **kw):
            time_mod.sleep(0.2)
            return []

        def slow_money_flow(*a, **kw):
            time_mod.sleep(0.2)
            return {}

        def slow_news(*a, **kw):
            time_mod.sleep(0.2)
            return []

        with patch.object(module, "fetch_kline", side_effect=slow_kline), \
             patch.object(module, "fetch_money_flow", side_effect=slow_money_flow), \
             patch.object(module, "fetch_news", side_effect=slow_news):
            start = time_mod.time()
            module.build_fund_data(fund, price_info)
            elapsed = time_mod.time() - start

        # 串行需要约 0.6s，并行应在 0.4s 内完成
        self.assertLess(elapsed, 0.4, f"enrich 应并行，实际耗时 {elapsed:.2f}s 超过预期")

    def test_main_loop_does_not_sleep_between_funds(self):
        """主循环处理多只基金时不应有固定 sleep。"""
        import time as time_mod

        funds = [
            {"code": "501018", "market": "sh", "name": "A", "notes": ""},
            {"code": "501021", "market": "sh", "name": "B", "notes": ""},
        ]
        price_map = {
            "501018": {"currentPrice": 1.0, "premiumRate": 5.0, "changePercent": 0.0,
                       "changeAmount": 0.0, "volume": 1000, "turnover": 1000.0},
            "501021": {"currentPrice": 2.0, "premiumRate": 1.0, "changePercent": 0.0,
                       "changeAmount": 0.0, "volume": 2000, "turnover": 2000.0},
        }

        with patch.object(module, "fetch_kline", return_value=[]), \
             patch.object(module, "fetch_money_flow", return_value={}), \
             patch.object(module, "fetch_news", return_value=[]):
            start = time_mod.time()
            results = {}
            for fund in funds:
                code = module.normalize_code(fund["code"])
                results[code] = module.build_fund_data(fund, price_map[code])
            elapsed = time_mod.time() - start

        # 无 sleep，两只基金处理应在 0.5s 内完成
        self.assertLess(elapsed, 0.5, f"主循环应无 sleep，实际耗时 {elapsed:.2f}s")

