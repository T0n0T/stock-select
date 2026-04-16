from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_select.review_protocol import (
    BASELINE_SCORE_WEIGHTS,
    build_baseline_comment,
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
    if normalized in {"b1", "hcr"}:
        return compute_weighted_total_without_macd(scores)
    return compute_weighted_total(scores)


def build_review_payload(
    *,
    code: str,
    pick_date: str,
    chart_path: str,
    rubric_path: str,
    prompt_path: str = REFERENCE_PROMPT_PATH,
) -> dict[str, str]:
    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "rubric_path": rubric_path,
        "prompt_path": prompt_path,
        "input_mode": "image",
        "dispatch": "subagent",
    }


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
    baseline_score = float(baseline_review.get("total_score", 0.0))
    llm_score = float(llm_review.get("total_score", 0.0))
    final_score = round(baseline_score * baseline_weight + llm_score * llm_weight, 2)
    if str(llm_review.get("signal_type", "")) == "distribution_risk" or str(llm_review.get("verdict", "")) == "FAIL":
        verdict = "FAIL"
    else:
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

    total_score = compute_method_total_score(str(payload.get("method", "default")), normalized_scores)

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
