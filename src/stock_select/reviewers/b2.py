from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_trend, classify_weekly_macd_trend
from stock_select.analysis.macd_wave_score import score_macd_review_context_from_history
from stock_select.environment_profiles import MethodEnvironmentProfile
from stock_select.indicators import compute_macd
from stock_select.review_orchestrator import (
    compute_method_total_score,
    describe_macd_trend_state,
    is_constructive_macd_trend_combo,
    map_macd_phase_score,
)
from stock_select.review_protocol import compute_b2_weighted_total_for_profile
from stock_select.review_protocol import infer_signal_type
from stock_select.strategies.b1 import compute_zx_lines


def _resolve_b2_daily_state_hint(*, weekly_trend: Any, daily_trend: Any) -> str:
    daily_stage = str(getattr(daily_trend, "wave_stage", "") or "")
    weekly_stage = str(getattr(weekly_trend, "wave_stage", "") or "")
    daily_phase = str(getattr(daily_trend, "phase", "") or "")
    phase_index = int(getattr(daily_trend, "phase_index", 0) or 0)

    if daily_phase == "falling":
        if "背离" in daily_stage:
            return "even_adjusting_invalid_divergence"
        return "even_adjusting"
    if phase_index >= 5:
        return "late_odd_wave"
    if daily_phase == "rising" and daily_stage in {"分歧", "背离", "强势转分歧", "分歧转背离"}:
        return "odd_stage3"
    if weekly_stage in {"分歧", "背离", "强势转分歧", "分歧转背离"}:
        return "odd_stage3"
    return "healthy_breakout"


def _compute_b2_overheat_penalty(
    *,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    daily_state_hint: str,
    signal: str | None = None,
    price_position: float | None = None,
    profile: MethodEnvironmentProfile | None = None,
) -> float:
    state = profile.state if profile is not None else "neutral"
    if state == "weak":
        return 0.0
    if state == "strong":
        if signal not in {"B3", "B3+"}:
            return 0.0
        if price_position is None or float(price_position) < 5.0:
            return 0.0
    params = {
        "strong": {
            "sideways_window": 10,
            "sideways_amp_pct": 15.0,
            "runup_window": 30,
            "runup_gain_pct": 50.0,
            "sideways_penalty": 0.15,
            "runup_penalty": 0.10,
            "risk_bonus": 0.15,
        },
        "neutral": {
            "sideways_window": 10,
            "sideways_amp_pct": 13.0,
            "runup_window": 30,
            "runup_gain_pct": 45.0,
            "sideways_penalty": 0.20,
            "runup_penalty": 0.25,
            "risk_bonus": 0.15,
        },
    }.get(state, {
        "sideways_window": 10,
        "sideways_amp_pct": 13.0,
        "runup_window": 30,
        "runup_gain_pct": 45.0,
        "sideways_penalty": 0.20,
        "runup_penalty": 0.25,
        "risk_bonus": 0.15,
    })

    penalty = 0.0
    close_vals = close.dropna().astype(float)
    high_vals = high.dropna().astype(float)
    low_vals = low.dropna().astype(float)

    if len(high_vals) >= params["sideways_window"] and len(low_vals) >= params["sideways_window"]:
        recent_high = float(high_vals.tail(params["sideways_window"]).max())
        recent_low = float(low_vals.tail(params["sideways_window"]).min())
        if recent_low > 0.0:
            amp_pct = (recent_high / recent_low - 1.0) * 100.0
            if amp_pct <= params["sideways_amp_pct"]:
                penalty += params["sideways_penalty"]

    if len(close_vals) >= params["runup_window"]:
        start_close = float(close_vals.iloc[-params["runup_window"]])
        latest_close = float(close_vals.iloc[-1])
        if start_close > 0.0:
            gain_pct = (latest_close / start_close - 1.0) * 100.0
            if gain_pct >= params["runup_gain_pct"]:
                penalty += params["runup_penalty"]

    if penalty > 0.0 and daily_state_hint in {
        "odd_stage3",
        "late_odd_wave",
        "even_adjusting",
        "even_adjusting_invalid_divergence",
    }:
        penalty += params["risk_bonus"]

    return round(penalty, 2)


def review_b2_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
    signal: str | None = None,
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
    ma25 = close.rolling(window=25, min_periods=25).mean()
    zxdq, zxdkx = _resolve_zx_lines(frame)
    support_slopes = _compute_recent_support_slopes(zxdq=zxdq, zxdkx=zxdkx)

    weekly_trend = classify_weekly_macd_trend(frame[["trade_date", "close"]], pick_date)
    daily_trend = classify_daily_macd_trend(frame[["trade_date", "close"]], pick_date)
    strong_negative_macd_guard = _resolve_strong_negative_macd_guard(frame)

    if profile is not None and profile.state == "weak":
        weak_result = _score_b2_weak_bundle(
            close=close,
            open_=open_,
            high=high,
            low=low,
            volume=volume,
            ma25=ma25,
            zxdq=zxdq,
            zxdkx=zxdkx,
            weekly_trend=weekly_trend,
            daily_trend=daily_trend,
            signal=signal,
            profile=profile,
        )
        comment = _build_b2_comment(weekly_trend=weekly_trend, daily_trend=daily_trend, verdict=str(weak_result["verdict"]))
        return {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": weak_result["trend_structure"],
            "price_position": weak_result["price_position"],
            "volume_behavior": weak_result["volume_behavior"],
            "previous_abnormal_move": weak_result["previous_abnormal_move"],
            "macd_phase": weak_result["macd_phase"],
            "total_score": weak_result["total_score"],
            "signal": signal,
            "signal_type": weak_result["signal_type"],
            "verdict": weak_result["verdict"],
            "elastic_watch": weak_result["elastic_watch"],
            "elastic_watch_reason": weak_result["elastic_watch_reason"],
            "watch_score": weak_result["watch_score"],
            "watch_tier": weak_result["watch_tier"],
            "comment": comment,
        }

    if profile is not None and profile.state == "neutral":
        neutral_result = _score_b2_neutral_bundle(
            close=close,
            open_=open_,
            high=high,
            low=low,
            volume=volume,
            ma25=ma25,
            zxdq=zxdq,
            zxdkx=zxdkx,
            weekly_trend=weekly_trend,
            daily_trend=daily_trend,
            signal=signal,
            profile=profile,
        )
        comment = _build_b2_comment(
            weekly_trend=weekly_trend,
            daily_trend=daily_trend,
            verdict=str(neutral_result["verdict"]),
        )
        return {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": neutral_result["trend_structure"],
            "price_position": neutral_result["price_position"],
            "volume_behavior": neutral_result["volume_behavior"],
            "previous_abnormal_move": neutral_result["previous_abnormal_move"],
            "macd_phase": neutral_result["macd_phase"],
            "total_score": neutral_result["total_score"],
            "signal": signal,
            "signal_type": neutral_result["signal_type"],
            "verdict": neutral_result["verdict"],
            "elastic_watch": neutral_result["elastic_watch"],
            "elastic_watch_reason": neutral_result["elastic_watch_reason"],
            "watch_score": neutral_result["watch_score"],
            "watch_tier": neutral_result["watch_tier"],
            "comment": comment,
        }

    trend_structure = _score_b2_trend_structure(
        close=close,
        low=low,
        ma25=ma25,
        zxdkx=zxdkx,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
        profile=profile,
    )
    price_position = _score_b2_price_position(
        close=close,
        high=high,
        low=low,
        ma25=ma25,
        zxdq=zxdq,
        profile=profile,
    )
    volume_behavior = _score_b2_volume_behavior(close=close, volume=volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume)
    if profile is not None:
        previous_abnormal_move = _score_b2_previous_abnormal_move(
            open_=open_,
            close=close,
            low=low,
            volume=volume,
            profile=profile,
        )
    macd_phase = _score_b2_macd_phase(frame, signal=signal, profile=profile)
    daily_state_hint = _resolve_b2_daily_state_hint(weekly_trend=weekly_trend, daily_trend=daily_trend)

    scores = {
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
    }
    base_total_score = (
        compute_b2_weighted_total_for_profile(scores, profile=profile, signal=signal)
        if profile is not None
        else compute_method_total_score("b2", scores, signal=signal)
    )
    overheat_penalty = _compute_b2_overheat_penalty(
        close=close,
        high=high,
        low=low,
        daily_state_hint=daily_state_hint,
        signal=signal,
        price_position=price_position,
        profile=profile,
    )
    total_score = round(max(1.0, float(base_total_score) - overheat_penalty), 2)
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
        zxdq_5d_slope_pct=support_slopes.get("zxdq_5d"),
        profile=profile,
        strong_negative_macd_guard=strong_negative_macd_guard,
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


def _score_b2_weak_bundle(
    *,
    close: pd.Series,
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    ma25: pd.Series,
    zxdq: pd.Series,
    zxdkx: pd.Series,
    weekly_trend: Any,
    daily_trend: Any,
    signal: str | None,
    profile: MethodEnvironmentProfile,
) -> dict[str, object]:
    support_slopes = _compute_recent_support_slopes(zxdq=zxdq, zxdkx=zxdkx)
    recent_volume = volume.tail(90).dropna()
    abnormal_gap_pct: float | None = None
    if not recent_volume.empty:
        event_idx = int(recent_volume.idxmax())
        event_open = float(open_.loc[event_idx])
        event_close = float(close.loc[event_idx])
        abnormal_price = event_close if event_close >= event_open else event_open
        if abnormal_price > 0.0:
            abnormal_gap_pct = (float(close.iloc[-1]) / abnormal_price - 1.0) * 100.0
    trend_structure = _score_b2_trend_structure(
        close=close,
        low=low,
        ma25=ma25,
        zxdkx=zxdkx,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
        profile=profile,
    )
    price_position = _score_b2_price_position(
        close=close,
        high=high,
        low=low,
        ma25=ma25,
        zxdq=zxdq,
        profile=profile,
    )
    volume_behavior = _score_b2_volume_behavior(close=close, volume=volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(
        open_=open_,
        close=close,
        low=low,
        volume=volume,
        profile=profile,
    )
    macd_phase = _score_b2_macd_phase(
        pd.DataFrame({"trade_date": range(len(close)), "close": close}),
        signal=signal,
        profile=profile,
    )
    scores = {
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
    }
    base_total_score = compute_b2_weighted_total_for_profile(scores, profile=profile, signal=signal)
    daily_state_hint = _resolve_b2_daily_state_hint(weekly_trend=weekly_trend, daily_trend=daily_trend)
    overheat_penalty = _compute_b2_overheat_penalty(
        close=close,
        high=high,
        low=low,
        daily_state_hint=daily_state_hint,
        signal=signal,
        price_position=price_position,
        profile=profile,
    )
    total_score = round(max(1.0, float(base_total_score) - overheat_penalty), 2)
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
        zxdq_5d_slope_pct=support_slopes.get("zxdq_5d"),
        profile=profile,
    )
    relaunch_override = _infer_b2_weak_relaunch_override(
        close=close,
        high=high,
        low=low,
        volume=volume,
        ma25=ma25,
        zxdq=zxdq,
        zxdkx=zxdkx,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        total_score=total_score,
        signal=signal,
        signal_type=signal_type,
        current_verdict=verdict,
    )
    verdict = str(relaunch_override.get("verdict") or verdict)
    watch_score_candidate = score_b2_watch(
        verdict="WATCH",
        total_score=total_score,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        elastic_watch_reason=None,
        signal=signal,
        signal_type=signal_type,
    )
    if (
        verdict == "WATCH"
        and signal == "B2"
        and signal_type == "rebound"
        and trend_structure >= 4.0
        and price_position <= 2.0
        and volume_behavior >= 4.0
        and previous_abnormal_move >= 5.0
        and macd_phase >= 4.34
        and total_score >= 4.0
        and total_score <= 4.06
        and watch_score_candidate is not None
        and 60.0 <= float(watch_score_candidate) < 70.0
        and abnormal_gap_pct is not None
        and abnormal_gap_pct <= 12.0
        and (support_slopes.get("zxdq_5d") is not None and float(support_slopes["zxdq_5d"]) >= 0.0)
    ):
        verdict = "PASS"
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
    if verdict == "WATCH" and relaunch_override.get("watch_tier") is not None:
        watch_tier = str(relaunch_override["watch_tier"])
    return {
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
        "total_score": total_score,
        "signal_type": signal_type,
        "verdict": verdict,
        "elastic_watch": elastic_watch,
        "elastic_watch_reason": elastic_watch_reason,
        "watch_score": watch_score,
        "watch_tier": watch_tier,
    }


def _infer_b2_weak_relaunch_override(
    *,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    ma25: pd.Series,
    zxdq: pd.Series,
    zxdkx: pd.Series,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    total_score: float,
    signal: str | None,
    signal_type: str,
    current_verdict: str,
) -> dict[str, object]:
    support_slopes = _compute_recent_support_slopes(zxdq=zxdq, zxdkx=zxdkx)
    support_positions = _compute_recent_support_positions(close=close, ma25=ma25, zxdq=zxdq, zxdkx=zxdkx)
    a_result = _detect_b2_weak_safe_relaunch_a(
        close=close,
        high=high,
        low=low,
        ma25=ma25,
        zxdkx=zxdkx,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        signal_type=signal_type,
    )
    if bool(a_result.get("matched")) and float(a_result.get("redundancy_pct") or 999.0) <= 5.0:
        if (
            str(a_result.get("quality") or "") == "clean"
            and signal == "B2"
            and signal_type == "rebound"
            and macd_phase < 4.0
            and not (
                float(support_slopes.get("zxdq_5d") or 0.0) <= -1.0
                and volume_behavior >= 3.0
                and macd_phase >= 3.5
            )
        ):
            return {"verdict": "PASS", "watch_tier": None}
        watch_tier = "WATCH-A"
        if signal_type == "trend_start":
            watch_tier = "WATCH-B"
        elif (
            signal in {"B3", "B3+"}
            and signal_type == "rebound"
        ):
            watch_tier = "WATCH-B"
        elif (
            signal_type == "rebound"
            and (
                (
                    float(support_slopes.get("zxdq_5d") or 0.0) <= -1.5
                    and float(support_positions.get("close_vs_ma25") or 0.0) <= 0.0
                    and float(support_positions.get("close_vs_zxdq") or 0.0) <= 0.0
                )
                or (
                    macd_phase >= 4.2
                    and float(support_positions.get("close_vs_zxdkx") or 0.0) >= 8.0
                )
            )
        ):
            watch_tier = "WATCH-B"
        return {"verdict": "WATCH", "watch_tier": watch_tier}

    b_result = _detect_b2_weak_safe_relaunch_b(
        close=close,
        high=high,
        low=low,
        volume=volume,
        ma25=ma25,
        zxdq=zxdq,
        zxdkx=zxdkx,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
        signal=signal,
        signal_type=signal_type,
    )
    if bool(b_result.get("matched")) and float(b_result.get("redundancy_pct") or 999.0) <= 5.0:
        if current_verdict == "FAIL":
            return {"verdict": "WATCH", "watch_tier": "WATCH-B"}
        if str(b_result.get("quality") or "") == "clean":
            return {"verdict": "WATCH", "watch_tier": "WATCH-A"}
        return {"verdict": "WATCH", "watch_tier": "WATCH-B"}

    return {"verdict": current_verdict, "watch_tier": None}


def _compute_recent_support_slopes(*, zxdq: pd.Series, zxdkx: pd.Series) -> dict[str, float | None]:
    return {
        "zxdq_5d": _tail_slope(zxdq, periods=5) * 100.0 if len(zxdq.dropna()) > 5 else None,
        "zxdkx_5d": _tail_slope(zxdkx, periods=5) * 100.0 if len(zxdkx.dropna()) > 5 else None,
    }


def _compute_recent_support_positions(
    *,
    close: pd.Series,
    ma25: pd.Series,
    zxdq: pd.Series,
    zxdkx: pd.Series,
) -> dict[str, float | None]:
    latest_close = float(close.iloc[-1]) if len(close) else 0.0
    latest_ma25 = float(ma25.iloc[-1]) if len(ma25) and pd.notna(ma25.iloc[-1]) else None
    latest_zxdq = float(zxdq.iloc[-1]) if len(zxdq) and pd.notna(zxdq.iloc[-1]) else None
    latest_zxdkx = float(zxdkx.iloc[-1]) if len(zxdkx) and pd.notna(zxdkx.iloc[-1]) else None

    def pct(numerator: float, denominator: float | None) -> float | None:
        if denominator is None or denominator == 0.0:
            return None
        return (numerator / denominator - 1.0) * 100.0

    return {
        "close_vs_ma25": pct(latest_close, latest_ma25),
        "close_vs_zxdq": pct(latest_close, latest_zxdq),
        "close_vs_zxdkx": pct(latest_close, latest_zxdkx),
    }


def _compute_abnormal_gap_pct(
    *,
    open_: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> float | None:
    if len(close) < 2:
        return None

    recent_volume = volume.tail(90).dropna()
    if recent_volume.empty:
        return None

    event_idx = int(recent_volume.idxmax())
    event_open = float(open_.loc[event_idx])
    event_close = float(close.loc[event_idx])
    abnormal_price = event_close if event_close >= event_open else event_open
    if abnormal_price <= 0.0:
        return None

    latest_close = float(close.iloc[-1])
    return (latest_close / abnormal_price - 1.0) * 100.0


def _detect_b2_weak_safe_relaunch_a(
    *,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    ma25: pd.Series,
    zxdkx: pd.Series,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    signal_type: str,
) -> dict[str, object]:
    if len(close) < 20:
        return {"matched": False, "quality": None, "redundancy_pct": None}

    latest_close = float(close.iloc[-1])
    latest_ma25 = float(ma25.iloc[-1]) if pd.notna(ma25.iloc[-1]) else float("nan")
    latest_zxdkx = float(zxdkx.iloc[-1]) if pd.notna(zxdkx.iloc[-1]) else float("nan")
    if not pd.notna(latest_zxdkx) or latest_zxdkx <= 0.0:
        return {"matched": False, "quality": None, "redundancy_pct": None}

    pullback_low = float(low.tail(15).min())
    reclaim_ok = latest_close >= latest_zxdkx and pullback_low <= latest_zxdkx * 1.02
    redundancy_pct = (latest_close / max(latest_zxdkx, latest_ma25) - 1.0) * 100.0 if pd.notna(latest_ma25) and latest_ma25 > 0 else (latest_close / latest_zxdkx - 1.0) * 100.0
    if not reclaim_ok:
        return {"matched": False, "quality": None, "redundancy_pct": round(redundancy_pct, 2)}

    matched = (
        signal_type in {"rebound", "trend_start"}
        and trend_structure >= 3.0
        and price_position >= 3.0
        and volume_behavior >= 2.0
        and previous_abnormal_move >= 5.0
        and pullback_low >= latest_zxdkx * 0.95
    )
    if not matched:
        return {"matched": False, "quality": None, "redundancy_pct": round(redundancy_pct, 2)}

    quality = "clean" if price_position >= 4.0 and volume_behavior in {2.0, 3.0} and macd_phase < 4.5 else "borderline"
    return {"matched": True, "quality": quality, "redundancy_pct": round(redundancy_pct, 2)}


def _detect_b2_weak_safe_relaunch_b(
    *,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    ma25: pd.Series,
    zxdq: pd.Series,
    zxdkx: pd.Series,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    signal: str | None,
    signal_type: str,
) -> dict[str, object]:
    if len(close) < 25:
        return {"matched": False, "quality": None, "redundancy_pct": None}

    latest_close = float(close.iloc[-1])
    latest_zxdq = float(zxdq.iloc[-1]) if pd.notna(zxdq.iloc[-1]) else float("nan")
    latest_zxdkx = float(zxdkx.iloc[-1]) if pd.notna(zxdkx.iloc[-1]) else float("nan")
    if not pd.notna(latest_zxdq) or latest_zxdq <= 0.0 or not pd.notna(latest_zxdkx):
        return {"matched": False, "quality": None, "redundancy_pct": None}

    tail_close = close.tail(20).astype(float).reset_index(drop=True)
    tail_low = low.tail(20).astype(float).reset_index(drop=True)
    tail_zxdq = zxdq.tail(20).astype(float).reset_index(drop=True)
    consolidation_low = float(tail_low.min())
    consolidation_high = float(high.tail(20).max())
    consolidation_span_pct = (consolidation_high / consolidation_low - 1.0) * 100.0 if consolidation_low > 0 else 999.0
    reclaim_ok = latest_close >= latest_zxdq and consolidation_low <= latest_zxdq * 1.05
    consolidation_ok = consolidation_span_pct <= 38.0 and float(tail_close.iloc[-1]) >= float(tail_close.iloc[0]) * 0.95
    anchor_price = _find_recent_support_reclaim_anchor(
        tail_close=tail_close,
        tail_low=tail_low,
        tail_support=tail_zxdq,
    )
    redundancy_pct = (
        (latest_close / anchor_price - 1.0) * 100.0
        if anchor_price is not None and anchor_price > 0.0
        else (latest_close / latest_zxdq - 1.0) * 100.0
    )
    if not reclaim_ok or not consolidation_ok:
        return {"matched": False, "quality": None, "redundancy_pct": round(redundancy_pct, 2)}

    matched = (
        signal_type == "trend_start"
        and trend_structure >= 4.0
        and price_position >= 4.0
        and volume_behavior >= 3.0
        and previous_abnormal_move >= 3.0
        and latest_close >= latest_zxdkx
    )
    if not matched:
        return {"matched": False, "quality": None, "redundancy_pct": round(redundancy_pct, 2)}

    quality = "clean" if signal == "B2" and macd_phase >= 4.2 else "normal"
    return {"matched": True, "quality": quality, "redundancy_pct": round(redundancy_pct, 2)}


def _find_recent_support_reclaim_anchor(
    *,
    tail_close: pd.Series,
    tail_low: pd.Series,
    tail_support: pd.Series,
) -> float | None:
    if len(tail_close) < 2:
        return None

    for idx in range(len(tail_close) - 1, 0, -1):
        current_close = float(tail_close.iloc[idx])
        current_support = float(tail_support.iloc[idx])
        previous_close = float(tail_close.iloc[idx - 1])
        previous_support = float(tail_support.iloc[idx - 1])
        current_low = float(tail_low.iloc[idx])
        previous_low = float(tail_low.iloc[idx - 1])

        touched_support = previous_low <= previous_support * 1.02 or current_low <= current_support * 1.02
        reclaimed_support = current_close >= current_support and previous_close < previous_support * 1.01
        if touched_support and reclaimed_support:
            return current_close

    return None


def _score_b2_neutral_bundle(
    *,
    close: pd.Series,
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    ma25: pd.Series,
    zxdq: pd.Series,
    zxdkx: pd.Series,
    weekly_trend: Any,
    daily_trend: Any,
    signal: str | None,
    profile: MethodEnvironmentProfile,
) -> dict[str, object]:
    trend_structure = _score_b2_trend_structure(
        close=close,
        low=low,
        ma25=ma25,
        zxdkx=zxdkx,
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
        profile=profile,
    )
    price_position = _score_b2_price_position(
        close=close,
        high=high,
        low=low,
        ma25=ma25,
        zxdq=zxdq,
        profile=profile,
    )
    if price_position == 3.0 and float(close.iloc[-1]) >= float(ma25.iloc[-1]):
        price_position = 4.0
    if price_position >= 5.0:
        price_position = 4.0
    volume_behavior = _score_b2_volume_behavior(close=close, volume=volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(
        open_=open_,
        close=close,
        low=low,
        volume=volume,
        profile=profile,
    )
    macd_phase = _score_b2_macd_phase(
        pd.DataFrame({"trade_date": range(len(close)), "close": close}),
        signal=signal,
        profile=profile,
    )
    scores = {
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
    }
    base_total_score = compute_b2_weighted_total_for_profile(scores, profile=profile, signal=signal)
    daily_state_hint = _resolve_b2_daily_state_hint(weekly_trend=weekly_trend, daily_trend=daily_trend)
    overheat_penalty = _compute_b2_overheat_penalty(
        close=close,
        high=high,
        low=low,
        daily_state_hint=daily_state_hint,
        signal=signal,
        price_position=price_position,
        profile=profile,
    )
    total_score = round(max(1.0, float(base_total_score) - overheat_penalty), 2)
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
        profile=profile,
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
    return {
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
        "total_score": total_score,
        "signal_type": signal_type,
        "verdict": verdict,
        "elastic_watch": elastic_watch,
        "elastic_watch_reason": elastic_watch_reason,
        "watch_score": watch_score,
        "watch_tier": watch_tier,
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
    zxdq_5d_slope_pct: float | None = None,
    profile: MethodEnvironmentProfile | None = None,
    strong_negative_macd_guard: bool = True,
) -> str:
    strong_negative_macd_guard_required = bool(
        profile is not None
        and profile.state == "strong"
        and price_position >= 4.0
        and trend_structure == 4.0
        and volume_behavior >= 5.0
    )

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

    is_weak_profile = profile is not None and profile.state == "weak"

    strong_macd_setup = (
        macd_phase >= 4.5
        and previous_abnormal_move >= 5.0
        and trend_structure >= 3.0
        and price_position >= 2.0
        and volume_behavior >= 2.0
        and total_score >= 3.6
        and (
            profile is None
            or profile.state == "strong"
        )
    )
    if strong_macd_setup:
        if strong_negative_macd_guard_required and not strong_negative_macd_guard:
            return "WATCH"
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
        and total_score >= (
            float(profile.pass_threshold) if profile is not None else 4.0
        )
        and not overheat_extension
        and not is_weak_profile
        and (
            macd_phase >= 4.2
            or (
                macd_phase >= 3.5
                and price_position >= 5.0
                and (
                    profile is None
                    or profile.state == "strong"
                )
                and total_score >= (float(profile.pass_threshold) if profile is not None else 4.2)
            )
        )
    )
    if (
        profile is not None
        and profile.state == "neutral"
        and signal_type == "trend_start"
        and price_position >= 4.0
        and macd_phase >= 4.2
    ):
        strong_trend_start_mid_macd_setup = False
    if strong_trend_start_mid_macd_setup:
        if strong_negative_macd_guard_required and not strong_negative_macd_guard:
            return "WATCH"
        return "PASS"

    if (
        profile is not None
        and profile.state == "neutral"
        and signal_type == "trend_start"
        and trend_structure >= 3.0
        and price_position == 4.0
        and volume_behavior >= 3.0
        and previous_abnormal_move >= 5.0
        and 3.8 <= macd_phase < 4.2
        and total_score >= 4.0
        and (zxdq_5d_slope_pct is None or zxdq_5d_slope_pct >= 0.0)
        and not overheat_extension
    ):
        return "PASS"

    if (
        profile is not None
        and profile.state == "neutral"
        and signal_type in {"rebound", "trend_start"}
        and trend_structure == 3.0
        and price_position >= 3.0
        and volume_behavior in {2.0, 3.0}
        and previous_abnormal_move >= 5.0
        and macd_phase < 4.5
        and total_score >= 3.45
        and (
            price_position >= 4.0
            or signal in {"B3", "B3+"}
        )
        and (zxdq_5d_slope_pct is None or zxdq_5d_slope_pct >= 0.0)
        and not overheat_extension
    ):
        return "PASS"

    if (
        profile is not None
        and profile.state == "neutral"
        and signal == "B3"
        and signal_type == "trend_start"
        and trend_structure == 4.0
        and price_position == 4.0
        and volume_behavior == 3.0
        and previous_abnormal_move >= 5.0
        and total_score <= 4.28
        and 4.2 <= macd_phase <= 4.42
        and not overheat_extension
    ):
        return "PASS"

    strong_b3_early_mid_macd_upgrade = (
        profile is not None
        and profile.state == "strong"
        and signal in {"B3", "B3+"}
        and signal_type in {"rebound", "trend_start"}
        and trend_structure == 4.0
        and price_position >= 4.0
        and volume_behavior >= 4.0
        and previous_abnormal_move >= 3.0
        and 3.0 <= macd_phase < 3.8
        and total_score >= 4.0
        and not overheat_extension
    )
    if strong_b3_early_mid_macd_upgrade:
        return "PASS"

    b3_upgrade_signal = signal in {"B3", "B3+"}
    b3_upgrade_setup = (
        b3_upgrade_signal
        and signal_type in {"rebound", "trend_start"}
        and trend_structure >= 4.0
        and price_position >= 5.0
        and previous_abnormal_move >= 5.0
        and total_score >= 4.15
        and not is_weak_profile
        and (
            macd_phase >= 4.2
            or (signal_type == "trend_start" and macd_phase >= 3.8)
        )
    )
    if b3_upgrade_setup:
        if strong_negative_macd_guard_required and not strong_negative_macd_guard:
            return "WATCH"
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
    profile: MethodEnvironmentProfile | None = None,
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
    mode = profile.subscore_mode.get("trend_structure", "default") if profile is not None else "default"

    if trend_window and ma_aligned and latest_zxdkx >= previous_zxdkx and near_ma25_support:
        if mode == "pullback_only":
            return 4.0
        return 5.0
    if mode == "aggressive" and trend_window and ma_aligned and latest_zxdkx >= previous_zxdkx:
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
    profile: MethodEnvironmentProfile | None = None,
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
    mode = profile.subscore_mode.get("price_position", "default") if profile is not None else "default"

    if mode == "low_risk_required":
        if 0.60 <= box_position < 0.80:
            return 4.0
        if 0.80 <= box_position < 0.92:
            return 2.0
    if mode == "breakout_tolerant":
        if 0.70 <= box_position < 0.92:
            return 5.0
        if 0.92 <= box_position < 1.00:
            return 4.0

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
    profile: MethodEnvironmentProfile | None = None,
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
    mode = profile.subscore_mode.get("previous_abnormal_move", "default") if profile is not None else "default"

    if position_pct > 10.0:
        return 3.0
    if mode == "strict":
        if position_pct > -10.0:
            return 3.0
        if position_pct > -30.0:
            return 5.0
        if position_pct > -45.0:
            return 3.0
        if position_pct > -55.0:
            return 2.0
        return 1.0
    if mode == "lenient":
        if position_pct > -15.0:
            return 5.0
        if position_pct > -35.0:
            return 3.0
        if position_pct > -55.0:
            return 2.0
        return 1.0
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
    signal: str | None,
    profile: MethodEnvironmentProfile | None = None,
) -> float:
    score = score_macd_review_context_from_history(
        frame,
        method="b2",
        signal=signal or "",
        environment_state=profile.state if profile is not None else None,
    )
    return score.score_1_to_5


def _strong_negative_macd_half_peak_guard(*, macd_hist: float, recent_peak: float) -> bool:
    if recent_peak <= 0.0:
        return True
    if macd_hist >= 0.0:
        return True
    return abs(macd_hist) < (recent_peak * 0.5)


def _resolve_strong_negative_macd_guard(frame: pd.DataFrame) -> bool:
    macd = compute_macd(frame[["close"]].astype(float))
    hist = pd.to_numeric(macd["macd_hist"], errors="coerce").dropna().reset_index(drop=True)
    if hist.empty:
        return True
    latest_hist = float(hist.iloc[-1])
    if latest_hist >= 0.0:
        return True

    negative_run: list[float] = []
    for value in reversed(hist.tolist()):
        value_f = float(value)
        if value_f < 0.0:
            negative_run.append(abs(value_f))
            continue
        break
    recent_peak = max(negative_run) if negative_run else abs(latest_hist)
    return _strong_negative_macd_half_peak_guard(macd_hist=latest_hist, recent_peak=recent_peak)


def _build_b2_comment(*, weekly_trend: Any, daily_trend: Any, verdict: str) -> str:
    combo_ok = is_constructive_macd_trend_combo(weekly_trend=weekly_trend, daily_trend=daily_trend)
    combo_text = "符合" if combo_ok else "不符合"
    weekly_text = describe_macd_trend_state("周线", weekly_trend)
    daily_text = describe_macd_trend_state("日线", daily_trend)
    return f"{weekly_text}、{daily_text}，该MACD组合{combo_text}b2，当前结论为{verdict}。"
