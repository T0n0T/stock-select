import subprocess
import contextlib
import io
import unittest
from pathlib import Path

from ml.backfill.record import (
    build_dates,
    parse_methods,
    resolve_record_methods,
    run_for_methods_and_dates,
)


class BackfillRecordScriptTest(unittest.TestCase):
    def test_parse_methods_accepts_common_separators(self):
        self.assertEqual(parse_methods("b2,lsh b3\n"), ["b2", "lsh", "b3"])

    def test_empty_record_methods_env_overrides_dotenv_methods(self):
        self.assertEqual(
            resolve_record_methods(None, {"STOCK_SELECT_RECORD_METHODS": "b2"}, env={"STOCK_SELECT_RECORD_METHODS": ""}),
            [],
        )

    def test_build_dates_keeps_latest_ten_trade_dates(self):
        trade_dates = [f"2026-06-{day:02d}" for day in range(1, 16)]

        self.assertEqual(build_dates(trade_dates, 10), trade_dates[-10:])

    def test_run_for_methods_and_dates_runs_each_method_date_with_record_flag(self):
        captured = []

        def fake_runner(command, **kwargs):
            captured.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with contextlib.redirect_stdout(io.StringIO()):
            rc = run_for_methods_and_dates(
                methods=["b2", "lsh"],
                dates=["2026-06-10", "2026-06-11"],
                binary=Path("stock-select-rs"),
                runtime_root=Path("runtime"),
                record_window_trading_days=7,
                runner=fake_runner,
            )

        self.assertEqual(rc, 0)
        self.assertEqual(len(captured), 4)
        first_command, first_kwargs = captured[0]
        self.assertEqual(
            first_command,
            [
                "stock-select-rs",
                "run",
                "--method",
                "b2",
                "--pick-date",
                "2026-06-10",
                "--runtime-root",
                "runtime",
                "--record",
                "--record-window-trading-days",
                "7",
            ],
        )
        self.assertEqual(first_kwargs["cwd"], Path.cwd())


if __name__ == "__main__":
    unittest.main()
