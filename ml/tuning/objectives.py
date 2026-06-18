from __future__ import annotations

from typing import Any

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
