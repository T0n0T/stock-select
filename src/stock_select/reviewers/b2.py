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
from stock_select.review_protocol import infer_signal_type
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
        ignore_volume_risk=True,
    )
    verdict = infer_b2_verdict(
        total_score=total_score,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        signal=signal,
        signal_type=signal_type,
        close_above_ma25_pct=(float(close.iloc[-1]) / float(ma25.iloc[-1]) - 1.0) * 100.0
        if pd.notna(ma25.iloc[-1]) and float(ma25.iloc[-1]) != 0.0
        else None,
        ma25_above_zxdkx_pct=(float(ma25.iloc[-1]) / float(zxdkx.iloc[-1]) - 1.0) * 100.0
        if pd.notna(ma25.iloc[-1]) and pd.notna(zxdkx.iloc[-1]) and float(zxdkx.iloc[-1]) != 0.0
        else None,
    )
    elastic_watch, elastic_watch_reason = infer_b2_elastic_watch(
        verdict=verdict,
        total_score=total_score,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
    )
    watch_score = score_b2_watch(
        verdict=verdict,
        total_score=total_score,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        elastic_watch_reason=elastic_watch_reason,
        signal=signal,
        signal_type=signal_type,
    )
    watch_tier = infer_b2_watch_tier(
        verdict=verdict,
        watch_score=watch_score,
        elastic_watch_reason=elastic_watch_reason,
        signal=signal,
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
        "signal": signal,
        "signal_type": signal_type,
        "verdict": verdict,
        "elastic_watch": elastic_watch,
        "elastic_watch_reason": elastic_watch_reason,
        "watch_score": watch_score,
        "watch_tier": watch_tier,
        "comment": comment,
    }


def infer_b2_verdict(
    *,
    total_score: float,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    signal: str | None,
    signal_type: str,
    close_above_ma25_pct: float | None = None,
    ma25_above_zxdkx_pct: float | None = None,
) -> str:
    if signal_type == "distribution_risk":
        if (
            macd_phase >= 4.5
            and previous_abnormal_move >= 5.0
            and trend_structure >= 3.0
            and price_position >= 3.0
            and total_score >= 3.6
        ):
            return "WATCH"
        return "FAIL"

    strong_macd_setup = (
        macd_phase >= 4.5
        and previous_abnormal_move >= 5.0
        and trend_structure >= 3.0
        and price_position >= 2.0
        and volume_behavior >= 2.0
        and total_score >= 3.6
    )
    if strong_macd_setup:
        return "PASS"

    overheat_extension = (
        close_above_ma25_pct is not None
        and close_above_ma25_pct >= 10.0
    ) or (
        ma25_above_zxdkx_pct is not None
        and ma25_above_zxdkx_pct >= 15.0
    )

    strong_trend_start_mid_macd_setup = (
        signal_type == "trend_start"
        and previous_abnormal_move >= 5.0
        and trend_structure >= 4.0
        and price_position >= 3.0
        and volume_behavior >= 3.0
        and total_score >= 4.0
        and not overheat_extension
        and (
            macd_phase >= 4.2
            or (
                macd_phase >= 3.5
                and price_position >= 5.0
                and total_score >= 4.2
            )
        )
    )
    if strong_trend_start_mid_macd_setup:
        return "PASS"

    b3_upgrade_signal = signal in {"B3", "B3+"}
    b3_upgrade_setup = (
        b3_upgrade_signal
        and signal_type in {"rebound", "trend_start"}
        and trend_structure >= 4.0
        and price_position >= 5.0
        and previous_abnormal_move >= 5.0
        and total_score >= 4.15
        and (
            macd_phase >= 4.2
            or (signal_type == "trend_start" and macd_phase >= 3.8)
        )
    )
    if b3_upgrade_setup:
        return "PASS"

    if total_score >= 3.3:
        return "WATCH"
    return "FAIL"


def infer_b2_elastic_watch(
    *,
    verdict: str,
    total_score: float,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
) -> tuple[bool, str | None]:
    if verdict != "WATCH":
        return False, None

    if (
        4.2 <= macd_phase < 4.5
        and price_position >= 4.0
        and previous_abnormal_move >= 5.0
        and total_score >= 4.0
    ):
        return True, "mid_macd_elastic_watch"

    if (
        volume_behavior < 2.0
        and trend_structure >= 4.0
        and price_position >= 4.0
        and previous_abnormal_move >= 5.0
        and total_score >= 4.0
    ):
        return True, "low_volume_elastic_watch"

    return False, None


def score_b2_watch(
    *,
    verdict: str,
    total_score: float,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    elastic_watch_reason: str | None,
    signal: str | None,
    signal_type: str,
) -> float | None:
    if verdict != "WATCH":
        return None

    score = 0.0
    score += max(0.0, total_score - 3.3) * 28.0
    score += max(0.0, trend_structure - 3.0) * 8.0
    score += max(0.0, price_position - 3.0) * 7.0
    score += max(0.0, volume_behavior - 2.0) * 7.0
    score += max(0.0, previous_abnormal_move - 3.0) * 6.0

    if 4.2 <= macd_phase < 4.5:
        score += 16.0
    elif 3.8 <= macd_phase < 4.2:
        score += 9.0
    elif macd_phase >= 4.5:
        score += 6.0

    if elastic_watch_reason == "mid_macd_elastic_watch":
        score += 12.0
    elif elastic_watch_reason == "low_volume_elastic_watch":
        score += 5.0

    if signal in {"B3", "B3+"}:
        score += 8.0
    elif signal == "B5":
        score -= 30.0

    if signal_type == "trend_start":
        score += 8.0
    elif signal_type == "distribution_risk":
        score -= 25.0

    return round(score, 2)


def infer_b2_watch_tier(
    *,
    verdict: str,
    watch_score: float | None,
    elastic_watch_reason: str | None,
    signal: str | None,
) -> str | None:
    if verdict != "WATCH":
        return None
    if signal == "B5":
        return "WATCH-C"

    score = float(watch_score or 0.0)
    if elastic_watch_reason in {"mid_macd_elastic_watch", "low_volume_elastic_watch"} and score >= 65.0:
        return "WATCH-A"
    if score >= 50.0:
        return "WATCH-B"
    return "WATCH-C"


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

    latest_high = float(high.iloc[-1]) if not pd.isna(high.iloc[-1]) else float("nan")
    latest_low = float(low.iloc[-1]) if not pd.isna(low.iloc[-1]) else float("nan")
    if not pd.notna(latest_high) or not pd.notna(latest_low):
        return 3.0

    current_mid_price = (latest_high + latest_low) / 2.0
    box_range = box_high - box_low
    box_position = (current_mid_price - box_low) / box_range

    if 0.70 <= box_position < 0.85:
        return 5.0
    if 0.60 <= box_position < 0.70 or 0.85 <= box_position < 0.92:
        return 4.0
    if 0.50 <= box_position < 0.60 or 0.92 <= box_position < 1.00:
        return 3.0
    if 0.40 <= box_position < 0.50 or 1.00 <= box_position < 1.08:
        return 2.0
    return 1.0


def _tail_slope(series: pd.Series, *, periods: int) -> float:
    values = series.dropna()
    if len(values) <= periods:
        return 0.0
    previous = float(values.iloc[-periods - 1])
    latest = float(values.iloc[-1])
    if previous == 0.0:
        return 0.0
    return latest / previous - 1.0


def _score_b2_volume_behavior(*, close: pd.Series, volume: pd.Series) -> float:
    if len(close) < 20:
        return 3.0

    recent_close = close.tail(20).astype(float)
    recent_volume = volume.tail(20).astype(float)
    latest_close = float(close.iloc[-1])
    previous_close = float(close.iloc[-2])
    latest_volume = float(volume.iloc[-1])
    average_close_5 = float(recent_close.tail(5).mean())
    average_volume_5 = float(recent_volume.tail(5).mean())
    average_volume_20 = float(recent_volume.mean())
    high_close_20 = float(recent_close.max())

    if latest_close < average_close_5 and latest_volume >= average_volume_5:
        return 1.0
    if latest_close < average_close_5:
        return 2.0
    if (
        latest_close >= high_close_20 * 0.98
        and latest_close >= previous_close
        and latest_volume >= average_volume_5 * 0.80
    ):
        return 5.0
    if latest_close >= high_close_20 * 0.95 and latest_volume <= average_volume_20 * 1.80:
        return 4.0
    return 3.0


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
        return 3.0
    if position_pct > -25.0:
        return 5.0
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
