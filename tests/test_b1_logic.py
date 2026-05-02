import pandas as pd

import stock_select.strategies.b1 as strategy_b1
from stock_select.strategies import compute_b1_tightening_columns as exported_compute_b1_tightening_columns
from stock_select.strategies.b1 import (
    DEFAULT_MAX_VOL_LOOKBACK,
    DEFAULT_TOP_M,
    DEFAULT_TURNOVER_WINDOW,
    DEFAULT_WEEKLY_MA_PERIODS,
    build_top_turnover_pool,
    compute_b1_tightening_columns,
    compute_expanding_j_quantile,
    compute_turnover_n,
    compute_weekly_close,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
    run_b1_screen_with_stats,
)
from stock_select.strategies.b1 import (
    DEFAULT_B1_CONFIG,
    DEFAULT_MAX_VOL_LOOKBACK as STRATEGY_DEFAULT_MAX_VOL_LOOKBACK,
    DEFAULT_TOP_M as STRATEGY_DEFAULT_TOP_M,
    DEFAULT_TURNOVER_WINDOW as STRATEGY_DEFAULT_TURNOVER_WINDOW,
    DEFAULT_WEEKLY_MA_PERIODS as STRATEGY_DEFAULT_WEEKLY_MA_PERIODS,
    build_top_turnover_pool as strategy_build_top_turnover_pool,
    compute_zx_lines as strategy_compute_zx_lines,
    run_b1_screen_with_stats as strategy_run_b1_screen_with_stats,
)


def test_b1_strategy_module_exports_current_defaults_and_functions() -> None:
    assert DEFAULT_B1_CONFIG == {"j_threshold": 15.0, "j_q_threshold": 0.10}
    assert STRATEGY_DEFAULT_TURNOVER_WINDOW == DEFAULT_TURNOVER_WINDOW
    assert STRATEGY_DEFAULT_WEEKLY_MA_PERIODS == DEFAULT_WEEKLY_MA_PERIODS
    assert STRATEGY_DEFAULT_MAX_VOL_LOOKBACK == DEFAULT_MAX_VOL_LOOKBACK
    assert STRATEGY_DEFAULT_TOP_M == DEFAULT_TOP_M
    assert set(strategy_b1.__all__) == {
        "DEFAULT_B1_CONFIG",
        "DEFAULT_MAX_VOL_LOOKBACK",
        "DEFAULT_TOP_M",
        "DEFAULT_TURNOVER_WINDOW",
        "DEFAULT_WEEKLY_MA_PERIODS",
        "build_top_turnover_pool",
        "compute_b1_tightening_columns",
        "compute_expanding_j_quantile",
        "compute_kdj",
        "compute_macd",
        "compute_turnover_n",
        "compute_weekly_close",
        "compute_weekly_ma_bull",
        "compute_zx_lines",
        "max_vol_not_bearish",
        "run_b1_screen",
        "run_b1_screen_with_stats",
    }
    assert exported_compute_b1_tightening_columns is compute_b1_tightening_columns
    assert strategy_run_b1_screen_with_stats is run_b1_screen_with_stats
    assert strategy_build_top_turnover_pool is build_top_turnover_pool
    assert strategy_compute_zx_lines is compute_zx_lines


def test_b1_strategy_module_is_primary_implementation_owner() -> None:
    assert strategy_b1.compute_turnover_n.__module__ == "stock_select.strategies.b1"
    assert strategy_b1.run_b1_screen_with_stats.__module__ == "stock_select.strategies.b1"


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


def test_compute_b1_tightening_columns_keeps_lt_waiver_after_pre114_crossover() -> None:
    close = [
        50.0,
        50.05,
        49.9,
        49.95,
        49.9,
        49.85,
        49.7,
        49.5,
        49.4,
        49.45,
        49.3,
        49.3,
        49.3,
        49.3,
        49.1,
        48.95,
        48.75,
        48.75,
        48.75,
        48.7,
        48.6,
        48.45,
        48.4,
        48.35,
        48.4,
        48.3,
        48.1,
        48.1,
        47.9,
        47.75,
        47.75,
        47.7,
        47.65,
        47.7,
        47.7,
        47.65,
        47.7,
        47.55,
        47.5,
        47.4,
        47.2,
        47.1,
        47.15,
        47.2,
        47.05,
        46.95,
        47.0,
        46.9,
        46.9,
        46.85,
        46.9,
        46.95,
        46.95,
        46.75,
        46.6,
        46.4,
        46.45,
        46.45,
        46.45,
        46.4,
        46.2,
        46.25,
        46.3,
        46.2,
        46.1,
        46.1,
        45.95,
        45.9,
        45.8,
        45.85,
        45.65,
        45.45,
        45.35,
        45.15,
        45.1,
        45.1,
        45.1,
        45.1,
        45.15,
        45.2,
        45.15,
        45.1,
        45.1,
        45.0,
        45.05,
        45.05,
        45.0,
        45.0,
        45.05,
        45.1,
        45.0,
        44.8,
        44.65,
        44.6,
        44.65,
        44.7,
        44.65,
        44.7,
        44.5,
        44.5,
        44.4,
        44.4,
        44.45,
        44.45,
        44.5,
        45.1,
        45.7,
        46.2,
        46.7,
        47.2,
        48.0,
        48.8,
        49.4,
        49.8,
        48.8,
        47.8,
        48.8,
        47.3,
        46.3,
        44.8,
        46.3,
        47.5,
        48.7,
        49.7,
        50.7,
        49.5,
        50.5,
        49.5,
        50.5,
        49.0,
        47.8,
        46.3,
        46.3,
        46.3,
        46.35,
        46.3,
        46.3,
        46.3,
        46.3,
        46.3,
        46.25,
        46.2,
        46.2,
        46.2,
        46.25,
        46.3,
        46.25,
        46.25,
        46.3,
        46.25,
        46.3,
        46.3,
        46.3,
        46.35,
        46.35,
        46.3,
        46.25,
        46.2,
        46.2,
        46.15,
    ]
    df = pd.DataFrame(
        {
            "open": [value - 0.1 for value in close],
            "high": [value + 0.2 for value in close],
            "low": [value - 0.2 for value in close],
            "close": close,
            "vol": [1000.0] * len(close),
        }
    )

    out = compute_b1_tightening_columns(df)

    assert bool(out.loc[131, "lt_filter"]) is True


def test_compute_b1_tightening_columns_reenables_safe_mode_after_cool_off() -> None:
    close = [10.0 + idx * 0.12 for idx in range(20)] + [12.0, 11.7, 11.5, 11.3, 11.1, 10.9]
    open_ = [value - 0.05 for value in close]
    open_[20] = 13.4
    high = [max(open_price, close_price) + 0.1 for open_price, close_price in zip(open_, close)]
    low = [min(open_price, close_price) - 0.1 for open_price, close_price in zip(open_, close)]
    volume = [1000.0] * 20 + [4000.0, 1100.0, 1050.0, 1000.0, 950.0, 900.0]
    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "vol": volume,
        }
    )

    out = compute_b1_tightening_columns(df)

    assert bool(out.loc[20, "safe_mode"]) is False
    assert bool(out.loc[24, "safe_mode"]) is False
    assert bool(out.loc[25, "safe_mode"]) is True


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
        pd.concat(
            [
                pd.DataFrame(
                    {
                        "ts_code": ["AAA.SZ", "AAA.SZ"],
                        "trade_date": pd.to_datetime(["2026-04-02", "2026-04-03"]),
                        "turnover_n": [100.0, 400.0],
                        "ma25": [11.0, 11.0],
                        "ma60": [10.0, 10.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "ts_code": ["BBB.SZ", "BBB.SZ"],
                        "trade_date": pd.to_datetime(["2026-04-02", "2026-04-03"]),
                        "turnover_n": [300.0, 200.0],
                        "ma25": [11.0, 11.0],
                        "ma60": [10.0, 10.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "ts_code": ["CCC.SZ", "CCC.SZ"],
                        "trade_date": pd.to_datetime(["2026-04-02", "2026-04-03"]),
                        "turnover_n": [200.0, 300.0],
                        "ma25": [11.0, 11.0],
                        "ma60": [10.0, 10.0],
                    }
                ),
            ],
            ignore_index=True,
        ),
        top_m=2,
    )

    assert pool[pd.Timestamp("2026-04-02")] == ["BBB.SZ", "CCC.SZ"]
    assert pool[pd.Timestamp("2026-04-03")] == ["AAA.SZ", "CCC.SZ"]


def test_build_top_turnover_pool_skips_malformed_rows() -> None:
    pool = build_top_turnover_pool(
        pd.concat(
            [
                pd.DataFrame(
                    {
                        "ts_code": ["AAA.SZ", "AAA.SZ"],
                        "trade_date": ["not-a-date", "2026-04-03"],
                        "turnover_n": [100.0, "boom"],
                        "ma25": [11.0, 11.0],
                        "ma60": [10.0, 10.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "ts_code": ["AAB.SZ"],
                        "trade_date": pd.to_datetime(["2026-04-02"]),
                        "ma25": [11.0],
                        "ma60": [10.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "ts_code": ["BBB.SZ", "BBB.SZ"],
                        "trade_date": pd.to_datetime(["2026-04-02", "2026-04-03"]),
                        "turnover_n": [300.0, 200.0],
                        "ma25": [11.0, 11.0],
                        "ma60": [10.0, 10.0],
                    }
                ),
            ],
            ignore_index=True,
        ),
        top_m=2,
    )

    assert pool == {
        pd.Timestamp("2026-04-02"): ["BBB.SZ"],
        pd.Timestamp("2026-04-03"): ["BBB.SZ"],
    }


def test_build_top_turnover_pool_requires_ma25_above_ma60() -> None:
    pool = build_top_turnover_pool(
        pd.concat(
            [
                pd.DataFrame(
                    {
                        "ts_code": ["AAA.SZ"],
                        "trade_date": ["2026-04-24"],
                        "turnover_n": [200.0],
                        "ma25": [10.5],
                        "ma60": [10.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "ts_code": ["BBB.SZ"],
                        "trade_date": ["2026-04-24"],
                        "turnover_n": [300.0],
                        "ma25": [9.8],
                        "ma60": [10.0],
                    }
                ),
            ],
            ignore_index=True,
        ),
        top_m=5,
    )

    assert pool == {pd.Timestamp("2026-04-24"): ["AAA.SZ"]}


def test_build_top_turnover_pool_skips_rows_missing_ma25_or_ma60() -> None:
    pool = build_top_turnover_pool(
        pd.concat(
            [
                pd.DataFrame(
                    {
                        "ts_code": ["AAA.SZ"],
                        "trade_date": ["2026-04-24"],
                        "turnover_n": [200.0],
                        "ma25": [None],
                        "ma60": [10.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "ts_code": ["BBB.SZ"],
                        "trade_date": ["2026-04-24"],
                        "turnover_n": [180.0],
                        "ma25": [10.2],
                        "ma60": [None],
                    }
                ),
                pd.DataFrame(
                    {
                        "ts_code": ["CCC.SZ"],
                        "trade_date": ["2026-04-24"],
                        "turnover_n": [160.0],
                        "ma25": [10.3],
                        "ma60": [10.0],
                    }
                ),
            ],
            ignore_index=True,
        ),
        top_m=5,
    )

    assert pool == {pd.Timestamp("2026-04-24"): ["CCC.SZ"]}


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
            "chg_d": [0.5, 0.6, 1.0],
            "amp_d": [2.0, 2.1, 2.2],
            "body_d": [-1.0, -1.0, -1.0],
            "vm3": [100.0, 110.0, 90.0],
            "vm5": [100.0, 110.0, 105.0],
            "vm10": [100.0, 110.0, 120.0],
            "m5": [10.2, 10.4, 10.6],
            "v_shrink": [True, True, True],
            "safe_mode": [True, True, True],
            "lt_filter": [True, True, True],
            "turnover_n": [1020.0, 2280.0, 3892.5],
        }
    )
    failing = passing.copy()
    failing["close"] = [10.4, 10.8, 10.3]

    passing["ts_code"] = "000001.SZ"
    failing["ts_code"] = "000002.SZ"
    result = run_b1_screen(
        pd.concat([passing, failing], ignore_index=True),
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
        chg_d: float = 1.0,
        v_shrink: bool = True,
        safe_mode: bool = True,
        lt_filter: bool = True,
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
                "chg_d": [0.5, 0.6, chg_d],
                "amp_d": [2.0, 2.1, 2.2],
                "body_d": [-1.0, -1.0, -1.0],
                "vm3": [100.0, 110.0, 90.0],
                "vm5": [100.0, 110.0, 105.0],
                "vm10": [100.0, 110.0, 120.0],
                "m5": [10.2, 10.4, 10.6],
                "v_shrink": [True, True, v_shrink],
                "safe_mode": [True, True, safe_mode],
                "lt_filter": [True, True, lt_filter],
                "turnover_n": [1020.0, 2280.0, 3892.5],
            }
        )

    prepared_frames = {}
    for _code, _frame in [
        ("PASS.SZ", make_frame()),
        ("FAILJ.SZ", make_frame(j=85.0)),
        ("FAILCLOSE.SZ", make_frame(close=10.2)),
        ("FAILZXDQ.SZ", make_frame(zxdq=10.1)),
        ("FAILWEEKLY.SZ", make_frame(weekly_ma_bull=False)),
        ("FAILMAXVOL.SZ", make_frame(max_vol_not_bearish_value=False)),
        ("FAILCHG.SZ", make_frame(chg_d=5.2)),
        ("FAILSHRINK.SZ", make_frame(v_shrink=False)),
        ("FAILSAFE.SZ", make_frame(safe_mode=False)),
        ("FAILLT.SZ", make_frame(lt_filter=False)),
        ("MISSING.SZ", make_frame().iloc[[0, 1]].copy()),
    ]:
        _frame["ts_code"] = _code
        prepared_frames[_code] = _frame

    candidates, stats = run_b1_screen_with_stats(
        pd.concat(list(prepared_frames.values()), ignore_index=True),
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert [candidate["code"] for candidate in candidates] == ["PASS.SZ"]
    assert stats == {
        "total_symbols": 11,
        "eligible": 10,
        "fail_j": 1,
        "fail_insufficient_history": 0,
        "fail_close_zxdkx": 1,
        "fail_zxdq_zxdkx": 1,
        "fail_weekly_ma": 1,
        "fail_max_vol": 1,
        "fail_chg_cap": 1,
        "fail_v_shrink": 1,
        "fail_safe_mode": 1,
        "fail_lt_filter": 1,
        "selected": 1,
    }


def test_run_b1_screen_with_stats_keeps_legacy_order_before_new_filters() -> None:
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
            "zxdkx": [10.0, 10.2, 10.4],
            "weekly_ma_bull": [True, True, False],
            "max_vol_not_bearish": [True, True, True],
            "chg_d": [0.5, 0.6, 5.5],
            "amp_d": [2.0, 2.0, 2.0],
            "body_d": [-1.0, -1.0, -1.0],
            "vm3": [90.0, 90.0, 150.0],
            "vm5": [95.0, 95.0, 120.0],
            "vm10": [100.0, 100.0, 110.0],
            "m5": [10.2, 10.4, 10.6],
            "v_shrink": [True, True, False],
            "safe_mode": [True, True, False],
            "lt_filter": [True, True, False],
            "turnover_n": [1020.0, 2280.0, 3892.5],
        }
    )

    frame["ts_code"] = "ORDER.SZ"
    _, stats = run_b1_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert stats["fail_weekly_ma"] == 1
    assert stats["fail_chg_cap"] == 0
    assert stats["fail_v_shrink"] == 0
    assert stats["fail_safe_mode"] == 0
    assert stats["fail_lt_filter"] == 0


def test_run_b1_screen_with_stats_counts_missing_tightening_columns_as_insufficient_history() -> None:
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
            "zxdkx": [10.0, 10.2, 10.4],
            "weekly_ma_bull": [True, True, True],
            "max_vol_not_bearish": [True, True, True],
            "turnover_n": [1020.0, 2280.0, 3892.5],
        }
    )

    frame["ts_code"] = "MISSINGTIGHTENING.SZ"
    candidates, stats = run_b1_screen_with_stats(
        frame,
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
        "fail_chg_cap": 0,
        "fail_v_shrink": 0,
        "fail_safe_mode": 0,
        "fail_lt_filter": 0,
        "selected": 0,
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

    frame["ts_code"] = "MISSINGZXDKX.SZ"
    candidates, stats = run_b1_screen_with_stats(
        frame,
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
        "fail_chg_cap": 0,
        "fail_v_shrink": 0,
        "fail_safe_mode": 0,
        "fail_lt_filter": 0,
        "selected": 0,
    }


def test_run_b1_screen_with_stats_counts_nan_tightening_booleans_as_first_failures() -> None:
    pick_date = pd.Timestamp("2026-04-03")

    def make_frame(
        *,
        v_shrink: object = True,
        safe_mode: object = True,
        lt_filter: object = True,
    ) -> pd.DataFrame:
        return pd.DataFrame(
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
                "chg_d": [0.5, 0.6, 1.0],
                "amp_d": [2.0, 2.1, 2.2],
                "body_d": [-1.0, -1.0, -1.0],
                "vm3": [100.0, 110.0, 90.0],
                "vm5": [100.0, 110.0, 105.0],
                "vm10": [100.0, 110.0, 120.0],
                "m5": [10.2, 10.4, 10.6],
                "v_shrink": [True, True, v_shrink],
                "safe_mode": [True, True, safe_mode],
                "lt_filter": [True, True, lt_filter],
                "turnover_n": [1020.0, 2280.0, 3892.5],
            }
        )

    prepared_frames = []
    for _code, _kwargs in [
        ("NANSHRINK.SZ", {"v_shrink": float("nan")}),
        ("NANSAFE.SZ", {"safe_mode": float("nan")}),
        ("NANLT.SZ", {"lt_filter": float("nan")}),
    ]:
        _frame = make_frame(**_kwargs)
        _frame["ts_code"] = _code
        prepared_frames.append(_frame)

    candidates, stats = run_b1_screen_with_stats(
        pd.concat(prepared_frames, ignore_index=True),
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert candidates == []
    assert stats["fail_v_shrink"] == 1
    assert stats["fail_safe_mode"] == 1
    assert stats["fail_lt_filter"] == 1
    assert stats["selected"] == 0


def test_run_b1_screen_with_stats_counts_only_earliest_new_failure() -> None:
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
            "zxdkx": [10.0, 10.2, 10.4],
            "weekly_ma_bull": [True, True, True],
            "max_vol_not_bearish": [True, True, True],
            "chg_d": [0.5, 0.6, 5.5],
            "amp_d": [2.0, 2.1, 2.2],
            "body_d": [-1.0, -1.0, -1.0],
            "vm3": [100.0, 110.0, 150.0],
            "vm5": [100.0, 110.0, 105.0],
            "vm10": [100.0, 110.0, 120.0],
            "m5": [10.2, 10.4, 10.6],
            "v_shrink": [True, True, False],
            "safe_mode": [True, True, False],
            "lt_filter": [True, True, False],
            "turnover_n": [1020.0, 2280.0, 3892.5],
        }
    )

    frame["ts_code"] = "ORDERNEW.SZ"
    _, stats = run_b1_screen_with_stats(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert stats["fail_chg_cap"] == 1
    assert stats["fail_v_shrink"] == 0
    assert stats["fail_safe_mode"] == 0
    assert stats["fail_lt_filter"] == 0


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
            "chg_d": [0.5, 0.6, 0.7, 0.8],
            "amp_d": [2.0, 2.1, 2.2, 2.3],
            "body_d": [-1.0, -1.0, -1.0, -1.0],
            "vm3": [100.0, 105.0, 110.0, 90.0],
            "vm5": [100.0, 105.0, 110.0, 100.0],
            "vm10": [100.0, 105.0, 110.0, 120.0],
            "m5": [10.0, 10.1, 10.2, 10.3],
            "v_shrink": [True, True, True, True],
            "safe_mode": [True, True, True, True],
            "lt_filter": [True, True, True, True],
            "turnover_n": [1000.0, 2000.0, 3000.0, 4000.0],
        }
    )

    frame["ts_code"] = "PASS.SZ"
    candidates = run_b1_screen(
        frame,
        pick_date=pick_date,
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert [candidate["code"] for candidate in candidates] == ["PASS.SZ"]
