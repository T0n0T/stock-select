from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

REFERENCE_PROMPT_PATH = str(
    (Path(__file__).resolve().parents[2] / ".agents" / "skills" / "stock-select" / "references" / "prompt.md")
)
REQUIRED_REASONING_FIELDS = (
    "trend_reasoning",
    "position_reasoning",
    "volume_reasoning",
    "abnormal_move_reasoning",
    "signal_reasoning",
)
REQUIRED_SCORE_FIELDS = (
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
)
ALLOWED_SIGNAL_TYPES = {"trend_start", "rebound", "distribution_risk"}
ALLOWED_VERDICTS = {"PASS", "WATCH", "FAIL"}


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
        "prompt_path": REFERENCE_PROMPT_PATH,
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
    existing_review: dict[str, Any],
    llm_review: dict[str, Any],
    baseline_weight: float = 0.4,
    llm_weight: float = 0.6,
) -> dict[str, Any]:
    baseline_review = existing_review["baseline_review"]
    baseline_score = float(baseline_review.get("total_score", 0.0))
    llm_score = float(llm_review.get("total_score", 0.0))
    final_score = round(baseline_score * baseline_weight + llm_score * llm_weight, 2)
    verdict = _infer_final_verdict(final_score)

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
        normalized_scores[field] = float(scores[field])

    signal_type = str(payload.get("signal_type", ""))
    if signal_type not in ALLOWED_SIGNAL_TYPES:
        raise ValueError(f"Invalid signal_type: {signal_type}")

    verdict = str(payload.get("verdict", ""))
    if verdict not in ALLOWED_VERDICTS:
        raise ValueError(f"Invalid verdict: {verdict}")

    comment = payload.get("comment")
    if not isinstance(comment, str) or not comment.strip():
        raise ValueError("Missing or empty required field: comment")

    return {
        **{field: str(payload[field]).strip() for field in REQUIRED_REASONING_FIELDS},
        "scores": normalized_scores,
        **normalized_scores,
        "total_score": float(payload.get("total_score", 0.0)),
        "signal_type": signal_type,
        "verdict": verdict,
        "comment": comment.strip(),
    }


def review_symbol_history(
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
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)

    ma20 = close.rolling(window=20, min_periods=20).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()
    latest_close = float(close.iloc[-1])
    latest_open = float(open_.iloc[-1])
    latest_volume = float(volume.iloc[-1])
    recent_window = frame.tail(20)
    recent_close = recent_window["close"].astype(float)
    recent_open = recent_window["open"].astype(float)
    recent_volume = (
        recent_window["vol"].astype(float)
        if "vol" in recent_window.columns
        else recent_window["volume"].astype(float)
    )

    trend_structure = _score_trend_structure(close, ma20, ma60)
    price_position = _score_price_position(close)
    volume_behavior = _score_volume_behavior(recent_open, recent_close, recent_volume)
    previous_abnormal_move = _score_previous_abnormal_move(close, volume)

    total_score = round(
        trend_structure * 0.20
        + price_position * 0.20
        + volume_behavior * 0.30
        + previous_abnormal_move * 0.30,
        2,
    )
    signal_type = _infer_signal_type(
        latest_close=latest_close,
        latest_open=latest_open,
        trend_structure=trend_structure,
        volume_behavior=volume_behavior,
        price_position=price_position,
    )
    verdict = _infer_verdict(total_score=total_score, volume_behavior=volume_behavior, signal_type=signal_type)

    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "review_type": "baseline",
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "total_score": total_score,
        "signal_type": signal_type,
        "verdict": verdict,
        "comment": _build_comment(signal_type=signal_type, verdict=verdict),
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


def _score_trend_structure(close: pd.Series, ma20: pd.Series, ma60: pd.Series) -> float:
    if len(close) < 60 or pd.isna(ma20.iloc[-1]) or pd.isna(ma60.iloc[-1]):
        return 3.0
    recent_gain = float(close.iloc[-1] / close.iloc[-20] - 1.0) if close.iloc[-20] else 0.0
    ma20_slope = float(ma20.iloc[-1] - ma20.iloc[-5])
    ma60_slope = float(ma60.iloc[-1] - ma60.iloc[-5])
    if close.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1] and ma20_slope > 0 and ma60_slope >= 0 and recent_gain > 0.05:
        return 5.0
    if close.iloc[-1] >= ma20.iloc[-1] and ma20.iloc[-1] >= ma60.iloc[-1] and ma20_slope >= 0:
        return 4.0
    if close.iloc[-1] >= ma20.iloc[-1]:
        return 3.0
    if close.iloc[-1] >= ma60.iloc[-1]:
        return 2.0
    return 1.0


def _score_price_position(close: pd.Series) -> float:
    if len(close) < 60:
        return 3.0
    recent = close.tail(120)
    low = float(recent.min())
    high = float(recent.max())
    if high <= low:
        return 3.0
    position = (float(close.iloc[-1]) - low) / (high - low)
    near_term_mean = float(close.tail(20).mean())
    mid_term_mean = float(close.tail(60).mean())
    if position <= 0.35:
        return 5.0
    if position <= 0.55:
        return 4.0
    if position <= 0.75:
        return 3.0
    if position <= 0.90:
        return 2.0
    if near_term_mean > mid_term_mean:
        return 3.0
    return 1.0


def _score_volume_behavior(open_: pd.Series, close: pd.Series, volume: pd.Series) -> float:
    bullish = volume[close >= open_]
    bearish = volume[close < open_]
    avg_bullish = float(bullish.mean()) if not bullish.empty else 0.0
    avg_bearish = float(bearish.mean()) if not bearish.empty else 0.0
    max_volume_index = int(volume.idxmax())
    max_volume_bullish = bool(close.loc[max_volume_index] >= open_.loc[max_volume_index])
    latest_green = bool(close.iloc[-1] >= open_.iloc[-1])

    if max_volume_bullish and avg_bullish > avg_bearish * 1.2 and latest_green:
        return 5.0
    if max_volume_bullish and avg_bullish >= avg_bearish:
        return 4.0
    if max_volume_bullish:
        return 3.0
    if latest_green and avg_bullish * 0.9 >= avg_bearish:
        return 2.0
    return 1.0


def _score_previous_abnormal_move(close: pd.Series, volume: pd.Series) -> float:
    if len(close) < 40:
        return 3.0
    latest_close = float(close.iloc[-1])
    early_close = float(close.iloc[-40])
    gain = latest_close / early_close - 1.0 if early_close else 0.0
    avg_volume = float(volume.tail(60).mean())
    peak_volume = float(volume.tail(60).max())

    if gain < 0.5 and peak_volume > avg_volume * 1.8:
        return 5.0
    if gain < 0.5 and peak_volume > avg_volume * 1.4:
        return 4.0
    if gain < 0.5:
        return 3.0
    if gain < 1.0:
        return 2.0
    return 1.0


def _infer_signal_type(
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


def _infer_verdict(*, total_score: float, volume_behavior: float, signal_type: str) -> str:
    if volume_behavior <= 1.0 or signal_type == "distribution_risk":
        return "FAIL"
    if total_score >= 4.0:
        return "PASS"
    if total_score >= 3.2:
        return "WATCH"
    return "FAIL"


def _infer_final_verdict(total_score: float) -> str:
    if total_score >= 4.0:
        return "PASS"
    if total_score >= 3.2:
        return "WATCH"
    return "FAIL"


def _build_comment(*, signal_type: str, verdict: str) -> str:
    if signal_type == "distribution_risk":
        return "趋势走弱且量价失衡，前期异动后的承接不足，当前更偏出货风险。"
    if verdict == "PASS":
        return "趋势结构顺畅，量价配合正常，前期异动仍有承接，当前具备继续走强条件。"
    return "结构有修复迹象，但量价与位置优势一般，暂时更适合继续观察。"
