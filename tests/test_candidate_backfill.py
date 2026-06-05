import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ml.backfill_candidates import (
    BackfillConfig,
    build_screen_command,
    parse_args,
    run_backfill,
    select_missing_dates,
)


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
