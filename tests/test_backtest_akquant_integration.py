from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


HAS_BACKTEST_DEPS = importlib.util.find_spec("akquant") is not None and importlib.util.find_spec("pandas") is not None


@unittest.skipUnless(HAS_BACKTEST_DEPS, "install the backtest extra to run AKQuant integration tests")
class AkQuantBacktestIntegrationTest(unittest.TestCase):
    def _market(self, symbols: tuple[str, ...], dates):
        import pandas as pd

        result = {}
        for symbol_index, symbol in enumerate(symbols):
            base = 10.0 + symbol_index
            opens = [base + day_index * 0.1 for day_index in range(len(dates))]
            result[symbol] = pd.DataFrame(
                {
                    "datetime": dates,
                    "open": opens,
                    "high": [price + 0.5 for price in opens],
                    "low": [price - 0.5 for price in opens],
                    "close": opens,
                    "volume": [1_000_000] * len(dates),
                }
            )
        return result

    def test_overlapping_daily_batches_sell_only_when_each_batch_expires(self):
        import pandas as pd

        from ml.backtest.akquant_gateway import BacktestConfig, run_akquant_backtest
        from ml.backtest.report import build_report
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        dates = pd.bdate_range("2026-01-05", periods=7)
        date_keys = [item.date().isoformat() for item in dates]
        market = self._market(("A", "B", "C", "D", "E", "F"), dates)
        signals = SignalBundle(
            {
                date_keys[0]: (
                    SignalRow(date_keys[0], "A", 0.9, 1),
                    SignalRow(date_keys[0], "B", 0.8, 2),
                    SignalRow(date_keys[0], "C", 0.7, 3),
                ),
                # Each signal day creates an independent batch.
                date_keys[1]: (
                    SignalRow(date_keys[1], "A", 1.0, 1),
                    SignalRow(date_keys[1], "D", 0.9, 2),
                ),
                date_keys[2]: (SignalRow(date_keys[2], "E", 1.0, 1),),
            }
        )

        result = run_akquant_backtest(market, signals, BacktestConfig())
        actions = {day: action for day, action in result.strategy.action_history}
        orders = result.orders_df.copy()
        orders["created_day"] = pd.to_datetime(orders["created_at"]).dt.date.astype(str)
        orders["filled_day"] = pd.to_datetime(orders["updated_at"]).dt.date.astype(str)

        self.assertEqual(actions[date_keys[0]].enter, ("A", "B", "C"))
        self.assertEqual(actions[date_keys[1]].enter, ("A", "D"))
        self.assertEqual(actions[date_keys[2]].enter, ("E",))
        self.assertEqual(actions[date_keys[3]].exit, ("B", "C"))
        self.assertEqual(actions[date_keys[3]].holding_day, 3)

        initial_buys = orders[(orders["side"] == "buy") & (orders["created_day"] == date_keys[0])]
        first_basket_sells = orders[(orders["side"] == "sell") & (orders["created_day"] == date_keys[3])]
        self.assertEqual(set(initial_buys["symbol"]), {"A", "B", "C"})
        self.assertEqual(set(first_basket_sells["symbol"]), {"A", "B", "C"})
        self.assertFalse(((orders["side"] == "sell") & (orders["created_day"] < date_keys[3])).any())
        self.assertTrue((orders["status"] == "filled").all())
        self.assertTrue((orders["filled_quantity"] == orders["quantity"]).all())
        self.assertEqual(set(initial_buys["filled_day"]), {date_keys[1]})
        self.assertEqual(set(first_basket_sells["filled_day"]), {date_keys[4]})
        self.assertEqual(
            initial_buys.set_index("symbol")["quantity"].to_dict(),
            first_basket_sells.set_index("symbol")["quantity"].to_dict(),
        )
        a_buy = orders[(orders["symbol"] == "A") & (orders["created_day"] == date_keys[1])]
        a_sell = orders[(orders["symbol"] == "A") & (orders["created_day"] == date_keys[4])]
        self.assertEqual(a_buy["side"].tolist(), ["buy"])
        self.assertEqual(a_sell["side"].tolist(), ["sell"])
        self.assertEqual(a_sell["quantity"].tolist(), a_buy["quantity"].tolist())
        for _, order in initial_buys.iterrows():
            expected_open = market[order["symbol"]].iloc[1]["open"]
            self.assertAlmostEqual(order["avg_price"], expected_open)

        # The result contains serializable order, trade, metric, equity, and action data.
        self.assertIsInstance(json.dumps(build_report(result), ensure_ascii=False), str)

    def test_cli_reads_daily_ranked_artifact_and_writes_portfolio_return(self):
        import pandas as pd

        from ml.cli import main

        dates = pd.bdate_range("2026-01-02", periods=8)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "select" / "2026-01-05.scm"
            run.mkdir(parents=True)
            symbols = ("600000.SH", "000001.SZ", "600001.SH", "000002.SZ")
            (run / "ranked.json").write_text(json.dumps({
                "artifact_key": "2026-01-05",
                "method": "scm",
                "rows": [
                    {"code": symbol, "model_rank": rank, "model_score": rank / 10}
                    for rank, symbol in enumerate(symbols, 1)
                ],
            }), encoding="utf-8")
            market = pd.concat([
                frame.assign(symbol=symbol)
                for symbol, frame in self._market(symbols, dates).items()
            ])
            market_file = root / "daily.parquet"
            market.to_parquet(market_file)
            output = root / "backtest.json"
            args = [
                "backtest", "run", "--signals", str(run.parent), "--method", "scm",
                "--market-data", str(market_file), "--output", str(output),
            ]

            self.assertEqual(main(args), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertGreater(report["metrics"]["total_return_pct"], 0)
            self.assertEqual(len(report["equity_curve"]), 5)
            self.assertEqual(report["actions"][0]["enter"], list(symbols[:3]))
            self.assertNotIn("weights", report["actions"][0])
            self.assertEqual(report["actions"][3]["expired_signal_dates"], ["2026-01-05"])
            self.assertEqual({order["tag"] for order in report["orders"]}, {"2026-01-05"})

            policy_file = root / "entry-policy.json"
            policy_file.write_text('{"name":"weak-off","by_environment":{"weak":{"allow_new_positions":false}}}', encoding="utf-8")
            context_file = root / "daily-context.csv"
            context_file.write_text("date,env\n2026-01-05,weak\n", encoding="utf-8")
            self.assertEqual(main(args + ["--entry-policy", str(policy_file), "--daily-context", str(context_file)]), 0)
            blocked = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(blocked["orders"], [])
            self.assertEqual(blocked["actions"][0]["enter"], [])
            self.assertEqual(blocked["daily_budgets"][0]["daily_budget"], 0)

    def test_rejects_market_data_that_ends_before_scheduled_exit_fill(self):
        import pandas as pd

        from ml.backtest.akquant_gateway import run_akquant_backtest
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        day = "2026-01-05"
        market = self._market(("A",), pd.bdate_range(day, periods=4))
        signals = SignalBundle({day: (SignalRow(day, "A", 1.0, 1),)})

        with self.assertRaisesRegex(ValueError, r"2026-01-05.*4 later trading sessions"):
            run_akquant_backtest(market, signals)

    def test_rejects_missing_selected_symbol_on_next_open_instead_of_filling_later(self):
        import pandas as pd

        from ml.backtest.akquant_gateway import run_akquant_backtest
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        day = "2026-01-05"
        dates = pd.bdate_range(day, periods=6)
        signals = SignalBundle({day: (SignalRow(day, "A", 1.0, 1),)})

        for missing_index in (0, 1, 4):
            with self.subTest(day=dates[missing_index]):
                market = self._market(("A", "B"), dates)
                market["A"] = market["A"].drop(index=missing_index)
                with self.assertRaisesRegex(ValueError, rf"A.*{dates[missing_index]:%Y-%m-%d}"):
                    run_akquant_backtest(market, signals)

    def test_rejects_multiple_bars_for_one_symbol_and_trading_day(self):
        import pandas as pd

        from ml.backtest.akquant_gateway import run_akquant_backtest
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        day = "2026-01-05"
        market = self._market(("A",), pd.bdate_range(day, periods=5))
        second_bar = market["A"].iloc[[0]].assign(datetime=pd.Timestamp(day) + pd.Timedelta(hours=1))
        market["A"] = pd.concat([market["A"], second_bar], ignore_index=True)
        signals = SignalBundle({day: (SignalRow(day, "A", 1.0, 1),)})

        with self.assertRaisesRegex(ValueError, r"A.*one bar per trading day"):
            run_akquant_backtest(market, signals)

    def test_suspended_exit_waits_for_first_tradable_open(self):
        import pandas as pd
        from ml.backtest.akquant_gateway import BacktestConfig, run_akquant_backtest
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        day = "2026-01-05"
        dates = pd.bdate_range(day, periods=7)
        market = self._market(("A", "B"), dates)
        market["A"] = market["A"].drop(index=4)
        signals = SignalBundle({day: (SignalRow(day, "A", 1.0, 1),)})
        result = run_akquant_backtest(market, signals, BacktestConfig(defer_suspended_exit=True))
        orders = result.orders_df
        sell = orders[orders["side"] == "sell"].iloc[0]
        self.assertEqual(sell["status"], "filled")
        self.assertEqual(pd.Timestamp(sell["updated_at"]).date(), dates[5].date())
        self.assertEqual(sell["avg_price"], market["A"].loc[5, "open"])

    def test_delayed_exit_reduces_new_batch_to_available_cash(self):
        import pandas as pd
        from ml.backtest.akquant_gateway import BacktestConfig, run_akquant_backtest
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        dates = pd.bdate_range("2026-01-05", periods=9)
        market = self._market(("A", "B", "C", "D"), dates)
        market["A"] = market["A"].drop(index=4)
        signals = SignalBundle({str(dates[i].date()): (SignalRow(str(dates[i].date()), code, 1, 1),)
                                for i, code in enumerate(["A", "B", "C", "D"])})
        result = run_akquant_backtest(market, signals, BacktestConfig(top_n=1, capital_allocation=0.9, defer_suspended_exit=True))
        orders = result.orders_df
        self.assertTrue((orders["status"] == "filled").all())
        buys = orders[orders["side"] == "buy"].set_index("symbol")
        self.assertLess(buys.loc["D", "quantity"] * 13, 150_000)

    def test_blocked_new_entries_preserve_exits_and_allow_later_reentry(self):
        import pandas as pd
        from ml.backtest.akquant_gateway import BacktestConfig, run_akquant_backtest
        from ml.backtest.entry_policy import EntryPolicy, EntryRule
        from ml.backtest.report import build_report
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        dates = pd.bdate_range("2026-01-05", periods=9)
        days = [str(day.date()) for day in dates]
        market = self._market(("A",), dates)
        signals = SignalBundle({day: (SignalRow(day, "A", 1, 1),) for day in days[:5]})
        environments = dict(zip(days, ["strong", "weak", "weak", "weak", "strong"]))
        policy = EntryPolicy(by_environment={"strong": EntryRule(), "weak": EntryRule(False)})

        result = run_akquant_backtest(market, signals, BacktestConfig(top_n=1, capital_allocation=0.9),
                                      entry_policy=policy, environments=environments)
        report = build_report(result)
        buys = result.orders_df[result.orders_df["side"] == "buy"]
        sells = result.orders_df[result.orders_df["side"] == "sell"]
        self.assertEqual(buys["tag"].tolist(), [days[0], days[4]])
        self.assertEqual(sells["tag"].tolist(), [days[0], days[4]])
        self.assertEqual(pd.Timestamp(sells.iloc[0]["updated_at"]).date(), dates[4].date())
        blocked = report["actions"][3]
        self.assertEqual(blocked["enter"], [])
        self.assertEqual(blocked["expired_signal_dates"], [days[0]])
        self.assertFalse(blocked["entry_decision"]["allow_new_positions"])
        self.assertEqual(blocked["entry_decision"]["environment"], "weak")
        self.assertEqual({row["group"] for row in report["diagnostics"]["attribution_by_environment"]}, {"strong"})
        self.assertAlmostEqual(sum(row["total_pnl"] for row in report["diagnostics"]["attribution_by_symbol"]),
                               result.trades_df["net_pnl"].sum())

    def test_daily_budget_controls_quantity_and_all_blocked_run_stays_in_cash(self):
        import pandas as pd
        from ml.backtest.akquant_gateway import BacktestConfig, run_akquant_backtest
        from ml.backtest.entry_policy import EntryPolicy, EntryRule
        from ml.backtest.report import build_report
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        day = "2026-01-05"
        market = self._market(("A",), pd.bdate_range(day, periods=5))
        signals = SignalBundle({day: (SignalRow(day, "A", 1, 1),)})
        config = BacktestConfig(top_n=1, capital_allocation=0.9)
        regular = run_akquant_backtest(market, signals, config)
        reduced = run_akquant_backtest(market, signals, config,
                                       entry_policy=EntryPolicy(default=EntryRule(daily_equity_fraction=0.15)))
        blocked = run_akquant_backtest(market, signals, config,
                                       entry_policy=EntryPolicy(default=EntryRule(False)))

        self.assertEqual(regular.orders_df.iloc[0]["quantity"], 30_000)
        self.assertEqual(reduced.orders_df.iloc[0]["quantity"], 15_000)
        report = build_report(reduced)
        self.assertEqual(report["daily_budgets"][0]["daily_budget"], 150_000)
        self.assertEqual(report["strategy_config"]["entry_policy"]["default"]["daily_equity_fraction"], 0.15)
        self.assertTrue(report["diagnostics"]["exposure"])
        self.assertEqual(len(report["cash_curve"]), len(report["equity_curve"]))
        self.assertTrue(blocked.orders_df.empty)
        self.assertTrue((blocked.equity_curve == config.initial_cash).all())
        self.assertTrue(all(not action.enter for _, action in blocked.strategy.action_history))

    def test_fee_tax_transfer_and_t_plus_one_settings_reach_akquant(self):
        import akquant as aq
        import pandas as pd

        from ml.backtest.akquant_gateway import BacktestConfig, run_akquant_backtest
        from ml.backtest.signal_bundle import SignalBundle, SignalRow

        day = "2026-01-05"
        market = self._market(("A",), pd.bdate_range(day, periods=5))
        empty_result = SimpleNamespace(orders_df=pd.DataFrame())
        config = BacktestConfig(
            commission_rate=0.002,
            stamp_tax_rate=0.003,
            transfer_fee_rate=0.004,
            min_commission=7.0,
            lot_size=10,
            t_plus_one=False,
        )
        signals = SignalBundle({day: (SignalRow(day, "A", 1.0, 1),)})

        with patch.object(aq, "run_backtest", return_value=empty_result) as run:
            run_akquant_backtest(market, signals, config)

        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["commission_rate"], 0.002)
        self.assertEqual(kwargs["stamp_tax_rate"], 0.003)
        self.assertEqual(kwargs["transfer_fee_rate"], 0.004)
        self.assertEqual(kwargs["min_commission"], 7.0)
        self.assertEqual(kwargs["lot_size"], 10)
        self.assertFalse(kwargs["t_plus_one"])
        self.assertIsInstance(kwargs["fill_policy"], aq.NextOpen)

    def test_rejected_orders_fail_the_backtest(self):
        import pandas as pd

        from ml.backtest.akquant_gateway import _raise_on_rejected_orders

        result = SimpleNamespace(
            orders_df=pd.DataFrame(
                [{"symbol": "A", "side": "buy", "quantity": 100, "status": "rejected", "reject_reason": "insufficient cash"}]
            )
        )
        with self.assertRaisesRegex(RuntimeError, "insufficient cash"):
            _raise_on_rejected_orders(result)

    def test_report_is_strict_json_serializable(self):
        import pandas as pd

        from ml.backtest.report import build_report

        result = SimpleNamespace(
            metrics=SimpleNamespace(),
            metrics_df=pd.DataFrame(
                {"value": [1.25, float("nan"), pd.Timestamp("2026-01-05")]},
                index=["total_return", "optional_metric", "start_time"],
            ),
            equity_curve=pd.Series([100.0], index=[pd.Timestamp("2026-01-05")]),
            orders_df=pd.DataFrame([{"created_at": pd.Timestamp("2026-01-05"), "quantity": 100}]),
            trades_df=pd.DataFrame(),
            strategy=SimpleNamespace(action_history=[]),
        )

        report = build_report(result)

        self.assertIsInstance(json.dumps(report, ensure_ascii=False, allow_nan=False), str)
        self.assertIsNone(report["metrics"]["optional_metric"])


if __name__ == "__main__":
    unittest.main()
