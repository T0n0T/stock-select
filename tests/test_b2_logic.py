import importlib

import pandas as pd
import pytest

import stock_select.strategies as strategies


def test_strategies_exports_b2_support() -> None:
    assert "b2" in strategies.SUPPORTED_METHODS
    assert strategies.validate_method(" b2 ") == "b2"
    assert hasattr(strategies, "run_b2_screen_with_stats")


def _load_run_b2_screen_with_stats():
    try:
        module = importlib.import_module("stock_select.strategies.b2")
    except ModuleNotFoundError as exc:
        if exc.name != "stock_select.strategies.b2":
            raise
        pytest.fail(f"Missing b2 strategy module: {exc}")
    return module.run_b2_screen_with_stats


def _load_prefilter_b2_non_macd():
    try:
        module = importlib.import_module("stock_select.strategies.b2")
    except ModuleNotFoundError as exc:
        if exc.name != "stock_select.strategies.b2":
            raise
        pytest.fail(f"Missing b2 strategy module: {exc}")
    return module.prefilter_b2_non_macd


def _base_b2_frame() -> pd.DataFrame:
    trade_dates = pd.date_range("2025-09-01", periods=160, freq="B")
    close = pd.Series([10.0] * 146 + [9.8, 9.7, 9.9, 10.1, 10.4, 10.8, 11.1, 11.4, 11.2, 11.0, 10.9, 10.92, 10.97, 11.02])
    ma25 = close.rolling(window=25, min_periods=25).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()
    ma144 = close.rolling(window=144, min_periods=144).mean()
    low = close - 0.15
    low.iloc[-1] = float(ma25.iloc[-1]) * 1.004
    volume = pd.Series([1000.0 + idx for idx in range(160)])
    volume.iloc[-1] = volume.iloc[-2] - 100.0
    j_values = [45.0] * 145 + [28.0, 26.0, 24.0, 22.0, 20.0, 18.0, 16.0, 14.0, 19.0, 21.0, 23.0, 25.0, 24.0, 22.0, 20.0]
    return pd.DataFrame(
        {
            "trade_date": trade_dates,
            "J": j_values,
            "zxdq": [float(value + 0.30) for value in close],
            "zxdkx": [float(value - 0.10) for value in close],
            "low": low,
            "close": close,
            "volume": volume,
            "vol": volume,
            "ma25": ma25,
            "ma60": ma60,
            "ma144": ma144,
            "dif": [0.04] * 159 + [0.12],
            "dea": [0.03] * 159 + [0.08],
            "dif_w": [0.05] * 159 + [0.20],
            "dea_w": [0.04] * 159 + [0.15],
            "dif_m": [0.06] * 159 + [0.30],
            "dea_m": [0.05] * 159 + [0.22],
            "turnover_n": [1000.0 + idx for idx in range(160)],
        }
    )


def test_run_b2_screen_with_stats_passes_when_recent_j_hit_and_new_formula_all_hold() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert stats["selected"] == 1


def test_prefilter_b2_non_macd_keeps_only_symbols_passing_non_macd_rules() -> None:
    prefilter_b2_non_macd = _load_prefilter_b2_non_macd()
    pick_date = pd.Timestamp("2026-04-10")
    passing = _base_b2_frame()
    fail_zxdq = _base_b2_frame()
    fail_zxdq.loc[fail_zxdq.index[-1], "zxdq"] = fail_zxdq.loc[fail_zxdq.index[-1], "zxdkx"] - 0.01
    fail_volume = _base_b2_frame()
    fail_volume.loc[fail_volume.index[-1], "volume"] = fail_volume.loc[fail_volume.index[-2], "volume"] + 1.0
    fail_volume.loc[fail_volume.index[-1], "vol"] = fail_volume.loc[fail_volume.index[-1], "volume"]

    selected = prefilter_b2_non_macd(
        {
            "PASS.SZ": passing,
            "FAILZXDQ.SZ": fail_zxdq,
            "FAILVOL.SZ": fail_volume,
        },
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert selected == ["PASS.SZ"]


def test_prefilter_b2_non_macd_does_not_require_daily_macd_any_more() -> None:
    prefilter_b2_non_macd = _load_prefilter_b2_non_macd()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-1], "dif"] = 0.07
    frame.loc[frame.index[-1], "dea"] = 0.08

    selected = prefilter_b2_non_macd(
        {"PASS.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert selected == ["PASS.SZ"]


def test_run_b2_screen_with_stats_fails_when_no_recent_j_hit_exists() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame["J"] = [100.0 + idx for idx in range(len(frame))]

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_recent_j"] == 1


def test_run_b2_screen_with_stats_fails_when_current_zxdq_is_not_above_zxdkx() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-1], "zxdq"] = 9.9

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_zxdq_zxdkx"] == 1


def test_run_b2_screen_with_stats_fails_when_support_on_ma25_is_not_valid() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-1], "low"] = 10.6
    frame.loc[frame.index[-1], "close"] = 10.4
    frame.loc[frame.index[-1], "ma25"] = 10.5

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_support_ma25"] == 1


def test_run_b2_screen_with_stats_fails_when_volume_does_not_shrink() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-1], "volume"] = frame.loc[frame.index[-2], "volume"] + 10.0
    frame.loc[frame.index[-1], "vol"] = frame.loc[frame.index[-1], "volume"]

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_volume_shrink"] == 1


def test_run_b2_screen_with_stats_fails_when_weekly_wave_is_not_allowed() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-14] :, "close"] = [11.4, 11.3, 11.1, 10.9, 10.8, 10.7, 10.65, 10.6, 10.58, 10.56, 10.54, 10.52, 10.5, 10.48]
    frame["ma25"] = frame["close"].rolling(window=25, min_periods=25).mean()
    frame["ma60"] = frame["close"].rolling(window=60, min_periods=60).mean()
    frame["ma144"] = frame["close"].rolling(window=144, min_periods=144).mean()
    frame["low"] = frame["close"] - 0.15
    frame.loc[frame.index[-1], "low"] = float(frame.loc[frame.index[-1], "ma25"]) * 1.004

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_weekly_wave"] == 1


def test_run_b2_screen_with_stats_fails_when_daily_wave_is_invalid() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-3] :, "close"] = [13.0, 12.5, 12.0]

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_daily_wave"] == 1


def test_run_b2_screen_with_stats_fails_when_ma60_is_not_upward() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-2], "ma60"] = 10.2
    frame.loc[frame.index[-1], "ma60"] = 10.1

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_ma60_trend"] == 1


def test_run_b2_screen_with_stats_fails_when_distance_to_ma144_exceeds_30_pct() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-1], "close"] = 16.0
    frame.loc[frame.index[-1], "low"] = 15.85
    frame.loc[frame.index[-1], "ma25"] = 15.9

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_ma144_distance"] == 1


def test_run_b2_screen_with_stats_treats_missing_required_columns_as_insufficient_history() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_b2_screen_with_stats(
        {
            "000001.SZ": _base_b2_frame().drop(columns=["dif_m", "dea_m", "ma144"]),
        },
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats == {
        "total_symbols": 1,
        "eligible": 1,
        "fail_recent_j": 0,
        "fail_insufficient_history": 1,
        "fail_support_ma25": 0,
        "fail_volume_shrink": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_ma60_trend": 0,
        "fail_ma144_distance": 0,
        "fail_weekly_wave": 0,
        "fail_daily_wave": 0,
        "fail_wave_combo": 0,
        "selected": 0,
    }


def test_run_b2_screen_with_stats_treats_malformed_trade_dates_as_insufficient_history() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame["trade_date"] = frame["trade_date"].astype(object)
    frame.loc[3, "trade_date"] = "not-a-date"

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_insufficient_history"] == 1


@pytest.mark.parametrize(
    "column_name",
    ["J", "zxdq", "zxdkx", "low", "close", "volume", "ma25", "ma60", "ma144", "dif", "dea", "dif_w", "dea_w", "dif_m", "dea_m", "turnover_n"],
)
def test_run_b2_screen_with_stats_treats_any_malformed_required_numeric_value_as_insufficient_history(
    column_name: str,
) -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame[column_name] = frame[column_name].astype(object)
    frame.loc[3, column_name] = "boom"

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_insufficient_history"] == 1
