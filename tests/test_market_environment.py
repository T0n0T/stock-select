import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_select.market_environment import (
    load_environment_history,
    resolve_market_environment,
    write_environment_history,
)


def test_environment_history_round_trip(tmp_path: Path) -> None:
    intervals = [
        {
            "state": "weak",
            "start_date": "2026-04-08",
            "end_date": "2026-05-11",
            "evaluated_at": "2026-04-08",
            "source": "scheduled",
            "manual_override": False,
            "reason": "risk-off",
        }
    ]

    write_environment_history(tmp_path, intervals)

    assert load_environment_history(tmp_path) == intervals


def test_load_environment_history_returns_empty_list_when_missing(tmp_path: Path) -> None:
    assert load_environment_history(tmp_path) == []


def test_load_environment_history_rejects_malformed_payload(tmp_path: Path) -> None:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True)
    (environment_dir / "history.json").write_text('[]', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid environment history payload"):
        load_environment_history(tmp_path)


def test_load_environment_history_rejects_malformed_interval_entry(tmp_path: Path) -> None:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True)
    (environment_dir / "history.json").write_text('{"intervals": [1]}', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid environment history payload"):
        load_environment_history(tmp_path)


def test_load_environment_history_rejects_invalid_json_text(tmp_path: Path) -> None:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True)
    (environment_dir / "history.json").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid environment history payload"):
        load_environment_history(tmp_path)


def test_resolve_market_environment_returns_interval_covering_pick_date(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-12",
                "end_date": None,
                "evaluated_at": "2026-05-12",
                "source": "scheduled",
                "manual_override": False,
                "reason": "broad rally",
            }
        ],
    )

    resolved = resolve_market_environment(tmp_path, pick_date="2026-05-19")

    assert resolved["state"] == "strong"
    assert resolved["interval_start"] == "2026-05-12"
    assert resolved["reason"] == "broad rally"


def test_resolve_market_environment_matches_boundary_dates(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "weak",
                "start_date": "2026-04-08",
                "end_date": "2026-05-11",
                "evaluated_at": "2026-04-08",
                "source": "scheduled",
                "manual_override": False,
                "reason": "risk-off",
            }
        ],
    )

    resolved = resolve_market_environment(tmp_path, pick_date="2026-05-11")

    assert resolved["state"] == "weak"
    assert resolved["interval_start"] == "2026-04-08"
    assert resolved["interval_end"] == "2026-05-11"


def test_resolve_market_environment_prefers_newer_overlapping_interval(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "weak",
                "start_date": "2026-04-08",
                "end_date": None,
                "evaluated_at": "2026-04-08",
                "source": "scheduled",
                "manual_override": False,
                "reason": "older trend",
            },
            {
                "state": "strong",
                "start_date": "2026-05-12",
                "end_date": None,
                "evaluated_at": "2026-05-12",
                "source": "manual",
                "manual_override": True,
                "reason": "manual rebound override",
            },
        ],
    )

    resolved = resolve_market_environment(tmp_path, pick_date="2026-05-19")

    assert resolved["state"] == "strong"
    assert resolved["interval_start"] == "2026-05-12"
    assert resolved["reason"] == "manual rebound override"


def test_resolve_market_environment_prefers_manual_override_over_later_start_date(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-10",
                "end_date": "2026-05-25",
                "evaluated_at": "2026-05-11",
                "source": "manual",
                "manual_override": True,
                "reason": "manual caution override",
            },
            {
                "state": "weak",
                "start_date": "2026-05-12",
                "end_date": "2026-05-25",
                "evaluated_at": "2026-05-12",
                "source": "scheduled",
                "manual_override": False,
                "reason": "later scheduled interval",
            },
        ],
    )

    resolved = resolve_market_environment(tmp_path, pick_date="2026-05-19")

    assert resolved["state"] == "strong"
    assert resolved["interval_start"] == "2026-05-10"
    assert resolved["reason"] == "manual caution override"
