from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_trend, classify_weekly_macd_trend
from stock_select.analysis.left_peak import find_recent_left_peak_breakout_prepared
from stock_select.environment_profiles import MethodEnvironmentProfile
from stock_select.review_orchestrator import (
    describe_macd_trend_state,
    is_constructive_macd_trend_combo,
    map_macd_phase_score,
)
from stock_select.reviewers.b1 import (
    _compute_bbi,
    _resolve_zx_lines,
    _score_b1_price_position,
    _score_b1_trend_structure,
    _score_b1_volume_behavior,
    apply_b1_macd_divergence_penalty,
)
from stock_select.reviewers.b2 import _score_b2_previous_abnormal_move


@dataclass(frozen=True)
class LeftPeakAnchor:
    left_peak_date: str | None
    left_peak_high: float | None
    breakout_date: str | None
    first_bear_date: str | None
    first_bear_open: float | None
    pick_close: float | None
    b_div_a: float | None
    abs_ba_minus_1: float | None
    a_lt_b: bool | None


def review_left_peak_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
    profile: MethodEnvironmentProfile | None = None,
) -> dict[str, Any]:
    frame = _prepare_history(history, pick_date)
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)

    ma25 = close.rolling(window=25, min_periods=25).mean()
    zxdq, zxdkx = _resolve_zx_lines(frame)
    bbi = _compute_bbi(close)
    recent = frame.tail(20)

    weekly_trend = classify_weekly_macd_trend(frame[["trade_date", "close"]], pick_date)
    daily_trend = classify_daily_macd_trend(frame[["trade_date", "close"]], pick_date)
    anchor = _compute_left_peak_anchor(frame, pd.Timestamp(pick_date))

    trend_structure = _score_b1_trend_structure(open_=open_, close=close, ma25=ma25, zxdkx=zxdkx, bbi=bbi)
    price_position = _score_b1_price_position(
        close=close,
        high=high,
        low=low,
        ma25=ma25,
        zxdq=zxdq,
        profile=profile,
    )
    volume_behavior = _score_b1_volume_behavior(
        recent["open"].astype(float),
        recent["close"].astype(float),
        recent["vol"].astype(float) if "vol" in recent.columns else recent["volume"].astype(float),
    )
    previous_abnormal_move = _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume)
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

    state = str(profile.state if profile is not None else "neutral").lower()
    score_combo_key = _build_score_combo_key(
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
    )
    scores = _compute_left_peak_scores(
        state=state,
        anchor=anchor,
        weekly_trend=weekly_trend,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
    )
    verdict, score_layer, score_layer_score, gate_flags = _classify_left_peak_verdict(
        state=state,
        anchor=anchor,
        weekly_trend=weekly_trend,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
    )
    total_score = _compute_total_score(scores=scores, score_layer=score_layer, score_layer_score=score_layer_score)

    weekly_desc = describe_macd_trend_state("周线", weekly_trend)
    daily_desc = describe_macd_trend_state("日线", daily_trend)
    combo_ok = is_constructive_macd_trend_combo(weekly_trend=weekly_trend, daily_trend=daily_trend)
    comment = _build_comment(
        state=state,
        verdict=verdict,
        score_layer=score_layer,
        weekly_desc=weekly_desc,
        daily_desc=daily_desc,
        combo_ok=combo_ok,
        anchor=anchor,
        gate_flags=gate_flags,
        score_combo_key=score_combo_key,
    )

    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "review_type": "baseline",
        "method": "left_peak",
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
        **scores,
        "total_score": total_score,
        "signal_type": "rebound",
        "score_combo_key": score_combo_key,
        "verdict": verdict,
        "score_layer": score_layer,
        "score_layer_score": score_layer_score,
        "gate_flags": gate_flags,
        "left_peak_date": anchor.left_peak_date,
        "left_peak_high": anchor.left_peak_high,
        "left_peak_breakout_date": anchor.breakout_date,
        "left_peak_first_bear_date": anchor.first_bear_date,
        "left_peak_first_bear_open": anchor.first_bear_open,
        "left_peak_pick_close": anchor.pick_close,
        "left_peak_b_div_a": anchor.b_div_a,
        "left_peak_abs_ba_minus_1": anchor.abs_ba_minus_1,
        "left_peak_a_lt_b": anchor.a_lt_b,
        "weekly_macd_phase": weekly_trend.phase,
        "weekly_macd_wave_label": weekly_trend.wave_label,
        "weekly_macd_wave_stage": weekly_trend.wave_stage,
        "weekly_macd_is_rising_initial": weekly_trend.is_rising_initial,
        "weekly_macd_is_top_divergence": weekly_trend.is_top_divergence,
        "weekly_macd_description": weekly_desc,
        "daily_macd_phase": daily_trend.phase,
        "daily_macd_wave_label": daily_trend.wave_label,
        "daily_macd_wave_stage": daily_trend.wave_stage,
        "daily_macd_is_rising_initial": daily_trend.is_rising_initial,
        "daily_macd_is_top_divergence": daily_trend.is_top_divergence,
        "daily_macd_description": daily_desc,
        "macd_combo_constructive": combo_ok,
        "comment": comment,
    }


def _prepare_history(history: pd.DataFrame, pick_date: str) -> pd.DataFrame:
    if history.empty:
        raise ValueError("No daily history available for review.")
    frame = history.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed")
    for column in ("open", "high", "low", "close"):
        if column not in frame.columns:
            raise ValueError(f"History missing required column: {column}")
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.loc[frame["trade_date"] <= pd.Timestamp(pick_date)].dropna(subset=["trade_date", "open", "high", "low", "close"])
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"No daily history available on or before pick_date: {pick_date}")
    return frame


def _compute_left_peak_anchor(frame: pd.DataFrame, pick_date: pd.Timestamp) -> LeftPeakAnchor:
    breakout = find_recent_left_peak_breakout_prepared(frame, pick_date)
    current = frame.loc[frame["trade_date"] <= pick_date].tail(1)
    pick_close = float(current.iloc[0]["close"]) if not current.empty and pd.notna(current.iloc[0]["close"]) else None
    if not breakout.is_valid or breakout.left_peak_date is None:
        return LeftPeakAnchor(None, None, None, None, None, pick_close, None, None, None)

    left_peak_date = pd.Timestamp(breakout.left_peak_date)
    after_peak = frame.loc[(frame["trade_date"] > left_peak_date) & (frame["trade_date"] <= pick_date)].copy()
    bear = after_peak.loc[after_peak["close"].astype(float) < after_peak["open"].astype(float)]
    if bear.empty or pick_close is None:
        return LeftPeakAnchor(
            breakout.left_peak_date,
            breakout.left_peak_high,
            breakout.breakout_date,
            None,
            None,
            pick_close,
            None,
            None,
            None,
        )
    first = bear.iloc[0]
    first_open = float(first["open"])
    b_div_a = pick_close / first_open if first_open else None
    abs_ba = abs(b_div_a - 1.0) if b_div_a is not None else None
    return LeftPeakAnchor(
        breakout.left_peak_date,
        breakout.left_peak_high,
        breakout.breakout_date,
        first["trade_date"].strftime("%Y-%m-%d"),
        first_open,
        pick_close,
        None if b_div_a is None else round(b_div_a, 4),
        None if abs_ba is None else round(abs_ba, 4),
        bool(first_open < pick_close),
    )


def _compute_left_peak_scores(
    *,
    state: str,
    anchor: LeftPeakAnchor,
    weekly_trend: Any,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
) -> dict[str, float]:
    return {
        "left_peak_anchor_score": _score_anchor(anchor, state=state),
        "structure_combo_score": _score_structure_combo(
            trend_structure=trend_structure,
            price_position=price_position,
            volume_behavior=volume_behavior,
            previous_abnormal_move=previous_abnormal_move,
            macd_phase=macd_phase,
            state=state,
        ),
        "macd_context_score": _score_macd_context(weekly_trend=weekly_trend, macd_phase=macd_phase),
        "environment_score": {"neutral": 5.0, "weak": 2.8, "strong": 3.0}.get(state, 3.0),
        "risk_penalty_score": _score_risk_penalty(anchor=anchor, state=state, macd_phase=macd_phase),
    }


def _score_anchor(anchor: LeftPeakAnchor, *, state: str) -> float:
    dist = anchor.abs_ba_minus_1
    if dist is None:
        return 2.0
    if state == "strong":
        if dist <= 0.03:
            return 5.0
        if dist <= 0.05:
            return 3.5
        if dist <= 0.08:
            return 2.0
        return 1.0
    if state == "weak":
        if dist <= 0.05:
            return 5.0
        if dist <= 0.08:
            return 2.5
        if dist <= 0.12:
            return 1.5
        return 1.0
    if dist <= 0.08:
        return 5.0
    if dist <= 0.12:
        return 3.5
    return 2.0


def _score_structure_combo(
    *,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    state: str,
) -> float:
    if _is_t3p3v4a5(
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
    ):
        return 5.0 if macd_phase <= 3.8 else 3.0
    if (
        state == "weak"
        and _near(trend_structure, 2.0)
        and _near(price_position, 4.0)
        and _near(volume_behavior, 4.0)
        and _near(previous_abnormal_move, 5.0)
        and 3.8 < macd_phase <= 4.2
    ):
        return 4.5
    return 3.0


def _score_macd_context(*, weekly_trend: Any, macd_phase: float) -> float:
    if str(getattr(weekly_trend, "phase", "")) != "rising":
        return 2.5
    if str(getattr(weekly_trend, "wave_label", "")) == "一浪" and str(getattr(weekly_trend, "wave_stage", "")) == "分歧":
        return 5.0
    if macd_phase <= 3.8:
        return 4.0
    if macd_phase <= 4.2:
        return 3.0
    return 2.5


def _score_risk_penalty(*, anchor: LeftPeakAnchor, state: str, macd_phase: float) -> float:
    dist = anchor.abs_ba_minus_1
    if dist is None:
        return 2.0
    if dist > 0.12:
        return 1.0
    if state == "weak" and dist > 0.08:
        return 1.5
    if state == "strong" and dist > 0.05:
        return 2.0
    if macd_phase > 4.2:
        return 2.5
    return 4.0


def _classify_left_peak_verdict(
    *,
    state: str,
    anchor: LeftPeakAnchor,
    weekly_trend: Any,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
) -> tuple[str, str, float, list[str]]:
    flags = _gate_flags(anchor=anchor, state=state, macd_phase=macd_phase)
    weekly_rising = str(getattr(weekly_trend, "phase", "")) == "rising"
    dist = anchor.abs_ba_minus_1
    core = _is_t3p3v4a5(
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
    )
    weak_special = (
        state == "weak"
        and _near(trend_structure, 2.0)
        and _near(price_position, 4.0)
        and _near(volume_behavior, 4.0)
        and _near(previous_abnormal_move, 5.0)
        and 3.8 < macd_phase <= 4.2
    )

    if "anchor_far" in flags or "weak_anchor_far" in flags:
        return "FAIL", "FAIL-anchor", 20.0, flags
    if state == "strong" and "strong_anchor_loose" in flags:
        return "FAIL", "FAIL-anchor", 25.0, flags

    if state == "neutral" and weekly_rising and dist is not None and dist <= 0.08 and (
        core or (str(getattr(weekly_trend, "wave_label", "")) == "一浪" and str(getattr(weekly_trend, "wave_stage", "")) == "分歧")
    ):
        return "PASS", "PASS-A", 92.0, flags
    if weekly_rising and dist is not None and dist <= 0.05 and core and macd_phase <= 3.8:
        return "PASS", "PASS-A", 90.0, flags
    if weekly_rising and dist is not None and dist <= 0.05 and weak_special:
        return "PASS", "PASS-B", 84.0, flags
    if state == "strong" and weekly_rising and dist is not None and dist <= 0.03:
        return "PASS", "PASS-B", 82.0, flags
    if state == "neutral" and weekly_rising and dist is not None and dist <= 0.12:
        return "WATCH", "WATCH-A", 72.0, flags
    if weekly_rising and dist is not None and dist <= 0.08:
        return "WATCH", "WATCH-B", 58.0, flags
    return "FAIL", "FAIL-structure", 30.0, flags


def _gate_flags(*, anchor: LeftPeakAnchor, state: str, macd_phase: float) -> list[str]:
    flags: list[str] = []
    dist = anchor.abs_ba_minus_1
    if dist is None:
        flags.append("anchor_missing")
    else:
        if dist >= 0.12:
            flags.append("anchor_far")
        if state == "weak" and dist > 0.08:
            flags.append("weak_anchor_far")
        if state == "strong" and dist > 0.05:
            flags.append("strong_anchor_loose")
    if macd_phase > 4.2:
        flags.append("macd_mature")
    return flags


def _compute_total_score(*, scores: dict[str, float], score_layer: str, score_layer_score: float) -> float:
    weighted = (
        scores["left_peak_anchor_score"] * 0.30
        + scores["structure_combo_score"] * 0.25
        + scores["macd_context_score"] * 0.18
        + scores["environment_score"] * 0.12
        + scores["risk_penalty_score"] * 0.15
    )
    layer_bonus = 0.25 if score_layer == "PASS-A" else 0.12 if score_layer == "PASS-B" else 0.0
    layer_penalty = -0.35 if score_layer.startswith("FAIL") else 0.0
    return round(max(1.0, min(5.0, weighted + layer_bonus + layer_penalty + score_layer_score / 500.0)), 2)


def _build_score_combo_key(
    *,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
) -> str:
    return (
        f"T{_bucket_int(trend_structure)}|P{_bucket_int(price_position)}|V{_bucket_int(volume_behavior)}|"
        f"A{_bucket_int(previous_abnormal_move)}|M{macd_phase:.1f}".rstrip("0").rstrip(".")
    )


def _bucket_int(value: float) -> str:
    return str(int(round(float(value))))


def _is_t3p3v4a5(
    *,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
) -> bool:
    return (
        _near(trend_structure, 3.0)
        and _near(price_position, 3.0)
        and _near(volume_behavior, 4.0)
        and _near(previous_abnormal_move, 5.0)
    )


def _near(value: float, target: float) -> bool:
    return abs(float(value) - target) <= 0.05


def _build_comment(
    *,
    state: str,
    verdict: str,
    score_layer: str,
    weekly_desc: str,
    daily_desc: str,
    combo_ok: bool,
    anchor: LeftPeakAnchor,
    gate_flags: list[str],
    score_combo_key: str,
) -> str:
    anchor_text = (
        "左峰锚点缺失"
        if anchor.abs_ba_minus_1 is None
        else f"B/A={anchor.b_div_a:.4f}，距1偏离={anchor.abs_ba_minus_1:.4f}"
    )
    combo_text = "符合" if combo_ok else "不符合"
    flags_text = "、".join(gate_flags) if gate_flags else "无硬风险"
    return (
        f"left_peak专用review：环境={state}，{anchor_text}，五维组合={score_combo_key}，"
        f"{weekly_desc}、{daily_desc}，MACD组合{combo_text}建设性条件，风险={flags_text}，"
        f"分层={score_layer}，结论={verdict}。"
    )
