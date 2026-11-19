import json
import tempfile
import unittest
from pathlib import Path

from ml.dataset import schema as rank_dataset_schema
from ml.training.features import (
    drop_optional_zero_coverage_features,
    load_feature_manifest,
    select_feature_columns,
    validate_selected_feature_coverage,
)


class LgbmTrainingFeaturesTest(unittest.TestCase):
    def test_scm_weekly_macd_state_text_fields_are_categorical_and_wave_index_numeric(self):
        columns = [
            "macd_state_weekly_phase_type",
            "macd_state_weekly_wave_index",
            "macd_state_weekly_wave_stage",
            "macd_state_weekly_daily_combo_type",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="all", method="scm")

        self.assertEqual(numeric, ["macd_state_weekly_wave_index"])
        self.assertEqual(
            categorical,
            [
                "macd_state_weekly_phase_type",
                "macd_state_weekly_wave_stage",
                "macd_state_weekly_daily_combo_type",
            ],
        )

    def test_scm_daily_macd_state_text_fields_are_categorical_and_wave_index_numeric(self):
        columns = [
            "macd_state_daily_phase_type",
            "macd_state_daily_wave_index",
            "macd_state_daily_wave_stage",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="all", method="scm")

        self.assertEqual(numeric, ["macd_state_daily_wave_index"])
        self.assertEqual(categorical, ["macd_state_daily_phase_type", "macd_state_daily_wave_stage"])

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

    def test_select_feature_columns_supports_czsc_structure_feature_sets(self):
        columns = [
            "env",
            "signal",
            "signal_type",
            "daily_macd_phase_type",
            "weekly_daily_combo_type",
            "czsc_status",
            "czsc_zs_lifecycle_state",
            "czsc_close_to_zs_zz_pct",
            "close_to_zxdkx_pct",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="raw_numeric")
        self.assertEqual(numeric, ["czsc_close_to_zs_zz_pct", "close_to_zxdkx_pct"])
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
                "czsc_status",
                "czsc_zs_lifecycle_state",
            ],
        )

    def test_select_feature_columns_uses_method_registered_raw_factors(self):
        original = rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["scm"]
        try:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["scm"] = [*original, "scm_only_raw_factor"]
            columns = ["close_to_zxdkx_pct", "scm_only_raw_factor"]

            b2_numeric, _b2_categorical = select_feature_columns(columns, feature_set="raw_numeric", method="b2")
            scm_numeric, _scm_categorical = select_feature_columns(columns, feature_set="raw_numeric", method="scm")

            self.assertEqual(b2_numeric, ["close_to_zxdkx_pct"])
            self.assertEqual(scm_numeric, ["close_to_zxdkx_pct", "scm_only_raw_factor"])
        finally:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["scm"] = original

    def test_select_feature_columns_keeps_intraday_czsc_for_intraday_training(self):
        columns = [
            "close_to_zxdkx_pct",
            "intraday_czsc_close_to_last_bi_high_pct",
            "intraday_czsc_close_to_zs_zz_pct",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="raw_numeric", method="b2")

        self.assertEqual(numeric, columns)
        self.assertEqual(categorical, [])

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

    def test_drop_optional_zero_coverage_features_only_drops_empty_intraday_czsc(self):
        intraday_columns = [
            "intraday_czsc_close_to_last_bi_high_pct",
            "intraday_czsc_close_to_last_bi_low_pct",
            "intraday_czsc_close_to_last_bi_mid_pct",
            "intraday_czsc_close_to_zs_zg_pct",
            "intraday_czsc_close_to_zs_zd_pct",
            "intraday_czsc_close_to_zs_zz_pct",
            "intraday_czsc_close_to_recent_peak_pct",
            "intraday_czsc_close_to_pricing_line_pct",
            "intraday_czsc_close_to_pricing_bear_high_pct",
            "intraday_czsc_close_to_pricing_bear_low_pct",
            "intraday_czsc_close_to_pricing_bear_close_pct",
        ]
        rows = [
            {"close_to_zxdkx_pct": "1.2", **dict.fromkeys(intraday_columns, "")},
            {"close_to_zxdkx_pct": "0.8", **dict.fromkeys(intraday_columns, "")},
        ]

        numeric, categorical, dropped = drop_optional_zero_coverage_features(
            rows,
            numeric_columns=["close_to_zxdkx_pct", *intraday_columns],
            categorical_columns=[],
        )

        self.assertEqual(numeric, ["close_to_zxdkx_pct"])
        self.assertEqual(categorical, [])
        self.assertEqual(dropped, intraday_columns)

    def test_drop_optional_zero_coverage_features_keeps_populated_intraday_czsc(self):
        rows = [
            {"close_to_zxdkx_pct": "1.2", "intraday_czsc_close_to_last_bi_high_pct": ""},
            {"close_to_zxdkx_pct": "0.8", "intraday_czsc_close_to_last_bi_high_pct": "3.5"},
        ]

        numeric, categorical, dropped = drop_optional_zero_coverage_features(
            rows,
            numeric_columns=["close_to_zxdkx_pct", "intraday_czsc_close_to_last_bi_high_pct"],
            categorical_columns=[],
        )

        self.assertEqual(
            numeric,
            ["close_to_zxdkx_pct", "intraday_czsc_close_to_last_bi_high_pct"],
        )
        self.assertEqual(categorical, [])
        self.assertEqual(dropped, [])

    def test_drop_optional_zero_coverage_features_drops_empty_profile_specific_aliases(self):
        optional_columns = [
            "macd_state_phase_score",
            "macd_state_daily_phase_type",
            "macd_state_daily_wave_index",
            "macd_state_daily_wave_stage",
            "macd_state_weekly_phase_type",
            "macd_state_weekly_wave_index",
            "macd_state_weekly_wave_stage",
            "macd_state_weekly_daily_combo_type",
            "bar_upper_shadow_pct",
            "signal_bullish_engulf_prev_bearish_flag",
            "signal_bullish_engulf_volume_ratio",
            "signal_yang_engulf_ma25_flag",
        ]
        rows = [
            {"close_to_zxdkx_pct": "1.2", **dict.fromkeys(optional_columns, "")},
            {"close_to_zxdkx_pct": "0.8", **dict.fromkeys(optional_columns, "")},
        ]

        numeric, categorical, dropped = drop_optional_zero_coverage_features(
            rows,
            numeric_columns=["close_to_zxdkx_pct", *optional_columns],
            categorical_columns=[],
        )

        self.assertEqual(numeric, ["close_to_zxdkx_pct"])
        self.assertEqual(categorical, [])
        self.assertEqual(dropped, optional_columns)

    def test_validate_selected_feature_coverage_fails_zero_coverage_feature(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "close_to_zxdkx_pct": "1.2", "test_no_coverage_factor": ""},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "close_to_zxdkx_pct": "0.8", "test_no_coverage_factor": ""},
        ]

        with self.assertRaisesRegex(ValueError, "zero coverage.*test_no_coverage_factor"):
            validate_selected_feature_coverage(
                rows,
                numeric_columns=["close_to_zxdkx_pct", "test_no_coverage_factor"],
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
