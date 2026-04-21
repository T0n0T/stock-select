from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_state, classify_daily_macd_wave, classify_weekly_macd_wave
from stock_select.review_orchestrator import apply_macd_verdict_gate, compute_method_total_score, map_macd_phase_score
from stock_select.review_protocol import infer_signal_type, infer_verdict
from stock_select.reviewers.b2 import (
    _score_b2_previous_abnormal_move,
    _score_b2_price_position,
    _score_b2_trend_structure,
    _score_b2_volume_behavior,
)


def review_dribull_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
) -> dict[str, Any]:
    frame = history.copy()
    if frame.empty:
        raise ValueError("No daily history available for review.")

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    cutoff = pd.Timestamp(pick_date)
    frame = frame.loc[frame["trade_date"] <= cutoff].sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"No daily history available on or before pick_date: {pick_date}")

    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)
    ma25 = close.rolling(window=25, min_periods=25).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()

    trend_structure = _score_b2_trend_structure(close=close, low=low, ma25=ma25, ma60=ma60)
    price_position = _score_b2_price_position(close=close, high=high, ma25=ma25)
    volume_behavior = _score_b2_volume_behavior(close=close, volume=volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(close=close, volume=volume, ma25=ma25, ma60=ma60)
    weekly_wave = classify_weekly_macd_wave(frame[["trade_date", "close"]], pick_date)
    daily_wave = classify_daily_macd_wave(frame[["trade_date", "close"]], pick_date)
    daily_state = classify_daily_macd_state(frame[["trade_date", "close"]], pick_date)
    macd_phase = map_macd_phase_score(method="dribull", history_len=len(frame), weekly_wave=weekly_wave, daily_state=daily_state)

    total_score = compute_method_total_score(
        "dribull",
        {
            "trend_structure": trend_structure,
            "price_position": price_position,
            "volume_behavior": volume_behavior,
            "previous_abnormal_move": previous_abnormal_move,
            "macd_phase": macd_phase,
        },
    )
    signal_type = infer_signal_type(
        latest_close=float(close.iloc[-1]),
        latest_open=float(open_.iloc[-1]),
        trend_structure=trend_structure,
        volume_behavior=volume_behavior,
        price_position=price_position,
    )
    verdict = infer_verdict(total_score=total_score, volume_behavior=volume_behavior, signal_type=signal_type)
    verdict = apply_macd_verdict_gate(method="dribull", current_verdict=verdict, daily_state=daily_state, weekly_wave=weekly_wave)

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
        "comment": _build_dribull_comment(weekly_wave=weekly_wave, daily_wave=daily_wave, verdict=verdict),
    }


def _is_dribull_wave_combo_ok(*, weekly_wave: Any, daily_wave: Any) -> bool:
    combo_ok = weekly_wave.label in {"wave1", "wave3"} and daily_wave.label in {"wave2_end", "wave4_end"}
    if not combo_ok:
        return False
    if daily_wave.label != "wave4_end":
        return True
    return float(daily_wave.details.get("third_wave_gain", 0.0)) <= 0.30


def _build_dribull_comment(*, weekly_wave: Any, daily_wave: Any, verdict: str) -> str:
    combo_ok = _is_dribull_wave_combo_ok(weekly_wave=weekly_wave, daily_wave=daily_wave)
    combo_text = "符合" if combo_ok else "不符合"
    if daily_wave.label == "wave4_end":
        gain = float(daily_wave.details.get("third_wave_gain", 0.0)) * 100.0
        return f"周线{weekly_wave.label}、日线{daily_wave.label}，三浪涨幅约{gain:.1f}%且该组合{combo_text}dribull，当前结论为{verdict}。"
    return f"周线{weekly_wave.label}、日线{daily_wave.label}，该组合{combo_text}dribull，当前结论为{verdict}。"
