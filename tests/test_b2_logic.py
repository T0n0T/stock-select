import importlib

import pandas as pd
import pytest


def _load_run_b2_screen_with_stats():
    try:
        module = importlib.import_module("stock_select.strategies.b2")
    except ModuleNotFoundError as exc:
        if exc.name != "stock_select.strategies.b2":
            raise
        pytest.fail(f"Missing b2 strategy module: {exc}")
    return module.run_b2_screen_with_stats


def test_run_b2_screen_with_stats_passes_when_recent_j_hit_and_macd_hist_is_rising() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-03-20", periods=16, freq="B"),
            "J": [40.0, 38.0, 36.0, 12.0, 25.0, 30.0, 28.0, 27.0, 26.0, 24.0, 23.0, 22.0, 21.0, 20.0, 19.0, 18.0],
            "zxdq": [10.5] * 16,
            "zxdkx": [10.0] * 16,
            "weekly_ma_bull": [True] * 16,
            "macd_hist": [-0.05, -0.04, -0.03, -0.02, -0.01, 0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10],
            "close": [10.8] * 16,
            "turnover_n": [1000.0] * 16,
        }
    )

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert stats["selected"] == 1


def test_run_b2_screen_with_stats_fails_when_no_recent_j_hit_exists() -> None:
    run_b2_screen_with_stats = _load_run_b2_screen_with_stats()
    pick_date = pd.Timestamp("2026-04-10")
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-03-20", periods=16, freq="B"),
            "J": [40.0] * 16,
            "zxdq": [10.5] * 16,
            "zxdkx": [10.0] * 16,
            "weekly_ma_bull": [True] * 16,
            "macd_hist": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16],
            "close": [10.8] * 16,
            "turnover_n": [1000.0] * 16,
        }
    )

    candidates, stats = run_b2_screen_with_stats(
        {"000001.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_recent_j"] == 1
