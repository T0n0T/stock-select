from __future__ import annotations

import math

BASELINE_SCORE_WEIGHTS = {
    "trend_structure": 0.18,
    "price_position": 0.18,
    "volume_behavior": 0.24,
    "previous_abnormal_move": 0.20,
    "macd_phase": 0.20,
}


def compute_weighted_total(scores: dict[str, float]) -> float:
    return round(sum(float(scores[field]) * weight for field, weight in BASELINE_SCORE_WEIGHTS.items()), 2)


def infer_signal_type(
    *,
    latest_close: float,
    latest_open: float,
    trend_structure: float,
    volume_behavior: float,
    price_position: float,
) -> str:
    if trend_structure <= 2.0 or volume_behavior <= 2.0:
        return "distribution_risk"
    if latest_close >= latest_open and trend_structure >= 4.0 and price_position >= 3.0:
        return "trend_start"
    return "rebound"


def infer_verdict(*, total_score: float, volume_behavior: float, signal_type: str) -> str:
    if volume_behavior <= 1.0 or signal_type == "distribution_risk":
        return "FAIL"
    if total_score >= 4.0:
        return "PASS"
    if total_score >= 3.2:
        return "WATCH"
    return "FAIL"


def infer_final_verdict(total_score: float) -> str:
    if total_score >= 4.0:
        return "PASS"
    if total_score >= 3.2:
        return "WATCH"
    return "FAIL"


def build_baseline_comment(*, signal_type: str, verdict: str) -> str:
    if signal_type == "distribution_risk":
        return "趋势走弱且量价失衡，前期异动后的承接不足，当前更偏出货风险。"
    if verdict == "PASS":
        return "趋势结构顺畅，量价配合正常，前期异动仍有承接，当前具备继续走强条件。"
    return "结构有修复迹象，但量价与位置优势一般，暂时更适合继续观察。"


def validate_score_field(field: str, value: object) -> float:
    score = float(value)
    if not math.isfinite(score) or score < 0.0 or score > 5.0:
        raise ValueError(f"Invalid score field: {field}")
    return score
