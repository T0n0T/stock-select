import contextlib
import io
import signal
import subprocess
import sys
import unittest
from pathlib import Path

from ml.backfill import runs as backfill_run
from ml.backfill.candidates import parse_args as parse_candidate_args
from ml.backfill.runs import RunConfig, main_from_args, parse_args, run_single_quiet


class RunBackfillTest(unittest.TestCase):
    def test_run_single_quiet_passes_runtime_root_to_cli(self):
        captured_commands = []
        config = RunConfig(
            binary=Path("target/debug/stock-select-rs"),
            runtime_root=Path("/tmp/runtime"),
            method="b3",
            workers=1,
            skip_existing=True,
            dry_run=False,
            recompute=True,
            pool_source="turnover-top",
        )

        def fake_run(command, **_kwargs):
            captured_commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        original_run = backfill_run.subprocess.run
        backfill_run.subprocess.run = fake_run
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                run_single_quiet("2026-06-03", config)
        finally:
            backfill_run.subprocess.run = original_run

        command = captured_commands[0]

        self.assertEqual(command[0], "target/debug/stock-select-rs")
        self.assertIn("--pick-date", command)
        self.assertIn("2026-06-03", command)
        self.assertIn("--runtime-root", command)
        self.assertIn("/tmp/runtime", command)
        self.assertIn("--recompute", command)

    def test_parse_args_uses_candidate_backfill_parameter_names(self):
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                args = parse_args(
                    [
                        "--start-date",
                        "2026-06-01",
                        "--end-date",
                        "2026-06-04",
                        "--method",
                        "b3",
                        "--workers",
                        "8",
                        "--dsn",
                        "postgres://example",
                        "--no-skip-existing",
                    ]
                )
            except SystemExit as exc:
                self.fail(f"parse_args should accept candidate-style parameters, exited with {exc.code}")

        self.assertEqual(args.workers, 8)
        self.assertEqual(args.dsn, "postgres://example")
        self.assertTrue(args.no_skip_existing)

    def test_parse_args_keeps_legacy_aliases_for_existing_run_commands(self):
        args = parse_args(
            [
                "--start-date",
                "2026-06-01",
                "--end-date",
                "2026-06-04",
                "--jobs",
                "3",
                "--postgres-dsn",
                "postgres://example",
                "--force",
            ]
        )

        self.assertEqual(args.workers, 3)
        self.assertEqual(args.dsn, "postgres://example")
        self.assertTrue(args.no_skip_existing)

    def test_candidate_backfill_accepts_run_backfill_legacy_aliases(self):
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                args = parse_candidate_args(
                    [
                        "--start-date",
                        "2026-06-01",
                        "--end-date",
                        "2026-06-04",
                        "--jobs",
                        "3",
                        "--postgres-dsn",
                        "postgres://example",
                        "--force",
                    ]
                )
            except SystemExit as exc:
                self.fail(f"candidate backfill should accept run-style aliases, exited with {exc.code}")

        self.assertEqual(args.workers, 3)
        self.assertEqual(args.dsn, "postgres://example")
        self.assertTrue(args.no_skip_existing)

    def test_run_single_quiet_reports_negative_returncode_as_signal(self):
        config = RunConfig(
            binary=Path("stock-select-rs"),
            runtime_root=Path("/tmp/runtime"),
            method="b3",
            workers=1,
            skip_existing=True,
            dry_run=False,
            recompute=False,
            pool_source="turnover-top",
        )

        def fake_run(command, **_kwargs):
            return subprocess.CompletedProcess(command, -signal.SIGINT, stdout="", stderr="")

        original_run = backfill_run.subprocess.run
        backfill_run.subprocess.run = fake_run
        try:
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                date_str, ok = run_single_quiet("2026-06-03", config)
        finally:
            backfill_run.subprocess.run = original_run

        self.assertEqual(date_str, "2026-06-03")
        self.assertFalse(ok)
        self.assertIn("失败 (signal=SIGINT)", stream.getvalue())

    def test_main_dry_run_prints_full_run_command(self):
        original_argv = sys.argv
        sys.argv = [
            "stock-select-ml backfill runs",
            "--start-date",
            "2026-06-01",
            "--end-date",
            "2026-06-01",
            "--runtime-root",
            "/tmp/runtime",
            "--method",
            "b3",
            "--workers",
            "1",
            "--dry-run",
        ]
        try:
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = backfill_run.main()
        finally:
            sys.argv = original_argv

        output = stream.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("run --method b3 --pick-date 2026-06-01", output)
        self.assertIn("--runtime-root /tmp/runtime", output)
        self.assertIn("--pool-source turnover-top", output)

    def test_main_reports_failed_run_dates_with_returncode_and_output_tail(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            dates_file = Path(temp_dir) / "dates.txt"
            dates_file.write_text("2026-06-01\n2026-06-02\n", encoding="utf-8")

            def fake_run(command, **_kwargs):
                if "2026-06-02" in command:
                    return subprocess.CompletedProcess(command, 7, stdout="out first\nout tail\n", stderr="err first\nerr tail\n")
                return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

            original_run = backfill_run.subprocess.run
            backfill_run.subprocess.run = fake_run
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = main_from_args(
                        parse_args(
                            [
                                "--start-date",
                                "2026-06-01",
                                "--end-date",
                                "2026-06-02",
                                "--runtime-root",
                                "/tmp/runtime",
                                "--binary",
                                "stock-select-rs",
                                "--method",
                                "b3",
                                "--dates-file",
                                str(dates_file),
                                "--workers",
                                "2",
                            ]
                        )
                    )
            finally:
                backfill_run.subprocess.run = original_run

        output = stream.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("失败:           1", output)
        self.assertIn("failed dates", output)
        self.assertIn("2026-06-02", output)
        self.assertIn("returncode=7", output)
        self.assertIn("err tail", output)
        self.assertIn("out tail", output)

    def test_main_returns_130_on_keyboard_interrupt(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            dates_file = Path(temp_dir) / "dates.txt"
            dates_file.write_text("2026-06-01\n", encoding="utf-8")

            def interrupted_run(_command, **_kwargs):
                raise KeyboardInterrupt

            original_run = backfill_run.subprocess.run
            backfill_run.subprocess.run = interrupted_run
            try:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = main_from_args(
                        parse_args(
                            [
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
                                "--workers",
                                "1",
                            ]
                        )
                    )
            finally:
                backfill_run.subprocess.run = original_run

        self.assertEqual(rc, 130)
        self.assertIn("interrupted", stream.getvalue())
        self.assertIn("rerun remaining dates", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
