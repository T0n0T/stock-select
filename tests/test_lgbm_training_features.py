import json
import tempfile
import unittest
from pathlib import Path

from ml.dataset import schema as rank_dataset_schema
from ml.training.features import (
    LABEL_COLUMNS,
    drop_optional_zero_coverage_features,
    load_feature_manifest,
    select_feature_columns,
    validate_selected_feature_coverage,
)


class LgbmTrainingFeaturesTest(unittest.TestCase):
    def test_long_czsc_structures_keep_calendar_durations_when_trade_window_is_too_short(self):
        rows = [{
            "czsc_monthly_snapshot_available": "1",
            "czsc_monthly_zs_duration_calendar_days": "1450",
            "czsc_monthly_zs_duration_trade_days": "",
        }]
        columns = list(rows[0])
        numeric, categorical, dropped = drop_optional_zero_coverage_features(
            rows, numeric_columns=columns, categorical_columns=[],
        )
        self.assertEqual(dropped, ["czsc_monthly_zs_duration_trade_days"])
        self.assertEqual(numeric, columns[:-1])
        self.assertEqual(categorical, [])
        validate_selected_feature_coverage(rows, numeric_columns=numeric, categorical_columns=categorical)

    def test_daily_macd_quality_and_long_rolling_lines_are_trainable(self):
        columns = ["macd_daily_dea_pctile", "macd_daily_period_count", "close_to_rolling_ma144_pct", "close_to_rolling_ma220_pct"]
        for method in ("b2", "scm", "pbm"):
            self.assertEqual(select_feature_columns(columns, method=method), (columns, []))

    def test_stock_weekly_monthly_czsc_reaches_training_with_correct_types(self):
        numeric_columns = [
            f"czsc_{period}_{field}"
            for period in ("weekly", "monthly")
            for field in (
                "snapshot_available", "period_complete", "last_bi_move_pct",
                "close_to_zs_zg_pct", "last_bi_duration_trade_days",
            )
        ]
        categorical_columns = [
            f"czsc_{period}_{field}"
            for period in ("weekly", "monthly")
            for field in ("status", "last_bi_direction", "zs_region")
        ]
        for method in ("b2", "scm", "pbm"):
            with self.subTest(method=method):
                numeric, categorical = select_feature_columns(
                    numeric_columns + categorical_columns, method=method,
                )
                self.assertEqual(numeric, numeric_columns)
                self.assertEqual(categorical, categorical_columns)

    def test_dynamic_index_context_factors_are_numeric_for_scm(self):
        columns = [
            "market_index_sse50_member_flag",
            "market_index_sse50_weight_pct",
            "market_index_sse50_weighted_idx_macd_bfq_to_close_pct",
            "market_index_csi_a50_calc_daily_czsc_structure_daily_recent_bi_count",
            "sw_l2_main_index_calc_daily_rolling_factors_position_90d",
            "sw_l2_main_moneyflow_net_mf_amount_per_stock",
            "market_index_ths_legacy_weighted_idx_macd_bfq",
            "market_unrelated_debug_value",
        ]

        numeric, categorical = select_feature_columns(columns, feature_set="raw_numeric", method="scm")

        self.assertEqual(numeric, columns[:-2])
        self.assertEqual(categorical, [])

    def test_chips_shape_factors_are_available_to_all_methods(self):
        columns = [
            "cyq_chips_near_close_5pct",
            "cyq_chips_overhead_10pct",
            "cyq_chips_support_10pct",
            "cyq_chips_peak_to_close_pct",
            "cyq_chips_std_to_close_pct",
        ]
        for method in ("b2", "scm", "pbm"):
            with self.subTest(method=method):
                numeric, categorical = select_feature_columns(columns, feature_set="raw_numeric", method=method)
                self.assertEqual(numeric, columns)
                self.assertEqual(categorical, [])
                kept, _, dropped = drop_optional_zero_coverage_features(
                    [dict.fromkeys(columns, "")], numeric_columns=columns, categorical_columns=[]
                )
                self.assertEqual(kept, [])
                self.assertEqual(dropped, columns)

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

    def test_future_selection_outcome_labels_are_explicitly_excluded(self):
        self.assertTrue({
            "ret_t1_open_to_t3_close",
            "benchmark_csi300_ret_t1_open_to_t3_close",
            "excess_ret_t1_open_to_t3_close",
        }.issubset(LABEL_COLUMNS))

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

    def test_select_feature_columns_includes_cyq_raw_factors(self):
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

        self.assertEqual(
            numeric,
            [
                "close_to_zxdkx_pct",
                "cyq_winner_rate",
                "cyq_cost_50_to_close_pct",
                "cyq_cost_85_to_close_pct",
                "cyq_weight_avg_to_close_pct",
                "cyq_cost_70_width_pct",
                "cyq_cost_90_width_pct",
            ],
        )
        self.assertEqual(categorical, [])

    def test_drop_optional_zero_coverage_features_drops_empty_cyq(self):
        cyq_columns = [
            "cyq_winner_rate",
            "cyq_cost_50_to_close_pct",
            "cyq_cost_85_to_close_pct",
            "cyq_weight_avg_to_close_pct",
            "cyq_cost_70_width_pct",
            "cyq_cost_90_width_pct",
        ]
        rows = [dict.fromkeys(cyq_columns, "") for _ in range(2)]

        numeric, categorical, dropped = drop_optional_zero_coverage_features(
            rows,
            numeric_columns=cyq_columns,
            categorical_columns=[],
        )

        self.assertEqual(numeric, [])
        self.assertEqual(categorical, [])
        self.assertEqual(dropped, cyq_columns)

    def test_drop_optional_zero_coverage_features_keeps_covered_cyq(self):
        rows = [
            {"cyq_winner_rate": "", "cyq_cost_50_to_close_pct": ""},
            {"cyq_winner_rate": "54.2", "cyq_cost_50_to_close_pct": "-1.1"},
        ]

        numeric, categorical, dropped = drop_optional_zero_coverage_features(
            rows,
            numeric_columns=["cyq_winner_rate", "cyq_cost_50_to_close_pct"],
            categorical_columns=[],
        )

        self.assertEqual(numeric, ["cyq_winner_rate", "cyq_cost_50_to_close_pct"])
        self.assertEqual(categorical, [])
        self.assertEqual(dropped, [])

    def test_drop_optional_zero_coverage_features_drops_unavailable_legacy_sw_l2_fields(self):
        legacy_sw_l2_columns = [
            "sw_l2_main_vol",
            "sw_l2_main_turnover_rate",
            "sw_l2_main_total_mv",
            "sw_l2_main_float_mv",
            "sw_l2_main_lead_stock_pct_change",
        ]
        rows = [dict.fromkeys(legacy_sw_l2_columns, "") for _ in range(2)]

        numeric, categorical, dropped = drop_optional_zero_coverage_features(
            rows,
            numeric_columns=legacy_sw_l2_columns,
            categorical_columns=[],
        )

        self.assertEqual(numeric, [])
        self.assertEqual(categorical, [])
        self.assertEqual(dropped, legacy_sw_l2_columns)

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
