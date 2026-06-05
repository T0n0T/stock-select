import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.ml.parity_b2_rank_pipeline import (
    compare_universe,
    current_artifact_dates,
    feature_matrix_diagnostics,
    filter_ignored_old_signals,
    old_review_dates,
    resolve_date_window,
    summarize_column_diffs,
    write_outputs,
)


class B2RankParityTest(unittest.TestCase):
    def test_resolve_date_window_defaults_to_latest_short_common_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            current = root / "current"
            old = root / "old"
            (current / "candidates").mkdir(parents=True)
            (current / "factors").mkdir(parents=True)
            (old / "reviews").mkdir(parents=True)
            for pick_date in ["2026-03-01", "2026-03-02", "2026-03-03"]:
                (current / "candidates" / f"{pick_date}.b2.json").write_text("{}", encoding="utf-8")
                (current / "factors" / f"{pick_date}.b2").mkdir()
                (current / "factors" / f"{pick_date}.b2" / "factors.json").write_text("{}", encoding="utf-8")
                (old / "reviews" / f"{pick_date}.b2").mkdir()
            (current / "candidates" / "2026-03-04.b2.json").write_text("{}", encoding="utf-8")
            (current / "factors" / "2026-03-04.b2").mkdir()
            (current / "factors" / "2026-03-04.b2" / "factors.json").write_text("{}", encoding="utf-8")

            start, end, dates = resolve_date_window(
                current_artifact_dates(current, "b2"),
                old_review_dates(old, "b2"),
                start_date=None,
                end_date=None,
                date_count=2,
            )

        self.assertEqual(start, "2026-03-02")
        self.assertEqual(end, "2026-03-03")
        self.assertEqual(dates, ["2026-03-02", "2026-03-03"])

    def test_filter_ignored_old_signals_excludes_b3_family_by_default(self):
        kept, ignored, counts = filter_ignored_old_signals(
            [
                {"date": "2026-03-02", "code": "a", "signal": "B2"},
                {"date": "2026-03-02", "code": "b", "signal": "B3"},
                {"date": "2026-03-02", "code": "c", "signal": "B3+"},
                {"date": "2026-03-02", "code": "d", "signal": "B4"},
            ],
            ignored_signals={"B3", "B3+"},
        )

        self.assertEqual([row["code"] for row in kept], ["a", "d"])
        self.assertEqual([row["code"] for row in ignored], ["b", "c"])
        self.assertEqual(counts[("2026-03-02", "B3")], 1)
        self.assertEqual(counts[("2026-03-02", "B3+")], 1)

    def test_compare_universe_reports_current_old_common_and_intentional_ignored_counts(self):
        summary, details = compare_universe(
            current_rows=[
                {"date": "2026-03-02", "code": "a", "signal": "B2"},
                {"date": "2026-03-02", "code": "b", "signal": "B2"},
            ],
            old_rows=[
                {"date": "2026-03-02", "code": "b", "signal": "B2"},
                {"date": "2026-03-02", "code": "c", "signal": "B2"},
            ],
            ignored_old_rows=[{"date": "2026-03-02", "code": "d", "signal": "B3"}],
            dates=["2026-03-02"],
        )

        self.assertEqual(summary[0]["current_count"], 2)
        self.assertEqual(summary[0]["old_count"], 2)
        self.assertEqual(summary[0]["common_count"], 1)
        self.assertEqual(summary[0]["current_only_count"], 1)
        self.assertEqual(summary[0]["old_only_count"], 1)
        self.assertEqual(summary[0]["ignored_old_count"], 1)
        self.assertEqual(details["2026-03-02"]["current_only"], ["a"])
        self.assertEqual(details["2026-03-02"]["old_only"], ["c"])
        self.assertEqual(details["2026-03-02"]["ignored_old"], ["d"])

    def test_factor_and_feature_matrix_diagnostics_are_written(self):
        current_rows = [
            {
                "date": "2026-03-02",
                "code": "a",
                "env": "weak",
                "signal": "B2",
                "close_to_ma25_pct": "0",
                "ma25_slope_5d_pct": "2",
            }
        ]
        old_rows = [
            {
                "date": "2026-03-02",
                "code": "a",
                "env": "neutral",
                "signal": "B2",
                "close_to_ma25_pct": "1.5",
                "ma25_slope_5d_pct": "2",
            }
        ]
        common_keys = [("2026-03-02", "a")]
        factor_diffs, examples = summarize_column_diffs(
            current_rows,
            old_rows,
            common_keys=common_keys,
            columns=["env", "signal", "close_to_ma25_pct", "ma25_slope_5d_pct"],
        )
        matrix = feature_matrix_diagnostics(
            current_rows,
            old_rows,
            common_keys=common_keys,
            feature_set="raw_plus_signal",
            feature_manifest=None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_outputs(
                output_dir=output_dir,
                report={"start_date": "2026-03-02", "end_date": "2026-03-02"},
                universe_rows=[{"date": "2026-03-02", "current_count": 1, "old_count": 1}],
                universe_details={"2026-03-02": {"current_only": [], "old_only": [], "ignored_old": []}},
                factor_rows=factor_diffs,
                factor_examples=examples,
                feature_matrix=matrix,
                current_dataset_rows=current_rows,
                old_dataset_rows=old_rows,
            )
            report = json.loads((output_dir / "parity_summary.json").read_text(encoding="utf-8"))
            with (output_dir / "factor_column_diff.csv").open("r", encoding="utf-8", newline="") as handle:
                persisted_factor_rows = list(csv.DictReader(handle))
            with (output_dir / "feature_matrix_diff.csv").open("r", encoding="utf-8", newline="") as handle:
                persisted_matrix_rows = list(csv.DictReader(handle))

        self.assertIn("feature_matrix", report)
        self.assertEqual(report["feature_matrix"]["common_row_count"], 1)
        self.assertEqual(report["feature_matrix"]["categorical_level_diffs"]["env"]["only_current"], ["weak"])
        self.assertEqual(report["feature_matrix"]["categorical_level_diffs"]["env"]["only_old"], ["neutral"])
        self.assertIn("close_to_ma25_pct", [row["column"] for row in persisted_factor_rows])
        self.assertIn("close_to_ma25_pct", [row["feature"] for row in persisted_matrix_rows])


if __name__ == "__main__":
    unittest.main()
