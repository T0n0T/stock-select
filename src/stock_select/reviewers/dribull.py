from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_trend, classify_weekly_macd_trend
from stock_select.review_orchestrator import (
    apply_macd_verdict_gate,
    compute_method_total_score,
    describe_macd_trend_state,
    is_constructive_macd_trend_combo,
    map_macd_phase_score,
)
from stock_select.review_protocol import infer_signal_type, infer_verdict
from stock_select.reviewers.b2 import (
    _resolve_zx_lines,
    _resolve_zxdkx,
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
    zxdq, zxdkx = _resolve_zx_lines(frame)

    weekly_trend = classify_weekly_macd_trend(frame[["trade_date", "close"]], pick_date)
    daily_trend = classify_daily_macd_trend(frame[["trade_date", "close"]], pick_date)

    trend_structure = _score_b2_trend_structure(
        close=close,
        low=low,
        ma25=ma25,
        zxdkx=zxdkx,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
    )
    price_position = _score_b2_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq)
    volume_behavior = _score_b2_volume_behavior(close=close, volume=volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume)
    macd_phase = map_macd_phase_score(
        method="dribull",
        history_len=len(frame),
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
    )

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
    verdict = _refine_dribull_verdict(
        verdict=verdict,
        total_score=total_score,
        price_position=price_position,
        volume_behavior=volume_behavior,
    )
    verdict = apply_macd_verdict_gate(
        method="dribull",
        current_verdict=verdict,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
    )

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
        "comment": _build_dribull_comment(weekly_trend=weekly_trend, daily_trend=daily_trend, verdict=verdict),
    }


def _build_dribull_comment(*, weekly_trend: Any, daily_trend: Any, verdict: str) -> str:
    combo_ok = is_constructive_macd_trend_combo(weekly_trend=weekly_trend, daily_trend=daily_trend)
    combo_text = "符合" if combo_ok else "不符合"
    weekly_text = describe_macd_trend_state("周线", weekly_trend)
    daily_text = describe_macd_trend_state("日线", daily_trend)
    return f"{weekly_text}、{daily_text}，该MACD组合{combo_text}dribull，当前结论为{verdict}。"


def _refine_dribull_verdict(
    *,
    verdict: str,
    total_score: float,
    price_position: float,
    volume_behavior: float,
) -> str:
    if verdict != "PASS":
        return verdict
    if total_score < 4.2:
        return "WATCH"
    if price_position < 4.0 or volume_behavior < 4.0:
        return "WATCH"
    return verdict
