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


if __name__ == "__main__":
    unittest.main()
