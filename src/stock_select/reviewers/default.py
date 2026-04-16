from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.review_protocol import (
    build_baseline_comment,
    infer_signal_type,
    infer_verdict,
)
from stock_select.review_orchestrator import compute_method_total_score
from stock_select.strategies import compute_macd


def review_symbol_history(
    *,
    method: str = "default",
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
) -> dict[str, Any]:
    frame = history.copy()
    if frame.empty:
        msg = "No daily history available for review."
        raise ValueError(msg)

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    cutoff = pd.Timestamp(pick_date)
    frame = frame.loc[frame["trade_date"] <= cutoff].sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        msg = f"No daily history available on or before pick_date: {pick_date}"
        raise ValueError(msg)

    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)

    ma20 = close.rolling(window=20, min_periods=20).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()
    latest_close = float(close.iloc[-1])
    latest_open = float(open_.iloc[-1])
    recent_window = frame.tail(20)
    recent_close = recent_window["close"].astype(float)
    recent_open = recent_window["open"].astype(float)
    recent_volume = (
        recent_window["vol"].astype(float)
        if "vol" in recent_window.columns
        else recent_window["volume"].astype(float)
    )

    trend_structure = _score_trend_structure(close, ma20, ma60)
    price_position = _score_price_position(close)
    volume_behavior = _score_volume_behavior(recent_open, recent_close, recent_volume)
    previous_abnormal_move = _score_previous_abnormal_move(close, volume)
    macd_phase = _score_macd_phase(close)

    score_fields = {
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
    }
    total_score = compute_method_total_score(method, score_fields)
    signal_type = infer_signal_type(
        latest_close=latest_close,
        latest_open=latest_open,
        trend_structure=trend_structure,
        volume_behavior=volume_behavior,
        price_position=price_position,
    )
    verdict = infer_verdict(total_score=total_score, volume_behavior=volume_behavior, signal_type=signal_type)

    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "review_type": "baseline",
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
        "total_score": total_score,
        "signal_type": signal_type,
        "verdict": verdict,
        "comment": build_baseline_comment(signal_type=signal_type, verdict=verdict),
    }


def _score_trend_structure(close: pd.Series, ma20: pd.Series, ma60: pd.Series) -> float:
    if len(close) < 60 or pd.isna(ma20.iloc[-1]) or pd.isna(ma60.iloc[-1]):
        return 3.0
    recent_gain = float(close.iloc[-1] / close.iloc[-20] - 1.0) if close.iloc[-20] else 0.0
    ma20_slope = float(ma20.iloc[-1] - ma20.iloc[-5])
    ma60_slope = float(ma60.iloc[-1] - ma60.iloc[-5])
    if close.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1] and ma20_slope > 0 and ma60_slope >= 0 and recent_gain > 0.05:
        return 5.0
    if close.iloc[-1] >= ma20.iloc[-1] and ma20.iloc[-1] >= ma60.iloc[-1] and ma20_slope >= 0:
        return 4.0
    if close.iloc[-1] >= ma20.iloc[-1]:
        return 3.0
    if close.iloc[-1] >= ma60.iloc[-1]:
        return 2.0
    return 1.0


def _score_price_position(close: pd.Series) -> float:
    if len(close) < 60:
        return 3.0
    recent = close.tail(120)
    low = float(recent.min())
    high = float(recent.max())
    if high <= low:
        return 3.0
    position = (float(close.iloc[-1]) - low) / (high - low)
    near_term_mean = float(close.tail(20).mean())
    mid_term_mean = float(close.tail(60).mean())
    if position <= 0.35:
        return 5.0
    if position <= 0.55:
        return 4.0
    if position <= 0.75:
        return 3.0
    if position <= 0.90:
        return 2.0
    if near_term_mean > mid_term_mean:
        return 3.0
    return 1.0


def _score_volume_behavior(open_: pd.Series, close: pd.Series, volume: pd.Series) -> float:
    bullish = volume[close >= open_]
    bearish = volume[close < open_]
    avg_bullish = float(bullish.mean()) if not bullish.empty else 0.0
    avg_bearish = float(bearish.mean()) if not bearish.empty else 0.0
    max_volume_index = int(volume.idxmax())
    max_volume_bullish = bool(close.loc[max_volume_index] >= open_.loc[max_volume_index])
    latest_green = bool(close.iloc[-1] >= open_.iloc[-1])

    if max_volume_bullish and avg_bullish > avg_bearish * 1.2 and latest_green:
        return 5.0
    if max_volume_bullish and avg_bullish >= avg_bearish:
        return 4.0
    if max_volume_bullish:
        return 3.0
    if latest_green and avg_bullish * 0.9 >= avg_bearish:
        return 2.0
    return 1.0


def _score_previous_abnormal_move(close: pd.Series, volume: pd.Series) -> float:
    if len(close) < 40:
        return 3.0
    latest_close = float(close.iloc[-1])
    early_close = float(close.iloc[-40])
    gain = latest_close / early_close - 1.0 if early_close else 0.0
    avg_volume = float(volume.tail(60).mean())
    peak_volume = float(volume.tail(60).max())

    if gain < 0.5 and peak_volume > avg_volume * 1.8:
        return 5.0
    if gain < 0.5 and peak_volume > avg_volume * 1.4:
        return 4.0
    if gain < 0.5:
        return 3.0
    if gain < 1.0:
        return 2.0
    return 1.0


def _score_macd_phase(close: pd.Series) -> float:
    if len(close) < 35:
        return 3.0

    macd = compute_macd(pd.DataFrame({"close": close}))
    dif = macd["dif"].astype(float)
    dea = macd["dea"].astype(float)
    hist = macd["macd_hist"].astype(float)
    recent_hist = hist.tail(5)

    if len(recent_hist) < 5:
        return 3.0

    if hist.iloc[-1] < 0.0 and hist.iloc[-2] >= 0.0:
        return 1.0
    if dif.iloc[-1] < dea.iloc[-1]:
        return 2.0

    recent_cross = ((dif.shift(1) <= dea.shift(1)) & (dif > dea)).tail(5).any()
    hist_increasing = bool((recent_hist.diff().iloc[1:] > 0.0).all())
    hist_decreasing = bool((recent_hist.diff().iloc[1:] < 0.0).all())
    lines_stretched = abs(float(dif.iloc[-1] - dea.iloc[-1])) > abs(float(hist.iloc[-1])) * 1.5

    if recent_cross and hist_increasing and hist.iloc[-1] > 0.0:
        return 5.0
    if hist_increasing and lines_stretched and hist.iloc[-1] > 0.0:
        return 4.0
    if hist_decreasing and close.iloc[-1] >= close.tail(5).max():
        return 3.0
    return 3.0
