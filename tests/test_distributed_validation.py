import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import date, timedelta

from ml.tuning.validation import distributed_backtest_splits, exclude_reserved_label_spans


class DistributedValidationTest(unittest.TestCase):
    def setUp(self):
        self.days = [(date(2023, 2, 1) + timedelta(days=i)).isoformat() for i in range(1200)
                     if (date(2023, 2, 1) + timedelta(days=i)).weekday() < 5]

    def plan(self, seed=17):
        return distributed_backtest_splits(
            self.days, self.days, initial_train_dates=120, test_dates=20,
            holdout_dates=10, purge_gap=4, seed=seed,
        )

    def test_quarter_blocks_are_reproducible_random_and_cover_multiple_years(self):
        plan = self.plan()
        self.assertEqual(plan, self.plan())
        self.assertNotEqual(plan["holdout_dates"], self.plan(seed=18)["holdout_dates"])
        self.assertGreaterEqual(len(plan["holdout_splits"]), 10)
        self.assertEqual({days[0][:4] for _, days in plan["holdout_splits"]},
                         {"2023", "2024", "2025", "2026"})
        for role in ("development_splits", "holdout_splits"):
            expected = 20 if role == "development_splits" else 10
            for _, days in plan[role]:
                if role == "development_splits":
                    self.assertGreaterEqual(len(days), 5)
                    self.assertLessEqual(len(days), expected)
                else:
                    self.assertEqual(len(days), expected)
                positions = [self.days.index(day) for day in days]
                self.assertEqual(positions, list(range(positions[0], positions[0] + len(days))))

    def test_holdout_is_never_used_for_training_or_tuning_and_all_models_use_past(self):
        plan = self.plan()
        reserved = set(plan["holdout_dates"])
        development_tests = {day for _, test in plan["development_splits"] for day in test}
        self.assertFalse(reserved & development_tests)
        self.assertFalse(reserved & set(plan["development_dates"]))
        for train, test in plan["development_splits"] + plan["holdout_splits"]:
            self.assertTrue(train)
            self.assertFalse(set(train) & reserved)
            self.assertLess(self.days.index(train[-1]) + 4, self.days.index(test[0]))

    def test_training_label_interval_cannot_touch_reserved_dates(self):
        rows = [{"date": "2023-08-01", "code": "A"},
                {"date": "2023-08-01", "code": "B"},
                {"date": "2023-08-10", "code": "C"}]
        ends = {("2023-08-01", "A"): "2023-08-10",
                ("2023-08-01", "B"): "2023-08-08",
                ("2023-08-10", "C"): "2023-08-14"}
        safe = exclude_reserved_label_spans(rows, ends, ["2023-08-09", "2023-08-10"])
        self.assertEqual([row["code"] for row in safe], ["B"])

    def test_too_short_history_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "quarter"):
            distributed_backtest_splits(self.days[:125], self.days[:125], initial_train_dates=120,
                                       test_dates=20, holdout_dates=10, purge_gap=4, seed=17)

    def test_partial_final_quarter_is_included_with_a_shorter_development_block(self):
        days = [day for day in self.days if day <= "2025-10-31"]
        plan = distributed_backtest_splits(days, days, initial_train_dates=120, test_dates=20,
                                          holdout_dates=10, purge_gap=4, seed=17)
        last = plan["quarter_blocks"][-1]
        self.assertEqual(last["quarter"], "2025Q4")
        self.assertEqual(len(last["holdout"]), 10)
        self.assertGreaterEqual(len(last["development"]), 5)
        self.assertLess(len(last["development"]), 20)

    def test_distributed_holdout_reports_all_folds_and_keeps_last_model_scope_explicit(self):
        from ml.tuning.backtest import PortfolioEvaluator
        evaluator = PortfolioEvaluator.__new__(PortfolioEvaluator)
        evaluator.args = SimpleNamespace(rolling_train_dates=120, top_n=3)
        evaluator.development = ["2023-02-01"]
        evaluator.holdout = ["2023-08-01", "2024-08-01"]
        evaluator.holdout_splits = [(["2023-02-01"], ["2023-08-01"]),
                                    (["2023-02-01", "2024-02-01"], ["2024-08-01"])]
        evaluator.exit_policy = None
        evaluator.holdout_end = "2024-09-01"
        evaluator.numeric, evaluator.categorical = ["x"], []
        evaluator.label_column = "rank_label_exit"
        fits = []
        for day, value in zip(evaluator.holdout, [5, -2]):
            row = {"date": day, "code": "A", "model_score": 1, "exit_net_return": value}
            result = SimpleNamespace(test_scored=[row], category_levels={}, feature_names=["x"],
                                     lightgbm_feature_names=["x"], categorical_code_maps={},
                                     model=Mock(), top_features=[], feature_count=1)
            fits.append((result, {"train": [], "test": [row],
                                 "report": {"model_params": {}, "test_row_count": 1,
                                            "test_start_date": day, "test_end_date": day,
                                            "metrics": {"train": {}, "test": {}},
                                            "metrics_as_of": evaluator.holdout_end}}))
        evaluator._fit = Mock(side_effect=fits)
        evaluator._portfolio = Mock(return_value={"total_return_pct": 1})
        with tempfile.TemporaryDirectory() as temp, \
                patch("ml.tuning.backtest.write_feature_manifest", return_value=Path(temp) / "manifest.json"), \
                patch("ml.tuning.backtest.build_model_metadata", return_value={}), \
                patch("ml.tuning.backtest.write_model_artifacts", return_value={}):
            summary = evaluator.evaluate_holdout({}, Path(temp))
            report = json.loads((Path(temp) / "lgbm_rank_report_holdout.json").read_text())
        self.assertEqual(evaluator._fit.call_count, 2)
        self.assertEqual(summary["metrics"]["test"]["top3_exit_net_return_positive_rate"], 50.0)
        self.assertEqual(report["evaluated_prediction_rows"], 2)
        self.assertEqual(report["validation_roles"]["exported_model"], "last_holdout_fold")

    def test_quarter_scheme_requires_akquant_instead_of_being_silently_ignored(self):
        from ml.cli import build_parser
        from ml.tuning.grid import main_from_args
        args = build_parser().parse_args(["tune", "lgbm-rank", "--validation-scheme", "quarter-blocks"])
        with self.assertRaisesRegex(ValueError, "quarter-blocks.*akquant"):
            main_from_args(args)


if __name__ == "__main__":
    unittest.main()
