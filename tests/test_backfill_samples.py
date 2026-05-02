from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_samples.py"
    spec = importlib.util.spec_from_file_location("backfill_samples", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load script module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_args_uses_method_specific_default_max_workers() -> None:
    script = _load_script_module()

    b1_args = script.parse_args(["--method", "b1"])
    b2_args = script.parse_args(["--method", "b2"])
    dribull_args = script.parse_args(["--method", "dribull"])
    hcr_args = script.parse_args(["--method", "hcr"])

    assert b1_args.max_workers == 4
    assert b2_args.max_workers == 4
    assert dribull_args.max_workers == 4
    assert hcr_args.max_workers == 6


def test_parse_args_accepts_explicit_positive_max_workers() -> None:
    script = _load_script_module()

    args = script.parse_args(["--max-workers", "3"])

    assert args.max_workers == 3


def test_collect_target_trade_dates_uses_latest_window_up_to_end_date() -> None:
    script = _load_script_module()
    trade_dates = pd.DataFrame(
        {
            "trade_date": [
                "2026-04-30",
                "2026-04-29",
                "2026-04-28",
                "2026-04-27",
                "2026-04-24",
            ]
        }
    )

    result = script.collect_target_trade_dates(trade_dates, end_date="2026-04-28", sample_size=3)

    assert result == ["2026-04-24", "2026-04-27", "2026-04-28"]


def test_collect_target_trade_dates_supports_forward_window_from_start_date() -> None:
    script = _load_script_module()
    trade_dates = pd.DataFrame(
        {
            "trade_date": [
                "2026-04-24",
                "2026-04-27",
                "2026-04-28",
                "2026-04-29",
                "2026-04-30",
            ]
        }
    )

    result = script.collect_target_trade_dates(
        trade_dates,
        end_date="2026-04-30",
        start_date="2026-04-28",
        sample_size=3,
    )

    assert result == ["2026-04-28", "2026-04-29", "2026-04-30"]


def test_collect_target_trade_dates_raises_when_history_is_insufficient() -> None:
    script = _load_script_module()
    trade_dates = pd.DataFrame({"trade_date": ["2026-04-28", "2026-04-27"]})

    with pytest.raises(ValueError, match="Only found 2 trade dates"):
        script.collect_target_trade_dates(trade_dates, end_date="2026-04-28", sample_size=3)


def test_plan_backfill_skips_only_dates_with_review_summary(tmp_path: Path) -> None:
    script = _load_script_module()
    runtime_root = tmp_path / "runtime"
    completed_summary = runtime_root / "reviews" / "2026-04-27.b2" / "summary.json"
    completed_summary.parent.mkdir(parents=True, exist_ok=True)
    completed_summary.write_text("{}", encoding="utf-8")
    candidate_only = runtime_root / "candidates" / "2026-04-28.b2.json"
    candidate_only.parent.mkdir(parents=True, exist_ok=True)
    candidate_only.write_text("{}", encoding="utf-8")

    plan = script.plan_backfill(
        target_dates=["2026-04-27", "2026-04-28"],
        runtime_root=runtime_root,
        method="b2",
    )

    assert plan.completed_dates == ["2026-04-27"]
    assert plan.missing_dates == ["2026-04-28"]


def test_build_run_command_keeps_requested_threshold_and_pick_date() -> None:
    script = _load_script_module()

    command = script.build_run_command(
        pick_date="2026-04-28",
        method="b2",
        llm_min_baseline_score=3.6,
        dsn="postgresql://example",
    )

    assert command == [
        "stock-select",
        "run",
        "--method",
        "b2",
        "--llm-min-baseline-score",
        "3.6",
        "--pick-date",
        "2026-04-28",
        "--dsn",
        "postgresql://example",
    ]


def test_run_backfill_runs_missing_dates_with_configured_parallelism(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = _load_script_module()
    trade_dates = pd.DataFrame({"trade_date": ["2026-04-28", "2026-04-27", "2026-04-24"]})
    args = SimpleNamespace(
        end_date="2026-04-28",
        start_date=None,
        forward=False,
        sample_size=3,
        method="b2",
        llm_min_baseline_score=3.6,
        dsn="postgresql://example",
        runtime_root=tmp_path / "runtime",
        stock_select_bin="stock-select",
        max_workers=2,
        dry_run=False,
    )
    started_dates: list[str] = []
    release_runs = threading.Event()
    lock = threading.Lock()

    class _FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_run(command: list[str], check: bool) -> None:
        pick_date = command[command.index("--pick-date") + 1]
        with lock:
            started_dates.append(pick_date)
            if len(started_dates) >= 2:
                release_runs.set()
        assert release_runs.wait(timeout=0.2), f"expected concurrent start before finishing {pick_date}"

    monkeypatch.setattr(script, "parse_args", lambda argv=None: args)
    monkeypatch.setattr(script, "resolve_script_dsn", lambda cli_dsn: "postgresql://resolved")
    monkeypatch.setattr(script, "fetch_available_trade_dates", lambda connection: trade_dates)
    monkeypatch.setattr(script, "print_plan", lambda **kwargs: None)
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda dsn: _FakeConnection()))
    monkeypatch.setattr(script.subprocess, "run", fake_run)

    assert script.run_backfill() == 0
    assert set(started_dates) == {"2026-04-24", "2026-04-27", "2026-04-28"}
    assert set(started_dates[:2]) == {"2026-04-24", "2026-04-27"}


def test_run_backfill_supports_forward_date_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = _load_script_module()
    trade_dates = pd.DataFrame(
        {"trade_date": ["2026-04-24", "2026-04-27", "2026-04-28", "2026-04-29", "2026-04-30"]}
    )
    args = SimpleNamespace(
        end_date="2026-04-30",
        start_date="2026-04-28",
        sample_size=3,
        method="dribull",
        llm_min_baseline_score=3.6,
        dsn="postgresql://example",
        runtime_root=tmp_path / "runtime",
        stock_select_bin="stock-select",
        max_workers=1,
        dry_run=False,
    )
    started_dates: list[str] = []

    class _FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_run(command: list[str], check: bool) -> None:
        started_dates.append(command[command.index("--pick-date") + 1])

    monkeypatch.setattr(script, "parse_args", lambda argv=None: args)
    monkeypatch.setattr(script, "resolve_script_dsn", lambda cli_dsn: "postgresql://resolved")
    monkeypatch.setattr(script, "fetch_available_trade_dates", lambda connection: trade_dates)
    monkeypatch.setattr(script, "print_plan", lambda **kwargs: None)
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda dsn: _FakeConnection()))
    monkeypatch.setattr(script.subprocess, "run", fake_run)

    assert script.run_backfill() == 0
    assert started_dates == ["2026-04-28", "2026-04-29", "2026-04-30"]
