from __future__ import annotations

import importlib.util
from stock_select.research.review_tuning import attach_environment_state
from pathlib import Path

import pandas as pd


def _load_review_tuning_attach_environment_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "review_tuning_attach_environment.py"
    spec = importlib.util.spec_from_file_location("review_tuning_attach_environment", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_attach_environment_state_uses_score_based_state_window(tmp_path) -> None:
    rows = [
        {"method": "b1", "pick_date": "2026-04-10", "code": "000001.SZ"},
        {"method": "b2", "pick_date": "2026-04-20", "code": "000002.SZ"},
    ]
    environment_history = [
        {
            "start_date": "2026-04-01",
            "end_date": "2026-04-15",
            "score_based_state": "weak",
            "state": "neutral",
        },
        {
            "start_date": "2026-04-16",
            "end_date": "2026-04-30",
            "score_based_state": "strong",
            "state": "strong",
        },
    ]

    tagged = attach_environment_state(rows, environment_history, environment_key="score_based_state")

    assert tagged[0]["environment_state"] == "weak"
    assert tagged[1]["environment_state"] == "strong"


def test_attach_environment_state_uses_unknown_when_no_window_matches() -> None:
    rows = [{"method": "b1", "pick_date": "2026-05-01", "code": "000001.SZ"}]

    tagged = attach_environment_state(
        rows,
        [{"start_date": "2026-04-01", "end_date": "2026-04-30", "score_based_state": "weak", "state": "neutral"}],
        environment_key="score_based_state",
    )

    assert tagged[0]["environment_state"] == "unknown"


def test_attach_environment_state_prefers_manual_override_for_overlapping_windows() -> None:
    rows = [{"method": "b2", "pick_date": "2026-04-10", "code": "000001.SZ"}]
    environment_history = [
        {
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "evaluated_at": "2026-04-01",
            "manual_override": False,
            "score_based_state": "weak",
            "state": "neutral",
        },
        {
            "start_date": "2026-04-05",
            "end_date": "2026-04-12",
            "evaluated_at": "2026-04-10",
            "manual_override": True,
            "score_based_state": "strong",
            "state": "strong",
        },
    ]

    tagged = attach_environment_state(rows, environment_history, environment_key="score_based_state")

    assert tagged[0]["environment_state"] == "strong"


def test_attach_environment_state_falls_back_to_state_when_score_based_state_missing() -> None:
    rows = [{"method": "b1", "pick_date": "2026-04-10", "code": "000001.SZ"}]
    environment_history = [
        {
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "evaluated_at": "2026-04-01",
            "manual_override": False,
            "state": "Neutral",
        }
    ]

    tagged = attach_environment_state(rows, environment_history, environment_key="score_based_state")

    assert tagged[0]["environment_state"] == "neutral"


def test_review_tuning_attach_environment_main_writes_samples_with_env_csv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_review_tuning_attach_environment_module()

    samples_path = tmp_path / "samples.csv"
    pd.DataFrame(
        [
            {"method": "b1", "pick_date": "2026-04-10", "code": "000001.SZ"},
            {"method": "b2", "pick_date": "2026-04-20", "code": "000002.SZ"},
        ]
    ).to_csv(samples_path, index=False)

    monkeypatch.setattr(
        module,
        "load_environment_history",
        lambda _runtime_root: [
            {
                "start_date": "2026-04-01",
                "end_date": "2026-04-15",
                "score_based_state": "weak",
                "state": "neutral",
            },
            {
                "start_date": "2026-04-16",
                "end_date": "2026-04-30",
                "score_based_state": "strong",
                "state": "strong",
            },
        ],
    )

    output_dir = tmp_path / "output"
    args = module.parse_args(
        [
            "--samples",
            str(samples_path),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--output-dir",
            str(output_dir),
        ]
    )

    module.main(args)

    frame = pd.read_csv(output_dir / "samples_with_env.csv")
    assert frame.loc[0, "environment_state"] == "weak"
    assert frame.loc[1, "environment_state"] == "strong"
