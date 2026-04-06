import pandas as pd

from stock_select.b1_logic import (
    compute_turnover_n,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
)


def test_compute_turnover_n_uses_midprice_times_volume() -> None:
    df = pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "close": [12.0, 13.0],
            "volume": [100.0, 200.0],
        }
    )

    out = compute_turnover_n(df, window=2)

    assert round(float(out.iloc[-1]), 2) == 3500.0


def test_compute_zx_lines_returns_double_ewm_and_average_ma() -> None:
    df = pd.DataFrame({"close": [10.0, 11.0, 12.0, 13.0, 14.0]})

    zxdq, zxdkx = compute_zx_lines(df, m1=2, m2=3, m3=4, m4=5, zxdq_span=2)

    assert len(zxdq) == len(df)
    assert len(zxdkx) == len(df)
    assert round(float(zxdq.iloc[-1]), 4) == 13.0288
    assert round(float(zxdkx.iloc[-1]), 4) == 12.7500


def test_max_vol_not_bearish_uses_max_volume_candle_in_window() -> None:
    df = pd.DataFrame(
        {
            "open": [10.0, 10.5, 11.0],
            "close": [10.2, 10.1, 11.3],
            "volume": [100.0, 300.0, 200.0],
        }
    )

    out = max_vol_not_bearish(df, lookback=3)

    assert out.tolist() == [True, False, False]


def test_run_b1_screen_filters_symbols_on_pick_date() -> None:
    pick_date = pd.Timestamp("2026-04-03")
    passing = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03"]),
            "open": [10.0, 10.2, 10.5],
            "close": [10.4, 10.8, 11.0],
            "high": [10.5, 10.9, 11.1],
            "low": [9.9, 10.1, 10.4],
            "volume": [100.0, 120.0, 150.0],
            "J": [12.0, 11.0, 10.0],
            "zxdq": [10.2, 10.5, 10.8],
            "zxdkx": [10.0, 10.2, 10.4],
            "weekly_ma_bull": [True, True, True],
            "max_vol_not_bearish": [True, True, True],
            "turnover_n": [1020.0, 2280.0, 3892.5],
        }
    )
    failing = passing.copy()
    failing["close"] = [10.4, 10.8, 10.3]

    result = run_b1_screen(
        {"000001.SZ": passing, "000002.SZ": failing},
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert result == [
        {
            "code": "000001.SZ",
            "pick_date": "2026-04-03",
            "close": 11.0,
            "turnover_n": 3892.5,
        }
    ]
