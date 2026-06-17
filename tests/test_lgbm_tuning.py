import sys
import types
import unittest
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from ml.cli import main
from ml.tuning.grid import default_grid_trials
from ml.tuning.objectives import score_trial_report
from ml.tuning.optuna_search import require_optuna


class LgbmTuningTest(unittest.TestCase):
    def test_default_grid_trials_include_ranking_controls(self):
        trials = default_grid_trials(max_trials=4)

        self.assertEqual(len(trials), 4)
        for trial in trials:
            self.assertIn("lambdarank_truncation_level", trial)
            self.assertIn("eval_at", trial)
            self.assertIn("top_k", trial)

    def test_score_trial_report_prioritizes_lower_top3_loss_rate(self):
        lower_loss = {
            "metrics": {
                "test": {
                    "top3_ret3_le_0_rate": 10.0,
                    "top3_ret3_positive_rate": 40.0,
                    "top3_ret3_ge_5_rate": 10.0,
                    "rank_ic_ret3": 0.01,
                }
            }
        }
        higher_loss_with_better_positive = {
            "metrics": {
                "test": {
                    "top3_ret3_le_0_rate": 30.0,
                    "top3_ret3_positive_rate": 90.0,
                    "top3_ret3_ge_5_rate": 60.0,
                    "rank_ic_ret3": 0.4,
                }
            }
        }

        self.assertGreater(score_trial_report(lower_loss), score_trial_report(higher_loss_with_better_positive))

    def test_score_trial_report_prefers_rolling_summary_over_holdout_metrics(self):
        rolling_winner_holdout_loser = {
            "rolling_summary": {
                "test_avg": {
                    "top3_ret3_le_0_rate": 10.0,
                    "top3_ret3_positive_rate": 50.0,
                    "top3_ret3_ge_5_rate": 20.0,
                    "rank_ic_ret3": 0.05,
                }
            },
            "metrics": {
                "test": {
                    "top3_ret3_le_0_rate": 80.0,
                    "top3_ret3_positive_rate": 10.0,
                    "top3_ret3_ge_5_rate": 0.0,
                    "rank_ic_ret3": -0.5,
                }
            },
        }
        rolling_loser_holdout_winner = {
            "rolling_summary": {
                "test_avg": {
                    "top3_ret3_le_0_rate": 40.0,
                    "top3_ret3_positive_rate": 80.0,
                    "top3_ret3_ge_5_rate": 60.0,
                    "rank_ic_ret3": 0.5,
                }
            },
            "metrics": {
                "test": {
                    "top3_ret3_le_0_rate": 5.0,
                    "top3_ret3_positive_rate": 95.0,
                    "top3_ret3_ge_5_rate": 80.0,
                    "rank_ic_ret3": 0.8,
                }
            },
        }

        self.assertGreater(score_trial_report(rolling_winner_holdout_loser), score_trial_report(rolling_loser_holdout_winner))

    def test_require_optuna_reports_missing_optional_dependency(self):
        with patch.dict(sys.modules, {"optuna": None}):
            with self.assertRaisesRegex(RuntimeError, "Optuna is required"):
                require_optuna()

    def test_require_optuna_returns_module_when_available(self):
        fake_optuna = types.SimpleNamespace(__version__="fixture")
        with patch.dict(sys.modules, {"optuna": fake_optuna}):
            self.assertIs(require_optuna(), fake_optuna)

    def test_cli_reports_missing_optuna_without_traceback(self):
        stderr = io.StringIO()
        stdout = io.StringIO()

        with patch.dict(sys.modules, {"optuna": None}):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = main(["tune", "lgbm-rank", "--strategy", "optuna"])

        self.assertNotEqual(rc, 0)
        output = stderr.getvalue() + stdout.getvalue()
        self.assertIn("Optuna is required", output)
        self.assertNotIn("Traceback", output)
        self.assertNotIn("NotImplementedError", output)

    def test_optuna_strategy_samples_params_and_writes_rich_summary(self):
        class FakeTrial:
            number = 0

            def __init__(self):
                self.params = {}
                self.user_attrs = {}
                self.suggest_calls = []

            def suggest_categorical(self, name, choices):
                self.suggest_calls.append(("categorical", name, list(choices)))
                value = {
                    "feature_set": "raw_plus_signal",
                    "label_column": "rank_label_5d",
                    "boosting_type": "dart",
                    "categorical_encoding": "native",
                    "num_leaves": 9,
                    "min_data_in_leaf": 120,
                    "num_boost_round": 80,
                    "early_stopping_rounds": 20,
                    "lambdarank_truncation_level": 8,
                }.get(name, list(choices)[0])
                self.params[name] = value
                return value

            def suggest_float(self, name, low, high, **kwargs):
                self.suggest_calls.append(("float", name, low, high, kwargs))
                value = {
                    "learning_rate": 0.035,
                    "bagging_fraction": 0.72,
                    "feature_fraction": 0.83,
                    "lambda_l1": 0.11,
                    "lambda_l2": 0.22,
                    "min_gain_to_split": 0.03,
                }.get(name, low)
                self.params[name] = value
                return value

            def set_user_attr(self, name, value):
                self.user_attrs[name] = value

        captured_study_kwargs = {}

        class FakeSampler:
            def __init__(self, *, seed):
                self.seed = seed

        class FakeStudy:
            study_name = "fixture-study"
            direction = "maximize"

            def __init__(self):
                self.trials = []
                self.best_trial = None
                self.best_value = None
                self.best_params = None

            def optimize(self, objective, n_trials):
                for _index in range(n_trials):
                    trial = FakeTrial()
                    value = objective(trial)
                    trial.value = value
                    self.trials.append(trial)
                self.best_trial = self.trials[0]
                self.best_value = self.trials[0].value
                self.best_params = dict(self.trials[0].params)

        def fake_create_study(**kwargs):
            captured_study_kwargs.update(kwargs)
            return fake_study

        fake_study = FakeStudy()
        fake_optuna = types.SimpleNamespace(
            __version__="3.4.0",
            samplers=types.SimpleNamespace(TPESampler=FakeSampler),
            create_study=fake_create_study,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "tuning"
            dataset = Path(temp_dir) / "rank_dataset.csv"
            dataset.write_text("date,code,rank_label_5d\n", encoding="utf-8")

            def fake_train_and_report(_dataset, output_dir, **kwargs):
                report = {
                    "feature_set": kwargs["feature_set"],
                    "label_column": kwargs["label_column"],
                    "model_params": {
                        "boosting_type": kwargs["boosting_type"],
                        "categorical_encoding": kwargs["categorical_encoding"],
                        "num_leaves": kwargs["num_leaves"],
                        "min_data_in_leaf": kwargs["min_data_in_leaf"],
                        "num_boost_round": kwargs["num_boost_round"],
                        "learning_rate": kwargs["learning_rate"],
                        "bagging_fraction": kwargs["bagging_fraction"],
                        "feature_fraction": kwargs["feature_fraction"],
                        "lambda_l1": kwargs["lambda_l1"],
                        "lambda_l2": kwargs["lambda_l2"],
                        "min_gain_to_split": kwargs["min_gain_to_split"],
                        "early_stopping_rounds": kwargs["early_stopping_rounds"],
                        "lambdarank_truncation_level": kwargs["lambdarank_truncation_level"],
                    },
                    "model_artifacts": {
                        "model": str(output_dir / "model.txt"),
                        "metadata": str(output_dir / "model_metadata.json"),
                    },
                    "metrics": {
                        "test": {
                            "top3_ret3_le_0_rate": 12.0,
                            "top3_ret3_positive_rate": 62.0,
                            "top3_ret3_ge_5_rate": 32.0,
                            "rank_ic_ret3": 0.12,
                        }
                    },
                    "rolling_summary": {
                        "test_avg": {
                            "top3_ret3_le_0_rate": 10.0,
                            "top3_ret3_positive_rate": 60.0,
                            "top3_ret3_ge_5_rate": 30.0,
                            "rank_ic_ret3": 0.1,
                        }
                    },
                    "output_dir": str(output_dir),
                }
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "lgbm_rank_report_raw_plus_signal_rank_label_5d.json").write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
                return report

            with patch.dict(sys.modules, {"optuna": fake_optuna}):
                with patch("ml.tuning.optuna_search.train_lgbm_rank.train_and_report", side_effect=fake_train_and_report) as train_and_report:
                    with contextlib.redirect_stdout(io.StringIO()):
                        rc = main(
                            [
                                "tune",
                                "lgbm-rank",
                                "--strategy",
                                "optuna",
                                "--method",
                                "b2",
                                "--dataset",
                                str(dataset),
                                "--output-root",
                                str(output_root),
                                "--max-trials",
                                "1",
                                "--seed",
                                "29",
                                "--rolling-folds",
                                "2",
                                "--skip-rf-diagnostics",
                            ]
                        )

            summary = json.loads((output_root / "tuning_summary.json").read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        kwargs = train_and_report.call_args.kwargs
        self.assertEqual(kwargs["feature_set"], "raw_plus_signal")
        self.assertEqual(kwargs["label_column"], "rank_label_5d")
        self.assertEqual(kwargs["boosting_type"], "dart")
        self.assertEqual(kwargs["categorical_encoding"], "native")
        self.assertEqual(kwargs["num_boost_round"], 80)
        self.assertEqual(kwargs["learning_rate"], 0.035)
        self.assertEqual(kwargs["early_stopping_rounds"], 0)
        self.assertEqual(kwargs["bagging_fraction"], 0.72)
        self.assertEqual(kwargs["seed"], 29)
        self.assertEqual(captured_study_kwargs["direction"], "maximize")
        self.assertIsInstance(captured_study_kwargs["sampler"], FakeSampler)
        self.assertEqual(captured_study_kwargs["sampler"].seed, 29)
        self.assertIn(("categorical", "feature_set", ["raw_numeric", "raw_plus_signal", "raw_plus_signal_macd"]), fake_study.trials[0].suggest_calls)
        self.assertIn(("categorical", "categorical_encoding", ["one_hot", "native"]), fake_study.trials[0].suggest_calls)
        self.assertIn(("categorical", "num_boost_round", [40, 60, 80, 120, 160]), fake_study.trials[0].suggest_calls)
        self.assertIn(("categorical", "early_stopping_rounds", [0, 10, 20, 40]), fake_study.trials[0].suggest_calls)
        self.assertTrue(any(call[0] == "float" and call[1] == "learning_rate" for call in fake_study.trials[0].suggest_calls))
        self.assertTrue(any(call[0] == "float" and call[1] == "bagging_fraction" for call in fake_study.trials[0].suggest_calls))
        self.assertEqual(summary["strategy"], "optuna")
        self.assertEqual(summary["method"], "b2")
        self.assertEqual(summary["dataset"], str(dataset))
        self.assertEqual(summary["output_root"], str(output_root))
        self.assertEqual(summary["seed"], 29)
        self.assertEqual(summary["optuna_version"], "3.4.0")
        self.assertEqual(summary["sampler"], "TPESampler")
        self.assertEqual(summary["study_name"], "fixture-study")
        self.assertEqual(summary["direction"], "maximize")
        self.assertEqual(summary["best_trial"], 1)
        self.assertEqual(summary["best_score"], fake_study.best_value)
        self.assertEqual(summary["best_params"]["boosting_type"], "dart")
        self.assertEqual(summary["best_params"]["early_stopping_rounds"], 0)
        self.assertEqual(summary["best_output_dir"], str(output_root / "optuna-trial-001"))
        self.assertEqual(summary["best_report_path"], str(output_root / "optuna-trial-001" / "lgbm_rank_report_raw_plus_signal_rank_label_5d.json"))
        self.assertEqual(summary["trials"][0]["params"]["feature_set"], "raw_plus_signal")
        self.assertEqual(summary["trials"][0]["params"]["early_stopping_rounds"], 0)
        self.assertEqual(summary["trials"][0]["output_dir"], str(output_root / "optuna-trial-001"))
        self.assertEqual(summary["trials"][0]["report_path"], str(output_root / "optuna-trial-001" / "lgbm_rank_report_raw_plus_signal_rank_label_5d.json"))
        self.assertEqual(summary["trials"][0]["metrics"]["test"]["top3_ret3_positive_rate"], 62.0)
        self.assertEqual(summary["trials"][0]["rolling_summary"]["test_avg"]["top3_ret3_positive_rate"], 60.0)
        self.assertEqual(summary["trials"][0]["model_params"]["early_stopping_rounds"], 0)
        self.assertEqual(summary["trials"][0]["model_artifacts"]["model"], str(output_root / "optuna-trial-001" / "model.txt"))

    def test_grid_is_default_and_writes_summary_without_optuna(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "tuning"
            dataset = Path(temp_dir) / "rank_dataset.csv"
            dataset.write_text("date,code,rank_label_3d\n", encoding="utf-8")

            def fake_train_and_report(_dataset, output_dir, **kwargs):
                return {
                    "model_params": {"boosting_type": kwargs["boosting_type"]},
                    "metrics": {
                        "test": {
                            "top3_ret3_le_0_rate": 20.0,
                            "top3_ret3_positive_rate": 55.0,
                            "top3_ret3_ge_5_rate": 15.0,
                            "rank_ic_ret3": 0.02,
                        }
                    },
                    "output_dir": str(output_dir),
                }

            with patch.dict(sys.modules, {"optuna": None}):
                with patch("ml.tuning.grid.train_lgbm_rank.train_and_report", side_effect=fake_train_and_report) as train_and_report:
                    with contextlib.redirect_stdout(io.StringIO()):
                        rc = main(
                            [
                                "tune",
                                "lgbm-rank",
                                "--method",
                                "b2",
                                "--dataset",
                                str(dataset),
                                "--output-root",
                                str(output_root),
                                "--max-trials",
                                "1",
                                "--skip-rf-diagnostics",
                            ]
                        )

            summary = json.loads((output_root / "tuning_summary.json").read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(train_and_report.call_count, 1)
        self.assertEqual(train_and_report.call_args.kwargs["seed"], 17)
        self.assertEqual(summary["strategy"], "grid")
        self.assertEqual(summary["method"], "b2")
        self.assertEqual(summary["dataset"], str(dataset))
        self.assertEqual(summary["output_root"], str(output_root))
        self.assertEqual(summary["trials"][0]["output_dir"], str(output_root / "trial_001"))

    def test_explicit_grid_strategy_does_not_require_optuna_and_trains(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "tuning"
            dataset = Path(temp_dir) / "rank_dataset.csv"
            dataset.write_text("date,code,rank_label_3d\n", encoding="utf-8")

            def fake_train_and_report(_dataset, output_dir, **kwargs):
                return {
                    "model_params": {"boosting_type": kwargs["boosting_type"]},
                    "metrics": {
                        "test": {
                            "top3_ret3_le_0_rate": 20.0,
                            "top3_ret3_positive_rate": 55.0,
                            "top3_ret3_ge_5_rate": 15.0,
                            "rank_ic_ret3": 0.02,
                        }
                    },
                    "output_dir": str(output_dir),
                }

            with patch.dict(sys.modules, {"optuna": None}):
                with patch("ml.tuning.grid.train_lgbm_rank.train_and_report", side_effect=fake_train_and_report) as train_and_report:
                    with contextlib.redirect_stdout(io.StringIO()):
                        rc = main(
                            [
                                "tune",
                                "lgbm-rank",
                                "--strategy",
                                "grid",
                                "--dataset",
                                str(dataset),
                                "--output-root",
                                str(output_root),
                                "--max-trials",
                                "1",
                                "--skip-rf-diagnostics",
                            ]
                        )

        self.assertEqual(rc, 0)
        self.assertEqual(train_and_report.call_count, 1)


if __name__ == "__main__":
    unittest.main()
