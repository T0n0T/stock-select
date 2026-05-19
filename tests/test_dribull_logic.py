import importlib
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import stock_select.strategies as strategies


def test_strategies_exports_dribull_support() -> None:
    assert "dribull" in strategies.SUPPORTED_METHODS
    assert strategies.validate_method(" dribull ") == "dribull"
    assert hasattr(strategies, "run_dribull_screen_with_stats")


def _load_run_dribull_screen_with_stats():
    try:
        module = importlib.import_module("stock_select.strategies.dribull")
    except ModuleNotFoundError as exc:
        if exc.name != "stock_select.strategies.dribull":
            raise
        pytest.fail(f"Missing dribull strategy module: {exc}")
    return module.run_dribull_screen_with_stats


def _load_prefilter_dribull_non_macd():
    try:
        module = importlib.import_module("stock_select.strategies.dribull")
    except ModuleNotFoundError as exc:
        if exc.name != "stock_select.strategies.dribull":
            raise
        pytest.fail(f"Missing dribull strategy module: {exc}")
    return module.prefilter_dribull_non_macd


def _trend(phase: str, *, initial: bool = False, divergence: bool = False) -> SimpleNamespace:
    return SimpleNamespace(phase=phase, is_rising_initial=initial, is_top_divergence=divergence)


def _base_dribull_frame() -> pd.DataFrame:
    frame, _, _ = _left_peak_dribull_frame()
    return frame.copy()


def _left_peak_dribull_frame() -> tuple[pd.DataFrame, str, str]:
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
    assert len(close) == 160
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
            "dif": [0.04] * 159 + [0.12],
            "dea": [0.03] * 159 + [0.08],
            "dif_w": [0.05] * 159 + [0.20],
            "dea_w": [0.04] * 159 + [0.15],
            "dif_m": [0.06] * 159 + [0.30],
            "dea_m": [0.05] * 159 + [0.22],
            "turnover_n": [1000.0 + idx for idx in range(160)],
        }
    )
    frame["ts_code"] = "000001.SZ"
    return frame, trade_dates[49].strftime("%Y-%m-%d"), trade_dates[155].strftime("%Y-%m-%d")


def test_run_dribull_screen_with_stats_passes_when_recent_j_hit_and_formula_hold() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame, _, _ = _left_peak_dribull_frame()
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert stats["selected"] == 1


def test_run_dribull_screen_with_stats_fails_when_weekly_trend_is_not_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("stock_select.strategies.dribull")
    pick_date = pd.Timestamp("2026-04-10")
    frame, _, _ = _left_peak_dribull_frame()
    monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("ended"))
    monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("rising", initial=True))

    candidates, stats = module.run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_weekly_trend"] == 1


def test_run_dribull_screen_with_stats_fails_when_daily_trend_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("stock_select.strategies.dribull")
    pick_date = pd.Timestamp("2026-04-10")
    frame, _, _ = _left_peak_dribull_frame()
    monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("invalid"))

    candidates, stats = module.run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_daily_trend"] == 1


def test_run_dribull_screen_with_stats_fails_when_trend_combo_is_not_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("stock_select.strategies.dribull")
    pick_date = pd.Timestamp("2026-04-10")
    frame, _, _ = _left_peak_dribull_frame()
    monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("rising", initial=False))

    candidates, stats = module.run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_trend_combo"] == 1


def test_run_dribull_screen_with_stats_rejects_top_divergence(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("stock_select.strategies.dribull")
    pick_date = pd.Timestamp("2026-04-10")
    frame, _, _ = _left_peak_dribull_frame()
    monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("rising", initial=True, divergence=True))

    candidates, stats = module.run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_trend_combo"] == 1


def test_prefilter_dribull_non_macd_keeps_only_symbols_passing_non_macd_rules() -> None:
    prefilter_dribull_non_macd = _load_prefilter_dribull_non_macd()
    pick_date = pd.Timestamp("2026-04-10")
    passing = _base_dribull_frame()
    fail_zxdq = _base_dribull_frame()
    fail_zxdq.loc[fail_zxdq.index[-1], "zxdq"] = fail_zxdq.loc[fail_zxdq.index[-1], "zxdkx"] - 0.01
    fail_volume = _base_dribull_frame()
    fail_volume.loc[fail_volume.index[-1], "volume"] = fail_volume.loc[fail_volume.index[-2], "volume"] + 1.0
    fail_volume.loc[fail_volume.index[-1], "vol"] = fail_volume.loc[fail_volume.index[-1], "volume"]

    passing["ts_code"] = "PASS.SZ"
    fail_zxdq["ts_code"] = "FAILZXDQ.SZ"
    fail_volume["ts_code"] = "FAILVOL.SZ"
    selected = prefilter_dribull_non_macd(
        pd.concat([passing, fail_zxdq, fail_volume], ignore_index=True),
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert selected == ["PASS.SZ"]


def test_prefilter_dribull_non_macd_ignores_weekly_trend(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("stock_select.strategies.dribull")
    pick_date = pd.Timestamp("2026-04-10")
    frame, _, _ = _left_peak_dribull_frame()
    monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("ended"))
    monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("rising", initial=True))

    selected = module.prefilter_dribull_non_macd(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert selected == ["000001.SZ"]


def test_prefilter_dribull_non_macd_ignores_daily_trend(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("stock_select.strategies.dribull")
    pick_date = pd.Timestamp("2026-04-10")
    frame, _, _ = _left_peak_dribull_frame()
    monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("invalid"))

    selected = module.prefilter_dribull_non_macd(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert selected == ["000001.SZ"]


def test_run_dribull_screen_with_stats_fails_when_no_recent_j_hit_exists() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_dribull_frame()
    frame["J"] = [100.0 + idx for idx in range(len(frame))]

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_recent_j"] == 1


def test_run_dribull_screen_with_stats_fails_when_current_zxdq_is_not_above_zxdkx() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_dribull_frame()
    frame.loc[frame.index[-1], "zxdq"] = 9.9

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_zxdq_zxdkx"] == 1


def test_run_dribull_screen_with_stats_fails_when_support_on_ma25_is_not_valid() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_dribull_frame()
    frame.loc[frame.index[-1], "low"] = 10.6
    frame.loc[frame.index[-1], "close"] = 10.4
    frame.loc[frame.index[-1], "ma25"] = 10.5

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_support_ma25"] == 1


def test_run_dribull_screen_with_stats_fails_when_volume_does_not_shrink() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_dribull_frame()
    frame.loc[frame.index[-1], "volume"] = frame.loc[frame.index[-2], "volume"] + 10.0
    frame.loc[frame.index[-1], "vol"] = frame.loc[frame.index[-1], "volume"]

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_volume_shrink"] == 1


def test_run_dribull_screen_with_stats_fails_when_ma60_is_not_upward() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_dribull_frame()
    frame.loc[frame.index[-2], "ma60"] = frame.loc[frame.index[-1], "ma60"] + 0.01

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_ma60_trend"] == 1


def test_run_dribull_screen_with_stats_fails_when_distance_to_ma144_exceeds_30_pct() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_dribull_frame()
    frame.loc[frame.index[-1], "close"] = frame.loc[frame.index[-1], "ma144"] * 1.31

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_ma144_distance"] == 1


def test_run_dribull_screen_with_stats_treats_missing_required_columns_as_insufficient_history() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")

    frame = _base_dribull_frame().drop(columns=["ma144"])
    frame["ts_code"] = "000001.SZ"

    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["eligible"] == 1
    assert stats["fail_insufficient_history"] == 1


def test_run_dribull_screen_with_stats_treats_malformed_trade_dates_as_insufficient_history() -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_dribull_frame()
    frame["trade_date"] = frame["trade_date"].astype(object)
    frame.loc[10, "trade_date"] = "boom"

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["eligible"] == 1
    assert stats["fail_insufficient_history"] == 1


@pytest.mark.parametrize("column_name", ["J", "zxdq", "zxdkx", "low", "close", "ma25", "ma60", "ma144", "turnover_n"])
def test_run_dribull_screen_with_stats_treats_any_malformed_required_numeric_value_as_insufficient_history(
    column_name: str,
) -> None:
    run_dribull_screen_with_stats = _load_run_dribull_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = _base_dribull_frame()
    frame[column_name] = frame[column_name].astype(object)
    frame.loc[3, column_name] = "boom"

    frame["ts_code"] = "000001.SZ"
    candidates, stats = run_dribull_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["eligible"] == 1
    assert stats["fail_insufficient_history"] == 1
