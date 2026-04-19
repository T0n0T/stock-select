import pandas as pd

from stock_select.analysis.macd_waves import (
    classify_daily_macd_wave,
    classify_weekly_macd_wave,
)


def _frame_with_close(close: list[float], *, start: str = "2026-01-05") -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=len(close))
    return pd.DataFrame({"trade_date": dates, "close": close})


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


def test_classify_daily_macd_wave_invalidates_wave4_when_third_wave_gain_exceeds_30_pct() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.7, 9.5, 9.8, 10.2, 10.6, 11.0, 10.6, 10.3, 10.5, 11.0, 11.8, 12.9, 13.6, 13.2, 12.9, 12.7, 12.8]
    )

    result = classify_daily_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "invalid"
    assert result.details["third_wave_gain"] > 0.30


def test_classify_weekly_macd_wave_returns_invalid_for_churn() -> None:
    frame = _frame_with_close(
        [10.0, 10.2, 9.9, 10.1, 9.8, 10.0, 9.85, 10.05, 9.9, 10.1] * 8
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-04-10")

    assert result.label == "invalid"
