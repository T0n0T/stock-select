import csv
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ml.train_rank_lgbm import (
    RandomForestDiagnosticsConfig,
    RandomForestThresholdError,
    average_metric_dicts,
    build_feature_matrix,
    build_feature_matrix_from_metadata,
    build_model_metadata,
    evaluate_model,
    labels,
    load_feature_manifest,
    parse_args,
    resolve_dataset_path,
    resolve_output_dir,
    rolling_walk_forward_splits,
    rows_for_dates,
    run_random_forest_diagnostics,
    select_features_by_rf_importance,
    select_feature_columns,
    train_and_report,
    validate_selected_feature_coverage,
    train_model_result,
    walk_forward_split_dates,
)
from scripts.ml import build_rank_dataset as rank_dataset_schema


class RankLgbmTest(unittest.TestCase):
    def test_default_paths_are_method_scoped(self):
        self.assertTrue(resolve_dataset_path(None, method="b1").as_posix().endswith("diagnostics/ml/b1/rank_dataset.csv"))
        self.assertTrue(resolve_output_dir(None, method="b1").as_posix().endswith("diagnostics/ml/b1/model"))

    def test_parse_args_accepts_comma_separated_label_gain(self):
        args = parse_args(["--label-gain", "0,1,5,15"])

        self.assertEqual(args.label_gain, [0, 1, 5, 15])

    def test_parse_args_enables_random_forest_diagnostics_by_default(self):
        args = parse_args([])

        self.assertTrue(args.rf_diagnostics)
        self.assertEqual(args.rf_n_estimators, 300)
        self.assertIsNone(args.rf_max_depth)
        self.assertEqual(args.rf_min_samples_leaf, 20)
        self.assertEqual(args.rf_max_features, "sqrt")
        self.assertIsNone(args.rf_min_oob_score)
        self.assertIsNone(args.rf_min_test_rank_ic_ret3)
        self.assertEqual(args.rf_feature_selection, "none")
        self.assertEqual(args.rf_cumulative_importance_threshold, 0.85)
        self.assertEqual(args.rf_min_selected_features, 12)

    def test_parse_args_accepts_random_forest_thresholds_and_skip_flag(self):
        args = parse_args(
            [
                "--skip-rf-diagnostics",
                "--rf-n-estimators",
                "123",
                "--rf-max-depth",
                "7",
                "--rf-min-samples-leaf",
                "11",
                "--rf-max-features",
                "log2",
                "--rf-min-oob-score",
                "0.51",
                "--rf-min-test-rank-ic-ret3",
                "0.02",
                "--rf-feature-selection",
                "cumulative_importance",
                "--rf-cumulative-importance-threshold",
                "0.9",
                "--rf-min-selected-features",
                "8",
            ]
        )

        self.assertFalse(args.rf_diagnostics)
        self.assertEqual(args.rf_n_estimators, 123)
        self.assertEqual(args.rf_max_depth, 7)
        self.assertEqual(args.rf_min_samples_leaf, 11)
        self.assertEqual(args.rf_max_features, "log2")
        self.assertEqual(args.rf_min_oob_score, 0.51)
        self.assertEqual(args.rf_min_test_rank_ic_ret3, 0.02)
        self.assertEqual(args.rf_feature_selection, "cumulative_importance")
        self.assertEqual(args.rf_cumulative_importance_threshold, 0.9)
        self.assertEqual(args.rf_min_selected_features, 8)

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
            "close_to_zxdkx_pct",
            "daily_macd_phase_type",
            "signal_type",
            "price_up_1d_flag",
            "ret3",
            "rank_label_3d",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="all")

        self.assertEqual(numeric, ["close_to_zxdkx_pct", "price_up_1d_flag"])
        self.assertEqual(categorical, ["env", "daily_macd_phase_type", "signal_type"])

    def test_select_feature_columns_supports_legacy_semantic_feature_sets(self):
        columns = [
            "env",
            "signal",
            "signal_type",
            "daily_macd_phase_type",
            "weekly_daily_combo_type",
            "midline_state",
            "price_vs_90d_mid",
            "close_to_zxdkx_pct",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="raw_numeric")
        self.assertEqual(numeric, ["price_vs_90d_mid", "close_to_zxdkx_pct"])
        self.assertEqual(categorical, [])

        _numeric, categorical = select_feature_columns(columns, feature_set="raw_plus_signal")
        self.assertEqual(categorical, ["env", "signal", "signal_type"])

        _numeric, categorical = select_feature_columns(columns, feature_set="raw_plus_signal_macd")
        self.assertEqual(
            categorical,
            [
                "env",
                "signal",
                "signal_type",
                "daily_macd_phase_type",
                "weekly_daily_combo_type",
                "midline_state",
            ],
        )

    def test_select_feature_columns_uses_method_registered_raw_factors(self):
        original = rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"]
        try:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"] = [*original, "b3_only_raw_factor"]
            columns = ["close_to_zxdkx_pct", "b3_only_raw_factor"]

            b2_numeric, _b2_categorical = select_feature_columns(columns, feature_set="raw_numeric", method="b2")
            b3_numeric, _b3_categorical = select_feature_columns(columns, feature_set="raw_numeric", method="b3")

            self.assertEqual(b2_numeric, ["close_to_zxdkx_pct"])
            self.assertEqual(b3_numeric, ["close_to_zxdkx_pct", "b3_only_raw_factor"])
        finally:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"] = original
    def test_select_feature_columns_uses_b3_training_factors(self):
        columns = [
            "env",
            "signal",
            "signal_type",
            "daily_macd_phase_type",
            "daily_macd_wave_stage",
            "weekly_macd_phase_type",
            "weekly_macd_wave_stage",
            "weekly_daily_combo_type",
            "midline_state",
            "macd_phase",
            "daily_macd_wave_index",
            "weekly_macd_wave_index",
            "box_mid_position_120d_pct",
            "trend_structure",
            "price_position",
            "volume_behavior",
            "close_to_zxdkx_pct",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="all", method="b3")

        self.assertEqual(
            numeric,
            [
                "macd_phase",
                "daily_macd_wave_index",
                "weekly_macd_wave_index",
                "box_mid_position_120d_pct",
                "close_to_zxdkx_pct",
            ],
        )
        self.assertEqual(
            categorical,
            [
                "env",
                "signal",
                "signal_type",
                "daily_macd_phase_type",
                "daily_macd_wave_stage",
                "weekly_macd_phase_type",
                "weekly_macd_wave_stage",
                "weekly_daily_combo_type",
                "midline_state",
            ],
        )

    def test_select_feature_columns_uses_lsh_specific_training_schema(self):
        columns = [
            "env",
            "signal",
            "signal_type",
            "daily_macd_phase_type",
            "macd_phase",
            "daily_macd_wave_index",
            "weekly_macd_wave_index",
            "price_vs_90d_high",
            "lsh_daily_macd_wave_index",
            "lsh_weekly_macd_wave_index",
            "lsh_daily_macd_rising_initial_flag",
            "close_to_zxdkx_pct",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="all", method="lsh")

        self.assertEqual(
            numeric,
            [
                "lsh_daily_macd_wave_index",
                "lsh_weekly_macd_wave_index",
                "lsh_daily_macd_rising_initial_flag",
                "close_to_zxdkx_pct",
            ],
        )
        self.assertEqual(categorical, ["env", "signal"])

    def test_validate_selected_feature_coverage_fails_zero_coverage_feature(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "close_to_zxdkx_pct": "1.2", "b3_volume_shrink_ratio": ""},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "close_to_zxdkx_pct": "0.8", "b3_volume_shrink_ratio": ""},
        ]

        with self.assertRaisesRegex(ValueError, "zero coverage.*b3_volume_shrink_ratio"):
            validate_selected_feature_coverage(
                rows,
                numeric_columns=["close_to_zxdkx_pct", "b3_volume_shrink_ratio"],
                categorical_columns=[],
            )

    def test_validate_selected_feature_coverage_reports_non_empty_counts(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "close_to_zxdkx_pct": "1.2", "signal_type": "trend_start"},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "close_to_zxdkx_pct": "", "signal_type": "rebound"},
        ]

        report = validate_selected_feature_coverage(
            rows,
            numeric_columns=["close_to_zxdkx_pct"],
            categorical_columns=["signal_type"],
        )

        self.assertEqual(report["features"]["close_to_zxdkx_pct"]["non_empty_count"], 1)
        self.assertEqual(report["features"]["signal_type"]["non_empty_count"], 2)
        self.assertEqual(report["zero_coverage_features"], [])

    def test_select_features_by_rf_importance_uses_cumulative_threshold_and_minimum(self):
        diagnostics = {
            "top_features": [
                {"feature": "x1", "importance": 0.5},
                {"feature": "env=weak", "importance": 0.2},
                {"feature": "x2", "importance": 0.1},
                {"feature": "env=strong", "importance": 0.1},
                {"feature": "x3", "importance": 0.1},
            ]
        }

        selection = select_features_by_rf_importance(
            diagnostics,
            numeric_columns=["x1", "x2", "x3"],
            categorical_columns=["env"],
            threshold=0.7,
            min_selected_features=1,
        )

        self.assertEqual(selection["numeric_columns"], ["x1"])
        self.assertEqual(selection["categorical_columns"], ["env"])
        self.assertEqual(selection["candidate_feature_count"], 4)
        self.assertEqual(selection["selected_feature_count"], 2)
        self.assertEqual(selection["selected_features"], ["x1", "env"])
        self.assertEqual(selection["dropped_features"], ["x2", "x3"])
        self.assertGreaterEqual(selection["selected_importance_sum"], 0.7)

    def test_select_features_by_rf_importance_keeps_all_when_total_importance_is_zero(self):
        diagnostics = {"top_features": [{"feature": "x1", "importance": 0.0}]}

        selection = select_features_by_rf_importance(
            diagnostics,
            numeric_columns=["x1", "x2"],
            categorical_columns=[],
            threshold=0.85,
            min_selected_features=1,
        )

        self.assertEqual(selection["numeric_columns"], ["x1", "x2"])
        self.assertEqual(selection["dropped_features"], [])
        self.assertEqual(selection["selected_feature_count"], 2)

    def test_select_features_by_rf_importance_prefers_full_importance_list(self):
        diagnostics = {
            "top_features": [
                {"feature": "x1", "importance": 0.5},
                {"feature": "x2", "importance": 0.3},
            ],
            "feature_importances": [
                {"feature": "x1", "importance": 0.5},
                {"feature": "x2", "importance": 0.3},
                {"feature": "x3", "importance": 0.15},
                {"feature": "x4", "importance": 0.05},
            ],
        }

        selection = select_features_by_rf_importance(
            diagnostics,
            numeric_columns=["x1", "x2", "x3", "x4"],
            categorical_columns=[],
            threshold=0.9,
            min_selected_features=1,
        )

        self.assertEqual(selection["selected_features"], ["x1", "x2", "x3"])
        self.assertEqual(selection["dropped_features"], ["x4"])

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

    def test_random_forest_diagnostics_reports_importance_and_metrics(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "3", "env": "weak"},
            {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0", "env": "strong"},
            {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "4", "env": "weak"},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0", "env": "strong"},
        ]
        captured = {}

        class FakeRandomForestClassifier:
            def __init__(self, **kwargs):
                captured["kwargs"] = kwargs
                self.classes_ = [0, 3]
                self.feature_importances_ = [0.8, 0.2, 0.0]
                self.oob_score_ = 0.62

            def fit(self, matrix, labels):
                captured["fit_matrix"] = matrix
                captured["fit_labels"] = labels
                return self

            def predict_proba(self, matrix):
                return [[0.1, 0.9] if row[0] > 0 else [0.9, 0.1] for row in matrix]

            def predict(self, matrix):
                return [3 if row[0] > 0 else 0 for row in matrix]

            def score(self, matrix, labels):
                return 1.0

        fake_sklearn_ensemble = types.SimpleNamespace(RandomForestClassifier=FakeRandomForestClassifier)
        with patch.dict(sys.modules, {"sklearn.ensemble": fake_sklearn_ensemble}):
            diagnostics = run_random_forest_diagnostics(
                rows[:2],
                rows[2:],
                numeric_columns=["x"],
                categorical_columns=["env"],
                label_column="rank_label_3d",
                label_gain=[0, 1, 3, 7],
                num_threads=2,
                fixed_categorical_levels={"env": ["weak", "strong"]},
                config=RandomForestDiagnosticsConfig(n_estimators=17, min_samples_leaf=3),
            )

        self.assertEqual(captured["kwargs"]["n_estimators"], 17)
        self.assertEqual(captured["kwargs"]["min_samples_leaf"], 3)
        self.assertEqual(captured["kwargs"]["n_jobs"], 2)
        self.assertEqual(captured["kwargs"]["random_state"], 17)
        self.assertTrue(captured["kwargs"]["bootstrap"])
        self.assertTrue(captured["kwargs"]["oob_score"])
        self.assertEqual(captured["fit_labels"], [3, 0])
        self.assertEqual(diagnostics["status"], "passed")
        self.assertEqual(diagnostics["feature_count"], 3)
        self.assertEqual(diagnostics["top_features"][0], {"feature": "x", "importance": 0.8})
        self.assertEqual(
            diagnostics["feature_importances"],
            [
                {"feature": "x", "importance": 0.8},
                {"feature": "env=weak", "importance": 0.2},
                {"feature": "env=strong", "importance": 0.0},
            ],
        )
        self.assertEqual(diagnostics["low_importance_features"], [{"feature": "env=strong", "importance": 0.0}])
        self.assertEqual(diagnostics["oob_score"], 0.62)
        self.assertEqual(diagnostics["accuracy"], {"train": 1.0, "test": 1.0})
        self.assertEqual(diagnostics["metrics"]["test"]["top3_ret3_positive_rate"], 50.0)

    def test_random_forest_diagnostics_keeps_full_importance_list_for_selection(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", **{f"x{i}": str(i) for i in range(55)}},
            {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", **{f"x{i}": "0" for i in range(55)}},
            {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", **{f"x{i}": str(i + 1) for i in range(55)}},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", **{f"x{i}": "0" for i in range(55)}},
        ]

        class FakeRandomForestClassifier:
            def __init__(self, **_kwargs):
                self.classes_ = [0, 3]
                self.feature_importances_ = [1.0 / 55.0 for _ in range(55)]
                self.oob_score_ = 0.62

            def fit(self, matrix, labels):
                return self

            def predict_proba(self, matrix):
                return [[0.1, 0.9] if row[1] > 0 else [0.9, 0.1] for row in matrix]

            def predict(self, matrix):
                return [3 if row[1] > 0 else 0 for row in matrix]

            def score(self, matrix, labels):
                return 1.0

        fake_sklearn_ensemble = types.SimpleNamespace(RandomForestClassifier=FakeRandomForestClassifier)
        with patch.dict(sys.modules, {"sklearn.ensemble": fake_sklearn_ensemble}):
            diagnostics = run_random_forest_diagnostics(
                rows[:2],
                rows[2:],
                numeric_columns=[f"x{i}" for i in range(55)],
                categorical_columns=[],
                label_column="rank_label_3d",
                label_gain=[0, 1, 3, 7],
                num_threads=2,
                fixed_categorical_levels={},
                config=RandomForestDiagnosticsConfig(n_estimators=17, min_samples_leaf=3),
            )

        self.assertEqual(len(diagnostics["top_features"]), 50)
        self.assertEqual(len(diagnostics["feature_importances"]), 55)

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

    def test_ret3_ge5_label_is_derived_from_forward_return(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "ret3": "6.2"},
            {"date": "2026-01-01", "code": "b", "ret3": "4.9"},
            {"date": "2026-01-01", "code": "c", "ret3": ""},
        ]

        selected = rows_for_dates(rows, {"2026-01-01"}, label_column="ret3_ge5_label")

        self.assertEqual([row["code"] for row in selected], ["a", "b"])
        self.assertEqual(labels(selected, label_column="ret3_ge5_label"), [3, 0])

    def test_ret5_ge5_label_is_derived_from_forward_return(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "ret5": "5.1"},
            {"date": "2026-01-01", "code": "b", "ret5": "4.9"},
            {"date": "2026-01-01", "code": "c", "ret5": ""},
        ]

        selected = rows_for_dates(rows, {"2026-01-01"}, label_column="ret5_ge5_label")

        self.assertEqual([row["code"] for row in selected], ["a", "b"])
        self.assertEqual(labels(selected, label_column="ret5_ge5_label"), [3, 0])

    def test_train_model_result_accepts_custom_label_gain(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "ret3": "6", "ret5": "6", "x": "1"},
            {"date": "2026-01-01", "code": "b", "ret3": "-1", "ret5": "-1", "x": "0"},
            {"date": "2026-01-02", "code": "a", "ret3": "7", "ret5": "7", "x": "1"},
            {"date": "2026-01-02", "code": "b", "ret3": "0", "ret5": "0", "x": "0"},
        ]
        captured = {}

        class DummyDataset:
            def __init__(self, *_args, **_kwargs):
                pass

        class DummyModel:
            def predict(self, matrix):
                return [float(row[0]) for row in matrix]

            def feature_importance(self):
                return [1]

        def fake_train(params, *_args, **_kwargs):
            captured["label_gain"] = params["label_gain"]
            captured["lambdarank_truncation_level"] = params["lambdarank_truncation_level"]
            return DummyModel()

        fake_lightgbm = types.SimpleNamespace(Dataset=DummyDataset, train=fake_train)
        fake_numpy = types.SimpleNamespace(array=lambda values, dtype=None: values)
        with patch.dict(sys.modules, {"lightgbm": fake_lightgbm, "numpy": fake_numpy}):
            train_model_result(
                rows,
                rows,
                numeric_columns=["x"],
                categorical_columns=[],
                num_leaves=5,
                min_data_in_leaf=1,
                num_boost_round=1,
                learning_rate=0.1,
                label_column="ret3_ge5_label",
                num_threads=1,
                label_gain=[0, 1, 4, 12],
                lambdarank_truncation_level=8,
            )

        self.assertEqual(captured["label_gain"], [0, 1, 4, 12])
        self.assertEqual(captured["lambdarank_truncation_level"], 8)

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
                        "categorical_features": ["env", "signal_type", "model_rank"],
                        "excluded_features": ["ret3", "model_rank"],
                    }
                ),
                encoding="utf-8",
            )

            numeric, categorical = load_feature_manifest(
                path,
                available_columns={"close_to_zxdkx_pct", "env", "signal_type", "ret3", "model_rank"},
            )

        self.assertEqual(numeric, ["close_to_zxdkx_pct"])
        self.assertEqual(categorical, ["env", "signal_type"])

    def test_load_feature_manifest_keeps_legacy_context_numeric_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feature_manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "numeric_features": ["close_to_zxdkx_pct", "price_vs_90d_mid"],
                        "categorical_features": [],
                    }
                ),
                encoding="utf-8",
            )

            numeric, categorical = load_feature_manifest(
                path,
                available_columns={"close_to_zxdkx_pct", "price_vs_90d_mid"},
            )

        self.assertEqual(numeric, ["close_to_zxdkx_pct", "price_vs_90d_mid"])
        self.assertEqual(categorical, [])

    def test_load_feature_manifest_uses_method_registered_raw_factors(self):
        original = rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"]
        try:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"] = [*original, "b3_only_raw_factor"]
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "feature_manifest.json"
                path.write_text(
                    json.dumps(
                        {
                            "numeric_features": ["close_to_zxdkx_pct", "b3_only_raw_factor"],
                            "categorical_features": [],
                        }
                    ),
                    encoding="utf-8",
                )

                b2_numeric, _b2_categorical = load_feature_manifest(
                    path,
                    available_columns={"close_to_zxdkx_pct", "b3_only_raw_factor"},
                    method="b2",
                )
                b3_numeric, _b3_categorical = load_feature_manifest(
                    path,
                    available_columns={"close_to_zxdkx_pct", "b3_only_raw_factor"},
                    method="b3",
                )

            self.assertEqual(b2_numeric, ["close_to_zxdkx_pct"])
            self.assertEqual(b3_numeric, ["close_to_zxdkx_pct", "b3_only_raw_factor"])
        finally:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"] = original

    def test_train_report_uses_fixed_categorical_levels_from_feature_manifest(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **kwargs):
            self.assertEqual(kwargs["fixed_categorical_levels"], {"env": ["weak", "strong", "neutral"]})

            def scored(rows):
                return [
                    {
                        **row,
                        "model_score": float(row.get("rank_label_3d") or 0),
                    }
                    for row in rows
                ]

            from scripts.ml.train_rank_lgbm import TrainedModelResult

            return TrainedModelResult(
                train_scored=scored(train_rows),
                test_scored=scored(test_rows),
                top_features=[{"feature": "env=neutral", "importance": 1}],
                feature_count=4,
                model=DummyModel(),
                feature_names=["close_to_zxdkx_pct", "env=weak", "env=strong", "env=neutral"],
                lightgbm_feature_names=["close_to_zxdkx_pct", "env_weak", "env_strong", "env_neutral"],
                category_levels={"env": ["weak", "strong", "neutral"]},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "close_to_zxdkx_pct", "env"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "close_to_zxdkx_pct": "1", "env": "weak"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "1", "ret3": "-1", "ret5": "0", "close_to_zxdkx_pct": "2", "env": "strong"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "2", "ret3": "3", "ret5": "4", "close_to_zxdkx_pct": "3", "env": "weak"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "close_to_zxdkx_pct": "4", "env": "strong"},
                    ]
                )
            manifest = root / "feature_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "numeric_features": ["close_to_zxdkx_pct"],
                        "categorical_features": ["env"],
                        "categorical_levels": {"env": ["weak", "strong", "neutral"]},
                    }
                ),
                encoding="utf-8",
            )

            with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                report = train_and_report(
                    dataset,
                    root / "model",
                    test_ratio=0.5,
                    feature_manifest=manifest,
                    feature_set="raw_numeric",
                    num_leaves=5,
                    min_data_in_leaf=120,
                    num_boost_round=10,
                    learning_rate=0.05,
                    label_column="rank_label_3d",
                    method="b2",
                    rf_diagnostics=False,
                )

        self.assertEqual(report["feature_count"], 4)

    def test_train_report_writes_and_embeds_random_forest_diagnostics(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **_kwargs):
            from scripts.ml.train_rank_lgbm import TrainedModelResult

            scored = [{**row, "model_score": float(row.get("rank_label_3d") or 0)} for row in test_rows]
            return TrainedModelResult(
                train_scored=[{**row, "model_score": float(row.get("rank_label_3d") or 0)} for row in train_rows],
                test_scored=scored,
                top_features=[{"feature": "x", "importance": 1}],
                feature_count=1,
                model=DummyModel(),
                feature_names=["x"],
                lightgbm_feature_names=["x"],
                category_levels={},
            )

        rf_payload = {
            "enabled": True,
            "status": "passed",
            "label_column": "rank_label_3d",
            "feature_count": 1,
            "numeric_feature_count": 1,
            "categorical_feature_count": 0,
            "params": {"n_estimators": 300},
            "thresholds": {"min_oob_score": None, "min_test_rank_ic_ret3": None},
            "metrics": {"test": {"rank_ic_ret3": 0.12, "top3_ret3_positive_rate": 66.7}, "train": {}},
            "oob_score": 0.61,
            "accuracy": {"train": 0.8, "test": 0.7},
            "top_features": [{"feature": "x", "importance": 0.9}],
            "low_importance_features": [],
            "output_paths": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "1"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0"},
                    ]
                )
            output_dir = root / "model"

            with patch("scripts.ml.train_rank_lgbm.run_random_forest_diagnostics", return_value=rf_payload):
                with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                    report = train_and_report(
                        dataset,
                        output_dir,
                        test_ratio=0.5,
                        feature_set="raw_numeric",
                        num_leaves=5,
                        min_data_in_leaf=1,
                        num_boost_round=1,
                        learning_rate=0.1,
                        label_column="rank_label_3d",
                        method="b2",
                    )

            rf_json = json.loads((output_dir / "rf_feature_diagnostics.json").read_text(encoding="utf-8"))
            rf_markdown = (output_dir / "rf_feature_diagnostics.md").read_text(encoding="utf-8")
            persisted = json.loads((output_dir / "lgbm_rank_report_raw_numeric.json").read_text(encoding="utf-8"))

        self.assertEqual(rf_json["output_paths"]["json"], str(output_dir / "rf_feature_diagnostics.json"))
        self.assertIn("# random forest factor diagnostics", rf_markdown)
        self.assertEqual(report["rf_diagnostics"]["status"], "passed")
        self.assertEqual(report["rf_diagnostics"]["oob_score"], 0.61)
        self.assertEqual(report["rf_diagnostics"]["top_features"], [{"feature": "x", "importance": 0.9}])
        self.assertEqual(persisted["rf_diagnostics"]["path"], str(output_dir / "rf_feature_diagnostics.json"))

    def test_train_report_uses_rf_selected_features_for_lgbm_and_manifest(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **kwargs):
            self.assertEqual(kwargs["numeric_columns"], ["close_to_zxdkx_pct"])
            self.assertEqual(kwargs["categorical_columns"], [])
            from scripts.ml.train_rank_lgbm import TrainedModelResult

            return TrainedModelResult(
                train_scored=[{**row, "model_score": float(row.get("rank_label_3d") or 0)} for row in train_rows],
                test_scored=[{**row, "model_score": float(row.get("rank_label_3d") or 0)} for row in test_rows],
                top_features=[{"feature": "close_to_zxdkx_pct", "importance": 1}],
                feature_count=1,
                model=DummyModel(),
                feature_names=["close_to_zxdkx_pct"],
                lightgbm_feature_names=["close_to_zxdkx_pct"],
                category_levels={},
            )

        rf_payload = {
            "enabled": True,
            "status": "passed",
            "label_column": "rank_label_3d",
            "feature_count": 3,
            "numeric_feature_count": 3,
            "categorical_feature_count": 0,
            "params": {},
            "thresholds": {"min_oob_score": None, "min_test_rank_ic_ret3": None},
            "metrics": {"test": {"rank_ic_ret3": 0.12}, "train": {}},
            "oob_score": 0.61,
            "accuracy": {"train": 0.8, "test": 0.7},
            "top_features": [
                {"feature": "close_to_zxdkx_pct", "importance": 0.8},
                {"feature": "low_to_ma25_pct", "importance": 0.1},
                {"feature": "pct_chg_1d", "importance": 0.1},
            ],
            "low_importance_features": [],
            "output_paths": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "low_to_ma25_pct", "close_to_zxdkx_pct", "pct_chg_1d"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "low_to_ma25_pct": "1", "close_to_zxdkx_pct": "9", "pct_chg_1d": "3"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "low_to_ma25_pct": "2", "close_to_zxdkx_pct": "8", "pct_chg_1d": "4"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "low_to_ma25_pct": "3", "close_to_zxdkx_pct": "7", "pct_chg_1d": "5"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "low_to_ma25_pct": "4", "close_to_zxdkx_pct": "6", "pct_chg_1d": "6"},
                    ]
                )
            output_dir = root / "model"

            with patch("scripts.ml.train_rank_lgbm.run_random_forest_diagnostics", return_value=rf_payload):
                with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                    report = train_and_report(
                        dataset,
                        output_dir,
                        test_ratio=0.5,
                        feature_set="raw_numeric",
                        num_leaves=5,
                        min_data_in_leaf=1,
                        num_boost_round=1,
                        learning_rate=0.1,
                        label_column="rank_label_3d",
                        method="b2",
                        rf_feature_selection="cumulative_importance",
                        rf_cumulative_importance_threshold=0.8,
                        rf_min_selected_features=1,
                    )

            manifest = json.loads((output_dir / "feature_manifest.json").read_text(encoding="utf-8"))
            rf_json = json.loads((output_dir / "rf_feature_diagnostics.json").read_text(encoding="utf-8"))
            metadata = json.loads((output_dir / "model_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["numeric_features"], ["close_to_zxdkx_pct"])
        self.assertEqual(report["numeric_columns"], ["close_to_zxdkx_pct"])
        self.assertEqual(report["rf_diagnostics"]["feature_selection"]["selected_features"], ["close_to_zxdkx_pct"])
        self.assertEqual(rf_json["feature_selection"]["dropped_features"], ["low_to_ma25_pct", "pct_chg_1d"])
        self.assertEqual(metadata["feature_selection"]["selected_features"], ["close_to_zxdkx_pct"])

    def test_train_report_rejects_rf_feature_selection_when_rf_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0"},
                    ]
                )

            with self.assertRaisesRegex(ValueError, "RF feature selection requires RF diagnostics"):
                train_and_report(
                    dataset,
                    root / "model",
                    test_ratio=0.5,
                    feature_set="raw_numeric",
                    num_leaves=5,
                    min_data_in_leaf=1,
                    num_boost_round=1,
                    learning_rate=0.1,
                    label_column="rank_label_3d",
                    rf_diagnostics=False,
                    rf_feature_selection="cumulative_importance",
                    method="b2",
                )

    def test_random_forest_threshold_failure_writes_report_and_stops_lgbm(self):
        rf_payload = {
            "enabled": True,
            "status": "passed",
            "label_column": "rank_label_3d",
            "feature_count": 1,
            "numeric_feature_count": 1,
            "categorical_feature_count": 0,
            "params": {},
            "thresholds": {"min_oob_score": 0.7, "min_test_rank_ic_ret3": None},
            "metrics": {"test": {"rank_ic_ret3": 0.03}, "train": {}},
            "oob_score": 0.61,
            "accuracy": {"train": 0.8, "test": 0.7},
            "top_features": [{"feature": "x", "importance": 0.9}],
            "low_importance_features": [],
            "output_paths": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "1"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0"},
                    ]
                )
            output_dir = root / "model"

            with patch("scripts.ml.train_rank_lgbm.run_random_forest_diagnostics", return_value=rf_payload):
                with patch("scripts.ml.train_rank_lgbm.train_model_result") as train_lgbm:
                    with self.assertRaisesRegex(RandomForestThresholdError, "oob_score"):
                        train_and_report(
                            dataset,
                            output_dir,
                            test_ratio=0.5,
                            feature_set="raw_numeric",
                            num_leaves=5,
                            min_data_in_leaf=1,
                            num_boost_round=1,
                            learning_rate=0.1,
                            label_column="rank_label_3d",
                            rf_min_oob_score=0.7,
                            method="b2",
                        )

                    train_lgbm.assert_not_called()

            self.assertTrue((output_dir / "rf_feature_diagnostics.json").exists())
            self.assertFalse((output_dir / "model.txt").exists())

    def test_train_report_can_skip_random_forest_diagnostics(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **_kwargs):
            from scripts.ml.train_rank_lgbm import TrainedModelResult

            return TrainedModelResult(
                train_scored=[{**row, "model_score": 1.0} for row in train_rows],
                test_scored=[{**row, "model_score": 1.0} for row in test_rows],
                top_features=[{"feature": "x", "importance": 1}],
                feature_count=1,
                model=DummyModel(),
                feature_names=["x"],
                lightgbm_feature_names=["x"],
                category_levels={},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "1"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0"},
                    ]
                )

            with patch("scripts.ml.train_rank_lgbm.run_random_forest_diagnostics") as rf_run:
                with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                    report = train_and_report(
                        dataset,
                        root / "model",
                        test_ratio=0.5,
                        feature_set="raw_numeric",
                        num_leaves=5,
                        min_data_in_leaf=1,
                        num_boost_round=1,
                        learning_rate=0.1,
                        label_column="rank_label_3d",
                        rf_diagnostics=False,
                        method="b2",
                    )

        rf_run.assert_not_called()
        self.assertEqual(
            report["rf_diagnostics"],
            {
                "enabled": False,
                "path": None,
                "status": "skipped",
                "oob_score": None,
                "metrics": {"test": {}},
                "top_features": [],
                "low_importance_feature_count": 0,
            },
        )

    def test_main_passes_random_forest_options_to_train_and_report(self):
        captured = {}

        def fake_train_and_report(dataset, output_dir, **kwargs):
            captured["dataset"] = dataset
            captured["output_dir"] = output_dir
            captured["kwargs"] = kwargs
            return {"metrics": {"test": {}}}

        with patch("scripts.ml.train_rank_lgbm.train_and_report", side_effect=fake_train_and_report):
            from scripts.ml.train_rank_lgbm import main

            exit_code = main(
                [
                    "--method",
                    "b2",
                    "--skip-rf-diagnostics",
                    "--rf-n-estimators",
                    "19",
                    "--rf-max-depth",
                    "5",
                    "--rf-min-oob-score",
                    "0.6",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertFalse(captured["kwargs"]["rf_diagnostics"])
        self.assertEqual(captured["kwargs"]["rf_n_estimators"], 19)
        self.assertEqual(captured["kwargs"]["rf_max_depth"], 5)
        self.assertEqual(captured["kwargs"]["rf_min_oob_score"], 0.6)
        self.assertEqual(captured["kwargs"]["rf_feature_selection"], "none")
        self.assertEqual(captured["kwargs"]["rf_cumulative_importance_threshold"], 0.85)
        self.assertEqual(captured["kwargs"]["rf_min_selected_features"], 12)

    def test_train_report_persists_custom_label_gain(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **kwargs):
            self.assertEqual(kwargs["label_gain"], [0, 1, 5, 15])
            self.assertEqual(kwargs["lambdarank_truncation_level"], 8)

            def scored(rows):
                return [
                    {
                        **row,
                        "model_score": float(row.get("ret3") or 0),
                    }
                    for row in rows
                ]

            from scripts.ml.train_rank_lgbm import TrainedModelResult

            return TrainedModelResult(
                train_scored=scored(train_rows),
                test_scored=scored(test_rows),
                top_features=[{"feature": "close_to_zxdkx_pct", "importance": 1}],
                feature_count=1,
                model=DummyModel(),
                feature_names=["close_to_zxdkx_pct"],
                lightgbm_feature_names=["close_to_zxdkx_pct"],
                category_levels={},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "close_to_zxdkx_pct"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "close_to_zxdkx_pct": "1"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "1", "ret3": "-1", "ret5": "0", "close_to_zxdkx_pct": "2"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "2", "ret3": "7", "ret5": "4", "close_to_zxdkx_pct": "3"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "close_to_zxdkx_pct": "4"},
                    ]
                )
            output_dir = root / "model"

            with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                report = train_and_report(
                    dataset,
                    output_dir,
                    test_ratio=0.5,
                    feature_set="raw_numeric",
                    num_leaves=5,
                    min_data_in_leaf=120,
                    num_boost_round=10,
                    learning_rate=0.05,
                    label_column="ret3_ge5_label",
                    label_gain=[0, 1, 5, 15],
                    lambdarank_truncation_level=8,
                    method="b2",
                    rf_diagnostics=False,
                )

            metadata = json.loads((output_dir / "model_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(report["model_params"]["label_gain"], [0, 1, 5, 15])
        self.assertEqual(report["model_params"]["lambdarank_truncation_level"], 8)
        self.assertEqual(metadata["model_params"]["label_gain"], [0, 1, 5, 15])
        self.assertEqual(metadata["model_params"]["lambdarank_truncation_level"], 8)

    def test_average_metric_dicts_skip_missing_values(self):
        average = average_metric_dicts(
            [
                {"rank_ic_ret3": "0.1", "top3_ret3_ge_5_rate": 20},
                {"rank_ic_ret3": "", "top3_ret3_ge_5_rate": 40},
            ]
        )

        self.assertEqual(average["rank_ic_ret3"], 0.1)
        self.assertEqual(average["top3_ret3_ge_5_rate"], 30.0)

    def test_train_report_does_not_include_baseline_comparisons(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **_kwargs):
            def scored(rows):
                return [
                    {
                        **row,
                        "model_score": float(row.get("rank_label_3d") or 0),
                    }
                    for row in rows
                ]

            from scripts.ml.train_rank_lgbm import TrainedModelResult

            return TrainedModelResult(
                train_scored=scored(train_rows),
                test_scored=scored(test_rows),
                top_features=[{"feature": "close_to_zxdkx_pct", "importance": 1}],
                feature_count=1,
                model=DummyModel(),
                feature_names=["close_to_zxdkx_pct"],
                lightgbm_feature_names=["close_to_zxdkx_pct"],
                category_levels={},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "close_to_zxdkx_pct"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "close_to_zxdkx_pct": "1"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "1", "ret3": "-1", "ret5": "0", "close_to_zxdkx_pct": "2"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "2", "ret3": "3", "ret5": "4", "close_to_zxdkx_pct": "3"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "close_to_zxdkx_pct": "4"},
                        {"date": "2026-01-03", "code": "a", "rank_label_3d": "3", "ret3": "8", "ret5": "9", "close_to_zxdkx_pct": "5"},
                        {"date": "2026-01-03", "code": "b", "rank_label_3d": "1", "ret3": "1", "ret5": "2", "close_to_zxdkx_pct": "6"},
                    ]
                )
            output_dir = root / "model"

            with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                report = train_and_report(
                    dataset,
                    output_dir,
                    test_ratio=0.34,
                    feature_set="raw_numeric",
                    num_leaves=5,
                    min_data_in_leaf=120,
                    num_boost_round=10,
                    learning_rate=0.05,
                    rolling_folds=1,
                    rolling_train_dates=2,
                    rolling_test_dates=1,
                    label_column="rank_label_3d",
                    method="b2",
                    rf_diagnostics=False,
                )

            persisted = json.loads((output_dir / "lgbm_rank_report_raw_numeric.json").read_text(encoding="utf-8"))
            markdown = (output_dir / "lgbm_rank_report_raw_numeric.md").read_text(encoding="utf-8").lower()

        self.assertNotIn("baseline_test_window", report)
        self.assertNotIn("baseline_test_avg", report["rolling_summary"])
        self.assertNotIn("baseline_test_window", report["rolling_folds"][0])
        self.assertNotIn("baseline", markdown)
        self.assertNotIn("baseline_test_window", persisted)
        self.assertNotIn("baseline_test_avg", persisted["rolling_summary"])

    def test_train_and_report_writes_model_artifacts_when_rolling_is_enabled(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **_kwargs):
            def scored(rows):
                return [
                    {
                        **row,
                        "model_score": float(row.get("rank_label_3d") or 0),
                    }
                    for row in rows
                ]

            from scripts.ml.train_rank_lgbm import TrainedModelResult

            return TrainedModelResult(
                train_scored=scored(train_rows),
                test_scored=scored(test_rows),
                top_features=[{"feature": "close_to_zxdkx_pct", "importance": 1}],
                feature_count=1,
                model=DummyModel(),
                feature_names=["close_to_zxdkx_pct"],
                lightgbm_feature_names=["close_to_zxdkx_pct"],
                category_levels={"env": ["weak", "strong"]},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["date", "code", "env", "rank_label_3d", "ret3", "ret5", "close_to_zxdkx_pct"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "env": "weak", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "close_to_zxdkx_pct": "1"},
                        {"date": "2026-01-01", "code": "b", "env": "strong", "rank_label_3d": "1", "ret3": "-1", "ret5": "0", "close_to_zxdkx_pct": "2"},
                        {"date": "2026-01-02", "code": "a", "env": "weak", "rank_label_3d": "2", "ret3": "3", "ret5": "4", "close_to_zxdkx_pct": "3"},
                        {"date": "2026-01-02", "code": "b", "env": "strong", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "close_to_zxdkx_pct": "4"},
                        {"date": "2026-01-03", "code": "a", "env": "weak", "rank_label_3d": "3", "ret3": "8", "ret5": "9", "close_to_zxdkx_pct": "5"},
                        {"date": "2026-01-03", "code": "b", "env": "strong", "rank_label_3d": "1", "ret3": "1", "ret5": "2", "close_to_zxdkx_pct": "6"},
                    ]
                )
            output_dir = root / "model"

            with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                report = train_and_report(
                    dataset,
                    output_dir,
                    test_ratio=0.34,
                    feature_set="raw_numeric",
                    num_leaves=5,
                    min_data_in_leaf=120,
                    num_boost_round=10,
                    learning_rate=0.05,
                    rolling_folds=1,
                    rolling_train_dates=2,
                    rolling_test_dates=1,
                    label_column="rank_label_3d",
                    method="b2",
                    rf_diagnostics=False,
                )

            self.assertEqual(report["feature_count"], 1)
            self.assertTrue((output_dir / "feature_manifest.json").exists())
            self.assertTrue((output_dir / "model.txt").exists())
            metadata = json.loads((output_dir / "model_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["feature_names"], ["close_to_zxdkx_pct"])
            self.assertEqual(metadata["numeric_columns"], ["close_to_zxdkx_pct"])
            self.assertEqual(metadata["categorical_columns"], [])
            self.assertEqual(metadata["label_column"], "rank_label_3d")


if __name__ == "__main__":
    unittest.main()
