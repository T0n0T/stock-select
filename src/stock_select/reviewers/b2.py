from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_trend, classify_weekly_macd_trend
from stock_select.review_protocol import infer_signal_type, infer_verdict
from stock_select.review_orchestrator import (
    apply_macd_verdict_gate,
    compute_method_total_score,
    describe_macd_trend_state,
    is_constructive_macd_trend_combo,
    map_macd_phase_score,
)


def review_b2_symbol_history(
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
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)
    ma25 = close.rolling(window=25, min_periods=25).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()

    weekly_trend = classify_weekly_macd_trend(frame[["trade_date", "close"]], pick_date)
    daily_trend = classify_daily_macd_trend(frame[["trade_date", "close"]], pick_date)

    trend_structure = _score_b2_trend_structure(
        close=close,
        low=low,
        ma25=ma25,
        ma60=ma60,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
    )
    price_position = _score_b2_price_position(close=close, high=high, ma25=ma25)
    volume_behavior = _score_b2_volume_behavior(close=close, volume=volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(close=close, volume=volume, ma25=ma25, ma60=ma60)
    macd_phase = _score_b2_macd_phase(frame, weekly_trend=weekly_trend, daily_trend=daily_trend)

    total_score = compute_method_total_score(
        "b2",
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
    verdict = apply_macd_verdict_gate(
        method="b2",
        current_verdict=verdict,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
    )
    comment = _build_b2_comment(weekly_trend=weekly_trend, daily_trend=daily_trend, verdict=verdict)

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
        "comment": comment,
    }


def _score_b2_trend_structure(
    *,
    close: pd.Series,
    low: pd.Series,
    ma25: pd.Series,
    ma60: pd.Series,
    weekly_trend: Any | None = None,
    daily_trend: Any | None = None,
) -> float:
    if len(close) < 60 or pd.isna(ma25.iloc[-1]) or pd.isna(ma60.iloc[-1]) or pd.isna(ma60.iloc[-2]):
        return 3.0

    latest_close = float(close.iloc[-1])
    latest_low = float(low.iloc[-1])
    latest_ma25 = float(ma25.iloc[-1])
    latest_ma60 = float(ma60.iloc[-1])
    previous_ma60 = float(ma60.iloc[-2])
    near_ma25_support = latest_low <= latest_ma25 * 1.03
    trend_window = (
        str(getattr(weekly_trend, "phase", "")) == "rising"
        and str(getattr(daily_trend, "phase", "")) == "rising"
        and bool(getattr(daily_trend, "is_rising_initial", False))
    )

    if trend_window and latest_close >= latest_ma25 and latest_ma25 >= latest_ma60 and latest_ma60 >= previous_ma60 and near_ma25_support:
        return 5.0
    if str(getattr(weekly_trend, "phase", "")) == "rising" and latest_close >= latest_ma25 and latest_ma25 >= latest_ma60:
        return 4.0
    if latest_close >= latest_ma25 and latest_ma25 >= latest_ma60:
        return 4.0
    if latest_close >= latest_ma60:
        return 3.0
    if latest_close >= latest_ma60 * 0.97:
        return 2.0
    return 1.0


def _score_b2_price_position(*, close: pd.Series, high: pd.Series, ma25: pd.Series) -> float:
    if len(close) < 25 or pd.isna(ma25.iloc[-1]):
        return 3.0

    recent_high = float(high.tail(20).max())
    latest_close = float(close.iloc[-1])
    latest_ma25 = float(ma25.iloc[-1])
    retrace_from_high = 0.0 if recent_high <= 0.0 else (recent_high - latest_close) / recent_high
    support_gap = latest_close / latest_ma25 - 1.0 if latest_ma25 else 0.0

    if support_gap >= 0.0 and retrace_from_high <= 0.03:
        return 5.0
    if support_gap >= -0.01 and retrace_from_high <= 0.06:
        return 4.0
    if latest_close >= latest_ma25:
        return 3.0
    if retrace_from_high <= 0.10:
        return 2.0
    return 1.0


def _score_b2_volume_behavior(*, close: pd.Series, volume: pd.Series) -> float:
    if len(close) < 20:
        return 3.0

    recent_close = close.tail(20)
    recent_volume = volume.tail(20)
    peak_volume = float(recent_volume.max())
    peak_idx = int(recent_volume.idxmax())
    peak_close = float(close.loc[peak_idx])
    latest_close = float(close.iloc[-1])
    latest_volume = float(volume.iloc[-1])
    average_last5 = float(recent_volume.tail(5).mean())
    retest_floor = float(recent_close.tail(10).min())

    if (
        peak_idx <= recent_volume.index[-6]
        and latest_volume <= peak_volume * 0.60
        and average_last5 <= peak_volume * 0.60
        and retest_floor >= peak_close * 0.96
        and latest_close >= peak_close
    ):
        return 5.0
    if (
        peak_idx <= recent_volume.index[-4]
        and latest_volume <= peak_volume * 0.75
        and average_last5 <= peak_volume * 0.75
        and retest_floor >= peak_close * 0.94
    ):
        return 4.0
    if latest_volume <= peak_volume * 0.90 and latest_close >= float(recent_close.iloc[-2]):
        return 3.0
    if latest_close >= float(recent_close.tail(5).mean()) and latest_volume <= peak_volume:
        return 2.0
    return 1.0


def _score_b2_previous_abnormal_move(
    *,
    close: pd.Series,
    volume: pd.Series,
    ma25: pd.Series,
    ma60: pd.Series,
) -> float:
    if len(close) < 60 or pd.isna(ma25.iloc[-1]) or pd.isna(ma60.iloc[-1]):
        return 3.0

    recent_close = close.tail(60)
    recent_volume = volume.tail(60)
    move_ratio = float(recent_close.max() / recent_close.min() - 1.0) if float(recent_close.min()) else 0.0
    volume_ratio = float(recent_volume.max() / recent_volume.mean()) if float(recent_volume.mean()) else 0.0
    above_support = float(close.iloc[-1]) >= float(ma25.iloc[-1]) >= float(ma60.iloc[-1])

    if above_support and move_ratio >= 0.20 and volume_ratio >= 1.60:
        return 5.0
    if above_support and move_ratio >= 0.12 and volume_ratio >= 1.40:
        return 4.0
    if above_support and move_ratio >= 0.08:
        return 3.0
    if move_ratio >= 0.05:
        return 2.0
    return 1.0


def _score_b2_macd_phase(
    frame: pd.DataFrame,
    *,
    weekly_trend: Any,
    daily_trend: Any,
) -> float:
    return map_macd_phase_score(method="b2", history_len=len(frame), weekly_trend=weekly_trend, daily_trend=daily_trend)


def _build_b2_comment(*, weekly_trend: Any, daily_trend: Any, verdict: str) -> str:
    combo_ok = is_constructive_macd_trend_combo(weekly_trend=weekly_trend, daily_trend=daily_trend)
    combo_text = "符合" if combo_ok else "不符合"
    weekly_text = describe_macd_trend_state("周线", weekly_trend)
    daily_text = describe_macd_trend_state("日线", daily_trend)
    return f"{weekly_text}、{daily_text}，该MACD组合{combo_text}b2，当前结论为{verdict}。"
