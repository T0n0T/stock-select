import pandas as pd

from stock_select.analysis.macd_waves import (
    _classify_macd_trend_from_lines,
    classify_daily_macd_state,
    classify_daily_macd_wave,
    classify_weekly_macd_wave,
)


def _frame_with_close(close: list[float], *, start: str = "2026-01-05") -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=len(close))
    return pd.DataFrame({"trade_date": dates, "close": close})


def _frame_from_weekly_close(weekly_close: list[float], *, start: str = "2025-01-03") -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=len(weekly_close), freq="W-FRI")
    return pd.DataFrame({"trade_date": dates, "close": weekly_close})


def _line_frame(dif: list[float], dea: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"dif": dif, "dea": dea})


def test_macd_trend_waits_for_both_lines_above_zero_after_underwater_cross() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, -0.12, -0.04],
            dea=[-0.28, -0.24, -0.16, -0.08],
        )
    )

    assert result.phase == "idle"
    assert result.direction == "neutral"
    assert result.reason == "waiting for both MACD lines above zero"


def test_macd_trend_enters_rising_after_underwater_cross_and_both_lines_above_zero() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, -0.12, 0.03, 0.08],
            dea=[-0.28, -0.24, -0.16, 0.01, 0.04],
        )
    )

    assert result.phase == "rising"
    assert result.direction == "rising"
    assert result.phase_index == 1
    assert result.bars_in_phase == 2
    assert result.is_rising_initial is True


def test_macd_trend_alternates_between_rising_and_falling_above_water() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.06, 0.05, 0.07],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.07, 0.06, 0.055],
        )
    )

    assert result.phase == "rising"
    assert result.direction == "rising"
    assert result.phase_index == 3
    assert result.bars_in_phase == 1


def test_macd_trend_marks_ended_when_dif_crosses_below_zero() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.02, -0.01],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.01, 0.005],
        )
    )

    assert result.phase == "ended"
    assert result.direction == "neutral"
    assert result.reason == "DIF crossed below zero"


def test_macd_trend_uses_latest_cycle_after_prior_cycle_ended() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, -0.01, -0.20, -0.12, 0.02, 0.06],
            dea=[-0.28, -0.24, 0.01, 0.00, -0.18, -0.14, 0.01, 0.03],
        )
    )

    assert result.phase == "rising"
    assert result.phase_index == 1
    assert result.bars_in_phase == 2


def test_macd_trend_stays_ended_when_next_startup_has_not_reached_zero_axis() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, -0.01, -0.20, -0.12, -0.08],
            dea=[-0.28, -0.24, 0.01, 0.00, -0.18, -0.14, -0.10],
        )
    )

    assert result.phase == "ended"
    assert result.reason == "DIF crossed below zero"


def test_macd_trend_flags_top_divergence_when_rising_spread_shrinks() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.09, 0.10],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.07],
        )
    )

    assert result.phase == "rising"
    assert result.metrics["spread"] == 0.03
    assert result.metrics["previous_spread"] == 0.05
    assert result.is_top_divergence is True


def test_classify_weekly_macd_wave_returns_wave1_for_first_constructive_advance() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.1, 10.4, 10.8, 11.2, 11.6, 12.0, 12.3, 12.6, 12.9]
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "wave1"
    assert "golden cross" in result.reason.lower()


def test_classify_weekly_macd_wave_returns_wave2_for_confirmed_pullback() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.2, 10.6, 11.0, 11.4, 11.7, 11.5, 11.2, 10.9, 10.6, 10.4, 10.3]
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "wave2"


def test_classify_daily_macd_wave_returns_wave2_end_for_left_side_pullback() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.1, 10.4, 10.8, 11.1, 11.4, 11.2, 11.0, 10.9, 10.92, 10.97, 11.02]
    )

    result = classify_daily_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "wave2_end"
    assert result.details["needs_recross"] is False


def test_classify_daily_macd_state_returns_wave2_end_valid_for_left_side_pullback() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.1, 10.4, 10.8, 11.1, 11.4, 11.2, 11.0, 10.9, 10.92, 10.97, 11.02]
    )

    result = classify_daily_macd_state(frame, pick_date="2026-03-31")

    assert result.state == "wave2_end_valid"
    assert result.valid_for_pullback is True


def test_classify_daily_macd_state_returns_overextended_when_wave4_shape_exceeds_30_pct_gain() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.7, 9.5, 9.8, 10.2, 10.6, 11.0, 10.6, 10.3, 10.5, 11.0, 11.8, 12.9, 13.6, 13.2, 12.9, 12.7, 12.8]
    )

    result = classify_daily_macd_state(frame, pick_date="2026-03-31")

    assert result.state == "overextended"
    assert result.metrics["third_wave_gain"] > 0.30


def test_classify_daily_macd_state_returns_deteriorating_when_pullback_keeps_worsening() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.3, 10.8, 11.3, 11.9, 12.4, 12.8, 13.0, 12.8, 12.5, 12.0, 11.5, 11.0, 10.6, 10.1]
    )

    result = classify_daily_macd_state(frame, pick_date="2026-04-03")

    assert result.state == "deteriorating"
    assert result.valid_for_pullback is False


def test_classify_daily_macd_wave_invalidates_wave4_when_third_wave_gain_exceeds_30_pct() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.7, 9.5, 9.8, 10.2, 10.6, 11.0, 10.6, 10.3, 10.5, 11.0, 11.8, 12.9, 13.6, 13.2, 12.9, 12.7, 12.8]
    )

    result = classify_daily_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "invalid"
    assert result.details["third_wave_gain"] > 0.30


def test_classify_daily_macd_wave_invalidates_negative_converging_pullback_above_30_pct() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.7, 9.5, 9.8, 10.2, 10.7, 11.2, 11.8, 12.4, 13.0, 13.4, 13.0, 12.6, 12.2, 11.9, 11.7, 11.6, 11.58, 11.57]
    )

    result = classify_daily_macd_wave(frame, pick_date="2026-04-10")

    assert result.label == "invalid"
    assert result.details["third_wave_gain"] > 0.30


def test_classify_weekly_macd_wave_prefers_wave2_for_fading_bullish_pullback_before_wave3() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.6, 9.4, 9.3, 9.5, 9.9, 10.4, 10.9, 11.4, 11.8, 12.1, 12.4, 12.1, 11.8, 11.5, 11.2, 11.0, 10.9, 10.85, 10.8]
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-04-10")

    assert result.label == "wave2"


def test_classify_weekly_macd_wave_returns_invalid_for_churn() -> None:
    frame = _frame_with_close(
        [10.0, 10.2, 9.9, 10.1, 9.8, 10.0, 9.85, 10.05, 9.9, 10.1] * 8
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-04-10")

    assert result.label == "invalid"


def test_classify_weekly_macd_wave_ignores_churn_outside_recent_six_month_window() -> None:
    frame = _frame_from_weekly_close(
        [10.0, 12.0, 9.0, 11.0, 8.0, 10.0, 12.0, 9.0, 11.0, 8.0, 10.0, 12.0, 9.0, 11.0]
        + [11.2, 11.4, 11.6, 11.8, 12.0, 12.2, 12.5, 12.8, 13.1, 13.4, 13.8, 14.2, 14.6, 15.0, 15.5, 16.0, 16.6, 17.2, 17.9, 18.6, 19.4, 20.2, 21.1, 22.0, 23.0, 24.0]
    )

    result = classify_weekly_macd_wave(frame, pick_date=str(frame["trade_date"].iloc[-1].date()))

    assert result.label == "wave1"


def test_classify_weekly_macd_wave_defaults_to_wave1_when_recent_window_has_no_underwater_cross() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [10.1, 10.2, 10.3, 10.4, 10.6, 10.8, 11.0, 11.3, 11.7, 12.1, 12.6, 13.2]
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "wave1"
