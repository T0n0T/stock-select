from stock_select.strategies.b1 import (
    DEFAULT_B1_CONFIG,
    DEFAULT_MAX_VOL_LOOKBACK,
    DEFAULT_TOP_M,
    DEFAULT_TURNOVER_WINDOW,
    DEFAULT_WEEKLY_MA_PERIODS,
    build_top_turnover_pool,
    compute_expanding_j_quantile,
    compute_kdj,
    compute_macd,
    compute_turnover_n,
    compute_weekly_close,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
    run_b1_screen_with_stats,
)
from stock_select.strategies.b2 import (
    B2_MACD_TREND_DAYS,
    B2_RECENT_J_LOOKBACK,
    prefilter_b2_non_macd,
    run_b2_screen,
    run_b2_screen_with_stats,
)

SUPPORTED_METHODS = ("b1", "b2", "hcr")


def normalize_method(method: str) -> str:
    return method.strip().lower()


def validate_method(method: str) -> str:
    normalized = normalize_method(method)
    if normalized not in SUPPORTED_METHODS:
        msg = f"Supported methods: {', '.join(SUPPORTED_METHODS)}"
        raise ValueError(msg)
    return normalized


__all__ = [
    "B2_MACD_TREND_DAYS",
    "B2_RECENT_J_LOOKBACK",
    "prefilter_b2_non_macd",
    "DEFAULT_B1_CONFIG",
    "DEFAULT_MAX_VOL_LOOKBACK",
    "DEFAULT_TOP_M",
    "DEFAULT_TURNOVER_WINDOW",
    "DEFAULT_WEEKLY_MA_PERIODS",
    "SUPPORTED_METHODS",
    "build_top_turnover_pool",
    "compute_expanding_j_quantile",
    "compute_kdj",
    "compute_macd",
    "compute_turnover_n",
    "compute_weekly_close",
    "compute_weekly_ma_bull",
    "compute_zx_lines",
    "max_vol_not_bearish",
    "normalize_method",
    "run_b1_screen",
    "run_b1_screen_with_stats",
    "run_b2_screen",
    "run_b2_screen_with_stats",
    "validate_method",
]
