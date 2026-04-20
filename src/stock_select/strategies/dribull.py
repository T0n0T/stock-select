from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
from stock_select.analysis.macd_waves import classify_daily_macd_wave, classify_weekly_macd_wave
from stock_select.strategies.b1 import DEFAULT_B1_CONFIG, compute_expanding_j_quantile

DRIBULL_RECENT_J_LOOKBACK = 15
DRIBULL_MACD_TREND_DAYS = 5
_DRIBULL_REQUIRED_COLUMNS = (
    "trade_date",
    "J",
    "zxdq",
    "zxdkx",
    "low",
    "close",
    "ma25",
    "ma60",
    "ma144",
    "turnover_n",
)
_DRIBULL_NUMERIC_COLUMNS = (
    "J",
    "zxdq",
    "zxdkx",
    "low",
    "close",
    "ma25",
    "ma60",
    "ma144",
    "turnover_n",
)


def run_dribull_screen(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    config: dict[str, float] | None = None,
) -> list[dict]:
    results, _stats = run_dribull_screen_with_stats(prepared_by_symbol, pick_date, config)
    return results


def prefilter_dribull_non_macd(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    config: dict[str, float] | None = None,
) -> list[str]:
    screen_config = DEFAULT_B1_CONFIG if config is None else config
    target_date = pd.Timestamp(pick_date)
    selected: list[str] = []

    for code, prepared in prepared_by_symbol.items():
        if prepared.empty or _missing_required_columns(prepared):
            continue

        frame = _normalize_dribull_frame(prepared)
        if _has_invalid_required_inputs(prepared, frame):
            continue

        history = frame.loc[frame["trade_date"] <= target_date].reset_index(drop=True)
        daily = history.loc[history["trade_date"] == target_date]
        if daily.empty:
            continue

        row = daily.iloc[-1]
        if not _has_minimum_history(history):
            continue
        if not _recent_j_rule_hit(history, screen_config):
            continue
        if not (float(row["zxdq"]) > float(row["zxdkx"])):
            continue
        if not _support_valid(row):
            continue
        if not _volume_shrink(history):
            continue
        if not _ma60_up(history):
            continue
        if not _ma144_distance_ok(row):
            continue

        selected.append(code)

    return selected


def run_dribull_screen_with_stats(
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
        "fail_support_ma25": 0,
        "fail_volume_shrink": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_ma60_trend": 0,
        "fail_ma144_distance": 0,
        "fail_weekly_wave": 0,
        "fail_daily_wave": 0,
        "fail_wave_combo": 0,
        "selected": 0,
    }

    for code, prepared in prepared_by_symbol.items():
        if prepared.empty:
            continue

        if _missing_required_columns(prepared):
            stats["eligible"] += 1
            stats["fail_insufficient_history"] += 1
            continue

        frame = _normalize_dribull_frame(prepared)
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

        if not _has_minimum_history(history):
            stats["fail_insufficient_history"] += 1
            continue

        if not _recent_j_rule_hit(history, screen_config):
            stats["fail_recent_j"] += 1
            continue

        if not (float(row["zxdq"]) > float(row["zxdkx"])):
            stats["fail_zxdq_zxdkx"] += 1
            continue

        if not _support_valid(row):
            stats["fail_support_ma25"] += 1
            continue

        if not _volume_shrink(history):
            stats["fail_volume_shrink"] += 1
            continue

        if not _ma60_up(history):
            stats["fail_ma60_trend"] += 1
            continue

        if not _ma144_distance_ok(row):
            stats["fail_ma144_distance"] += 1
            continue

        weekly_wave = classify_weekly_macd_wave(
            history[["trade_date", "close"]],
            target_date.strftime("%Y-%m-%d"),
        )
        if weekly_wave.label not in {"wave1", "wave3"}:
            stats["fail_weekly_wave"] += 1
            continue

        daily_wave = classify_daily_macd_wave(
            history[["trade_date", "close"]],
            target_date.strftime("%Y-%m-%d"),
        )
        if daily_wave.label == "invalid":
            stats["fail_daily_wave"] += 1
            continue

        if daily_wave.label not in {"wave2_end", "wave4_end"}:
            stats["fail_wave_combo"] += 1
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


def _missing_required_columns(frame: pd.DataFrame) -> set[str]:
    return set(_DRIBULL_REQUIRED_COLUMNS) - set(frame.columns)


def _normalize_dribull_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce", format="mixed")
    for column in _DRIBULL_NUMERIC_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "volume" in normalized.columns:
        normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce")
    elif "vol" in normalized.columns:
        normalized["volume"] = pd.to_numeric(normalized["vol"], errors="coerce")
    return normalized


def _coerced_numeric_columns(original: pd.DataFrame, normalized: pd.DataFrame) -> set[str]:
    invalid_columns: set[str] = set()
    for column in _DRIBULL_NUMERIC_COLUMNS:
        original_series = original[column]
        normalized_series = normalized[column]
        invalid_mask = original_series.notna() & normalized_series.isna()
        if bool(invalid_mask.any()):
            invalid_columns.add(column)
    if "volume" in original.columns:
        volume_mask = original["volume"].notna() & normalized["volume"].isna()
        if bool(volume_mask.any()):
            invalid_columns.add("volume")
    elif "vol" in original.columns:
        volume_mask = original["vol"].notna() & normalized["volume"].isna()
        if bool(volume_mask.any()):
            invalid_columns.add("volume")
    return invalid_columns


def _has_invalid_required_inputs(original: pd.DataFrame, normalized: pd.DataFrame) -> bool:
    return bool(normalized["trade_date"].isna().any() or _coerced_numeric_columns(original, normalized))


def _has_minimum_history(history: pd.DataFrame) -> bool:
    if len(history) < max(DRIBULL_RECENT_J_LOOKBACK, 144):
        return False
    if history["J"].tail(DRIBULL_RECENT_J_LOOKBACK).isna().any():
        return False
    if len(history) < 2:
        return False
    required_today = (
        "zxdq",
        "zxdkx",
        "low",
        "close",
        "ma25",
        "ma60",
        "ma144",
        "turnover_n",
        "volume",
    )
    row = history.iloc[-1]
    if any(pd.isna(row[column]) for column in required_today):
        return False
    previous_row = history.iloc[-2]
    if pd.isna(previous_row["ma60"]) or pd.isna(previous_row["volume"]):
        return False
    return True


def _recent_j_rule_hit(history: pd.DataFrame, config: dict[str, float]) -> bool:
    j_threshold = float(config.get("j_threshold", DEFAULT_B1_CONFIG["j_threshold"]))
    q_threshold = float(config.get("j_q_threshold", DEFAULT_B1_CONFIG["j_q_threshold"]))
    j_series = history["J"].astype(float)
    j_quantile = compute_expanding_j_quantile(j_series, q_threshold)
    recent = pd.DataFrame({"J": j_series, "j_quantile": j_quantile}).tail(DRIBULL_RECENT_J_LOOKBACK)
    return bool(((recent["J"] < j_threshold) | (recent["J"] <= recent["j_quantile"])).any())


def _support_valid(row: pd.Series) -> bool:
    ma25 = float(row["ma25"])
    low = float(row["low"])
    close = float(row["close"])
    return bool(low <= ma25 * 1.005 and close >= ma25)


def _volume_shrink(history: pd.DataFrame) -> bool:
    latest_volume = float(history.iloc[-1]["volume"])
    previous_volume = float(history.iloc[-2]["volume"])
    return latest_volume < previous_volume


def _macd_red(dif: float, dea: float) -> bool:
    return float(dif) > float(dea)


def _ma60_up(history: pd.DataFrame) -> bool:
    latest_ma60 = float(history.iloc[-1]["ma60"])
    previous_ma60 = float(history.iloc[-2]["ma60"])
    return latest_ma60 >= previous_ma60


def _ma144_distance_ok(row: pd.Series) -> bool:
    close = float(row["close"])
    ma144 = float(row["ma144"])
    distance = abs((close / ma144 - 1.0) * 100.0)
    return distance <= 30.0


__all__ = [
    "DRIBULL_MACD_TREND_DAYS",
    "DRIBULL_RECENT_J_LOOKBACK",
    "prefilter_dribull_non_macd",
    "run_dribull_screen",
    "run_dribull_screen_with_stats",
]
