from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from stock_select.research.review_tuning import build_recommendations, render_recommendation_summary


def _load_review_tuning_recommend_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "review_tuning_recommend.py"
    spec = importlib.util.spec_from_file_location("review_tuning_recommend", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_recommendations_prefers_threshold_only_when_layering_direction_is_correct() -> None:
    correlations = {
        "groups": [
            {
                "scope": "method=b2,environment=neutral",
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 60,
                "conclusion_strength": "strong",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 60,
                        "coverage_strength": "strong",
                        "pearson_r": 0.12,
                        "spearman_r": 0.10,
                    }
                ],
            }
        ]
    }
    segments = [
        {
            "scope": "method=b2,environment=neutral",
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "avg_ret3_pct": 2.1,
            "ret3": {"avg": 2.1},
        },
        {
            "scope": "method=b2,environment=neutral",
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "avg_ret3_pct": 1.2,
            "ret3": {"avg": 1.2},
        },
        {
            "scope": "method=b2,environment=neutral",
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "avg_ret3_pct": -0.5,
            "ret3": {"avg": -0.5},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"][0]["action_type"] == "threshold_only"
    assert "environment_profiles.py" in result["recommendations"][0]["target_files"][0]


def test_build_recommendations_escalates_to_weights_and_thresholds_when_subscores_disagree() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:weak",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "weak",
                "sample_count": 24,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 24,
                        "coverage_strength": "weak",
                        "pearson_r": 0.03,
                        "spearman_r": 0.04,
                    },
                    {
                        "score_field": "macd_phase",
                        "target_field": "ret3_pct",
                        "pair_count": 24,
                        "coverage_strength": "weak",
                        "pearson_r": 0.21,
                        "spearman_r": 0.18,
                    },
                    {
                        "score_field": "price_position",
                        "target_field": "ret3_pct",
                        "pair_count": 24,
                        "coverage_strength": "weak",
                        "pearson_r": -0.17,
                        "spearman_r": -0.12,
                    },
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.1},
        },
        {
            "group_key": "method:b2|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.8},
        },
        {
            "group_key": "method:b2|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret3": {"avg": 0.2},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"][0]["action_type"] == "weights_and_thresholds"
    assert result["recommendations"][0]["target_files"] == ["src/stock_select/environment_profiles.py"]


def test_build_recommendations_skips_tuning_when_samples_are_insufficient() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 8,
                "conclusion_strength": "insufficient",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 8,
                        "coverage_strength": "insufficient",
                        "pearson_r": 0.4,
                        "spearman_r": 0.3,
                    }
                ],
            }
        ]
    }

    result = build_recommendations(correlations, [])

    assert result["recommendations"] == []
    assert result["excluded"][0]["reason"] == "insufficient_samples"


def test_build_recommendations_excludes_scope_when_total_score_coverage_is_insufficient_for_both_horizons() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 22,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 6,
                        "coverage_strength": "insufficient",
                        "pearson_r": 0.18,
                        "spearman_r": 0.16,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 7,
                        "coverage_strength": "insufficient",
                        "pearson_r": 0.21,
                        "spearman_r": 0.17,
                    },
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.1},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.4},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"] == []
    assert result["excluded"][0]["reason"] == "insufficient_coverage"


def test_build_recommendations_excludes_scope_when_verdict_layers_are_fewer_than_two() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 22,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 12,
                        "coverage_strength": "weak",
                        "pearson_r": 0.18,
                        "spearman_r": 0.16,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 12,
                        "coverage_strength": "weak",
                        "pearson_r": 0.11,
                        "spearman_r": 0.09,
                    },
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.3},
        }
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"] == []
    assert result["excluded"][0]["reason"] == "insufficient_verdict_layers"


def test_build_recommendations_can_use_ret5_horizon_when_ret3_coverage_is_insufficient() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 28,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 7,
                        "coverage_strength": "insufficient",
                        "pearson_r": 0.25,
                        "spearman_r": 0.19,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 15,
                        "coverage_strength": "weak",
                        "pearson_r": 0.14,
                        "spearman_r": 0.12,
                    },
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret5": {"avg": 2.0},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret5": {"avg": 0.8},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret5": {"avg": -0.2},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"][0]["action_type"] == "threshold_only"


def test_build_recommendations_accepts_positive_pass_watch_only_scope() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 18,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 18,
                        "coverage_strength": "weak",
                        "pearson_r": 0.09,
                        "spearman_r": 0.08,
                    }
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.6},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.7},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"][0]["action_type"] == "threshold_only"


def test_build_recommendations_does_not_trigger_reviewer_rework_for_repeated_negative_pass_watch_only_scopes() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b1|environment_state:strong",
                "scope_type": "method_environment_state",
                "method": "b1",
                "environment_state": "strong",
                "sample_count": 20,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 20,
                        "coverage_strength": "weak",
                        "pearson_r": -0.11,
                        "spearman_r": -0.10,
                    }
                ],
            },
            {
                "group_key": "method:b1|environment_state:weak",
                "scope_type": "method_environment_state",
                "method": "b1",
                "environment_state": "weak",
                "sample_count": 19,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 19,
                        "coverage_strength": "weak",
                        "pearson_r": -0.13,
                        "spearman_r": -0.09,
                    }
                ],
            },
        ]
    }
    segments = [
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": -0.4},
        },
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.2},
        },
        {
            "group_key": "method:b1|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": -0.3},
        },
        {
            "group_key": "method:b1|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.1},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"] == []
    assert all(item.get("action_type") != "reviewer_rework" for item in result["recommendations"])


def test_build_recommendations_prefers_usable_horizon_over_higher_coverage_but_unusable_horizon() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 26,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 20,
                        "coverage_strength": "strong",
                        "pearson_r": None,
                        "spearman_r": None,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 14,
                        "coverage_strength": "weak",
                        "pearson_r": 0.10,
                        "spearman_r": 0.08,
                    },
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret5": {"avg": 1.5},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret5": {"avg": 0.6},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret5": {"avg": -0.2},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"][0]["action_type"] == "threshold_only"
    assert "ret5_pct" in result["recommendations"][0]["reason"]


def test_build_recommendations_uses_two_layer_horizon_for_general_threshold_decision_when_other_horizon_is_not_usable() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 24,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 24,
                        "coverage_strength": "strong",
                        "pearson_r": 0.11,
                        "spearman_r": 0.10,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 16,
                        "coverage_strength": "insufficient",
                        "pearson_r": -0.12,
                        "spearman_r": -0.11,
                    },
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.5},
            "ret5": {"avg": -0.8},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.6},
            "ret5": {"avg": 0.2},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret5": {"avg": 0.5},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"][0]["action_type"] == "threshold_only"
    assert "ret3_pct" in result["recommendations"][0]["reason"]


def test_build_recommendations_excludes_conflicting_general_horizons_before_reviewer_rework() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b1|environment_state:strong",
                "scope_type": "method_environment_state",
                "method": "b1",
                "environment_state": "strong",
                "sample_count": 24,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 24,
                        "coverage_strength": "strong",
                        "pearson_r": 0.09,
                        "spearman_r": 0.08,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 16,
                        "coverage_strength": "weak",
                        "pearson_r": -0.13,
                        "spearman_r": -0.12,
                    },
                ],
            },
            {
                "group_key": "method:b1|environment_state:weak",
                "scope_type": "method_environment_state",
                "method": "b1",
                "environment_state": "weak",
                "sample_count": 22,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 22,
                        "coverage_strength": "strong",
                        "pearson_r": 0.07,
                        "spearman_r": 0.06,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 15,
                        "coverage_strength": "weak",
                        "pearson_r": -0.14,
                        "spearman_r": -0.10,
                    },
                ],
            },
        ]
    }
    segments = [
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.2},
            "ret5": {"avg": -0.7},
        },
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.5},
            "ret5": {"avg": 0.1},
        },
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret5": {"avg": 0.6},
        },
        {
            "group_key": "method:b1|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.0},
            "ret5": {"avg": -0.5},
        },
        {
            "group_key": "method:b1|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.4},
            "ret5": {"avg": 0.0},
        },
        {
            "group_key": "method:b1|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret5": {"avg": 0.4},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"] == []
    assert len(result["excluded"]) == 2
    assert {item["reason"] for item in result["excluded"]} == {"conflicting_horizons"}


def test_build_recommendations_excludes_scope_when_usable_horizons_conflict() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 24,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 24,
                        "coverage_strength": "strong",
                        "pearson_r": 0.12,
                        "spearman_r": 0.10,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 20,
                        "coverage_strength": "strong",
                        "pearson_r": -0.11,
                        "spearman_r": -0.09,
                    },
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.5},
            "ret5": {"avg": -0.7},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.7},
            "ret5": {"avg": 0.1},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret3": {"avg": -0.1},
            "ret5": {"avg": 0.5},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"] == []
    assert result["excluded"][0]["reason"] == "conflicting_horizons"


def test_build_recommendations_requires_pass_to_be_strictly_above_watch() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 21,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 21,
                        "coverage_strength": "weak",
                        "pearson_r": 0.09,
                        "spearman_r": 0.08,
                    }
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.0},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 1.0},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret3": {"avg": 0.2},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"] == []
    assert result["excluded"][0]["reason"] == "no_clear_recommendation"


def test_build_recommendations_excludes_scope_when_usable_horizons_imply_different_positive_actions() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b2|environment_state:neutral",
                "scope_type": "method_environment_state",
                "method": "b2",
                "environment_state": "neutral",
                "sample_count": 26,
                "conclusion_strength": "weak",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 26,
                        "coverage_strength": "strong",
                        "pearson_r": 0.10,
                        "spearman_r": 0.08,
                    },
                    {
                        "score_field": "price_position",
                        "target_field": "ret3_pct",
                        "pair_count": 26,
                        "coverage_strength": "strong",
                        "pearson_r": 0.14,
                        "spearman_r": 0.12,
                    },
                    {
                        "score_field": "total_score",
                        "target_field": "ret5_pct",
                        "pair_count": 20,
                        "coverage_strength": "weak",
                        "pearson_r": 0.03,
                        "spearman_r": 0.02,
                    },
                    {
                        "score_field": "price_position",
                        "target_field": "ret5_pct",
                        "pair_count": 20,
                        "coverage_strength": "weak",
                        "pearson_r": -0.11,
                        "spearman_r": -0.09,
                    },
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": 1.4},
            "ret5": {"avg": 1.1},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.7},
            "ret5": {"avg": 0.5},
        },
        {
            "group_key": "method:b2|environment_state:neutral",
            "scope_type": "method_environment_state",
            "method": "b2",
            "environment_state": "neutral",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret3": {"avg": 0.1},
            "ret5": {"avg": 0.1},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"] == []
    assert result["excluded"][0]["reason"] == "conflicting_horizons"


def test_build_recommendations_does_not_trigger_reviewer_rework_from_single_environment() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b1|environment_state:strong",
                "scope_type": "method_environment_state",
                "method": "b1",
                "environment_state": "strong",
                "sample_count": 42,
                "conclusion_strength": "strong",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 42,
                        "coverage_strength": "strong",
                        "pearson_r": -0.19,
                        "spearman_r": -0.21,
                    }
                ],
            }
        ]
    }
    segments = [
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": -0.8},
        },
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.4},
        },
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret3": {"avg": 0.7},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"] == []
    assert result["excluded"][0]["reason"] == "no_clear_recommendation"


def test_build_recommendations_triggers_reviewer_rework_after_repeated_negative_evidence_across_environments() -> None:
    correlations = {
        "groups": [
            {
                "group_key": "method:b1|environment_state:strong",
                "scope_type": "method_environment_state",
                "method": "b1",
                "environment_state": "strong",
                "sample_count": 42,
                "conclusion_strength": "strong",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 42,
                        "coverage_strength": "strong",
                        "pearson_r": -0.19,
                        "spearman_r": -0.21,
                    }
                ],
            },
            {
                "group_key": "method:b1|environment_state:weak",
                "scope_type": "method_environment_state",
                "method": "b1",
                "environment_state": "weak",
                "sample_count": 35,
                "conclusion_strength": "strong",
                "metrics": [
                    {
                        "score_field": "total_score",
                        "target_field": "ret3_pct",
                        "pair_count": 35,
                        "coverage_strength": "strong",
                        "pearson_r": -0.14,
                        "spearman_r": -0.16,
                    }
                ],
            },
        ]
    }
    segments = [
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": -0.8},
        },
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.4},
        },
        {
            "group_key": "method:b1|environment_state:strong",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "strong",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret3": {"avg": 0.7},
        },
        {
            "group_key": "method:b1|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "PASS",
            "ret3": {"avg": -0.6},
        },
        {
            "group_key": "method:b1|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "WATCH",
            "ret3": {"avg": 0.3},
        },
        {
            "group_key": "method:b1|environment_state:weak",
            "scope_type": "method_environment_state",
            "method": "b1",
            "environment_state": "weak",
            "segment_type": "verdict",
            "segment_value": "FAIL",
            "ret3": {"avg": 0.5},
        },
    ]

    result = build_recommendations(correlations, segments)

    assert len(result["recommendations"]) == 2
    assert {item["action_type"] for item in result["recommendations"]} == {"reviewer_rework"}


def test_render_recommendation_summary_includes_action_and_next_tasks() -> None:
    payload = {
        "recommendations": [
            {
                "scope": "method=b2,environment=neutral",
                "action_type": "threshold_only",
                "reason": "total_score non-negative and verdict layering is directionally correct",
                "target_files": ["src/stock_select/environment_profiles.py"],
                "next_tasks": ["adjust PASS/WATCH thresholds for neutral environment"],
                "success_criteria": ["PASS avg ret3_pct stays above WATCH and FAIL"],
            }
        ],
        "excluded": [],
    }

    summary = render_recommendation_summary(payload)

    assert "threshold_only" in summary
    assert "src/stock_select/environment_profiles.py" in summary
    assert "adjust PASS/WATCH thresholds for neutral environment" in summary


def test_review_tuning_recommend_main_writes_json_and_markdown(tmp_path: Path) -> None:
    module = _load_review_tuning_recommend_module()

    correlations_path = tmp_path / "correlations.json"
    correlations_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "group_key": "method:b2|environment_state:neutral",
                        "scope_type": "method_environment_state",
                        "method": "b2",
                        "environment_state": "neutral",
                        "sample_count": 30,
                        "conclusion_strength": "strong",
                        "metrics": [
                        {
                            "score_field": "total_score",
                            "target_field": "ret3_pct",
                            "pair_count": 30,
                            "coverage_strength": "strong",
                            "pearson_r": 0.08,
                            "spearman_r": 0.07,
                        }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    segments_path = tmp_path / "segments.json"
    segments_path.write_text(
        json.dumps(
            [
                {
                    "group_key": "method:b2|environment_state:neutral",
                    "scope_type": "method_environment_state",
                    "method": "b2",
                    "environment_state": "neutral",
                    "segment_type": "verdict",
                    "segment_value": "PASS",
                    "ret3": {"avg": 1.4},
                },
                {
                    "group_key": "method:b2|environment_state:neutral",
                    "scope_type": "method_environment_state",
                    "method": "b2",
                    "environment_state": "neutral",
                    "segment_type": "verdict",
                    "segment_value": "WATCH",
                    "ret3": {"avg": 0.9},
                },
                {
                    "group_key": "method:b2|environment_state:neutral",
                    "scope_type": "method_environment_state",
                    "method": "b2",
                    "environment_state": "neutral",
                    "segment_type": "verdict",
                    "segment_value": "FAIL",
                    "ret3": {"avg": -0.2},
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    args = module.parse_args(
        [
            "--correlations",
            str(correlations_path),
            "--segments",
            str(segments_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert module.main(args) == 0

    payload = json.loads((output_dir / "recommendations.json").read_text(encoding="utf-8"))
    summary = (output_dir / "summary.md").read_text(encoding="utf-8")
    assert payload["recommendations"][0]["action_type"] == "threshold_only"
    assert "threshold_only" in summary
