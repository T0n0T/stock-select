import contextlib
import io
import signal
import subprocess
import sys
import unittest
from pathlib import Path

from scripts import backfill_run
from scripts.backfill_run import RunConfig, parse_args, run_single_quiet
from scripts.ml.backfill_candidates import parse_args as parse_candidate_args


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
            "backfill_run.py",
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


if __name__ == "__main__":
    unittest.main()
