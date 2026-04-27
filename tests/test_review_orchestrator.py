import pandas as pd
import pytest

from stock_select.review_orchestrator import (
    apply_macd_verdict_gate,
    compute_method_total_score,
    build_review_payload,
    build_review_result,
    merge_review_result,
    normalize_llm_review,
    review_symbol_history as orchestrator_review_symbol_history,
    summarize_reviews,
)
from stock_select.reviewers.default import review_symbol_history as default_review_symbol_history


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


def test_build_review_payload_merges_extra_context() -> None:
    payload = build_review_payload(
        code="000001.SZ",
        pick_date="2026-04-01",
        chart_path="/tmp/000001_day.png",
        rubric_path="references/review-rubric.md",
        extra_context={"weekly_wave_context": "周线 wave1"},
    )

    assert payload["weekly_wave_context"] == "周线 wave1"


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

    assert normalized["scores"] == {
        "trend_structure": 5.0,
        "price_position": 4.0,
        "volume_behavior": 5.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 5.0,
    }
    assert normalized["trend_structure"] == 5.0
    assert normalized["price_position"] == 4.0
    assert normalized["volume_behavior"] == 5.0
    assert normalized["previous_abnormal_move"] == 4.0
    assert normalized["macd_phase"] == 5.0
    assert normalized["total_score"] == pytest.approx(4.62)
    assert normalized["verdict"] == "PASS"
    assert normalized["signal_type"] == "trend_start"


def test_normalize_llm_review_excludes_macd_from_b1_total_score() -> None:
    payload = {
        "trend_reasoning": "趋势向上",
        "position_reasoning": "位置适中",
        "volume_reasoning": "量价健康",
        "abnormal_move_reasoning": "前期有异动",
        "macd_reasoning": "MACD偏弱但仅作风险描述",
        "signal_reasoning": "符合b1回调低点",
        "scores": {
            "trend_structure": 4,
            "price_position": 3,
            "volume_behavior": 2,
            "previous_abnormal_move": 4,
            "macd_phase": 1,
        },
        "signal_type": "rebound",
        "verdict": "WATCH",
        "comment": "MACD只参与描述，不参与LLM总分。",
        "method": "b1",
    }

    low_macd = normalize_llm_review(payload)
    high_macd = normalize_llm_review({**payload, "scores": {**payload["scores"], "macd_phase": 5}})

    assert low_macd["total_score"] == pytest.approx(3.25)
    assert high_macd["total_score"] == pytest.approx(low_macd["total_score"])
    assert low_macd["macd_phase"] == 1.0
    assert high_macd["macd_phase"] == 5.0


def test_compute_method_total_score_includes_macd_for_b1() -> None:
    scores = {
        "trend_structure": 5.0,
        "price_position": 4.0,
        "volume_behavior": 5.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 1.0,
    }

    assert compute_method_total_score("b1", scores) == pytest.approx(4.0)


def test_compute_method_total_score_reduces_macd_weight_for_b1() -> None:
    low_macd = {
        "trend_structure": 5.0,
        "price_position": 5.0,
        "volume_behavior": 5.0,
        "previous_abnormal_move": 5.0,
        "macd_phase": 1.0,
    }
    high_macd = {**low_macd, "macd_phase": 5.0}

    assert compute_method_total_score("b1", high_macd) - compute_method_total_score("b1", low_macd) == pytest.approx(0.6)


def test_compute_method_total_score_excludes_macd_for_hcr() -> None:
    scores = {
        "trend_structure": 5.0,
        "price_position": 4.0,
        "volume_behavior": 5.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 1.0,
    }

    assert compute_method_total_score("hcr", scores) == pytest.approx(4.53)


def test_compute_method_total_score_keeps_macd_for_b2() -> None:
    scores = {
        "trend_structure": 5.0,
        "price_position": 4.0,
        "volume_behavior": 5.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 1.0,
    }

    assert compute_method_total_score("b2", scores) == pytest.approx(3.82)


def test_compute_method_total_score_keeps_macd_for_default() -> None:
    scores = {
        "trend_structure": 5.0,
        "price_position": 4.0,
        "volume_behavior": 5.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 1.0,
    }

    assert compute_method_total_score("default", scores) == pytest.approx(3.82)


def test_b1_macd_gate_does_not_fail_non_wave1_wave3_weekly_labels() -> None:
    weekly_wave = type("Wave", (), {"label": "wave2"})()

    verdict = apply_macd_verdict_gate(
        method="b1",
        current_verdict="PASS",
        weekly_wave=weekly_wave,
        daily_recent_death_cross=False,
    )

    assert verdict == "PASS"


def test_b1_macd_gate_downgrades_recent_daily_death_cross_pass_to_watch() -> None:
    weekly_wave = type("Wave", (), {"label": "wave2"})()

    verdict = apply_macd_verdict_gate(
        method="b1",
        current_verdict="PASS",
        weekly_wave=weekly_wave,
        daily_recent_death_cross=True,
    )

    assert verdict == "WATCH"


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


def test_default_review_symbol_history_returns_watch_for_constructive_trend() -> None:
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

    review = default_review_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-01",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review["code"] == "000001.SZ"
    assert review["pick_date"] == "2026-04-01"
    assert review["chart_path"] == "/tmp/000001.SZ_day.png"
    assert review["review_type"] == "baseline"
    assert review["trend_structure"] == 5.0
    assert review["price_position"] == 3.0
    assert review["volume_behavior"] == 5.0
    assert review["previous_abnormal_move"] == 3.0
    assert review["macd_phase"] == 4.0
    assert review["total_score"] == 4.04
    assert review["signal_type"] == "trend_start"
    assert review["verdict"] == "PASS"
    assert review["comment"] == "趋势结构顺畅，量价配合正常，前期异动仍有承接，当前具备继续走强条件。"


def test_default_review_symbol_history_uses_b1_total_weight_when_method_is_b1() -> None:
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

    review = default_review_symbol_history(
        method="b1",
        code="000001.SZ",
        pick_date="2026-04-01",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review["trend_structure"] == 5.0
    assert review["price_position"] == 3.0
    assert review["volume_behavior"] == 5.0
    assert review["previous_abnormal_move"] == 3.0
    assert review["macd_phase"] == 4.0
    assert review["total_score"] == pytest.approx(4.05)
    assert review["verdict"] == "PASS"


def test_default_review_symbol_history_ignores_future_rows_after_pick_date() -> None:
    dates = pd.date_range("2026-01-01", periods=200, freq="B")
    pivot_index = 159
    pick_date = dates[pivot_index].strftime("%Y-%m-%d")

    constructive_history = pd.DataFrame(
        {
            "trade_date": dates[: pivot_index + 1],
            "open": [10.0 + idx * 0.05 for idx in range(pivot_index + 1)],
            "high": [10.3 + idx * 0.05 for idx in range(pivot_index + 1)],
            "low": [9.8 + idx * 0.05 for idx in range(pivot_index + 1)],
            "close": [10.2 + idx * 0.05 for idx in range(pivot_index + 1)],
            "vol": [1000.0 + idx * 5.0 for idx in range(pivot_index + 1)],
        }
    )
    future_collapse = pd.DataFrame(
        {
            "trade_date": dates[pivot_index + 1 :],
            "open": [18.0 - idx * 0.3 for idx in range(len(dates) - pivot_index - 1)],
            "high": [18.1 - idx * 0.3 for idx in range(len(dates) - pivot_index - 1)],
            "low": [17.3 - idx * 0.3 for idx in range(len(dates) - pivot_index - 1)],
            "close": [17.5 - idx * 0.3 for idx in range(len(dates) - pivot_index - 1)],
            "vol": [2000.0 + idx * 20.0 for idx in range(len(dates) - pivot_index - 1)],
        }
    )
    full_history = pd.concat([constructive_history, future_collapse], ignore_index=True)

    review_from_pick_slice = default_review_symbol_history(
        code="000001.SZ",
        pick_date=pick_date,
        history=constructive_history,
        chart_path="/tmp/000001.SZ_day.png",
    )
    review_with_future_rows = default_review_symbol_history(
        code="000001.SZ",
        pick_date=pick_date,
        history=full_history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review_with_future_rows["pick_date"] == pick_date
    assert review_with_future_rows["verdict"] == review_from_pick_slice["verdict"]
    assert review_with_future_rows["signal_type"] == review_from_pick_slice["signal_type"]
    assert review_with_future_rows["total_score"] == review_from_pick_slice["total_score"]
    assert review_with_future_rows["comment"] == review_from_pick_slice["comment"]


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

    review = orchestrator_review_symbol_history(
        code="000002.SZ",
        pick_date="2026-04-01",
        history=history,
        chart_path="/tmp/000002.SZ_day.png",
    )

    assert review["verdict"] == "FAIL"
    assert review["signal_type"] == "distribution_risk"
    assert review["volume_behavior"] <= 2.0


@pytest.mark.parametrize("invalid_score", [float("nan"), float("inf"), -1, 9])
def test_normalize_llm_review_rejects_non_finite_and_out_of_range_scores(invalid_score: float) -> None:
    with pytest.raises(ValueError, match="trend_structure"):
        normalize_llm_review(
            {
                "trend_reasoning": "趋势向上",
                "position_reasoning": "位置中位",
                "volume_reasoning": "量价配合良好",
                "abnormal_move_reasoning": "前期有异动",
                "macd_reasoning": "MACD 进入启动阶段",
                "signal_reasoning": "更像主升启动",
                "scores": {
                    "trend_structure": invalid_score,
                    "price_position": 4,
                    "volume_behavior": 5,
                    "previous_abnormal_move": 4,
                    "macd_phase": 5,
                },
                "total_score": 4.6,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "非法评分",
            }
        )


def test_merge_review_result_does_not_let_distribution_risk_veto_weighted_score() -> None:
    merged = merge_review_result(
        existing_review={
            "code": "000001.SZ",
            "pick_date": "2026-04-01",
            "chart_path": "/tmp/000001_day.png",
            "review_mode": "baseline_local",
            "baseline_review": {
                "total_score": 5.0,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "baseline",
            },
            "llm_review": None,
            "total_score": 5.0,
            "signal_type": "trend_start",
            "verdict": "PASS",
            "comment": "baseline",
        },
        llm_review={
            "total_score": 3.6,
            "signal_type": "distribution_risk",
            "verdict": "FAIL",
            "comment": "llm hard fail",
        },
    )

    assert merged["review_mode"] == "merged"
    assert merged["signal_type"] == "distribution_risk"
    assert merged["final_score"] == 4.16
    assert merged["verdict"] == "PASS"
    assert merged["comment"] == "llm hard fail"


def test_merge_review_result_does_not_let_explicit_llm_fail_veto_weighted_score() -> None:
    merged = merge_review_result(
        existing_review={
            "code": "000001.SZ",
            "pick_date": "2026-04-01",
            "chart_path": "/tmp/000001_day.png",
            "review_mode": "baseline_local",
            "baseline_review": {
                "total_score": 4.5,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "baseline",
            },
            "llm_review": None,
            "total_score": 4.5,
            "signal_type": "trend_start",
            "verdict": "PASS",
            "comment": "baseline",
        },
        llm_review={
            "total_score": 3.8,
            "signal_type": "rebound",
            "verdict": "FAIL",
            "comment": "llm explicit fail",
        },
    )

    assert merged["signal_type"] == "rebound"
    assert merged["final_score"] == 4.08
    assert merged["verdict"] == "PASS"
    assert merged["comment"] == "llm explicit fail"


def test_merge_review_result_uses_lower_llm_weight_for_b1() -> None:
    existing_review = {
        "code": "000001.SZ",
        "pick_date": "2026-04-01",
        "chart_path": "/tmp/000001_day.png",
        "review_mode": "baseline_local",
        "baseline_review": {
            "total_score": 4.6,
            "signal_type": "rebound",
            "verdict": "PASS",
            "comment": "baseline",
        },
        "llm_review": None,
        "total_score": 4.6,
        "signal_type": "rebound",
        "verdict": "PASS",
        "comment": "baseline",
    }
    llm_review = {
        "total_score": 3.0,
        "signal_type": "rebound",
        "verdict": "WATCH",
        "comment": "llm watch",
    }

    merged = merge_review_result(method="b1", existing_review=existing_review, llm_review=llm_review)

    assert merged["final_score"] == pytest.approx(3.96)


def test_normalize_llm_review_validates_macd_phase_score() -> None:
    with pytest.raises(ValueError, match="macd_phase"):
        normalize_llm_review(
            {
                "trend_reasoning": "趋势向上",
                "position_reasoning": "位置中位",
                "volume_reasoning": "量价配合良好",
                "abnormal_move_reasoning": "前期有异动",
                "macd_reasoning": "MACD 进入启动阶段",
                "signal_reasoning": "更像主升启动",
                "scores": {
                    "trend_structure": 5,
                    "price_position": 4,
                    "volume_behavior": 5,
                    "previous_abnormal_move": 4,
                },
                "total_score": 4.6,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "缺少 macd_phase",
            }
        )
