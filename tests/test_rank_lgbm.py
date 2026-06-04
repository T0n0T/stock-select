import unittest

from scripts.ml.train_rank_lgbm import (
    average_metric_dicts,
    build_feature_matrix,
    build_feature_matrix_from_metadata,
    build_model_metadata,
    evaluate_model,
    load_feature_manifest,
    resolve_dataset_path,
    resolve_output_dir,
    rolling_walk_forward_splits,
    rows_for_dates,
    select_feature_columns,
    walk_forward_split_dates,
)


class RankLgbmTest(unittest.TestCase):
    def test_default_paths_are_method_scoped(self):
        self.assertTrue(resolve_dataset_path(None, method="b1").as_posix().endswith("diagnostics/ml/b1/rank_dataset.csv"))
        self.assertTrue(resolve_output_dir(None, method="b1").as_posix().endswith("diagnostics/ml/b1/model"))

    def test_walk_forward_split_dates_keeps_date_groups_ordered(self):
        train_dates, test_dates = walk_forward_split_dates(
            ["2026-01-03", "2026-01-01", "2026-01-02", "2026-01-04", "2026-01-05"],
            test_ratio=0.4,
        )

        self.assertEqual(train_dates, ["2026-01-01", "2026-01-02", "2026-01-03"])
        self.assertEqual(test_dates, ["2026-01-04", "2026-01-05"])

    def test_rolling_walk_forward_splits_use_ordered_windows(self):
        dates = [f"2026-01-{day:02d}" for day in range(1, 11)]

        splits = rolling_walk_forward_splits(dates, train_date_count=4, test_date_count=2, fold_count=3)

        self.assertEqual(splits[0], (dates[0:4], dates[4:6]))
        self.assertEqual(splits[1], (dates[2:6], dates[6:8]))
        self.assertEqual(splits[2], (dates[4:8], dates[8:10]))

    def test_select_feature_columns_excludes_artifact_scores_and_labels(self):
        columns = [
            "date",
            "code",
            "env",
            "model_score",
            "model_rank",
            "llm_action",
            "risk_flags",
            "current_score",
            "baseline_score",
            "close_to_zxdkx_pct",
            "daily_macd_phase_type",
            "signal_type",
            "ret3",
            "rank_label_3d",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="all")

        self.assertEqual(numeric, ["close_to_zxdkx_pct"])
        self.assertEqual(categorical, ["env", "daily_macd_phase_type", "signal_type"])

    def test_build_feature_matrix_one_hot_encodes_categoricals(self):
        rows = [
            {"date": "2026-01-01", "env": "weak", "signal_type": "rebound", "close_to_zxdkx_pct": "1.5"},
            {"date": "2026-01-01", "env": "strong", "signal_type": "trend_start", "close_to_zxdkx_pct": ""},
        ]

        matrix, feature_names = build_feature_matrix(
            rows,
            numeric_columns=["close_to_zxdkx_pct"],
            categorical_columns=["env", "signal_type"],
        )

        self.assertIn("close_to_zxdkx_pct", feature_names)
        self.assertIn("env=weak", feature_names)
        self.assertIn("signal_type=trend_start", feature_names)
        self.assertEqual(matrix[0][feature_names.index("close_to_zxdkx_pct")], 1.5)
        self.assertEqual(matrix[1][feature_names.index("close_to_zxdkx_pct")], 0.0)

    def test_model_metadata_rebuilds_feature_matrix_with_training_levels(self):
        train_rows = [
            {"date": "2026-01-01", "env": "weak", "close_to_zxdkx_pct": "1.5"},
            {"date": "2026-01-02", "env": "strong", "close_to_zxdkx_pct": "2.5"},
        ]
        score_rows = [
            {"date": "2026-01-03", "env": "neutral", "close_to_zxdkx_pct": ""},
            {"date": "2026-01-03", "env": "weak", "close_to_zxdkx_pct": "3.5"},
        ]
        levels = {"env": ["weak", "strong"]}
        expected_matrix, feature_names = build_feature_matrix(
            score_rows,
            numeric_columns=["close_to_zxdkx_pct"],
            categorical_columns=["env"],
            levels=levels,
        )
        metadata = build_model_metadata(
            feature_manifest="/tmp/feature_manifest.json",
            train_rows=train_rows,
            score_rows=score_rows,
            numeric_columns=["close_to_zxdkx_pct"],
            categorical_columns=["env"],
            levels=levels,
            feature_names=feature_names,
            lightgbm_feature_names=["close_to_zxdkx_pct", "env_weak", "env_strong"],
            label_column="rank_label_3d",
            model_params={"num_leaves": 9},
        )

        matrix, rebuilt_names = build_feature_matrix_from_metadata(score_rows, metadata)

        self.assertEqual(rebuilt_names, feature_names)
        self.assertEqual(matrix, expected_matrix)
        self.assertEqual(matrix[0], [0.0, 0.0, 0.0])

    def test_rows_for_dates_uses_requested_label_column(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "1", "rank_label_5d": ""},
            {"date": "2026-01-01", "code": "b", "rank_label_3d": "", "rank_label_5d": "3"},
        ]

        selected = rows_for_dates(rows, {"2026-01-01"}, label_column="rank_label_5d")

        self.assertEqual([row["code"] for row in selected], ["b"])

    def test_evaluate_model_reports_ret3_and_ret5_metrics(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "model_score": 3, "ret3": "6", "ret5": "-1"},
            {"date": "2026-01-01", "code": "b", "model_score": 2, "ret3": "-1", "ret5": "8"},
            {"date": "2026-01-01", "code": "c", "model_score": 1, "ret3": "2", "ret5": "1"},
        ]

        metrics = evaluate_model(rows, top_n=2)

        self.assertEqual(metrics["top2_ret3_positive_rate"], 50.0)
        self.assertEqual(metrics["top2_ret3_ge_5_rate"], 50.0)
        self.assertEqual(metrics["top2_ret5_positive_rate"], 50.0)
        self.assertEqual(metrics["top2_ret5_ge_5_rate"], 50.0)
        self.assertIn("rank_ic_ret5", metrics)

    def test_load_feature_manifest_filters_unknown_and_excluded_columns(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feature_manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "numeric_features": ["close_to_zxdkx_pct", "missing_factor", "ret3"],
                        "categorical_features": ["env", "signal_type", "baseline_verdict"],
                        "excluded_features": ["ret3", "baseline_verdict"],
                    }
                ),
                encoding="utf-8",
            )

            numeric, categorical = load_feature_manifest(
                path,
                available_columns={"close_to_zxdkx_pct", "env", "signal_type", "ret3", "baseline_verdict"},
            )

        self.assertEqual(numeric, ["close_to_zxdkx_pct"])
        self.assertEqual(categorical, ["env", "signal_type"])

    def test_average_metric_dicts_skip_missing_values(self):
        average = average_metric_dicts(
            [
                {"rank_ic_ret3": "0.1", "top3_ret3_ge_5_rate": 20},
                {"rank_ic_ret3": "", "top3_ret3_ge_5_rate": 40},
            ]
        )

        self.assertEqual(average["rank_ic_ret3"], 0.1)
        self.assertEqual(average["top3_ret3_ge_5_rate"], 30.0)


if __name__ == "__main__":
    unittest.main()
