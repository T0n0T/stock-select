import pandas as pd

from stock_select.b1_logic import (
    build_top_turnover_pool,
    compute_expanding_j_quantile,
    compute_turnover_n,
    compute_weekly_close,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
    run_b1_screen_with_stats,
)
from stock_select.strategies.b1 import DEFAULT_B1_CONFIG, run_b1_screen_with_stats as strategy_run_b1_screen_with_stats


def test_b1_strategy_module_exports_current_defaults() -> None:
    assert DEFAULT_B1_CONFIG == {"j_threshold": 15.0, "j_q_threshold": 0.10}
    assert callable(strategy_run_b1_screen_with_stats)


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


def test_compute_expanding_j_quantile_uses_only_history_up_to_each_day() -> None:
    series = pd.Series([50.0, 10.0, 40.0, 20.0])

    out = compute_expanding_j_quantile(series, 0.10)

    assert out.round(1).tolist() == [50.0, 14.0, 16.0, 13.0]


def test_compute_zx_lines_returns_double_ewm_and_average_ma() -> None:
    df = pd.DataFrame({"close": [10.0, 11.0, 12.0, 13.0, 14.0]})

    zxdq, zxdkx = compute_zx_lines(df, m1=2, m2=3, m3=4, m4=5, zxdq_span=2)

    assert len(zxdq) == len(df)
    assert len(zxdkx) == len(df)
    assert round(float(zxdq.iloc[-1]), 4) == 13.0288
    assert round(float(zxdkx.iloc[-1]), 4) == 12.7500


def test_compute_weekly_close_uses_last_actual_trade_day_in_iso_week() -> None:
    df = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                [
                    "2026-01-05",
                    "2026-01-06",
                    "2026-01-08",
                    "2026-01-12",
                    "2026-01-13",
                ]
            ),
            "close": [10.0, 10.2, 10.8, 11.0, 11.3],
        }
    )

    out = compute_weekly_close(df)

    assert out.index.tolist() == [pd.Timestamp("2026-01-08"), pd.Timestamp("2026-01-13")]
    assert out.tolist() == [10.8, 11.3]


def test_compute_weekly_ma_bull_can_use_reference_b1_periods() -> None:
    weekly_dates = pd.date_range("2025-01-03", periods=31, freq="W-FRI")
    trade_dates: list[pd.Timestamp] = []
    close_values: list[float] = []
    for idx, weekly_date in enumerate(weekly_dates):
        trade_dates.extend([weekly_date - pd.Timedelta(days=1), weekly_date])
        close_values.extend([10.0 + idx, 10.2 + idx])

    df = pd.DataFrame({"trade_date": trade_dates, "close": close_values})

    out = compute_weekly_ma_bull(df, ma_periods=(10, 20, 30))

    assert bool(out.iloc[-1]) is True


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


def test_max_vol_not_bearish_tolerates_all_na_volume_window() -> None:
    df = pd.DataFrame(
        {
            "open": [10.0, 10.2, 10.4],
            "close": [10.1, 10.3, 10.5],
            "vol": [None, None, 120.0],
        }
    )

    out = max_vol_not_bearish(df, lookback=20)

    assert out.tolist() == [False, False, True]


def test_build_top_turnover_pool_keeps_only_top_codes_per_pick_date() -> None:
    pool = build_top_turnover_pool(
        {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-02", "2026-04-03"]),
                    "turnover_n": [100.0, 400.0],
                }
            ),
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-02", "2026-04-03"]),
                    "turnover_n": [300.0, 200.0],
                }
            ),
            "CCC.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-02", "2026-04-03"]),
                    "turnover_n": [200.0, 300.0],
                }
            ),
        },
        top_m=2,
    )

    assert pool[pd.Timestamp("2026-04-02")] == ["BBB.SZ", "CCC.SZ"]
    assert pool[pd.Timestamp("2026-04-03")] == ["AAA.SZ", "CCC.SZ"]


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


def test_run_b1_screen_with_stats_reports_first_failed_condition_counts() -> None:
    pick_date = pd.Timestamp("2026-04-03")

    def make_frame(
        *,
        j: float = 10.0,
        close: float = 11.0,
        zxdq: float = 10.8,
        zxdkx: float = 10.4,
        weekly_ma_bull: bool = True,
        max_vol_not_bearish_value: bool = True,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03"]),
                "open": [10.0, 10.2, 10.5],
                "close": [10.4, 10.8, close],
                "high": [10.5, 10.9, 11.1],
                "low": [9.9, 10.1, 10.4],
                "volume": [100.0, 120.0, 150.0],
                "J": [12.0, 11.0, j],
                "zxdq": [10.2, 10.5, zxdq],
                "zxdkx": [10.0, 10.2, zxdkx],
                "weekly_ma_bull": [True, True, weekly_ma_bull],
                "max_vol_not_bearish": [True, True, max_vol_not_bearish_value],
                "turnover_n": [1020.0, 2280.0, 3892.5],
            }
        )

    candidates, stats = run_b1_screen_with_stats(
        {
            "PASS.SZ": make_frame(),
            "FAILJ.SZ": make_frame(j=85.0),
            "FAILCLOSE.SZ": make_frame(close=10.2),
            "FAILZXDQ.SZ": make_frame(zxdq=10.1),
            "FAILWEEKLY.SZ": make_frame(weekly_ma_bull=False),
            "FAILMAXVOL.SZ": make_frame(max_vol_not_bearish_value=False),
            "MISSING.SZ": make_frame().iloc[[0, 1]].copy(),
        },
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert [candidate["code"] for candidate in candidates] == ["PASS.SZ"]
    assert stats == {
        "total_symbols": 7,
        "eligible": 6,
        "fail_j": 1,
        "fail_insufficient_history": 0,
        "fail_close_zxdkx": 1,
        "fail_zxdq_zxdkx": 1,
        "fail_weekly_ma": 1,
        "fail_max_vol": 1,
        "selected": 1,
    }


def test_run_b1_screen_with_stats_counts_missing_zxdkx_as_insufficient_history() -> None:
    pick_date = pd.Timestamp("2026-04-03")
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03"]),
            "open": [10.0, 10.2, 10.5],
            "close": [10.4, 10.8, 11.0],
            "high": [10.5, 10.9, 11.1],
            "low": [9.9, 10.1, 10.4],
            "volume": [100.0, 120.0, 150.0],
            "J": [12.0, 11.0, 10.0],
            "zxdq": [10.2, 10.5, 10.8],
            "zxdkx": [10.0, 10.2, float("nan")],
            "weekly_ma_bull": [True, True, True],
            "max_vol_not_bearish": [True, True, True],
            "turnover_n": [1020.0, 2280.0, 3892.5],
        }
    )

    candidates, stats = run_b1_screen_with_stats(
        {"MISSINGZXDKX.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert candidates == []
    assert stats == {
        "total_symbols": 1,
        "eligible": 1,
        "fail_j": 0,
        "fail_insufficient_history": 1,
        "fail_close_zxdkx": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_weekly_ma": 0,
        "fail_max_vol": 0,
        "selected": 0,
    }


def test_run_b1_screen_uses_expanding_history_quantile_per_symbol() -> None:
    pick_date = pd.Timestamp("2026-04-04")
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04"]),
            "open": [10.0, 10.1, 10.2, 10.3],
            "close": [10.2, 10.3, 10.4, 10.5],
            "high": [10.3, 10.4, 10.5, 10.6],
            "low": [9.9, 10.0, 10.1, 10.2],
            "volume": [100.0, 110.0, 120.0, 130.0],
            "J": [50.0, 10.0, 40.0, 13.0],
            "zxdq": [10.0, 10.1, 10.2, 10.6],
            "zxdkx": [9.8, 9.9, 10.0, 10.2],
            "weekly_ma_bull": [True, True, True, True],
            "max_vol_not_bearish": [True, True, True, True],
            "turnover_n": [1000.0, 2000.0, 3000.0, 4000.0],
        }
    )

    candidates = run_b1_screen(
        {"PASS.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert [candidate["code"] for candidate in candidates] == ["PASS.SZ"]
