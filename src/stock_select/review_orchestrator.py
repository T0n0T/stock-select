from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_select.analysis.macd_waves import DailyMacdState
from stock_select.review_protocol import (
    BASELINE_SCORE_WEIGHTS,
    build_baseline_comment,
    compute_b1_llm_weighted_total_without_macd,
    compute_b1_weighted_total,
    compute_b2_weighted_total,
    compute_weighted_total,
    compute_weighted_total_without_macd,
    infer_final_verdict,
    validate_score_field,
)

REFERENCE_PROMPT_PATH = str(
    (Path(__file__).resolve().parents[2] / ".agents" / "skills" / "stock-select" / "references" / "prompt.md")
)
REQUIRED_REASONING_FIELDS = (
    "trend_reasoning",
    "position_reasoning",
    "volume_reasoning",
    "abnormal_move_reasoning",
    "macd_reasoning",
    "signal_reasoning",
)
REQUIRED_SCORE_FIELDS = (
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "macd_phase",
)
ALLOWED_SIGNAL_TYPES = {"trend_start", "rebound", "distribution_risk"}
ALLOWED_VERDICTS = {"PASS", "WATCH", "FAIL"}


def compute_method_total_score(method: str, scores: dict[str, float], *, signal: str | None = None) -> float:
    normalized = str(method).strip().lower()
    if normalized == "b1":
        return compute_b1_weighted_total(scores)
    if normalized == "b2":
        return compute_b2_weighted_total(scores, signal=signal)
    if normalized == "hcr":
        return compute_weighted_total_without_macd(scores)
    return compute_weighted_total(scores)


def map_macd_phase_score(
    *,
    method: str,
    history_len: int,
    weekly_trend: Any | None = None,
    daily_trend: Any | None = None,
    daily_state: DailyMacdState | None = None,
    weekly_wave: Any | None = None,
    daily_recent_death_cross: bool = False,
) -> float:
    normalized = str(method).strip().lower()
    if normalized in {"b1", "b2", "dribull"} and history_len < 60:
        return 3.0
    if normalized not in {"b1", "b2", "dribull"} and history_len < 35:
        return 3.0

    if weekly_trend is not None and daily_trend is not None:
        return _map_macd_trend_phase_score(weekly_trend=weekly_trend, daily_trend=daily_trend)

    if normalized == "b1":
        if daily_recent_death_cross:
            return 2.0
        return 3.0

    if daily_state is None:
        return 3.0

    state = daily_state.state
    if state in {"hard_invalid", "deteriorating", "overextended"}:
        return 1.0
    if state == "repair_candidate":
        return 2.0
    if state in {"wave2_end_valid", "wave4_end_valid"}:
        return 4.0
    if state == "early_recross":
        return 3.0
    return 3.0


def apply_macd_verdict_gate(
    *,
    method: str,
    current_verdict: str,
    weekly_trend: Any | None = None,
    daily_trend: Any | None = None,
    daily_state: DailyMacdState | None = None,
    weekly_wave: Any | None = None,
    daily_recent_death_cross: bool = False,
) -> str:
    normalized = str(method).strip().lower()

    if weekly_trend is not None and daily_trend is not None:
        return _apply_macd_trend_verdict_gate(
            current_verdict=current_verdict,
            weekly_trend=weekly_trend,
            daily_trend=daily_trend,
        )

    weekly_label = str(getattr(weekly_wave, "label", ""))

    if normalized == "b1":
        if daily_recent_death_cross and current_verdict == "PASS":
            return "WATCH"
        return current_verdict

    if daily_state is None:
        return current_verdict

    state = daily_state.state

    if normalized == "b2":
        if state == "hard_invalid":
            return "FAIL"
        if state in {"deteriorating", "overextended"} and current_verdict == "PASS":
            return "WATCH"
        return current_verdict

    if normalized == "dribull":
        if state in {"hard_invalid", "deteriorating"}:
            return "FAIL"
        return current_verdict

    return current_verdict


def _map_macd_trend_phase_score(*, weekly_trend: Any, daily_trend: Any) -> float:
    percent_score = calculate_dual_period_macd_score(weekly_trend=weekly_trend, daily_trend=daily_trend)["total"]
    return round(1.0 + max(0.0, min(100.0, percent_score)) / 25.0, 2)


def calculate_dual_period_macd_score(*, weekly_trend: Any, daily_trend: Any) -> dict[str, Any]:
    weekly_wave = _trend_wave_number(weekly_trend)
    daily_wave = _trend_wave_number(daily_trend)
    weekly_dir = _wave_direction(weekly_wave)
    daily_dir = _wave_direction(daily_wave)
    weekly_stage = _normalized_wave_stage(weekly_trend)
    daily_stage = _normalized_wave_stage(daily_trend)

    weekly_wave_score = _weekly_wave_score(weekly_trend, weekly_wave)
    weekly_stage_score = _stage_score(direction=weekly_dir, stage=weekly_stage, weekly=True)
    weekly_zero_score = _weekly_zero_axis_score(weekly_trend)
    weekly_total = weekly_wave_score + weekly_stage_score + weekly_zero_score

    daily_wave_score = _daily_wave_score(daily_trend, daily_wave)
    daily_stage_score = _stage_score(direction=daily_dir, stage=daily_stage, weekly=False)
    daily_aux_score = 6.0
    daily_total = daily_wave_score + daily_stage_score + daily_aux_score

    direction_resonance = _direction_resonance(weekly_dir=weekly_dir, daily_dir=daily_dir)
    phase_resonance = _phase_resonance(
        weekly_trend=weekly_trend,
        daily_trend=daily_trend,
        weekly_dir=weekly_dir,
        daily_dir=daily_dir,
        weekly_stage=weekly_stage,
        daily_stage=daily_stage,
    )
    zero_resonance = _zero_resonance(weekly_trend=weekly_trend, daily_trend=daily_trend)
    resonance_total = direction_resonance + phase_resonance + zero_resonance
    total = weekly_total + daily_total + resonance_total
    setup_bonus = 0.0
    if weekly_dir == "上升" and weekly_stage == "背离" and daily_dir == "下跌" and daily_stage in {"强势", "强势转分歧"}:
        if _trend_metric(weekly_trend, "hist_change_rate") >= 1.0 and _trend_metric(daily_trend, "hist_change_rate") >= 0.5:
            setup_bonus = 14.0
        else:
            setup_bonus = 6.0
        total += setup_bonus
    total = round(min(100.0, total), 2)

    return {
        "total": total,
        "grade": _macd_percent_grade(total),
        "weekly_total": weekly_total,
        "daily_total": daily_total,
        "resonance_total": resonance_total,
        "details": {
            "weekly_wave": weekly_wave_score,
            "weekly_stage": weekly_stage_score,
            "weekly_zero": weekly_zero_score,
            "daily_wave": daily_wave_score,
            "daily_stage": daily_stage_score,
            "daily_aux": daily_aux_score,
            "resonance_direction": direction_resonance,
            "resonance_stage": phase_resonance,
            "resonance_zero": zero_resonance,
            "setup_bonus": setup_bonus,
        },
    }


def _trend_wave_number(trend: Any) -> int:
    phase = str(getattr(trend, "phase", ""))
    if phase == "ended":
        return -1
    if phase in {"idle", "invalid"}:
        return 0
    idx = int(getattr(trend, "phase_index", 0) or 0)
    if idx <= 0:
        if phase == "rising":
            return 1
        if phase == "falling":
            return 2
        return 0
    return idx


def _wave_direction(wave: int) -> str:
    if wave in {1, 3, 5, 7} or wave > 7 and wave % 2 == 1:
        return "上升"
    if wave in {2, 4, 6} or wave > 7 and wave % 2 == 0:
        return "下跌"
    return "初始"


def _normalized_wave_stage(trend: Any) -> str:
    stage = str(getattr(trend, "wave_stage", "") or "")
    warnings = tuple(getattr(trend, "transition_warnings", ()) or ())
    if stage == "强势" and any("强势→分歧" in item for item in warnings):
        return "强势转分歧"
    if stage == "分歧" and bool(getattr(trend, "is_top_divergence", False)):
        return "分歧转背离"
    return stage or "初始"


def _weekly_wave_score(trend: Any, wave: int) -> float:
    phase = str(getattr(trend, "phase", ""))
    if phase == "ended" or wave < 0:
        return 0.0
    if wave == 0:
        return 2.0
    if wave in {1, 3}:
        return 20.0
    if wave == 5:
        return 15.0
    if wave >= 7:
        return 8.0
    if wave == 2:
        return 16.0
    if wave == 4:
        return 14.0
    if wave == 6:
        return 6.0
    return 0.0


def _daily_wave_score(trend: Any, wave: int) -> float:
    if str(getattr(trend, "phase", "")) == "ended" or wave <= 0:
        return 0.0
    if wave in {1, 3}:
        return 12.0
    if wave == 5:
        return 9.0
    if wave >= 7:
        return 5.0
    if wave == 2:
        return 8.0
    if wave == 4:
        return 7.0
    if wave == 6:
        return 4.0
    return 0.0


def _stage_score(*, direction: str, stage: str, weekly: bool) -> float:
    if weekly:
        scores = {
            ("上升", "强势"): 20.0,
            ("上升", "强势转分歧"): 15.0,
            ("上升", "分歧"): 12.0,
            ("上升", "分歧转背离"): 8.0,
            ("上升", "背离"): 4.0,
            ("下跌", "背离"): 18.0,
            ("下跌", "分歧转背离"): 14.0,
            ("下跌", "分歧"): 10.0,
            ("下跌", "强势转分歧"): 6.0,
            ("下跌", "强势"): 2.0,
        }
    else:
        scores = {
            ("上升", "强势"): 12.0,
            ("上升", "强势转分歧"): 9.0,
            ("上升", "分歧"): 7.0,
            ("上升", "分歧转背离"): 5.0,
            ("上升", "背离"): 3.0,
            ("下跌", "背离"): 11.0,
            ("下跌", "分歧转背离"): 9.0,
            ("下跌", "分歧"): 6.0,
            ("下跌", "强势转分歧"): 6.0,
            ("下跌", "强势"): 2.0,
        }
    return scores.get((direction, stage), 0.0)


def _trend_metric(trend: Any, key: str) -> float:
    metrics = getattr(trend, "metrics", {}) or {}
    try:
        return float(metrics.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _weekly_zero_axis_score(trend: Any) -> float:
    dif = _trend_metric(trend, "dif")
    dea = _trend_metric(trend, "dea")
    spread = dif - dea
    previous_spread = _trend_metric(trend, "previous_spread")
    if dif > 0 and dea > 0 and dif > dea:
        if spread > previous_spread:
            return 10.0
        return 8.0
    if dif > 0 and dea > 0:
        return 5.0
    if dif > 0 or dea > 0:
        return 4.0 if dif > dea else 3.0
    return 3.0 if dif > dea else 0.0


def _direction_resonance(*, weekly_dir: str, daily_dir: str) -> float:
    if weekly_dir == "上升" and daily_dir == "上升":
        return 8.0
    if weekly_dir == "上升" and daily_dir == "下跌":
        return 6.0
    if weekly_dir == "下跌" and daily_dir == "上升":
        return 4.0
    return 0.0


def _phase_resonance(
    *,
    weekly_trend: Any,
    daily_trend: Any,
    weekly_dir: str,
    daily_dir: str,
    weekly_stage: str,
    daily_stage: str,
) -> float:
    if weekly_stage == "强势" and daily_stage == "背离" and _trend_metric(weekly_trend, "hist_change_rate") >= 1.0:
        return -2.0
    if weekly_dir == "下跌" and weekly_stage == "背离" and daily_dir == "上升" and daily_stage == "背离":
        return 5.0
    scores = {
        ("强势", "强势"): 7.0,
        ("强势", "分歧"): 6.0,
        ("强势", "强势转分歧"): 6.0,
        ("分歧", "强势"): 6.0,
        ("强势", "背离"): 1.0,
        ("强势", "分歧转背离"): 4.0,
        ("分歧", "分歧"): 4.0,
        ("分歧", "背离"): 2.0,
        ("分歧", "分歧转背离"): 2.0,
        ("背离", "强势"): 8.0,
        ("背离", "强势转分歧"): 8.0,
        ("背离", "分歧"): 6.0,
        ("背离", "分歧转背离"): 4.0,
        ("背离", "背离"): 1.0,
    }
    return scores.get((weekly_stage, daily_stage), 3.0)


def _zero_resonance(*, weekly_trend: Any, daily_trend: Any) -> float:
    week_dif = _trend_metric(weekly_trend, "dif")
    week_dea = _trend_metric(weekly_trend, "dea")
    day_dif = _trend_metric(daily_trend, "dif")
    day_dea = _trend_metric(daily_trend, "dea")
    if week_dif > 0 and week_dea > 0:
        if day_dif > 0 and day_dea > 0:
            return 5.0
        if abs(day_dif) < max(abs(_trend_metric(daily_trend, "dif_max_20")), abs(day_dif), 1e-12) * 0.2:
            return 4.0
        return 3.0
    if week_dif > 0 or week_dea > 0:
        return 2.0 if day_dif > 0 else 1.0
    return 0.0


def _macd_percent_grade(total: float) -> str:
    if total >= 85:
        return "S"
    if total >= 70:
        return "A"
    if total >= 55:
        return "B"
    if total >= 40:
        return "C"
    return "D"


def _apply_macd_trend_verdict_gate(*, current_verdict: str, weekly_trend: Any, daily_trend: Any) -> str:
    weekly_phase = str(getattr(weekly_trend, "phase", ""))
    daily_phase = str(getattr(daily_trend, "phase", ""))
    has_divergence = bool(getattr(weekly_trend, "is_top_divergence", False)) or bool(
        getattr(daily_trend, "is_top_divergence", False)
    )

    if weekly_phase in {"invalid", "ended"} or daily_phase in {"invalid", "ended"}:
        return "FAIL"
    if weekly_phase == "falling" and daily_phase == "falling":
        return "FAIL"
    if has_divergence and current_verdict == "PASS":
        return "WATCH"
    return current_verdict


def describe_macd_trend_state(label: str, trend: Any) -> str:
    phase = str(getattr(trend, "phase", "invalid"))
    phase_text = {
        "rising": "上升浪",
        "falling": "下跌浪",
        "idle": "等待启动",
        "ended": "波段结束",
        "invalid": "状态无效",
    }.get(phase, "状态无效")
    extras: list[str] = []
    if bool(getattr(trend, "is_rising_initial", False)):
        extras.append("上升初期")
    if bool(getattr(trend, "is_top_divergence", False)):
        extras.append("顶背离风险")
    suffix = f"（{'、'.join(extras)}）" if extras else ""
    return f"{label}MACD{phase_text}{suffix}"


def is_constructive_macd_trend_combo(*, weekly_trend: Any, daily_trend: Any) -> bool:
    weekly_phase = str(getattr(weekly_trend, "phase", ""))
    daily_phase = str(getattr(daily_trend, "phase", ""))
    if weekly_phase in {"invalid", "ended"} or daily_phase in {"invalid", "ended"}:
        return False
    if bool(getattr(weekly_trend, "is_top_divergence", False)) or bool(getattr(daily_trend, "is_top_divergence", False)):
        return False
    if weekly_phase == "rising" and daily_phase == "rising" and bool(getattr(daily_trend, "is_rising_initial", False)):
        return True
    return weekly_phase == "rising" and daily_phase == "falling"


def build_review_payload(
    *,
    code: str,
    pick_date: str,
    chart_path: str,
    rubric_path: str,
    prompt_path: str = REFERENCE_PROMPT_PATH,
    extra_context: dict[str, str] | None = None,
) -> dict[str, str]:
    payload = {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "rubric_path": rubric_path,
        "prompt_path": prompt_path,
        "input_mode": "image",
        "dispatch": "subagent",
    }
    if extra_context:
        payload.update(extra_context)
    return payload


def build_review_result(
    *,
    code: str,
    pick_date: str,
    chart_path: str,
    baseline_review: dict[str, Any],
    llm_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary = llm_review if llm_review is not None else baseline_review
    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "review_mode": "llm_primary" if llm_review is not None else "baseline_local",
        "llm_review": llm_review,
        "baseline_review": baseline_review,
        "total_score": float(primary.get("total_score", 0.0)),
        "signal_type": str(primary.get("signal_type", "")),
        "verdict": str(primary.get("verdict", "")),
        "comment": str(primary.get("comment", "")),
    }


def merge_review_result(
    *,
    method: str = "default",
    existing_review: dict[str, Any],
    llm_review: dict[str, Any],
    baseline_weight: float = 0.4,
    llm_weight: float = 0.6,
) -> dict[str, Any]:
    baseline_review = existing_review["baseline_review"]
    normalized = str(method).strip().lower()
    if normalized in {"b1", "b2"} and baseline_weight == 0.4 and llm_weight == 0.6:
        baseline_weight = 0.6
        llm_weight = 0.4
    baseline_score = float(baseline_review.get("total_score", 0.0))
    llm_score = float(llm_review.get("total_score", 0.0))
    final_score = round(baseline_score * baseline_weight + llm_score * llm_weight, 2)
    verdict = infer_final_verdict(final_score)

    return {
        **existing_review,
        "review_mode": "merged",
        "llm_review": llm_review,
        "final_score": final_score,
        "total_score": final_score,
        "signal_type": str(llm_review.get("signal_type", "")),
        "verdict": verdict,
        "comment": str(llm_review.get("comment", "")),
    }


def normalize_llm_review(payload: dict[str, Any]) -> dict[str, Any]:
    for field in REQUIRED_REASONING_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing or empty required field: {field}")

    scores = payload.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("Missing or invalid required field: scores")

    normalized_scores: dict[str, float] = {}
    for field in REQUIRED_SCORE_FIELDS:
        if field not in scores:
            raise ValueError(f"Missing score field: {field}")
        normalized_scores[field] = validate_score_field(field, scores[field])

    signal_type = str(payload.get("signal_type", ""))
    if signal_type not in ALLOWED_SIGNAL_TYPES:
        raise ValueError(f"Invalid signal_type: {signal_type}")

    verdict = str(payload.get("verdict", ""))
    if verdict not in ALLOWED_VERDICTS:
        raise ValueError(f"Invalid verdict: {verdict}")

    comment = payload.get("comment")
    if not isinstance(comment, str) or not comment.strip():
        raise ValueError("Missing or empty required field: comment")

    method = str(payload.get("method", "default"))
    total_score = (
        compute_b1_llm_weighted_total_without_macd(normalized_scores)
        if method.strip().lower() == "b1"
        else compute_method_total_score(method, normalized_scores)
    )

    return {
        **{field: str(payload[field]).strip() for field in REQUIRED_REASONING_FIELDS},
        "scores": normalized_scores,
        **normalized_scores,
        "total_score": total_score,
        "signal_type": signal_type,
        "verdict": verdict,
        "comment": comment.strip(),
    }


def review_symbol_history(
    *,
    method: str = "default",
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
) -> dict[str, Any]:
    from stock_select.reviewers.default import review_symbol_history as default_review_symbol_history

    return default_review_symbol_history(
        method=method,
        code=code,
        pick_date=pick_date,
        history=history,
        chart_path=chart_path,
    )


def summarize_reviews(
    pick_date: str,
    method: str,
    reviews: list[dict[str, Any]],
    *,
    min_score: float,
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_method = method.strip().lower()
    sort_key = lambda item: float(item.get("total_score", 0.0))
    recommendations = sorted(
        [
            review
            for review in reviews
            if review.get("verdict") == "PASS" and float(review.get("total_score", 0.0)) >= min_score
        ],
        key=sort_key,
        reverse=True,
    )
    excluded = sorted(
        [review for review in reviews if review not in recommendations],
        key=sort_key,
        reverse=True,
    )
    return {
        "pick_date": pick_date,
        "method": method,
        "reviewed_count": len(reviews),
        "recommendations": recommendations,
        "excluded": excluded,
        "failures": failures,
    }

