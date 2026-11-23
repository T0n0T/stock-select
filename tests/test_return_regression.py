from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ml.training.lgbm_ranker import train_model_result
from ml.tuning.backtest import suggest_portfolio_params, training_rows_before


class ReturnRegressionTest(unittest.TestCase):
    def test_signed_decimal_targets_train_and_reload_without_prediction_labels(self):
        import lightgbm as lgb
        import numpy as np

        train = [{"date": "2026-02-05", "code": str(i), "x": i / 10,
                  "exit_net_return": i / 10 - 3.25} for i in range(60)]
        test = [{"date": "2026-02-06", "code": str(i), "x": i / 10,
                 "exit_net_return": "unknown future"} for i in [2, 50]]
        real_train = lgb.train
        for objective, metric in [("regression", "l2"), ("regression_l1", "l1")]:
            with self.subTest(objective=objective), patch("lightgbm.train", wraps=real_train) as fit:
                result = train_model_result(
                    train, test, numeric_columns=["x"], categorical_columns=[],
                    num_leaves=5, min_data_in_leaf=3, num_boost_round=20,
                    learning_rate=.1, label_column="exit_net_return", num_threads=4,
                    training_objective=objective, lambdarank_truncation_level=3,
                )
                params, dataset = fit.call_args.args
                np.testing.assert_allclose(dataset.get_label(), [r["exit_net_return"] for r in train], atol=1e-6)
                self.assertIsNone(dataset.get_group())
                self.assertEqual(params["objective"], objective)
                self.assertEqual(params["metric"], metric)
                for rank_only in ["label_gain", "eval_at", "lambdarank_truncation_level"]:
                    self.assertNotIn(rank_only, params)
                self.assertLess(result.test_scored[0]["model_score"], 0)
                self.assertGreater(result.test_scored[1]["model_score"], 0)
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "model.txt"
                    result.model.save_model(str(path))
                    reloaded = lgb.Booster(model_file=str(path))
                    np.testing.assert_allclose(reloaded.predict([[.2], [5.]]),
                                               [r["model_score"] for r in result.test_scored])

    def test_regression_rejects_missing_or_nonfinite_training_targets(self):
        for value in ["", None, "nan", "inf", "-inf"]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite.*exit_net_return"):
                train_model_result(
                    [{"date": "2026-02-05", "code": "A", "x": 1, "exit_net_return": value}],
                    [{"date": "2026-02-06", "code": "A", "x": 2}],
                    numeric_columns=["x"], categorical_columns=[], num_leaves=3,
                    min_data_in_leaf=1, num_boost_round=2, learning_rate=.1,
                    label_column="exit_net_return", num_threads=4, training_objective="regression",
                )

    def test_continuous_target_is_not_rebinned_and_actual_exit_is_purged(self):
        rows = [{"date": "2026-02-05", "code": code, "exit_date": end,
                 "exit_net_return": value, "rank_label_exit": 3}
                for code, end, value in [("A", "2026-02-06", -2.75),
                                         ("B", "2026-02-10", 19.5),
                                         ("C", "2026-02-09", .125)]]
        safe = training_rows_before(rows, {"2026-02-05"}, "2026-02-10", {}, label_column="exit_net_return")
        self.assertEqual([(r["code"], r["exit_net_return"]) for r in safe], [("A", -2.75), ("C", .125)])
        self.assertEqual(rows[0]["rank_label_exit"], 3)

    def test_regression_search_uses_return_target_and_searches_loss(self):
        trial = Mock()
        trial.suggest_categorical.side_effect = lambda _name, choices: choices[0]
        trial.suggest_float.side_effect = lambda _name, low, _high, **_kwargs: low
        params = suggest_portfolio_params(trial, holding_days=3, top_n=3, label_column="exit_net_return")
        self.assertEqual(params["training_objective"], "regression")
        self.assertEqual(params["label_column"], "exit_net_return")
        searched = {call.args[0]: call.args[1] for call in trial.suggest_categorical.call_args_list}
        self.assertEqual(searched["training_objective"], ["regression", "regression_l1"])
        self.assertNotIn("lambdarank_truncation_level", searched)
        self.assertNotIn("label_gain", params)
        self.assertNotIn("eval_at", params)

    def test_regression_cli_requires_rule_exit_and_akquant(self):
        from ml.cli import build_parser
        from ml.tuning.grid import main_from_args

        parser = build_parser()
        for extra in [[], ["--objective", "akquant"]]:
            args = parser.parse_args(["tune", "lgbm-rank", "--strategy", "optuna",
                                      "--learning-task", "return-regression", *extra])
            with self.assertRaisesRegex(ValueError, "return-regression requires"):
                main_from_args(args)
        args = parser.parse_args(["tune", "lgbm-rank", "--strategy", "optuna", "--objective", "akquant",
                                  "--exit-policy", "exit.json", "--learning-task", "return-regression"])
        with patch("ml.tuning.optuna_search.run_optuna_search", return_value=0) as run:
            self.assertEqual(main_from_args(args), 0)
        run.assert_called_once_with(args)

    def test_regression_loss_survives_parameter_normalization(self):
        from ml.training.trial_params import lightgbm_ranking_params_with_defaults
        params = lightgbm_ranking_params_with_defaults({"training_objective": "regression_l1"})
        self.assertEqual(params["training_objective"], "regression_l1")


if __name__ == "__main__":
    unittest.main()
