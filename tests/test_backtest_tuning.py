import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from ml.tuning.backtest import (
    latest_oof_signals,
    partition_backtest_dates,
    suggest_portfolio_params,
    training_rows_before,
    optimize_portfolio,
    align_strategy_labels,
)


class BacktestTuningTest(unittest.TestCase):
    def test_training_window_comparison_keeps_identical_oof_dates(self):
        from ml.tuning.backtest import anchored_training_windows
        reference = [(["01", "02", "03", "04"], ["06", "07"]),
                     (["03", "04", "05", "06"], ["08", "09"])]
        shorter = anchored_training_windows(reference, train_date_count=2)
        self.assertEqual(shorter, [(["03", "04"], ["06", "07"]),
                                   (["05", "06"], ["08", "09"])])
        self.assertEqual(reference[0][0], ["01", "02", "03", "04"])
        for count in [0, 5]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                anchored_training_windows(reference, train_date_count=count)

    def test_exit_label_is_fixed_in_search_and_actual_exit_is_purged(self):
        trial=Mock()
        trial.suggest_categorical.side_effect=lambda _name,choices:choices[0]
        trial.suggest_float.side_effect=lambda _name,low,_high,**_kwargs:low
        params=suggest_portfolio_params(trial,holding_days=3,top_n=3,label_column="rank_label_exit")
        self.assertEqual(params["label_column"],"rank_label_exit")
        rows=[{"date":"2026-02-05","code":"A","exit_date":"2026-02-10","exit_net_return":10,"rank_label_exit":3}]
        self.assertEqual(training_rows_before(rows,{"2026-02-05"},"2026-02-10",{},label_column="rank_label_exit"),[])

    def test_default_stamp_tax_matches_current_a_share_rate(self):
        from ml.backtest.akquant_gateway import BacktestConfig
        from ml.cli import build_parser
        self.assertEqual(BacktestConfig().stamp_tax_rate, 0.0005)
        args = build_parser().parse_args(["backtest", "run", "--signals", "signals.csv", "--market-data", "prices.parquet", "--output", "report.json"])
        self.assertEqual(args.stamp_tax_rate, 0.0005)

    def test_partition_reserves_holdout_and_its_label_gap(self):
        dates = [f"2026-01-{day:02d}" for day in range(1, 31)]
        development, holdout = partition_backtest_dates(dates, dates, holding_days=3, holdout_dates=5)
        self.assertEqual(holdout, dates[21:26])
        self.assertEqual(development, dates[:17])
        self.assertLess(dates.index(development[-1]) + 4, dates.index(holdout[0]))

    def test_oof_uses_latest_model_and_ignores_inherited_rank(self):
        rows = [
            {"date": "2026-01-05", "code": "A", "fold": 1, "candidate_score": 99, "model_rank": 1},
            {"date": "2026-01-05", "code": "B", "fold": 1, "candidate_score": 0, "model_rank": 2},
            {"date": "2026-01-05", "code": "A", "fold": 2, "candidate_score": 0, "model_rank": 1},
            {"date": "2026-01-05", "code": "B", "fold": 2, "candidate_score": 2, "model_rank": 2},
        ]
        bundle = latest_oof_signals(rows)
        self.assertEqual([row.code for row in bundle.rows_for_date("2026-01-05")], ["B", "A"])
        self.assertEqual([row.model_rank for row in bundle.rows_for_date("2026-01-05")], [1, 2])

    def test_strategy_horizon_and_training_rounds_stay_fixed(self):
        class Trial:
            def suggest_categorical(self, name, choices):
                self_calls[name] = choices
                return choices[0]

            def suggest_float(self, _name, low, _high, **_kwargs):
                return low

        self_calls = {}
        params = suggest_portfolio_params(Trial(), holding_days=3, top_n=3)
        self.assertEqual(params["label_column"], "rank_label_3d")
        self.assertEqual(params["early_stopping_rounds"], 0)
        self.assertEqual(params["feature_set"], "all")
        self.assertNotIn("label_column", self_calls)
        self.assertNotIn("holding_days", self_calls)
        self.assertNotIn("early_stopping_rounds", self_calls)

    def test_holdout_must_leave_enough_development_dates(self):
        with self.assertRaisesRegex(ValueError, "holdout"):
            partition_backtest_dates(["2026-01-05"], ["2026-01-05"], holding_days=3, holdout_dates=40)

    def test_suspended_stock_label_cannot_cross_validation_boundary(self):
        rows = [
            {"date": "2026-01-05", "code": "A", "ret3": 2, "rank_label_3d": 3},
            {"date": "2026-01-05", "code": "B", "ret3": 10, "rank_label_3d": 3},
            {"date": "2026-01-05", "code": "C", "ret3": 5, "rank_label_3d": 0},
        ]
        ends = {("2026-01-05", "A"): "2026-01-09", ("2026-01-05", "B"): "2026-02-03", ("2026-01-05", "C"): "2026-01-09"}
        safe = training_rows_before(rows, {"2026-01-05"}, "2026-01-12", ends, label_column="rank_label_3d")
        self.assertEqual([row["code"] for row in safe], ["A", "C"])
        # Rank labels are rebuilt using only returns known before validation.
        self.assertEqual(safe[0]["rank_label_3d"], 0)
        self.assertEqual(rows[0]["rank_label_3d"], 3)

    def test_optuna_value_comes_from_portfolio_not_label_diagnostics(self):
        try:
            import optuna
        except ImportError:
            self.skipTest("install tuning extra")
        evaluate = Mock(side_effect=[
            {"backtest_metrics": {"total_return_pct": -2.5}, "rolling_summary": {"rank_ic_ret3": 0.9}},
            {"backtest_metrics": {"total_return_pct": 1.25}, "rolling_summary": {"rank_ic_ret3": -0.9}},
        ])
        with tempfile.TemporaryDirectory() as temporary:
            summary = optimize_portfolio(optuna, evaluate, output_root=Path(temporary),
                max_trials=2, patience=4, seed=17, holding_days=3, top_n=3)
        self.assertEqual(summary["best_score"], 1.25)
        self.assertEqual(summary["best_trial"], 2)
        self.assertEqual(evaluate.call_count, 2)

    def test_cli_accepts_akquant_objective_and_requires_optuna(self):
        from ml.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["tune", "lgbm-rank", "--strategy", "optuna", "--objective", "akquant", "--market-data", "prices.parquet"])
        self.assertEqual(args.holding_days, 3)
        from ml.tuning.grid import main_from_args
        args.strategy = "grid"
        with self.assertRaisesRegex(ValueError, "optuna"):
            main_from_args(args)

    def test_exit_policy_cannot_be_silently_ignored_by_other_objectives(self):
        from ml.cli import build_parser
        from ml.tuning.grid import main_from_args
        args = build_parser().parse_args(["tune", "lgbm-rank", "--strategy", "optuna", "--exit-policy", "exit.json"])
        with self.assertRaisesRegex(ValueError, "--objective akquant"):
            main_from_args(args)

    def test_labels_use_calendar_holding_days_and_defer_only_untradable_exit(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("install backtest extra")
        dates = pd.bdate_range("2026-01-05", periods=8)
        market = {
            "A": pd.DataFrame({"datetime": dates, "open": [10, 11, 12, 13, 14, 15, 16, 17]}).drop(index=[2, 4]),
            "calendar": pd.DataFrame({"datetime": dates, "open": [1] * 8}),
        }
        rows, ends = align_strategy_labels([{"date": "2026-01-05", "code": "A", "ret3": 999}], market, holding_days=3)
        self.assertAlmostEqual(rows[0]["ret3"], (15 / 11 - 1) * 100)
        self.assertEqual(ends[("2026-01-05", "A")], dates[5].date().isoformat())

    def test_winner_is_selected_before_holdout_evaluation(self):
        from types import SimpleNamespace
        from ml.tuning.backtest import run_akquant_study
        from unittest.mock import patch
        events = []
        with tempfile.TemporaryDirectory() as temporary:
            evaluator = Mock(root=Path(temporary), dataset=Path("dataset.csv"), label_column="rank_label_3d", split_summary={})
            evaluator.evaluate.return_value = {}
            evaluator.evaluate_holdout.side_effect = lambda params, directory, **kwargs: events.append(("holdout", params)) or {}
            winner = {"best_params": {"num_leaves": 5}, "trials": [{"trial": 1}], "best_trial": 1}
            def search(*args, **kwargs):
                events.append(("search", None))
                return dict(winner)
            args = SimpleNamespace(market_data=Path("market.parquet"), holding_days=3, max_trials=2, patience=4, seed=17, top_n=3, method="scm")
            with patch("ml.tuning.backtest.PortfolioEvaluator", return_value=evaluator), patch("ml.tuning.backtest.optimize_portfolio", side_effect=search):
                run_akquant_study(args, Mock())
        self.assertEqual(events[0][0], "search")
        self.assertEqual(events[1], ("holdout", winner["best_params"]))
