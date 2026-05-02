import importlib

import pandas as pd
import pytest

import stock_select.strategies as strategies


def test_strategies_exports_b2_support() -> None:
    assert "b2" in strategies.SUPPORTED_METHODS
    assert "dribull" in strategies.SUPPORTED_METHODS
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


def _base_b2_frame(*, code: str = "000001.SZ") -> pd.DataFrame:
    trade_dates = pd.date_range("2025-09-01", periods=160, freq="B")
    close = pd.Series([10.0] * 151 + [10.8, 10.7, 10.6, 10.4, 10.2, 10.0, 9.9, 10.2, 10.65])
    open_ = close.shift(1).fillna(close.iloc[0] * 0.99)
    open_.iloc[-1] = 10.15
    high = pd.concat([open_, close], axis=1).max(axis=1) + 0.15
    low = pd.concat([open_, close], axis=1).min(axis=1) - 0.15
    high.iloc[-1] = 10.82
    low.iloc[-1] = 10.00
    volume = pd.Series([1000.0 + idx for idx in range(160)])
    volume.iloc[-2] = 1350.0
    volume.iloc[-1] = 2100.0
    turnover = ((open_ + close) / 2.0) * volume
    turnover_n = turnover.rolling(window=43, min_periods=1).sum()
    return pd.DataFrame(
        {
            "trade_date": trade_dates,
            "ts_code": code,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "vol": volume,
            "volume": volume,
            "turnover_n": turnover_n,
        }
    )


def test_run_b2_screen_with_stats_selects_cur_b2_signal() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()

    candidates, stats = run_b2_screen_with_stats(frame, pick_date=pick_date)

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert candidates[0]["signal"] == "B2"
    assert stats["selected"] == 1
    assert stats["selected_b2"] == 1


def test_run_b2_screen_with_stats_rejects_when_price_gain_is_too_small() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-1], "close"] = 10.50
    frame.loc[frame.index[-1], "high"] = 10.68
    frame.loc[frame.index[-1], "low"] = 10.00

    candidates, stats = run_b2_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_pct"] == 1


def test_run_b2_screen_with_stats_rejects_when_previous_bar_not_pre_ok() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-2], "close"] = 10.70

    candidates, stats = run_b2_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_pre_ok"] == 1


def test_run_b2_screen_with_stats_rejects_when_k_shape_is_invalid() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_b2_frame()
    frame.loc[frame.index[-1], "high"] = 11.80

    candidates, stats = run_b2_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
    assert stats["fail_k_shape"] == 1


def test_run_b2_screen_with_stats_selects_cur_b3_plus_signal() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-11")
    frame = _base_b2_frame()
    extra = {
        "trade_date": pd.Timestamp("2026-04-11"),
        "ts_code": "000001.SZ",
        "open": 11.00,
        "high": 11.15,
        "low": 10.96,
        "close": 11.05,
        "vol": 900.0,
        "volume": 900.0,
        "turnover_n": float(frame["turnover_n"].iloc[-1] + 1.0),
    }
    frame = pd.concat([frame, pd.DataFrame([extra])], ignore_index=True)

    candidates, stats = run_b2_screen_with_stats(frame, pick_date=pick_date)

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert candidates[0]["signal"] == "B3+"
    assert stats["selected_b3_plus"] == 1


def test_run_b2_screen_with_stats_ignores_cur_b4_signal() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-11")
    frame = _base_b2_frame()
    extra = {
        "trade_date": pd.Timestamp("2026-04-11"),
        "ts_code": "000001.SZ",
        "open": 11.00,
        "high": 11.14,
        "low": 10.94,
        "close": 11.06,
        "vol": 2050.0,
        "volume": 2050.0,
        "turnover_n": float(frame["turnover_n"].iloc[-1] + 1.0),
    }
    frame = pd.concat([frame, pd.DataFrame([extra])], ignore_index=True)

    candidates, stats = run_b2_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []


def test_run_b2_screen_with_stats_ignores_cur_b5_signal() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-14")
    frame = _base_b2_frame()
    day_2 = {
        "trade_date": pd.Timestamp("2026-04-11"),
        "ts_code": "000001.SZ",
        "open": 11.00,
        "high": 11.15,
        "low": 10.96,
        "close": 11.05,
        "vol": 900.0,
        "volume": 900.0,
        "turnover_n": float(frame["turnover_n"].iloc[-1] + 1.0),
    }
    day_3 = {
        "trade_date": pd.Timestamp("2026-04-14"),
        "ts_code": "000001.SZ",
        "open": 11.03,
        "high": 11.12,
        "low": 10.99,
        "close": 11.07,
        "vol": 700.0,
        "volume": 700.0,
        "turnover_n": float(frame["turnover_n"].iloc[-1] + 2.0),
    }
    frame = pd.concat([frame, pd.DataFrame([day_2, day_3])], ignore_index=True)

    candidates, stats = run_b2_screen_with_stats(frame, pick_date=pick_date)

    assert candidates == []
