from __future__ import annotations

import pandas as pd

HCR_RESONANCE_TOLERANCE_PCT = 0.015
HCR_MIN_CLOSE = 1.0


def compute_hcr_yx(frame: pd.DataFrame) -> pd.Series:
    high_30 = frame["high"].astype(float).rolling(window=30, min_periods=30).max()
    low_30 = frame["low"].astype(float).rolling(window=30, min_periods=30).min()
    return (high_30 + low_30) / 2.0


def compute_hcr_reference_price(frame: pd.DataFrame) -> pd.Series:
    rolling_high = frame["high"].astype(float).rolling(window=300, min_periods=300).max()
    shifted = rolling_high.shift(60)
    if shifted.empty:
        return shifted
    last_value = shifted.iloc[-1]
    if pd.isna(last_value):
        return pd.Series(pd.NA, index=frame.index, dtype="Float64")
    return pd.Series(float(last_value), index=frame.index, dtype=float)


def prepare_hcr_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"])
    prepared["yx"] = compute_hcr_yx(prepared)
    prepared["p"] = compute_hcr_reference_price(prepared)
    prepared["resonance_gap_pct"] = (prepared["yx"] - prepared["p"]).abs() / prepared["p"].abs()
    return prepared


def run_hcr_screen_with_stats(
    prepared_by_symbol: dict[str, pd.DataFrame],
    pick_date: pd.Timestamp,
) -> tuple[list[dict], dict[str, int]]:
    target_date = pd.Timestamp(pick_date)
    candidates: list[dict] = []
    stats = {
        "total_symbols": len(prepared_by_symbol),
        "eligible": 0,
        "fail_insufficient_history": 0,
        "fail_resonance": 0,
        "fail_close_floor": 0,
        "fail_breakout": 0,
        "selected": 0,
    }

    for code, frame in prepared_by_symbol.items():
        trade_dates = pd.to_datetime(frame["trade_date"])
        daily = frame.loc[trade_dates == target_date]
        if daily.empty:
            continue
        stats["eligible"] += 1
        row = daily.iloc[-1]
        if pd.isna(row["yx"]) or pd.isna(row["p"]) or float(row["p"]) == 0.0:
            stats["fail_insufficient_history"] += 1
            continue
        if float(row["resonance_gap_pct"]) > HCR_RESONANCE_TOLERANCE_PCT:
            stats["fail_resonance"] += 1
            continue
        if float(row["close"]) <= HCR_MIN_CLOSE:
            stats["fail_close_floor"] += 1
            continue
        if float(row["close"]) <= float(row["yx"]):
            stats["fail_breakout"] += 1
            continue
        candidates.append(
            {
                "code": code,
                "pick_date": target_date.strftime("%Y-%m-%d"),
                "close": float(row["close"]),
                "turnover_n": float(row["turnover_n"]),
                "yx": float(row["yx"]),
                "p": float(row["p"]),
                "resonance_gap_pct": float(row["resonance_gap_pct"]),
            }
        )
        stats["selected"] += 1

    return candidates, stats
