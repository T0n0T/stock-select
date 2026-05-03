import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_select.market_environment import (
    _score_index_environment_frame,
    ensure_market_environment,
    evaluate_market_environment,
    load_environment_history,
    override_market_environment,
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


def test_ensure_market_environment_reuses_existing_interval(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "neutral",
                "start_date": "2026-05-05",
                "end_date": None,
                "evaluated_at": "2026-05-05",
                "source": "scheduled",
                "manual_override": False,
                "reason": "range-bound",
            }
        ],
    )

    called = {"value": False}

    def fake_loader() -> dict[str, object]:
        called["value"] = True
        return {}

    resolved = ensure_market_environment(tmp_path, pick_date="2026-05-12", evaluation_loader=fake_loader)

    assert resolved["state"] == "neutral"
    assert called["value"] is False


def test_ensure_market_environment_creates_and_persists_interval(tmp_path: Path) -> None:
    evaluation = {
        "evaluate_date": "2026-05-19",
        "state": "strong",
        "total_score": 8.5,
        "indices": {
            "sse": {"total_score": 4.0},
            "cn2000": {"total_score": 4.5},
        },
        "reason": "indices trend up",
        "source": "scheduled",
    }

    def fake_loader() -> dict[str, object]:
        return evaluation

    resolved = ensure_market_environment(tmp_path, pick_date="2026-05-19", evaluation_loader=fake_loader)

    assert resolved == {
        "state": "strong",
        "interval_start": "2026-05-19",
        "interval_end": None,
        "reason": "indices trend up",
        "source": "scheduled",
    }
    assert load_environment_history(tmp_path) == [
        {
            "state": "strong",
            "start_date": "2026-05-19",
            "end_date": None,
            "evaluated_at": "2026-05-19",
            "source": "scheduled",
            "manual_override": False,
            "reason": "indices trend up",
        }
    ]


def test_ensure_market_environment_malformed_history_does_not_trigger_loader(tmp_path: Path) -> None:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True)
    (environment_dir / "history.json").write_text("{", encoding="utf-8")

    called = {"value": False}

    def fake_loader() -> dict[str, object]:
        called["value"] = True
        return {}

    with pytest.raises(ValueError, match="Invalid environment history payload"):
        ensure_market_environment(tmp_path, pick_date="2026-05-19", evaluation_loader=fake_loader)

    assert called["value"] is False


def test_override_market_environment_closes_previous_interval(tmp_path: Path) -> None:
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

    override_market_environment(
        tmp_path,
        pick_date="2026-05-19",
        state="weak",
        reason="panic break",
    )

    intervals = load_environment_history(tmp_path)
    assert intervals[0]["end_date"] == "2026-05-18"
    assert intervals[1]["state"] == "weak"
    assert intervals[1]["manual_override"] is True


def test_evaluate_market_environment_returns_strong_when_indices_trend_up() -> None:
    dates = pd.date_range("2026-01-05", periods=120, freq="B")
    sse = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [3000 + i for i in range(len(dates))],
            "high": [3005 + i for i in range(len(dates))],
            "low": [2995 + i for i in range(len(dates))],
            "close": [3002 + i for i in range(len(dates))],
            "vol": [1000 + i * 10 for i in range(len(dates))],
        }
    )
    cn2000 = sse.assign(ts_code="399303.SZ", close=[3100 + i * 1.4 for i in range(len(dates))])

    result = evaluate_market_environment(
        pick_date="2026-04-30",
        sse_history=sse,
        cn2000_history=cn2000,
    )

    assert result["state"] == "strong"
    assert result["total_score"] > 0
    assert "indices" in result


def test_evaluate_market_environment_returns_weak_when_indices_break_down() -> None:
    dates = pd.date_range("2026-01-05", periods=120, freq="B")
    sse = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [3200 - i for i in range(len(dates))],
            "high": [3205 - i for i in range(len(dates))],
            "low": [3190 - i for i in range(len(dates))],
            "close": [3195 - i for i in range(len(dates))],
            "vol": [2000 + i * 15 for i in range(len(dates))],
        }
    )
    cn2000 = sse.assign(ts_code="399303.SZ", close=[3300 - i * 1.6 for i in range(len(dates))])

    result = evaluate_market_environment(
        pick_date="2026-04-30",
        sse_history=sse,
        cn2000_history=cn2000,
    )

    assert result["state"] == "weak"


def test_score_index_environment_frame_raises_for_insufficient_history() -> None:
    dates = pd.date_range("2026-03-02", periods=59, freq="B")
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [3000 + i for i in range(len(dates))],
            "high": [3005 + i for i in range(len(dates))],
            "low": [2995 + i for i in range(len(dates))],
            "close": [3002 + i for i in range(len(dates))],
            "vol": [1000 + i * 10 for i in range(len(dates))],
        }
    )

    with pytest.raises(ValueError, match="Insufficient history for market environment evaluation"):
        _score_index_environment_frame(frame, pick_date="2026-05-21")


def test_score_index_environment_frame_raises_when_pick_date_is_missing() -> None:
    dates = pd.date_range("2026-01-05", periods=60, freq="B")
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [3000 + i for i in range(len(dates))],
            "high": [3005 + i for i in range(len(dates))],
            "low": [2995 + i for i in range(len(dates))],
            "close": [3002 + i for i in range(len(dates))],
            "vol": [1000 + i * 10 for i in range(len(dates))],
        }
    )

    with pytest.raises(ValueError, match="No market environment data found for pick_date 2026-03-28"):
        _score_index_environment_frame(frame, pick_date="2026-03-28")


def test_score_index_environment_frame_ignores_rows_after_pick_date() -> None:
    dates = pd.date_range("2026-01-05", periods=70, freq="B")
    baseline = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [3000 + i for i in range(len(dates))],
            "high": [3005 + i for i in range(len(dates))],
            "low": [2995 + i for i in range(len(dates))],
            "close": [3002 + i for i in range(len(dates))],
            "vol": [1000 + i * 10 for i in range(len(dates))],
        }
    )
    pick_date = str(dates[59].date())
    future_breakdown = baseline.copy()
    future_mask = future_breakdown["trade_date"] > pd.Timestamp(pick_date)
    future_breakdown.loc[future_mask, "close"] = 100.0
    future_breakdown.loc[future_mask, "vol"] = 1.0

    assert _score_index_environment_frame(future_breakdown, pick_date=pick_date) == _score_index_environment_frame(
        baseline.loc[baseline["trade_date"] <= pd.Timestamp(pick_date)],
        pick_date=pick_date,
    )


def test_score_index_environment_frame_uses_fixed_tail_windows() -> None:
    dates = pd.date_range("2026-01-05", periods=120, freq="B")
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [100.0] * len(dates),
            "high": [101.0] * len(dates),
            "low": [99.0] * len(dates),
            "close": [200.0] * 61 + [100.0] * 58 + [101.0],
            "vol": [1000.0] * 100 + [1.0] * 19 + [20.0],
        }
    )

    result = _score_index_environment_frame(frame, pick_date="2026-06-19")

    assert result["position_score"] == 1.0
    assert result["volume_score"] == 1.0


def test_score_index_environment_frame_returns_exact_component_scores() -> None:
    dates = pd.date_range("2026-01-05", periods=60, freq="B")
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [100.0] * len(dates),
            "high": [101.0] * len(dates),
            "low": [99.0] * len(dates),
            "close": [100.0] * 59 + [101.0],
            "vol": [100.0] * 59 + [50.0],
        }
    )

    assert _score_index_environment_frame(frame, pick_date="2026-03-27") == {
        "trend_score": 2.0,
        "position_score": 1.0,
        "volume_score": 0.0,
        "macd_score": 1.0,
        "total_score": 4.0,
    }


def test_evaluate_market_environment_returns_neutral_at_boundary_scores() -> None:
    dates = pd.date_range("2026-01-05", periods=60, freq="B")
    sse = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [100.0] * len(dates),
            "high": [101.0] * len(dates),
            "low": [99.0] * len(dates),
            "close": [100.0] * 59 + [101.0],
            "vol": [100.0] * 59 + [50.0],
        }
    )
    cn2000 = pd.DataFrame(
        {
            "ts_code": ["399303.SZ"] * len(dates),
            "trade_date": dates,
            "open": [200.0] * len(dates),
            "high": [201.0] * len(dates),
            "low": [199.0] * len(dates),
            "close": [100.0] * 41 + [99.0] * 19,
            "vol": [100.0] * 59 + [50.0],
        }
    )

    result = evaluate_market_environment(
        pick_date="2026-03-27",
        sse_history=sse,
        cn2000_history=cn2000,
    )

    assert result["state"] == "neutral"
    assert result["total_score"] == 4.0
