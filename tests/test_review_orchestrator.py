import pandas as pd
import pytest

from stock_select.review_orchestrator import (
    build_review_payload,
    build_review_result,
    normalize_llm_review,
    review_symbol_history,
    summarize_reviews,
)


def test_build_review_payload_includes_chart_and_rubric() -> None:
    payload = build_review_payload(
        code="000001.SZ",
        pick_date="2026-04-01",
        chart_path="/tmp/000001_day.png",
        rubric_path="references/review-rubric.md",
    )

    assert payload["code"] == "000001.SZ"
    assert payload["chart_path"] == "/tmp/000001_day.png"
    assert payload["rubric_path"] == "references/review-rubric.md"
    assert payload["prompt_path"].endswith(".agents/skills/stock-select/references/prompt.md")
    assert payload["input_mode"] == "image"
    assert payload["dispatch"] == "subagent"


def test_build_review_result_prefers_llm_review_when_present() -> None:
    result = build_review_result(
        code="000001.SZ",
        pick_date="2026-04-01",
        chart_path="/tmp/000001_day.png",
        baseline_review={
            "total_score": 3.4,
            "signal_type": "rebound",
            "verdict": "WATCH",
            "comment": "baseline",
        },
        llm_review={
            "total_score": 4.6,
            "signal_type": "trend_start",
            "verdict": "PASS",
            "comment": "llm",
            "trend_reasoning": "up",
            "position_reasoning": "mid",
            "volume_reasoning": "good",
            "abnormal_move_reasoning": "present",
            "macd_reasoning": "histogram improving",
            "signal_reasoning": "trend start",
            "scores": {
                "trend_structure": 5,
                "price_position": 4,
                "volume_behavior": 5,
                "previous_abnormal_move": 4,
                "macd_phase": 5,
            },
        },
    )

    assert result["review_mode"] == "llm_primary"
    assert result["total_score"] == 4.6
    assert result["verdict"] == "PASS"
    assert result["llm_review"]["comment"] == "llm"
    assert result["llm_review"]["macd_reasoning"] == "histogram improving"
    assert result["llm_review"]["scores"]["macd_phase"] == 5
    assert result["baseline_review"]["comment"] == "baseline"


def test_normalize_llm_review_validates_and_flattens_scores() -> None:
    normalized = normalize_llm_review(
        {
            "trend_reasoning": "趋势向上",
            "position_reasoning": "位置中位",
            "volume_reasoning": "量价配合良好",
            "abnormal_move_reasoning": "前期有异动",
            "macd_reasoning": "MACD柱体持续修复",
            "signal_reasoning": "更像主升启动",
            "scores": {
                "trend_structure": 5,
                "price_position": 4,
                "volume_behavior": 5,
                "previous_abnormal_move": 4,
                "macd_phase": 5,
            },
            "total_score": 4.6,
            "signal_type": "trend_start",
            "verdict": "PASS",
            "comment": "趋势顺畅，量价配合健康，前期异动有效，当前仍有上行空间。",
        }
    )

    assert normalized["trend_structure"] == 5.0
    assert normalized["price_position"] == 4.0
    assert normalized["volume_behavior"] == 5.0
    assert normalized["previous_abnormal_move"] == 4.0
    assert normalized["macd_phase"] == 5.0
    assert normalized["verdict"] == "PASS"
    assert normalized["signal_type"] == "trend_start"


def test_normalize_llm_review_rejects_missing_reasoning() -> None:
    try:
        normalize_llm_review(
            {
                "scores": {
                    "trend_structure": 5,
                    "price_position": 4,
                    "volume_behavior": 5,
                    "previous_abnormal_move": 4,
                },
                "total_score": 4.6,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "缺少 reasoning",
            }
        )
    except ValueError as exc:
        assert "trend_reasoning" in str(exc)
    else:
        raise AssertionError("normalize_llm_review should reject missing reasoning fields")


def test_normalize_llm_review_requires_macd_reasoning() -> None:
    with pytest.raises(ValueError, match="macd_reasoning"):
        normalize_llm_review(
            {
                "trend_reasoning": "趋势向上",
                "position_reasoning": "位置适中",
                "volume_reasoning": "量价健康",
                "abnormal_move_reasoning": "前期有异动",
                "signal_reasoning": "主升启动",
                "scores": {
                    "trend_structure": 5,
                    "price_position": 4,
                    "volume_behavior": 5,
                    "previous_abnormal_move": 4,
                    "macd_phase": 5,
                },
                "total_score": 4.6,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "缺少 macd reasoning",
            }
        )


def test_summarize_reviews_sorts_recommendations() -> None:
    reviews = [
        {
            "code": "A",
            "review_mode": "baseline_local",
            "total_score": 3.0,
            "verdict": "FAIL",
            "baseline_review": {"total_score": 3.0, "verdict": "FAIL"},
        },
        {
            "code": "B",
            "review_mode": "llm_primary",
            "total_score": 5.0,
            "verdict": "PASS",
            "llm_review": {"total_score": 5.0, "verdict": "PASS"},
            "baseline_review": {"total_score": 3.5, "verdict": "WATCH"},
        },
    ]

    summary = summarize_reviews("2026-04-01", "b1", reviews, min_score=4.0, failures=[])

    assert summary["recommendations"][0]["code"] == "B"
    assert summary["excluded"][0]["code"] == "A"


def test_summarize_reviews_keeps_method_value_for_hcr() -> None:
    summary = summarize_reviews(
        "2026-04-01",
        "hcr",
        [{"code": "A", "review_mode": "baseline_local", "total_score": 4.6, "verdict": "PASS"}],
        min_score=4.0,
        failures=[],
    )

    assert summary["method"] == "hcr"


def test_review_symbol_history_returns_pass_for_constructive_trend() -> None:
    history = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=160, freq="B"),
            "open": [10.0 + idx * 0.05 for idx in range(160)],
            "high": [10.3 + idx * 0.05 for idx in range(160)],
            "low": [9.8 + idx * 0.05 for idx in range(160)],
            "close": [10.2 + idx * 0.05 for idx in range(160)],
            "vol": [1000.0 + idx * 5.0 for idx in range(160)],
        }
    )

    review = review_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-01",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review["code"] == "000001.SZ"
    assert review["chart_path"] == "/tmp/000001.SZ_day.png"
    assert review["verdict"] == "PASS"
    assert review["signal_type"] == "trend_start"
    assert review["total_score"] >= 4.0
    assert review["review_type"] == "baseline"


def test_review_symbol_history_flags_distribution_risk() -> None:
    history = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=160, freq="B"),
            "open": [20.0 - idx * 0.04 for idx in range(160)],
            "high": [20.2 - idx * 0.04 for idx in range(160)],
            "low": [19.7 - idx * 0.04 for idx in range(160)],
            "close": [19.8 - idx * 0.04 for idx in range(160)],
            "vol": [900.0 + idx * 8.0 for idx in range(160)],
        }
    )

    review = review_symbol_history(
        code="000002.SZ",
        pick_date="2026-04-01",
        history=history,
        chart_path="/tmp/000002.SZ_day.png",
    )

    assert review["verdict"] == "FAIL"
    assert review["signal_type"] == "distribution_risk"
    assert review["volume_behavior"] <= 2.0
