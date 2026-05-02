from __future__ import annotations

import pandas as pd

HCR_RESONANCE_TOLERANCE_PCT = 0.005
HCR_MIN_CLOSE = 1.0
HCR_REFERENCE_LOOKBACK_DAYS = 180
HCR_REFERENCE_SHIFT_DAYS = 60
HCR_REQUIRED_TRADING_DAYS = HCR_REFERENCE_LOOKBACK_DAYS + HCR_REFERENCE_SHIFT_DAYS


def compute_hcr_yx(frame: pd.DataFrame) -> pd.Series:
    high_30 = frame["high"].astype(float).rolling(window=30, min_periods=30).max()
    low_30 = frame["low"].astype(float).rolling(window=30, min_periods=30).min()
    return (high_30 + low_30) / 2.0


def compute_hcr_reference_price(frame: pd.DataFrame) -> pd.Series:
    rolling_high = frame["high"].astype(float).rolling(
        window=HCR_REFERENCE_LOOKBACK_DAYS,
        min_periods=HCR_REFERENCE_LOOKBACK_DAYS,
    ).max()
    shifted = rolling_high.shift(HCR_REFERENCE_SHIFT_DAYS)
    if shifted.empty:
        return shifted
    last_value = shifted.iloc[-1]
    if pd.isna(last_value):
        return pd.Series(pd.NA, index=frame.index, dtype="Float64")
    return pd.Series(float(last_value), index=frame.index, dtype=float)


def prepare_hcr_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"])
    close = prepared["close"].astype(float)
    prepared["ma25"] = close.rolling(window=25, min_periods=25).mean()
    prepared["ma60"] = close.rolling(window=60, min_periods=60).mean()
    prepared["yx"] = compute_hcr_yx(prepared)
    prepared["p"] = compute_hcr_reference_price(prepared)
    prepared["resonance_gap_pct"] = (prepared["yx"] - prepared["p"]).abs() / prepared["p"].abs()
    return prepared


def _score_hcr_resonance(*, resonance_gap_pct: float) -> float:
    if resonance_gap_pct <= 0.0010:
        return 30.0
    if resonance_gap_pct <= 0.0015:
        return 26.0
    if resonance_gap_pct <= 0.0030:
        return 20.0
    if resonance_gap_pct <= HCR_RESONANCE_TOLERANCE_PCT:
        return 12.0
    return 0.0


def _score_hcr_close_extension(*, close_above_ma25_pct: float) -> float:
    if close_above_ma25_pct < 0.0:
        return 4.0
    if close_above_ma25_pct < 4.0:
        return 10.0
    if close_above_ma25_pct < 8.0:
        return 17.0
    if close_above_ma25_pct <= 16.0:
        return 25.0
    if close_above_ma25_pct <= 20.0:
        return 8.0
    return 0.0


def _score_hcr_trend_support(*, ma25_above_ma60_pct: float) -> float:
    if ma25_above_ma60_pct < 0.0:
        return 0.0
    if ma25_above_ma60_pct < 2.5:
        return 8.0
    if ma25_above_ma60_pct < 4.0:
        return 18.0
    if ma25_above_ma60_pct <= 8.0:
        return 30.0
    if ma25_above_ma60_pct <= 10.0:
        return 12.0
    return 0.0


def _score_hcr_liquidity(*, turnover_n: float) -> float:
    # Liquidity is useful as a capacity guard, but April diagnostics showed that
    # unlimited turnover ranking is not predictive. Keep this capped and low weight.
    if turnover_n >= 500_000_000:
        return 15.0
    if turnover_n >= 100_000_000:
        return 10.0
    if turnover_n >= 30_000_000:
        return 6.0
    return 3.0


def score_hcr_candidate(row: pd.Series, *, previous_close: float | None = None) -> float:
    """Score an already-selected hcr candidate for ranking.

    The screen condition remains strict resonance + breakout. This score is only
    for ranking the selected pool: reward tight resonance and the April-observed
    trend-support sweet spot, cap liquidity, and penalize late-extension heat.
    """
    close = float(row["close"])
    ma25 = float(row["ma25"])
    ma60 = float(row["ma60"])
    resonance_gap_pct = float(row["resonance_gap_pct"])
    turnover_n = float(row["turnover_n"])

    close_above_ma25_pct = (close / ma25 - 1.0) * 100.0 if ma25 else 0.0
    ma25_above_ma60_pct = (ma25 / ma60 - 1.0) * 100.0 if ma60 else 0.0
    day_pct = (close / float(row["open"]) - 1.0) * 100.0 if "open" in row and float(row["open"]) else 0.0
    prev1_ret_pct = (close / previous_close - 1.0) * 100.0 if previous_close else 0.0
    score = (
        _score_hcr_resonance(resonance_gap_pct=resonance_gap_pct)
        + _score_hcr_close_extension(close_above_ma25_pct=close_above_ma25_pct)
        + _score_hcr_trend_support(ma25_above_ma60_pct=ma25_above_ma60_pct)
        + _score_hcr_liquidity(turnover_n=turnover_n)
    )
    if close_above_ma25_pct > 20.0:
        score -= 22.0
    if day_pct > 5.0 and prev1_ret_pct > 4.0:
        score -= 18.0
    return round(max(score, 0.0), 2)


def run_hcr_screen_with_stats(
    prepared_table: pd.DataFrame,
    pick_date: pd.Timestamp,
) -> tuple[list[dict], dict[str, int]]:
    target_date = pd.Timestamp(pick_date)
    candidates: list[dict] = []
    grouped = prepared_table.groupby("ts_code", sort=False) if not prepared_table.empty else []
    stats = {
        "total_symbols": prepared_table["ts_code"].nunique() if not prepared_table.empty and "ts_code" in prepared_table.columns else 0,
        "eligible": 0,
        "fail_insufficient_history": 0,
        "fail_resonance": 0,
        "fail_close_floor": 0,
        "fail_breakout": 0,
        "selected": 0,
    }

    for code, frame in grouped:
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
        previous_daily = frame.loc[trade_dates < target_date].tail(1)
        previous_close = None if previous_daily.empty else float(previous_daily.iloc[-1]["close"])
        hcr_score = score_hcr_candidate(row, previous_close=previous_close)
        close_above_ma25_pct = (float(row["close"]) / float(row["ma25"]) - 1.0) * 100.0
        ma25_above_ma60_pct = (float(row["ma25"]) / float(row["ma60"]) - 1.0) * 100.0
        candidates.append(
            {
                "code": code,
                "pick_date": target_date.strftime("%Y-%m-%d"),
                "close": float(row["close"]),
                "turnover_n": float(row["turnover_n"]),
                "yx": float(row["yx"]),
                "p": float(row["p"]),
                "resonance_gap_pct": float(row["resonance_gap_pct"]),
                "close_above_ma25_pct": round(close_above_ma25_pct, 4),
                "ma25_above_ma60_pct": round(ma25_above_ma60_pct, 4),
                "hcr_score": hcr_score,
            }
        )
        stats["selected"] += 1

    candidates.sort(
        key=lambda item: (
            -float(item["hcr_score"]),
            -float(item["turnover_n"]),
            float(item["resonance_gap_pct"]),
            str(item["code"]),
        )
    )
    return candidates, stats
