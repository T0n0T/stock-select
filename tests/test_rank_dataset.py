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
    context_features,
    compute_forward_labels,
    format_csv_value,
    load_candidate_rows,
    load_selection_rows,
    normalize_env,
    normalize_verdict,
    parse_args,
    resolve_output_dir,
)


class RankDatasetTest(unittest.TestCase):
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

    def test_load_candidate_rows_reads_current_candidates_artifacts_without_select(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "candidates"
            candidate_dir.mkdir(parents=True)
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
                                "signal_type": "trend_start",
                                "env": "neutral",
                                "factors": {"close_to_zxdkx_pct": 1.25},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
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
        self.assertEqual(row["signal_type"], "trend_start")
        self.assertEqual(row["close_to_zxdkx_pct"], 1.25)

    def test_load_selection_rows_reads_current_select_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            select_dir = root / "select" / "2026-05-25.b2"
            select_dir.mkdir(parents=True)
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
            (select_dir / "factors.json").write_text(
                json.dumps(
                    {
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
                        ]
                    }
                ),
                encoding="utf-8",
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
        self.assertEqual(row["signal_type"], "trend_start")
        self.assertEqual(row["close_to_zxdkx_pct"], 1.25)
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

    def test_build_dataset_rows_merges_labels_context_and_select_factors(self):
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

    def test_context_features_compute_raw_ratio_factors(self):
        price_rows = []
        start = date(2026, 1, 1)
        for day in range(1, 131):
            close = 100.0 + day
            price_rows.append(
                {
                    "trade_date": (start + timedelta(days=day - 1)).isoformat(),
                    "open": close - 0.5,
                    "close": close,
                    "high": close + 1.0,
                    "low": close - 2.0,
                    "vol": 1000.0 + day * 10.0,
                    "turnover_rate": 2.0 + day / 100.0,
                    "pct_chg": 1.0,
                }
            )

        features = context_features(price_rows, (start + timedelta(days=129)).isoformat())

        self.assertEqual(features["close_to_ma25_pct"], 5.5046)
        self.assertEqual(features["close_to_zxdkx_pct"], 12.8142)
        self.assertEqual(features["ma25_to_zxdkx_pct"], 6.9283)
        self.assertEqual(features["near_ma25_support_flag"], 0)
        self.assertEqual(features["ma_aligned_flag"], 1)
        self.assertEqual(features["zxdkx_up_1d_flag"], 1)
        self.assertEqual(features["box_position_120d_pct"], 99.1803)
        self.assertEqual(features["latest_bar_position_pct"], 66.6667)
        self.assertEqual(features["volume_to_ma5_ratio"], 1.0088)
        self.assertEqual(features["abnormal_volume_event_days_ago"], 0)
        self.assertIn("macd_hist_to_close_pct", features)

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
