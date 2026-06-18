from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Sequence

from .labels import as_float, pct


def average_metric_dicts(metrics: Sequence[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted({key for item in metrics for key in item.keys()})
    result: dict[str, Any] = {}
    for key in keys:
        values = [as_float(item.get(key)) for item in metrics]
        valid = [value for value in values if value is not None]
        result[key] = round(sum(valid) / len(valid), 4) if valid else None
    return result


def env_partitions(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    partitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        env = str(row.get("env") or "unknown").lower()
        partitions[env].append(row)
    return dict(partitions)


def month_partitions(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    partitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        partitions[str(row.get("date") or "unknown")[:7]].append(row)
    return dict(partitions)


def assign_scores(rows: Sequence[dict[str, Any]], scores: Sequence[float]) -> list[dict[str, Any]]:
    output = []
    for row, score in zip(rows, scores):
        item = dict(row)
        item["model_score"] = float(score)
        output.append(item)
    return output


def grouped_by_date(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("date"))].append(row)
    return grouped


def evaluate_model(
    rows: Sequence[dict[str, Any]],
    *,
    top_n: int | None = None,
    top_k: Sequence[int] | None = None,
    label_column: str = "rank_label_3d",
    ndcg_at: Sequence[int] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    resolved_top_k = sorted({int(value) for value in (top_k if top_k is not None else [top_n or 3]) if int(value) > 0})
    resolved_ndcg_at = sorted({int(value) for value in (ndcg_at or []) if int(value) > 0})
    ordered_by_date = grouped_by_date(rows)
    for k in resolved_top_k:
        for _date, day_rows in ordered_by_date.items():
            ordered = sorted(day_rows, key=lambda row: (-(as_float(row.get("model_score")) or 0.0), str(row.get("code"))))
            result.setdefault("_ordered_by_date", {})[_date] = ordered
        for return_column in ("ret3", "ret5"):
            positive = ge5 = le0 = total = captured_ge5 = total_ge5 = 0
            ic_values: list[float] = []
            for _date, day_rows in ordered_by_date.items():
                ordered = result["_ordered_by_date"][_date]
                top_rows = ordered[:k]
                top_codes = {str(row.get("code")) for row in top_rows}
                good = [
                    row
                    for row in day_rows
                    if (as_float(row.get(return_column)) is not None and as_float(row.get(return_column)) >= 5.0)
                ]
                total_ge5 += len(good)
                captured_ge5 += sum(1 for row in good if str(row.get("code")) in top_codes)
                values = [as_float(row.get(return_column)) for row in top_rows if as_float(row.get(return_column)) is not None]
                positive += sum(1 for value in values if value is not None and value > 0.0)
                ge5 += sum(1 for value in values if value is not None and value >= 5.0)
                le0 += sum(1 for value in values if value is not None and value <= 0.0)
                total += len(values)
                ic = rank_ic(ordered, return_column)
                if ic is not None:
                    ic_values.append(ic)
            prefix = f"top{k}_{return_column}"
            result.update(
                {
                    f"{prefix}_positive_rate": pct(positive, total),
                    f"{prefix}_ge_5_rate": pct(ge5, total),
                    f"{prefix}_le_0_rate": pct(le0, total),
                    f"{prefix}_ge_5_capture_rate": pct(captured_ge5, total_ge5),
                    f"rank_ic_{return_column}": round(sum(ic_values) / len(ic_values), 4) if ic_values else None,
                }
            )
    result.pop("_ordered_by_date", None)
    for k in resolved_ndcg_at:
        values = []
        for day_rows in ordered_by_date.values():
            ordered = sorted(day_rows, key=lambda row: (-(as_float(row.get("model_score")) or 0.0), str(row.get("code"))))
            value = ndcg(ordered, label_column=label_column, k=k)
            if value is not None:
                values.append(value)
        result[f"ndcg_at_{k}"] = round(sum(values) / len(values), 4) if values else None
    return result


def dcg(gains: Sequence[float]) -> float:
    return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))


def ndcg(ordered_rows: Sequence[dict[str, Any]], *, label_column: str, k: int) -> float | None:
    gains = [as_float(row.get(label_column)) for row in ordered_rows]
    valid_gains = [max(0.0, float(value)) for value in gains if value is not None]
    if not valid_gains:
        return None
    ranked_gains = valid_gains[:k]
    ideal_gains = sorted(valid_gains, reverse=True)[:k]
    ideal = dcg(ideal_gains)
    if ideal == 0.0:
        return None
    return dcg(ranked_gains) / ideal


def rank_ic(ordered_rows: Sequence[dict[str, Any]], return_column: str) -> float | None:
    pairs = [
        (-float(index + 1), as_float(row.get(return_column)))
        for index, row in enumerate(ordered_rows)
        if as_float(row.get(return_column)) is not None
    ]
    if len(pairs) < 2:
        return None
    rank_values, ret_values = zip(*pairs)
    return pearson(rank_values, ret_values)


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_den = math.sqrt(sum((a - left_mean) ** 2 for a in left))
    right_den = math.sqrt(sum((b - right_mean) ** 2 for b in right))
    if left_den == 0.0 or right_den == 0.0:
        return None
    return round(numerator / left_den / right_den, 4)


def partition_diagnostics(rows: Sequence[dict[str, Any]], *, partition: str) -> dict[str, Any]:
    if partition == "env":
        partitions = env_partitions(rows)
    elif partition == "month":
        partitions = month_partitions(rows)
    else:
        raise ValueError(f"unsupported partition: {partition}")
    return {
        key: {
            "row_count": len(partition_rows),
            "metrics": evaluate_model(partition_rows, top_n=3),
        }
        for key, partition_rows in sorted(partitions.items())
        if partition_rows
    }
