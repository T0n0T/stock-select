from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Sequence

from .labels import as_float, pct

SELECTION_SUCCESS_RETURN_COLUMN = "ret_t1_open_to_t3_close"
SELECTION_BENCHMARK_RETURN_COLUMN = "benchmark_csi300_ret_t1_open_to_t3_close"
MARKET_ENVIRONMENT_COLUMNS = (
    "market_up_ratio",
    "market_ge5_ratio",
    "market_le_minus5_ratio",
    "market_median_pct_chg",
    "market_amount_ma5_ratio",
    "market_net_mf_to_amount_pct",
    "market_approx_limit_up_count",
    "market_approx_limit_down_count",
)


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


def topn_return_overlap(
    rows: Sequence[dict[str, Any]], *, return_column: str, top_n: int,
) -> dict[str, Any]:
    """Compare each day's model TopN with the TopN realized-return set."""
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    overlaps: list[int] = []
    for day_rows in grouped_by_date(rows).values():
        eligible = []
        for row in day_rows:
            score = as_float(row.get("model_score"))
            realized = as_float(row.get(return_column))
            if score is not None and realized is not None and math.isfinite(score) and math.isfinite(realized):
                eligible.append((str(row.get("code")), score, realized))
        if len(eligible) < top_n:
            continue
        predicted = {code for code, _score, _realized in
                     sorted(eligible, key=lambda item: (-item[1], item[0]))[:top_n]}
        realized = {code for code, _score, _return in
                    sorted(eligible, key=lambda item: (-item[2], item[0]))[:top_n]}
        overlaps.append(len(predicted & realized))
    prefix = f"top{top_n}_{return_column}"
    days = len(overlaps)
    total = sum(overlaps)
    return {
        f"{prefix}_overlap_dates": days,
        f"{prefix}_mean_overlap": round(total / days, 4) if days else None,
        f"{prefix}_overlap_rate": round(total / (days * top_n) * 100.0, 4) if days else None,
        f"{prefix}_exact_match_rate": round(sum(value == top_n for value in overlaps) / days * 100.0, 4)
        if days else None,
    }


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
    return_thresholds = (("ret3", 5.0, "ge_5"), ("ret5", 5.0, "ge_5"), ("ret10", 10.0, "ge_10"))
    if any("exit_net_return" in row for row in rows):
        return_thresholds += (("exit_return", 5.0, "ge_5"), ("exit_net_return", 5.0, "ge_5"))
    for k in resolved_top_k:
        for _date, day_rows in ordered_by_date.items():
            ordered = sorted(day_rows, key=lambda row: (-(as_float(row.get("model_score")) or 0.0), str(row.get("code"))))
            result.setdefault("_ordered_by_date", {})[_date] = ordered
        for return_column, threshold, threshold_key in return_thresholds:
            positive = ge_threshold = le0 = total = captured_ge_threshold = total_ge_threshold = 0
            ic_values: list[float] = []
            for _date, day_rows in ordered_by_date.items():
                ordered = result["_ordered_by_date"][_date]
                top_rows = ordered[:k]
                top_codes = {str(row.get("code")) for row in top_rows}
                good = [
                    row
                    for row in day_rows
                    if (as_float(row.get(return_column)) is not None and as_float(row.get(return_column)) >= threshold)
                ]
                total_ge_threshold += len(good)
                captured_ge_threshold += sum(1 for row in good if str(row.get("code")) in top_codes)
                values = [as_float(row.get(return_column)) for row in top_rows if as_float(row.get(return_column)) is not None]
                positive += sum(1 for value in values if value is not None and value > 0.0)
                ge_threshold += sum(1 for value in values if value is not None and value >= threshold)
                le0 += sum(1 for value in values if value is not None and value <= 0.0)
                total += len(values)
                ic = rank_ic(ordered, return_column)
                if ic is not None:
                    ic_values.append(ic)
            prefix = f"top{k}_{return_column}"
            result.update(
                {
                    f"{prefix}_positive_rate": pct(positive, total),
                    f"{prefix}_{threshold_key}_rate": pct(ge_threshold, total),
                    f"{prefix}_le_0_rate": pct(le0, total),
                    f"{prefix}_{threshold_key}_capture_rate": pct(captured_ge_threshold, total_ge_threshold),
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


def selection_success_analysis(
    rows: Sequence[dict[str, Any]],
    *,
    top_k: int | None,
    return_column: str = SELECTION_SUCCESS_RETURN_COLUMN,
    benchmark_return_column: str = SELECTION_BENCHMARK_RETURN_COLUMN,
) -> dict[str, Any]:
    """Summarize daily Top-K win rates and their relation to market context."""
    if top_k is not None and top_k <= 0:
        raise ValueError("top_k must be positive")

    daily_results: list[dict[str, Any]] = []
    for day_rows in grouped_by_date(rows).values():
        ranked = sorted(
            day_rows,
            key=lambda row: (-(as_float(row.get("model_score")) or 0.0), str(row.get("code"))),
        )
        selected = ranked if top_k is None else ranked[:top_k]
        outcomes = []
        for row in selected:
            realized = as_float(row.get(return_column))
            if realized is None or not math.isfinite(realized):
                continue
            benchmark = as_float(row.get(benchmark_return_column))
            if benchmark is not None and not math.isfinite(benchmark):
                benchmark = None
            outcomes.append((realized, benchmark))
        if not outcomes:
            continue

        environment = next(
            (str(row.get("env")).strip().lower() for row in day_rows if str(row.get("env") or "").strip()),
            "unknown",
        )
        environment_factors: dict[str, float] = {}
        for column in MARKET_ENVIRONMENT_COLUMNS:
            value = next(
                (
                    numeric
                    for row in day_rows
                    if (numeric := as_float(row.get(column))) is not None and math.isfinite(numeric)
                ),
                None,
            )
            if value is not None:
                environment_factors[column] = value

        returns = [realized for realized, _benchmark in outcomes]
        benchmark_pairs = [
            (realized, benchmark)
            for realized, benchmark in outcomes
            if benchmark is not None
        ]
        daily_results.append(
            {
                "env": environment,
                "returns": returns,
                "win_count": sum(realized > 0.0 for realized in returns),
                "win_rate": pct(sum(realized > 0.0 for realized in returns), len(returns)),
                "benchmark_pairs": benchmark_pairs,
                "benchmark_win_count": sum(realized > benchmark for realized, benchmark in benchmark_pairs),
                "excess_returns": [realized - benchmark for realized, benchmark in benchmark_pairs],
                "environment_factors": environment_factors,
            }
        )

    def summarize(days: Sequence[dict[str, Any]]) -> dict[str, Any]:
        returns = [value for day in days for value in day["returns"]]
        benchmark_pairs = [pair for day in days for pair in day["benchmark_pairs"]]
        excess_returns = [value for day in days for value in day["excess_returns"]]
        daily_win_rates = [float(day["win_rate"]) for day in days if day["win_rate"] is not None]
        win_count = sum(int(day["win_count"]) for day in days)
        benchmark_win_count = sum(int(day["benchmark_win_count"]) for day in days)
        return {
            "date_count": len(days),
            "selected_count": len(returns),
            "win_count": win_count,
            "pooled_win_rate": pct(win_count, len(returns)),
            "mean_daily_win_rate": round(sum(daily_win_rates) / len(daily_win_rates), 4) if daily_win_rates else None,
            "mean_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
            "benchmark_observation_count": len(benchmark_pairs),
            "benchmark_win_count": benchmark_win_count,
            "benchmark_win_rate": pct(benchmark_win_count, len(benchmark_pairs)),
            "mean_excess_return_pct": round(sum(excess_returns) / len(excess_returns), 4) if excess_returns else None,
        }

    by_env_days: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for day in daily_results:
        by_env_days[day["env"]].append(day)

    correlations: dict[str, dict[str, Any]] = {}
    for column in MARKET_ENVIRONMENT_COLUMNS:
        pairs = [
            (float(day["win_rate"]), day["environment_factors"][column])
            for day in daily_results
            if day["win_rate"] is not None and column in day["environment_factors"]
        ]
        if pairs:
            correlations[column] = {
                "date_count": len(pairs),
                "pearson_r": pearson([value for value, _factor in pairs], [factor for _value, factor in pairs]),
            }

    return {
        "top_k": top_k,
        "selection_scope": "all_candidates" if top_k is None else "model_top_k",
        "return_column": return_column,
        "return_definition": "t+1 open entry to t+3 close exit; win means return > 0",
        **summarize(daily_results),
        "by_env": {env: summarize(days) for env, days in sorted(by_env_days.items())},
        "environment_correlations": correlations,
    }


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
