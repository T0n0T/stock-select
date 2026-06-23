from __future__ import annotations

from typing import Any, Callable

from ml.training.labels import as_float


def score_trial_report(report: dict[str, Any], *, primary_top_k: int = 3) -> float:
    rolling_metrics = ((report.get("rolling_summary") or {}).get("test_avg") or {})
    metrics = rolling_metrics or ((report.get("metrics") or {}).get("test") or {})
    loss_rate = as_float(metrics.get(f"top{primary_top_k}_ret3_le_0_rate"))
    positive_rate = as_float(metrics.get(f"top{primary_top_k}_ret3_positive_rate"))
    ge5_rate = as_float(metrics.get(f"top{primary_top_k}_ret3_ge_5_rate"))
    rank_ic = as_float(metrics.get("rank_ic_ret3"))
    ret5_ge5_rate = as_float(metrics.get(f"top{primary_top_k}_ret5_ge_5_rate"))
    ret5_rank_ic = as_float(metrics.get("rank_ic_ret5"))

    return (
        -(loss_rate if loss_rate is not None else 100.0) * 10000.0
        + (positive_rate or 0.0) * 100.0
        + (ge5_rate or 0.0) * 10.0
        + (rank_ic or 0.0) * 100.0
        + (ret5_ge5_rate or 0.0)
        + (ret5_rank_ic or 0.0) * 10.0
    )


def score_trial_report_ret10_ge_10(report: dict[str, Any], *, primary_top_k: int = 3) -> float:
    rolling_metrics = ((report.get("rolling_summary") or {}).get("test_avg") or {})
    metrics = rolling_metrics or ((report.get("metrics") or {}).get("test") or {})
    ge10_rate = as_float(metrics.get(f"top{primary_top_k}_ret10_ge_10_rate"))
    positive_rate = as_float(metrics.get(f"top{primary_top_k}_ret10_positive_rate"))
    le0_rate = as_float(metrics.get(f"top{primary_top_k}_ret10_le_0_rate"))
    rank_ic_ret10 = as_float(metrics.get("rank_ic_ret10"))
    ge10_capture = as_float(metrics.get(f"top{primary_top_k}_ret10_ge_10_capture_rate"))

    return (
        (ge10_rate or 0.0) * 10000.0
        + (ge10_capture or 0.0) * 100.0
        + (positive_rate or 0.0) * 100.0
        - (le0_rate or 0.0) * 100.0
        + (rank_ic_ret10 or 0.0) * 100.0
    )


OBJECTIVES: dict[str, Callable[[dict[str, Any]], float]] = {
    "default": score_trial_report,
    "top3_ret10_ge_10": score_trial_report_ret10_ge_10,
}


def resolve_objective(name: str) -> Callable[[dict[str, Any]], float]:
    if name not in OBJECTIVES:
        raise ValueError(f"unsupported objective: {name}; available: {sorted(OBJECTIVES.keys())}")
    return OBJECTIVES[name]
