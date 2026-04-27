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


def compute_method_total_score(method: str, scores: dict[str, float]) -> float:
    normalized = str(method).strip().lower()
    if normalized == "b1":
        return compute_b1_weighted_total(scores)
    if normalized == "hcr":
        return compute_weighted_total_without_macd(scores)
    return compute_weighted_total(scores)


def map_macd_phase_score(
    *,
    method: str,
    history_len: int,
    daily_state: DailyMacdState | None = None,
    weekly_wave: Any | None = None,
    daily_recent_death_cross: bool = False,
) -> float:
    normalized = str(method).strip().lower()
    if normalized in {"b1", "b2", "dribull"} and history_len < 60:
        return 3.0
    if normalized not in {"b1", "b2", "dribull"} and history_len < 35:
        return 3.0

    weekly_label = str(getattr(weekly_wave, "label", ""))

    if normalized == "b1":
        if weekly_wave is not None and weekly_label not in {"wave1", "wave3"}:
            return 1.0
        if daily_recent_death_cross:
            return 2.0
        return 4.0

    if daily_state is None:
        return 3.0

    state = daily_state.state
    third_wave_gain = float(daily_state.metrics.get("third_wave_gain", 0.0))

    if normalized == "b2":
        if state in {"hard_invalid", "deteriorating"}:
            return 1.0
        if weekly_label in {"wave1", "wave3"} and state in {"wave2_end_valid", "wave4_end_valid"}:
            return 5.0
        if weekly_label in {"wave1", "wave3"} and state in {"repair_candidate", "early_recross"}:
            return 4.0
        if weekly_label == "wave2" and state in {"wave2_end_valid", "wave4_end_valid", "repair_candidate"}:
            return 3.0
        if state == "overextended":
            return 2.0
        if state == "repair_candidate":
            return 2.0
        return 1.0

    if normalized == "dribull":
        if state in {"hard_invalid", "deteriorating"}:
            return 1.0
        if weekly_label == "wave3" and state == "wave4_end_valid":
            return 5.0
        if weekly_label == "wave1" and state == "wave2_end_valid":
            return 5.0
        if weekly_label == "wave3" and state == "repair_candidate":
            return 4.0
        if weekly_label in {"wave1", "wave3"} and state in {"wave2_end_valid", "wave4_end_valid"}:
            return 4.0
        if weekly_label in {"wave1", "wave3"} and state == "early_recross":
            return 3.0
        if weekly_label == "wave2" and state == "wave4_end_valid":
            return 3.0
        if state in {"repair_candidate", "overextended"}:
            return 2.0
        return 1.0

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
    daily_state: DailyMacdState | None = None,
    weekly_wave: Any | None = None,
    daily_recent_death_cross: bool = False,
) -> str:
    normalized = str(method).strip().lower()
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
        if weekly_label not in {"wave1", "wave3"} and current_verdict == "PASS":
            return "WATCH"
        return current_verdict

    return current_verdict


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
    if normalized == "b1" and baseline_weight == 0.4 and llm_weight == 0.6:
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
    recommendations = sorted(
        [
            review
            for review in reviews
            if review.get("verdict") == "PASS" and float(review.get("total_score", 0.0)) >= min_score
        ],
        key=lambda item: float(item.get("total_score", 0.0)),
        reverse=True,
    )
    excluded = sorted(
        [review for review in reviews if review not in recommendations],
        key=lambda item: float(item.get("total_score", 0.0)),
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
