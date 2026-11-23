import argparse
import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ml.backfill import candidates, record, runs
from ml.diagnostics.controlled_rerank import TrialModelConfig, rolling_oof_predictions
from ml.scoring.score_blends import rolling_scores_for_trial
from ml.training.labels import label_purge_gap
from ml.training.lgbm_ranker import TrainedModelResult
from ml.training.trial_params import LIGHTGBM_RANKING_DEFAULTS
from ml.training.train_lgbm_rank import (
    parse_args,
    rolling_walk_forward_splits,
    train_and_report,
    walk_forward_split_dates,
)
from ml.tuning import grid


class TrainingConstraintsTest(unittest.TestCase):
    def test_training_and_tuning_default_to_eight_threads(self):
        self.assertEqual(parse_args([]).num_threads, 8)
        parser = argparse.ArgumentParser()
        grid.add_parser(parser.add_subparsers())
        self.assertEqual(parser.parse_args(["lgbm-rank"]).num_threads, 8)

    def test_training_and_backfill_reject_parallelism_outside_one_to_eight(self):
        window = ["--start-date", "2026-01-01", "--end-date", "2026-11-19"]
        tuning = argparse.ArgumentParser()
        grid.add_parser(tuning.add_subparsers())
        parsers = [
            (parse_args, [], "--num-threads"),
            (tuning.parse_args, ["lgbm-rank"], "--num-threads"),
            (candidates.parse_args, window, "--workers"),
            (runs.parse_args, window, "--workers"),
            (record.parse_args, [], "--workers"),
            (candidates.parse_args, window, "--jobs"),
            (runs.parse_args, window, "--jobs"),
            (record.parse_args, [], "--jobs"),
        ]
        for parser, args, option in parsers:
            for count in ("0", "-1", "9", "16"):
                with self.subTest(parser=parser, option=option, count=count):
                    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                        parser([*args, option, count])

    def test_direct_training_rejects_excess_threads_before_reading_data(self):
        with self.assertRaisesRegex(ValueError, "8"):
            train_and_report(Path("missing.csv"), Path("unused"), test_ratio=0.2, num_threads=9)

    def test_single_split_purges_label_window_before_test(self):
        dates = [f"2026-01-{day:02d}" for day in range(1, 21)]
        train, test = walk_forward_split_dates(dates, test_ratio=0.2, purge_gap=4)
        self.assertEqual(train, dates[:12])
        self.assertEqual(test, dates[16:])

    def test_rolling_split_preserves_train_count_and_purges_four_dates(self):
        dates = [f"2026-01-{day:02d}" for day in range(1, 21)]
        splits = rolling_walk_forward_splits(
            dates, train_date_count=8, test_date_count=4, fold_count=2, purge_gap=4
        )
        self.assertEqual(splits, [(dates[:8], dates[12:16]), (dates[4:12], dates[16:20])])
        for train, test in splits:
            self.assertLess(dates.index(train[-1]) + 4, dates.index(test[0]))

    def test_split_fails_if_purge_would_remove_all_training_dates(self):
        dates = ["2026-01-05", "2026-01-06", "2026-01-07"]
        with self.assertRaisesRegex(ValueError, "purge"):
            walk_forward_split_dates(dates, test_ratio=0.3, purge_gap=4)
        with self.assertRaisesRegex(ValueError, "not enough"):
            rolling_walk_forward_splits(
                dates, train_date_count=2, test_date_count=1, fold_count=1, purge_gap=4
            )

    def test_label_windows_include_next_open_entry(self):
        for label, gap in [("rank_label_3d", 4), ("ret3_ge5_label", 4),
                           ("rank_label_5d", 6), ("ret5_ge5_label", 6), ("rank_label_10d", 11)]:
            with self.subTest(label=label):
                self.assertEqual(label_purge_gap(label), gap)

    def test_training_infers_purge_and_applies_it_to_every_fold(self):
        dates = [f"2026-01-{day:02d}" for day in range(1, 21)]
        rows = [{"date": day, "code": "A", "rank_label_3d": 1, "close_to_zxdkx_pct": 1} for day in dates]

        def fake_train(train, test, **_kwargs):
            return TrainedModelResult(
                [{**row, "model_score": 1} for row in train],
                [{**row, "model_score": 1} for row in test], [], 1, None, [], [], {}, {},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with patch("ml.training.train_lgbm_rank.train_model_result", side_effect=fake_train) as train:
                report = train_and_report(
                    dataset, root / "model", test_ratio=0.2, num_threads=0,
                    rf_diagnostics=False, rolling_folds=2, rolling_train_dates=8, rolling_test_dates=4,
                )
        self.assertEqual(train.call_count, 3)
        self.assertEqual(report["purge_gap"], 4)
        self.assertEqual(report["rolling_summary"]["purge_gap"], 4)
        self.assertEqual(report["model_params"]["num_threads"], 8)
        for call in train.call_args_list:
            last_train = dates.index(call.args[0][-1]["date"])
            first_test = dates.index(call.args[1][0]["date"])
            self.assertLess(last_train + 4, first_test)
            self.assertEqual(call.kwargs["num_threads"], 8)

    def test_oof_predictions_use_the_longest_label_window(self):
        dates = [f"2026-01-{day:02d}" for day in range(1, 25)]
        rows = [{"date": day, "code": "A", "rank_label_3d": 1, "rank_label_5d": 1} for day in dates]
        configs = [
            TrialModelConfig(
                name=name, numeric_columns=["factor"], categorical_columns=[],
                fixed_categorical_levels={}, categorical_encoding="one_hot",
                label_column=label, model_params={"num_threads": 1},
            )
            for name, label in [("main", "rank_label_3d"), ("risk", "rank_label_5d")]
        ]

        def fake_train(train, test, **_kwargs):
            self.assertLess(dates.index(train[-1]["date"]) + 6, dates.index(test[0]["date"]))
            return TrainedModelResult([], [{**row, "model_score": 1} for row in test], [], 1,
                                      None, [], [], {}, {})

        with patch("ml.diagnostics.controlled_rerank.train_model_result", side_effect=fake_train):
            scores = rolling_oof_predictions(rows, configs, rolling_train_dates=8,
                                             rolling_test_dates=4, rolling_folds=2)
        self.assertEqual(len(scores), 8)
        self.assertTrue(all(row["purge_gap"] == 6 for row in scores))

    def test_score_blends_purge_training_label_window(self):
        dates = [f"2026-01-{day:02d}" for day in range(1, 21)]
        rows = [{"date": day, "code": "A", "rank_label_3d": 1} for day in dates]
        config = {**LIGHTGBM_RANKING_DEFAULTS, "label_column": "rank_label_3d",
                  "feature_manifest": "manifest.json", "categorical_encoding": "one_hot"}

        def fake_train(train, test, **_kwargs):
            self.assertLess(dates.index(train[-1]["date"]) + 4, dates.index(test[0]["date"]))
            return [], [{**row, "model_score": 1} for row in test], [], 1

        with patch("ml.scoring.score_blends.load_trial_config", return_value=config), patch(
            "ml.scoring.score_blends.load_feature_manifest_with_levels", return_value=(["factor"], [], {})
        ), patch("ml.scoring.score_blends.train_model", side_effect=fake_train):
            scores, summary = rolling_scores_for_trial(
                rows, trial_dir=Path("unused"), method="scm", rolling_train_dates=8,
                rolling_test_dates=4, rolling_folds=2,
            )
        self.assertEqual(len(scores), 8)
        self.assertEqual(summary["purge_gap"], 4)

    def test_oof_signal_export_keeps_candidates_without_future_labels(self):
        rows = [
            {"date": f"2026-01-{day:02d}", "code": code, "rank_label_3d": label}
            for day in range(1, 21) for code, label in [("A", "1"), ("B", "")]
        ]
        config = TrialModelConfig(
            name="main", numeric_columns=["factor"], categorical_columns=[],
            fixed_categorical_levels={}, categorical_encoding="one_hot",
            label_column="rank_label_3d", model_params={"num_threads": 1},
        )

        def fake_train(train, test, **_kwargs):
            self.assertEqual({row["code"] for row in train}, {"A"})
            self.assertEqual({row["code"] for row in test}, {"A", "B"})
            return TrainedModelResult([], [{**row, "model_score": 1} for row in test], [], 1,
                                      None, [], [], {}, {})

        with patch("ml.diagnostics.controlled_rerank.train_model_result", side_effect=fake_train):
            scores = rolling_oof_predictions(
                rows, [config], rolling_train_dates=8, rolling_test_dates=4,
                rolling_folds=1, include_unlabeled_test=True,
            )
        self.assertEqual(len(scores), 8)
