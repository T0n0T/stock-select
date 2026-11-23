from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from ml.backtest.akquant_gateway import load_market_data
from ml.backtest.policy import TopNHoldPolicy
from ml.backtest.signal_bundle import load_signal_bundle


class TopNHoldPolicyTest(unittest.TestCase):
    def test_enters_stable_top_three(self):
        policy = TopNHoldPolicy(top_n=3, holding_days=3)

        action = policy.on_trading_day(
            "2026-01-05",
            [
                ("600003", 0.8),
                ("600001", 0.9),
                ("600002", 0.9),
                ("600004", 0.7),
            ],
        )

        self.assertEqual(action.enter, ("600001", "600002", "600003"))
        self.assertEqual(action.exit, ())
        self.assertEqual(action.holding_day, 0)

    def test_enters_each_daily_top_three_and_expires_each_batch_after_three_sessions(self):
        policy = TopNHoldPolicy(top_n=3, holding_days=3)
        first = policy.on_trading_day("2026-01-05", [("A", 3), ("B", 2), ("C", 1)])
        second = policy.on_trading_day("2026-01-06", [("D", 4), ("E", 3), ("F", 2)])
        third = policy.on_trading_day("2026-01-07", [("G", 4), ("H", 3), ("I", 2)])
        fourth = policy.on_trading_day("2026-01-08", [("J", 4), ("K", 3), ("L", 2)])

        self.assertEqual(first.enter, ("A", "B", "C"))
        self.assertEqual(second.enter, ("D", "E", "F"))
        self.assertEqual(second.exit, ())
        self.assertEqual(third.enter, ("G", "H", "I"))
        self.assertEqual(third.exit, ())
        self.assertEqual(fourth.enter, ("J", "K", "L"))
        self.assertEqual(fourth.exit, ("A", "B", "C"))
        self.assertEqual(fourth.expired_signal_dates, ("2026-01-05",))
        self.assertEqual(fourth.holding_day, 3)
        self.assertEqual(fourth.reason, "rollover")

    def test_reenters_on_next_available_signal_after_exit(self):
        policy = TopNHoldPolicy(top_n=3, holding_days=3)
        policy.on_trading_day("2026-01-05", [("A", 3)])
        policy.on_trading_day("2026-01-06", [])
        policy.on_trading_day("2026-01-07", [])
        exit_action = policy.on_trading_day("2026-01-08", [])
        reentry = policy.on_trading_day("2026-01-09", [("B", 2), ("A", 1)])

        self.assertEqual(exit_action.exit, ("A",))
        self.assertEqual(reentry.enter, ("B", "A"))

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            TopNHoldPolicy(top_n=0)
        with self.assertRaises(ValueError):
            TopNHoldPolicy(holding_days=0)


class BacktestInputTest(unittest.TestCase):
    def test_run_directory_requires_one_method_and_ignores_intraday(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for artifact_key, method, code in [
                ("2026-11-17", "scm", "600000.SH"),
                ("2026-11-17", "b2", "000001.SZ"),
                ("2026-11-17.intraday", "scm", "000002.SZ"),
                ("2026-11-18", "scm", "600001.SH"),
            ]:
                artifact = root / f"{artifact_key}.{method}"
                artifact.mkdir()
                (artifact / "ranked.json").write_text(
                    json.dumps({
                        "artifact_key": artifact_key,
                        "method": method,
                        "rows": [{"code": code, "model_rank": 1, "model_score": 0.9}],
                    }),
                    encoding="utf-8",
                )

            with self.assertRaisesRegex(ValueError, "--method"):
                load_signal_bundle(root)
            bundle = load_signal_bundle(root, method="scm")

        self.assertEqual(bundle.dates, ("2026-11-17", "2026-11-18"))
        self.assertEqual(bundle.symbols, ("600000.SH", "600001.SH"))

    def test_ranked_directory_infers_date_from_artifact_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            ranked = Path(temporary) / "2026-11-17.scm" / "ranked.json"
            ranked.parent.mkdir()
            ranked.write_text(
                json.dumps(
                    {
                        "artifact_key": "2026-11-17",
                        "method": "scm",
                        "rows": [
                            {"code": "600000.SH", "model_rank": 1, "model_score": 0.9}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            bundle = load_signal_bundle(ranked.parent.parent)

        self.assertEqual(bundle.dates, ("2026-11-17",))
        self.assertEqual(bundle.rows_for_date("2026-11-17")[0].code, "600000.SH")

    def test_signal_csv_infers_date_from_artifact_directory_when_date_column_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "2026-11-17.scm"
            artifact.mkdir()
            signal_file = artifact / "signals.csv"
            signal_file.write_text("code,model_rank,model_score\n600000.SH,1,0.9\n", encoding="utf-8")

            bundle = load_signal_bundle(signal_file)

        self.assertEqual(bundle.dates, ("2026-11-17",))

    @unittest.skipUnless(__import__("importlib.util").util.find_spec("pandas"), "pandas is provided by the backtest extra")
    def test_market_csv_is_normalized_by_symbol(self):
        import pandas as pd

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "market.csv"
            pd.DataFrame(
                [
                    {
                        "code": "000001",
                        "date": "2026-11-17",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10.5,
                        "volume": 1000,
                    }
                ]
            ).to_csv(path, index=False)

            market = load_market_data(path)

        self.assertEqual(tuple(market), ("000001",))
        self.assertEqual(market["000001"].columns.tolist(), ["datetime", "open", "high", "low", "close", "volume"])


if __name__ == "__main__":
    unittest.main()
