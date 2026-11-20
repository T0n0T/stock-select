import contextlib
import io
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ml import paths
from ml.backfill import candidates
from ml.db import query_rows


class StockSelectBinaryTest(unittest.TestCase):
    def test_direct_duckdb_query_prefers_release_even_if_debug_is_newer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            release_binary = root / "target/release/stock-select-rs"
            debug_binary = root / "target/debug/stock-select-rs"
            for binary in (release_binary, debug_binary):
                binary.parent.mkdir(parents=True)
                binary.touch()
            os.utime(release_binary, ns=(1, 1))
            os.utime(debug_binary, ns=(2, 2))
            with (
                patch("ml.paths.PROJECT_ROOT", root),
                patch("ml.db.resolve_config_value", return_value=None),
                patch("ml.db.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "[]", "")) as run,
            ):
                self.assertEqual(query_rows("fixture.duckdb", "SELECT 1", []), [])
            self.assertEqual(run.call_args.args[0], [str(release_binary), "db-query"])

    def test_candidate_backfill_uses_same_binary_for_calendar_and_screen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            release_binary = root / "target/release/stock-select-rs"
            debug_binary = root / "target/debug/stock-select-rs"
            for binary in (release_binary, debug_binary):
                binary.parent.mkdir(parents=True)
                binary.touch()
            os.utime(release_binary, ns=(1, 1))
            os.utime(debug_binary, ns=(2, 2))
            args = [
                "--start-date", "2026-02-03", "--end-date", "2026-02-03",
                "--runtime-root", str(root), "--duckdb-path", "fixture.duckdb",
                "--method", "scm", "--dry-run",
            ]
            calendar = subprocess.CompletedProcess([], 0, '[{"trade_date": "2026-02-03"}]', "")
            for override, configured, expected in (
                ([], {}, release_binary),
                ([], {"STOCK_SELECT_BIN": str(debug_binary)}, debug_binary),
                (["--binary", str(release_binary)], {"STOCK_SELECT_BIN": str(debug_binary)}, release_binary),
            ):
                with (
                    self.subTest(override=override, configured=configured),
                    patch.dict(os.environ, {"STOCK_SELECT_BIN": ""}),
                    patch("ml.paths.PROJECT_ROOT", root),
                    patch("ml.backfill.candidates.load_dotenv_values", return_value=configured),
                    patch("ml.db.load_dotenv_values", return_value=configured),
                    patch("ml.db.subprocess.run", return_value=calendar) as query,
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    self.assertEqual(candidates.main(args + override), 0)
                    self.assertEqual(query.call_args.args[0], [str(expected), "db-query"])
                    self.assertEqual(shlex.split(output.getvalue().splitlines()[1])[:2], [str(expected), "screen"])

    def test_release_binary_is_default_when_both_builds_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            release_binary = project_root / "target" / "release" / "stock-select-rs"
            debug_binary = project_root / "target" / "debug" / "stock-select-rs"
            release_binary.parent.mkdir(parents=True)
            debug_binary.parent.mkdir(parents=True)
            release_binary.touch()
            debug_binary.touch()

            with patch("ml.paths.PROJECT_ROOT", project_root):
                binary = paths.resolve_stock_select_binary()

        self.assertEqual(binary, release_binary)


if __name__ == "__main__":
    unittest.main()
