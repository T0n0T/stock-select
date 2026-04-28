import pandas as pd
import pytest

from stock_select.reviewers.b2 import (
    infer_b2_verdict,
    _score_b2_previous_abnormal_move,
    _score_b2_price_position,
    _score_b2_trend_structure,
    _score_b2_volume_behavior,
    review_b2_symbol_history,
)


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


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=range(len(values)), dtype="float64")


def test_b2_verdict_passes_strong_macd_and_constructive_wash() -> None:
    assert (
        infer_b2_verdict(
            total_score=3.72,
            trend_structure=3.0,
            price_position=2.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=4.5,
            signal="B2",
            signal_type="rebound",
        )
        == "PASS"
    )


def test_b2_verdict_passes_strong_structure_with_good_macd() -> None:
    assert (
        infer_b2_verdict(
            total_score=3.7,
            trend_structure=4.0,
            price_position=3.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=3.8,
            signal="B2",
            signal_type="trend_start",
        )
        == "PASS"
    )


def test_b2_verdict_keeps_distribution_risk_as_watch_only_when_strongly_elastic() -> None:
    assert (
        infer_b2_verdict(
            total_score=3.66,
            trend_structure=3.0,
            price_position=3.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=4.5,
            signal="B3",
            signal_type="distribution_risk",
        )
        == "WATCH"
    )


def test_b2_verdict_does_not_pass_loose_macd_setup() -> None:
    assert (
        infer_b2_verdict(
            total_score=3.39,
            trend_structure=3.0,
            price_position=4.0,
            volume_behavior=3.0,
            previous_abnormal_move=5.0,
            macd_phase=4.0,
            signal="B5",
            signal_type="rebound",
        )
        == "WATCH"
    )


def test_b2_verdict_fails_distribution_risk_without_elasticity() -> None:
    assert (
        infer_b2_verdict(
            total_score=3.2,
            trend_structure=2.0,
            price_position=2.0,
            volume_behavior=2.0,
            previous_abnormal_move=3.0,
            macd_phase=3.2,
            signal="B2",
            signal_type="distribution_risk",
        )
        == "FAIL"
    )


def test_b2_verdict_fails_low_score_without_elasticity() -> None:
    assert (
        infer_b2_verdict(
            total_score=3.1,
            trend_structure=3.0,
            price_position=2.0,
            volume_behavior=2.0,
            previous_abnormal_move=3.0,
            macd_phase=3.2,
            signal="B5",
            signal_type="rebound",
        )
        == "FAIL"
    )


def test_b2_price_position_scores_mid_box_as_base_not_center_deviation_bonus() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    high.iloc[-1] = 15.5
    low.iloc[-1] = 14.5
    close.iloc[-1] = 15.2
    ma25 = _series([14.0] * len(close))
    zxdq = _series([13.8] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 3.0


def test_b2_price_position_rewards_upper_box_breakout_with_trend_support() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    high.iloc[-1] = 19.2
    low.iloc[-1] = 18.4
    close.iloc[-1] = 18.9
    ma25 = _series([15.0] * 114 + [16.0, 16.1, 16.2, 16.3, 16.5, 16.8])
    zxdq = _series([14.0] * 114 + [15.0, 15.1, 15.2, 15.3, 15.4, 15.5])

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 5.0


def test_b2_price_position_penalizes_upper_box_extension_without_trend_support() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    # 高位接近箱体上沿，但均线/中线支撑没有跟上，应视作高位虚浮而非突破延续。
    high.iloc[-10] = 20.0
    low.iloc[-10] = 10.0
    close.iloc[-8] = 12.0
    high.iloc[-1] = 19.8
    low.iloc[-1] = 18.8
    close.iloc[-1] = 19.4
    ma25 = _series([15.0] * 114 + [16.2, 16.15, 16.1, 16.05, 16.0, 15.95])
    zxdq = _series([15.8] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 1.0


def test_b2_price_position_scores_low_box_as_weak_even_when_close_to_lower_center_distance() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    high.iloc[-1] = 13.5
    low.iloc[-1] = 12.5
    close.iloc[-1] = 13.0
    ma25 = _series([12.0] * len(close))
    zxdq = _series([11.8] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 1.0


def test_b2_trend_structure_uses_zxdkx_as_medium_support_line() -> None:
    close = _series([10.0] * 60 + [10.2, 10.4, 10.6, 10.8, 11.0])
    low = close * 0.99
    ma25 = _series([9.8] * 60 + [10.0, 10.1, 10.2, 10.3, 10.4])
    zxdkx = _series([9.4] * 60 + [9.6, 9.7, 9.8, 9.9, 10.0])

    assert _score_b2_trend_structure(close=close, low=low, ma25=ma25, zxdkx=zxdkx) == 4.0


def test_b2_price_position_uses_current_mid_price_and_recognizes_breakout_extension() -> None:
    low = _series([10.0] * 120)
    high = _series([11.0] * 120)
    close = _series([10.5] * 120)
    # 入选日中位价相对箱体中点偏高，但价格沿均线支撑突破延续，应按突破型给高分。
    high.iloc[-5] = 20.0
    close.iloc[-5] = 18.0
    close.iloc[-3] = 12.0
    low.iloc[-3] = 11.8
    high.iloc[-1] = 18.3
    close.iloc[-1] = 18.0
    low.iloc[-1] = 17.8
    ma25 = _series([16.0] * len(close))
    zxdq = _series([15.0] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 4.0


def test_b2_previous_abnormal_move_scores_pullback_above_high_volume_body_price() -> None:
    open_ = _series([10.0] * 92 + [100.0, 230.0, 232.0, 234.0])
    close = _series([10.0] * 92 + [150.0, 231.0, 233.0, 235.0])
    low = _series([9.8] * 92 + [99.0, 226.0, 228.0, 230.0])
    volume = _series([1000.0] * 92 + [9000.0, 2000.0, 1800.0, 1600.0])

    assert _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume) == 3.0


def test_b2_previous_abnormal_move_rewards_constructive_wash_without_damage() -> None:
    open_ = _series([10.0] * 92 + [100.0, 92.0, 94.0, 96.0])
    close = _series([10.0] * 92 + [100.0, 92.0, 94.0, 96.0])
    low = _series([9.8] * 92 + [100.0, 91.0, 93.0, 95.0])
    volume = _series([1000.0] * 92 + [9000.0, 2000.0, 1800.0, 1600.0])

    assert _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume) == 5.0


def test_b2_previous_abnormal_move_uses_redundant_price_and_body_low() -> None:
    open_ = _series([10.0] * 92 + [100.0, 96.0, 95.0, 94.0])
    close = _series([10.0] * 92 + [100.0, 96.0, 95.0, 94.0])
    low = _series([9.8] * 92 + [100.0, 70.0, 70.0, 70.0])
    volume = _series([1000.0] * 92 + [9000.0, 2000.0, 1800.0, 1600.0])

    assert _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume) == 5.0


def test_b2_previous_abnormal_move_uses_bearish_body_high_as_abnormal_price() -> None:
    open_ = _series([10.0] * 92 + [120.0, 160.0, 159.0, 158.0])
    close = _series([10.0] * 92 + [100.0, 159.0, 158.0, 157.0])
    low = _series([9.8] * 92 + [99.0, 157.0, 158.0, 159.0])
    volume = _series([1000.0] * 92 + [9000.0, 2000.0, 1800.0, 1600.0])

    assert _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume) == 3.0


def test_b2_price_position_penalizes_passive_ma25_touch_after_high_consolidation() -> None:
    close = _series([10.0] * 40 + [12.0, 14.0, 15.5, 16.0, 15.8, 15.9, 15.7, 15.6, 15.4, 15.2])
    high = close * 1.01
    low = close * 0.99
    ma25 = close.rolling(window=25, min_periods=25).mean()
    zxdq = ma25 * 1.20

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 2.0


def test_b2_volume_behavior_rewards_breakout_volume_then_shrinking_retest() -> None:
    close = _series([10.0] * 40 + [10.3, 10.7, 11.2, 11.0, 10.9, 10.8, 10.95, 11.05, 11.15, 11.25])
    volume = _series([900.0] * 40 + [1200.0, 1800.0, 3200.0, 1500.0, 1100.0, 980.0, 940.0, 960.0, 1000.0, 1040.0])

    assert _score_b2_volume_behavior(close=close, volume=volume) == 5.0


def test_b2_volume_behavior_penalizes_retest_without_volume_contraction() -> None:
    close = _series([10.0] * 40 + [10.3, 10.7, 11.2, 11.0, 10.9, 10.8, 10.95, 11.05, 11.15, 11.25])
    volume = _series([900.0] * 40 + [1200.0, 1800.0, 3200.0, 3000.0, 2900.0, 3100.0, 3050.0, 2950.0, 3000.0, 3150.0])

    assert _score_b2_volume_behavior(close=close, volume=volume) == 2.0


def test_b2_previous_abnormal_move_scores_one_when_high_volume_price_is_lost() -> None:
    open_ = _series([10.0] * 92 + [100.0, 42.0, 40.0, 38.0])
    close = _series([10.0] * 92 + [110.0, 41.0, 39.0, 37.0])
    low = _series([9.8] * 92 + [99.0, 40.0, 38.0, 36.0])
    volume = _series([1000.0] * 92 + [9000.0, 2000.0, 1800.0, 1600.0])

    assert _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume) == 1.0


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
    assert review["price_position"] == 1.0
    assert review["volume_behavior"] == 5.0
    assert review["previous_abnormal_move"] == 5.0
    assert review["macd_phase"] == pytest.approx(4.5)
    assert review["total_score"] == 3.78
    assert review["signal"] is None
    assert "ranking_score" not in review
    assert "rank_features" not in review
    assert review["signal_type"] == "rebound"
    assert review["verdict"] == "WATCH"
    assert "周线MACD" in review["comment"]
    assert "日线MACD" in review["comment"]
    assert "wave" not in review["comment"]
    assert "三浪" not in review["comment"]


def test_b2_review_does_not_apply_macd_verdict_gate(monkeypatch) -> None:
    invalid_weekly = type(
        "Trend",
        (),
        {"phase": "invalid", "is_top_divergence": False, "is_rising_initial": False},
    )()
    rising_daily = type(
        "Trend",
        (),
        {"phase": "rising", "is_top_divergence": False, "is_rising_initial": True},
    )()
    monkeypatch.setattr("stock_select.reviewers.b2.classify_weekly_macd_trend", lambda *_args, **_kwargs: invalid_weekly)
    monkeypatch.setattr("stock_select.reviewers.b2.classify_daily_macd_trend", lambda *_args, **_kwargs: rising_daily)
    monkeypatch.setattr("stock_select.reviewers.b2.map_macd_phase_score", lambda **_kwargs: 5.0)

    review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
        signal="B3",
    )

    assert review["macd_phase"] == 5.0
    assert review["total_score"] >= 4.0
    # If the old b2 MACD verdict gate still ran, invalid weekly MACD would force FAIL.
    assert review["verdict"] != "FAIL"


def test_b2_review_includes_candidate_signal_in_total_score() -> None:
    neutral_review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )
    b3_review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
        signal="B3",
    )

    assert b3_review["signal"] == "B3"
    assert b3_review["total_score"] > neutral_review["total_score"]
    assert round(b3_review["total_score"] - neutral_review["total_score"], 2) == 0.3
    assert "ranking_score" not in b3_review
    assert "rank_features" not in b3_review


def test_b2_review_penalizes_distribution_damage_with_exact_scores() -> None:
    review = review_b2_symbol_history(
        code="000002.SZ",
        pick_date="2026-04-30",
        history=_damaged_b2_history(),
        chart_path="/tmp/000002.SZ_day.png",
    )

    assert review["code"] == "000002.SZ"
    assert review["pick_date"] == "2026-04-30"
    assert review["chart_path"] == "/tmp/000002.SZ_day.png"
    assert review["review_type"] == "baseline"
    assert review["trend_structure"] == 1.0
    assert review["price_position"] == 1.0
    assert review["volume_behavior"] == 1.0
    assert review["previous_abnormal_move"] == 3.0
    assert review["macd_phase"] == pytest.approx(1.0)
    assert review["total_score"] == 1.5
    assert review["signal"] is None
    assert "ranking_score" not in review
    assert "rank_features" not in review
    assert review["signal_type"] == "distribution_risk"
    assert review["verdict"] == "FAIL"
    assert "周线MACD" in review["comment"]
    assert "日线MACD" in review["comment"]
    assert "wave" not in review["comment"]
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
    assert review["macd_phase"] == pytest.approx(4.5)


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
    assert review["macd_phase"] <= 4.5
