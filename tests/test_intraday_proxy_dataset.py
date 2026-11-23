import csv
import tempfile
import unittest
from pathlib import Path

from ml.dataset.intraday_proxy import (
    INTRADAY_FACTOR_GROUPS,
    build_intraday_proxy_dataset,
    classify_intraday_factor,
)


class IntradayProxyDatasetTest(unittest.TestCase):
    def test_classifies_factors_from_static_rt_k_contract(self):
        self.assertEqual(classify_intraday_factor("close_to_ma25_pct"), "live_recomputed_from_rt_k")
        self.assertEqual(classify_intraday_factor("czsc_last_bi_range_width_pct"), "previous_eod_snapshot")
        self.assertEqual(classify_intraday_factor("sw_l2_main_pct_change"), "previous_eod_snapshot")
        self.assertEqual(
            classify_intraday_factor("intraday_czsc_close_to_last_bi_high_pct"),
            "live_price_against_previous_structure",
        )
        for column in [
            "turnover_rate_f",
            "stock_mf_net_amount",
            "dmi_adx_qfq",
            "trix_qfq",
            "obv_qfq",
        ]:
            self.assertEqual(classify_intraday_factor(column), "unavailable_intraday")

        classified = set().union(*map(set, INTRADAY_FACTOR_GROUPS.values()))
        self.assertIn("ma25_bullish_engulf_volume_ratio", classified)
        for column in [
            "ma25_weekly_macd_wave_index",
            "ma25_weekly_macd_rising_initial_flag",
            "ma25_weekly_macd_top_divergence_flag",
            "ma25_weekly_daily_constructive_combo_flag",
            "macd_weekly_hist",
            "macd_monthly_hist",
        ]:
            self.assertEqual(classify_intraday_factor(column), "live_recomputed_from_rt_k")

        self.assertEqual(
            classify_intraday_factor("structure_zxdkx"),
            "live_recomputed_excluded_after_validation",
        )

        for column in [
            "macd_daily_hist_to_close_pct",
            "volume_event_abnormal_to_ma20_ratio",
            "bar_close_position_pct",
        ]:
            self.assertEqual(classify_intraday_factor(column), "duplicate_runtime_alias")

        for column in [
            "macd_weekly_dea_pctile",
            "macd_state_weekly_phase_type",
            "bar_upper_shadow_pct",
        ]:
            self.assertEqual(classify_intraday_factor(column), "unavailable_intraday")

        # SCM screening emits this value for every selected row. It is available
        # intraday, but constant and therefore deliberately not a model feature.
        self.assertEqual(classify_intraday_factor("signal"), "constant_strategy_metadata")

    def test_builds_static_proxy_without_intraday_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "rank_dataset.csv"
            source.write_text(
                "date,code,env,close_to_ma25_pct,stock_mf_net_amount,turnover_rate_f,"
                "czsc_close_to_last_bi_high_pct,czsc_last_bi_range_width_pct,czsc_status,"
                "ma25_bullish_engulf_volume_ratio,ma25_weekly_macd_wave_index,structure_zxdkx,signal,ret3,rank_label_3d\n"
                "2026-07-01,000001.SZ,strong,1.2,99,2.1,-2.5,8.0,ok,1.4,2,10.2,SCM,3.1,3\n"
                "2026-07-02,000002.SZ,weak,0.8,88,1.8,-1.5,6.0,ok,0.9,3,11.4,SCM,-1.0,0\n",
                encoding="utf-8",
            )
            output_dir = root / "output"

            summary = build_intraday_proxy_dataset(
                source_dataset=source,
                output_dir=output_dir,
            )

            with (output_dir / "rank_dataset.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(summary["row_count"], 2)
        self.assertIn("close_to_ma25_pct", summary["feature_columns"])
        self.assertNotIn("czsc_last_bi_range_width_pct", summary["feature_columns"])
        self.assertNotIn("czsc_status", summary["feature_columns"])
        self.assertIn("ma25_bullish_engulf_volume_ratio", summary["feature_columns"])
        self.assertIn("ma25_weekly_macd_wave_index", summary["feature_columns"])
        self.assertNotIn("structure_zxdkx", summary["feature_columns"])
        self.assertNotIn("signal", summary["feature_columns"])
        self.assertIn("signal", summary["constant_strategy_metadata_columns"])
        self.assertNotIn("stock_mf_net_amount", summary["feature_columns"])
        self.assertNotIn("turnover_rate_f", summary["feature_columns"])
        self.assertNotIn("czsc_close_to_last_bi_high_pct", summary["feature_columns"])
        self.assertNotIn("intraday_czsc_close_to_last_bi_high_pct", summary["feature_columns"])
        self.assertEqual(rows[0]["rank_label_3d"], "3")
        self.assertEqual(summary["capability_basis"]["previous_eod_tables"], [
            "stock_stk_factor_pro", "calc_daily_czsc_structure",
            "calc_daily_rolling_factors", "calc_indicator_state",
        ])
        self.assertEqual(summary["proxy_aliases"], {})
        self.assertNotIn("intraday_factor_artifact", summary)
        self.assertEqual(summary["factor_groups"]["unavailable_intraday"]["reason"], "盘中无当天数据源")
        self.assertIn(
            "czsc_last_bi_range_width_pct",
            summary["factor_groups"]["previous_eod_snapshot"]["source_columns"],
        )

    def test_rejects_unknown_feature_instead_of_silently_including_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "rank_dataset.csv"
            source.write_text(
                "date,code,mystery_factor,ret3,rank_label_3d\n"
                "2026-07-01,000001.SZ,1.0,3.1,3\n",
                encoding="utf-8",
            )

            summary = build_intraday_proxy_dataset(source_dataset=source, output_dir=root / "output")

        self.assertNotIn("mystery_factor", summary["feature_columns"])
        self.assertIn("mystery_factor", summary["unclassified_source_columns"])

    def test_rebuilds_intraday_czsc_from_previous_eod_structure_and_live_close(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "rank_dataset.csv"
            source.write_text(
                "date,code,czsc_snapshot_available,czsc_last_bi_range_width_pct,"
                "intraday_czsc_close_to_last_bi_high_pct,ret3,rank_label_3d\n"
                "2026-07-02,000001.SZ,1,99,,3.1,3\n",
                encoding="utf-8",
            )
            lookup = {
                ("2026-07-02", "000001.SZ"): {
                    "current_close_qfq": 11.0,
                    "snapshot_available": True,
                    "source_bar_valid": True,
                    "status": "ok",
                    "available_finished_bi_count": 7,
                    "recent_bi_count": 5,
                    "last_bi_direction": "up",
                    "last_bi_high": 10.0,
                    "last_bi_low": 8.0,
                    "last_bi_mid": 9.0,
                    "latest_zs_zg": 10.0,
                    "latest_zs_zd": 8.0,
                    "latest_zs_zz": 9.0,
                    "latest_zs_bi_count": 4,
                    "recent_peak_high": 12.0,
                    "recent_peak_date_present": True,
                    "post_peak_first_bear_open": 9.5,
                    "post_peak_first_bear_high": 10.0,
                    "post_peak_first_bear_low": 9.0,
                    "post_peak_first_bear_close": 9.2,
                    "post_peak_first_bear_date_present": True,
                    "post_peak_first_bear_missing": False,
                }
            }

            summary = build_intraday_proxy_dataset(
                source_dataset=source,
                output_dir=root / "output",
                previous_eod_czsc_lookup=lookup,
            )
            with (root / "output" / "rank_dataset.csv").open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))

        self.assertEqual(row["czsc_snapshot_available"], "1")
        self.assertEqual(row["czsc_status"], "ok")
        self.assertEqual(row["czsc_last_bi_range_width_pct"], "25")
        self.assertEqual(row["intraday_czsc_close_to_last_bi_high_pct"], "10")
        self.assertEqual(row["intraday_czsc_close_to_zs_zz_pct"], "22.2222")
        self.assertEqual(row["czsc_pricing_bear_body_pct"], "-3.1579")
        self.assertIn("intraday_czsc_close_to_last_bi_high_pct", summary["feature_columns"])
        self.assertEqual(summary["previous_eod_czsc_lookup_covered_rows"], 1)


if __name__ == "__main__":
    unittest.main()
