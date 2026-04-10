from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from stock_select.strategies.b1 import DEFAULT_B1_CONFIG, compute_expanding_j_quantile

B2_RECENT_J_LOOKBACK = 15
B2_MACD_TREND_DAYS = 5
_B2_REQUIRED_COLUMNS = (
    "trade_date",
    "J",
    "zxdq",
    "zxdkx",
    "weekly_ma_bull",
    "macd_hist",
    "close",
    "turnover_n",
)
_B2_NUMERIC_COLUMNS = (
    "J",
    "zxdq",
    "zxdkx",
    "macd_hist",
    "close",
    "turnover_n",
)


def run_b2_screen(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    config: dict[str, float] | None = None,
) -> list[dict]:
    results, _stats = run_b2_screen_with_stats(prepared_by_symbol, pick_date, config)
    return results


def run_b2_screen_with_stats(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    config: dict[str, float] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    screen_config = DEFAULT_B1_CONFIG if config is None else config
    target_date = pd.Timestamp(pick_date)
    candidates: list[dict] = []
    stats = {
        "total_symbols": len(prepared_by_symbol),
        "eligible": 0,
        "fail_recent_j": 0,
        "fail_insufficient_history": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_weekly_ma": 0,
        "fail_macd_trend": 0,
        "selected": 0,
    }

    for code, prepared in prepared_by_symbol.items():
        if prepared.empty:
            continue

        if _missing_required_columns(prepared):
            stats["eligible"] += 1
            stats["fail_insufficient_history"] += 1
            continue

        frame = _normalize_b2_frame(prepared)
        if _has_invalid_required_inputs(prepared, frame):
            stats["eligible"] += 1
            stats["fail_insufficient_history"] += 1
            continue
        history = frame.loc[frame["trade_date"] <= target_date].reset_index(drop=True)
        daily = history.loc[history["trade_date"] == target_date]
        if daily.empty:
            continue

        stats["eligible"] += 1
        row = daily.iloc[-1]
        recent_j = history["J"].tail(B2_RECENT_J_LOOKBACK)
        recent_macd = history["macd_hist"].tail(B2_MACD_TREND_DAYS)

        if (
            len(history) < B2_RECENT_J_LOOKBACK
            or recent_j.isna().any()
            or pd.isna(row["zxdq"])
            or pd.isna(row["zxdkx"])
            or pd.isna(row["close"])
            or pd.isna(row["turnover_n"])
            or pd.isna(row["weekly_ma_bull"])
        ):
            stats["fail_insufficient_history"] += 1
            continue

        if not _recent_j_rule_hit(history, screen_config):
            stats["fail_recent_j"] += 1
            continue

        if not (float(row["zxdq"]) > float(row["zxdkx"])):
            stats["fail_zxdq_zxdkx"] += 1
            continue

        if not bool(row["weekly_ma_bull"]):
            stats["fail_weekly_ma"] += 1
            continue

        if len(recent_macd) < B2_MACD_TREND_DAYS or recent_macd.isna().any():
            stats["fail_insufficient_history"] += 1
            continue
        if not _is_strictly_increasing(recent_macd):
            stats["fail_macd_trend"] += 1
            continue

        candidates.append(
            {
                "code": code,
                "pick_date": target_date.strftime("%Y-%m-%d"),
                "close": float(row["close"]),
                "turnover_n": float(row["turnover_n"]),
            }
        )
        stats["selected"] += 1

    return candidates, stats


def _recent_j_rule_hit(history: pd.DataFrame, config: dict[str, float]) -> bool:
    j_threshold = float(config.get("j_threshold", DEFAULT_B1_CONFIG["j_threshold"]))
    q_threshold = float(config.get("j_q_threshold", DEFAULT_B1_CONFIG["j_q_threshold"]))
    j_series = history["J"].astype(float)
    j_quantile = compute_expanding_j_quantile(j_series, q_threshold)
    recent = pd.DataFrame({"J": j_series, "j_quantile": j_quantile}).tail(B2_RECENT_J_LOOKBACK)
    return bool(((recent["J"] < j_threshold) | (recent["J"] <= recent["j_quantile"])).any())


def _is_strictly_increasing(values: pd.Series) -> bool:
    diffs = values.astype(float).diff().iloc[1:]
    return bool((diffs > 0.0).all())


def _missing_required_columns(frame: pd.DataFrame) -> set[str]:
    return set(_B2_REQUIRED_COLUMNS) - set(frame.columns)


def _normalize_b2_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce", format="mixed")
    for column in _B2_NUMERIC_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["weekly_ma_bull"] = pd.Series(
        [_normalize_weekly_ma_value(value) for value in normalized["weekly_ma_bull"]],
        index=normalized.index,
        dtype="boolean",
    )
    return normalized


def _normalize_weekly_ma_value(value: Any) -> bool | pd.NA:
    if isinstance(value, (bool,)):
        return value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            scalar = item()
        except Exception:
            scalar = value
        else:
            if isinstance(scalar, bool):
                return scalar
    return pd.NA


def _coerced_numeric_columns(original: pd.DataFrame, normalized: pd.DataFrame) -> set[str]:
    invalid_columns: set[str] = set()
    for column in _B2_NUMERIC_COLUMNS:
        original_series = original[column]
        normalized_series = normalized[column]
        invalid_mask = original_series.notna() & normalized_series.isna()
        if bool(invalid_mask.any()):
            invalid_columns.add(column)
    return invalid_columns


def _coerced_weekly_ma_mask(original: pd.DataFrame) -> pd.Series:
    original_series = original["weekly_ma_bull"]
    normalized = pd.Series(
        [_normalize_weekly_ma_value(value) for value in original_series],
        index=original_series.index,
        dtype="boolean",
    )
    return original_series.notna() & normalized.isna()


def _has_invalid_required_inputs(original: pd.DataFrame, normalized: pd.DataFrame) -> bool:
    return bool(
        normalized["trade_date"].isna().any()
        or _coerced_numeric_columns(original, normalized)
        or _coerced_weekly_ma_mask(original).any()
    )


__all__ = [
    "B2_MACD_TREND_DAYS",
    "B2_RECENT_J_LOOKBACK",
    "run_b2_screen",
    "run_b2_screen_with_stats",
]
