from __future__ import annotations

import pandas as pd

from stock_select.strategies.hcr import (
    compute_hcr_reference_price,
    compute_hcr_yx,
    prepare_hcr_frame,
    run_hcr_screen_with_stats,
    score_hcr_candidate,
)


def test_compute_hcr_yx_uses_30_bar_high_low_midpoint() -> None:
    frame = pd.DataFrame(
        {
            "high": [10.0 + idx * 0.1 for idx in range(30)],
            "low": [9.0 + idx * 0.1 for idx in range(30)],
        }
    )

    yx = compute_hcr_yx(frame)

    assert round(float(yx.iloc[-1]), 4) == 10.95


def test_compute_hcr_reference_price_uses_const_ref_hhv_180_shift_60_semantics() -> None:
    highs = [10.0] * 239 + [12.0]
    frame = pd.DataFrame({"high": highs})

    reference = compute_hcr_reference_price(frame)

    assert reference.notna().all()
    assert float(reference.iloc[0]) == 10.0
    assert float(reference.iloc[-1]) == 10.0
    assert reference.nunique(dropna=True) == 1


def test_prepare_hcr_frame_adds_pool_moving_averages() -> None:
    close = [float(idx) for idx in range(1, 61)]
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2026-01-01", periods=60),
            "high": [value + 0.5 for value in close],
            "low": [value - 0.5 for value in close],
            "close": close,
        }
    )

    prepared = prepare_hcr_frame(frame)

    assert "ma25" in prepared.columns
    assert "ma60" in prepared.columns
    assert float(prepared["ma25"].iloc[-1]) > float(prepared["ma60"].iloc[-1])


def test_run_hcr_screen_with_stats_selects_symbol_when_resonance_and_breakout_pass() -> None:
    pick_date = pd.Timestamp("2026-04-01")
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-10-17", periods=380),
            "open": [9.8] * 380,
            "high": [10.2] * 350 + [10.4] * 30,
            "low": [9.6] * 350 + [9.8] * 30,
            "close": [9.9] * 379 + [10.25],
            "volume": [100.0] * 380,
            "turnover_n": [1000.0] * 380,
        }
    )
    frame = prepare_hcr_frame(frame)
    frame.loc[frame.index[-1], "p"] = frame.loc[frame.index[-1], "yx"] * 1.004
    frame.loc[frame.index[-1], "resonance_gap_pct"] = abs(
        frame.loc[frame.index[-1], "yx"] - frame.loc[frame.index[-1], "p"]
    ) / frame.loc[frame.index[-1], "p"]

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_hcr_screen_with_stats(frame, pick_date=pick_date)

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert stats["selected"] == 1


def test_run_hcr_screen_with_stats_counts_insufficient_history_separately() -> None:
    pick_date = pd.Timestamp("2026-03-11")
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2026-01-01", periods=50),
            "open": [9.8] * 50,
            "high": [10.2] * 50,
            "low": [9.6] * 50,
            "close": [10.1] * 50,
            "volume": [100.0] * 50,
            "turnover_n": [1000.0] * 50,
        }
    )
    frame = prepare_hcr_frame(frame)
    frame["ts_code"] = "000001.SZ"

    _candidates, stats = run_hcr_screen_with_stats(frame, pick_date=pick_date)

    assert stats["eligible"] == 1
    assert stats["fail_insufficient_history"] == 1
    assert stats["fail_resonance"] == 0


def test_run_hcr_screen_with_stats_rejects_gap_above_half_percent() -> None:
    pick_date = pd.Timestamp("2026-04-01")
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-10-17", periods=380),
            "open": [9.8] * 380,
            "high": [10.2] * 350 + [10.4] * 30,
            "low": [9.6] * 350 + [9.8] * 30,
            "close": [9.9] * 379 + [10.25],
            "volume": [100.0] * 380,
            "turnover_n": [1000.0] * 380,
        }
    )
    frame = prepare_hcr_frame(frame)
    frame.loc[frame.index[-1], "p"] = 10.0
    frame.loc[frame.index[-1], "yx"] = 10.06
    frame.loc[frame.index[-1], "resonance_gap_pct"] = 0.006

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_hcr_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_resonance"] == 1
    assert stats["selected"] == 0


def test_run_hcr_screen_with_stats_requires_exact_pick_date_match() -> None:
    pick_date = pd.Timestamp("2026-04-01")
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2026-01-01", periods=50),
            "open": [9.8] * 50,
            "high": [10.2] * 50,
            "low": [9.6] * 50,
            "close": [10.1] * 50,
            "volume": [100.0] * 50,
            "turnover_n": [1000.0] * 50,
        }
    )
    frame = prepare_hcr_frame(frame)
    frame["ts_code"] = "000001.SZ"

    candidates, stats = run_hcr_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["eligible"] == 0
    assert stats["fail_insufficient_history"] == 0


def test_score_hcr_candidate_rewards_april_sweet_spot_and_penalizes_overheat() -> None:
    sweet = pd.Series(
        {
            "open": 108.0,
            "close": 110.0,
            "ma25": 100.0,
            "ma60": 95.0,
            "turnover_n": 600_000_000.0,
            "resonance_gap_pct": 0.001,
        }
    )
    overheated = pd.Series(
        {
            "open": 118.0,
            "close": 122.0,
            "ma25": 100.0,
            "ma60": 88.0,
            "turnover_n": 600_000_000.0,
            "resonance_gap_pct": 0.001,
        }
    )

    assert score_hcr_candidate(sweet) > score_hcr_candidate(overheated)


def test_score_hcr_candidate_penalizes_two_day_acceleration() -> None:
    normal = pd.Series(
        {
            "open": 108.0,
            "close": 110.0,
            "ma25": 100.0,
            "ma60": 95.0,
            "turnover_n": 600_000_000.0,
            "resonance_gap_pct": 0.001,
        }
    )
    accelerated = pd.Series(
        {
            "open": 104.0,
            "close": 110.0,
            "ma25": 100.0,
            "ma60": 95.0,
            "turnover_n": 600_000_000.0,
            "resonance_gap_pct": 0.001,
        }
    )

    assert score_hcr_candidate(normal, previous_close=105.0) > score_hcr_candidate(
        accelerated,
        previous_close=105.0,
    )


def test_run_hcr_screen_with_stats_sorts_by_hcr_score_before_turnover() -> None:
    pick_date = pd.Timestamp("2026-04-01")
    dates = pd.bdate_range("2024-10-17", periods=380)

    def _frame(*, close: float, ma25: float, ma60: float, turnover: float) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "trade_date": dates,
                "open": [close * 0.99] * 380,
                "high": [10.2] * 350 + [10.4] * 30,
                "low": [9.6] * 350 + [9.8] * 30,
                "close": [close] * 380,
                "volume": [100.0] * 380,
                "turnover_n": [turnover] * 380,
            }
        )
        frame = prepare_hcr_frame(frame)
        frame.loc[frame.index[-1], "p"] = 10.0
        frame.loc[frame.index[-1], "yx"] = 10.0
        frame.loc[frame.index[-1], "resonance_gap_pct"] = 0.001
        frame.loc[frame.index[-1], "ma25"] = ma25
        frame.loc[frame.index[-1], "ma60"] = ma60
        frame.loc[frame.index[-1], "close"] = close
        frame.loc[frame.index[-1], "turnover_n"] = turnover
        return frame

    sweet = _frame(close=110.0, ma25=100.0, ma60=95.0, turnover=200_000_000.0)
    sweet["ts_code"] = "SWEET.SZ"
    hot = _frame(close=122.0, ma25=100.0, ma60=88.0, turnover=2_000_000_000.0)
    hot["ts_code"] = "HOT.SZ"

    candidates, stats = run_hcr_screen_with_stats(
        pd.concat([sweet, hot], ignore_index=True), pick_date=pick_date
    )

    assert stats["selected"] == 2
    assert [item["code"] for item in candidates] == ["SWEET.SZ", "HOT.SZ"]
    assert candidates[0]["hcr_score"] > candidates[1]["hcr_score"]
