import pandas as pd
import pytest

from stock_select.reviewers.b2 import (
    infer_b2_elastic_watch,
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


def test_b2_verdict_passes_strong_trend_start_watch_when_mid_high_macd_and_structure_are_strong() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.08,
            trend_structure=4.0,
            price_position=3.0,
            volume_behavior=3.0,
            previous_abnormal_move=5.0,
            macd_phase=4.3,
            signal="B2",
            signal_type="trend_start",
        )
        == "PASS"
    )


def test_b2_verdict_keeps_rebound_mid_high_macd_as_watch_without_stricter_macd_pass() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.08,
            trend_structure=4.0,
            price_position=3.0,
            volume_behavior=3.0,
            previous_abnormal_move=5.0,
            macd_phase=4.3,
            signal="B2",
            signal_type="rebound",
        )
        == "WATCH"
    )


def test_b2_verdict_keeps_trend_start_mid_high_macd_watch_when_volume_too_weak() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.48,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=4.34,
            signal="B2",
            signal_type="trend_start",
        )
        == "WATCH"
    )


def test_b2_verdict_passes_trend_start_mid_macd_when_volume_and_structure_support() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.22,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=3.0,
            previous_abnormal_move=5.0,
            macd_phase=3.6,
            signal="B2",
            signal_type="trend_start",
            close_above_ma25_pct=4.0,
            ma25_above_zxdkx_pct=8.0,
        )
        == "PASS"
    )


def test_b2_verdict_keeps_trend_start_mid_macd_as_watch_when_overextended_above_ma25() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.22,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=3.0,
            previous_abnormal_move=5.0,
            macd_phase=3.6,
            signal="B2",
            signal_type="trend_start",
            close_above_ma25_pct=12.0,
            ma25_above_zxdkx_pct=8.0,
        )
        == "WATCH"
    )


def test_b2_verdict_keeps_trend_start_mid_macd_as_watch_when_ma25_too_far_above_zxdkx() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.22,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=3.0,
            previous_abnormal_move=5.0,
            macd_phase=3.6,
            signal="B2",
            signal_type="trend_start",
            close_above_ma25_pct=4.0,
            ma25_above_zxdkx_pct=18.0,
        )
        == "WATCH"
    )


def test_b2_verdict_keeps_trend_start_mid_macd_as_watch_when_total_score_below_relaxed_boundary() -> None:
    assert (
        infer_b2_verdict(
            total_score=3.99,
            trend_structure=4.0,
            price_position=3.0,
            volume_behavior=3.0,
            previous_abnormal_move=5.0,
            macd_phase=4.3,
            signal="B2",
            signal_type="trend_start",
        )
        == "WATCH"
    )


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


def test_b2_verdict_keeps_strong_structure_with_good_mid_macd_as_watch() -> None:
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
        == "WATCH"
    )


def test_b2_verdict_upgrades_b3_trend_start_watch_to_pass_when_structure_is_strong() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.16,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=3.85,
            signal="B3",
            signal_type="trend_start",
        )
        == "PASS"
    )


def test_b2_verdict_upgrades_b3_rebound_watch_to_pass_when_mid_macd_and_price_are_strong() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.16,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=4.2,
            signal="B3",
            signal_type="rebound",
        )
        == "PASS"
    )


def test_b2_verdict_does_not_upgrade_b3_without_enough_structure_confirmation() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.16,
            trend_structure=3.0,
            price_position=5.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=4.2,
            signal="B3",
            signal_type="rebound",
        )
        == "WATCH"
    )


def test_b2_verdict_does_not_upgrade_b3_rebound_below_macd_boundary() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.16,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=4.19,
            signal="B3",
            signal_type="rebound",
        )
        == "WATCH"
    )


def test_b2_verdict_does_not_upgrade_b3_trend_start_below_score_boundary() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.14,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=2.0,
            previous_abnormal_move=5.0,
            macd_phase=3.85,
            signal="B3",
            signal_type="trend_start",
        )
        == "WATCH"
    )


def test_b2_verdict_keeps_distribution_risk_out_of_b3_upgrade_even_with_strong_scores() -> None:
    assert (
        infer_b2_verdict(
            total_score=4.3,
            trend_structure=4.0,
            price_position=5.0,
            volume_behavior=1.0,
            previous_abnormal_move=5.0,
            macd_phase=4.6,
            signal="B3",
            signal_type="distribution_risk",
        )
        == "WATCH"
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


def test_b2_verdict_does_not_fail_when_only_volume_is_weak() -> None:
    assert (
        infer_b2_verdict(
            total_score=3.6,
            trend_structure=4.0,
            price_position=3.0,
            volume_behavior=1.0,
            previous_abnormal_move=5.0,
            macd_phase=4.5,
            signal="B2",
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
            signal=None,
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
            signal=None,
            signal_type="rebound",
        )
        == "FAIL"
    )


def test_b2_price_position_scores_from_box_position_only() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    high.iloc[-1] = 17.7
    low.iloc[-1] = 16.3
    close.iloc[-1] = 17.0
    ma25 = _series([14.0] * len(close))
    zxdq = _series([13.8] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 5.0


def test_b2_price_position_scores_high_middle_box_position_as_strongest_band() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    high.iloc[-1] = 18.3
    low.iloc[-1] = 17.7
    close.iloc[-1] = 18.0
    ma25 = _series([12.0] * len(close))
    zxdq = _series([18.0] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 5.0


def test_b2_price_position_scores_upper_box_extension_as_second_band_without_trend_support() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    high.iloc[-1] = 19.0
    low.iloc[-1] = 18.0
    close.iloc[-1] = 18.5
    ma25 = _series([15.0] * 114 + [16.2, 16.15, 16.1, 16.05, 16.0, 15.95])
    zxdq = _series([15.8] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 4.0


def test_b2_price_position_scores_lower_box_position_as_weak_band() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    high.iloc[-1] = 13.5
    low.iloc[-1] = 12.5
    close.iloc[-1] = 13.0
    ma25 = _series([12.0] * len(close))
    zxdq = _series([11.8] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 1.0


def test_b2_price_position_scores_extreme_upper_box_position_as_neutral_band() -> None:
    low = _series([10.0] * 120)
    high = _series([20.0] * 120)
    close = _series([15.0] * 120)
    high.iloc[-1] = 20.0
    low.iloc[-1] = 19.0
    close.iloc[-1] = 19.5
    ma25 = _series([19.0] * len(close))
    zxdq = _series([18.8] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 3.0


def test_b2_trend_structure_uses_zxdkx_as_medium_support_line() -> None:
    close = _series([10.0] * 60 + [10.2, 10.4, 10.6, 10.8, 11.0])
    low = close * 0.99
    ma25 = _series([9.8] * 60 + [10.0, 10.1, 10.2, 10.3, 10.4])
    zxdkx = _series([9.4] * 60 + [9.6, 9.7, 9.8, 9.9, 10.0])

    assert _score_b2_trend_structure(close=close, low=low, ma25=ma25, zxdkx=zxdkx) == 4.0


def test_b2_price_position_uses_current_mid_price_for_box_position() -> None:
    low = _series([10.0] * 120)
    high = _series([11.0] * 120)
    close = _series([10.5] * 120)
    # 入选日中位价相对箱体位置约 80%，应落在最高非线性分档。
    high.iloc[-5] = 20.0
    close.iloc[-5] = 18.0
    close.iloc[-3] = 12.0
    low.iloc[-3] = 11.8
    high.iloc[-1] = 18.3
    close.iloc[-1] = 18.0
    low.iloc[-1] = 17.8
    ma25 = _series([16.0] * len(close))
    zxdq = _series([15.0] * len(close))

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 5.0


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


def test_b2_price_position_ignores_ma25_zxdq_support_exception() -> None:
    close = _series([10.0] * 40 + [12.0, 14.0, 15.5, 16.0, 15.8, 15.9, 15.7, 15.6, 15.4, 15.2])
    high = close * 1.01
    low = close * 0.99
    ma25 = close.rolling(window=25, min_periods=25).mean()
    zxdq = ma25 * 1.20
    weak_ma25 = ma25 * 0.50
    weak_zxdq = zxdq * 2.00

    assert _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq) == 5.0
    assert _score_b2_price_position(close=close, high=high, low=low, ma25=weak_ma25, zxdq=weak_zxdq) == 5.0


def test_b2_volume_behavior_rewards_right_side_confirmation() -> None:
    close = _series([10.0] * 40 + [10.3, 10.7, 11.2, 11.0, 10.9, 10.8, 10.95, 11.05, 11.15, 11.25])
    volume = _series([900.0] * 40 + [1200.0, 1400.0, 1800.0, 1500.0, 1300.0, 1200.0, 1180.0, 1160.0, 1150.0, 1500.0])

    assert _score_b2_volume_behavior(close=close, volume=volume) == 5.0


def test_b2_volume_behavior_scores_high_hold_without_confirmation_as_four() -> None:
    close = _series([10.0] * 40 + [10.3, 10.7, 11.2, 11.0, 10.9, 10.8, 10.95, 11.05, 11.15, 11.25])
    volume = _series([900.0] * 40 + [1200.0, 1400.0, 1800.0, 1500.0, 1300.0, 1200.0, 1180.0, 1160.0, 1150.0, 800.0])

    assert _score_b2_volume_behavior(close=close, volume=volume) == 4.0


def test_b2_volume_behavior_scores_above_five_day_average_as_neutral() -> None:
    close = _series([10.0] * 40 + [10.2, 12.0, 10.5, 10.4, 10.45, 10.5, 10.55, 10.6, 10.65, 10.68])
    volume = _series([900.0] * 40 + [1200.0, 1400.0, 1800.0, 1500.0, 1300.0, 1200.0, 1180.0, 1160.0, 1150.0, 1100.0])

    assert _score_b2_volume_behavior(close=close, volume=volume) == 3.0


def test_b2_volume_behavior_penalizes_below_average_with_volume() -> None:
    close = _series([10.0] * 40 + [10.3, 10.7, 11.2, 11.0, 10.9, 10.8, 10.7, 10.6, 10.5, 10.4])
    volume = _series([900.0] * 40 + [1200.0, 1400.0, 1800.0, 1500.0, 1300.0, 1200.0, 1180.0, 1160.0, 1150.0, 1300.0])

    assert _score_b2_volume_behavior(close=close, volume=volume) == 1.0


def test_b2_volume_behavior_scores_below_average_without_volume_as_two() -> None:
    close = _series([10.0] * 40 + [10.3, 10.7, 11.2, 11.0, 10.9, 10.8, 10.7, 10.6, 10.5, 10.4])
    volume = _series([900.0] * 40 + [1200.0, 1400.0, 1800.0, 1500.0, 1300.0, 1200.0, 1180.0, 1160.0, 1150.0, 900.0])

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
    assert review["price_position"] == 3.0
    assert review["volume_behavior"] == 5.0
    assert review["previous_abnormal_move"] == 5.0
    assert review["macd_phase"] == pytest.approx(4.5)
    assert review["total_score"] == 3.95
    assert review["signal"] is None
    assert "ranking_score" not in review
    assert "rank_features" not in review
    assert review["signal_type"] == "trend_start"
    assert review["verdict"] == "PASS"
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


def test_b2_review_marks_mid_macd_elastic_watch_for_non_upgrade_path(monkeypatch) -> None:
    monkeypatch.setattr("stock_select.reviewers.b2._score_b2_price_position", lambda **_kwargs: 4.0)
    monkeypatch.setattr("stock_select.reviewers.b2._score_b2_macd_phase", lambda *_args, **_kwargs: 4.3)

    review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
        signal="B2",
    )

    assert review["signal_type"] == "trend_start"
    assert review["verdict"] == "WATCH"
    assert review["elastic_watch"] is True
    assert review["elastic_watch_reason"] == "mid_macd_elastic_watch"


def test_b2_review_marks_low_volume_elastic_watch(monkeypatch) -> None:
    monkeypatch.setattr("stock_select.reviewers.b2._score_b2_price_position", lambda **_kwargs: 4.0)
    monkeypatch.setattr("stock_select.reviewers.b2._score_b2_volume_behavior", lambda *, close, volume: 1.0)
    monkeypatch.setattr("stock_select.reviewers.b2._score_b2_macd_phase", lambda *_args, **_kwargs: 3.7)

    review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
        signal="B2",
    )

    assert review["verdict"] == "WATCH"
    assert review["elastic_watch"] is True
    assert review["elastic_watch_reason"] == "low_volume_elastic_watch"


def test_b2_review_keeps_pass_out_of_elastic_watch() -> None:
    review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
        signal="B3",
    )

    assert review["verdict"] == "PASS"
    assert review["elastic_watch"] is False
    assert review["elastic_watch_reason"] is None


def test_b2_elastic_watch_matches_c_rule() -> None:
    assert infer_b2_elastic_watch(
        verdict="WATCH",
        total_score=4.1,
        trend_structure=3.0,
        price_position=4.0,
        volume_behavior=3.0,
        previous_abnormal_move=5.0,
        macd_phase=4.3,
    ) == (True, "mid_macd_elastic_watch")


def test_b2_elastic_watch_matches_e_rule() -> None:
    assert infer_b2_elastic_watch(
        verdict="WATCH",
        total_score=4.05,
        trend_structure=4.0,
        price_position=4.0,
        volume_behavior=1.0,
        previous_abnormal_move=5.0,
        macd_phase=3.7,
    ) == (True, "low_volume_elastic_watch")


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
    assert review["total_score"] == 1.58
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
