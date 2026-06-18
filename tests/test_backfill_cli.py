import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ml.cli import main


class BackfillCliTest(unittest.TestCase):
    def test_backfill_candidates_dry_run_prints_screen_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dates_file = Path(temp_dir) / "dates.txt"
            dates_file.write_text("2026-06-01\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = main(
                    [
                        "backfill",
                        "candidates",
                        "--start-date",
                        "2026-06-01",
                        "--end-date",
                        "2026-06-01",
                        "--runtime-root",
                        "/tmp/runtime",
                        "--binary",
                        "stock-select-rs",
                        "--method",
                        "b3",
                        "--dates-file",
                        str(dates_file),
                        "--dry-run",
                    ]
                )

        self.assertEqual(rc, 0)
        self.assertIn("screen --method b3 --pick-date 2026-06-01", stdout.getvalue())

    def test_backfill_runs_dry_run_prints_run_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dates_file = Path(temp_dir) / "dates.txt"
            dates_file.write_text("2026-06-01\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = main(
                    [
                        "backfill",
                        "runs",
                        "--start-date",
                        "2026-06-01",
                        "--end-date",
                        "2026-06-01",
                        "--runtime-root",
                        "/tmp/runtime",
                        "--binary",
                        "stock-select-rs",
                        "--method",
                        "b3",
                        "--dates-file",
                        str(dates_file),
                        "--dry-run",
                    ]
                )

        self.assertEqual(rc, 0)
        self.assertIn("run --method b3 --pick-date 2026-06-01", stdout.getvalue())

    def test_backfill_records_dry_run_prints_record_run_command(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = main(
                [
                    "backfill",
                    "records",
                    "--methods",
                    "b2,lsh",
                    "--dates",
                    "2026-06-01,2026-06-02",
                    "--runtime-root",
                    "/tmp/runtime",
                    "--binary",
                    "stock-select-rs",
                    "--dry-run",
                ]
            )

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("run --method b2 --pick-date 2026-06-01", output)
        self.assertIn("run --method lsh --pick-date 2026-06-02", output)
        self.assertIn("--record", output)

    def test_backfill_help_lists_only_records_command(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exit_context:
                main(["backfill", "-h"])

        self.assertEqual(exit_context.exception.code, 0)
        help_text = stdout.getvalue()

        self.assertIn("records", help_text)
        self.assertNotIn("record,records", help_text)


if __name__ == "__main__":
    unittest.main()
