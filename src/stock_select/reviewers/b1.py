from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_trend, classify_weekly_macd_trend
from stock_select.indicators import compute_macd
from stock_select.review_orchestrator import (
    apply_macd_verdict_gate,
    compute_method_total_score,
    describe_macd_trend_state,
    is_constructive_macd_trend_combo,
    map_macd_phase_score,
)
from stock_select.review_protocol import infer_signal_type
from stock_select.reviewers.b2 import _score_b2_previous_abnormal_move
from stock_select.strategies.b1 import compute_zx_lines

_APPROX_TOLERANCE = 0.05


@dataclass(frozen=True)
class B1WeeklyMacdContext:
    red_histogram: bool
    above_water: bool
    diverging: bool
    improving: bool


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
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)

    ma25 = _resolve_series(frame, "ma25", close.rolling(window=25, min_periods=25).mean())
    zxdq, zxdkx = _resolve_zx_lines(frame)
    bbi = _resolve_series(frame, "bbi", _compute_bbi(close))
    recent_window = frame.tail(20)
    recent_open = recent_window["open"].astype(float)
    recent_close = recent_window["close"].astype(float)
    recent_volume = (
        recent_window["vol"].astype(float)
        if "vol" in recent_window.columns
        else recent_window["volume"].astype(float)
    )

    trend_structure = _score_b1_trend_structure(open_=open_, close=close, ma25=ma25, zxdkx=zxdkx, bbi=bbi)
    price_position = _score_b1_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq)
    volume_behavior = _score_b1_volume_behavior(recent_open, recent_close, recent_volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume)
    weekly_trend = classify_weekly_macd_trend(frame[["trade_date", "close"]], pick_date)
    daily_trend = classify_daily_macd_trend(frame[["trade_date", "close"]], pick_date)
    weekly_macd = _classify_b1_weekly_macd_context(frame)
    daily_recent_death_cross = _has_recent_daily_macd_death_cross(frame)
    macd_phase = map_macd_phase_score(
        method="b1",
        history_len=len(close),
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
    )
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
    verdict = infer_b1_verdict(
        total_score=total_score,
        volume_behavior=volume_behavior,
        signal_type=signal_type,
        trend_structure=trend_structure,
        price_position=price_position,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        close_above_ma25_pct=(float(close.iloc[-1]) / float(ma25.iloc[-1]) - 1.0) * 100.0
        if pd.notna(ma25.iloc[-1]) and float(ma25.iloc[-1]) != 0.0
        else None,
        ma25_above_zxdkx_pct=(float(ma25.iloc[-1]) / float(zxdkx.iloc[-1]) - 1.0) * 100.0
        if pd.notna(ma25.iloc[-1]) and pd.notna(zxdkx.iloc[-1]) and float(zxdkx.iloc[-1]) != 0.0
        else None,
        close_above_zxdq_pct=(float(close.iloc[-1]) / float(zxdq.iloc[-1]) - 1.0) * 100.0
        if pd.notna(zxdq.iloc[-1]) and float(zxdq.iloc[-1]) != 0.0
        else None,
        day_pct=(float(close.iloc[-1]) / float(open_.iloc[-1]) - 1.0) * 100.0
        if float(open_.iloc[-1]) != 0.0
        else None,
    )
    allow_divergence_pass = verdict == "PASS" and signal_type in {"trend_start", "rebound"}
    verdict = apply_macd_verdict_gate(
        method="b1",
        current_verdict=verdict,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
        allow_divergence_pass=allow_divergence_pass,
    )
    watch_reason = infer_b1_watch_reason(
        verdict=verdict,
        signal_type=signal_type,
        total_score=total_score,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        close_above_ma25_pct=(float(close.iloc[-1]) / float(ma25.iloc[-1]) - 1.0) * 100.0
        if pd.notna(ma25.iloc[-1]) and float(ma25.iloc[-1]) != 0.0
        else None,
        ma25_above_zxdkx_pct=(float(ma25.iloc[-1]) / float(zxdkx.iloc[-1]) - 1.0) * 100.0
        if pd.notna(ma25.iloc[-1]) and pd.notna(zxdkx.iloc[-1]) and float(zxdkx.iloc[-1]) != 0.0
        else None,
        close_above_zxdq_pct=(float(close.iloc[-1]) / float(zxdq.iloc[-1]) - 1.0) * 100.0
        if pd.notna(zxdq.iloc[-1]) and float(zxdq.iloc[-1]) != 0.0
        else None,
        day_pct=(float(close.iloc[-1]) / float(open_.iloc[-1]) - 1.0) * 100.0
        if float(open_.iloc[-1]) != 0.0
        else None,
    )
    watch_score = score_b1_watch(
        verdict=verdict,
        signal_type=signal_type,
        watch_reason=watch_reason,
        trend_structure=trend_structure,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        close_above_ma25_pct=(float(close.iloc[-1]) / float(ma25.iloc[-1]) - 1.0) * 100.0
        if pd.notna(ma25.iloc[-1]) and float(ma25.iloc[-1]) != 0.0
        else None,
        close_above_zxdq_pct=(float(close.iloc[-1]) / float(zxdq.iloc[-1]) - 1.0) * 100.0
        if pd.notna(zxdq.iloc[-1]) and float(zxdq.iloc[-1]) != 0.0
        else None,
        day_pct=(float(close.iloc[-1]) / float(open_.iloc[-1]) - 1.0) * 100.0
        if float(open_.iloc[-1]) != 0.0
        else None,
    )
    watch_tier = infer_b1_watch_tier(verdict=verdict, watch_reason=watch_reason, watch_score=watch_score)

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
        "watch_reason": watch_reason,
        "watch_score": watch_score,
        "watch_tier": watch_tier,
        "comment": _build_b1_comment(
            weekly_trend=weekly_trend,
            daily_trend=daily_trend,
            weekly_macd=weekly_macd,
            verdict=verdict,
            daily_recent_death_cross=daily_recent_death_cross,
        ),
    }


def infer_b1_verdict(
    *,
    total_score: float,
    volume_behavior: float,
    signal_type: str,
    trend_structure: float,
    price_position: float,
    previous_abnormal_move: float = 3.0,
    macd_phase: float,
    close_above_ma25_pct: float | None = None,
    ma25_above_zxdkx_pct: float | None = None,
    close_above_zxdq_pct: float | None = None,
    day_pct: float | None = None,
) -> str:
    if volume_behavior <= 1.0:
        return "FAIL"

    if signal_type == "distribution_risk":
        elastic_distribution_watch = (
            total_score >= 3.0
            and volume_behavior >= 3.0
            and previous_abnormal_move >= 3.0
            and 2.0 <= macd_phase <= 4.2
            and 3.0 <= price_position <= 4.0
            and (close_above_ma25_pct is None or close_above_ma25_pct <= -3.0)
            and (day_pct is None or day_pct <= -2.0)
        )
        return "WATCH" if elastic_distribution_watch else "FAIL"

    if signal_type == "trend_start":
        repair_start_setup = (
            total_score >= 3.8
            and trend_structure >= 4.0
            and 3.0 <= price_position <= 4.0
            and volume_behavior >= 4.0
            and 3.2 <= macd_phase <= 4.05
            and (close_above_ma25_pct is None or close_above_ma25_pct <= -1.0)
            and (ma25_above_zxdkx_pct is None or ma25_above_zxdkx_pct >= 3.0)
            and (close_above_zxdq_pct is None or close_above_zxdq_pct <= -6.0)
            and (day_pct is None or day_pct <= 1.0)
        )
        if repair_start_setup:
            return "PASS"
        if total_score >= 3.2:
            return "WATCH"
        return "FAIL"

    if total_score >= 4.0:
        rebound_repair_setup = (
            signal_type == "rebound"
            and trend_structure >= 4.0
            and 3.0 <= price_position <= 4.0
            and volume_behavior >= 4.0
            and 3.5 <= macd_phase <= 4.1
            and (close_above_ma25_pct is None or close_above_ma25_pct <= -3.0)
            and (ma25_above_zxdkx_pct is None or ma25_above_zxdkx_pct >= 6.0)
            and (close_above_zxdq_pct is None or close_above_zxdq_pct <= -5.0)
            and (day_pct is None or day_pct <= 0.5)
        )
        return "PASS" if rebound_repair_setup else "WATCH"
    elastic_rebound_watch = (
        signal_type == "rebound"
        and total_score >= 3.0
        and trend_structure >= 3.0
        and 2.0 <= price_position <= 5.0
        and volume_behavior >= 3.0
        and previous_abnormal_move >= 3.0
        and 2.8 <= macd_phase <= 4.2
    )
    if total_score >= 3.2 or elastic_rebound_watch:
        return "WATCH"
    return "FAIL"


def infer_b1_watch_reason(
    *,
    verdict: str,
    signal_type: str,
    total_score: float,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    close_above_ma25_pct: float | None = None,
    ma25_above_zxdkx_pct: float | None = None,
    close_above_zxdq_pct: float | None = None,
    day_pct: float | None = None,
) -> str | None:
    if verdict != "WATCH":
        return None
    if signal_type == "distribution_risk":
        return "distribution_elastic"
    if signal_type == "trend_start":
        trend_repair_like = (
            total_score >= 3.8
            and trend_structure >= 4.0
            and 3.0 <= price_position <= 4.0
            and volume_behavior >= 3.0
            and previous_abnormal_move >= 3.0
            and 3.2 <= macd_phase <= 4.2
            and (close_above_zxdq_pct is None or close_above_zxdq_pct <= -5.0)
            and (day_pct is None or day_pct <= 1.5)
        )
        return "trend_start_repair" if trend_repair_like else "trend_start_weak"
    if signal_type == "rebound":
        if total_score >= 4.0:
            return "rebound_near_pass_flawed"
        elastic_rebound = (
            total_score >= 3.0
            and trend_structure >= 3.0
            and volume_behavior >= 3.0
            and previous_abnormal_move >= 3.0
            and 2.8 <= macd_phase <= 4.2
        )
        return "rebound_elastic" if elastic_rebound else "rebound_ordinary"
    return "watch_ordinary"


def score_b1_watch(
    *,
    verdict: str,
    signal_type: str,
    watch_reason: str | None,
    trend_structure: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    close_above_ma25_pct: float | None = None,
    close_above_zxdq_pct: float | None = None,
    day_pct: float | None = None,
) -> float | None:
    if verdict != "WATCH":
        return None
    score = 0.0
    if close_above_ma25_pct is not None:
        if close_above_ma25_pct <= -5.0:
            score += 25.0
        elif close_above_ma25_pct <= -3.0:
            score += 20.0
        elif close_above_ma25_pct <= 0.0:
            score += 10.0
        else:
            score -= 10.0
    if close_above_zxdq_pct is not None:
        if close_above_zxdq_pct <= -6.0:
            score += 20.0
        elif close_above_zxdq_pct <= -4.0:
            score += 12.0
        elif close_above_zxdq_pct <= 0.0:
            score += 5.0
        else:
            score -= 10.0
    if 3.2 <= macd_phase <= 4.05:
        score += 20.0
    elif 2.8 <= macd_phase < 3.2:
        score += 12.0
    elif 4.05 < macd_phase <= 4.2:
        score += 5.0
    else:
        score -= 8.0
    score += max(0.0, trend_structure - 3.0) * 6.0
    score += max(0.0, volume_behavior - 3.0) * 5.0
    score += max(0.0, previous_abnormal_move - 3.0) * 4.0
    if day_pct is not None:
        if day_pct <= 0.0:
            score += 10.0
        elif day_pct <= 1.0:
            score += 5.0
        elif day_pct > 3.0:
            score -= 10.0
    reason_adjustment = {
        "distribution_elastic": 5.0,
        "rebound_elastic": 6.0,
        "trend_start_repair": 4.0,
        "rebound_near_pass_flawed": -2.0,
        "trend_start_weak": -12.0,
    }
    score += reason_adjustment.get(str(watch_reason or ""), 0.0)
    return round(score, 2)


def infer_b1_watch_tier(*, verdict: str, watch_reason: str | None, watch_score: float | None) -> str | None:
    if verdict != "WATCH":
        return None
    reason = str(watch_reason or "")
    score = float(watch_score or 0.0)
    if reason == "distribution_elastic":
        return "WATCH-A"
    if reason == "rebound_elastic" and score >= 55.0:
        return "WATCH-A"
    if reason == "trend_start_repair" or score >= 40.0:
        return "WATCH-B"
    return "WATCH-C"


def _resolve_series(frame: pd.DataFrame, column: str, fallback: pd.Series) -> pd.Series:
    if column in frame.columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.notna().any():
            return series.astype(float)
    return fallback.astype(float)


def _resolve_zx_lines(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if {"zxdq", "zxdkx"}.issubset(frame.columns):
        zxdq = pd.to_numeric(frame["zxdq"], errors="coerce")
        zxdkx = pd.to_numeric(frame["zxdkx"], errors="coerce")
        if zxdq.notna().any() and zxdkx.notna().any():
            return zxdq.astype(float), zxdkx.astype(float)
    return compute_zx_lines(frame)


def _compute_bbi(close: pd.Series) -> pd.Series:
    return (
        close.rolling(window=3, min_periods=3).mean()
        + close.rolling(window=6, min_periods=6).mean()
        + close.rolling(window=12, min_periods=12).mean()
        + close.rolling(window=24, min_periods=24).mean()
    ) / 4.0


def _score_b1_trend_structure(
    *,
    open_: pd.Series,
    close: pd.Series,
    ma25: pd.Series,
    zxdkx: pd.Series,
    bbi: pd.Series,
) -> float:
    if len(close) < 5 or pd.isna(ma25.iloc[-1]) or pd.isna(zxdkx.iloc[-1]):
        return 3.0

    p_value = (float(open_.iloc[-1]) + float(close.iloc[-1])) / 2.0
    latest_ma25 = float(ma25.iloc[-1])
    latest_zxdkx = float(zxdkx.iloc[-1])
    if latest_ma25 <= 0.0 or latest_zxdkx <= 0.0:
        return 3.0

    ma25_rising = _recent_slope_non_negative(ma25)
    zxdkx_rising = _recent_slope_non_negative(zxdkx)
    if not (ma25_rising and zxdkx_rising):
        return 1.0

    p_below_ma25 = p_value < latest_ma25
    p_above_zxdkx = p_value > latest_zxdkx
    p_near_or_above_zxdkx = p_value >= latest_zxdkx * (1.0 - _APPROX_TOLERANCE)
    p_near_or_above_ma25 = p_value >= latest_ma25 * (1.0 - _APPROX_TOLERANCE)
    bbi_above_ma25 = _tail_all_greater(bbi, ma25, periods=30)
    ma25_above_zxdkx = _tail_all_greater(ma25, zxdkx, periods=30)

    if p_below_ma25 and p_near_or_above_zxdkx and bbi_above_ma25:
        return 5.0
    if p_below_ma25 and p_above_zxdkx:
        return 4.0
    if p_near_or_above_ma25 and ma25_above_zxdkx:
        return 3.0
    if p_value > latest_ma25:
        return 2.0
    return 1.0


def _score_b1_price_position(
    *,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    ma25: pd.Series,
    zxdq: pd.Series,
) -> float:
    recent_high = high.tail(120).dropna()
    recent_low = low.tail(120).dropna()
    if recent_high.empty or recent_low.empty or pd.isna(close.iloc[-1]):
        return 3.0

    box_high = float(recent_high.max())
    box_low = float(recent_low.min())
    if box_high <= box_low:
        return 3.0

    position = (float(close.iloc[-1]) - box_low) / (box_high - box_low)
    latest_ma25 = float(ma25.iloc[-1]) if not pd.isna(ma25.iloc[-1]) else float("nan")
    latest_zxdq = float(zxdq.iloc[-1]) if not pd.isna(zxdq.iloc[-1]) else float("nan")
    ma25_holds_zxdq = bool(
        pd.notna(latest_ma25)
        and pd.notna(latest_zxdq)
        and latest_zxdq > 0.0
        and latest_ma25 >= latest_zxdq * (1.0 - _APPROX_TOLERANCE)
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


def _score_b1_volume_behavior(open_: pd.Series, close: pd.Series, volume: pd.Series) -> float:
    if len(volume) < 2:
        return 3.0

    latest_volume = float(volume.iloc[-1])
    if latest_volume <= 0.0:
        return 1.0

    max_volume_index = volume.idxmax()
    max_volume = float(volume.loc[max_volume_index])
    volume_ratio = max_volume / latest_volume
    max_volume_bullish = bool(close.loc[max_volume_index] >= open_.loc[max_volume_index])
    pullback_volume_expanding = _latest_pullback_volume_expanding(close=close, volume=volume)

    if volume_ratio >= 2.0 and max_volume_bullish and pullback_volume_expanding:
        return 5.0
    if (volume_ratio >= 2.0 and max_volume_bullish) or (
        volume_ratio >= 3.0 and not max_volume_bullish and pullback_volume_expanding
    ):
        return 4.0
    if 1.5 <= volume_ratio < 2.0 and max_volume_bullish and pullback_volume_expanding:
        return 4.0
    if 1.5 <= volume_ratio < 2.0 and max_volume_bullish:
        return 3.0
    if max_volume_bullish or pullback_volume_expanding:
        return 2.0
    return 1.0


def _score_b1_macd_phase(
    *,
    history_len: int,
    weekly_macd: B1WeeklyMacdContext,
    daily_recent_death_cross: bool,
) -> float:
    if history_len < 60:
        return 3.0
    if not weekly_macd.red_histogram:
        return 1.0
    if daily_recent_death_cross:
        return 2.0
    if weekly_macd.diverging:
        return 2.0
    if weekly_macd.above_water and weekly_macd.improving:
        return 5.0
    if weekly_macd.above_water:
        return 4.0
    return 4.0


def _recent_slope_non_negative(series: pd.Series) -> bool:
    clean = pd.to_numeric(series, errors="coerce")
    if len(clean) < 5 or pd.isna(clean.iloc[-1]) or pd.isna(clean.iloc[-5]):
        return False
    return bool(float(clean.iloc[-1]) - float(clean.iloc[-5]) >= 0.0)


def _tail_all_greater(left: pd.Series, right: pd.Series, *, periods: int) -> bool:
    left_tail = pd.to_numeric(left, errors="coerce").tail(periods)
    right_tail = pd.to_numeric(right, errors="coerce").tail(periods)
    if len(left_tail) < periods or len(right_tail) < periods:
        return False
    valid = pd.DataFrame({"left": left_tail.to_numpy(), "right": right_tail.to_numpy()}).dropna()
    return bool(len(valid) == periods and (valid["left"] > valid["right"]).all())


def _latest_pullback_volume_expanding(*, close: pd.Series, volume: pd.Series) -> bool:
    if len(close) < 3:
        return False
    start = len(close) - 1
    while start > 0 and float(close.iloc[start]) < float(close.iloc[start - 1]):
        start -= 1
    if start >= len(close) - 2:
        return False
    pullback_volume = volume.iloc[start:].astype(float).reset_index(drop=True)
    return bool((pullback_volume.diff().dropna() > 0.0).any())


def _classify_b1_weekly_macd_context(frame: pd.DataFrame) -> B1WeeklyMacdContext:
    working = frame.copy()
    working["trade_date"] = pd.to_datetime(working["trade_date"])
    weekly_close = working.set_index("trade_date")["close"].astype(float).resample("W-FRI").last().dropna()
    if len(weekly_close) < 3:
        return B1WeeklyMacdContext(red_histogram=False, above_water=False, diverging=False, improving=False)

    macd = compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
    dif = pd.to_numeric(macd["dif"], errors="coerce").reset_index(drop=True)
    dea = pd.to_numeric(macd["dea"], errors="coerce").reset_index(drop=True)
    hist = pd.to_numeric(macd["macd_hist"], errors="coerce").reset_index(drop=True)
    if pd.isna(dif.iloc[-1]) or pd.isna(dea.iloc[-1]) or pd.isna(hist.iloc[-1]):
        return B1WeeklyMacdContext(red_histogram=False, above_water=False, diverging=False, improving=False)

    latest_hist = float(hist.iloc[-1])
    previous_hist = float(hist.iloc[-2]) if pd.notna(hist.iloc[-2]) else latest_hist
    recent_close = weekly_close.reset_index(drop=True).tail(12)
    recent_hist = hist.tail(12).dropna()
    prior_close_high = float(recent_close.iloc[:-1].max()) if len(recent_close) > 1 else float(recent_close.iloc[-1])
    prior_hist_high = float(recent_hist.iloc[:-1].max()) if len(recent_hist) > 1 else latest_hist
    price_near_high = prior_close_high > 0.0 and float(recent_close.iloc[-1]) >= prior_close_high * 0.98
    histogram_lags = prior_hist_high > 0.0 and latest_hist < prior_hist_high * 0.80

    return B1WeeklyMacdContext(
        red_histogram=latest_hist > 0.0,
        above_water=float(dif.iloc[-1]) > 0.0 and float(dea.iloc[-1]) > 0.0,
        diverging=bool(latest_hist > 0.0 and price_near_high and histogram_lags),
        improving=latest_hist >= previous_hist,
    )


def _has_recent_daily_macd_death_cross(frame: pd.DataFrame) -> bool:
    if {"dif", "dea"}.issubset(frame.columns):
        dif = pd.to_numeric(frame["dif"], errors="coerce")
        dea = pd.to_numeric(frame["dea"], errors="coerce")
    else:
        macd = compute_macd(frame[["close"]].astype(float))
        dif = macd["dif"]
        dea = macd["dea"]
    if len(dif) < 2:
        return False
    death_cross = (dif.shift(1) >= dea.shift(1)) & (dif < dea)
    return bool(death_cross.tail(3).fillna(False).any())


def _build_b1_comment(
    *,
    weekly_trend: Any,
    daily_trend: Any,
    weekly_macd: B1WeeklyMacdContext,
    verdict: str,
    daily_recent_death_cross: bool,
) -> str:
    combo_ok = is_constructive_macd_trend_combo(weekly_trend=weekly_trend, daily_trend=daily_trend)
    combo_text = "符合" if combo_ok else "不符合"
    death_cross_text = "近3日出现MACD死叉" if daily_recent_death_cross else "近3日未见MACD死叉"
    weekly_macd_text = (
        f"周MACD{'红柱' if weekly_macd.red_histogram else '非红柱'}、"
        f"{'水上' if weekly_macd.above_water else '未完全水上'}、"
        f"{'有背离' if weekly_macd.diverging else '无明显背离'}"
    )
    weekly_text = describe_macd_trend_state("周线", weekly_trend)
    daily_text = describe_macd_trend_state("日线", daily_trend)
    return (
        f"{weekly_text}、{daily_text}，该MACD组合{combo_text}b1，{weekly_macd_text}，{death_cross_text}，"
        f"按N型回调的超卖低点观察，当前结论为{verdict}。"
    )
