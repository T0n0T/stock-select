import signal
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from ml.dates import fetch_trade_dates, read_dates_file, validate_date, weekday_fallback
from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import candidate_path, factor_artifact_path, select_dir
from ml.subprocesses import format_returncode


class MlCommonTest(unittest.TestCase):
    def test_load_dotenv_values_handles_export_and_quotes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text("export STOCK_SELECT_RUNTIME_ROOT='runtime-x'\nDUCKDB_PATH=market-cache.duckdb\n", encoding="utf-8")
            values = load_dotenv_values(path)
        self.assertEqual(values["STOCK_SELECT_RUNTIME_ROOT"], "runtime-x")
        self.assertEqual(values["DUCKDB_PATH"], "market-cache.duckdb")

    def test_resolve_config_value_prefers_cli_then_env_then_dotenv(self):
        self.assertEqual(resolve_config_value("cli", "KEY", {"KEY": "dotenv"}, env={"KEY": "env"}), "cli")
        self.assertEqual(resolve_config_value(None, "KEY", {"KEY": "dotenv"}, env={"KEY": "env"}), "env")
        self.assertEqual(resolve_config_value(None, "KEY", {"KEY": "dotenv"}, env={}), "dotenv")

    def test_dates_and_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dates.txt"
            path.write_text("2026-06-02\n# comment\n2026-06-01\n2026-06-02\n", encoding="utf-8")
            self.assertEqual(read_dates_file(path), ["2026-06-01", "2026-06-02"])
        self.assertEqual(validate_date("2026-06-03"), "2026-06-03")
        self.assertEqual(weekday_fallback("2026-06-05", "2026-06-08"), ["2026-06-05", "2026-06-08"])
        root = Path("/tmp/runtime")
        self.assertEqual(candidate_path(root, "2026-06-01", "scm"), root / "candidates" / "2026-06-01.scm.json")
        self.assertEqual(factor_artifact_path(root, "2026-06-01", "scm"), root / "factors" / "2026-06-01.scm" / "factors.json")
        self.assertEqual(select_dir(root, "2026-06-01", "scm"), root / "select" / "2026-06-01.scm")
        self.assertEqual(
            candidate_path(root, "2026-06-01", "b2", intraday=True),
            root / "candidates" / "2026-06-01.intraday.b2.json",
        )
        self.assertEqual(
            factor_artifact_path(root, "2026-06-01", "b2", intraday=True),
            root / "factors" / "2026-06-01.intraday.b2" / "factors.json",
        )
        self.assertEqual(
            select_dir(root, "2026-06-01", "b2", intraday=True),
            root / "select" / "2026-06-01.intraday.b2",
        )

    def test_fetch_trade_dates_uses_stock_cache_factor_table(self):
        with patch("ml.dates.query_rows", return_value=[
            {"trade_date": "2026-06-01"}, {"trade_date": "2026-06-02"},
        ]) as query:
            dates = fetch_trade_dates("cache.duckdb", "2026-06-01", "2026-06-03")
        self.assertEqual(dates, ["2026-06-01", "2026-06-02"])
        self.assertIn("stock_stk_factor_pro", query.call_args.args[1].lower())

    def test_format_returncode_labels_signals(self):
        self.assertEqual(format_returncode(-signal.SIGKILL), "signal=SIGKILL")
        self.assertEqual(format_returncode(2), "rc=2")


if __name__ == "__main__":
    unittest.main()
