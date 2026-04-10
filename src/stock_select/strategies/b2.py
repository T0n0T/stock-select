from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from stock_select.strategies.b1 import DEFAULT_B1_CONFIG, compute_expanding_j_quantile

B2_RECENT_J_LOOKBACK = 15
B2_MACD_TREND_DAYS = 5


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

        frame = prepared.copy()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        history = frame.loc[frame["trade_date"] <= target_date].reset_index(drop=True)
        daily = history.loc[history["trade_date"] == target_date]
        if daily.empty:
            continue

        stats["eligible"] += 1
        row = daily.iloc[-1]

        if (
            len(history) < B2_RECENT_J_LOOKBACK
            or pd.isna(row["zxdq"])
            or pd.isna(row["zxdkx"])
        ):
            stats["fail_insufficient_history"] += 1
            continue

        if not _recent_j_rule_hit(history, screen_config):
            stats["fail_recent_j"] += 1
            continue

        if not (float(row["zxdq"]) > float(row["zxdkx"])):
            stats["fail_zxdq_zxdkx"] += 1
            continue

        if pd.isna(row["weekly_ma_bull"]) or not bool(row["weekly_ma_bull"]):
            stats["fail_weekly_ma"] += 1
            continue

        macd_hist = history["macd_hist"].dropna().astype(float)
        if len(macd_hist) < B2_MACD_TREND_DAYS:
            stats["fail_insufficient_history"] += 1
            continue
        if not _is_strictly_increasing(macd_hist.tail(B2_MACD_TREND_DAYS)):
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


__all__ = [
    "B2_MACD_TREND_DAYS",
    "B2_RECENT_J_LOOKBACK",
    "run_b2_screen",
    "run_b2_screen_with_stats",
]
