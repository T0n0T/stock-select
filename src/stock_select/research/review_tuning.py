from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError

from stock_select.cli import SHARED_PREPARED_METHODS, _load_prepared_cache_v2


SCORE_FIELDS = (
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "macd_phase",
)

CORRELATION_SCORE_FIELDS = ("total_score",) + SCORE_FIELDS
RETURN_FIELDS = ("ret3_pct", "ret5_pct")
DEFAULT_TOTAL_BAND_EDGES = (3.5, 4.0, 4.3, 4.6)
CORRELATION_CSV_COLUMNS = [
    "group_key",
    "scope_type",
    "method",
    "environment_state",
    "sample_count",
    "conclusion_strength",
    "score_field",
    "target_field",
    "pair_count",
    "coverage_strength",
    "pearson_r",
    "spearman_r",
]
SEGMENT_CSV_COLUMNS = [
    "group_key",
    "scope_type",
    "method",
    "environment_state",
    "segment_type",
    "segment_value",
    "sample_count",
    "ret3_n",
    "ret3_avg",
    "ret3_median",
    "ret3_win_rate",
    "ret3_max",
    "ret3_min",
    "ret5_n",
    "ret5_avg",
    "ret5_median",
    "ret5_win_rate",
    "ret5_max",
    "ret5_min",
]


@dataclass(frozen=True)
class RecommendationDecision:
    action_type: str
    reason: str
    target_files: list[str]
    next_tasks: list[str]
    success_criteria: list[str]


def _load_prepared(method: str, prepared_root: Path, *, end_date: str) -> pd.DataFrame:
    normalized_method = method.strip().lower()
    if normalized_method in SHARED_PREPARED_METHODS:
        feather_pattern = "*.feather"
        ignored_feather_suffixes = {".hcr.feather", ".intraday.feather"}
        feather_suffix = ".feather"
    else:
        feather_pattern = f"*.{normalized_method}.feather"
        ignored_feather_suffixes = set()
        feather_suffix = f".{normalized_method}.feather"

    candidates: list[tuple[str, Path]] = []
    for path in sorted(prepared_root.glob(feather_pattern)):
        if any(path.name.endswith(suffix) for suffix in ignored_feather_suffixes):
            continue
        date_part = path.name.removesuffix(feather_suffix)
        if date_part <= end_date:
            candidates.append((date_part, path))

    if not candidates:
        raise FileNotFoundError(
            f"No prepared cache found for method={method} on or before {end_date} in {prepared_root}"
        )

    data_path = sorted(candidates, key=lambda item: item[0])[-1][1]
    payload = _load_prepared_cache_v2(data_path, data_path.with_suffix(".meta.json"))
    prepared = payload.get("prepared_table")
    if not isinstance(prepared, pd.DataFrame):
        raise ValueError("Prepared cache prepared_table missing.")
    return prepared


def _get_forward_returns(prepared: pd.DataFrame, *, code: str, pick_date: str) -> dict[str, float | None] | None:
    if prepared.empty or "ts_code" not in prepared.columns:
        return None

    df = prepared.loc[prepared["ts_code"] == code].copy()
    if df.empty:
        return None

    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce", format="mixed")
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    current = df[df["trade_date"] <= pd.Timestamp(pick_date)].tail(1)
    if current.empty or pd.isna(current.iloc[0]["close"]):
        return None

    entry_close = float(current.iloc[0]["close"])
    future = df[df["trade_date"] > pd.Timestamp(pick_date)].reset_index(drop=True)

    result: dict[str, float | None] = {"ret3_pct": None, "ret5_pct": None}
    if len(future) >= 3 and pd.notna(future.iloc[2]["close"]):
        result["ret3_pct"] = round((float(future.iloc[2]["close"]) / entry_close - 1.0) * 100, 2)
    if len(future) >= 5 and pd.notna(future.iloc[4]["close"]):
        result["ret5_pct"] = round((float(future.iloc[4]["close"]) / entry_close - 1.0) * 100, 2)
    return result


def _get_score(item: dict[str, object], field: str) -> float | None:
    if field in item and item[field] is not None:
        return float(item[field])
    baseline = item.get("baseline_review") or {}
    value = baseline.get(field)
    return None if value is None else float(value)


def _get_verdict(item: dict[str, object]) -> str:
    top_level = item.get("verdict")
    if top_level:
        return str(top_level).upper()
    baseline = item.get("baseline_review") or {}
    return str(baseline.get("verdict") or "").upper()


def _coerce_finite_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _normalize_category_value(value: object) -> str | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.lower() == "nan":
        return None
    return normalized


def read_rows_csv(path: Path) -> list[dict[str, object]]:
    try:
        frame = pd.read_csv(path)
    except EmptyDataError:
        return []
    if frame.empty:
        return []
    return frame.to_dict("records")


def _finite_pairs(
    rows: list[dict[str, object]],
    x_field: str,
    y_field: str,
) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in rows:
        x_value = _coerce_finite_float(row.get(x_field))
        y_value = _coerce_finite_float(row.get(y_field))
        if x_value is None or y_value is None:
            continue
        pairs.append((x_value, y_value))
    return pairs


def _pearson_from_pairs(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    x_mean = sum(x for x, _ in pairs) / len(pairs)
    y_mean = sum(y for _, y in pairs) / len(pairs)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_scale = math.sqrt(sum((x - x_mean) ** 2 for x, _ in pairs))
    y_scale = math.sqrt(sum((y - y_mean) ** 2 for _, y in pairs))
    if x_scale == 0 or y_scale == 0:
        return None
    return numerator / (x_scale * y_scale)


def _rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        average_rank = (start + end + 2) / 2.0
        for index in range(start, end + 1):
            ranks[order[index]] = average_rank
        start = end + 1
    return ranks


def safe_pearson(rows: list[dict[str, object]], x_field: str, y_field: str) -> float | None:
    value = _pearson_from_pairs(_finite_pairs(rows, x_field, y_field))
    return None if value is None else round(value, 4)


def safe_spearman(rows: list[dict[str, object]], x_field: str, y_field: str) -> float | None:
    pairs = _finite_pairs(rows, x_field, y_field)
    if len(pairs) < 3:
        return None
    x_ranks = _rankdata([x for x, _ in pairs])
    y_ranks = _rankdata([y for _, y in pairs])
    value = _pearson_from_pairs(list(zip(x_ranks, y_ranks)))
    return None if value is None else round(value, 4)


def _classify_conclusion_strength(
    sample_count: int,
    *,
    min_samples_strong: int,
    min_samples_weak: int,
) -> str:
    if sample_count >= min_samples_strong:
        return "strong"
    if sample_count >= min_samples_weak:
        return "weak"
    return "insufficient"


def iter_scoped_rows(
    rows: list[dict[str, object]],
) -> list[tuple[dict[str, object], list[dict[str, object]]]]:
    groups: list[tuple[dict[str, object], list[dict[str, object]]]] = [
        (
            {
                "group_key": "overall",
                "scope_type": "overall",
                "method": None,
                "environment_state": None,
            },
            rows,
        )
    ]

    methods = sorted(
        {
            normalized
            for row in rows
            if (normalized := _normalize_category_value(row.get("method"))) is not None
        }
    )
    for method in methods:
        scoped_rows = [row for row in rows if _normalize_category_value(row.get("method")) == method]
        groups.append(
            (
                {
                    "group_key": f"method:{method}",
                    "scope_type": "method",
                    "method": method,
                    "environment_state": None,
                },
                scoped_rows,
            )
        )

    environment_states = sorted(
        {
            normalized
            for row in rows
            if (normalized := _normalize_category_value(row.get("environment_state"))) is not None
        }
    )
    for environment_state in environment_states:
        scoped_rows = [
            row
            for row in rows
            if _normalize_category_value(row.get("environment_state")) == environment_state
        ]
        groups.append(
            (
                {
                    "group_key": f"environment_state:{environment_state}",
                    "scope_type": "environment_state",
                    "method": None,
                    "environment_state": environment_state,
                },
                scoped_rows,
            )
        )

    method_environment_pairs = sorted(
        {
            (method, environment_state)
            for row in rows
            if (method := _normalize_category_value(row.get("method"))) is not None
            and (environment_state := _normalize_category_value(row.get("environment_state"))) is not None
        }
    )
    for method, environment_state in method_environment_pairs:
        scoped_rows = [
            row
            for row in rows
            if _normalize_category_value(row.get("method")) == method
            and _normalize_category_value(row.get("environment_state")) == environment_state
        ]
        groups.append(
            (
                {
                    "group_key": f"method:{method}|environment_state:{environment_state}",
                    "scope_type": "method_environment_state",
                    "method": method,
                    "environment_state": environment_state,
                },
                scoped_rows,
            )
        )

    return groups


def build_group_payload(
    scope: dict[str, object],
    scoped_rows: list[dict[str, object]],
    metrics: list[dict[str, object]],
    min_samples_strong: int,
    min_samples_weak: int,
) -> dict[str, object]:
    sample_count = len(scoped_rows)
    return {
        **scope,
        "sample_count": sample_count,
        "conclusion_strength": _classify_conclusion_strength(
            sample_count,
            min_samples_strong=min_samples_strong,
            min_samples_weak=min_samples_weak,
        ),
        "metrics": metrics,
    }


def compute_correlations(
    rows: list[dict[str, object]],
    *,
    min_samples_strong: int = 30,
    min_samples_weak: int = 10,
) -> dict[str, list[dict[str, object]]]:
    if not rows:
        return {"groups": []}
    groups: list[dict[str, object]] = []
    for scope, scoped_rows in iter_scoped_rows(rows):
        metrics: list[dict[str, object]] = []
        for score_field in CORRELATION_SCORE_FIELDS:
            for target_field in RETURN_FIELDS:
                pair_count = len(_finite_pairs(scoped_rows, score_field, target_field))
                metrics.append(
                    {
                        "score_field": score_field,
                        "target_field": target_field,
                        "pair_count": pair_count,
                        "coverage_strength": _classify_conclusion_strength(
                            pair_count,
                            min_samples_strong=min_samples_strong,
                            min_samples_weak=min_samples_weak,
                        ),
                        "pearson_r": safe_pearson(scoped_rows, score_field, target_field),
                        "spearman_r": safe_spearman(scoped_rows, score_field, target_field),
                    }
                )
        groups.append(
            build_group_payload(
                scope,
                scoped_rows,
                metrics,
                min_samples_strong=min_samples_strong,
                min_samples_weak=min_samples_weak,
            )
        )
    return {"groups": groups}


def _return_stats(rows: list[dict[str, object]], key: str) -> dict[str, float | int]:
    values = [_coerce_finite_float(row.get(key)) for row in rows]
    finite_values = [value for value in values if value is not None]
    if not finite_values:
        return {"n": 0}
    wins = sum(value > 0 for value in finite_values)
    return {
        "n": len(finite_values),
        "avg": round(sum(finite_values) / len(finite_values), 3),
        "median": round(statistics.median(finite_values), 3),
        "win_rate": round(wins / len(finite_values) * 100, 1),
        "max": round(max(finite_values), 3),
        "min": round(min(finite_values), 3),
    }


def _score_bucket(value: object) -> str | None:
    numeric_value = _coerce_finite_float(value)
    if numeric_value is None:
        return None
    rounded = math.floor(numeric_value + 0.5)
    bounded = max(1, min(5, rounded))
    return str(bounded)


def _total_score_band(value: object, edges: tuple[float, ...] = DEFAULT_TOTAL_BAND_EDGES) -> str | None:
    numeric_value = _coerce_finite_float(value)
    if numeric_value is None:
        return None
    if numeric_value < edges[0]:
        return f"<{edges[0]:.1f}"
    for left, right in zip(edges, edges[1:]):
        if left <= numeric_value < right:
            return f"{left:.1f}-{right:.1f}"
    return f">={edges[-1]:.1f}"


def _ordered_total_score_band_labels(
    edges: tuple[float, ...] = DEFAULT_TOTAL_BAND_EDGES,
) -> list[str]:
    labels = [f"<{edges[0]:.1f}"]
    labels.extend(f"{left:.1f}-{right:.1f}" for left, right in zip(edges, edges[1:]))
    labels.append(f">={edges[-1]:.1f}")
    return labels


def _build_segment_payload(
    *,
    scope: dict[str, object],
    segment_type: str,
    segment_value: str,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        **scope,
        "segment_type": segment_type,
        "segment_value": segment_value,
        "sample_count": len(rows),
        "ret3": _return_stats(rows, "ret3_pct"),
        "ret5": _return_stats(rows, "ret5_pct"),
    }


def build_score_bucket_segments(
    rows: list[dict[str, object]],
    *,
    scope: dict[str, object],
    field: str,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        bucket = _score_bucket(row.get(field))
        if bucket is None:
            continue
        grouped.setdefault(bucket, []).append(row)
    return [
        _build_segment_payload(
            scope=scope,
            segment_type=f"{field}_bucket",
            segment_value=segment_value,
            rows=grouped[segment_value],
        )
        for segment_value in sorted(grouped)
    ]


def build_total_score_band_segments(
    rows: list[dict[str, object]],
    *,
    scope: dict[str, object],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        band = _total_score_band(row.get("total_score"))
        if band is None:
            continue
        grouped.setdefault(band, []).append(row)
    return [
        _build_segment_payload(
            scope=scope,
            segment_type="total_score_band",
            segment_value=segment_value,
            rows=grouped[segment_value],
        )
        for segment_value in _ordered_total_score_band_labels()
        if segment_value in grouped
    ]


def build_verdict_segments(
    rows: list[dict[str, object]],
    *,
    scope: dict[str, object],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        normalized_verdict = _normalize_category_value(row.get("verdict"))
        verdict = "" if normalized_verdict is None else normalized_verdict.upper()
        if not verdict:
            continue
        grouped.setdefault(verdict, []).append(row)
    return [
        _build_segment_payload(
            scope=scope,
            segment_type="verdict",
            segment_value=segment_value,
            rows=grouped[segment_value],
        )
        for segment_value in sorted(grouped)
    ]


def compute_segments(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    for scope, scoped_rows in iter_scoped_rows(rows):
        for field in SCORE_FIELDS:
            segments.extend(build_score_bucket_segments(scoped_rows, scope=scope, field=field))
        segments.extend(build_total_score_band_segments(scoped_rows, scope=scope))
        segments.extend(build_verdict_segments(scoped_rows, scope=scope))
    return segments


def flatten_segment_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    flattened_rows: list[dict[str, object]] = []
    for row in rows:
        base = {key: value for key, value in row.items() if key not in {"ret3", "ret5"}}
        for prefix in ("ret3", "ret5"):
            stats = row.get(prefix) or {}
            base[f"{prefix}_n"] = stats.get("n")
            base[f"{prefix}_avg"] = stats.get("avg")
            base[f"{prefix}_median"] = stats.get("median")
            base[f"{prefix}_win_rate"] = stats.get("win_rate")
            base[f"{prefix}_max"] = stats.get("max")
            base[f"{prefix}_min"] = stats.get("min")
        flattened_rows.append(base)
    return flattened_rows


def flatten_correlation_rows(payload: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    flattened_rows: list[dict[str, object]] = []
    for group in payload["groups"]:
        base = {key: value for key, value in group.items() if key != "metrics"}
        for metric in group["metrics"]:
            flattened_rows.append({**base, **metric})
    return flattened_rows


def build_correlation_frame(payload: dict[str, list[dict[str, object]]]) -> pd.DataFrame:
    return pd.DataFrame(flatten_correlation_rows(payload), columns=CORRELATION_CSV_COLUMNS)


def build_segment_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(flatten_segment_rows(rows), columns=SEGMENT_CSV_COLUMNS)


def _format_scope_label(group: dict[str, object]) -> str:
    method = _normalize_category_value(group.get("method")) or "unknown"
    environment_state = _normalize_category_value(group.get("environment_state")) or "unknown"
    return f"method={method},environment={environment_state}"


def _segment_avg_ret3(segment: dict[str, object]) -> float | None:
    nested_stats = segment.get("ret3")
    if isinstance(nested_stats, dict):
        nested_avg = _coerce_finite_float(nested_stats.get("avg"))
        if nested_avg is not None:
            return nested_avg
    return _coerce_finite_float(segment.get("avg_ret3_pct"))


def _is_layering_direction_correct(segments: list[dict[str, object]]) -> bool:
    verdict_avgs = {
        str(segment.get("segment_value") or "").upper(): _segment_avg_ret3(segment)
        for segment in segments
        if segment.get("segment_type") == "verdict"
    }
    pass_avg = verdict_avgs.get("PASS")
    watch_avg = verdict_avgs.get("WATCH")
    fail_avg = verdict_avgs.get("FAIL")
    if pass_avg is None or watch_avg is None or fail_avg is None:
        return False
    return pass_avg > watch_avg and watch_avg >= fail_avg


def _find_metric(
    group: dict[str, object],
    *,
    score_field: str,
    target_field: str = "ret3_pct",
) -> dict[str, object] | None:
    for metric in group.get("metrics", []):
        if metric.get("score_field") == score_field and metric.get("target_field") == target_field:
            return metric
    return None


def _metric_signal(metric: dict[str, object] | None) -> float | None:
    if metric is None:
        return None
    pearson = _coerce_finite_float(metric.get("pearson_r"))
    if pearson is not None:
        return pearson
    return _coerce_finite_float(metric.get("spearman_r"))


def _scope_segments(segments: list[dict[str, object]], group: dict[str, object]) -> list[dict[str, object]]:
    group_key = group.get("group_key")
    if group_key is None:
        return []
    return [segment for segment in segments if segment.get("group_key") == group_key]


def classify_scope_decision(
    group: dict[str, object],
    segments: list[dict[str, object]],
) -> RecommendationDecision | None:
    total_score_metric = _find_metric(group, score_field="total_score")
    total_signal = _metric_signal(total_score_metric)
    layering_ok = _is_layering_direction_correct(segments)

    if total_signal is not None and total_signal < 0 and not layering_ok:
        method = _normalize_category_value(group.get("method")) or "default"
        environment_state = _normalize_category_value(group.get("environment_state")) or "unknown"
        return RecommendationDecision(
            action_type="reviewer_rework",
            reason="total_score correlation is negative and PASS/WATCH/FAIL layering is broken",
            target_files=[f"src/stock_select/reviewers/{method}.py"],
            next_tasks=[
                f"review {method} scoring logic for {environment_state} environment samples",
                "trace which core subscores are inverting expected return ordering",
            ],
            success_criteria=[
                "total_score correlation returns to non-negative territory",
                "PASS avg ret3_pct is above WATCH and FAIL after rerun",
            ],
        )

    if total_signal is not None and total_signal >= 0 and layering_ok:
        subscore_signals = [
            _metric_signal(metric)
            for metric in group.get("metrics", [])
            if metric.get("target_field") == "ret3_pct" and metric.get("score_field") != "total_score"
        ]
        has_inconsistent_subscore = any(signal is not None and signal < 0 for signal in subscore_signals)
        environment_state = _normalize_category_value(group.get("environment_state")) or "unknown"
        if total_signal < 0.05 and has_inconsistent_subscore:
            return RecommendationDecision(
                action_type="weights_and_thresholds",
                reason="total_score correlation is non-negative but weak, with inconsistent subscore directions",
                target_files=["src/stock_select/environment_profiles.py"],
                next_tasks=[
                    f"rebalance subscore weights for {environment_state} environment",
                    "revisit PASS/WATCH/FAIL thresholds after weight changes",
                ],
                success_criteria=[
                    "total_score ret3 correlation strengthens after profile update",
                    "subscore directions are aligned with expected return ordering",
                ],
            )
        return RecommendationDecision(
            action_type="threshold_only",
            reason="total_score correlation is non-negative and PASS/WATCH/FAIL layering is directionally correct",
            target_files=["src/stock_select/environment_profiles.py"],
            next_tasks=[
                f"adjust verdict thresholds for {environment_state} environment",
                "rerun diagnostics to confirm wider PASS/WATCH/FAIL separation",
            ],
            success_criteria=[
                "PASS avg ret3_pct stays above WATCH and FAIL",
                "verdict layers show clearer return separation after threshold tuning",
            ],
        )

    return None


def build_recommendations(
    correlations: dict[str, list[dict[str, object]]],
    segments: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    recommendations: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []

    for group in correlations.get("groups", []):
        if group.get("scope_type") != "method_environment_state":
            continue

        sample_count = int(group.get("sample_count") or 0)
        if sample_count < 10 or group.get("conclusion_strength") == "insufficient":
            excluded.append(
                {
                    "scope": _format_scope_label(group),
                    "group_key": group.get("group_key"),
                    "reason": "insufficient_samples",
                    "sample_count": sample_count,
                }
            )
            continue

        scoped_segments = _scope_segments(segments, group)
        decision = classify_scope_decision(group, scoped_segments)
        if decision is None:
            excluded.append(
                {
                    "scope": _format_scope_label(group),
                    "group_key": group.get("group_key"),
                    "reason": "no_clear_recommendation",
                    "sample_count": sample_count,
                }
            )
            continue

        recommendations.append(
            {
                "scope": _format_scope_label(group),
                "group_key": group.get("group_key"),
                "action_type": decision.action_type,
                "reason": decision.reason,
                "target_files": decision.target_files,
                "next_tasks": decision.next_tasks,
                "success_criteria": decision.success_criteria,
            }
        )

    return {"recommendations": recommendations, "excluded": excluded}


def render_recommendation_summary(payload: dict[str, list[dict[str, object]]]) -> str:
    lines = ["# Review Tuning Recommendations", ""]

    recommendations = payload.get("recommendations", [])
    if recommendations:
        lines.append("## Recommendations")
        for item in recommendations:
            lines.append(f"- {item['scope']}: `{item['action_type']}`")
            lines.append(f"  reason: {item['reason']}")
            lines.append(f"  target_files: {', '.join(item.get('target_files', []))}")
            lines.append(f"  next_tasks: {', '.join(item.get('next_tasks', []))}")
            lines.append(f"  success_criteria: {', '.join(item.get('success_criteria', []))}")
    else:
        lines.append("## Recommendations")
        lines.append("- none")

    excluded = payload.get("excluded", [])
    if excluded:
        lines.append("")
        lines.append("## Excluded")
        for item in excluded:
            lines.append(f"- {item['scope']}: {item['reason']}")

    return "\n".join(lines) + "\n"


def attach_environment_state(
    rows: list[dict[str, object]],
    environment_history: list[dict[str, object]],
    *,
    environment_key: str,
) -> list[dict[str, object]]:
    tagged: list[dict[str, object]] = []
    for row in rows:
        pick_date = str(row["pick_date"])
        applicable = [
            item
            for item in environment_history
            if str(item["start_date"]) <= pick_date
            and (item.get("end_date") is None or pick_date <= str(item["end_date"]))
        ]
        preferred = [item for item in applicable if bool(item.get("manual_override"))]
        ranked = preferred or applicable
        matched = (
            max(
                ranked,
                key=lambda item: (
                    str(item["start_date"]),
                    str(item.get("evaluated_at") or item["start_date"]),
                    bool(item.get("manual_override")),
                ),
            )
            if ranked
            else None
        )
        tagged.append(
            {
                **row,
                "environment_state": (
                    str(matched.get(environment_key) or matched.get("state")).lower()
                    if matched is not None
                    else "unknown"
                ),
            }
        )
    return tagged


def collect_review_samples(
    *,
    methods: list[str],
    start_date: str,
    end_date: str,
    runtime_root: Path,
    prepared_root: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for method in methods:
        normalized_method = method.strip().lower()
        prepared = _load_prepared(normalized_method, prepared_root, end_date=end_date)
        reviews_root = runtime_root / "reviews"
        for review_dir in sorted(reviews_root.glob(f"????-??-??.{normalized_method}")):
            pick_date = review_dir.name.replace(f".{normalized_method}", "")
            if pick_date < start_date or pick_date > end_date:
                continue

            summary_path = review_dir / "summary.json"
            if not summary_path.exists():
                continue

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            items = summary.get("recommendations", []) + summary.get("excluded", [])
            summary_pick_date = str(summary.get("pick_date", pick_date))
            for item in items:
                code = str(item["code"])
                fwd = _get_forward_returns(prepared, code=code, pick_date=summary_pick_date)
                row = {
                    "method": normalized_method,
                    "pick_date": summary_pick_date,
                    "code": code,
                    "total_score": float(item["total_score"]),
                    "verdict": _get_verdict(item),
                    "ret3_pct": None if fwd is None else fwd.get("ret3_pct"),
                    "ret5_pct": None if fwd is None else fwd.get("ret5_pct"),
                }
                for field in SCORE_FIELDS:
                    row[field] = _get_score(item, field)
                rows.append(
                    row
                )

    return rows
