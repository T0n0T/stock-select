import json
import contextlib
import io
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts.ml.build_rank_dataset import (
    add_day_relative_labels,
    build_dataset_rows,
    compute_forward_labels,
    dataset_columns_for_method,
    format_csv_value,
    load_candidate_rows,
    load_external_feature_rows,
    load_factor_artifact_rows,
    load_selection_rows,
    normalize_env,
    normalize_verdict,
    parse_args,
    raw_factor_columns_for_method,
    resolve_output_dir,
    resolve_runtime_root,
)
from scripts.ml import build_rank_dataset as rank_dataset_schema

TEST_FACTOR_ARTIFACT_VERSION = 2
TEST_FACTOR_LIBRARY_VERSION = "rust-factor-library-v3"


class RankDatasetTest(unittest.TestCase):
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
        self.assertEqual(args.start_date, "2025-06-04")
        self.assertEqual(args.end_date, "2026-06-04")

    def test_output_dir_defaults_to_method_scoped_diagnostics(self):
        self.assertEqual(resolve_output_dir(None, method="b1").as_posix().split("/")[-3:], ["diagnostics", "ml", "b1"])

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

    def test_b3_dataset_schema_has_independent_method_entry_with_b3_specific_factors(self):
        b3_specific = [
            "b3_volume_shrink_ratio",
            "b3_amplitude_pct",
            "b3_body_pct",
            "b3_upper_shadow_pct",
            "b3_lower_shadow_pct",
            "b3_j_delta",
            "b3_prev_b2_flag",
            "b3_plus_flag",
        ]

        for column in b3_specific:
            self.assertIn(column, dataset_columns_for_method("b3"))
            self.assertIn(column, raw_factor_columns_for_method("b3"))
            self.assertNotIn(column, dataset_columns_for_method("b2"))
            self.assertNotIn(column, raw_factor_columns_for_method("b2"))

        original = rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"]
        try:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"] = [*original, "b3_only_raw_factor"]

            self.assertIn("b3_only_raw_factor", dataset_columns_for_method("b3"))
            self.assertNotIn("b3_only_raw_factor", dataset_columns_for_method("b2"))
        finally:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"] = original

    def test_b3_dataset_schema_excludes_review_scores_but_keeps_training_factors(self):
        columns = dataset_columns_for_method("b3")

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
        ]:
            self.assertIn(training_column, columns)

    def test_b3_factor_artifact_merge_ignores_review_scores_and_keeps_training_features(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "candidates"
            factor_dir = root / "factors" / "2026-05-25.b3"
            candidate_dir.mkdir(parents=True)
            factor_dir.mkdir(parents=True)
            (candidate_dir / "2026-05-25.b3.json").write_text(
                json.dumps(
                    {
                        "method": "b3",
                        "pick_date": "2026-05-25",
                        "candidates": [{"code": "000001.SZ", "name": "平安银行", "signal": "B3+"}],
                    }
                ),
                encoding="utf-8",
            )
            self.write_factor_artifact(
                factor_dir,
                {
                    "method": "b3",
                    "artifact_key": "2026-05-25",
                    "rows": [
                        {
                            "code": "000001.SZ",
                            "factors": {
                                "env": "neutral",
                                "signal_type": "trend_start",
                                "daily_macd_phase_type": "rising",
                                "daily_macd_wave_index": 2,
                                "daily_macd_wave_stage": "early",
                                "weekly_macd_phase_type": "rising",
                                "weekly_macd_wave_index": 1,
                                "weekly_macd_wave_stage": "early",
                                "weekly_daily_combo_type": "rising:1|rising:2",
                                "midline_state": "above_hold",
                                "macd_phase": 4.5,
                                "box_mid_position_120d_pct": 74.0,
                                "b3_volume_shrink_ratio": 0.5,
                                "close_to_zxdkx_pct": 1.25,
                                "trend_structure": 4.0,
                                "price_position": 3.0,
                                "volume_behavior": 5.0,
                            },
                        }
                    ],
                    }
            )

            rows, warnings = load_candidate_rows(
                root,
                method="b3",
                start_date="2026-05-25",
                end_date="2026-05-25",
            )

        self.assertEqual(warnings, [])
        self.assertEqual(rows[0]["signal_type"], "trend_start")
        self.assertEqual(rows[0]["daily_macd_phase_type"], "rising")
        self.assertEqual(rows[0]["daily_macd_wave_index"], 2)
        self.assertEqual(rows[0]["weekly_macd_phase_type"], "rising")
        self.assertEqual(rows[0]["weekly_macd_wave_index"], 1)
        self.assertEqual(rows[0]["weekly_daily_combo_type"], "rising:1|rising:2")
        self.assertEqual(rows[0]["midline_state"], "above_hold")
        self.assertEqual(rows[0]["macd_phase"], 4.5)
        self.assertEqual(rows[0]["box_mid_position_120d_pct"], 74.0)
        self.assertEqual(rows[0]["b3_volume_shrink_ratio"], 0.5)
        self.assertEqual(rows[0]["close_to_zxdkx_pct"], 1.25)
        self.assertNotIn("trend_structure", rows[0])
        self.assertNotIn("price_position", rows[0])
        self.assertNotIn("volume_behavior", rows[0])
    def test_lsh_dataset_schema_has_independent_method_entry_with_lsh_specific_factors(self):
        lsh_specific = [
            "lsh_daily_macd_wave_index",
            "lsh_weekly_macd_wave_index",
            "lsh_daily_macd_rising_initial_flag",
            "lsh_weekly_macd_rising_initial_flag",
            "lsh_daily_macd_top_divergence_flag",
            "lsh_weekly_macd_top_divergence_flag",
            "lsh_weekly_daily_constructive_combo_flag",
            "lsh_bullish_engulf_prev_bearish_flag",
            "lsh_volume_bullish_engulf_prev_bearish_flag",
            "lsh_bullish_engulf_volume_ratio",
        ]

        for column in lsh_specific:
            self.assertIn(column, dataset_columns_for_method("lsh"))
            self.assertIn(column, raw_factor_columns_for_method("lsh"))
            self.assertNotIn(column, dataset_columns_for_method("b2"))
            self.assertNotIn(column, raw_factor_columns_for_method("b2"))

        lsh_excluded_after_ablation = ["vr_qfq", "cyq_cost_85_to_close_pct"]
        for column in lsh_excluded_after_ablation:
            self.assertNotIn(column, dataset_columns_for_method("lsh"))
            self.assertNotIn(column, raw_factor_columns_for_method("lsh"))
            self.assertIn(column, dataset_columns_for_method("b2"))

    def test_lsh_schema_uses_lsh_state_machine_not_b2_family_semantics(self):
        columns = dataset_columns_for_method("lsh")

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
            "lsh_daily_macd_wave_index",
            "lsh_weekly_macd_wave_index",
            "lsh_daily_macd_rising_initial_flag",
            "lsh_weekly_macd_rising_initial_flag",
            "lsh_daily_macd_top_divergence_flag",
            "lsh_weekly_macd_top_divergence_flag",
            "lsh_weekly_daily_constructive_combo_flag",
        ]:
            self.assertIn(included, columns)

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
            "large_net_amount_to_amount_pct",
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

    def test_dataset_schema_includes_market_and_sw_l2_relative_strength_factors(self):
        expected = [
            "market_sse_ret5_pct",
            "market_sse_ret20_pct",
            "market_sse_ma20_bias_pct",
            "market_sse_volatility20_pct",
            "market_cn2000_ret5_pct",
            "market_cn2000_ret20_pct",
            "market_cn2000_ma20_bias_pct",
            "market_cn2000_volatility20_pct",
            "market_broad_ret5_pct",
            "market_broad_ret20_pct",
            "market_broad_ma20_bias_pct",
            "market_broad_volatility20_pct",
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
        ]

        for method in ("b2", "b3", "lsh"):
            for column in expected:
                self.assertIn(column, dataset_columns_for_method(method))
                self.assertIn(column, raw_factor_columns_for_method(method))

    def test_dataset_schema_includes_sw_l2_crowding_and_capital_concentration_factors(self):
        expected = [
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

        for method in ("b2", "b3", "lsh"):
            for column in expected:
                self.assertIn(column, dataset_columns_for_method(method))
                self.assertIn(column, raw_factor_columns_for_method(method))

    def test_b2_dataset_schema_includes_rdagent_rank_factors_without_polluting_other_methods(self):
        b2_specific = [
            "D",
            "close_to_lt_r_pct",
            "lt_r_to_ma60_pct",
            "hl90_position",
            "hl90_range_pct",
            "close_to_hl90_mid_pct",
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
            self.assertNotIn(column, dataset_columns_for_method("b3"))
            self.assertNotIn(column, raw_factor_columns_for_method("b3"))
            self.assertNotIn(column, dataset_columns_for_method("lsh"))
            self.assertNotIn(column, raw_factor_columns_for_method("lsh"))

    def test_dataset_schema_includes_shared_chip_age_cache_factors_for_model_methods(self):
        expected = [
            "total_mass",
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

        for column in expected:
            for method in ("b2", "b3", "lsh"):
                self.assertIn(column, dataset_columns_for_method(method))
                self.assertIn(column, raw_factor_columns_for_method(method))

    def test_load_external_feature_rows_accepts_symbol_or_code_and_filters_to_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "chip_age.csv"
            path.write_text(
                "\n".join(
                    [
                        "date,symbol,profit_ratio,chip_entropy,unknown_feature,ret5,env",
                        "2026-05-25,000001.SZ,0.61,0.72,999,88,strong",
                        "2026-05-25,000002.SZ,,0.55,999,77,weak",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            rows, warnings = load_external_feature_rows(path, method="b2")

        self.assertEqual(warnings, [])
        self.assertEqual(rows[("2026-05-25", "000001.SZ")]["profit_ratio"], 0.61)
        self.assertEqual(rows[("2026-05-25", "000001.SZ")]["chip_entropy"], 0.72)
        self.assertNotIn("unknown_feature", rows[("2026-05-25", "000001.SZ")])
        self.assertNotIn("ret5", rows[("2026-05-25", "000001.SZ")])
        self.assertNotIn("env", rows[("2026-05-25", "000001.SZ")])
        self.assertNotIn("profit_ratio", rows[("2026-05-25", "000002.SZ")])

    def test_build_dataset_rows_merges_external_chip_age_features_by_date_and_code(self):
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
                {"trade_date": "2026-05-25", "close": 10, "high": 10.2, "low": 9.8},
                {"trade_date": "2026-05-26", "close": 11, "high": 11.2, "low": 10.9},
                {"trade_date": "2026-05-27", "close": 12, "high": 12.2, "low": 11.8},
                {"trade_date": "2026-05-28", "close": 13, "high": 13.2, "low": 12.7},
                {"trade_date": "2026-05-29", "close": 14, "high": 14.2, "low": 13.6},
                {"trade_date": "2026-06-01", "close": 15, "high": 15.2, "low": 14.4},
            ],
        }
        external_features = {
            ("2026-05-25", "000001.SZ"): {
                "profit_ratio": 0.61,
                "chip_entropy": 0.72,
                "chip_age_l0_b00": 0.03,
                "env": "strong",
                "ret5": 88.0,
            }
        }

        rows = build_dataset_rows(selection_rows, prices, external_features_by_key=external_features)

        self.assertEqual(rows[0]["env"], "neutral")
        self.assertEqual(rows[0]["ret5"], 50.0)
        self.assertEqual(rows[0]["profit_ratio"], 0.61)
        self.assertEqual(rows[0]["chip_entropy"], 0.72)
        self.assertEqual(rows[0]["chip_age_l0_b00"], 0.03)

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

    def test_load_candidate_rows_reads_b3_factor_artifact_with_b3_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "candidates"
            factor_dir = root / "factors" / "2026-05-25.b3"
            candidate_dir.mkdir(parents=True)
            factor_dir.mkdir(parents=True)
            (candidate_dir / "2026-05-25.b3.json").write_text(
                json.dumps(
                    {
                        "method": "b3",
                        "pick_date": "2026-05-25",
                        "candidates": [{"code": "000001.SZ", "name": "平安银行", "signal": "B3"}],
                    }
                ),
                encoding="utf-8",
            )
            self.write_factor_artifact(
                factor_dir,
                {
                    "method": "b3",
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
                method="b3",
                start_date="2026-05-25",
                end_date="2026-05-25",
            )

        self.assertEqual(warnings, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["method"], "b3")
        self.assertEqual(rows[0]["signal"], "B3")
        self.assertEqual(rows[0]["env"], "neutral")
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
                        "artifact_version": 1,
                        "factor_library_version": "rust-factor-library-v2",
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
                "artifact_version=1:factor_library_version=rust-factor-library-v2"
            ],
        )

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
            {"trade_date": "2026-05-25", "close": 10.0, "low": 9.8},
            {"trade_date": "2026-05-26", "close": 10.5, "low": 10.1},
            {"trade_date": "2026-05-27", "close": 9.5, "low": 9.2},
            {"trade_date": "2026-05-28", "close": 11.0, "low": 10.7},
            {"trade_date": "2026-05-29", "close": 12.0, "low": 11.5},
            {"trade_date": "2026-06-01", "close": 8.0, "low": 7.6},
            {"trade_date": "2026-06-02", "close": 13.0, "low": 12.5},
            {"trade_date": "2026-06-03", "close": 14.0, "low": 13.7},
            {"trade_date": "2026-06-04", "close": 15.0, "low": 14.6},
            {"trade_date": "2026-06-05", "close": 16.0, "low": 15.5},
            {"trade_date": "2026-06-08", "close": 17.0, "low": 16.6},
        ]

        labels = compute_forward_labels(rows, "2026-05-25")

        self.assertEqual(labels["ret3"], 10.0)
        self.assertEqual(labels["ret5"], -20.0)
        self.assertEqual(labels["ret10"], 70.0)
        self.assertEqual(labels["max_drawdown_5d"], -24.0)

    def test_forward_labels_use_front_adjusted_prices_when_adj_factor_is_available(self):
        rows = [
            {"trade_date": "2026-05-25", "close": 10.0, "low": 9.8, "adj_factor": 1.0},
            {"trade_date": "2026-05-26", "close": 5.5, "low": 5.0, "adj_factor": 2.0},
            {"trade_date": "2026-05-27", "close": 5.75, "low": 5.5, "adj_factor": 2.0},
            {"trade_date": "2026-05-28", "close": 6.0, "low": 5.8, "adj_factor": 2.0},
        ]

        labels = compute_forward_labels(rows, "2026-05-25")

        self.assertEqual(labels["ret3"], 20.0)
        self.assertEqual(labels["max_drawdown_5d"], 0.0)

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
                {"trade_date": "2026-05-25", "close": 10, "high": 10.2, "low": 9.8},
                {"trade_date": "2026-05-26", "close": 11, "high": 11.2, "low": 10.9},
                {"trade_date": "2026-05-27", "close": 12, "high": 12.2, "low": 11.8},
                {"trade_date": "2026-05-28", "close": 13, "high": 13.2, "low": 12.7},
                {"trade_date": "2026-05-29", "close": 14, "high": 14.2, "low": 13.6},
                {"trade_date": "2026-06-01", "close": 15, "high": 15.2, "low": 14.4},
            ],
            "000002.SZ": [
                {"trade_date": "2026-05-25", "close": 20, "high": 20.2, "low": 19.5},
                {"trade_date": "2026-05-26", "close": 19, "high": 19.2, "low": 18.8},
                {"trade_date": "2026-05-27", "close": 18, "high": 18.2, "low": 17.8},
                {"trade_date": "2026-05-28", "close": 17, "high": 17.2, "low": 16.5},
                {"trade_date": "2026-05-29", "close": 16, "high": 16.2, "low": 15.6},
                {"trade_date": "2026-06-01", "close": 15, "high": 15.2, "low": 14.7},
            ],
        }

        rows = build_dataset_rows(selection_rows, prices)

        by_code = {row["code"]: row for row in rows}
        self.assertEqual(by_code["000001.SZ"]["ret3"], 30.0)
        self.assertEqual(by_code["000002.SZ"]["ret3"], -15.0)
        self.assertEqual(by_code["000001.SZ"]["win3_vs_day_median"], 1)
        self.assertEqual(by_code["000002.SZ"]["rank_label_3d"], 0)
        self.assertEqual(by_code["000001.SZ"]["close_to_zxdkx_pct"], 1.25)

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
                "midline_state": "pullback_confirm",
                "price_vs_90d_mid": -1.5,
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

        rows = build_dataset_rows(selection_rows, prices)

        self.assertEqual(rows[0]["signal_type"], "manual_signal")
        self.assertEqual(rows[0]["daily_macd_phase_type"], "manual_daily")
        self.assertEqual(rows[0]["weekly_daily_combo_type"], "manual_combo")
        self.assertEqual(rows[0]["midline_state"], "pullback_confirm")
        self.assertEqual(rows[0]["price_vs_90d_mid"], -1.5)

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
