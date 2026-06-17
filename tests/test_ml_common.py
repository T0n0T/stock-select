import signal
import tempfile
import unittest
from pathlib import Path

from ml.dates import read_dates_file, validate_date, weekday_fallback
from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import candidate_path, factor_artifact_path, select_dir
from ml.subprocesses import format_returncode


class MlCommonTest(unittest.TestCase):
    def test_load_dotenv_values_handles_export_and_quotes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text("export STOCK_SELECT_RUNTIME_ROOT='runtime-x'\nPOSTGRES_DSN=postgres://secret\n", encoding="utf-8")
            values = load_dotenv_values(path)
        self.assertEqual(values["STOCK_SELECT_RUNTIME_ROOT"], "runtime-x")
        self.assertEqual(values["POSTGRES_DSN"], "postgres://secret")

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
        self.assertEqual(candidate_path(root, "2026-06-01", "b3"), root / "candidates" / "2026-06-01.b3.json")
        self.assertEqual(factor_artifact_path(root, "2026-06-01", "b3"), root / "factors" / "2026-06-01.b3" / "factors.json")
        self.assertEqual(select_dir(root, "2026-06-01", "b3"), root / "select" / "2026-06-01.b3")

    def test_format_returncode_labels_signals(self):
        self.assertEqual(format_returncode(-signal.SIGKILL), "signal=SIGKILL")
        self.assertEqual(format_returncode(2), "rc=2")


if __name__ == "__main__":
    unittest.main()
