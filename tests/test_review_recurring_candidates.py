import contextlib
import builtins
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ml.cli import main
from ml.review.recurring_candidates import (
    collect_candidate_occurrences,
    collect_candidate_occurrences_from_payloads,
    fetch_recent_trade_dates,
    format_recurring_lines_from_review_list,
    format_recurring_lines,
    parse_methods,
    recent_trade_dates,
    resolve_trade_dates,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class ReviewRecurringCandidatesTest(unittest.TestCase):
    def test_parse_methods_accepts_b2_scm_pbm_combinations(self):
        self.assertEqual(
            parse_methods("b2,scm pbm,SCM PBM"),
            ["b2", "scm", "pbm"],
        )

    def test_recent_trade_dates_keeps_only_previous_window_dates(self):
        self.assertEqual(
            recent_trade_dates(
                "2026-06-08",
                ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-08"],
                window=2,
            ),
            ["2026-06-02", "2026-06-03"],
        )

    def test_collect_candidate_occurrences_does_not_backfill_missing_dates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            write_json(
                runtime_root / "candidates" / "2026-06-01.b2.json",
                {"candidates": [{"code": "000999.SZ"}]},
            )
            write_json(
                runtime_root / "candidates" / "2026-06-03.b2.json",
                {"candidates": [{"code": "000001.SZ"}]},
            )

            occurrences = collect_candidate_occurrences(
                runtime_root=runtime_root,
                dates=["2026-06-02", "2026-06-03"],
                methods=["b2"],
            )

        self.assertEqual(list(occurrences), ["000001.SZ"])
        self.assertEqual(occurrences["000001.SZ"][0].pick_date, "2026-06-03")

    def test_format_recurring_lines_appends_repeat_marker(self):
        rows = [
            {
                "code": "000001.SZ",
                "name": "Ping An",
                "industry": "Bank",
                "model_rank": 1,
                "model_score": 0.1234567,
                "llm_action": "KEEP",
            },
            {"code": "000002.SZ", "model_rank": 2, "model_score": None, "llm_action": None},
        ]
        occurrences = collect_candidate_occurrences_from_payloads(
            [("2026-06-03", "b2", {"candidates": [{"code": "000001.SZ"}]})]
        )

        self.assertEqual(
            format_recurring_lines(rows, occurrences),
            [
                "1\t000001.SZ\tPing An\tBank\t0.123457\t\u2191\trepeat:b2@2026-06-03",
                "2\t000002.SZ\t-\t-\t-\t-\t-",
            ],
        )

    def test_format_recurring_lines_from_review_list_preserves_name_and_industry(self):
        occurrences = collect_candidate_occurrences_from_payloads(
            [("2026-07-03", "b2", {"candidates": [{"code": "600183.SH"}]})]
        )

        self.assertEqual(
            format_recurring_lines_from_review_list(
                ["5\t600183.SH\t生益科技\t元器件\t0.979487\t-"],
                occurrences,
            ),
            ["5\t600183.SH\t生益科技\t元器件\t0.979487\t-\trepeat:b2@2026-07-03"],
        )

    def test_cli_prints_display_rows_with_recurring_candidate_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            dates_file = Path(temp_dir) / "dates.txt"
            dates_file.write_text("2026-06-01\n2026-06-02\n2026-06-03\n2026-06-08\n", encoding="utf-8")
            write_json(
                runtime_root / "select" / "2026-06-08.b2" / "display.json",
                {
                    "rows": [
                        {
                            "code": "000001.SZ",
                            "name": "Ping An",
                            "industry": "Bank",
                            "model_rank": 1,
                            "model_score": 0.7,
                            "llm_action": "CAUTION",
                        },
                        {
                            "code": "000002.SZ",
                            "name": "Vanke",
                            "industry": "Real Estate",
                            "model_rank": 2,
                            "model_score": 0.5,
                            "llm_action": "REJECT",
                        },
                    ]
                },
            )
            write_json(
                runtime_root / "candidates" / "2026-06-01.b2.json",
                {"candidates": [{"code": "000002.SZ"}]},
            )
            write_json(
                runtime_root / "candidates" / "2026-06-02.b2.json",
                {"candidates": [{"code": "000001.SZ"}]},
            )
            write_json(
                runtime_root / "candidates" / "2026-06-03.scm.json",
                {"candidates": [{"code": "000001.SZ"}]},
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = main(
                    [
                        "review",
                        "recurring-candidates",
                        "--pick-date",
                        "2026-06-08",
                        "--runtime-root",
                        str(runtime_root),
                        "--method",
                        "b2",
                        "--candidate-methods",
                        "b2,scm",
                        "--dates-file",
                        str(dates_file),
                        "--window",
                        "2",
                    ]
                )

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("1\t000001.SZ\tPing An\tBank\t0.700000\t\u2192\trepeat:b2@2026-06-02,scm@2026-06-03", output)
        self.assertIn("2\t000002.SZ\tVanke\tReal Estate\t0.500000\t\u2193\t-", output)

    def test_cli_defaults_candidate_methods_to_b2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            dates_file = Path(temp_dir) / "dates.txt"
            dates_file.write_text("2026-06-02\n2026-06-08\n", encoding="utf-8")
            write_json(
                runtime_root / "select" / "2026-06-08.b2" / "display.json",
                {"rows": [{"code": "000001.SZ", "model_rank": 1, "model_score": 0.7}]},
            )
            write_json(
                runtime_root / "candidates" / "2026-06-02.b2.json",
                {"candidates": [{"code": "000001.SZ"}]},
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = main(
                    [
                        "review",
                        "recurring-candidates",
                        "--pick-date",
                        "2026-06-08",
                        "--runtime-root",
                        str(runtime_root),
                        "--dates-file",
                        str(dates_file),
                    ]
                )

        self.assertEqual(rc, 0)
        self.assertIn("repeat:b2@2026-06-02", stdout.getvalue())

    def test_resolve_trade_dates_fetches_recent_window_when_dates_file_omitted(self):
        import argparse
        from ml.review import recurring_candidates

        calls = []

        def fake_fetch(duckdb_path, pick_date, window):
            calls.append((duckdb_path, pick_date, window))
            return ["2026-06-01", "2026-06-02", "2026-06-03"]

        original_fetch = recurring_candidates.fetch_recent_trade_dates
        recurring_candidates.fetch_recent_trade_dates = fake_fetch
        try:
            dates = resolve_trade_dates(
                argparse.Namespace(dates_file=None, duckdb_path=None, pick_date="2026-06-08", window=2),
                {"DUCKDB_PATH": "cache.duckdb"},
            )
        finally:
            recurring_candidates.fetch_recent_trade_dates = original_fetch

        self.assertEqual(dates, ["2026-06-01", "2026-06-02", "2026-06-03"])
        self.assertEqual(calls, [("cache.duckdb", "2026-06-08", 2)])

    def test_fetch_recent_trade_dates_propagates_database_errors(self):
        with patch("ml.review.recurring_candidates.query_rows", side_effect=RuntimeError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                fetch_recent_trade_dates("cache.duckdb", "2026-07-09", 3)


if __name__ == "__main__":
    unittest.main()
