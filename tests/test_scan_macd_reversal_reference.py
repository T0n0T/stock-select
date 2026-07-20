import importlib.util
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scan_macd_reversal.py"
if not SCRIPT_PATH.exists():
    raise unittest.SkipTest(f"reference script not found: {SCRIPT_PATH}")
SPEC = importlib.util.spec_from_file_location("scan_macd_reversal", SCRIPT_PATH)
REFERENCE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = REFERENCE
SPEC.loader.exec_module(REFERENCE)


class ScanMacdReversalReferenceTests(unittest.TestCase):
    def test_reference_script_no_longer_requires_postgres(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertNotIn("POSTGRES_DSN", source)
        self.assertNotIn("--dsn", source)

    def test_tushare_rest_payload_uses_comma_separated_fields(self):
        payload = REFERENCE.tushare_request_payload(
            "daily",
            "secret-token",
            {"ts_code": "000001.SZ", "end_date": "20260710"},
            ["ts_code", "trade_date", "close"],
        )

        self.assertEqual(payload["api_name"], "daily")
        self.assertEqual(payload["token"], "secret-token")
        self.assertEqual(payload["fields"], "ts_code,trade_date,close")
        self.assertEqual(payload["params"]["ts_code"], "000001.SZ")

    def test_online_daily_loader_uses_tushare_daily_and_adj_factor(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def query(self, api_name, params, fields):
                self.calls.append((api_name, params, fields))
                if api_name == "daily":
                    return [
                        {
                            "ts_code": "000001.SZ",
                            "trade_date": "20260102",
                            "open": 20.0,
                            "high": 23.0,
                            "low": 19.0,
                            "close": 22.0,
                            "vol": 200.0,
                        },
                        {
                            "ts_code": "000001.SZ",
                            "trade_date": "20260101",
                            "open": 10.0,
                            "high": 12.0,
                            "low": 9.0,
                            "close": 11.0,
                            "vol": 100.0,
                        },
                    ]
                if api_name == "adj_factor":
                    return [
                        {"ts_code": "000001.SZ", "trade_date": "20260102", "adj_factor": 2.0},
                        {"ts_code": "000001.SZ", "trade_date": "20260101", "adj_factor": 1.0},
                    ]
                self.fail(f"unexpected api: {api_name}")

        client = FakeClient()
        rows = REFERENCE.fetch_online_stock_history(
            client,
            "000001.SZ",
            "平安银行",
            date(2026, 1, 1),
            date(2026, 1, 2),
        )

        self.assertEqual([call[0] for call in client.calls], ["daily", "adj_factor"])
        self.assertEqual([row["trade_date"] for row in rows], [date(2026, 1, 1), date(2026, 1, 2)])
        self.assertAlmostEqual(rows[0]["open"], 5.0)
        self.assertAlmostEqual(rows[0]["close"], 5.5)
        self.assertAlmostEqual(rows[1]["close"], 22.0)
        self.assertAlmostEqual(rows[0]["turnover_daily"], 1050.0)
        self.assertIn("macd_hist", rows[-1])

    def test_online_intraday_recomputes_macd_from_history_without_db_state(self):
        start = date(2022, 1, 3)
        rows = []
        current = start
        close = 10.0
        while len(rows) < 900:
            if current.weekday() < 5:
                close += 0.01
                rows.append(
                    {
                        "ts_code": "000001.SZ",
                        "name": "平安银行",
                        "trade_date": current,
                        "open": close - 0.05,
                        "high": close + 0.1,
                        "low": close - 0.1,
                        "close": close,
                        "raw_open": close - 0.05,
                        "raw_high": close + 0.1,
                        "raw_low": close - 0.1,
                        "raw_close": close,
                        "vol": 1000.0,
                        "adj_factor": 1.0,
                        "turnover_daily": (close - 0.025) * 1000.0,
                    }
                )
            current += timedelta(days=1)
        REFERENCE.decorate_online_history(rows)
        pick_date = rows[-1]["trade_date"] + timedelta(days=1)
        while pick_date.weekday() >= 5:
            pick_date += timedelta(days=1)

        REFERENCE.apply_online_intraday_snapshot(
            {"000001.SZ": rows},
            [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "open": 19.0,
                    "high": 20.5,
                    "low": 18.8,
                    "close": 20.0,
                    "vol": 2000.0,
                    "amount": 39000.0,
                }
            ],
            pick_date,
        )

        latest = rows[-1]
        self.assertEqual(latest["trade_date"], pick_date)
        self.assertIsInstance(latest["macd_hist"], float)
        self.assertIsInstance(latest["macd_weekly_dif"], float)
        self.assertIsInstance(latest["macd_weekly_dea"], float)
        self.assertIsInstance(latest["macd_weekly_hist"], float)
        self.assertIsInstance(latest["macd_monthly_dif"], float)
        self.assertIsInstance(latest["macd_monthly_dea"], float)
        self.assertIsInstance(latest["macd_monthly_hist"], float)
        self.assertNotIn("macd_weekly_prev_hist", latest)
        self.assertNotIn("macd_monthly_prev_hist", latest)
        self.assertGreaterEqual(latest["macd_weekly_period_count"], 40)
        self.assertGreaterEqual(latest["macd_monthly_period_count"], 30)

    def test_weekly_and_monthly_closes_use_last_daily_close_including_current_period(self):
        rows = [
            {"trade_date": date(2026, 1, 29), "close": 10.0},
            {"trade_date": date(2026, 1, 30), "close": 11.0},
            {"trade_date": date(2026, 2, 2), "close": 12.0},
            {"trade_date": date(2026, 2, 3), "close": 13.0},
        ]

        weekly = REFERENCE.period_closes(rows, "weekly")
        monthly = REFERENCE.period_closes(rows, "monthly")

        self.assertEqual([close for _, close in weekly], [11.0, 13.0])
        self.assertEqual([close for _, close in monthly], [11.0, 13.0])

    def test_online_history_loader_reports_completed_symbol_progress(self):
        original = REFERENCE.fetch_online_stock_history
        messages = []

        def fake_history(client, code, name, start_date, pick_date):
            return [{"ts_code": code, "name": name, "trade_date": pick_date}]

        REFERENCE.fetch_online_stock_history = fake_history
        try:
            histories, failures = REFERENCE.fetch_online_histories(
                object(),
                ["000001.SZ", "000002.SZ", "600000.SH"],
                {},
                date(2025, 1, 1),
                date(2026, 1, 1),
                workers=2,
                progress=messages.append,
            )
        finally:
            REFERENCE.fetch_online_stock_history = original

        self.assertEqual(len(histories), 3)
        self.assertEqual(failures, [])
        self.assertTrue(any("历史行情 1/3" in message for message in messages))
        self.assertTrue(any("历史行情 3/3" in message for message in messages))

    def test_two_green_segments_require_second_peak_to_have_started_contracting(self):
        hist = [0.02] * 4 + [
            -0.05,
            -0.10,
            -0.20,
            -0.35,
            -0.25,
            -0.12,
            0.04,
            -0.04,
            -0.08,
            -0.12,
            -0.16,
        ]

        result = REFERENCE.check_daily_green_divergence(hist)

        self.assertFalse(result["divergence_detected"])

    def test_red_bar_completes_second_green_peak_contraction(self):
        hist = [
            -0.05,
            -0.10,
            -0.20,
            -0.35,
            -0.25,
            -0.12,
            0.04,
            -0.04,
            -0.08,
            -0.16,
            0.02,
        ] + [0.03] * 4

        result = REFERENCE.check_daily_green_divergence(hist)

        self.assertTrue(result["divergence_detected"])

    def test_single_green_segment_uses_two_completed_local_peaks(self):
        hist = [
            -0.05,
            -0.10,
            -0.20,
            -0.35,
            -0.25,
            -0.12,
            -0.08,
            -0.10,
            -0.14,
            -0.18,
            0.02,
        ] + [0.03] * 4

        result = REFERENCE.check_daily_green_divergence(hist)

        self.assertTrue(result["divergence_detected"])
        self.assertEqual(result["segments_used"], 1)

    def test_period_macd_matches_shared_dif_and_dea_condition(self):
        self.assertTrue(REFERENCE.check_period_macd_positive(0.10, 0.06))
        self.assertFalse(REFERENCE.check_period_macd_positive(-0.05, 0.10))
        self.assertFalse(REFERENCE.check_period_macd_positive(0.10, -0.05))

    def test_surge_volume_uses_last_22_rows_and_prior_three_to_five_volumes(self):
        rows = [
            {"close": 10.0, "vol": 100.0, "trade_date": f"d{idx}"}
            for idx in range(23)
        ]
        rows[-1]["close"] = 11.0
        rows[-1]["vol"] = 200.0

        result = REFERENCE.check_surge_volume(rows)

        self.assertTrue(result["detected"])
        self.assertEqual(result["details"][0]["date"], "d22")

    def test_intraday_macd_uses_completed_state_and_live_qfq_price(self):
        state = REFERENCE.MacdPeriodState(
            ts_code="000001.SZ",
            period_type="weekly",
            ema12=10.0,
            ema26=9.0,
            dea=0.8,
            period_count=40,
        )

        result = REFERENCE.derive_live_macd_from_period_state(state, 11.0)

        expected_ema12 = 10.0 * (11.0 / 13.0) + 11.0 * (2.0 / 13.0)
        expected_ema26 = 9.0 * (25.0 / 27.0) + 11.0 * (2.0 / 27.0)
        expected_dif = expected_ema12 - expected_ema26
        expected_dea = 0.8 * 0.8 + expected_dif * 0.2
        self.assertAlmostEqual(result["dif"], expected_dif)
        self.assertAlmostEqual(result["dea"], expected_dea)
        self.assertAlmostEqual(result["hist"], expected_dif - expected_dea)
        self.assertNotIn("previous_hist", result)
        self.assertEqual(result["period_count"], 41)

    def test_turnover_ranks_use_only_pick_date_rows_after_intraday_injection(self):
        rows_by_code = {
            "000001.SZ": [
                {"trade_date": "2026-07-09", "turnover_n": 999.0},
                {"trade_date": "2026-07-10", "turnover_n": 200.0},
            ],
            "000002.SZ": [
                {"trade_date": "2026-07-10", "turnover_n": 300.0},
            ],
            "000003.SZ": [
                {"trade_date": "2026-07-09", "turnover_n": 500.0},
            ],
        }

        ranks = REFERENCE.turnover_ranks_from_rows(rows_by_code, "2026-07-10")

        self.assertEqual(ranks["000002.SZ"], (300.0, 1))
        self.assertEqual(ranks["000001.SZ"], (200.0, 2))
        self.assertNotIn("000003.SZ", ranks)


if __name__ == "__main__":
    unittest.main()
