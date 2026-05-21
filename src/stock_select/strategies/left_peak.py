from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from stock_select.analysis.left_peak import find_recent_left_peak_breakout_prepared
from stock_select.strategies.b1 import compute_expanding_j_quantile

LEFT_PEAK_RECENT_HIGH_LOOKBACK = 15
LEFT_PEAK_J_THRESHOLD = 15.0
LEFT_PEAK_J_Q_THRESHOLD = 0.10
LEFT_PEAK_CLOSE_BAND = 0.05
LEFT_PEAK_MA25_SLOPE_LOOKBACK = 30
LEFT_PEAK_MIN_MA25_ABOVE_MA60 = True

_LEFT_PEAK_REQUIRED_COLUMNS = (
    "trade_date",
    "J",
    "close",
    "ma25",
    "ma60",
    "turnover_n",
    "open",
    "high",
    "low",
    "chg_d",
    "v_shrink",
    "lt_filter",
    "zxdkx",
    "zxdq",
)
_LEFT_PEAK_NUMERIC_COLUMNS = (
    "J",
    "close",
    "ma25",
    "ma60",
    "turnover_n",
    "open",
    "high",
    "low",
    "chg_d",
    "zxdkx",
    "zxdq",
)


@dataclass(frozen=True)
class LeftPeakScreenConfig:
    recent_high_lookback: int = LEFT_PEAK_RECENT_HIGH_LOOKBACK
    j_threshold: float = LEFT_PEAK_J_THRESHOLD
    j_q_threshold: float = LEFT_PEAK_J_Q_THRESHOLD
    close_band: float = LEFT_PEAK_CLOSE_BAND
    ma25_slope_lookback: int = LEFT_PEAK_MA25_SLOPE_LOOKBACK


def run_left_peak_screen(
    prepared_table: pd.DataFrame,
    pick_date: pd.Timestamp,
    config: dict[str, float] | None = None,
) -> list[dict]:
    results, _stats = run_left_peak_screen_with_stats(prepared_table, pick_date, config)
    return results


def run_left_peak_screen_with_stats(
    prepared_table: pd.DataFrame,
    pick_date: pd.Timestamp,
    config: dict[str, float] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    screen_config = _resolve_config(config)
    target_date = pd.Timestamp(pick_date)
    candidates: list[dict] = []
    grouped = prepared_table.groupby("ts_code", sort=False) if not prepared_table.empty else []
    stats = {
        "total_symbols": prepared_table["ts_code"].nunique() if not prepared_table.empty and "ts_code" in prepared_table.columns else 0,
        "eligible": 0,
        "fail_recent_high": 0,
        "fail_recent_j": 0,
        "fail_ma25_ma60": 0,
        "fail_ma25_slope": 0,
        "fail_close_zxdkx": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_chg_cap": 0,
        "fail_v_shrink": 0,
        "fail_lt_filter": 0,
        "fail_insufficient_history": 0,
        "fail_left_peak": 0,
        "fail_left_peak_close_band": 0,
        "selected": 0,
    }

    for code, prepared in grouped:
        if prepared.empty:
            continue

        if _missing_required_columns(prepared):
            stats["eligible"] += 1
            stats["fail_insufficient_history"] += 1
            continue

        frame = _normalize_left_peak_frame(prepared)
        if _has_invalid_required_inputs(prepared, frame):
            stats["eligible"] += 1
            stats["fail_insufficient_history"] += 1
            continue

        history = frame.loc[frame["trade_date"] <= target_date].reset_index(drop=True)
        daily = history.loc[history["trade_date"] == target_date]
        if daily.empty:
            continue

        stats["eligible"] += 1
        if len(history) < max(60, screen_config.recent_high_lookback):
            stats["fail_insufficient_history"] += 1
            continue

        row = daily.iloc[-1]
        recent_window = history.tail(screen_config.recent_high_lookback).copy()
        if not _recent_60d_high_hit(history, recent_window):
            stats["fail_recent_high"] += 1
            continue

        if not _recent_j_rule_hit(history, screen_config):
            stats["fail_recent_j"] += 1
            continue

        if not (float(row["ma25"]) > float(row["ma60"])):
            stats["fail_ma25_ma60"] += 1
            continue

        if not _ma25_slope_positive(history, screen_config):
            stats["fail_ma25_slope"] += 1
            continue

        if not (float(row["close"]) > float(row["zxdkx"])):
            stats["fail_close_zxdkx"] += 1
            continue

        if not (float(row["zxdq"]) > float(row["zxdkx"])):
            stats["fail_zxdq_zxdkx"] += 1
            continue

        if not (float(row["chg_d"]) <= 4.0):
            stats["fail_chg_cap"] += 1
            continue

        if not _flag_is_true(row["v_shrink"]):
            stats["fail_v_shrink"] += 1
            continue

        if not _flag_is_true(row["lt_filter"]):
            stats["fail_lt_filter"] += 1
            continue

        left_peak = find_recent_left_peak_breakout_prepared(history, target_date)
        if not left_peak.is_valid or left_peak.left_peak_high is None:
            stats["fail_left_peak"] += 1
            continue

        close_value = float(row["close"])
        left_peak_high = float(left_peak.left_peak_high)
        lower_bound = left_peak_high * (1.0 - screen_config.close_band)
        upper_bound = left_peak_high * (1.0 + screen_config.close_band)
        if not (lower_bound <= close_value <= upper_bound):
            stats["fail_left_peak_close_band"] += 1
            continue

        candidates.append(
            {
                "code": code,
                "pick_date": target_date.strftime("%Y-%m-%d"),
                "close": close_value,
                "turnover_n": float(row["turnover_n"]),
            }
        )
        stats["selected"] += 1

    return candidates, stats


def iter_left_peak_screen_rows(
    prepared_table: pd.DataFrame,
    pick_date: pd.Timestamp,
    config: dict[str, float] | None = None,
) -> tuple[list[dict[str, float | str]], dict[str, int]]:
    return run_left_peak_screen_with_stats(prepared_table, pick_date, config)


def _resolve_config(config: dict[str, float] | None) -> LeftPeakScreenConfig:
    if config is None:
        return LeftPeakScreenConfig()
    return LeftPeakScreenConfig(
        recent_high_lookback=int(config.get("recent_high_lookback", LEFT_PEAK_RECENT_HIGH_LOOKBACK)),
        j_threshold=float(config.get("j_threshold", LEFT_PEAK_J_THRESHOLD)),
        j_q_threshold=float(config.get("j_q_threshold", LEFT_PEAK_J_Q_THRESHOLD)),
        close_band=float(config.get("close_band", LEFT_PEAK_CLOSE_BAND)),
        ma25_slope_lookback=int(config.get("ma25_slope_lookback", LEFT_PEAK_MA25_SLOPE_LOOKBACK)),
    )


def _recent_60d_high_hit(history: pd.DataFrame, recent_window: pd.DataFrame) -> bool:
    close = history["close"].astype(float)
    rolling_high = close.rolling(window=60, min_periods=60).max()
    recent_indices = recent_window.index
    if len(recent_indices) == 0:
        return False
    recent_high = rolling_high.loc[recent_indices]
    recent_close = close.loc[recent_indices]
    return bool((recent_close >= recent_high).fillna(False).any())


def _recent_j_rule_hit(history: pd.DataFrame, config: LeftPeakScreenConfig) -> bool:
    j_series = history["J"].astype(float)
    recent_j = j_series.tail(config.recent_high_lookback)
    if recent_j.empty:
        return False
    j_quantile = compute_expanding_j_quantile(j_series, config.j_q_threshold).tail(config.recent_high_lookback)
    return bool(((recent_j < config.j_threshold) | (recent_j <= j_quantile)).fillna(False).any())


def _ma25_slope_positive(history: pd.DataFrame, config: LeftPeakScreenConfig) -> bool:
    ma25 = history["ma25"].astype(float).tail(config.ma25_slope_lookback)
    if len(ma25) < config.ma25_slope_lookback or ma25.isna().any():
        return False
    x = pd.Series(range(len(ma25)), dtype=float)
    x_centered = x - float(x.mean())
    y_centered = ma25.reset_index(drop=True) - float(ma25.mean())
    denominator = float((x_centered * x_centered).sum())
    if denominator <= 0.0:
        return False
    slope = float((x_centered * y_centered).sum()) / denominator
    return slope > 0.0


def _missing_required_columns(frame: pd.DataFrame) -> set[str]:
    return set(_LEFT_PEAK_REQUIRED_COLUMNS) - set(frame.columns)


def _normalize_left_peak_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if not pd.api.types.is_datetime64_any_dtype(normalized["trade_date"]):
        normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce", format="mixed")
    for column in _LEFT_PEAK_NUMERIC_COLUMNS:
        if not pd.api.types.is_numeric_dtype(normalized[column]):
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "volume" in normalized.columns:
        if not pd.api.types.is_numeric_dtype(normalized["volume"]):
            normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce")
    elif "vol" in normalized.columns:
        if not pd.api.types.is_numeric_dtype(normalized["vol"]):
            normalized["volume"] = pd.to_numeric(normalized["vol"], errors="coerce")
        else:
            normalized["volume"] = normalized["vol"]
    return normalized.sort_values("trade_date").reset_index(drop=True)


def _coerced_numeric_columns(original: pd.DataFrame, normalized: pd.DataFrame) -> set[str]:
    invalid_columns: set[str] = set()
    for column in _LEFT_PEAK_NUMERIC_COLUMNS:
        original_series = original[column]
        normalized_series = normalized[column]
        invalid_mask = original_series.notna() & normalized_series.isna()
        if bool(invalid_mask.any()):
            invalid_columns.add(column)
    return invalid_columns


def _has_invalid_required_inputs(original: pd.DataFrame, normalized: pd.DataFrame) -> bool:
    return bool(normalized["trade_date"].isna().any() or _coerced_numeric_columns(original, normalized))


def _flag_is_true(value: object) -> bool:
    if pd.isna(value):
        return False
    return bool(value)


__all__ = [
    "LEFT_PEAK_RECENT_HIGH_LOOKBACK",
    "LEFT_PEAK_J_THRESHOLD",
    "LEFT_PEAK_J_Q_THRESHOLD",
    "LEFT_PEAK_CLOSE_BAND",
    "LEFT_PEAK_MA25_SLOPE_LOOKBACK",
    "iter_left_peak_screen_rows",
    "run_left_peak_screen",
    "run_left_peak_screen_with_stats",
]
