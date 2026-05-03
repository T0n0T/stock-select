import sys
from pathlib import Path

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
