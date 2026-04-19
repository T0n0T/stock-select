from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_wave, classify_weekly_macd_wave
from stock_select.review_orchestrator import compute_method_total_score
from stock_select.review_protocol import infer_signal_type, infer_verdict
from stock_select.reviewers.default import (
    _score_macd_phase as _legacy_score_macd_phase,
    _score_previous_abnormal_move,
    _score_price_position,
    _score_trend_structure,
    _score_volume_behavior,
)


def review_b1_symbol_history(
    *,
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
    recent_window = frame.tail(20)
    recent_open = recent_window["open"].astype(float)
    recent_close = recent_window["close"].astype(float)
    recent_volume = (
        recent_window["vol"].astype(float)
        if "vol" in recent_window.columns
        else recent_window["volume"].astype(float)
    )

    trend_structure = _score_trend_structure(close, ma20, ma60)
    price_position = _score_price_position(close)
    volume_behavior = _score_volume_behavior(recent_open, recent_close, recent_volume)
    previous_abnormal_move = _score_previous_abnormal_move(close, volume)
    weekly_wave = classify_weekly_macd_wave(frame[["trade_date", "close"]], pick_date)
    daily_wave = classify_daily_macd_wave(frame[["trade_date", "close"]], pick_date)
    macd_phase = _score_b1_macd_phase(close=close, weekly_wave=weekly_wave, daily_wave=daily_wave)
    total_score = compute_method_total_score(
        "b1",
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
        "comment": _build_b1_comment(weekly_wave=weekly_wave, daily_wave=daily_wave, verdict=verdict),
    }


def _score_b1_macd_phase(*, close: pd.Series, weekly_wave: Any, daily_wave: Any) -> float:
    if len(close) < 60:
        return 3.0

    if _is_b1_wave_combo_ok(weekly_wave=weekly_wave, daily_wave=daily_wave):
        return 5.0
    if weekly_wave.label in {"wave1", "wave3"}:
        return 4.0
    if daily_wave.label in {"wave2_end", "wave4_end"}:
        return 2.0
    return max(1.0, min(3.0, float(_legacy_score_macd_phase(close))))


def _is_b1_wave_combo_ok(*, weekly_wave: Any, daily_wave: Any) -> bool:
    combo_ok = weekly_wave.label in {"wave1", "wave3"} and daily_wave.label in {"wave2_end", "wave4_end"}
    if not combo_ok:
        return False
    if daily_wave.label != "wave4_end":
        return True
    return float(daily_wave.details.get("third_wave_gain", 0.0)) <= 0.30


def _build_b1_comment(*, weekly_wave: Any, daily_wave: Any, verdict: str) -> str:
    combo_ok = _is_b1_wave_combo_ok(weekly_wave=weekly_wave, daily_wave=daily_wave)
    combo_text = "符合" if combo_ok else "不符合"
    if daily_wave.label == "wave4_end":
        gain = float(daily_wave.details.get("third_wave_gain", 0.0)) * 100.0
        return f"周线{weekly_wave.label}、日线{daily_wave.label}，三浪涨幅约{gain:.1f}%且该组合{combo_text}b1，当前结论为{verdict}。"
    return f"周线{weekly_wave.label}、日线{daily_wave.label}，该组合{combo_text}b1，当前结论为{verdict}。"
