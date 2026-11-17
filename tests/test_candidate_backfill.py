import contextlib
import io
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path

from ml.backfill import candidates as backfill_candidates
from ml.backfill.candidates import (
    BackfillConfig,
    parse_args,
    run_backfill,
    select_missing_dates,
)
from ml.backfill.commands import build_screen_command
from ml.subprocesses import format_returncode


class CandidateBackfillTest(unittest.TestCase):
    def test_parse_args_accepts_future_methods_without_new_script(self):
        args = parse_args(["--start-date", "2026-06-01", "--end-date", "2026-06-04", "--method", "b1"])

        self.assertEqual(args.method, "b1")

    def test_select_missing_dates_skips_existing_eod_candidates_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            candidate_dir = runtime_root / "candidates"
            candidate_dir.mkdir()
            (candidate_dir / "2026-06-03.b2.json").write_text("{}", encoding="utf-8")
            (candidate_dir / "2026-06-04.intraday.b2.json").write_text("{}", encoding="utf-8")

            missing = select_missing_dates(
                ["2026-06-03", "2026-06-04"],
                runtime_root=runtime_root,
                method="b2",
                skip_existing=True,
            )

        self.assertEqual(missing, ["2026-06-04"])

    def test_select_missing_dates_can_target_intraday_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            candidate_dir = runtime_root / "candidates"
            candidate_dir.mkdir()
            (candidate_dir / "2026-06-03.b2.json").write_text("{}", encoding="utf-8")
            (candidate_dir / "2026-06-04.intraday.b2.json").write_text("{}", encoding="utf-8")

            missing = select_missing_dates(
                ["2026-06-03", "2026-06-04"],
                runtime_root=runtime_root,
                method="b2",
                skip_existing=True,
                intraday=True,
            )

        self.assertEqual(missing, ["2026-06-03"])

    def test_select_missing_dates_requires_factor_artifacts_when_exporting_factors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            candidate_dir = runtime_root / "candidates"
            factor_dir = runtime_root / "factors" / "2026-06-03.b2"
            candidate_dir.mkdir()
            factor_dir.mkdir(parents=True)
            (candidate_dir / "2026-06-03.b2.json").write_text("{}", encoding="utf-8")
            (candidate_dir / "2026-06-04.b2.json").write_text("{}", encoding="utf-8")
            (factor_dir / "factors.json").write_text("{}", encoding="utf-8")

            missing = select_missing_dates(
                ["2026-06-03", "2026-06-04"],
                runtime_root=runtime_root,
                method="b2",
                skip_existing=True,
                require_factor_artifact=True,
            )

        self.assertEqual(missing, ["2026-06-04"])

    def test_build_screen_command_does_not_put_credentials_on_command_line(self):
        command = build_screen_command(
            binary=Path("target/debug/stock-select-rs"),
            pick_date="2026-06-03",
            runtime_root=Path("/tmp/runtime"),
            method="b2",
            recompute=True,
            pool_source="turnover-top",
            export_factors=False,
        )

        command_text = " ".join(command)
        self.assertEqual(command[0], "target/debug/stock-select-rs")
        self.assertIn("--pick-date", command)
        self.assertIn("2026-06-03", command)
        self.assertIn("--runtime-root", command)
        self.assertIn("/tmp/runtime", command)
        self.assertIn("--recompute", command)
        self.assertNotIn("--dsn", command)
        self.assertNotIn("--tushare-token", command_text)

    def test_build_screen_command_can_request_runtime_factor_export(self):
        command = build_screen_command(
            binary=Path("target/debug/stock-select-rs"),
            pick_date="2026-06-03",
            runtime_root=Path("/tmp/runtime"),
            method="b2",
            recompute=False,
            pool_source="turnover-top",
            export_factors=True,
        )

        self.assertIn("--export-factors", command)

    def test_build_screen_command_can_request_intraday_runtime_factor_export(self):
        command = build_screen_command(
            binary=Path("target/debug/stock-select-rs"),
            pick_date="2026-06-03",
            runtime_root=Path("/tmp/runtime"),
            method="b2",
            recompute=False,
            pool_source="turnover-top",
            export_factors=True,
            intraday=True,
        )

        self.assertIn("--intraday", command)
        self.assertIn("--export-factors", command)

    def test_run_backfill_dry_run_does_not_call_runner(self):
        calls = []
        config = BackfillConfig(
            binary=Path("stock-select-rs"),
            runtime_root=Path("/tmp/runtime"),
            method="b2",
            workers=2,
            dry_run=True,
        )

        result = run_backfill(
            ["2026-06-01", "2026-06-02"],
            config=config,
            runner=lambda *_args, **_kwargs: calls.append(_args),
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.dry_run_count, 2)
        self.assertEqual(result.success_count, 0)
        self.assertEqual(result.failures, [])

    def test_scm_and_pbm_backfills_run_one_worker_to_bound_memory(self):
        import threading
        import time

        for method in ("scm", "pbm"):
            with self.subTest(method=method):
                active_workers = 0
                max_active_workers = 0
                active_workers_lock = threading.Lock()

                def fake_runner(command, **_kwargs):
                    nonlocal active_workers, max_active_workers
                    with active_workers_lock:
                        active_workers += 1
                        max_active_workers = max(max_active_workers, active_workers)
                    time.sleep(0.03)
                    with active_workers_lock:
                        active_workers -= 1
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

                config = BackfillConfig(
                    binary=Path("stock-select-rs"),
                    runtime_root=Path("/tmp/runtime"),
                    method=method,
                    workers=4,
                )

                result = run_backfill(
                    ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"],
                    config=config,
                    runner=fake_runner,
                )

                self.assertEqual(result.success_count, 4)
                self.assertEqual(max_active_workers, 1)

    def test_single_worker_backfill_does_not_start_queued_dates_after_interrupt(self):
        calls = []

        def interrupting_runner(command, **_kwargs):
            pick_date = command[command.index("--pick-date") + 1]
            calls.append(pick_date)
            raise KeyboardInterrupt

        config = BackfillConfig(
            binary=Path("stock-select-rs"),
            runtime_root=Path("/tmp/runtime"),
            method="scm",
            workers=1,
        )

        with self.assertRaises(KeyboardInterrupt):
            run_backfill(
                ["2026-06-01", "2026-06-02", "2026-06-03"],
                config=config,
                runner=interrupting_runner,
            )

        self.assertEqual(calls, ["2026-06-01"])

    def test_run_backfill_collects_failed_dates(self):
        def fake_runner(command, **_kwargs):
            if command[command.index("--pick-date") + 1] == "2026-06-02":
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="screen failed")
            return subprocess.CompletedProcess(command, 0, stdout="screen complete", stderr="")

        config = BackfillConfig(
            binary=Path("stock-select-rs"),
            runtime_root=Path("/tmp/runtime"),
            method="b2",
            workers=2,
        )

        result = run_backfill(
            ["2026-06-01", "2026-06-02"],
            config=config,
            runner=fake_runner,
        )

        self.assertEqual(result.success_count, 1)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].pick_date, "2026-06-02")
        self.assertIn("screen failed", result.failures[0].stderr)

    def test_run_backfill_releases_completed_outputs_between_jobs(self):
        import gc
        import time
        import weakref

        payload_refs = []
        observed = {}

        class Payload:
            pass

        def fake_runner(command, **_kwargs):
            pick_date = command[command.index("--pick-date") + 1]
            payload = Payload()
            payload_refs.append(weakref.ref(payload))
            if pick_date == "2026-06-03":
                for _ in range(50):
                    gc.collect()
                    if payload_refs[0]() is None:
                        break
                    time.sleep(0.01)
                observed["first_payload_collected"] = payload_refs[0]() is None
            return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

        config = BackfillConfig(
            binary=Path("stock-select-rs"),
            runtime_root=Path("/tmp/runtime"),
            method="b2",
            workers=1,
            quiet=True,
        )

        result = run_backfill(
            ["2026-06-01", "2026-06-02", "2026-06-03"],
            config=config,
            runner=fake_runner,
        )

        self.assertEqual(result.success_count, 3)
        self.assertTrue(observed["first_payload_collected"])

    def test_format_returncode_labels_negative_signal_exit(self):
        self.assertEqual(format_returncode(-signal.SIGKILL), "signal=SIGKILL")

    def test_run_backfill_prints_signal_name_for_killed_subprocess(self):
        def fake_runner(command, **_kwargs):
            return subprocess.CompletedProcess(command, -signal.SIGKILL, stdout="", stderr="")

        config = BackfillConfig(
            binary=Path("stock-select-rs"),
            runtime_root=Path("/tmp/runtime"),
            method="b3",
            workers=1,
            quiet=False,
        )

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = run_backfill(["2026-06-01"], config=config, runner=fake_runner)

        self.assertEqual(len(result.failures), 1)
        self.assertIn("2026-06-01 failed signal=SIGKILL", stream.getvalue())

    def test_main_returns_130_without_traceback_on_keyboard_interrupt(self):
        def interrupting_run_backfill(*_args, **_kwargs):
            raise KeyboardInterrupt

        original_run_backfill = backfill_candidates.run_backfill
        backfill_candidates.run_backfill = interrupting_run_backfill
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                dates_file = Path(temp_dir) / "dates.txt"
                dates_file.write_text("2026-06-01\n", encoding="utf-8")
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    rc = backfill_candidates.main(
                        [
                            "--start-date",
                            "2026-06-01",
                            "--end-date",
                            "2026-06-01",
                            "--runtime-root",
                            temp_dir,
                            "--dates-file",
                            str(dates_file),
                        ]
                    )
        finally:
            backfill_candidates.run_backfill = original_run_backfill

        self.assertEqual(rc, 130)
        self.assertIn("backfill interrupted", stream.getvalue())
