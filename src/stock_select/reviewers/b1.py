from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_trend, classify_weekly_macd_trend
from stock_select.environment_profiles import MethodEnvironmentProfile
from stock_select.indicators import compute_macd
from stock_select.review_orchestrator import (
    apply_macd_verdict_gate,
    compute_method_total_score,
    describe_macd_trend_state,
    is_constructive_macd_trend_combo,
    map_macd_phase_score,
)
from stock_select.review_protocol import infer_signal_type, infer_verdict_for_profile
from stock_select.reviewers.b2 import _score_b2_previous_abnormal_move
from stock_select.strategies.b1 import compute_zx_lines

_APPROX_TOLERANCE = 0.05
_B1_HIGH_RETURN_SCORE_COMBOS = {
    "rebound|T3|P3|V4|A5|M3.5",
    "distribution_risk|T2|P4|V4|A5|M4.0",
    "trend_start|T4|P3|V4|A5|M3.5",
}


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
    profile: MethodEnvironmentProfile | None = None,
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
    price_position = _score_b1_price_position(
        close=close,
        high=high,
        low=low,
        ma25=ma25,
        zxdq=zxdq,
        profile=profile,
    )
    volume_behavior = _score_b1_volume_behavior(recent_open, recent_close, recent_volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume)
    weekly_trend = classify_weekly_macd_trend(frame[["trade_date", "close"]], pick_date)
    daily_trend = classify_daily_macd_trend(frame[["trade_date", "close"]], pick_date)
    weekly_macd = _classify_b1_weekly_macd_context(frame)
    daily_recent_death_cross = _has_recent_daily_macd_death_cross(frame)
    daily_dif, daily_dea = _resolve_daily_macd_lines(frame)
    macd_phase = map_macd_phase_score(
        method="b1",
        history_len=len(close),
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
        environment_state=profile.state if profile is not None else None,
    )
    macd_phase = apply_b1_macd_divergence_penalty(
        macd_phase=macd_phase,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
        close=close,
        environment_state=profile.state if profile is not None else None,
    )
    score_fields = {
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
    }
    raw_total_score = (
        compute_method_total_score("b1", score_fields)
        if profile is None
        else round(sum(float(score_fields[field]) * weight for field, weight in profile.weights.items()), 2)
    )
    total_score = raw_total_score
    effective_environment_state = str(profile.state if profile is not None else "neutral")
    environment_gate = _compute_b1_environment_gate(
        close=close,
        ma25=ma25,
        dif=daily_dif,
        dea=daily_dea,
        profile=profile,
    )
    signal_type = infer_signal_type(
        latest_close=float(close.iloc[-1]),
        latest_open=float(open_.iloc[-1]),
        trend_structure=trend_structure,
        volume_behavior=volume_behavior,
        price_position=price_position,
    )
    family_result = _classify_b1_pass_family(
        signal_type=signal_type,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
    )
    high_return_combo = _classify_b1_high_return_combo(
        signal_type=signal_type,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
    )
    exact_combo_pass_allowed = _is_b1_exact_combo_pass_allowed(
        combo_key=high_return_combo["combo_key"],
        environment_state=effective_environment_state,
    )
    verdict = "PASS" if high_return_combo["match_type"] == "exact" and exact_combo_pass_allowed else _infer_b1_family_verdict(
        family=family_result["family"],
        tier=family_result["tier"],
        environment_state=effective_environment_state,
        total_score=total_score,
    )
    allow_divergence_pass = verdict == "PASS" and signal_type in {"trend_start", "rebound"}
    verdict = apply_macd_verdict_gate(
        method="b1",
        current_verdict=verdict,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
        allow_divergence_pass=allow_divergence_pass,
    )
    if high_return_combo["match_type"] == "exact" and exact_combo_pass_allowed:
        verdict = "PASS"
    verdict = _apply_b1_environment_verdict_gate(
        high_return_match=high_return_combo["match_type"],
        family=family_result["family"],
        environment_state=effective_environment_state,
        current_verdict=verdict,
        gate_flags=list(environment_gate["triggered_flags"]),
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
    score_layer = _score_b1_layer(
        verdict=verdict,
        environment_state=effective_environment_state,
        score_combo_key=high_return_combo["combo_key"],
        gate_flags=list(environment_gate.get("triggered_flags", [])),
        high_return_match=high_return_combo["match_type"],
    )
    total_score = _compute_b1_calibrated_total_score(
        raw_total_score=raw_total_score,
        verdict=verdict,
        environment_state=effective_environment_state,
        high_return_match=high_return_combo["match_type"],
        pass_family=family_result["family"],
        pass_family_tier=family_result["tier"],
        score_layer=score_layer["score_layer"],
        score_layer_score=score_layer["score_layer_score"],
        gate_flags=list(environment_gate.get("triggered_flags", [])),
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
        "raw_total_score": raw_total_score,
        "total_score": total_score,
        "signal_type": signal_type,
        "score_combo_key": high_return_combo["combo_key"],
        "high_return_combo_match": high_return_combo["match_type"],
        "pass_family": family_result["family"],
        "pass_family_tier": family_result["tier"],
        "verdict": verdict,
        "gate_flags": list(environment_gate.get("triggered_flags", [])),
        "gate_cooldown_active": environment_gate.get("cooldown_active"),
        "gate_below_ma25": environment_gate.get("below_ma25"),
        "gate_runup_pct": environment_gate.get("runup_pct"),
        "gate_sideways_amplitude_pct": environment_gate.get("sideways_amplitude_pct"),
        "gate_drawdown_pct": environment_gate.get("drawdown_pct"),
        "gate_weekly_slope_26w": environment_gate.get("weekly_slope_26w"),
        "gate_weekly_macd_cooldown_active": environment_gate.get("weekly_macd_cooldown_active"),
        "watch_reason": watch_reason,
        "watch_score": watch_score,
        "watch_tier": watch_tier,
        "score_layer": score_layer["score_layer"],
        "score_layer_score": score_layer["score_layer_score"],
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
    close_above_zxdkx_pct: float | None = None,
    close_above_zxdq_pct: float | None = None,
    day_pct: float | None = None,
    profile: MethodEnvironmentProfile | None = None,
) -> str:
    is_weak_profile = profile is not None and profile.state == "weak"

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
        weak_repair_start_whitelist = (
            is_weak_profile
            and total_score >= 4.35
            and trend_structure >= 4.0
            and 3.0 <= price_position <= 4.0
            and volume_behavior >= 5.0
            and previous_abnormal_move >= 5.0
            and 3.5 <= macd_phase <= 4.0
            and (close_above_ma25_pct is None or close_above_ma25_pct <= -5.0)
            and (ma25_above_zxdkx_pct is None or ma25_above_zxdkx_pct >= 6.0)
            and close_above_zxdkx_pct is not None
            and 0.0 <= close_above_zxdkx_pct <= 8.0
            and (day_pct is None or day_pct <= 0.5)
        )
        if repair_start_setup and not is_weak_profile:
            return "PASS"
        if weak_repair_start_whitelist:
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
        weak_rebound_repair_whitelist = (
            is_weak_profile
            and total_score >= 4.18
            and trend_structure >= 4.0
            and 3.0 <= price_position <= 4.0
            and volume_behavior >= 4.0
            and previous_abnormal_move >= 5.0
            and 3.8 <= macd_phase <= 4.05
            and (close_above_ma25_pct is None or close_above_ma25_pct <= -3.0)
            and (ma25_above_zxdkx_pct is None or ma25_above_zxdkx_pct >= 6.0)
            and close_above_zxdkx_pct is not None
            and 0.0 <= close_above_zxdkx_pct <= 8.0
            and (close_above_zxdq_pct is None or close_above_zxdq_pct <= -5.0)
            and (day_pct is None or day_pct <= 0.5)
        )
        if rebound_repair_setup and not is_weak_profile:
            return "PASS"
        if weak_rebound_repair_whitelist:
            return "PASS"
        return "WATCH"
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
    profile: MethodEnvironmentProfile | None = None,
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
    mode = profile.subscore_mode.get("price_position", "default") if profile is not None else "default"

    if mode == "left_side_favored":
        if position <= 0.45:
            return 5.0
        if position <= 0.60:
            return 4.0
    if mode == "less_left_bias":
        if position <= 0.30:
            return 5.0
        if position <= 0.50:
            return 4.0

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
        return 3.0
    return 4.0


def _format_b1_bucket(value: float) -> str:
    rounded = round(float(value))
    return str(int(max(1, min(5, rounded))))


def _format_b1_macd_bucket(value: float) -> str:
    bucket = round(float(value) * 2.0) / 2.0
    bounded = max(1.0, min(5.0, bucket))
    return f"{bounded:.1f}"


def _build_b1_score_combo_key(
    *,
    signal_type: str,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
) -> str:
    return (
        f"{signal_type}|"
        f"T{_format_b1_bucket(trend_structure)}|"
        f"P{_format_b1_bucket(price_position)}|"
        f"V{_format_b1_bucket(volume_behavior)}|"
        f"A{_format_b1_bucket(previous_abnormal_move)}|"
        f"M{_format_b1_macd_bucket(macd_phase)}"
    )


def _classify_b1_high_return_combo(
    *,
    signal_type: str,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
) -> dict[str, str]:
    combo_key = _build_b1_score_combo_key(
        signal_type=signal_type,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
    )
    match_type = "exact" if combo_key in _B1_HIGH_RETURN_SCORE_COMBOS else _classify_b1_high_return_core_combo(combo_key)
    return {"combo_key": combo_key, "match_type": match_type}


def _classify_b1_high_return_core_combo(combo_key: str) -> str:
    parts = combo_key.split("|")
    if len(parts) != 6:
        return "none"
    signal_type, trend, price, volume, abnormal, macd = parts
    if abnormal != "A5":
        return "none"
    if (
        signal_type == "distribution_risk"
        and trend == "T2"
        and price in {"P3", "P4"}
        and volume in {"V4", "V5"}
        and macd == "M4.0"
    ):
        return "dist_core"
    if (
        signal_type == "rebound"
        and trend == "T3"
        and price in {"P2", "P3"}
        and volume == "V4"
        and macd in {"M3.5", "M4.0"}
    ):
        return "rebound_core"
    if (
        signal_type == "trend_start"
        and trend == "T4"
        and price in {"P3", "P4"}
        and volume == "V4"
        and macd in {"M3.5", "M4.0"}
    ):
        return "trend_core"
    return "none"


def _is_b1_exact_combo_pass_allowed(*, combo_key: str, environment_state: str) -> bool:
    state = environment_state.lower()
    if combo_key not in _B1_HIGH_RETURN_SCORE_COMBOS:
        return False
    if state == "neutral":
        return True
    if state == "strong":
        return combo_key == "trend_start|T4|P3|V4|A5|M3.5"
    if state == "weak":
        return combo_key == "distribution_risk|T2|P4|V4|A5|M4.0"
    return False


def _score_b1_layer(
    *,
    verdict: str,
    environment_state: str,
    score_combo_key: str,
    gate_flags: list[str],
    high_return_match: str = "none",
) -> dict[str, float | str | None]:
    state = environment_state.lower()
    flags = set(gate_flags)
    layer_score = 0.0
    layer: str | None = None

    pass_scores = {
        ("neutral", "distribution_risk|T2|P4|V4|A5|M4.0"): 95.0,
        ("neutral", "rebound|T3|P3|V4|A5|M3.5"): 90.0,
        ("neutral", "trend_start|T4|P3|V4|A5|M3.5"): 78.0,
        ("strong", "trend_start|T4|P3|V4|A5|M3.5"): 82.0,
        ("weak", "distribution_risk|T2|P4|V4|A5|M4.0"): 84.0,
    }
    watch_scores = {
        ("strong", "trend_start|T4|P3|V4|A5|M3.5"): 76.0,
        ("neutral", "distribution_risk|T2|P4|V4|A5|M4.0"): 72.0,
        ("neutral", "rebound|T3|P3|V4|A5|M3.5"): 70.0,
        ("weak", "distribution_risk|T2|P4|V4|A5|M4.0"): 72.0,
    }

    if verdict == "PASS":
        layer_score = pass_scores.get((state, score_combo_key), 70.0)
        if "runup_over_limit" in flags:
            layer_score -= 8.0
        if "below_ma25" in flags:
            layer_score -= 6.0
        if layer_score >= 88.0:
            layer = "PASS-A"
        elif layer_score >= 80.0:
            layer = "PASS-B"
        else:
            layer = "PASS-C"
    elif verdict == "WATCH":
        layer_score = watch_scores.get((state, score_combo_key), 50.0)
        core_watch_scores = {
            ("neutral", "dist_core"): 62.0,
            ("neutral", "rebound_core"): 70.0,
            ("neutral", "trend_core"): 70.0,
            ("strong", "trend_core"): 74.0,
            ("weak", "rebound_core"): 58.0,
        }
        layer_score = max(layer_score, core_watch_scores.get((state, high_return_match), 0.0))
        if "runup_over_limit" in flags:
            layer_score += 2.0
        if "below_ma25" in flags:
            layer_score -= 4.0
        if layer_score >= 70.0:
            layer = "WATCH-A"
        elif layer_score >= 55.0:
            layer = "WATCH-B"
        else:
            layer = "WATCH-C"

    return {"score_layer": layer, "score_layer_score": round(layer_score, 2) if layer is not None else None}


def _compute_b1_calibrated_total_score(
    *,
    raw_total_score: float,
    verdict: str,
    environment_state: str,
    high_return_match: str,
    pass_family: str | None,
    pass_family_tier: str | None,
    score_layer: str | None,
    score_layer_score: float | None,
    gate_flags: list[str],
) -> float:
    flags = set(gate_flags)
    match = str(high_return_match or "none")
    layer = str(score_layer or "")
    state = environment_state.lower()

    if match == "exact":
        score = 4.72
        if layer == "PASS-A":
            score += 0.12
        elif layer == "PASS-B":
            score += 0.06
        elif verdict == "WATCH":
            score -= 0.22
        if state == "neutral":
            score += 0.03
    elif match in {"dist_core", "rebound_core", "trend_core"}:
        score = {
            "dist_core": 4.28,
            "rebound_core": 4.22,
            "trend_core": 4.18,
        }[match]
        if layer == "WATCH-A":
            score += 0.08
        elif layer == "WATCH-C":
            score -= 0.12
    elif pass_family is not None and str(pass_family_tier or "") == "core":
        score = 3.88
    elif pass_family is not None and str(pass_family_tier or "") == "near":
        score = 3.62
    else:
        score = min(float(raw_total_score), 3.35)

    if "runup_over_limit" in flags:
        score -= 0.18
    if "below_ma25" in flags and match != "exact":
        score -= 0.12
    if "cooldown_active" in flags and match not in {"exact", "dist_core"}:
        score -= 0.08
    if verdict == "FAIL":
        score = min(score, 3.85)

    return round(max(0.0, min(5.0, score)), 2)


def _classify_b1_pass_family(
    *,
    signal_type: str,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
) -> dict[str, str | None]:
    if (
        signal_type == "rebound"
        and 3.0 <= trend_structure <= 4.0
        and price_position == 3.0
        and volume_behavior >= 4.0
        and previous_abnormal_move >= 5.0
        and 3.3 <= macd_phase <= 3.8
    ):
        return {"family": "rebound", "tier": "core"}
    if (
        signal_type == "rebound"
        and 3.0 <= trend_structure <= 4.0
        and 2.0 <= price_position <= 4.0
        and volume_behavior >= 3.0
        and previous_abnormal_move >= 4.0
        and 3.0 <= macd_phase <= 4.0
    ):
        return {"family": "rebound", "tier": "near"}

    if (
        signal_type == "distribution_risk"
        and 2.0 <= trend_structure <= 3.0
        and price_position == 4.0
        and volume_behavior >= 4.0
        and previous_abnormal_move >= 5.0
        and 3.6 <= macd_phase <= 4.2
    ):
        return {"family": "distribution", "tier": "core"}
    if (
        signal_type == "distribution_risk"
        and 2.0 <= trend_structure <= 3.0
        and 3.0 <= price_position <= 5.0
        and volume_behavior >= 3.0
        and previous_abnormal_move >= 4.0
        and 3.2 <= macd_phase <= 4.3
    ):
        return {"family": "distribution", "tier": "near"}

    if (
        signal_type == "trend_start"
        and 4.0 <= trend_structure <= 5.0
        and price_position == 3.0
        and volume_behavior >= 4.0
        and previous_abnormal_move >= 5.0
        and 3.3 <= macd_phase <= 3.8
    ):
        return {"family": "trend_start", "tier": "core"}
    if (
        signal_type == "trend_start"
        and trend_structure >= 4.0
        and 3.0 <= price_position <= 4.0
        and volume_behavior >= 3.0
        and previous_abnormal_move >= 4.0
        and 3.1 <= macd_phase <= 4.0
    ):
        return {"family": "trend_start", "tier": "near"}

    return {"family": None, "tier": "none"}


def _infer_b1_family_verdict(
    *,
    family: str | None,
    tier: str,
    environment_state: str,
    total_score: float,
) -> str:
    if family is None or tier == "none":
        return "FAIL"
    return "WATCH"


def _apply_b1_environment_verdict_gate(
    *,
    high_return_match: str = "none",
    family: str | None,
    environment_state: str,
    current_verdict: str,
    gate_flags: list[str],
) -> str:
    if current_verdict != "PASS":
        return current_verdict

    state = environment_state.lower()
    if "runup_over_limit" in gate_flags:
        return "WATCH"
    if high_return_match == "exact" and state in {"neutral", "weak"} and "below_ma25" in gate_flags:
        return "WATCH"
    return current_verdict


def _compute_b1_environment_gate(
    *,
    close: pd.Series,
    ma25: pd.Series,
    dif: pd.Series,
    dea: pd.Series,
    profile: MethodEnvironmentProfile | None = None,
    trade_dates: pd.Series | None = None,
    weekly_dif: pd.Series | None = None,
    weekly_dea: pd.Series | None = None,
) -> dict[str, Any]:
    state = str(profile.state if profile is not None else "neutral").lower()
    cooldown_days = 4 if state == "weak" else 2
    cooldown_active = False
    below_ma25 = bool(close.iloc[-1] < ma25.iloc[-1]) if len(close) and len(ma25) else False
    runup_pct = _compute_b1_30d_runup_pct(close=close)
    sideways_amplitude_pct = _compute_b1_sideways_amplitude_pct(close=close)
    weekly_slope_26w = _compute_b1_weekly_slope_26w(close=close, trade_dates=trade_dates)
    weekly_macd_cooldown_active = _compute_b1_weekly_macd_cooldown_active(
        close=close,
        trade_dates=trade_dates,
        weekly_dif=weekly_dif,
        weekly_dea=weekly_dea,
    )

    runup_limit = _resolve_b1_runup_limit(environment_state=state)
    sideways_limit = 20.0
    weekly_slope_limit = 0.2

    if len(dif) >= 2 and len(dea) >= 2:
        death_cross = ((dif.shift(1) >= dea.shift(1)) & (dif < dea)).fillna(False)
        golden_cross = ((dif.shift(1) <= dea.shift(1)) & (dif > dea)).fillna(False)
        death_indexes = [int(index) for index, value in enumerate(death_cross.tolist()) if value]
        golden_indexes = [int(index) for index, value in enumerate(golden_cross.tolist()) if value]
        latest_death_index = death_indexes[-1] if death_indexes else None
        latest_golden_index = golden_indexes[-1] if golden_indexes else None
        if latest_death_index is not None:
            if latest_golden_index is None or latest_golden_index < latest_death_index:
                bars_since_death_cross = len(dif) - 1 - latest_death_index
                cooldown_active = bars_since_death_cross < cooldown_days

    triggered_flags: list[str] = []
    if cooldown_active:
        triggered_flags.append("cooldown_active")
    if weekly_macd_cooldown_active:
        triggered_flags.append("weekly_macd_cooldown_active")
    if weekly_slope_26w is not None and weekly_slope_26w <= weekly_slope_limit:
        triggered_flags.append("weekly_slope_not_rising")
    if below_ma25:
        triggered_flags.append("below_ma25")
    if runup_pct is not None and runup_pct >= runup_limit:
        triggered_flags.append("runup_over_limit")
    if sideways_amplitude_pct is not None and sideways_amplitude_pct <= sideways_limit:
        triggered_flags.append("sideways_tight_range")

    return {
        "score_penalty": round(
            (0.15 if below_ma25 else 0.0)
            + (0.2 if runup_pct is not None and runup_pct >= runup_limit else 0.0)
            + (0.15 if sideways_amplitude_pct is not None and sideways_amplitude_pct <= sideways_limit else 0.0),
            2,
        ),
        "cooldown_active": cooldown_active,
        "cooldown_reason": "recent_death_cross_cooldown" if cooldown_active else None,
        "runup_pct": runup_pct,
        "drawdown_pct": None,
        "below_ma25": below_ma25,
        "sideways_amplitude_pct": sideways_amplitude_pct,
        "weekly_slope_26w": weekly_slope_26w,
        "weekly_macd_cooldown_active": weekly_macd_cooldown_active,
        "triggered_flags": triggered_flags,
    }


def _compute_b1_30d_runup_pct(*, close: pd.Series) -> float | None:
    values = pd.to_numeric(close, errors="coerce").dropna().tail(30)
    if values.empty:
        return None
    trailing_high = float(values.max())
    trailing_low = float(values.min())
    if trailing_low <= 0.0:
        return None
    return round((trailing_high / trailing_low - 1.0) * 100.0, 2)


def _resolve_b1_runup_limit(*, environment_state: str) -> float:
    state = environment_state.lower()
    if state == "strong":
        return 60.0
    if state == "weak":
        return 80.0
    return 70.0


def _compute_b1_sideways_amplitude_pct(*, close: pd.Series) -> float | None:
    values = pd.to_numeric(close, errors="coerce").dropna().tail(10)
    if len(values) < 5:
        return None
    latest_high = float(values.max())
    latest_low = float(values.min())
    if latest_low <= 0.0:
        return None
    return round((latest_high / latest_low - 1.0) * 100.0, 2)


def _compute_b1_weekly_slope_26w(*, close: pd.Series, trade_dates: pd.Series | None = None) -> float | None:
    if trade_dates is None or len(close) != len(trade_dates):
        return None
    weekly_close = (
        pd.DataFrame({"trade_date": pd.to_datetime(trade_dates, errors="coerce"), "close": pd.to_numeric(close, errors="coerce")})
        .dropna(subset=["trade_date", "close"])
        .set_index("trade_date")["close"]
        .resample("W-FRI")
        .last()
        .dropna()
        .tail(26)
    )
    if len(weekly_close) < 26:
        return None
    start = float(weekly_close.iloc[0])
    end = float(weekly_close.iloc[-1])
    if start <= 0.0:
        return None
    return round((end / start - 1.0) * 100.0 / 25.0, 3)


def _compute_b1_weekly_macd_cooldown_active(
    *,
    close: pd.Series,
    trade_dates: pd.Series | None = None,
    weekly_dif: pd.Series | None = None,
    weekly_dea: pd.Series | None = None,
) -> bool:
    if weekly_dif is None or weekly_dea is None:
        if trade_dates is None or len(close) != len(trade_dates):
            return False
        weekly_close = (
            pd.DataFrame({"trade_date": pd.to_datetime(trade_dates, errors="coerce"), "close": pd.to_numeric(close, errors="coerce")})
            .dropna(subset=["trade_date", "close"])
            .set_index("trade_date")["close"]
            .resample("W-FRI")
            .last()
            .dropna()
        )
        if len(weekly_close) < 2:
            return False
        weekly_macd = compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
        weekly_dif = pd.to_numeric(weekly_macd["dif"], errors="coerce")
        weekly_dea = pd.to_numeric(weekly_macd["dea"], errors="coerce")
    dif = pd.to_numeric(weekly_dif, errors="coerce").reset_index(drop=True)
    dea = pd.to_numeric(weekly_dea, errors="coerce").reset_index(drop=True)
    if len(dif) < 2 or len(dea) < 2:
        return False
    death_cross = ((dif.shift(1) >= dea.shift(1)) & (dif < dea)).fillna(False)
    golden_cross = ((dif.shift(1) <= dea.shift(1)) & (dif > dea)).fillna(False)
    death_indexes = [int(index) for index, value in enumerate(death_cross.tolist()) if value]
    golden_indexes = [int(index) for index, value in enumerate(golden_cross.tolist()) if value]
    latest_death_index = death_indexes[-1] if death_indexes else None
    latest_golden_index = golden_indexes[-1] if golden_indexes else None
    if latest_death_index is None:
        return False
    if latest_golden_index is not None and latest_golden_index > latest_death_index:
        return False
    bars_since_death_cross = len(dif) - 1 - latest_death_index
    return bars_since_death_cross < 2


def _resolve_daily_macd_lines(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if {"dif", "dea"}.issubset(frame.columns):
        dif = pd.to_numeric(frame["dif"], errors="coerce")
        dea = pd.to_numeric(frame["dea"], errors="coerce")
    else:
        daily_macd = compute_macd(frame[["close"]].astype(float))
        dif = pd.to_numeric(daily_macd["dif"], errors="coerce")
        dea = pd.to_numeric(daily_macd["dea"], errors="coerce")
    return dif.reset_index(drop=True), dea.reset_index(drop=True)


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
    dif, dea = _resolve_daily_macd_lines(frame)
    if len(dif) < 2:
        return False
    death_cross = (dif.shift(1) >= dea.shift(1)) & (dif < dea)
    return bool(death_cross.tail(3).fillna(False).any())


def _is_weekly_initial_divergence(weekly_trend: Any) -> bool:
    return bool(
        str(getattr(weekly_trend, "phase", "")) == "rising"
        and int(getattr(weekly_trend, "phase_index", 0) or 0) <= 1
        and bool(getattr(weekly_trend, "is_rising_initial", False))
        and bool(getattr(weekly_trend, "is_top_divergence", False))
    )


def apply_b1_macd_divergence_penalty(
    *,
    macd_phase: float,
    weekly_trend: Any,
    daily_trend: Any,
    close: pd.Series,
    environment_state: str | None = None,
) -> float:
    score = float(macd_phase)
    normalized_environment = str(environment_state or "").strip().lower()

    if bool(getattr(weekly_trend, "is_top_divergence", False)):
        score -= 0.5

    if bool(getattr(daily_trend, "is_top_divergence", False)):
        daily_penalty_waived = _daily_top_divergence_penalty_waived(close=close)
        if not daily_penalty_waived:
            score -= 0.5

    return round(max(1.0, min(5.0, score)), 2)


def _daily_top_divergence_penalty_waived(*, close: pd.Series) -> bool:
    previous_low, current_low = _latest_two_pullback_lows(close=close)
    if previous_low is None or current_low is None:
        return False
    return current_low >= previous_low


def _latest_two_pullback_lows(*, close: pd.Series) -> tuple[float | None, float | None]:
    values = pd.to_numeric(close, errors="coerce").dropna().reset_index(drop=True)
    if len(values) < 5:
        return None, None

    pivot_lows: list[float] = []
    for idx in range(1, len(values) - 1):
        prev_value = float(values.iloc[idx - 1])
        current_value = float(values.iloc[idx])
        next_value = float(values.iloc[idx + 1])
        if current_value <= prev_value and current_value <= next_value:
            pivot_lows.append(current_value)

    if len(pivot_lows) < 2:
        return None, None
    return pivot_lows[-2], pivot_lows[-1]


def _is_weak_zxdkx_repair_whitelist(
    *,
    signal_type: str,
    total_score: float,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    close_above_ma25_pct: float | None,
    ma25_above_zxdkx_pct: float | None,
    close_above_zxdkx_pct: float | None,
    close_above_zxdq_pct: float | None,
    day_pct: float | None,
) -> bool:
    if signal_type == "trend_start":
        return bool(
            total_score >= 4.35
            and trend_structure >= 4.0
            and 3.0 <= price_position <= 4.0
            and volume_behavior >= 5.0
            and previous_abnormal_move >= 5.0
            and 3.5 <= macd_phase <= 4.0
            and (close_above_ma25_pct is None or close_above_ma25_pct <= -5.0)
            and (ma25_above_zxdkx_pct is None or ma25_above_zxdkx_pct >= 6.0)
            and close_above_zxdkx_pct is not None
            and 0.0 <= close_above_zxdkx_pct <= 8.0
            and (day_pct is None or day_pct <= 0.5)
        )
    if signal_type == "rebound":
        return bool(
            total_score >= 4.18
            and trend_structure >= 4.0
            and 3.0 <= price_position <= 4.0
            and volume_behavior >= 4.0
            and previous_abnormal_move >= 5.0
            and 3.8 <= macd_phase <= 4.05
            and (close_above_ma25_pct is None or close_above_ma25_pct <= -3.0)
            and (ma25_above_zxdkx_pct is None or ma25_above_zxdkx_pct >= 6.0)
            and close_above_zxdkx_pct is not None
            and 0.0 <= close_above_zxdkx_pct <= 8.0
            and (close_above_zxdq_pct is None or close_above_zxdq_pct <= -5.0)
            and (day_pct is None or day_pct <= 0.5)
        )
    return False


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
