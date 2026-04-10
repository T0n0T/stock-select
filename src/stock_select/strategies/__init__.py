from stock_select.strategies.b1 import (
    DEFAULT_B1_CONFIG,
    DEFAULT_MAX_VOL_LOOKBACK,
    DEFAULT_TOP_M,
    DEFAULT_TURNOVER_WINDOW,
    DEFAULT_WEEKLY_MA_PERIODS,
    build_top_turnover_pool,
    compute_expanding_j_quantile,
    compute_kdj,
    compute_turnover_n,
    compute_weekly_close,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
    run_b1_screen_with_stats,
)

SUPPORTED_METHODS = ("b1", "hcr")


def normalize_method(method: str) -> str:
    return method.strip().lower()


def validate_method(method: str) -> str:
    normalized = normalize_method(method)
    if normalized not in SUPPORTED_METHODS:
        msg = f"Supported methods: {', '.join(SUPPORTED_METHODS)}"
        raise ValueError(msg)
    return normalized
