import csv
import json
import contextlib
import io
import sys
import tempfile
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from ml.dataset.rank_dataset import (
    add_day_relative_labels,
    build_dataset_rows,
    compute_forward_labels,
    dataset_columns_for_method,
    extract_selection_row,
    fetch_benchmark_price_rows,
    format_csv_value,
    load_candidate_rows,
    load_external_feature_rows,
    load_factor_artifact_rows,
    fetch_price_rows,
    infer_listing_board,
    is_index_context_factor_column,
    load_selection_rows,
    main_from_args,
    normalize_env,
    normalize_verdict,
    parse_args,
    raw_factor_columns_for_method,
    resolve_output_dir,
    resolve_runtime_root,
    write_dataset,
)
from ml.dataset import schema as rank_dataset_schema
from ml.dataset import rank_dataset

TEST_FACTOR_ARTIFACT_VERSION = 2
TEST_FACTOR_LIBRARY_VERSION = "rust-factor-library-v11"


class RankDatasetTest(unittest.TestCase):
    def test_multiperiod_structure_survives_artifact_dataset_and_training(self):
        from ml.training.features import select_feature_columns
        factors = {
            "czsc_period_complete": False,
            "czsc_weekly_status": "ok",
            "czsc_weekly_close_to_last_bi_mid_pct": 10.0,
            "czsc_monthly_last_bi_direction": "down",
            "czsc_monthly_period_complete": False,
            "kdj_weekly_k": 55.0,
            "kdj_monthly_j": 30.0,
            "sw_l2_main_index_calc_daily_czsc_structure_monthly_status_code": 4.0,
        }
        for method in ("b2", "scm", "pbm"):
            row = {"date": "2026-11-20", "code": "000001.SZ"}
            rank_dataset.merge_factor_artifact_values(row, factors, method=method)
            rows = build_dataset_rows([row], {}, method=method)
            self.assertTrue(set(factors) <= rows[0].keys(), method)
            numeric, categorical = select_feature_columns(list(factors), method=method)
            self.assertEqual(set(numeric + categorical), set(factors), method)
            self.assertEqual(row["czsc_monthly_period_complete"], 0.0)

    def write_factor_artifact(self, factor_dir: Path, payload: dict) -> None:
        artifact = {
            "artifact_version": TEST_FACTOR_ARTIFACT_VERSION,
            "factor_library_version": TEST_FACTOR_LIBRARY_VERSION,
            **payload,
        }
        (factor_dir / "factors.json").write_text(json.dumps(artifact), encoding="utf-8")

    def test_parse_args_requires_training_window_dates(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args([])

    def test_parse_args_defaults_to_candidates_source_for_retraining_when_window_is_explicit(self):
        args = parse_args(["--start-date", "2025-06-04", "--end-date", "2026-06-04"])

        self.assertEqual(args.source, "candidates")
        self.assertEqual(args.method, "b2")
        self.assertFalse(args.intraday)
        self.assertEqual(args.start_date, "2025-06-04")
        self.assertEqual(args.end_date, "2026-06-04")

    def test_parse_args_accepts_intraday_dataset_mode(self):
        args = parse_args(["--start-date", "2026-06-01", "--end-date", "2026-06-04", "--intraday"])

        self.assertTrue(args.intraday)

    def test_output_dir_defaults_to_method_scoped_diagnostics(self):
        self.assertEqual(resolve_output_dir(None, method="scm").as_posix().split("/")[-3:], ["diagnostics", "ml", "scm"])

    def test_runtime_root_resolves_from_shell_env_then_dotenv_without_legacy_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv = Path(temp_dir) / ".env"
            dotenv.write_text("STOCK_SELECT_RUNTIME_ROOT=dotenv-runtime\n", encoding="utf-8")

            self.assertEqual(
                resolve_runtime_root(None, env_runtime_root="shell-runtime", dotenv_path=dotenv),
                Path("shell-runtime"),
            )
            self.assertEqual(resolve_runtime_root(None, env_runtime_root=None, dotenv_path=dotenv), Path("dotenv-runtime"))
            self.assertEqual(
                resolve_runtime_root(Path("cli-runtime"), env_runtime_root="shell-runtime", dotenv_path=dotenv),
                Path("cli-runtime"),
            )


    def test_index_weight_membership_factors_are_registered_for_all_screening_methods(self):
        aliases = [
            "sse50",
            "csi300",
            "csi500",
            "guozheng2000",
            "chinext",
            "sci50",
            "bse50",
            "csi_a50",
            "csi_dividend",
        ]

        for method in ["b2", "scm", "pbm"]:
            with self.subTest(method=method):
                columns = dataset_columns_for_method(method)
                raw_columns = raw_factor_columns_for_method(method)
                for alias in aliases:
                    for suffix in ("member_flag", "weight_pct"):
                        factor = f"market_index_{alias}_{suffix}"
                        self.assertIn(factor, columns)
                        self.assertIn(factor, raw_columns)
                self.assertIn("sw_l2_membership_current_flag", columns)
                self.assertIn("sw_l2_main_pct_change", raw_columns)

    def test_dynamic_index_context_factor_columns_exclude_legacy_ths(self):
        self.assertTrue(is_index_context_factor_column("market_index_sse50_weighted_idx_macd_bfq_to_close_pct"))
        self.assertTrue(is_index_context_factor_column("sw_l2_main_index_calc_daily_rolling_factors_position_90d"))
        self.assertFalse(is_index_context_factor_column("market_index_ths_legacy_ret5_pct"))

    def test_b2_dataset_schema_excludes_review_scores_but_keeps_training_factors(self):
        columns = dataset_columns_for_method("b2")

        for review_score in [
            "trend_structure",
            "price_position",
            "volume_behavior",
            "previous_abnormal_move",
            "weekly_daily_combo_score",
            "total_score",
            "verdict",
        ]:
            self.assertNotIn(review_score, columns)

        for training_column in [
            "listing_board",
            "signal_type",
            "daily_macd_phase_type",
            "daily_macd_wave_stage",
            "weekly_macd_phase_type",
            "weekly_macd_wave_stage",
            "weekly_daily_combo_type",
            "czsc_status",
            "macd_phase",
            "daily_macd_wave_index",
            "weekly_macd_wave_index",
            "box_mid_position_120d_pct",
        ]:
            self.assertIn(training_column, columns)

    def test_listing_board_is_b2_categorical_training_feature(self):
        for method in ["b2"]:
            with self.subTest(method=method):
                self.assertIn("listing_board", dataset_columns_for_method(method))
                self.assertNotIn("listing_board", raw_factor_columns_for_method(method))

        self.assertNotIn("listing_board", dataset_columns_for_method("scm"))

    def test_infer_listing_board_from_a_share_code(self):
        cases = {
            "000001.SZ": "main",
            "002594.SZ": "main",
            "300750.SZ": "chinext",
            "301269.SZ": "chinext",
            "600000.SH": "main",
            "688001.SH": "star",
            "430047.BJ": "bse",
            "920002.BJ": "bse",
            "830799": "bse",
            "": "unknown",
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(infer_listing_board(code), expected)

    def test_ma25_dataset_schema_has_independent_method_entry_with_ma25_specific_factors(self):
        ma25_specific = [
            "ma25_daily_macd_wave_index",
            "ma25_weekly_macd_wave_index",
            "ma25_daily_macd_rising_initial_flag",
            "ma25_weekly_macd_rising_initial_flag",
            "ma25_daily_macd_top_divergence_flag",
            "ma25_weekly_macd_top_divergence_flag",
            "ma25_weekly_daily_constructive_combo_flag",
            "ma25_bullish_engulf_prev_bearish_flag",
            "ma25_volume_bullish_engulf_prev_bearish_flag",
            "ma25_bullish_engulf_volume_ratio",
        ]

        for column in ma25_specific:
            self.assertIn(column, dataset_columns_for_method("scm"))
            self.assertIn(column, raw_factor_columns_for_method("scm"))
            self.assertNotIn(column, dataset_columns_for_method("b2"))
            self.assertNotIn(column, raw_factor_columns_for_method("b2"))

        ma25_excluded_after_ablation = ["cyq_cost_85_to_close_pct"]
        for column in ma25_excluded_after_ablation:
            self.assertNotIn(column, dataset_columns_for_method("scm"))
            self.assertNotIn(column, raw_factor_columns_for_method("scm"))
            self.assertIn(column, dataset_columns_for_method("b2"))

    def test_scm_schema_uses_ma25_state_machine_not_b2_family_semantics(self):
        columns = dataset_columns_for_method("scm")

        for excluded in [
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
            "price_vs_90d_high",
            "price_vs_90d_low",
            "price_vs_90d_mid",
        ]:
            self.assertNotIn(excluded, columns)

        for included in [
            "env",
            "signal",
            "ma25_daily_macd_wave_index",
            "ma25_weekly_macd_wave_index",
            "ma25_daily_macd_rising_initial_flag",
            "ma25_weekly_macd_rising_initial_flag",
            "ma25_daily_macd_top_divergence_flag",
            "ma25_weekly_macd_top_divergence_flag",
            "ma25_weekly_daily_constructive_combo_flag",
        ]:
            self.assertIn(included, columns)

    def test_scm_and_pbm_use_independent_ma25_training_schemas(self):
        ma25_columns = dataset_columns_for_method("scm")
        ma25_raw_columns = raw_factor_columns_for_method("scm")

        for method in ["scm", "pbm"]:
            self.assertEqual(dataset_columns_for_method(method), ma25_columns)
            self.assertEqual(raw_factor_columns_for_method(method), ma25_raw_columns)

    def test_scm_schema_wires_kdj_and_weekly_monthly_macd_factors(self):
        expected = [
            "kdj_k_qfq",
            "kdj_d_qfq",
            "kdj_j_qfq",
            "macd_weekly_dif",
            "macd_weekly_dea",
            "macd_weekly_hist",
            "macd_weekly_dea_pctile",
            "macd_weekly_period_count",
            "macd_monthly_dif",
            "macd_monthly_dea",
            "macd_monthly_hist",
            "macd_monthly_dea_pctile",
            "macd_monthly_period_count",
        ]
        raw_columns = raw_factor_columns_for_method("scm")
        dataset_columns = dataset_columns_for_method("scm")

        for column in expected:
            self.assertIn(column, raw_columns)
            self.assertIn(column, dataset_columns)

    def test_scm_schema_wires_valuation_market_cap_and_rsi_factors(self):
        expected = [
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "dv_ratio",
            "total_mv",
            "circ_mv",
            "total_share",
            "free_share",
            "rsi_qfq_6",
            "rsi_qfq_12",
            "rsi_qfq_24",
        ]
        raw_columns = raw_factor_columns_for_method("scm")
        dataset_columns = dataset_columns_for_method("scm")

        for column in expected:
            self.assertIn(column, raw_columns)
            self.assertIn(column, dataset_columns)

    def test_b2_dataset_schema_includes_db_and_market_state_factors(self):
        expected = [
            "boll_width_pct",
            "dmi_adxr_qfq",
            "dmi_adx_qfq",
            "dmi_pdi_qfq",
            "dmi_mdi_qfq",
            "dmi_pdi_mdi_spread_qfq",
            "dmi_adx_adxr_gap_qfq",
            "wr_qfq",
            "mtm_qfq",
            "roc_qfq",
            "trix_qfq",
            "obv_qfq",
            "vr_qfq",
            "psy_qfq",
            "bias1_qfq",
            "turnover_rate_f",
            "dist_to_up_limit_pct",
            "dist_to_down_limit_pct",
            "stock_mf_net_amount",
            "stock_mf_net_d5_amount",
            "stock_mf_buy_lg_amount",
            "stock_mf_buy_lg_amount_rate",
            "stock_mf_buy_md_amount",
            "stock_mf_buy_md_amount_rate",
            "stock_mf_buy_sm_amount",
            "stock_mf_buy_sm_amount_rate",
            "large_net_amount_to_amount_pct",
            "mid_net_amount_to_amount_pct",
            "small_net_amount_to_amount_pct",
            "net_mf_amount_to_amount_pct",
            "turnover_n",
            "market_up_ratio",
            "market_ge5_ratio",
            "market_le_minus5_ratio",
            "market_median_pct_chg",
            "market_amount_ma5_ratio",
            "market_net_mf_to_amount_pct",
            "market_approx_limit_up_count",
            "market_approx_limit_down_count",
            "cyq_winner_rate",
            "cyq_cost_50_to_close_pct",
            "cyq_cost_85_to_close_pct",
            "cyq_weight_avg_to_close_pct",
            "cyq_cost_70_width_pct",
            "cyq_cost_90_width_pct",
        ]

        for column in expected:
            self.assertIn(column, dataset_columns_for_method("b2"))
            self.assertIn(column, raw_factor_columns_for_method("b2"))

    def test_dataset_schema_includes_market_relative_strength_factors(self):
        expected = [
            "market_index_sse50_member_flag",
            "market_index_sse50_weight_pct",
            "market_index_csi300_member_flag",
            "market_index_csi300_weight_pct",
            "market_index_csi500_member_flag",
            "market_index_csi500_weight_pct",
            "market_index_guozheng2000_member_flag",
            "market_index_guozheng2000_weight_pct",
            "market_index_chinext_member_flag",
            "market_index_chinext_weight_pct",
            "market_index_sci50_member_flag",
            "market_index_sci50_weight_pct",
            "market_index_bse50_member_flag",
            "market_index_bse50_weight_pct",
            "market_index_csi_a50_member_flag",
            "market_index_csi_a50_weight_pct",
            "market_index_csi_dividend_member_flag",
            "market_index_csi_dividend_weight_pct",
        ]

        for method in ("b2", "scm", "pbm"):
            for column in expected:
                self.assertIn(column, dataset_columns_for_method(method))
                self.assertIn(column, raw_factor_columns_for_method(method))

    def test_dynamic_index_factors_flow_from_artifact_into_scm_dataset(self):
        dynamic_factors = {
            "market_index_sse50_idx_macd_bfq_to_close_pct": 12.0,
            "market_index_sse50_weighted_idx_macd_bfq_to_close_pct": 0.06,
            "market_index_sse50_calc_daily_indicators_weekly_kdj_k_asof": 62.0,
            "market_index_sse50_calc_daily_rolling_factors_position_90d": 0.7,
            "market_index_sse50_weighted_calc_daily_rolling_factors_position_90d": 0.0035,
            "sw_l2_main_index_idx_xsii_td4_bfq": 48.0,
            "sw_l2_main_moneyflow_net_mf_amount_per_stock": 3.4,
        }
        artifact_row = extract_selection_row(
            {"code": "600000.SH", "name": "Example"},
            pick_date="2026-05-25",
            method="scm",
            env="neutral",
            factors=dynamic_factors,
        )

        self.assertEqual({key: artifact_row[key] for key in dynamic_factors}, dynamic_factors)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "dataset"
            write_dataset(
                [artifact_row],
                output_dir,
                runtime_root=Path(temp_dir),
                method="scm",
                start_date="2026-05-25",
                end_date="2026-05-25",
                warnings=[],
                source="selection",
            )
            with (output_dir / "rank_dataset.csv").open(encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))

        for factor in dynamic_factors:
            self.assertIn(factor, header)

    def test_previous_factor_library_artifact_is_rejected_after_multiperiod_feature_contract_change(self):
        warning = rank_dataset.validate_factor_artifact_contract(
            {"artifact_version": 2, "factor_library_version": "rust-factor-library-v10"},
            method="scm",
            artifact_key="2026-05-25",
        )

        self.assertEqual(
            warning,
            "stale_factor_artifact:2026-05-25.scm:artifact_version=2:factor_library_version=rust-factor-library-v10",
        )

    def test_dataset_schema_includes_sw_l2_current_membership_sector_factors(self):
        expected = [
            "sw_l2_membership_current_flag",
            "sw_l2_main_pct_change",
            "sw_l2_main_net_amount_per_stock",
            "stock_vs_sw_l2_main_pct_change",
        ]

        for method in ("b2", "scm", "pbm"):
            for column in expected:
                self.assertIn(column, dataset_columns_for_method(method))
                self.assertIn(column, raw_factor_columns_for_method(method))

        dynamic_index_factors = [
            "sw_l2_main_index_idx_macd_bfq_to_close_pct",
            "sw_l2_main_index_calc_daily_indicators_weekly_kdj_k_asof",
            "sw_l2_main_index_calc_daily_rolling_factors_position_90d",
            "sw_l2_main_index_calc_daily_czsc_structure_daily_recent_bi_count",
            "sw_l2_main_moneyflow_net_mf_amount_per_stock",
        ]
        for column in dynamic_index_factors:
            self.assertTrue(is_index_context_factor_column(column))

    def test_dataset_schema_includes_db_native_special_structure_factor_families(self):
        expected = [
            "structure_box_position_120d_pct",
            "structure_box_mid_position_120d_pct",
            "structure_close_to_120d_max_pct",
            "structure_close_to_120d_min_pct",
            "structure_close_to_120d_range_center_pct",
            "structure_range_width_120d_pct",
            "structure_range_compression_20d",
            "structure_range_compression_40d",
            "structure_close_to_ma25_pct",
            "structure_low_to_ma25_pct",
            "structure_near_ma25_support_flag",
            "structure_ma25_slope_5d_pct",
            "structure_ma_aligned_flag",
            "structure_zxdkx",
            "structure_close_to_zxdkx_pct",
            "structure_zxdq_slope_5d_pct",
            "structure_zxdkx_slope_5d_pct",
            "macd_state_phase_score",
            "macd_state_daily_phase_type",
            "macd_state_daily_wave_index",
            "macd_state_daily_wave_stage",
            "macd_state_weekly_phase_type",
            "macd_state_weekly_wave_index",
            "macd_state_weekly_wave_stage",
            "macd_state_weekly_daily_combo_type",
            "macd_state_daily_rising_initial_flag",
            "macd_state_top_divergence_flag",
            "macd_daily_dif_to_close_pct",
            "macd_daily_dea_to_close_pct",
            "macd_daily_hist_to_close_pct",
            "macd_daily_hist_delta_to_close_pct",
            "macd_daily_hist_slope_3d_to_close_pct",
            "macd_daily_hist_positive_flag",
            "macd_weekly_dea_pctile",
            "macd_weekly_hist",
            "macd_monthly_dea_pctile",
            "macd_monthly_hist",
            "volume_event_abnormal_days_ago",
            "volume_event_abnormal_to_ma20_ratio",
            "volume_event_body_pct",
            "volume_event_price_to_current_pct",
            "volume_event_post_drawdown_pct",
            "volume_event_redundant_position_pct",
            "bar_close_position_pct",
            "bar_upper_shadow_pct",
            "signal_bullish_engulf_prev_bearish_flag",
            "signal_bullish_engulf_volume_ratio",
            "signal_yang_engulf_ma25_flag",
        ]

        for method in ("b2", "scm", "pbm"):
            for column in expected:
                self.assertIn(column, dataset_columns_for_method(method))
                self.assertIn(column, raw_factor_columns_for_method(method))

    def test_dataset_schema_replaces_legacy_structure_proxies_with_czsc_factors(self):
        retained_window_factors = [
            "box_position_120d_pct",
            "box_mid_position_120d_pct",
            "close_to_120d_max_pct",
            "close_to_120d_min_pct",
            "close_to_120d_range_center_pct",
            "breakout_distance_120d_pct",
            "range_floor_distance_120d_pct",
            "range_width_120d_pct",
            "close_to_20d_max_close_pct",
            "range_compression_20d",
            "range_compression_40d",
        ]
        czsc_categorical_factors = [
            "czsc_status",
            "czsc_last_bi_direction",
            "czsc_zs_region",
            "czsc_pricing_lifecycle_state",
            "czsc_zs_lifecycle_state",
        ]
        czsc_raw_factors = [
            "czsc_snapshot_available",
            "czsc_source_bar_valid",
            "czsc_available_finished_bi_count",
            "czsc_recent_bi_count",
            "czsc_bi_available",
            "czsc_close_to_last_bi_high_pct",
            "czsc_close_to_last_bi_low_pct",
            "czsc_close_to_last_bi_mid_pct",
            "czsc_last_bi_range_width_pct",
            "czsc_last_bi_move_pct",
            "czsc_last_bi_duration_trade_days",
            "czsc_zs_available",
            "czsc_close_to_zs_zg_pct",
            "czsc_close_to_zs_zd_pct",
            "czsc_close_to_zs_zz_pct",
            "czsc_zs_width_pct",
            "czsc_zs_bi_count",
            "czsc_zs_duration_trade_days",
            "czsc_recent_peak_available",
            "czsc_close_to_recent_peak_pct",
            "czsc_recent_peak_age_trade_days",
            "czsc_pricing_line_available",
            "czsc_pricing_line_missing_after_peak",
            "czsc_close_to_pricing_line_pct",
            "czsc_pricing_line_age_trade_days",
            "czsc_pricing_bear_body_pct",
            "czsc_pricing_bear_amplitude_pct",
            "czsc_close_to_pricing_bear_high_pct",
            "czsc_close_to_pricing_bear_low_pct",
            "czsc_close_to_pricing_bear_close_pct",
            "czsc_pricing_line_active_flag",
            "czsc_pricing_cycle_count",
            "czsc_pricing_failed_cycle_count",
            "czsc_pricing_pullback_count",
            "czsc_pricing_days_since_breakout",
            "czsc_pricing_days_since_first_pullback",
            "czsc_pricing_days_since_latest_pullback",
            "czsc_pricing_latest_pullback_distance_pct",
            "czsc_pricing_latest_pullback_volume_to_breakout",
            "czsc_pricing_latest_pullback_volume_to_prev5",
            "czsc_pricing_latest_pullback_shrink_flag",
            "czsc_pricing_pullback_today_flag",
            "czsc_zs_upper_active_flag",
            "czsc_zs_cycle_count",
            "czsc_zs_failed_cycle_count",
            "czsc_zs_pullback_count",
            "czsc_zs_days_since_breakout",
            "czsc_zs_days_since_first_pullback",
            "czsc_zs_days_since_latest_pullback",
            "czsc_zs_latest_pullback_distance_pct",
            "czsc_zs_latest_pullback_volume_to_breakout",
            "czsc_zs_latest_pullback_volume_to_prev5",
            "czsc_zs_latest_pullback_shrink_flag",
            "czsc_zs_pullback_today_flag",
        ]
        removed_legacy_factors = [
            "midline_state",
            "price_vs_90d_high",
            "price_vs_90d_low",
            "price_vs_90d_mid",
            "structure_hl90_position",
            "structure_hl90_range_pct",
            "left_peak_valid",
            "left_peak_b_div_a",
            "left_peak_days_since_peak",
        ]

        for method in ("b2", "scm", "pbm"):
            columns = dataset_columns_for_method(method)
            raw_columns = raw_factor_columns_for_method(method)
            for column in retained_window_factors:
                self.assertIn(column, columns)
            for column in czsc_categorical_factors:
                self.assertIn(column, columns)
                self.assertNotIn(column, raw_columns)
            for column in czsc_raw_factors:
                self.assertIn(column, columns)
                self.assertIn(column, raw_columns)
            for column in removed_legacy_factors:
                self.assertNotIn(column, columns)
                self.assertNotIn(column, raw_columns)

    def test_dataset_schema_excludes_legacy_sw_l2_training_factors(self):
        legacy_columns = [
            "sw_l2_ret5_pct",
            "sw_l2_ret20_pct",
            "sw_l2_ma20_bias_pct",
            "sw_l2_volatility20_pct",
            "sw_l2_ret5_rank_pct",
            "sw_l2_ret20_rank_pct",
            "sw_l2_vs_market_ret5_pct",
            "sw_l2_vs_market_ret20_pct",
            "stock_vs_sw_l2_ret5_pct",
            "stock_vs_sw_l2_ret20_pct",
            "sw_l2_up_ratio",
            "sw_l2_ge5_ratio",
            "sw_l2_limit_up_ratio",
            "sw_l2_limit_down_ratio",
            "sw_l2_amount_share_pct",
            "sw_l2_amount_share_rank_pct",
            "sw_l2_amount_share_ma5_ratio",
            "sw_l2_top1_amount_share_pct",
            "sw_l2_top3_amount_share_pct",
            "sw_l2_top5_amount_share_pct",
            "sw_l2_net_mf_to_amount_pct",
            "sw_l2_net_mf_market_share_pct",
            "sw_l2_net_mf_rank_pct",
            "stock_amount_to_sw_l2_amount_pct",
            "stock_net_mf_to_sw_l2_amount_pct",
        ]

        for method in ("b2", "scm", "pbm"):
            columns = dataset_columns_for_method(method)
            raw_columns = raw_factor_columns_for_method(method)
            for column in legacy_columns:
                self.assertNotIn(column, columns)
                self.assertNotIn(column, raw_columns)

    def test_dataset_schema_keeps_sw_l2_factors_and_excludes_legacy_ths_factors(self):
        for method in ("b2", "scm", "pbm"):
            columns = dataset_columns_for_method(method)
            raw_columns = raw_factor_columns_for_method(method)
            self.assertIn("sw_l2_membership_current_flag", columns)
            self.assertIn("sw_l2_main_pct_change", raw_columns)
            for column in columns:
                self.assertNotIn("ths", column.casefold(), f"{method} still registers {column}")
                self.assertFalse(column.startswith("stock_env_"), f"{method} still registers {column}")
            for column in raw_columns:
                self.assertNotIn("ths", column.casefold(), f"{method} raw schema still registers {column}")
                self.assertFalse(column.startswith("stock_env_"), f"{method} raw schema still registers {column}")

    def test_b2_dataset_schema_includes_rdagent_rank_factors_without_polluting_other_methods(self):
        b2_specific = [
            "D",
            "close_to_lt_r_pct",
            "lt_r_to_ma60_pct",
            "bar_close_position",
            "upper_shadow_pct",
            "weekly_dea_pctile",
            "weekly_macd_hist",
            "monthly_dea_pctile",
            "monthly_macd_hist",
            "b2_bullish_engulf_prev_bearish_flag",
            "b2_volume_bullish_engulf_prev_bearish_flag",
            "b2_bullish_engulf_volume_ratio",
        ]

        for column in b2_specific:
            self.assertIn(column, dataset_columns_for_method("b2"))
            self.assertIn(column, raw_factor_columns_for_method("b2"))
            self.assertNotIn(column, dataset_columns_for_method("pbm"))
            self.assertNotIn(column, raw_factor_columns_for_method("pbm"))
            self.assertNotIn(column, dataset_columns_for_method("scm"))
            self.assertNotIn(column, raw_factor_columns_for_method("scm"))

    def test_dataset_schema_excludes_removed_chip_age_factors_for_model_methods(self):
        removed = [
            "total_mass",
            "chip_age_layer_sum",
            "chip_age_ultrashort_ratio",
            "chip_age_short_ratio",
            "chip_age_mid_ratio",
            "chip_age_long_ratio",
            "profit_ratio",
            "avg_cost_close_ratio",
            "peak_price_close_ratio",
            "chip_entropy",
            "chip_concentration",
            "chip_age_l0_b00",
            "chip_age_l3_b31",
        ]

        for method in ("b2", "scm", "pbm"):
            for column in removed:
                self.assertNotIn(column, dataset_columns_for_method(method))
                self.assertNotIn(column, raw_factor_columns_for_method(method))

    def test_load_external_feature_rows_accepts_symbol_or_code_and_filters_to_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "external_features.csv"
            path.write_text(
                "\n".join(
                    [
                        "date,symbol,market_index_sse50_weighted_idx_macd_bfq_to_close_pct,market_sse_ret5_pct,structure_zxdkx,unknown_feature,ret5,env",
                        "2026-05-25,000001.SZ,0.61,0.42,10.72,999,88,strong",
                        "2026-05-25,000002.SZ,,0.22,9.55,999,77,weak",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            rows, warnings = load_external_feature_rows(path, method="b2")

        self.assertEqual(warnings, [])
        self.assertEqual(rows[("2026-05-25", "000001.SZ")]["market_index_sse50_weighted_idx_macd_bfq_to_close_pct"], 0.61)
        self.assertNotIn("market_sse_ret5_pct", rows[("2026-05-25", "000001.SZ")])
        self.assertEqual(rows[("2026-05-25", "000001.SZ")]["structure_zxdkx"], 10.72)
        self.assertNotIn("unknown_feature", rows[("2026-05-25", "000001.SZ")])
        self.assertNotIn("ret5", rows[("2026-05-25", "000001.SZ")])
        self.assertNotIn("env", rows[("2026-05-25", "000001.SZ")])
        self.assertNotIn("market_index_sse50_weighted_idx_macd_bfq_to_close_pct", rows[("2026-05-25", "000002.SZ")])

    def test_build_dataset_rows_merges_external_schema_features_by_date_and_code(self):
        selection_rows = [
            {
                "date": "2026-05-25",
                "code": "000001.SZ",
                "env": "neutral",
                "method": "b2",
            }
        ]
        prices = {
            "000001.SZ": [
                {"trade_date": "2026-05-25", "open": 10, "close": 10, "high": 10.2, "low": 9.8},
                {"trade_date": "2026-05-26", "open": 11, "close": 11, "high": 11.2, "low": 10.9},
                {"trade_date": "2026-05-27", "open": 12, "close": 12, "high": 12.2, "low": 11.8},
                {"trade_date": "2026-05-28", "open": 13, "close": 13, "high": 13.2, "low": 12.7},
                {"trade_date": "2026-05-29", "open": 14, "close": 14, "high": 14.2, "low": 13.6},
                {"trade_date": "2026-06-01", "open": 15, "close": 15, "high": 15.2, "low": 14.4},
                {"trade_date": "2026-06-02", "open": 16, "close": 16, "high": 16.2, "low": 15.4},
            ],
        }
        external_features = {
            ("2026-05-25", "000001.SZ"): {
                "market_index_sse50_weighted_idx_macd_bfq_to_close_pct": 0.61,
                "market_sse_ret5_pct": 0.42,
                "structure_zxdkx": 10.72,
                "env": "strong",
                "ret5": 88.0,
            }
        }

        prices = {code: [{**row, "price_basis": "qfq"} for row in history] for code, history in prices.items()}
        rows = build_dataset_rows(selection_rows, prices, external_features_by_key=external_features)

        self.assertEqual(rows[0]["env"], "neutral")
        self.assertEqual(rows[0]["ret5"], 45.4545)
        self.assertEqual(rows[0]["market_index_sse50_weighted_idx_macd_bfq_to_close_pct"], 0.61)
        self.assertNotIn("market_sse_ret5_pct", rows[0])
        self.assertEqual(rows[0]["structure_zxdkx"], 10.72)

    def test_load_candidate_rows_reads_current_candidates_artifacts_without_select(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "candidates"
            factor_dir = root / "factors" / "2026-05-25.b2"
            candidate_dir.mkdir(parents=True)
            factor_dir.mkdir(parents=True)
            (candidate_dir / "2026-05-25.b2.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "pick_date": "2026-05-25",
                        "candidates": [
                            {
                                "code": "000001.SZ",
                                "name": "平安银行",
                                "signal": "B2",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.write_factor_artifact(
                factor_dir,
                {
                    "method": "b2",
                    "artifact_key": "2026-05-25",
                    "rows": [
                        {
                            "code": "000001.SZ",
                            "factors": {
                                "env": "neutral",
                                "signal_type": "trend_start",
                                "close_to_zxdkx_pct": 1.25,
                            },
                        }
                    ],
                },
            )

            rows, warnings = load_candidate_rows(
                root,
                method="b2",
                start_date="2026-05-25",
                end_date="2026-05-25",
            )

        self.assertEqual(warnings, [])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["date"], "2026-05-25")
        self.assertEqual(row["code"], "000001.SZ")
        self.assertEqual(row["name"], "平安银行")
        self.assertEqual(row["method"], "b2")
        self.assertEqual(row["env"], "neutral")
        self.assertEqual(row["signal"], "B2")
        self.assertEqual(row["close_to_zxdkx_pct"], 1.25)
        self.assertEqual(row["signal_type"], "trend_start")

    def test_load_candidate_rows_allows_empty_candidate_artifact_with_empty_factors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "candidates"
            factor_dir = root / "factors" / "2026-05-25.b2"
            candidate_dir.mkdir(parents=True)
            factor_dir.mkdir(parents=True)
            (candidate_dir / "2026-05-25.b2.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "pick_date": "2026-05-25",
                        "candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            self.write_factor_artifact(
                factor_dir,
                {
                    "method": "b2",
                    "artifact_key": "2026-05-25",
                    "rows": [],
                },
            )

            rows, warnings = load_candidate_rows(
                root,
                method="b2",
                start_date="2026-05-25",
                end_date="2026-05-25",
            )

        self.assertEqual(rows, [])
        self.assertEqual(warnings, [])

    def test_load_candidate_rows_can_read_intraday_rt_k_factor_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "candidates"
            eod_factor_dir = root / "factors" / "2026-05-25.b2"
            intraday_factor_dir = root / "factors" / "2026-05-25.intraday.b2"
            candidate_dir.mkdir(parents=True)
            eod_factor_dir.mkdir(parents=True)
            intraday_factor_dir.mkdir(parents=True)
            (candidate_dir / "2026-05-25.b2.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "pick_date": "2026-05-25",
                        "candidates": [{"code": "000002.SZ", "name": "EOD"}],
                    }
                ),
                encoding="utf-8",
            )
            (candidate_dir / "2026-05-25.intraday.b2.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "pick_date": "2026-05-25",
                        "environment": {"state": "strong"},
                        "candidates": [{"code": "000001.SZ", "name": "平安银行", "signal": "B2"}],
                    }
                ),
                encoding="utf-8",
            )
            self.write_factor_artifact(
                eod_factor_dir,
                {
                    "method": "b2",
                    "artifact_key": "2026-05-25",
                    "rows": [{"code": "000002.SZ", "factors": {"close_to_zxdkx_pct": 99.0}}],
                },
            )
            self.write_factor_artifact(
                intraday_factor_dir,
                {
                    "method": "b2",
                    "artifact_key": "2026-05-25.intraday",
                    "rows": [
                        {
                            "code": "000001.SZ",
                            "factors": {
                                "signal_type": "trend_start",
                                "close_to_zxdkx_pct": 1.25,
                                "intraday_price_live_qfq": 10.6,
                                "macd_daily_period_count": 101,
                            },
                        }
                    ],
                },
            )

            rows, warnings = load_candidate_rows(
                root,
                method="b2",
                start_date="2026-05-25",
                end_date="2026-05-25",
                intraday=True,
            )

        self.assertEqual(warnings, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["code"], "000001.SZ")
        self.assertEqual(rows[0]["env"], "strong")
        self.assertEqual(rows[0]["signal_type"], "trend_start")
        self.assertEqual(rows[0]["close_to_zxdkx_pct"], 1.25)


    def test_load_candidate_rows_merges_runtime_factor_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "candidates"
            factor_dir = root / "factors" / "2026-05-25.b2"
            candidate_dir.mkdir(parents=True)
            factor_dir.mkdir(parents=True)
            (candidate_dir / "2026-05-25.b2.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "pick_date": "2026-05-25",
                        "candidates": [{"code": "000001.SZ", "name": "平安银行", "signal": "B2"}],
                    }
                ),
                encoding="utf-8",
            )
            self.write_factor_artifact(
                factor_dir,
                {
                    "method": "b2",
                    "artifact_key": "2026-05-25",
                    "rows": [
                        {
                            "code": "000001.SZ",
                            "factors": {
                                "env": "strong",
                                "close_to_zxdkx_pct": 1.5,
                                "macd_hist_to_close_pct": 0.25,
                                "macd_hist_positive_flag": 1,
                            },
                        }
                    ],
                },
            )

            rows, warnings = load_candidate_rows(root, method="b2", start_date="2026-05-25", end_date="2026-05-25")

        self.assertEqual(warnings, [])
        self.assertEqual(rows[0]["env"], "strong")
        self.assertEqual(rows[0]["close_to_zxdkx_pct"], 1.5)
        self.assertEqual(rows[0]["macd_hist_to_close_pct"], 0.25)
        self.assertEqual(rows[0]["macd_hist_positive_flag"], 1)

    def test_load_factor_artifact_rows_reports_missing_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            rows, warnings = load_factor_artifact_rows(Path(temp_dir), method="b2", artifact_key="2026-05-25")

        self.assertEqual(rows, {})
        self.assertEqual(warnings, ["missing_factor_artifact:2026-05-25.b2"])

    def test_load_factor_artifact_rows_rejects_stale_artifact_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            factor_dir = root / "factors" / "2026-05-25.b2"
            factor_dir.mkdir(parents=True)
            (factor_dir / "factors.json").write_text(
                json.dumps(
                    {
                        "artifact_version": 2,
                        "factor_library_version": "rust-factor-library-v3",
                        "method": "b2",
                        "artifact_key": "2026-05-25",
                        "rows": [
                            {
                                "code": "000001.SZ",
                                "factors": {
                                    "close_to_zxdkx_pct": 1.25,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            rows, warnings = load_factor_artifact_rows(root, method="b2", artifact_key="2026-05-25")

        self.assertEqual(rows, {})
        self.assertEqual(
            warnings,
            [
                "stale_factor_artifact:2026-05-25.b2:"
                "artifact_version=2:factor_library_version=rust-factor-library-v3"
            ],
        )

    def test_dataset_build_fails_on_stale_factor_artifact_without_writing_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            output_dir = root / "out"
            candidate_dir = runtime / "candidates"
            factor_dir = runtime / "factors" / "2026-05-25.b2"
            candidate_dir.mkdir(parents=True)
            factor_dir.mkdir(parents=True)
            (candidate_dir / "2026-05-25.b2.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "pick_date": "2026-05-25",
                        "environment": {"state": "neutral"},
                        "candidates": [{"code": "000001.SZ", "name": "平安银行"}],
                    }
                ),
                encoding="utf-8",
            )
            (factor_dir / "factors.json").write_text(
                json.dumps(
                    {
                        "artifact_version": 1,
                        "factor_library_version": "rust-factor-library-v2",
                        "method": "b2",
                        "artifact_key": "2026-05-25",
                        "rows": [{"code": "000001.SZ", "factors": {"close_to_zxdkx_pct": 1.2}}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                main_from_args(
                    type(
                        "Args",
                        (),
                        {
                            "runtime_root": runtime,
                            "duckdb_path": "fixture.duckdb",
                            "method": "b2",
                            "start_date": "2026-05-25",
                            "end_date": "2026-05-25",
                            "output_dir": output_dir,
                            "source": "candidates",
                            "min_history_days": 120,
                            "forward_days": 15,
                            "external_feature_csv": [],
                        },
                    )()
                )

        message = str(raised.exception)
        self.assertIn("stale_factor_artifact", message)
        self.assertIn("2026-05-25.b2", message)
        self.assertIn("stock-select-rs screen --method b2 --pick-date 2026-05-25 --export-factors", message)
        self.assertFalse((output_dir / "rank_dataset.csv").exists())

    def test_dataset_build_records_manifest_gaps_without_czsc_coverage_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            output_dir = root / "out"
            candidate_dir = runtime / "candidates"
            factor_dir = runtime / "factors" / "2026-05-25.b2"
            candidate_dir.mkdir(parents=True)
            factor_dir.mkdir(parents=True)
            codes = [f"{index:06d}.SZ" for index in range(1000)]
            (candidate_dir / "2026-05-25.b2.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "pick_date": "2026-05-25",
                        "environment": {"state": "neutral"},
                        "candidates": [{"code": code} for code in codes],
                    }
                ),
                encoding="utf-8",
            )
            self.write_factor_artifact(
                factor_dir,
                {
                    "method": "b2",
                    "artifact_key": "2026-05-25",
                    "rows": [
                        {
                            "code": code,
                            "factors": {"czsc_snapshot_available": index < 949},
                        }
                        for index, code in enumerate(codes)
                    ],
                },
            )
            (factor_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "artifact_key": "2026-05-25",
                        "method": "b2",
                        "db_data_gaps": {
                            "calc_daily_industry_moneyflow": {
                                "reason": "missing_rows",
                                "expected_rows": 1,
                                "actual_rows": 0,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("ml.dataset.rank_dataset.fetch_price_rows", return_value={}):
                with patch("ml.dataset.rank_dataset.fetch_benchmark_price_rows", return_value=[]):
                    main_from_args(
                        type(
                            "Args",
                            (),
                            {
                                "runtime_root": runtime,
                                "duckdb_path": "must-not-be-used.duckdb",
                                "method": "b2",
                                "start_date": "2026-05-25",
                                "end_date": "2026-05-25",
                                "output_dir": output_dir,
                                "source": "candidates",
                                "intraday": False,
                                "min_history_days": 120,
                                "forward_days": 15,
                                "external_feature_csv": [],
                            },
                        )()
                    )

            summary = json.loads(
                (output_dir / "rank_dataset_summary.json").read_text(encoding="utf-8")
            )
            self.assertTrue((output_dir / "rank_dataset.csv").exists())
            self.assertFalse(
                any("czsc_training_coverage" in warning for warning in summary["warnings"])
            )
            self.assertEqual(
                summary["db_data_gaps"]["calc_daily_industry_moneyflow"],
                {
                    "artifact_count": 1,
                    "artifacts": {
                        "2026-05-25.b2": {
                            "reason": "missing_rows",
                            "expected_rows": 1,
                            "actual_rows": 0,
                        }
                    },
                },
            )

    def test_intraday_missing_factor_hint_keeps_intraday_screen_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir) / "runtime"
            output_dir = Path(temp_dir) / "out"
            candidate_dir = runtime / "candidates"
            candidate_dir.mkdir(parents=True)
            (candidate_dir / "2026-05-25.intraday.b2.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "pick_date": "2026-05-25",
                        "candidates": [{"code": "000001.SZ", "name": "平安银行"}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                main_from_args(
                    type(
                        "Args",
                        (),
                        {
                            "runtime_root": runtime,
                            "duckdb_path": "fixture.duckdb",
                            "method": "b2",
                            "start_date": "2026-05-25",
                            "end_date": "2026-05-25",
                            "output_dir": output_dir,
                            "source": "candidates",
                            "intraday": True,
                            "min_history_days": 120,
                            "forward_days": 15,
                            "external_feature_csv": [],
                        },
                    )()
                )

        message = str(raised.exception)
        self.assertIn("missing_factor_artifact", message)
        self.assertIn("2026-05-25.intraday.b2", message)
        self.assertIn("stock-select-rs screen --method b2 --intraday --pick-date 2026-05-25 --export-factors", message)
        self.assertFalse((output_dir / "rank_dataset.csv").exists())

    def test_load_selection_rows_reads_current_select_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            select_dir = root / "select" / "2026-05-25.b2"
            factor_dir = root / "factors" / "2026-05-25.b2"
            select_dir.mkdir(parents=True)
            factor_dir.mkdir(parents=True)
            (select_dir / "run.json").write_text(
                json.dumps(
                    {
                        "method": "b2",
                        "artifact_key": "2026-05-25",
                        "environment": {"state": "Neutral"},
                    }
                ),
                encoding="utf-8",
            )
            (select_dir / "display.json").write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "code": "000001.SZ",
                                "name": "平安银行",
                                "model_rank": 1,
                                "model_score": 0.72,
                                "llm_action": "watch",
                                "llm_risk_flags": ["volume"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.write_factor_artifact(
                factor_dir,
                {
                    "method": "b2",
                    "artifact_key": "2026-05-25",
                    "rows": [
                        {
                            "code": "000001.SZ",
                            "factors": {
                                "signal": "B2",
                                "signal_type": "trend_start",
                                "close_to_zxdkx_pct": 1.25,
                                "near_ma25_support_flag": True,
                            },
                        }
                    ],
                },
            )

            rows, warnings = load_selection_rows(
                root,
                method="b2",
                start_date="2026-05-25",
                end_date="2026-05-25",
            )

        self.assertEqual(warnings, [])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["date"], "2026-05-25")
        self.assertEqual(row["code"], "000001.SZ")
        self.assertEqual(row["name"], "平安银行")
        self.assertEqual(row["env"], "neutral")
        self.assertEqual(row["method"], "b2")
        self.assertEqual(row["model_rank"], 1)
        self.assertEqual(row["model_score"], 0.72)
        self.assertEqual(row["llm_action"], "watch")
        self.assertEqual(row["risk_flags"], "volume")
        self.assertEqual(row["signal"], "B2")
        self.assertEqual(row["close_to_zxdkx_pct"], 1.25)
        self.assertEqual(row["signal_type"], "trend_start")
        self.assertEqual(row["near_ma25_support_flag"], 1)

    def test_forward_labels_use_future_trade_bars(self):
        rows = [
            {"trade_date": "2026-05-25", "open": 9.5, "close": 10.0, "low": 9.8},
            {"trade_date": "2026-05-26", "open": 100.0, "close": 105.0, "low": 90.0},
            {"trade_date": "2026-05-27", "open": 110.0, "close": 95.0, "low": 95.0},
            {"trade_date": "2026-05-28", "open": 90.0, "close": 110.0, "low": 85.0},
            {"trade_date": "2026-05-29", "open": 120.0, "close": 120.0, "low": 115.0},
            {"trade_date": "2026-06-01", "open": 80.0, "close": 80.0, "low": 75.0},
            {"trade_date": "2026-06-02", "open": 130.0, "close": 130.0, "low": 125.0},
            {"trade_date": "2026-06-03", "open": 140.0, "close": 140.0, "low": 135.0},
            {"trade_date": "2026-06-04", "open": 150.0, "close": 150.0, "low": 145.0},
            {"trade_date": "2026-06-05", "open": 160.0, "close": 160.0, "low": 155.0},
            {"trade_date": "2026-06-08", "open": 160.0, "close": 160.0, "low": 155.0},
            {"trade_date": "2026-06-09", "open": 170.0, "close": 170.0, "low": 165.0},
        ]

        rows = [{**row, "price_basis": "qfq"} for row in rows]
        labels = compute_forward_labels(rows, "2026-05-25")

        self.assertEqual(labels["ret3"], 20.0)
        self.assertEqual(labels["ret5"], 30.0)
        self.assertEqual(labels["ret10"], 70.0)
        self.assertEqual(labels["max_drawdown_5d"], -25.0)
        self.assertEqual(labels["ret_t1_open_to_t3_close"], 10.0)


    def test_forward_labels_do_not_adjust_qfq_prices_twice(self):
        raw_rows = [
            {"trade_date": "2026-06-01", "open": 10.0, "close": 10.0, "low": 9.8, "adj_factor": 1.0},
            {"trade_date": "2026-06-02", "open": 5.5, "close": 5.5, "low": 5.0, "adj_factor": 2.0},
            {"trade_date": "2026-06-03", "open": 5.75, "close": 5.75, "low": 5.4, "adj_factor": 2.0},
            {"trade_date": "2026-06-04", "open": 6.0, "close": 6.0, "low": 5.8, "adj_factor": 2.0},
            {"trade_date": "2026-06-05", "open": 6.25, "close": 6.25, "low": 6.0, "adj_factor": 2.0},
            {"trade_date": "2026-06-08", "open": 6.5, "close": 6.5, "low": 6.1, "adj_factor": 2.0},
            {"trade_date": "2026-06-09", "open": 6.5, "close": 6.5, "low": 6.1, "adj_factor": 2.0},
        ]
        qfq_rows = [
            {
                **row,
                "close": row["close"] * row["adj_factor"] / 2.0,
                "low": row["low"] * row["adj_factor"] / 2.0,
                "price_basis": "qfq",
            }
            for row in raw_rows
        ]

        labels = compute_forward_labels(qfq_rows, "2026-06-01")

        self.assertEqual(labels["ret3"], 13.6364)
        self.assertEqual(labels["ret5"], 18.1818)
        self.assertEqual(labels["max_drawdown_5d"], -9.0909)
        self.assertEqual(qfq_rows[0]["adj_factor"], 1.0)
        self.assertEqual(qfq_rows[1]["adj_factor"], 2.0)

    def test_forward_labels_reject_mixed_price_bases(self):
        rows = [
            {"trade_date": "2026-06-01", "close": 5.0, "price_basis": "qfq"},
            {"trade_date": "2026-06-02", "close": 11.0},
        ]

        with self.assertRaisesRegex(ValueError, "price basis"):
            compute_forward_labels(rows, "2026-06-01")

    def test_forward_labels_reject_unknown_price_basis(self):
        rows = [{"trade_date": "2026-06-01", "close": 5.0, "price_basis": "unknown"}]

        with self.assertRaisesRegex(ValueError, "price basis"):
            compute_forward_labels(rows, "2026-06-01")

    def test_fetch_price_rows_uses_stock_cache_factor_table_for_labels(self):
        sample = {"ts_code": "000001.SZ", "trade_date": "2026-06-01", "open": 10.0,
                  "close": 10.5, "high": 10.8, "low": 9.8, "vol": 1000.0,
                  "turnover_rate": 2.5, "pct_chg": 5.0, "adj_factor": 1.2}
        with patch("ml.dataset.rank_dataset.query_rows", return_value=[sample]) as query:
            rows = fetch_price_rows("cache.duckdb", ["000001.SZ"], "2026-06-01", "2026-06-05")
        sql = query.call_args.args[1].lower()
        self.assertIn("stock_stk_factor_pro", sql)
        self.assertIn("close_qfq", sql)
        self.assertEqual(rows["000001.SZ"][0]["adj_factor"], 1.2)
        self.assertEqual(rows["000001.SZ"][0]["price_basis"], "qfq")

    def test_fetch_benchmark_price_rows_uses_hushen_300_index_bars(self):
        sample = {"ts_code": "000300.SH", "trade_date": "2026-06-01", "open": 4000.0, "close": 4020.0}
        with patch("ml.dataset.rank_dataset.query_rows", return_value=[sample]) as query:
            rows = fetch_benchmark_price_rows("cache.duckdb", "2026-06-01", "2026-06-05")

        sql = query.call_args.args[1].lower()
        self.assertIn("index_idx_factor_pro", sql)
        self.assertEqual(rows[0]["open"], 4000.0)
        self.assertEqual(rows[0]["close"], 4020.0)
        self.assertEqual(rows[0]["trade_date"], "2026-06-01")

    def test_build_dataset_rows_merges_labels_and_runtime_factors(self):
        selection_rows = [
            {
                "date": "2026-05-25",
                "code": "000001.SZ",
                "env": "neutral",
                "method": "b2",
                "close_to_zxdkx_pct": 1.25,
            },
            {
                "date": "2026-05-25",
                "code": "000002.SZ",
                "env": "weak",
                "method": "b2",
                "close_to_zxdkx_pct": -0.5,
            },
        ]
        prices = {
            "000001.SZ": [
                {"trade_date": "2026-05-25", "open": 10, "close": 10, "high": 10.2, "low": 9.8},
                {"trade_date": "2026-05-26", "open": 11, "close": 11, "high": 11.2, "low": 10.9},
                {"trade_date": "2026-05-27", "open": 12, "close": 12, "high": 12.2, "low": 11.8},
                {"trade_date": "2026-05-28", "open": 13, "close": 13, "high": 13.2, "low": 12.7},
                {"trade_date": "2026-05-29", "open": 14, "close": 14, "high": 14.2, "low": 13.6},
                {"trade_date": "2026-06-01", "open": 15, "close": 15, "high": 15.2, "low": 14.4},
            ],
            "000002.SZ": [
                {"trade_date": "2026-05-25", "open": 20, "close": 20, "high": 20.2, "low": 19.5},
                {"trade_date": "2026-05-26", "open": 19, "close": 19, "high": 19.2, "low": 18.8},
                {"trade_date": "2026-05-27", "open": 18, "close": 18, "high": 18.2, "low": 17.8},
                {"trade_date": "2026-05-28", "open": 17, "close": 17, "high": 17.2, "low": 16.5},
                {"trade_date": "2026-05-29", "open": 16, "close": 16, "high": 16.2, "low": 15.6},
                {"trade_date": "2026-06-01", "open": 15, "close": 15, "high": 15.2, "low": 14.7},
            ],
        }

        prices = {code: [{**row, "price_basis": "qfq"} for row in history] for code, history in prices.items()}
        rows = build_dataset_rows(selection_rows, prices)

        by_code = {row["code"]: row for row in rows}
        self.assertEqual(by_code["000001.SZ"]["ret3"], 27.2727)
        self.assertEqual(by_code["000001.SZ"]["ret_t1_open_to_t3_close"], 18.1818)
        self.assertEqual(by_code["000002.SZ"]["ret3"], -15.7895)
        self.assertEqual(by_code["000001.SZ"]["win3_vs_day_median"], 1)
        self.assertEqual(by_code["000002.SZ"]["rank_label_3d"], 0)
        self.assertEqual(by_code["000001.SZ"]["close_to_zxdkx_pct"], 1.25)
        self.assertEqual(by_code["000001.SZ"]["listing_board"], "main")

    def test_build_dataset_rows_adds_benchmark_and_excess_return_labels(self):
        selection_rows = [{"date": "2026-05-25", "code": "000001.SZ", "env": "neutral", "method": "b2"}]
        stock_prices = {"000001.SZ": [
            {"trade_date": "2026-05-25", "open": 10, "close": 10},
            {"trade_date": "2026-05-26", "open": 10, "close": 10},
            {"trade_date": "2026-05-27", "open": 10, "close": 11},
            {"trade_date": "2026-05-28", "open": 10, "close": 12},
        ]}
        benchmark_prices = [
            {"trade_date": "2026-05-26", "open": 4000, "close": 4010},
            {"trade_date": "2026-05-27", "open": 4010, "close": 4020},
            {"trade_date": "2026-05-28", "open": 4020, "close": 4040},
        ]
        stock_prices = {code: [{**row, "price_basis": "qfq"} for row in history] for code, history in stock_prices.items()}

        row = build_dataset_rows(selection_rows, stock_prices, benchmark_price_rows=benchmark_prices)[0]

        self.assertEqual(row["ret_t1_open_to_t3_close"], 20.0)
        self.assertEqual(row["benchmark_csi300_ret_t1_open_to_t3_close"], 1.0)
        self.assertEqual(row["excess_ret_t1_open_to_t3_close"], 19.0)
        self.assertIn("ret_t1_open_to_t3_close", rank_dataset.LABEL_COLUMNS)
        self.assertIn("benchmark_csi300_ret_t1_open_to_t3_close", rank_dataset.LABEL_COLUMNS)
        self.assertIn("excess_ret_t1_open_to_t3_close", rank_dataset.LABEL_COLUMNS)

    def test_build_dataset_rows_preserves_artifact_listing_board(self):
        selection_rows = [
            {
                "date": "2026-05-25",
                "code": "300750.SZ",
                "env": "neutral",
                "method": "b2",
                "listing_board": "manual_board",
            }
        ]
        prices = {
            "300750.SZ": [
                {"trade_date": "2026-05-25", "close": 10, "high": 10.2, "low": 9.8},
                {"trade_date": "2026-05-26", "close": 11, "high": 11.2, "low": 10.9},
                {"trade_date": "2026-05-27", "close": 12, "high": 12.2, "low": 11.8},
                {"trade_date": "2026-05-28", "close": 13, "high": 13.2, "low": 12.7},
            ]
        }

        prices = {code: [{**row, "price_basis": "qfq"} for row in history] for code, history in prices.items()}
        rows = build_dataset_rows(selection_rows, prices)

        self.assertEqual(rows[0]["listing_board"], "manual_board")

    def test_build_dataset_rows_preserves_semantic_classifier_fields(self):
        selection_rows = [
            {
                "date": "2026-05-25",
                "code": "000001.SZ",
                "env": "neutral",
                "method": "b2",
                "signal_type": "manual_signal",
                "daily_macd_phase_type": "manual_daily",
                "weekly_daily_combo_type": "manual_combo",
                "czsc_zs_region": "inside_upper_half",
                "czsc_close_to_zs_zz_pct": -1.5,
            }
        ]
        prices = {
            "000001.SZ": [
                {
                    "trade_date": (date(2026, 1, 1) + timedelta(days=offset)).isoformat(),
                    "close": 100.0 + offset,
                    "high": 101.0 + offset,
                    "low": 99.0 + offset,
                }
                for offset in range(150)
            ]
        }

        prices = {code: [{**row, "price_basis": "qfq"} for row in history] for code, history in prices.items()}
        rows = build_dataset_rows(selection_rows, prices)

        self.assertEqual(rows[0]["signal_type"], "manual_signal")
        self.assertEqual(rows[0]["daily_macd_phase_type"], "manual_daily")
        self.assertEqual(rows[0]["weekly_daily_combo_type"], "manual_combo")
        self.assertEqual(rows[0]["czsc_zs_region"], "inside_upper_half")
        self.assertEqual(rows[0]["czsc_close_to_zs_zz_pct"], -1.5)

    def test_normalizers_and_csv_values_are_stable(self):
        self.assertEqual(normalize_env("Strong"), "strong")
        self.assertEqual(normalize_env("sideways"), "unknown")
        self.assertEqual(normalize_verdict("pass"), "PASS")
        self.assertEqual(normalize_verdict(""), "UNKNOWN")
        self.assertEqual(format_csv_value(None), "")
        self.assertEqual(format_csv_value(float("nan")), "")
        self.assertEqual(format_csv_value(1.234567), "1.2346")

    def test_day_relative_labels_ignore_missing_returns(self):
        rows = [
            {"date": "2026-05-25", "code": "000001.SZ", "ret3": 10.0, "ret5": 3.0},
            {"date": "2026-05-25", "code": "000002.SZ", "ret3": 0.0, "ret5": None},
            {"date": "2026-05-25", "code": "000003.SZ", "ret3": -5.0, "ret5": -1.0},
            {"date": "2026-05-25", "code": "000004.SZ", "ret3": None, "ret5": 8.0},
        ]

        labeled = add_day_relative_labels(rows)
        by_code = {row["code"]: row for row in labeled}

        self.assertEqual(by_code["000001.SZ"]["win3_vs_day_median"], 1)
        self.assertEqual(by_code["000002.SZ"]["win3_vs_day_median"], 0)
        self.assertEqual(by_code["000003.SZ"]["win3_vs_day_median"], 0)
        self.assertEqual(by_code["000004.SZ"]["win3_vs_day_median"], "")
        self.assertEqual(by_code["000001.SZ"]["rank_label_3d"], 3)
        self.assertEqual(by_code["000002.SZ"]["rank_label_3d"], 1)
        self.assertEqual(by_code["000003.SZ"]["rank_label_3d"], 0)


if __name__ == "__main__":
    unittest.main()
