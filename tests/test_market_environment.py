import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_select.market_environment import (
    _apply_environment_state_machine,
    _box_volume_component,
    _build_monthly_macd_bias,
    _collapse_single_day_neutral_islands,
    _compute_raw_environment_state,
    _diagnostic_macd_environment_state,
    _score_based_environment_state,
    _smooth_environment_states,
    _score_index_environment_frame,
    _combine_environment_state,
    _macd_component,
    _vote_based_environment_state,
    build_environment_history_for_dates,
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


def test_build_environment_history_for_dates_compacts_sorted_unique_pick_dates() -> None:
    calls: list[str] = []
    states = {
        "2026-04-01": "weak",
        "2026-04-02": "weak",
        "2026-04-03": "strong",
        "2026-04-07": "weak",
    }

    def fake_evaluator(pick_date: str) -> dict[str, object]:
        calls.append(pick_date)
        return {
            "state": states[pick_date],
            "score_based_state": states[pick_date],
            "evaluate_date": pick_date,
            "reason": f"state on {pick_date}",
            "source": "scheduled",
        }

    intervals = build_environment_history_for_dates(
        ["2026-04-03", "2026-04-01", "2026-04-02", "2026-04-02", "2026-04-07"],
        fake_evaluator,
    )

    assert calls == ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-07"]
    assert intervals == [
        {
            "state": "weak",
            "start_date": "2026-04-01",
            "end_date": "2026-04-02",
            "evaluated_at": "2026-04-02",
            "source": "scheduled",
            "manual_override": False,
            "reason": "state on 2026-04-02",
        },
        {
            "state": "strong",
            "start_date": "2026-04-03",
            "end_date": "2026-04-06",
            "evaluated_at": "2026-04-03",
            "source": "scheduled",
            "manual_override": False,
            "reason": "state on 2026-04-03",
        },
        {
            "state": "weak",
            "start_date": "2026-04-07",
            "end_date": "2026-04-07",
            "evaluated_at": "2026-04-07",
            "source": "scheduled",
            "manual_override": False,
            "reason": "state on 2026-04-07",
        },
    ]


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


def test_ensure_market_environment_inserts_historical_interval_before_future_interval(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-19",
                "end_date": None,
                "evaluated_at": "2026-05-19",
                "source": "scheduled",
                "manual_override": False,
                "reason": "broad rally",
            }
        ],
    )

    called = {"value": False}

    def fake_loader() -> dict[str, object]:
        called["value"] = True
        return {
            "state": "weak",
            "evaluate_date": "2026-05-12",
            "source": "scheduled",
            "reason": "backfilled historical gap",
        }

    resolved = ensure_market_environment(tmp_path, pick_date="2026-05-12", evaluation_loader=fake_loader)

    assert resolved == {
        "state": "weak",
        "interval_start": "2026-05-12",
        "interval_end": "2026-05-18",
        "reason": "backfilled historical gap",
        "source": "scheduled",
    }
    assert called["value"] is True
    assert load_environment_history(tmp_path) == [
        {
            "state": "weak",
            "start_date": "2026-05-12",
            "end_date": "2026-05-18",
            "evaluated_at": "2026-05-12",
            "source": "scheduled",
            "manual_override": False,
            "reason": "backfilled historical gap",
        },
        {
            "state": "strong",
            "start_date": "2026-05-19",
            "end_date": None,
            "evaluated_at": "2026-05-19",
            "source": "scheduled",
            "manual_override": False,
            "reason": "broad rally",
        },
    ]


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


def test_override_market_environment_rejects_out_of_order_override_before_future_interval(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-19",
                "end_date": None,
                "evaluated_at": "2026-05-19",
                "source": "scheduled",
                "manual_override": False,
                "reason": "broad rally",
            }
        ],
    )

    with pytest.raises(ValueError, match="Out-of-order market environment insertion is not supported for pick_date 2026-05-12"):
        override_market_environment(
            tmp_path,
            pick_date="2026-05-12",
            state="weak",
            reason="panic break",
        )


def test_override_market_environment_truncates_closed_interval_covering_pick_date(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-10",
                "end_date": "2026-05-20",
                "evaluated_at": "2026-05-10",
                "source": "scheduled",
                "manual_override": False,
                "reason": "broad rally",
            }
        ],
    )

    override_market_environment(
        tmp_path,
        pick_date="2026-05-15",
        state="weak",
        reason="panic break",
    )

    intervals = load_environment_history(tmp_path)
    active_for_day = [
        interval
        for interval in intervals
        if interval["start_date"] <= "2026-05-15" and (interval["end_date"] is None or "2026-05-15" <= interval["end_date"])
    ]

    assert intervals[0]["end_date"] == "2026-05-14"
    assert intervals[1]["start_date"] == "2026-05-15"
    assert intervals[1]["manual_override"] is True
    assert len(active_for_day) == 1
    assert active_for_day[0]["state"] == "weak"


def test_override_market_environment_resolves_new_override_inside_closed_interval(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-10",
                "end_date": "2026-05-20",
                "evaluated_at": "2026-05-10",
                "source": "scheduled",
                "manual_override": False,
                "reason": "broad rally",
            }
        ],
    )

    override_market_environment(
        tmp_path,
        pick_date="2026-05-15",
        state="weak",
        reason="panic break",
    )

    resolved = resolve_market_environment(tmp_path, pick_date="2026-05-15")

    assert resolved["state"] == "weak"
    assert resolved["interval_start"] == "2026-05-15"
    assert resolved["source"] == "manual_override"


def test_override_market_environment_replaces_closed_interval_at_start_boundary(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-10",
                "end_date": "2026-05-20",
                "evaluated_at": "2026-05-10",
                "source": "scheduled",
                "manual_override": False,
                "reason": "broad rally",
            }
        ],
    )

    override_market_environment(
        tmp_path,
        pick_date="2026-05-10",
        state="weak",
        reason="panic break",
    )

    intervals = load_environment_history(tmp_path)

    assert intervals == [
        {
            "state": "weak",
            "start_date": "2026-05-10",
            "end_date": None,
            "evaluated_at": "2026-05-10",
            "source": "manual_override",
            "manual_override": True,
            "reason": "panic break",
        }
    ]
    assert all(
        interval["end_date"] is None or interval["end_date"] >= interval["start_date"]
        for interval in intervals
    )

    resolved = resolve_market_environment(tmp_path, pick_date="2026-05-10")
    assert resolved["state"] == "weak"
    assert resolved["interval_start"] == "2026-05-10"
    assert resolved["source"] == "manual_override"


def test_override_market_environment_same_day_does_not_create_invalid_interval(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-19",
                "end_date": None,
                "evaluated_at": "2026-05-19",
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
    assert intervals == [
        {
            "state": "weak",
            "start_date": "2026-05-19",
            "end_date": None,
            "evaluated_at": "2026-05-19",
            "source": "manual_override",
            "manual_override": True,
            "reason": "panic break",
        }
    ]


def test_override_market_environment_repeated_same_day_resolves_to_latest_state(tmp_path: Path) -> None:
    override_market_environment(
        tmp_path,
        pick_date="2026-05-19",
        state="weak",
        reason="panic break",
    )

    override_market_environment(
        tmp_path,
        pick_date="2026-05-19",
        state="strong",
        reason="reversal rebound",
    )

    resolved = resolve_market_environment(tmp_path, pick_date="2026-05-19")

    assert resolved["state"] == "strong"
    assert resolved["reason"] == "reversal rebound"
    assert resolved["source"] == "manual_override"


def test_override_market_environment_same_day_keeps_single_active_interval(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "neutral",
                "start_date": "2026-05-19",
                "end_date": None,
                "evaluated_at": "2026-05-19",
                "source": "scheduled",
                "manual_override": False,
                "reason": "range-bound",
            }
        ],
    )

    override_market_environment(
        tmp_path,
        pick_date="2026-05-19",
        state="strong",
        reason="late breakout",
    )

    intervals = load_environment_history(tmp_path)
    active_for_day = [
        interval
        for interval in intervals
        if interval["start_date"] <= "2026-05-19" and (interval["end_date"] is None or "2026-05-19" <= interval["end_date"])
    ]

    assert len(active_for_day) == 1
    assert active_for_day[0]["state"] == "strong"
    assert active_for_day[0]["manual_override"] is True


def test_override_market_environment_creates_manual_interval_for_empty_history(tmp_path: Path) -> None:
    override_market_environment(
        tmp_path,
        pick_date="2026-05-19",
        state="weak",
        reason="panic break",
    )

    assert load_environment_history(tmp_path) == [
        {
            "state": "weak",
            "start_date": "2026-05-19",
            "end_date": None,
            "evaluated_at": "2026-05-19",
            "source": "manual_override",
            "manual_override": True,
            "reason": "panic break",
        }
    ]


def test_override_market_environment_preserves_boundary_resolution(tmp_path: Path) -> None:
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

    previous_day = resolve_market_environment(tmp_path, pick_date="2026-05-18")
    override_day = resolve_market_environment(tmp_path, pick_date="2026-05-19")

    assert previous_day["state"] == "strong"
    assert previous_day["interval_end"] == "2026-05-18"
    assert override_day["state"] == "weak"
    assert override_day["interval_start"] == "2026-05-19"
    assert override_day["source"] == "manual_override"


def test_evaluate_market_environment_keeps_uptrend_without_wave_confirmation_as_neutral() -> None:
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

    assert result["state"] == "neutral"
    assert result["total_score"] > 0
    assert result["indices"]["sse"]["trend"]["state"] == "Sx_mixed"
    assert result["indices"]["sse"]["macd"]["state"] == "M6_top_divergence_setup"
    assert "indices" in result


def test_evaluate_market_environment_treats_breakdown_with_bottom_divergence_setup_as_score_weak() -> None:
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
    assert result["score_based_state"] == "weak"
    assert result["rule_based_state"] == "neutral"
    assert result["vote_based_state"] == "weak"
    assert result["score_based_total"] == -14.0
    assert result["indices"]["sse"]["trend"]["state"] == "S10_weak"
    assert result["indices"]["sse"]["macd"]["state"] == "M2_bottom_divergence_setup"


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


def test_score_index_environment_frame_pivot_box_detection() -> None:
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

    assert result["box_volume"]["zone"] == "opportunity"
    assert result["box_volume"]["volume_up"] is True
    assert result["total_score"] == 1.0
    assert result["state_hint"] == "neutral"


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
        "box_volume": {
            "phase": "strong_box",
            "zone": "risk",
            "score": -1.0,
            "P": 100.0,
            "V": 100.0,
            "N": 100.0,
            "Q": "high_first",
            "volume_up": False,
        },
        "trend": {
            "state": "Sx_mixed",
            "score": 0.0,
            "bbi_slope": "up",
            "close_vs_zxdkx": "below",
            "ma25_vs_ma60": "above",
            "ma25_slope": "up",
            "ma60_slope": "down",
        },
        "macd": {
            "state": "M12_primary_advance",
            "score": 4.5,
            "golden_cross": True,
            "death_cross": False,
            "dea_sign": "above_zero",
            "dea_trend": "up",
            "hist_trend": "expand",
        },
        "total_score": 3.5,
        "state_hint": "neutral",
        "close": 101.0,
        "ma25": 100.04,
        "ma60": 100.017,
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
    assert result["total_score"] == 1.5
    assert result["indices"]["cn2000"]["trend"]["state"] == "S10_weak"
    assert result["indices"]["cn2000"]["state_hint"] == "neutral"


def test_combine_environment_state_promotes_underwater_golden_cross_to_strong() -> None:
    sse_score = {
        "box_volume": {"zone": "risk"},
        "trend": {"state": "S1_weak_to_strong_initial"},
        "macd": {"state": "M3_underwater_golden_cross"},
    }
    cn2000_score = {
        "box_volume": {"zone": "risk"},
        "trend": {"state": "Sx_mixed"},
        "macd": {"state": "M3_underwater_golden_cross"},
    }

    assert _combine_environment_state(sse_score=sse_score, cn2000_score=cn2000_score) == "strong"


def test_combine_environment_state_keeps_repair_window_neutral_even_if_trend_is_weak() -> None:
    sse_score = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S10_weak"},
        "macd": {"state": "M2_bottom_divergence_setup"},
    }
    cn2000_score = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S9_risk_increasing"},
        "macd": {"state": "M2_bottom_divergence_setup"},
    }

    assert _combine_environment_state(sse_score=sse_score, cn2000_score=cn2000_score) == "neutral"


def test_macd_component_marks_long_positive_shrink_streak_as_uptrend_exhausting() -> None:
    frame = pd.DataFrame(
        {
            "dif": [10.0, 9.5],
            "dea": [7.8, 8.2],
            "hist": [2.2, 1.3],
            "golden_cross": [False, False],
            "death_cross": [False, False],
            "hist_shrink_streak": [4, 5],
        }
    )

    result = _macd_component(frame)

    assert result["state"] == "M7_uptrend_exhausting"
    assert result["score"] == -1.0


def test_macd_component_keeps_underwater_post_cross_expansion_constructive() -> None:
    frame = pd.DataFrame(
        {
            "dif": [-42.6901, -37.3014],
            "dea": [-47.0016, -45.0615],
            "hist": [4.3115, 7.7601],
            "golden_cross": [True, False],
            "death_cross": [False, False],
            "hist_shrink_streak": [1, 1],
        }
    )

    result = _macd_component(frame)

    assert result["state"] == "M5_underwater_advance"
    assert result["score"] == 4.0


def test_macd_component_keeps_underwater_advance_for_recent_post_cross_expansion() -> None:
    frame = pd.DataFrame(
        {
            "dif": [-42.6901, -37.3014, -31.0547],
            "dea": [-47.0016, -45.0615, -42.2602],
            "hist": [4.3115, 7.7601, 11.2054],
            "golden_cross": [True, False, False],
            "death_cross": [False, False, False],
            "hist_shrink_streak": [1, 1, 1],
        }
    )

    result = _macd_component(frame)

    assert result["state"] == "M5_underwater_advance"
    assert result["score"] == 4.0


def test_macd_component_does_not_mark_first_positive_shrink_as_top_divergence_setup() -> None:
    frame = pd.DataFrame(
        {
            "dif": [90.1015, 113.2727],
            "dea": [-18.5392, 7.8232],
            "hist": [108.6407, 105.4495],
            "golden_cross": [False, False],
            "death_cross": [False, False],
            "hist_shrink_streak": [1, 2],
        }
    )

    result = _macd_component(frame)

    assert result["state"] == "M12_primary_advance"
    assert result["score"] == 4.5


def test_combine_environment_state_treats_mature_top_exhaustion_as_weak() -> None:
    sse_score = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S5_strong"},
        "macd": {"state": "M7_uptrend_exhausting"},
    }
    cn2000_score = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S5_strong"},
        "macd": {"state": "M7_uptrend_exhausting"},
    }

    assert _combine_environment_state(sse_score=sse_score, cn2000_score=cn2000_score) == "weak"


def test_combine_environment_state_keeps_single_m7_exhaustion_as_neutral() -> None:
    sse_score = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S5_strong"},
        "macd": {"state": "M7_uptrend_exhausting"},
    }
    cn2000_score = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S5_strong"},
        "macd": {"state": "M6_top_divergence_setup"},
    }

    assert _combine_environment_state(sse_score=sse_score, cn2000_score=cn2000_score) == "neutral"


def test_build_monthly_macd_bias_marks_underwater_monthly_repair_as_negative() -> None:
    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    close = [120.0 - idx * 0.25 for idx in range(220)] + [65.0 + idx * 0.35 for idx in range(40)]
    frame = pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "vol": [1000.0] * len(close),
        }
    )

    result = _build_monthly_macd_bias(frame, pick_date="2025-12-31")

    assert result["bias"] in {"negative", "repairing"}


def test_compute_raw_environment_state_downgrades_single_day_strong_when_monthly_bias_is_negative() -> None:
    sse_score = {
        "box_volume": {"zone": "risk"},
        "trend": {"state": "S1_weak_to_strong_initial"},
        "macd": {"state": "M3_underwater_golden_cross"},
    }
    cn2000_score = {
        "box_volume": {"zone": "risk"},
        "trend": {"state": "Sx_mixed"},
        "macd": {"state": "M3_underwater_golden_cross"},
    }

    result = _compute_raw_environment_state(
        sse_score=sse_score,
        cn2000_score=cn2000_score,
        sse_monthly_bias={"bias": "negative"},
        cn2000_monthly_bias={"bias": "negative"},
    )

    assert result == "neutral"


def test_apply_environment_state_machine_allows_direct_weak_to_strong_jump() -> None:
    result = _apply_environment_state_machine(
        previous_state="weak",
        raw_state="strong",
        consecutive_raw_counts={"strong": 2, "neutral": 0, "weak": 0},
        hard_strong_trigger=False,
        hard_weak_trigger=False,
    )

    assert result == "strong"


def test_apply_environment_state_machine_allows_direct_strong_to_weak_jump() -> None:
    result = _apply_environment_state_machine(
        previous_state="strong",
        raw_state="weak",
        consecutive_raw_counts={"strong": 0, "neutral": 0, "weak": 2},
        hard_strong_trigger=False,
        hard_weak_trigger=True,
    )

    assert result == "weak"


def test_apply_environment_state_machine_promotes_neutral_to_strong_without_confirmation() -> None:
    result = _apply_environment_state_machine(
        previous_state="neutral",
        raw_state="strong",
        consecutive_raw_counts={"strong": 1, "neutral": 0, "weak": 0},
        hard_strong_trigger=False,
        hard_weak_trigger=False,
    )

    assert result == "strong"


def test_apply_environment_state_machine_delays_strong_to_neutral_until_second_neutral_day() -> None:
    first = _apply_environment_state_machine(
        previous_state="strong",
        raw_state="neutral",
        consecutive_raw_counts={"strong": 0, "neutral": 1, "weak": 0},
        hard_strong_trigger=False,
        hard_weak_trigger=False,
    )
    second = _apply_environment_state_machine(
        previous_state="strong",
        raw_state="neutral",
        consecutive_raw_counts={"strong": 0, "neutral": 2, "weak": 0},
        hard_strong_trigger=False,
        hard_weak_trigger=False,
    )

    assert first == "strong"
    assert second == "neutral"


def test_apply_environment_state_machine_delays_weak_to_neutral_until_second_neutral_day() -> None:
    first = _apply_environment_state_machine(
        previous_state="weak",
        raw_state="neutral",
        consecutive_raw_counts={"strong": 0, "neutral": 1, "weak": 0},
        hard_strong_trigger=False,
        hard_weak_trigger=False,
    )
    second = _apply_environment_state_machine(
        previous_state="weak",
        raw_state="neutral",
        consecutive_raw_counts={"strong": 0, "neutral": 2, "weak": 0},
        hard_strong_trigger=False,
        hard_weak_trigger=False,
    )

    assert first == "weak"
    assert second == "neutral"


def test_smooth_environment_states_backfills_single_day_neutral_before_confirmed_strong() -> None:
    result = _smooth_environment_states(
        raw_states=["neutral", "strong", "strong"],
        hard_strong_triggers=[False, False, False],
        hard_weak_triggers=[False, False, False],
    )

    assert result == ["neutral", "strong", "strong"]


def test_smooth_environment_states_switches_directly_between_weak_and_strong() -> None:
    result = _smooth_environment_states(
        raw_states=["weak", "strong", "strong"],
        hard_strong_triggers=[False, False, False],
        hard_weak_triggers=[False, False, False],
    )

    assert result == ["weak", "strong", "strong"]


def test_smooth_environment_states_requires_two_neutral_days_before_leaving_strong() -> None:
    result = _smooth_environment_states(
        raw_states=["strong", "neutral", "neutral"],
        hard_strong_triggers=[False, False, False],
        hard_weak_triggers=[False, False, False],
    )

    assert result == ["strong", "strong", "neutral"]


def test_collapse_single_day_neutral_islands_fills_same_side_weak_gap() -> None:
    result = _collapse_single_day_neutral_islands(["weak", "neutral", "weak"])

    assert result == ["weak", "weak", "weak"]


def test_collapse_single_day_neutral_islands_keeps_transition_between_strong_and_weak() -> None:
    result = _collapse_single_day_neutral_islands(["strong", "neutral", "weak"])

    assert result == ["strong", "neutral", "weak"]


def test_box_volume_component_uses_right_to_left_pivot_order_for_q() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=65, freq="B"),
            "open": [100.0] * 65,
            "high": [100.0] * 65,
            "low": [100.0] * 65,
            "close": [100.0] * 65,
            "vol": [1000.0] * 65,
        }
    )
    phase_high_values = [110.0] * 60
    phase_low_values = [90.0] * 60
    phase_high_values[10] = 120.0
    phase_high_values[45] = 118.0
    phase_low_values[20] = 80.0
    phase_low_values[50] = 82.0
    frame.loc[5:, "high"] = phase_high_values
    frame.loc[5:, "low"] = phase_low_values
    frame.loc[64, "open"] = 101.0
    frame.loc[64, "close"] = 101.5

    result = _box_volume_component(frame)

    assert result["Q"] == "low_first"
    assert result["phase"] == "weak_box"


def test_box_volume_component_returns_zero_for_high_first_else_branch() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=65, freq="B"),
            "open": [100.0] * 65,
            "high": [100.0] * 65,
            "low": [100.0] * 65,
            "close": [100.0] * 65,
            "vol": [1000.0] * 65,
        }
    )
    phase_high_values = [110.0] * 60
    phase_low_values = [90.0] * 60
    phase_high_values[45] = 120.0
    phase_low_values[15] = 80.0
    frame.loc[5:, "high"] = phase_high_values
    frame.loc[5:, "low"] = phase_low_values
    frame.loc[39, "vol"] = 5000.0
    frame.loc[39, "open"] = 80.0
    frame.loc[64, "open"] = 101.0
    frame.loc[64, "close"] = 102.0

    result = _box_volume_component(frame)

    assert result["Q"] == "high_first"
    assert result["zone"] == "risk"
    assert result["score"] == -1.0


def test_box_volume_component_returns_zero_for_weak_first_else_branch() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=65, freq="B"),
            "open": [100.0] * 65,
            "high": [100.0] * 65,
            "low": [100.0] * 65,
            "close": [100.0] * 65,
            "vol": [1000.0] * 65,
        }
    )
    phase_high_values = [110.0] * 60
    phase_low_values = [90.0] * 60
    phase_low_values[45] = 80.0
    phase_high_values[15] = 120.0
    frame.loc[5:, "high"] = phase_high_values
    frame.loc[5:, "low"] = phase_low_values
    frame.loc[39, "vol"] = 5000.0
    frame.loc[39, "open"] = 130.0
    frame.loc[64, "open"] = 150.0
    frame.loc[64, "close"] = 151.0

    result = _box_volume_component(frame)

    assert result["Q"] == "low_first"
    assert result["zone"] == "neutral"
    assert result["score"] == 0.0


def test_score_based_environment_state_uses_combined_thresholds() -> None:
    assert _score_based_environment_state(combined_total=19.0) == "strong"
    assert _score_based_environment_state(combined_total=8.0) == "neutral"
    assert _score_based_environment_state(combined_total=-10.0) == "weak"


def test_diagnostic_macd_environment_state_treats_m7_as_neutral() -> None:
    score = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S5_strong"},
        "macd": {"state": "M7_uptrend_exhausting"},
    }

    assert _diagnostic_macd_environment_state(score) == "neutral"


def test_diagnostic_macd_environment_state_requires_structure_or_risk_for_m8_and_m9() -> None:
    m8_neutral = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S5_strong"},
        "macd": {"state": "M8_above_water_dead_cross"},
    }
    m8_weak = {
        "box_volume": {"zone": "risk"},
        "trend": {"state": "S5_strong"},
        "macd": {"state": "M8_above_water_dead_cross"},
    }
    m9_neutral = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S5_strong"},
        "macd": {"state": "M9_pullback"},
    }
    m9_weak = {
        "box_volume": {"zone": "opportunity"},
        "trend": {"state": "S6_strong_to_weak_initial"},
        "macd": {"state": "M9_pullback"},
    }

    assert _diagnostic_macd_environment_state(m8_neutral) == "neutral"
    assert _diagnostic_macd_environment_state(m8_weak) == "weak"
    assert _diagnostic_macd_environment_state(m9_neutral) == "neutral"
    assert _diagnostic_macd_environment_state(m9_weak) == "weak"


def test_vote_based_environment_state_uses_three_dimension_majority() -> None:
    sse_score = {
        "box_volume": {"zone": "opportunity", "score": 1.0},
        "trend": {"state": "S5_strong", "score": 4.0},
        "macd": {"state": "M7_uptrend_exhausting", "score": -1.0},
    }
    cn2000_score = {
        "box_volume": {"zone": "opportunity", "score": 1.0},
        "trend": {"state": "S5_strong", "score": 4.0},
        "macd": {"state": "M6_top_divergence_setup", "score": 1.0},
    }

    assert _vote_based_environment_state(sse_score=sse_score, cn2000_score=cn2000_score) == "strong"


def test_evaluate_market_environment_returns_score_and_diagnostic_states() -> None:
    dates = pd.date_range("2026-01-05", periods=120, freq="B")
    sse = pd.DataFrame(
        {
            "ts_code": ["000001.SH"] * len(dates),
            "trade_date": dates,
            "open": [100.0 + i * 0.8 for i in range(len(dates))],
            "high": [101.0 + i * 0.8 for i in range(len(dates))],
            "low": [99.0 + i * 0.8 for i in range(len(dates))],
            "close": [100.5 + i * 0.8 for i in range(len(dates))],
            "vol": [1000.0 + i * 8 for i in range(len(dates))],
        }
    )
    cn2000 = sse.assign(ts_code="399303.SZ", close=[130.0 + i * 1.1 for i in range(len(dates))])

    result = evaluate_market_environment(
        pick_date=dates[-1].strftime("%Y-%m-%d"),
        sse_history=sse,
        cn2000_history=cn2000,
    )

    assert result["state"] == result["score_based_state"]
    assert "rule_based_state" in result
    assert "vote_based_state" in result
    assert "score_thresholds" in result
    assert result["score_based_total"] == result["total_score"]
