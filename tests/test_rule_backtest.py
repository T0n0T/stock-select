from __future__ import annotations

import importlib.util
import unittest

from ml.backtest.akquant_gateway import BacktestConfig, run_akquant_backtest
from ml.backtest.report import build_report
from ml.backtest.rule_exit import ExitMarket, ExitPolicyConfig
from ml.backtest.signal_bundle import SignalBundle, SignalRow
from tests.test_policy_labels import market_fixture


@unittest.skipUnless(importlib.util.find_spec("akquant") and importlib.util.find_spec("pandas"), "install backtest extra")
class RuleBacktestTest(unittest.TestCase):
    def test_expected_untradable_order_does_not_hide_other_rejection_reasons(self):
        from types import SimpleNamespace
        import pandas as pd
        from ml.backtest.akquant_gateway import _raise_on_rejected_orders
        orders = pd.DataFrame([{"id": "entry", "symbol": "A", "side": "buy",
                                "status": "rejected", "reject_reason": "Insufficient cash"}])
        with self.assertRaisesRegex(RuntimeError, "Insufficient cash"):
            _raise_on_rejected_orders(SimpleNamespace(orders_df=orders), untradable_entry_order_ids={"entry"})

    def test_suspended_next_open_records_unfilled_order_without_replacement_or_late_fill(self):
        dates, market = market_fixture()
        market["B"] = market["A"].copy()
        market["A"] = market["A"].drop(index=[25])
        day, next_day = str(dates[24].date()), str(dates[25].date())
        signals = SignalBundle({day: (SignalRow(day, "A", 2., 1), SignalRow(day, "B", 1., 2))})
        prepared = ExitMarket(market, ExitPolicyConfig())
        self.assertEqual(prepared.outcome("A", day)["status"], "untradable_entry")
        result = run_akquant_backtest(market, signals, BacktestConfig(top_n=1),
                                     exit_policy=ExitPolicyConfig(), exit_market=prepared)
        report = build_report(result)
        self.assertEqual(report["actions"][0]["enter"], ["A"])
        self.assertEqual(len(report["orders"]), 1)
        self.assertEqual(report["orders"][0]["symbol"], "A")
        self.assertEqual(report["orders"][0]["status"], "rejected")
        self.assertIn("Missing market data", report["orders"][0]["reject_reason"])
        self.assertEqual(report["trades"], [])
        self.assertEqual(report["open_batches"], [])
        event = report["unfilled_entries"][0]
        self.assertEqual((event["signal_date"], event["date"], event["code"]), (day, next_day, "A"))

    def test_rule_strategy_rejects_disabling_t_plus_one(self):
        dates, market = market_fixture()
        day = str(dates[24].date())
        signals = SignalBundle({day: (SignalRow(day, "A", 1., 1),)})
        with self.assertRaisesRegex(ValueError, "T\\+1"):
            run_akquant_backtest(market, signals, BacktestConfig(t_plus_one=False),
                                exit_policy=ExitPolicyConfig())

    def test_suspended_t3_is_checked_on_first_resumed_close(self):
        dates, market = market_fixture([10.] * 25 + [10.5] * 3 + [10.2] * 7)
        market["calendar"] = market["A"].copy()
        market["A"] = market["A"].drop(index=[28])
        day = str(dates[24].date())
        signals = SignalBundle({day: (SignalRow(day, "A", 1., 1),)})
        result = run_akquant_backtest(market, signals, BacktestConfig(), exit_policy=ExitPolicyConfig())
        event = build_report(result)["exit_events"][0]
        self.assertEqual(event["exit_date"], str(dates[29].date()))
        self.assertEqual(event["reasons"], ["t3_return_below_3pct"])
        self.assertEqual(event["holding_sessions"], 5)

    def test_cli_accepts_shared_exit_policy_for_backtest_and_training(self):
        from ml.cli import build_parser
        parser=build_parser()
        args=parser.parse_args(["backtest","run","--signals","signals.csv","--market-data","market.parquet",
                               "--output","report.json","--exit-policy","exit.json","--backtest-end-date","2026-11-19"])
        self.assertEqual(str(args.exit_policy),"exit.json")
        args=parser.parse_args(["tune","lgbm-rank","--strategy","optuna","--objective","akquant","--exit-policy","exit.json"])
        self.assertEqual(str(args.exit_policy),"exit.json")

    def test_exit_rules_match_label_dates_and_close_prices_with_overlapping_batches(self):
        dates,market=market_fixture()
        signals=SignalBundle({str(dates[i].date()):(SignalRow(str(dates[i].date()),"A",1.,1),) for i in [24,25]})
        config=BacktestConfig(top_n=1,capital_allocation=.9)
        policy=ExitPolicyConfig()
        prepared=ExitMarket(market,policy)
        result=run_akquant_backtest(market,signals,config,exit_policy=policy,exit_market=prepared)
        orders=result.orders_df
        self.assertTrue((orders["status"]=="filled").all())
        self.assertEqual(orders["side"].tolist().count("buy"),2)
        self.assertEqual(orders["side"].tolist().count("sell"),2)
        report=build_report(result)
        self.assertEqual(report["open_batches"],[])
        for event in report["exit_events"]:
            outcome=prepared.outcome("A",event["signal_date"])
            self.assertEqual(event["exit_date"],outcome["exit_date"])
            self.assertEqual(event["reasons"],[outcome["exit_reason"]])
            sell=orders[(orders["side"]=="sell") & (orders["tag"]==event["signal_date"])].iloc[0]
            self.assertEqual(sell["avg_price"],outcome["exit_price"])
            self.assertEqual(str(sell["updated_at"].date()),outcome["exit_date"])
        self.assertEqual(report["strategy_config"]["exit_policy"]["timeout_days"],3)

    def test_gap_entry_uses_actual_next_open_for_return_and_t3_condition(self):
        dates,market=market_fixture()
        market["A"].loc[25,["open","high"]]=[11.,11.2]
        day=str(dates[24].date())
        signals=SignalBundle({day:(SignalRow(day,"A",1.,1),)})
        result=run_akquant_backtest(market,signals,BacktestConfig(top_n=1,capital_allocation=.9),exit_policy=ExitPolicyConfig())
        trade=result.trades_df.iloc[0]
        self.assertAlmostEqual(trade["return_pct"],(10.2/11.-1)*100)

    def test_right_censored_position_is_marked_to_market_and_not_forced_closed(self):
        dates,market=market_fixture([10.]*25+[10.4]*10)
        day=str(dates[24].date())
        signals=SignalBundle({day:(SignalRow(day,"A",1.,1),)})
        result=run_akquant_backtest(market,signals,BacktestConfig(top_n=1,capital_allocation=.9),exit_policy=ExitPolicyConfig())
        report=build_report(result)
        self.assertTrue(result.trades_df.empty)
        self.assertEqual(result.orders_df["side"].tolist(),["buy"])
        self.assertEqual(len(report["open_batches"]),1)
        self.assertEqual(report["metrics"]["open_batch_count"],1)
        self.assertGreater(report["metrics"]["total_return_pct"],0)


if __name__=="__main__":
    unittest.main()
