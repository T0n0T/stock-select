import pandas as pd

from stock_select.analysis.macd_waves import classify_weekly_macd_trend


def test_classify_weekly_macd_trend_excludes_future_week_friday_for_midweek_pick() -> None:
    # Regression: W-FRI resample labels a partial Monday/Tuesday week as the coming Friday.
    # For a Monday pick date, that future-labeled partial week must not enter MACD calculation,
    # otherwise 2026-04-20 would be scored with a synthetic 2026-04-24 weekly close.
    dates = pd.bdate_range("2025-01-03", periods=90)
    close = [10.0 + idx * 0.1 for idx in range(len(dates))]
    frame = pd.DataFrame({"trade_date": dates, "close": close})

    pick_date = "2025-04-21"
    result_midweek = classify_weekly_macd_trend(frame, pick_date=pick_date)
    result_previous_friday = classify_weekly_macd_trend(frame, pick_date="2025-04-18")

    assert result_midweek.metrics == result_previous_friday.metrics
    assert result_midweek.phase == result_previous_friday.phase
