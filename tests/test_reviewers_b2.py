import pandas as pd

from stock_select.reviewers.b2 import review_b2_symbol_history


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


def _constructive_b2_history() -> pd.DataFrame:
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


def _damaged_b2_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=170),
            "open": [16.0 - idx * 0.02 for idx in range(170)],
            "high": [16.2 - idx * 0.02 for idx in range(170)],
            "low": [15.7 - idx * 0.02 for idx in range(170)],
            "close": [15.9 - idx * 0.02 for idx in range(170)],
            "vol": [1000.0 + idx * 12.0 for idx in range(170)],
        }
    )


def test_b2_review_prefers_shrink_on_retest_structure_with_exact_scores() -> None:
    review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review["code"] == "000001.SZ"
    assert review["pick_date"] == "2026-04-30"
    assert review["chart_path"] == "/tmp/000001.SZ_day.png"
    assert review["review_type"] == "baseline"
    assert review["trend_structure"] == 4.0
    assert review["price_position"] == 5.0
    assert review["volume_behavior"] == 5.0
    assert review["previous_abnormal_move"] == 5.0
    assert review["macd_phase"] == 2.0
    assert review["total_score"] == 4.22
    assert review["signal_type"] == "trend_start"
    assert review["verdict"] == "PASS"
    assert "周线MACD等待启动" in review["comment"]
    assert "日线MACD等待启动" in review["comment"]
    assert "wave" not in review["comment"]


def test_b2_review_penalizes_distribution_damage_with_exact_scores() -> None:
    review = review_b2_symbol_history(
        code="000002.SZ",
        pick_date="2026-04-30",
        history=_damaged_b2_history(),
        chart_path="/tmp/000002.SZ_day.png",
    )

    assert review["code"] == "000002.SZ"
    assert review["trend_structure"] == 1.0
    assert review["price_position"] == 2.0
    assert review["volume_behavior"] == 1.0
    assert review["previous_abnormal_move"] == 2.0
    assert review["macd_phase"] == 2.0
    assert review["total_score"] == 1.58
    assert review["signal_type"] == "distribution_risk"
    assert review["verdict"] == "FAIL"
    assert "周线MACD等待启动" in review["comment"]
    assert "日线MACD等待启动" in review["comment"]
    assert "三浪" not in review["comment"]


def test_b2_review_keeps_schema_stable_without_extra_reasoning_fields() -> None:
    review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "macd_reasoning" not in review
    assert "signal_reasoning" not in review


def test_b2_review_comment_mentions_weekly_and_daily_waves() -> None:
    review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "周线" in review["comment"]
    assert "日线" in review["comment"]
    assert "b2" in review["comment"]


def test_b2_review_comment_uses_trend_state_not_wave_labels() -> None:
    review = review_b2_symbol_history(
        code="000002.SZ",
        pick_date="2026-04-30",
        history=_damaged_b2_history(),
        chart_path="/tmp/000002.SZ_day.png",
    )

    assert "MACD" in review["comment"]
    assert "wave4_end" not in review["comment"]
    assert "三浪涨幅约" not in review["comment"]


def test_b2_review_ignores_future_rows_after_pick_date() -> None:
    baseline_history = _constructive_b2_history()
    future_damage = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(start="2026-05-01", periods=20),
            "open": [14.0 - idx * 0.30 for idx in range(20)],
            "high": [14.2 - idx * 0.30 for idx in range(20)],
            "low": [13.6 - idx * 0.30 for idx in range(20)],
            "close": [13.8 - idx * 0.30 for idx in range(20)],
            "vol": [3000.0 + idx * 100.0 for idx in range(20)],
        }
    )
    full_history = pd.concat([baseline_history, future_damage], ignore_index=True)

    review_from_pick_slice = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=baseline_history,
        chart_path="/tmp/000001.SZ_day.png",
    )
    review_with_future_rows = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=full_history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review_with_future_rows == review_from_pick_slice


def test_b2_review_keeps_neutral_macd_score_when_history_is_too_short_for_wave_judgment() -> None:
    history = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=40),
            "open": [10.0 + idx * 0.05 for idx in range(40)],
            "high": [10.2 + idx * 0.05 for idx in range(40)],
            "low": [9.9 + idx * 0.05 for idx in range(40)],
            "close": [10.1 + idx * 0.05 for idx in range(40)],
            "vol": [1000.0 + idx * 5.0 for idx in range(40)],
        }
    )

    review = review_b2_symbol_history(
        code="000003.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000003.SZ_day.png",
    )

    assert review["macd_phase"] == 3.0


def test_b2_review_scores_invalid_daily_state_low_even_with_constructive_weekly_wave() -> None:
    periods = _first_non_fallback_periods()
    history = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=periods),
            "open": [10.0] * (periods - 20)
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
            "high": [10.2] * (periods - 20)
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
            "low": [9.8] * (periods - 20)
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
            "close": [10.0] * (periods - 20)
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
            "vol": [900.0] * (periods - 20)
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
    weekly_closes = history.set_index("trade_date")["close"].resample("W-FRI").last().dropna()
    monthly_closes = history.set_index("trade_date")["close"].resample("ME").last().dropna()
    previous_history = history.iloc[1:].reset_index(drop=True)
    previous_weekly_closes = previous_history.set_index("trade_date")["close"].resample("W-FRI").last().dropna()
    previous_monthly_closes = previous_history.set_index("trade_date")["close"].resample("ME").last().dropna()

    review = review_b2_symbol_history(
        code="000005.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000005.SZ_day.png",
    )

    assert periods == 848
    assert len(weekly_closes) == 170
    assert len(monthly_closes) == _MULTI_TIMEFRAME_CONFIRMATION_POINTS
    assert len(previous_monthly_closes) == _MULTI_TIMEFRAME_CONFIRMATION_POINTS - 1
    assert len(previous_weekly_closes) >= _MULTI_TIMEFRAME_CONFIRMATION_POINTS
    assert review["macd_phase"] == 2.0


def test_b2_review_uses_neutral_wave_score_one_step_before_boundary_when_daily_wave_is_invalid() -> None:
    periods = _first_non_fallback_periods() - 1
    history = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=periods),
            "open": [10.0] * (periods - 20)
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
            "high": [10.2] * (periods - 20)
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
            "low": [9.8] * (periods - 20)
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
            "close": [10.0] * (periods - 20)
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
            "vol": [900.0] * (periods - 20)
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
    weekly_closes = history.set_index("trade_date")["close"].resample("W-FRI").last().dropna()
    monthly_closes = history.set_index("trade_date")["close"].resample("ME").last().dropna()

    review = review_b2_symbol_history(
        code="000006.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000006.SZ_day.png",
    )

    assert len(monthly_closes) == _MULTI_TIMEFRAME_CONFIRMATION_POINTS - 1
    assert len(weekly_closes) >= _MULTI_TIMEFRAME_CONFIRMATION_POINTS
    assert review["macd_phase"] <= 3.0
