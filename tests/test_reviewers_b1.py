import pandas as pd
import pytest

from stock_select.reviewers import b1 as b1_reviewer
from stock_select.reviewers.b1 import review_b1_symbol_history


_MULTI_TIMEFRAME_CONFIRMATION_POINTS = 40


def _first_non_fallback_periods(end: str = "2026-04-30") -> int:
    for periods in range(_MULTI_TIMEFRAME_CONFIRMATION_POINTS, 1600):
        trade_dates = pd.bdate_range(end=end, periods=periods)
        weekly_closes = pd.Series(range(len(trade_dates)), index=trade_dates).resample("W-FRI").last().dropna()
        monthly_closes = pd.Series(range(len(trade_dates)), index=trade_dates).resample("ME").last().dropna()
        if len(weekly_closes) >= _MULTI_TIMEFRAME_CONFIRMATION_POINTS and len(monthly_closes) >= _MULTI_TIMEFRAME_CONFIRMATION_POINTS:
            return periods
    msg = "could not find non-fallback periods"
    raise AssertionError(msg)


def _constructive_b1_history() -> pd.DataFrame:
    tail = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=170),
            "open": [10.0] * 150
            + [
                12.4,
                12.8,
                13.2,
                13.4,
                13.1,
                12.9,
                12.8,
                12.85,
                12.95,
                13.1,
                13.2,
                13.3,
                13.35,
                13.4,
                13.5,
                13.55,
                13.6,
                13.65,
                13.7,
                13.8,
            ],
            "high": [10.2] * 150
            + [
                12.9,
                13.2,
                13.5,
                13.6,
                13.2,
                13.0,
                12.95,
                13.0,
                13.1,
                13.25,
                13.35,
                13.45,
                13.5,
                13.55,
                13.65,
                13.7,
                13.75,
                13.8,
                13.9,
                14.0,
            ],
            "low": [9.8] * 150
            + [
                12.1,
                12.6,
                13.0,
                13.0,
                12.8,
                12.7,
                12.7,
                12.8,
                12.9,
                13.0,
                13.1,
                13.2,
                13.25,
                13.3,
                13.35,
                13.4,
                13.45,
                13.5,
                13.6,
                13.7,
            ],
            "close": [10.0] * 150
            + [
                12.7,
                13.0,
                13.3,
                13.1,
                12.95,
                12.85,
                12.82,
                12.9,
                13.02,
                13.15,
                13.25,
                13.35,
                13.4,
                13.45,
                13.55,
                13.6,
                13.65,
                13.72,
                13.82,
                13.95,
            ],
            "vol": [900.0] * 150
            + [
                2500.0,
                3100.0,
                3600.0,
                2200.0,
                1400.0,
                1200.0,
                1100.0,
                1150.0,
                1180.0,
                1300.0,
                1320.0,
                1350.0,
                1380.0,
                1400.0,
                1450.0,
                1500.0,
                1520.0,
                1550.0,
                1600.0,
                1680.0,
            ],
        }
    )
    prefix_periods = _first_non_fallback_periods() - len(tail)
    prefix_dates = pd.bdate_range(end=tail["trade_date"].iloc[0] - pd.offsets.BDay(1), periods=prefix_periods)
    prefix = pd.DataFrame(
        {
            "trade_date": prefix_dates,
            "open": [10.0] * prefix_periods,
            "high": [10.2] * prefix_periods,
            "low": [9.8] * prefix_periods,
            "close": [10.0] * prefix_periods,
            "vol": [900.0] * prefix_periods,
        }
    )
    return pd.concat([prefix, tail], ignore_index=True)


def test_b1_review_keeps_schema_stable_without_extra_reasoning_fields() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "macd_reasoning" not in review
    assert "signal_reasoning" not in review


def test_b1_review_comment_mentions_weekly_and_daily_waves() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "周线" in review["comment"]
    assert "日线" in review["comment"]
    assert "b1" in review["comment"]


def test_b1_review_counts_macd_phase_in_total_score() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    score_without_macd = round(
        review["trend_structure"] * 0.225
        + review["price_position"] * 0.225
        + review["volume_behavior"] * 0.30
        + review["previous_abnormal_move"] * 0.25,
        2,
    )
    assert review["total_score"] != score_without_macd


def test_b1_review_caps_invalid_daily_wave_below_pass_band() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "日线MACD" in review["comment"]
    assert review["macd_phase"] <= 4.5
    assert review["verdict"] != "PASS"


def test_b1_trend_structure_rewards_pullback_to_zxdkx_with_rising_ma25_and_zxdkx() -> None:
    close = pd.Series([10.0] * 30)
    open_ = pd.Series([10.0] * 30)
    ma25 = pd.Series([10.6 + idx * 0.01 for idx in range(30)])
    zxdkx = pd.Series([9.6 + idx * 0.01 for idx in range(30)])
    bbi = ma25 + 0.4

    score = b1_reviewer._score_b1_trend_structure(open_=open_, close=close, ma25=ma25, zxdkx=zxdkx, bbi=bbi)

    assert score == 5.0


def test_b1_trend_structure_scores_three_for_price_above_ma25_with_ma25_above_zxdkx() -> None:
    close = pd.Series([10.0 + idx * 0.1 for idx in range(30)])
    open_ = close + 0.1
    ma25 = close - 0.8
    zxdkx = ma25 - 0.4
    bbi = ma25 - 0.1

    score = b1_reviewer._score_b1_trend_structure(open_=open_, close=close, ma25=ma25, zxdkx=zxdkx, bbi=bbi)

    assert score == 3.0


def test_b1_price_position_uses_deeper_box_pullback_as_better_odds() -> None:
    low_box = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 12.0, 11.5, 11.0])
    high_box = low_box + 1.0
    close = pd.Series([10.5, 11.5, 12.5, 13.5, 14.5, 12.5, 11.8, 11.2])
    ma25 = pd.Series([12.0] * len(close))
    zxdq = pd.Series([11.6] * len(close))

    score = b1_reviewer._score_b1_price_position(close=close, high=high_box, low=low_box, ma25=ma25, zxdq=zxdq)

    assert score == 5.0


def test_b1_price_position_keeps_high_position_observable_when_ma25_holds_zxdq() -> None:
    low = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    high = pd.Series([11.0, 12.0, 13.0, 14.0, 15.0])
    close = pd.Series([10.5, 11.5, 12.5, 13.5, 14.2])
    ma25 = pd.Series([13.0] * len(close))
    zxdq = pd.Series([12.7] * len(close))

    score = b1_reviewer._score_b1_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq)

    assert score == 3.0


def test_b1_volume_behavior_scores_peak_bullish_and_pullback_volume_expansion() -> None:
    open_ = pd.Series([10.0] * 20)
    close = pd.Series([10.2] * 20)
    volume = pd.Series([1000.0] * 20)
    volume.iloc[5] = 3600.0
    volume.iloc[-3:] = [1200.0, 1400.0, 1600.0]
    close.iloc[-3:] = [10.0, 9.9, 9.8]

    score = b1_reviewer._score_b1_volume_behavior(open_=open_, close=close, volume=volume)

    assert score == 5.0


def test_b1_volume_behavior_treats_any_pullback_expansion_as_support() -> None:
    open_ = pd.Series([10.0] * 20)
    close = pd.Series([10.2] * 20)
    volume = pd.Series([1000.0] * 20)
    volume.iloc[5] = 1760.0
    close.iloc[-3:] = [9.9, 9.8, 9.7]
    volume.iloc[-3:] = [1000.0, 1100.0, 950.0]

    score = b1_reviewer._score_b1_volume_behavior(open_=open_, close=close, volume=volume)

    assert score == 4.0


def test_b1_volume_behavior_scores_four_for_large_bearish_peak_with_pullback_volume_expansion() -> None:
    open_ = pd.Series([10.0] * 20)
    close = pd.Series([10.2] * 20)
    volume = pd.Series([1000.0] * 20)
    open_.iloc[5] = 10.5
    close.iloc[5] = 10.0
    volume.iloc[5] = 4800.0
    volume.iloc[-3:] = [1200.0, 1400.0, 1600.0]
    close.iloc[-3:] = [10.0, 9.9, 9.8]

    score = b1_reviewer._score_b1_volume_behavior(open_=open_, close=close, volume=volume)

    assert score == 4.0


def test_b1_macd_phase_rewards_weekly_red_histogram_above_water_without_divergence() -> None:
    score = b1_reviewer._score_b1_macd_phase(
        history_len=80,
        weekly_macd=b1_reviewer.B1WeeklyMacdContext(
            red_histogram=True,
            above_water=True,
            diverging=False,
            improving=True,
        ),
        daily_recent_death_cross=False,
    )

    assert score == 5.0


def test_b1_macd_phase_penalizes_recent_three_day_daily_death_cross() -> None:
    score = b1_reviewer._score_b1_macd_phase(
        history_len=80,
        weekly_macd=b1_reviewer.B1WeeklyMacdContext(
            red_histogram=True,
            above_water=True,
            diverging=False,
            improving=True,
        ),
        daily_recent_death_cross=True,
    )

    assert score == 2.0


def test_b1_macd_phase_scores_one_when_weekly_histogram_is_not_red() -> None:
    score = b1_reviewer._score_b1_macd_phase(
        history_len=80,
        weekly_macd=b1_reviewer.B1WeeklyMacdContext(
            red_histogram=False,
            above_water=True,
            diverging=False,
            improving=False,
        ),
        daily_recent_death_cross=False,
    )

    assert score == 1.0


def test_b1_review_uses_precomputed_zx_fields_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    history = _constructive_b1_history()
    history["ma25"] = 14.5
    history["zxdq"] = 14.2
    history["zxdkx"] = 13.7
    history["bbi"] = 14.8

    monkeypatch.setattr(
        b1_reviewer,
        "classify_weekly_macd_trend",
        lambda frame, pick_date: type("Trend", (), {"phase": "rising", "is_rising_initial": False, "is_top_divergence": False})(),
    )
    monkeypatch.setattr(
        b1_reviewer,
        "classify_daily_macd_trend",
        lambda frame, pick_date: type("Trend", (), {"phase": "rising", "is_rising_initial": True, "is_top_divergence": False})(),
    )

    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review["trend_structure"] == 5.0
    assert "N型回调" in review["comment"]
    assert "超卖" in review["comment"]
