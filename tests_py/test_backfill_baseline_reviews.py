from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backfill_baseline_reviews.py"
spec = importlib.util.spec_from_file_location("backfill_baseline_reviews", SCRIPT_PATH)
backfill = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = backfill
spec.loader.exec_module(backfill)


def test_collect_target_trade_dates_uses_range_or_latest_sample() -> None:
    trade_dates = ["2026-05-20", "2026-05-21", "2026-05-22", "2026-05-25"]

    assert backfill.collect_target_trade_dates(
        trade_dates,
        start_date="2026-05-21",
        end_date="2026-05-25",
        sample_size=2,
    ) == ["2026-05-21", "2026-05-22", "2026-05-25"]
    assert backfill.collect_target_trade_dates(
        trade_dates,
        start_date=None,
        end_date="2026-05-22",
        sample_size=2,
    ) == ["2026-05-21", "2026-05-22"]


def test_plan_backfill_skips_existing_summary_and_environment(tmp_path: Path) -> None:
    review_dir = tmp_path / "reviews" / "2026-05-21.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text("{}", encoding="utf-8")
    env_dir = tmp_path / "environment" / "daily"
    env_dir.mkdir(parents=True)
    (env_dir / "2026-05-21.weak.json").write_text("{}", encoding="utf-8")

    plan = backfill.plan_backfill(
        target_dates=["2026-05-21", "2026-05-22"],
        runtime_root=tmp_path,
        method="b2",
        force=False,
    )

    assert plan.completed_dates == ["2026-05-21"]
    assert plan.missing_dates == ["2026-05-22"]


def test_build_run_command_defaults_to_baseline_only_run(tmp_path: Path) -> None:
    command = backfill.build_run_command(
        pick_date="2026-05-21",
        method="b2",
        dsn="postgresql://example",
        runtime_root=tmp_path,
        stock_select_bin="stock-select-rs",
        llm_min_baseline_score=None,
        llm_review_limit=None,
        recompute=True,
        no_progress=True,
    )

    assert command == [
        "stock-select-rs",
        "run",
        "--method",
        "b2",
        "--pick-date",
        "2026-05-21",
        "--dsn",
        "postgresql://example",
        "--runtime-root",
        str(tmp_path),
        "--recompute",
        "--no-progress",
    ]
