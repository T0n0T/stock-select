from __future__ import annotations

import math

BASELINE_SCORE_WEIGHTS = {
    "trend_structure": 0.18,
    "price_position": 0.18,
    "volume_behavior": 0.24,
    "previous_abnormal_move": 0.20,
    "macd_phase": 0.20,
}
B2_BASELINE_SCORE_WEIGHTS = {
    "trend_structure": 0.14,
    "price_position": 0.22,
    "volume_behavior": 0.00,
    "previous_abnormal_move": 0.14,
    "macd_phase": 0.35,
    "signal": 0.15,
}
B2_SIGNAL_SCORE = {
    "B3": 5.0,
    "B3+": 5.0,
    "B2": 4.0,
}
B1_BASELINE_SCORE_WEIGHTS = {
    "trend_structure": 0.23,
    "price_position": 0.20,
    "volume_behavior": 0.22,
    "previous_abnormal_move": 0.20,
    "macd_phase": 0.15,
}
NO_MACD_SCORE_WEIGHTS = {
    "trend_structure": 0.30,
    "price_position": 0.25,
    "volume_behavior": 0.40,
    "previous_abnormal_move": 0.05,
}

B1_LLM_NO_MACD_SCORE_WEIGHTS = {
    "trend_structure": B1_BASELINE_SCORE_WEIGHTS["trend_structure"] / (1.0 - B1_BASELINE_SCORE_WEIGHTS["macd_phase"]),
    "price_position": B1_BASELINE_SCORE_WEIGHTS["price_position"] / (1.0 - B1_BASELINE_SCORE_WEIGHTS["macd_phase"]),
    "volume_behavior": B1_BASELINE_SCORE_WEIGHTS["volume_behavior"] / (1.0 - B1_BASELINE_SCORE_WEIGHTS["macd_phase"]),
    "previous_abnormal_move": B1_BASELINE_SCORE_WEIGHTS["previous_abnormal_move"] / (1.0 - B1_BASELINE_SCORE_WEIGHTS["macd_phase"]),
}


def compute_weighted_total(scores: dict[str, float]) -> float:
    return round(sum(float(scores[field]) * weight for field, weight in BASELINE_SCORE_WEIGHTS.items()), 2)


def b2_signal_score(signal: str | None) -> float:
    signal_label = str(signal or "").strip().upper()
    return B2_SIGNAL_SCORE.get(signal_label, 3.0)


def compute_b2_weighted_total(scores: dict[str, float], *, signal: str | None = None) -> float:
    total = sum(float(scores[field]) * weight for field, weight in B2_BASELINE_SCORE_WEIGHTS.items() if field != "signal")
    total += b2_signal_score(signal) * B2_BASELINE_SCORE_WEIGHTS["signal"]
    return round(total, 2)


def compute_b1_weighted_total(scores: dict[str, float]) -> float:
    return round(sum(float(scores[field]) * weight for field, weight in B1_BASELINE_SCORE_WEIGHTS.items()), 2)


def compute_b1_llm_weighted_total_without_macd(scores: dict[str, float]) -> float:
    return round(sum(float(scores[field]) * weight for field, weight in B1_LLM_NO_MACD_SCORE_WEIGHTS.items()), 2)


def compute_weighted_total_without_macd(scores: dict[str, float]) -> float:
    return round(sum(float(scores[field]) * weight for field, weight in NO_MACD_SCORE_WEIGHTS.items()), 2)


def infer_signal_type(
    *,
    latest_close: float,
    latest_open: float,
    trend_structure: float,
    volume_behavior: float,
    price_position: float,
    ignore_volume_risk: bool = False,
) -> str:
    if trend_structure <= 2.0:
        return "distribution_risk"
    if not ignore_volume_risk:
        if volume_behavior <= 1.0:
            return "distribution_risk"
        if volume_behavior <= 2.0 and trend_structure < 4.0:
            return "distribution_risk"
    if latest_close >= latest_open and trend_structure >= 4.0 and price_position >= 3.0:
        return "trend_start"
    return "rebound"


def infer_verdict(*, total_score: float, volume_behavior: float, signal_type: str, method: str = "") -> str:
    if volume_behavior <= 1.0 or signal_type == "distribution_risk":
        return "FAIL"
    is_hcr = method.strip().lower() == "hcr"
    pass_threshold = 3.5 if is_hcr else 4.0
    watch_threshold = 3.0 if is_hcr else 3.2
    if total_score >= pass_threshold:
        return "PASS"
    if total_score >= watch_threshold:
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
