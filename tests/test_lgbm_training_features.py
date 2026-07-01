import json
import tempfile
import unittest
from pathlib import Path

from ml.dataset import schema as rank_dataset_schema
from ml.training.features import (
    load_feature_manifest,
    select_feature_columns,
    validate_selected_feature_coverage,
)


class LgbmTrainingFeaturesTest(unittest.TestCase):
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

    def test_select_feature_columns_skips_unstable_zero_coverage_raw_factors(self):
        columns = [
            "date",
            "code",
            "close_to_zxdkx_pct",
            "cyq_winner_rate",
            "cyq_cost_50_to_close_pct",
            "cyq_cost_85_to_close_pct",
            "cyq_weight_avg_to_close_pct",
            "cyq_cost_70_width_pct",
            "cyq_cost_90_width_pct",
            "bar_lower_shadow_pct",
            "bar_amplitude_pct",
            "bar_body_pct",
            "signal_prev_b2_flag",
            "signal_b3_plus_flag",
            "rank_label_3d",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="raw_numeric", method="b2")

        self.assertEqual(numeric, ["close_to_zxdkx_pct"])
        self.assertEqual(categorical, [])

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

    def test_load_feature_manifest_filters_unknown_and_excluded_columns(self):
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


if __name__ == "__main__":
    unittest.main()
