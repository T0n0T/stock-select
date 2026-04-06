from __future__ import annotations

from typing import Any


def build_review_payload(
    *,
    code: str,
    pick_date: str,
    chart_path: str,
    rubric_path: str,
) -> dict[str, str]:
    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "rubric_path": rubric_path,
    }


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
