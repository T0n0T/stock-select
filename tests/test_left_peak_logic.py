import importlib

import numpy as np
import pandas as pd
import pytest

import stock_select.strategies as strategies


def test_strategies_exports_left_peak_support() -> None:
    assert "left_peak" in strategies.SUPPORTED_METHODS
    assert strategies.validate_method(" left_peak ") == "left_peak"
    assert hasattr(strategies, "run_left_peak_screen_with_stats")


def _load_run_left_peak_screen_with_stats():
    module = importlib.import_module("stock_select.strategies.left_peak")
    return module.run_left_peak_screen_with_stats


def _base_left_peak_frame() -> pd.DataFrame:
    trade_dates = pd.bdate_range("2025-09-01", periods=160)
    close = pd.Series(
        [
            *([10.0] * 40),
            *np.linspace(10.0, 13.0, 10, endpoint=True),
            *np.linspace(12.95, 11.4, 15, endpoint=True),
            *np.linspace(11.45, 12.84, 90, endpoint=True),
            13.24,
            12.98,
            12.96,
            12.94,
            12.95,
        ],
        dtype=float,
    )
    open_ = close - 0.04
    high = close + 0.12
    low = close - 0.18
    peak_idx = 49
    breakout_idx = 155
    close.iloc[peak_idx] = 13.0
    open_.iloc[peak_idx] = 12.88
    high.iloc[peak_idx] = 13.08
    low.iloc[peak_idx] = 12.80
    open_.iloc[breakout_idx] = 13.15
    close.iloc[breakout_idx] = 13.24
    high.iloc[breakout_idx] = 13.30
    low.iloc[breakout_idx] = 13.05
    ma25 = close.rolling(window=25, min_periods=25).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()
    ma144 = close.rolling(window=144, min_periods=144).mean()
    low.iloc[-1] = float(ma25.iloc[-1]) * 1.004
    open_.iloc[-1] = float(close.iloc[-1]) - 0.03
    high.iloc[-1] = float(close.iloc[-1]) + 0.09
    volume = pd.Series([1000.0 + idx for idx in range(160)])
    volume.iloc[-1] = volume.iloc[-2] - 100.0
    j_values = [45.0] * 145 + [28.0, 26.0, 24.0, 22.0, 20.0, 18.0, 16.0, 14.0, 19.0, 21.0, 23.0, 25.0, 24.0, 22.0, 20.0]
    frame = pd.DataFrame(
        {
            "trade_date": trade_dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "vol": volume,
            "J": j_values,
            "zxdq": [float(value + 0.30) for value in close],
            "zxdkx": [float(value - 0.10) for value in close],
            "ma25": ma25,
            "ma60": ma60,
            "ma144": ma144,
            "chg_d": [1.0] * 160,
            "v_shrink": [True] * 160,
            "lt_filter": [True] * 160,
            "turnover_n": [1000.0 + idx for idx in range(160)],
        }
    )
    frame["ts_code"] = "000001.SZ"
    return frame


def test_run_left_peak_screen_with_stats_selects_matching_symbol() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert stats["selected"] == 1


def test_run_left_peak_screen_with_stats_rejects_when_ma25_not_above_ma60() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    frame.loc[frame.index[-1], "ma25"] = 17.60
    frame.loc[frame.index[-1], "ma60"] = 17.70
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_ma25_ma60"] == 1


def test_run_left_peak_screen_with_stats_rejects_when_ma25_30d_slope_is_non_positive() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    descending = pd.Series(np.linspace(18.5, 17.0, 30), dtype=float)
    frame.loc[frame.index[-30:], "ma25"] = descending.to_numpy()
    frame.loc[frame.index[-30:], "ma60"] = (descending - 0.6).to_numpy()
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_ma25_slope"] == 1


def test_run_left_peak_screen_with_stats_rejects_when_close_not_above_zxdkx() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    frame.loc[frame.index[-1], "zxdkx"] = frame.loc[frame.index[-1], "close"] + 0.01
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_close_zxdkx"] == 1


def test_run_left_peak_screen_with_stats_rejects_when_zxdq_not_above_zxdkx() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    frame.loc[frame.index[-1], "zxdq"] = frame.loc[frame.index[-1], "zxdkx"] - 0.01
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_zxdq_zxdkx"] == 1


def test_run_left_peak_screen_with_stats_rejects_when_daily_gain_too_large() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    frame.loc[frame.index[-1], "chg_d"] = 4.5
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_chg_cap"] == 1


def test_run_left_peak_screen_with_stats_rejects_when_not_volume_shrunk() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    frame.loc[frame.index[-1], "v_shrink"] = False
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_v_shrink"] == 1


def test_run_left_peak_screen_with_stats_rejects_when_lt_filter_is_false() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    frame.loc[frame.index[-1], "lt_filter"] = False
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_lt_filter"] == 1


def test_run_left_peak_screen_with_stats_rejects_when_close_outside_left_peak_band() -> None:
    run_left_peak_screen_with_stats = _load_run_left_peak_screen_with_stats()
    frame = _base_left_peak_frame()
    frame.loc[frame.index[-1], "close"] = 19.50
    frame.loc[frame.index[-1], "open"] = 19.40
    frame.loc[frame.index[-1], "high"] = 19.60
    frame.loc[frame.index[-1], "low"] = 19.30
    frame.loc[frame.index[-1], "ma25"] = 18.20
    frame.loc[frame.index[-1], "ma60"] = 17.70
    pick_date = pd.Timestamp("2026-04-10")

    candidates, stats = run_left_peak_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_left_peak_close_band"] == 1


def test_iter_left_peak_screen_rows_matches_main_screen_function() -> None:
    module = importlib.import_module("stock_select.strategies.left_peak")
    frame = _base_left_peak_frame()
    pick_date = pd.Timestamp("2026-04-10")

    expected_candidates, expected_stats = module.run_left_peak_screen_with_stats(frame, pick_date=pick_date)
    actual_candidates, actual_stats = module.iter_left_peak_screen_rows(frame, pick_date=pick_date)

    assert actual_candidates == expected_candidates
    assert actual_stats == expected_stats


def test_prepared_left_peak_breakout_matches_standard_entrypoint() -> None:
    analysis_module = importlib.import_module("stock_select.analysis.left_peak")
    frame = _base_left_peak_frame()
    pick_date = pd.Timestamp("2026-04-10")
    prepared = frame[["trade_date", "open", "high", "low", "close"]].copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"])
    for column in ("open", "high", "low", "close"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared = prepared.sort_values("trade_date").reset_index(drop=True)

    standard = analysis_module.find_recent_left_peak_breakout(frame, pick_date.strftime("%Y-%m-%d"))
    fast = analysis_module.find_recent_left_peak_breakout_prepared(prepared, pick_date)

    assert fast == standard
