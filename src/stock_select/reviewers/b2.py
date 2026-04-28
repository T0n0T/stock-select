from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_trend, classify_weekly_macd_trend
from stock_select.review_orchestrator import (
    compute_method_total_score,
    describe_macd_trend_state,
    is_constructive_macd_trend_combo,
    map_macd_phase_score,
)
from stock_select.review_protocol import infer_signal_type, infer_verdict
from stock_select.strategies.b1 import compute_zx_lines


def review_b2_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
    signal: str | None = None,
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
    macd_phase = _score_b2_macd_phase(frame, weekly_trend=weekly_trend, daily_trend=daily_trend)

    scores = {
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
    }
    total_score = compute_method_total_score(
        "b2",
        scores,
        signal=signal,
    )
    signal_type = infer_signal_type(
        latest_close=float(close.iloc[-1]),
        latest_open=float(open_.iloc[-1]),
        trend_structure=trend_structure,
        volume_behavior=volume_behavior,
        price_position=price_position,
    )
    verdict = infer_verdict(total_score=total_score, volume_behavior=volume_behavior, signal_type=signal_type)
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
        "signal": signal,
        "signal_type": signal_type,
        "verdict": verdict,
        "comment": comment,
    }


def _resolve_zx_lines(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if {"zxdq", "zxdkx"}.issubset(frame.columns):
        zxdq = pd.to_numeric(frame["zxdq"], errors="coerce")
        zxdkx = pd.to_numeric(frame["zxdkx"], errors="coerce")
        if zxdq.notna().any() and zxdkx.notna().any():
            return zxdq.astype(float), zxdkx.astype(float)
    zxdq, zxdkx = compute_zx_lines(frame)
    return zxdq.astype(float), zxdkx.astype(float)


def _resolve_zxdkx(frame: pd.DataFrame) -> pd.Series:
    return _resolve_zx_lines(frame)[1]


def _score_b2_trend_structure(
    *,
    close: pd.Series,
    low: pd.Series,
    ma25: pd.Series,
    zxdkx: pd.Series,
    weekly_trend: Any | None = None,
    daily_trend: Any | None = None,
) -> float:
    if len(close) < 60 or pd.isna(ma25.iloc[-1]) or pd.isna(zxdkx.iloc[-1]) or pd.isna(zxdkx.iloc[-2]):
        return 3.0

    latest_close = float(close.iloc[-1])
    latest_low = float(low.iloc[-1])
    latest_ma25 = float(ma25.iloc[-1])
    latest_zxdkx = float(zxdkx.iloc[-1])
    previous_zxdkx = float(zxdkx.iloc[-2])
    latest_ma25_prev = float(ma25.iloc[-2]) if not pd.isna(ma25.iloc[-2]) else latest_ma25
    near_ma25_support = latest_low <= latest_ma25 * 1.03
    ma_aligned = latest_close >= latest_ma25 >= latest_zxdkx
    weekly_phase = str(getattr(weekly_trend, "phase", ""))
    daily_phase = str(getattr(daily_trend, "phase", ""))
    daily_initial = bool(getattr(daily_trend, "is_rising_initial", False))
    has_divergence = bool(getattr(weekly_trend, "is_top_divergence", False)) or bool(
        getattr(daily_trend, "is_top_divergence", False)
    )
    trend_window = weekly_phase == "rising" and daily_phase == "rising" and daily_initial and not has_divergence
    constructive_pullback = weekly_phase == "rising" and daily_phase == "falling" and not has_divergence

    if trend_window and ma_aligned and latest_zxdkx >= previous_zxdkx and near_ma25_support:
        return 5.0
    if (trend_window or constructive_pullback or weekly_phase == "rising") and ma_aligned:
        return 4.0
    if ma_aligned and latest_zxdkx >= previous_zxdkx and latest_ma25 >= latest_ma25_prev:
        return 4.0
    if latest_close >= latest_zxdkx:
        return 3.0
    if latest_close >= latest_zxdkx * 0.97:
        return 2.0
    return 1.0


def _score_b2_price_position(
    *,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    ma25: pd.Series,
    zxdq: pd.Series,
) -> float:
    recent_high = high.tail(120).dropna()
    recent_low = low.tail(120).dropna()
    recent_close = close.tail(120).dropna()
    if recent_high.empty or recent_low.empty or recent_close.empty or pd.isna(close.iloc[-1]):
        return 3.0

    box_high = float(recent_high.max())
    box_low = float(recent_low.min())
    if box_high <= box_low:
        return 3.0

    high_idx = recent_high.idxmax()
    high_to_pick_close = close.loc[high_idx : close.index[-1]].dropna()
    if high_to_pick_close.empty:
        position_price = float(close.iloc[-1])
    else:
        position_price = float(high_to_pick_close.min())
    position = (position_price - box_low) / (box_high - box_low)
    latest_ma25 = float(ma25.iloc[-1]) if not pd.isna(ma25.iloc[-1]) else float("nan")
    latest_zxdq = float(zxdq.iloc[-1]) if not pd.isna(zxdq.iloc[-1]) else float("nan")
    ma25_holds_zxdq = bool(
        pd.notna(latest_ma25)
        and pd.notna(latest_zxdq)
        and latest_zxdq > 0.0
        and latest_ma25 >= latest_zxdq * 0.95
    )

    if position <= 0.45:
        return 5.0
    if position <= 0.55:
        return 4.0
    if position <= 0.65 or (position > 0.75 and ma25_holds_zxdq):
        return 3.0
    if position <= 0.75:
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
    retest_floor = float(close.loc[peak_idx : close.index[-1]].min())
    pre_peak_close = float(close.shift(1).loc[peak_idx]) if peak_idx in close.index and peak_idx > close.index.min() else peak_close
    peak_breakout = peak_close >= pre_peak_close * 1.02

    if (
        peak_breakout
        and peak_idx <= recent_volume.index[-6]
        and latest_volume <= peak_volume * 0.60
        and average_last5 <= peak_volume * 0.60
        and retest_floor >= peak_close * 0.96
        and latest_close >= peak_close
    ):
        return 5.0
    if (
        peak_breakout
        and peak_idx <= recent_volume.index[-4]
        and latest_volume <= peak_volume * 0.75
        and average_last5 <= peak_volume * 0.75
        and retest_floor >= peak_close * 0.94
    ):
        return 4.0
    if peak_idx <= recent_volume.index[-4] and average_last5 >= peak_volume * 0.85 and latest_close >= peak_close * 0.96:
        return 2.0
    if latest_volume <= peak_volume * 0.90 and latest_close >= float(recent_close.iloc[-2]):
        return 3.0
    if latest_close >= float(recent_close.tail(5).mean()) and latest_volume <= peak_volume:
        return 2.0
    return 1.0


def _score_b2_previous_abnormal_move(
    *,
    open_: pd.Series,
    close: pd.Series,
    low: pd.Series,
    volume: pd.Series,
) -> float:
    if len(close) < 2:
        return 3.0

    recent_volume = volume.tail(90).dropna()
    if recent_volume.empty:
        return 3.0

    event_idx = int(recent_volume.idxmax())
    event_open = float(open_.loc[event_idx])
    event_close = float(close.loc[event_idx])
    abnormal_price = event_close if event_close >= event_open else event_open
    if abnormal_price <= 0.0:
        return 1.0

    body_low = pd.concat([open_, close], axis=1).min(axis=1)
    post_event_body_low = body_low.loc[event_idx + 1 : close.index[-1]].dropna()
    if post_event_body_low.empty:
        min_low_after_event = float(body_low.loc[event_idx])
    else:
        min_low_after_event = float(post_event_body_low.min())
    redundant_price = abnormal_price * 0.90
    if redundant_price <= 0.0:
        return 1.0
    position_pct = (min_low_after_event / redundant_price - 1.0) * 100.0

    if position_pct > 10.0:
        return 5.0
    if position_pct > -25.0:
        return 4.0
    if position_pct > -40.0:
        return 3.0
    if position_pct > -55.0:
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
