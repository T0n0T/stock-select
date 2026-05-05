from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import pandas as pd

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

    methods = sorted({str(row.get("method")) for row in rows if row.get("method") is not None})
    for method in methods:
        scoped_rows = [row for row in rows if row.get("method") == method]
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
        {str(row.get("environment_state")) for row in rows if row.get("environment_state") is not None}
    )
    for environment_state in environment_states:
        scoped_rows = [row for row in rows if row.get("environment_state") == environment_state]
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
            (str(row.get("method")), str(row.get("environment_state")))
            for row in rows
            if row.get("method") is not None and row.get("environment_state") is not None
        }
    )
    for method, environment_state in method_environment_pairs:
        scoped_rows = [
            row
            for row in rows
            if row.get("method") == method and row.get("environment_state") == environment_state
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
    groups: list[dict[str, object]] = []
    for scope, scoped_rows in iter_scoped_rows(rows):
        metrics: list[dict[str, object]] = []
        for score_field in CORRELATION_SCORE_FIELDS:
            for target_field in RETURN_FIELDS:
                metrics.append(
                    {
                        "score_field": score_field,
                        "target_field": target_field,
                        "pair_count": len(_finite_pairs(scoped_rows, score_field, target_field)),
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
    rounded = int(round(numeric_value))
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
        for segment_value in sorted(grouped)
    ]


def build_verdict_segments(
    rows: list[dict[str, object]],
    *,
    scope: dict[str, object],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        verdict = str(row.get("verdict") or "").upper()
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
        segments.extend(build_score_bucket_segments(scoped_rows, scope=scope, field="price_position"))
        segments.extend(build_score_bucket_segments(scoped_rows, scope=scope, field="macd_phase"))
        segments.extend(build_total_score_band_segments(scoped_rows, scope=scope))
        segments.extend(build_verdict_segments(scoped_rows, scope=scope))
    return segments


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
