# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "lightgbm",
#   "numpy",
# ]
# ///
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ml import build_rank_dataset as rank_dataset_schema


DEFAULT_METHOD = "b2"
DEFAULT_LABEL_GAIN = [0, 1, 3, 7]
DEFAULT_RF_N_ESTIMATORS = 300
DEFAULT_RF_MIN_SAMPLES_LEAF = 20
DEFAULT_RF_MAX_FEATURES = "sqrt"
LOW_IMPORTANCE_THRESHOLD = 1e-6

IDENTITY_COLUMNS = {"date", "code", "name", "method"}
LABEL_COLUMNS = {
    "ret3",
    "ret5",
    "ret10",
    "max_drawdown_5d",
    "win3_vs_day_median",
    "win5_vs_day_median",
    "rank_label_3d",
    "rank_label_5d",
}
NON_FEATURE_COLUMNS = {
    "model_score",
    "model_rank",
    "llm_action",
    "risk_flags",
}
CATEGORICAL_COLUMNS = {
    "env",
    "signal",
    "signal_type",
    "daily_macd_phase_type",
    "daily_macd_wave_stage",
    "weekly_macd_phase_type",
    "weekly_macd_wave_stage",
    "weekly_daily_combo_type",
    "midline_state",
}
SIGNAL_CATEGORICAL_COLUMNS = {"env", "signal", "signal_type"}
MACD_CATEGORICAL_COLUMNS = {
    "daily_macd_phase_type",
    "daily_macd_wave_stage",
    "weekly_macd_phase_type",
    "weekly_macd_wave_stage",
    "weekly_daily_combo_type",
}
CONTEXT_CATEGORICAL_COLUMNS = {"midline_state"}
RAW_NUMERIC_COLUMNS = set(rank_dataset_schema.raw_factor_columns_for_method(DEFAULT_METHOD))
LEGACY_CONTEXT_NUMERIC_COLUMNS = {
    "price_vs_90d_high",
    "price_vs_90d_low",
    "price_vs_90d_mid",
}
FEATURE_SETS = {"raw_numeric", "raw_plus_signal", "raw_plus_signal_macd", "all"}
TRAIN_MODES = {"overall", "by_env"}
TRAIN_LABEL_COLUMNS = {"rank_label_3d", "rank_label_5d", "ret3_ge5_label", "ret5_ge5_label"}


@dataclass
class TrainedModelResult:
    train_scored: list[dict[str, Any]]
    test_scored: list[dict[str, Any]]
    top_features: list[dict[str, Any]]
    feature_count: int
    model: Any
    feature_names: list[str]
    lightgbm_feature_names: list[str]
    category_levels: dict[str, list[str]]


@dataclass
class RandomForestDiagnosticsConfig:
    enabled: bool = True
    n_estimators: int = DEFAULT_RF_N_ESTIMATORS
    max_depth: int | None = None
    min_samples_leaf: int = DEFAULT_RF_MIN_SAMPLES_LEAF
    max_features: str | int | float | None = DEFAULT_RF_MAX_FEATURES
    min_oob_score: float | None = None
    min_test_rank_ic_ret3: float | None = None


class RandomForestThresholdError(ValueError):
    pass


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def pct(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100.0, 1) if denominator else None


def read_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def walk_forward_split_dates(dates: Sequence[str], *, test_ratio: float) -> tuple[list[str], list[str]]:
    ordered = sorted(set(str(date) for date in dates))
    if len(ordered) < 2:
        return ordered, []
    test_count = max(1, int(round(len(ordered) * test_ratio)))
    test_count = min(test_count, len(ordered) - 1)
    return ordered[:-test_count], ordered[-test_count:]


def rolling_walk_forward_splits(
    dates: Sequence[str],
    *,
    train_date_count: int,
    test_date_count: int,
    fold_count: int,
) -> list[tuple[list[str], list[str]]]:
    ordered = sorted(set(str(date) for date in dates))
    if train_date_count <= 0 or test_date_count <= 0 or fold_count <= 0:
        raise ValueError("rolling train/test/fold counts must be positive")
    window = train_date_count + test_date_count
    if len(ordered) < window:
        raise ValueError("not enough dates for rolling walk-forward split")
    max_start = len(ordered) - window
    if fold_count == 1:
        starts = [max_start]
    else:
        starts = [round(index * max_start / (fold_count - 1)) for index in range(fold_count)]
    result = []
    seen: set[int] = set()
    for start in starts:
        if start in seen:
            continue
        seen.add(start)
        train_dates = ordered[start : start + train_date_count]
        test_dates = ordered[start + train_date_count : start + window]
        result.append((train_dates, test_dates))
    return result


def raw_numeric_columns_for_method(method: str = DEFAULT_METHOD) -> set[str]:
    return set(rank_dataset_schema.raw_factor_columns_for_method(method))


def select_feature_columns(
    columns: Sequence[str],
    *,
    feature_set: str = "all",
    method: str = DEFAULT_METHOD,
) -> tuple[list[str], list[str]]:
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"unsupported feature_set: {feature_set}")
    numeric: list[str] = []
    categorical: list[str] = []
    raw_numeric_columns = raw_numeric_columns_for_method(method) | LEGACY_CONTEXT_NUMERIC_COLUMNS
    if feature_set == "raw_numeric":
        allowed_categorical: set[str] = set()
    elif feature_set == "raw_plus_signal":
        allowed_categorical = SIGNAL_CATEGORICAL_COLUMNS
    elif feature_set == "raw_plus_signal_macd":
        allowed_categorical = (
            SIGNAL_CATEGORICAL_COLUMNS | MACD_CATEGORICAL_COLUMNS | CONTEXT_CATEGORICAL_COLUMNS
        )
    else:
        allowed_categorical = CATEGORICAL_COLUMNS
    excluded = IDENTITY_COLUMNS | LABEL_COLUMNS | NON_FEATURE_COLUMNS
    for column in columns:
        if column in excluded:
            continue
        if column in allowed_categorical:
            categorical.append(column)
        elif column in raw_numeric_columns or column in LEGACY_CONTEXT_NUMERIC_COLUMNS:
            numeric.append(column)
    return numeric, categorical


def load_feature_manifest_with_levels(
    path: Path,
    *,
    available_columns: set[str],
    method: str = DEFAULT_METHOD,
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature manifest must be a JSON object")
    excluded = set(payload.get("excluded_features") or []) | IDENTITY_COLUMNS | LABEL_COLUMNS | NON_FEATURE_COLUMNS
    raw_numeric_columns = raw_numeric_columns_for_method(method) | LEGACY_CONTEXT_NUMERIC_COLUMNS

    def clean(values: Any, *, allowed_columns: set[str]) -> list[str]:
        if not isinstance(values, list):
            return []
        result = []
        for value in values:
            column = str(value)
            if (
                column in allowed_columns
                and column in available_columns
                and column not in excluded
                and column not in result
            ):
                result.append(column)
        return result

    numeric = clean(payload.get("numeric_features"), allowed_columns=raw_numeric_columns)
    categorical = clean(payload.get("categorical_features"), allowed_columns=CATEGORICAL_COLUMNS)
    fixed_levels: dict[str, list[str]] = {}
    raw_levels = payload.get("categorical_levels")
    if isinstance(raw_levels, dict):
        for column in categorical:
            values = raw_levels.get(column)
            if not isinstance(values, list):
                continue
            cleaned_values = []
            for value in values:
                level = str(value)
                if level not in cleaned_values:
                    cleaned_values.append(level)
            if cleaned_values:
                fixed_levels[column] = cleaned_values
    return numeric, categorical, fixed_levels


def load_feature_manifest(
    path: Path,
    *,
    available_columns: set[str],
    method: str = DEFAULT_METHOD,
) -> tuple[list[str], list[str]]:
    numeric, categorical, _fixed_levels = load_feature_manifest_with_levels(
        path,
        available_columns=available_columns,
        method=method,
    )
    return numeric, categorical


def category_levels(
    rows: Sequence[dict[str, Any]],
    categorical_columns: Sequence[str],
    *,
    max_levels: int = 32,
    fixed_categorical_levels: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    levels: dict[str, list[str]] = {}
    for column in categorical_columns:
        if fixed_categorical_levels and column in fixed_categorical_levels:
            levels[column] = list(fixed_categorical_levels[column])
            continue
        counts = Counter(str(row.get(column) or "unknown") for row in rows)
        levels[column] = [value for value, _count in counts.most_common(max_levels)]
    return levels


def build_feature_matrix(
    rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    levels: dict[str, list[str]] | None = None,
) -> tuple[list[list[float]], list[str]]:
    levels = levels or category_levels(rows, categorical_columns)
    feature_names = list(numeric_columns)
    for column in categorical_columns:
        feature_names.extend(f"{column}={value}" for value in levels.get(column, []))

    matrix: list[list[float]] = []
    for row in rows:
        values = [as_float(row.get(column)) or 0.0 for column in numeric_columns]
        for column in categorical_columns:
            current = str(row.get(column) or "unknown")
            values.extend(1.0 if current == value else 0.0 for value in levels.get(column, []))
        matrix.append(values)
    return matrix, feature_names


def build_feature_matrix_from_metadata(
    rows: Sequence[dict[str, Any]],
    metadata: dict[str, Any],
) -> tuple[list[list[float]], list[str]]:
    numeric_columns = [str(value) for value in metadata.get("numeric_columns") or []]
    categorical_columns = [str(value) for value in metadata.get("categorical_columns") or []]
    levels = {
        str(column): [str(value) for value in values]
        for column, values in (metadata.get("categorical_levels") or {}).items()
        if isinstance(values, list)
    }
    return build_feature_matrix(
        rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
    )


def build_model_metadata(
    *,
    feature_manifest: str | None,
    train_rows: Sequence[dict[str, Any]],
    score_rows: Sequence[dict[str, Any]],
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    levels: dict[str, list[str]],
    feature_names: Sequence[str],
    lightgbm_feature_names: Sequence[str],
    label_column: str,
    model_params: dict[str, Any],
) -> dict[str, Any]:
    train_dates = sorted({str(row.get("date")) for row in train_rows})
    score_dates = sorted({str(row.get("date")) for row in score_rows})
    return {
        "feature_manifest": feature_manifest,
        "train_start": train_dates[0] if train_dates else None,
        "train_end": train_dates[-1] if train_dates else None,
        "score_start": score_dates[0] if score_dates else None,
        "score_end": score_dates[-1] if score_dates else None,
        "model_params": model_params,
        "numeric_columns": list(numeric_columns),
        "categorical_columns": list(categorical_columns),
        "feature_names": list(feature_names),
        "lightgbm_feature_names": list(lightgbm_feature_names),
        "categorical_levels": {column: list(values) for column, values in levels.items()},
        "one_hot_levels": {column: [f"{column}={value}" for value in values] for column, values in levels.items()},
        "label_column": label_column,
    }


def write_model_artifacts(model: Any, metadata: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.txt"
    metadata_path = output_dir / "model_metadata.json"
    model.save_model(str(model_path))
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"model": str(model_path), "metadata": str(metadata_path)}


def write_feature_manifest(
    output_dir: Path,
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    fixed_categorical_levels: dict[str, list[str]],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "feature_manifest.json"
    payload = {
        "numeric_features": list(numeric_columns),
        "categorical_features": list(categorical_columns),
        "categorical_levels": {column: list(values) for column, values in fixed_categorical_levels.items()},
        "excluded_features": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def safe_feature_names(feature_names: Sequence[str]) -> list[str]:
    result = []
    seen: dict[str, int] = defaultdict(int)
    for index, name in enumerate(feature_names):
        safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
        safe = safe.strip("_") or f"feature_{index}"
        seen[safe] += 1
        if seen[safe] > 1:
            safe = f"{safe}_{seen[safe]}"
        result.append(safe)
    return result


def label_value(row: dict[str, Any], *, label_column: str) -> int | None:
    if label_column == "ret3_ge5_label":
        ret3 = as_float(row.get("ret3"))
        if ret3 is None:
            return None
        return 3 if ret3 >= 5.0 else 0
    if label_column == "ret5_ge5_label":
        ret5 = as_float(row.get("ret5"))
        if ret5 is None:
            return None
        return 3 if ret5 >= 5.0 else 0
    value = as_float(row.get(label_column))
    return None if value is None else int(value)


def rows_for_dates(rows: Sequence[dict[str, Any]], dates: set[str], *, label_column: str = "rank_label_3d") -> list[dict[str, Any]]:
    filtered = [row for row in rows if str(row.get("date")) in dates and label_value(row, label_column=label_column) is not None]
    return sorted(filtered, key=lambda row: (str(row.get("date")), str(row.get("code"))))


def average_metric_dicts(metrics: Sequence[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted({key for item in metrics for key in item.keys()})
    result: dict[str, Any] = {}
    for key in keys:
        values = [as_float(item.get(key)) for item in metrics]
        valid = [value for value in values if value is not None]
        result[key] = round(sum(valid) / len(valid), 4) if valid else None
    return result


def group_sizes_by_date(rows: Sequence[dict[str, Any]]) -> list[int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("date"))] += 1
    return [counts[date] for date in sorted(counts)]


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


def labels(rows: Sequence[dict[str, Any]], *, label_column: str) -> list[int]:
    return [int(label_value(row, label_column=label_column) or 0) for row in rows]


def assign_scores(rows: Sequence[dict[str, Any]], scores: Sequence[float]) -> list[dict[str, Any]]:
    output = []
    for row, score in zip(rows, scores):
        item = dict(row)
        item["model_score"] = float(score)
        output.append(item)
    return output


def random_forest_n_jobs(num_threads: int) -> int | None:
    return num_threads if num_threads > 0 else None


def random_forest_probability_scores(
    model: Any,
    probabilities: Sequence[Sequence[float]],
    label_gain: Sequence[int],
) -> list[float]:
    classes = [int(value) for value in getattr(model, "classes_", [])]
    if not classes:
        return []
    scores: list[float] = []
    for row in probabilities:
        total = 0.0
        for class_value, probability in zip(classes, row):
            gain = label_gain[class_value] if 0 <= class_value < len(label_gain) else float(class_value)
            total += float(probability) * float(gain)
        scores.append(total)
    return scores


def random_forest_fallback_scores(model: Any, matrix: Sequence[Sequence[float]]) -> list[float]:
    return [float(value) for value in model.predict(matrix)]


def run_random_forest_diagnostics(
    train_rows: Sequence[dict[str, Any]],
    test_rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    label_column: str,
    label_gain: Sequence[int],
    num_threads: int,
    fixed_categorical_levels: dict[str, list[str]],
    config: RandomForestDiagnosticsConfig,
) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestClassifier

    levels = category_levels(
        train_rows,
        categorical_columns,
        fixed_categorical_levels=fixed_categorical_levels,
    )
    train_matrix, feature_names = build_feature_matrix(
        train_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
    )
    test_matrix, _feature_names = build_feature_matrix(
        test_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
    )
    model = RandomForestClassifier(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        min_samples_leaf=config.min_samples_leaf,
        max_features=config.max_features,
        random_state=17,
        bootstrap=True,
        oob_score=True,
        n_jobs=random_forest_n_jobs(num_threads),
    )
    train_labels = labels(train_rows, label_column=label_column)
    test_labels = labels(test_rows, label_column=label_column)
    model.fit(train_matrix, train_labels)

    try:
        train_scores = random_forest_probability_scores(model, model.predict_proba(train_matrix), label_gain)
        test_scores = random_forest_probability_scores(model, model.predict_proba(test_matrix), label_gain)
    except Exception:
        train_scores = random_forest_fallback_scores(model, train_matrix)
        test_scores = random_forest_fallback_scores(model, test_matrix)

    if len(train_scores) != len(train_rows):
        train_scores = random_forest_fallback_scores(model, train_matrix)
    if len(test_scores) != len(test_rows):
        test_scores = random_forest_fallback_scores(model, test_matrix)

    importances = [float(value) for value in getattr(model, "feature_importances_", [])]
    ranked_features = sorted(zip(feature_names, importances), key=lambda item: (-item[1], item[0]))
    low_features = sorted(
        (
            (feature, importance)
            for feature, importance in zip(feature_names, importances)
            if importance <= LOW_IMPORTANCE_THRESHOLD
        ),
        key=lambda item: (item[1], item[0]),
    )

    return {
        "enabled": True,
        "status": "passed",
        "label_column": label_column,
        "feature_count": len(feature_names),
        "numeric_feature_count": len(numeric_columns),
        "categorical_feature_count": len(categorical_columns),
        "params": {
            "n_estimators": config.n_estimators,
            "max_depth": config.max_depth,
            "min_samples_leaf": config.min_samples_leaf,
            "max_features": config.max_features,
            "random_state": 17,
            "bootstrap": True,
            "oob_score": True,
            "n_jobs": random_forest_n_jobs(num_threads),
        },
        "thresholds": {
            "min_oob_score": config.min_oob_score,
            "min_test_rank_ic_ret3": config.min_test_rank_ic_ret3,
        },
        "metrics": {
            "train": evaluate_model(assign_scores(train_rows, train_scores), top_n=3),
            "test": evaluate_model(assign_scores(test_rows, test_scores), top_n=3),
        },
        "oob_score": getattr(model, "oob_score_", None),
        "accuracy": {
            "train": float(model.score(train_matrix, train_labels)),
            "test": float(model.score(test_matrix, test_labels)),
        },
        "top_features": [
            {"feature": feature, "importance": round(importance, 8)} for feature, importance in ranked_features[:50]
        ],
        "low_importance_features": [
            {"feature": feature, "importance": round(importance, 8)} for feature, importance in low_features
        ],
        "output_paths": {},
    }


def grouped_by_date(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("date"))].append(row)
    return grouped


def evaluate_model(rows: Sequence[dict[str, Any]], *, top_n: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    ordered_by_date = grouped_by_date(rows)
    for return_column in ("ret3", "ret5"):
        positive = ge5 = le0 = total = captured_ge5 = total_ge5 = 0
        ic_values: list[float] = []
        for _date, day_rows in ordered_by_date.items():
            ordered = sorted(day_rows, key=lambda row: (-(as_float(row.get("model_score")) or 0.0), str(row.get("code"))))
            top_rows = ordered[:top_n]
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
        prefix = f"top{top_n}_{return_column}"
        result.update(
            {
                f"{prefix}_positive_rate": pct(positive, total),
                f"{prefix}_ge_5_rate": pct(ge5, total),
                f"{prefix}_le_0_rate": pct(le0, total),
                f"{prefix}_ge_5_capture_rate": pct(captured_ge5, total_ge5),
                f"rank_ic_{return_column}": round(sum(ic_values) / len(ic_values), 4) if ic_values else None,
            }
        )
    return result


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


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# {report.get('method', DEFAULT_METHOD)} LightGBM rank report",
        "",
        f"dataset: `{report['dataset']}`",
        f"train dates: `{report['train_date_count']}`",
        f"test dates: `{report['test_date_count']}`",
        f"features: `{report['feature_count']}`",
        "",
        "| split | top3 positive | top3 >=5 | top3 <=0 | top3 >=5 capture | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split in ["train", "test"]:
        metrics = report["metrics"][split]
        lines.append(
            "| {split} | {pos} | {ge5} | {le0} | {capture_ret3} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                split=split,
                pos=metrics.get("top3_ret3_positive_rate"),
                ge5=metrics.get("top3_ret3_ge_5_rate"),
                le0=metrics.get("top3_ret3_le_0_rate"),
                capture_ret3=metrics.get("top3_ret3_ge_5_capture_rate"),
                ic_ret3=metrics.get("rank_ic_ret3"),
                ge5_ret5=metrics.get("top3_ret5_ge_5_rate"),
                ic_ret5=metrics.get("rank_ic_ret5"),
            )
        )
    lines.extend(["", "## top features", ""])
    lines.extend(f"- {item['feature']}: {item['importance']}" for item in report.get("top_features", [])[:20])
    rf_summary = report.get("rf_diagnostics") or {}
    if rf_summary:
        rf_metrics = ((rf_summary.get("metrics") or {}).get("test") or {})
        lines.extend(
            [
                "",
                "## random forest factor diagnostics",
                "",
                f"- status: {rf_summary.get('status')}",
                f"- oob_score: {rf_summary.get('oob_score')}",
                f"- test rank_ic_ret3: {rf_metrics.get('rank_ic_ret3')}",
                f"- low importance features: {rf_summary.get('low_importance_feature_count')}",
            ]
        )
        lines.extend(
            f"- {item['feature']}: {item['importance']}" for item in list(rf_summary.get("top_features") or [])[:20]
        )
    if report.get("rolling_folds"):
        summary = report.get("rolling_summary") or {}
        test_avg = summary.get("test_avg") or {}
        if test_avg:
            lines.extend(
                [
                    "",
                    "## rolling summary",
                    "",
                    "| scope | top3 positive | top3 >=5 | top3 <=0 | top3 >=5 capture | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|",
                    "| model avg | {pos} | {ge5} | {le0} | {capture} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                        pos=test_avg.get("top3_ret3_positive_rate"),
                        ge5=test_avg.get("top3_ret3_ge_5_rate"),
                        le0=test_avg.get("top3_ret3_le_0_rate"),
                        capture=test_avg.get("top3_ret3_ge_5_capture_rate"),
                        ic_ret3=test_avg.get("rank_ic_ret3"),
                        ge5_ret5=test_avg.get("top3_ret5_ge_5_rate"),
                        ic_ret5=test_avg.get("rank_ic_ret5"),
                    ),
                ]
                )
        lines.extend(["", "## rolling folds", ""])
        lines.extend(
            [
                "| fold | train dates | test dates | top3 positive | top3 >=5 | top3 <=0 | top3 >=5 capture | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |",
                "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for fold in report["rolling_folds"]:
            metrics = fold["metrics"]["test"]
            lines.append(
                "| {fold} | {train_start}..{train_end} | {test_start}..{test_end} | {pos} | {ge5} | {le0} | {capture} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                    fold=fold["fold"],
                    train_start=fold["train_start_date"],
                    train_end=fold["train_end_date"],
                    test_start=fold["test_start_date"],
                    test_end=fold["test_end_date"],
                    pos=metrics.get("top3_ret3_positive_rate"),
                    ge5=metrics.get("top3_ret3_ge_5_rate"),
                    le0=metrics.get("top3_ret3_le_0_rate"),
                    capture=metrics.get("top3_ret3_ge_5_capture_rate"),
                    ic_ret3=metrics.get("rank_ic_ret3"),
                    ge5_ret5=metrics.get("top3_ret5_ge_5_rate"),
                    ic_ret5=metrics.get("rank_ic_ret5"),
                )
            )
        if any(fold.get("by_env") for fold in report["rolling_folds"]):
            lines.extend(["", "### rolling fold by-env", "", "| fold | env | rows | top3 >=5 | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |", "|---|---:|---:|---:|---:|---:|---:|"])
            for fold in report["rolling_folds"]:
                for env, diag in sorted((fold.get("by_env") or {}).items()):
                    m = diag.get("metrics") or {}
                    lines.append(
                        "| {fold} | {env} | {rows} | {ge5} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                            fold=fold["fold"],
                            env=env,
                            rows=diag.get("row_count"),
                            ge5=m.get("top3_ret3_ge_5_rate"),
                            ic_ret3=m.get("rank_ic_ret3"),
                            ge5_ret5=m.get("top3_ret5_ge_5_rate"),
                            ic_ret5=m.get("rank_ic_ret5"),
                        )
                    )
        if any(fold.get("by_month") for fold in report["rolling_folds"]):
            lines.extend(["", "### rolling fold by-month", "", "| fold | month | rows | top3 >=5 | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |", "|---|---:|---:|---:|---:|---:|---:|"])
            for fold in report["rolling_folds"]:
                for month, diag in sorted((fold.get("by_month") or {}).items()):
                    m = diag.get("metrics") or {}
                    lines.append(
                        "| {fold} | {month} | {rows} | {ge5} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                            fold=fold["fold"],
                            month=month,
                            rows=diag.get("row_count"),
                            ge5=m.get("top3_ret3_ge_5_rate"),
                            ic_ret3=m.get("rank_ic_ret3"),
                            ge5_ret5=m.get("top3_ret5_ge_5_rate"),
                            ic_ret5=m.get("rank_ic_ret5"),
                        )
                    )
    return "\n".join(lines) + "\n"


def report_paths(
    output_dir: Path,
    feature_set: str,
    train_mode: str = "overall",
    label_column: str = "rank_label_3d",
) -> tuple[Path, Path]:
    suffix = "" if feature_set == "all" else f"_{feature_set}"
    if train_mode != "overall":
        suffix = f"{suffix}_{train_mode}"
    if label_column != "rank_label_3d":
        suffix = f"{suffix}_{label_column}"
    return output_dir / f"lgbm_rank_report{suffix}.json", output_dir / f"lgbm_rank_report{suffix}.md"


def rf_diagnostic_paths(output_dir: Path) -> tuple[Path, Path]:
    return output_dir / "rf_feature_diagnostics.json", output_dir / "rf_feature_diagnostics.md"


def rf_diagnostics_summary(diagnostics: dict[str, Any], json_path: Path | None = None) -> dict[str, Any]:
    return {
        "enabled": bool(diagnostics.get("enabled")),
        "path": str(json_path) if json_path is not None else None,
        "status": diagnostics.get("status"),
        "oob_score": diagnostics.get("oob_score"),
        "metrics": {"test": (diagnostics.get("metrics") or {}).get("test") or {}},
        "top_features": list(diagnostics.get("top_features") or [])[:20],
        "low_importance_feature_count": len(diagnostics.get("low_importance_features") or []),
    }


def markdown_rf_diagnostics(diagnostics: dict[str, Any]) -> str:
    metrics = ((diagnostics.get("metrics") or {}).get("test") or {})
    lines = [
        "# random forest factor diagnostics",
        "",
        f"status: `{diagnostics.get('status')}`",
        f"label: `{diagnostics.get('label_column')}`",
        f"features: `{diagnostics.get('feature_count')}`",
        f"oob_score: `{diagnostics.get('oob_score')}`",
        f"test rank_ic_ret3: `{metrics.get('rank_ic_ret3')}`",
        f"test top3_ret3_positive_rate: `{metrics.get('top3_ret3_positive_rate')}`",
        "",
        "## top features",
        "",
    ]
    lines.extend(f"- {item['feature']}: {item['importance']}" for item in list(diagnostics.get("top_features") or [])[:20])
    return "\n".join(lines) + "\n"


def write_rf_diagnostics_artifacts(
    diagnostics: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, Any], Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = rf_diagnostic_paths(output_dir)
    payload = dict(diagnostics)
    payload["output_paths"] = {"json": str(json_path), "markdown": str(markdown_path)}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_rf_diagnostics(payload), encoding="utf-8")
    return payload, json_path, markdown_path


def parse_label_gain(value: str) -> list[int]:
    try:
        gains = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("label gain must be comma-separated integers") from exc
    if not gains:
        raise argparse.ArgumentTypeError("label gain must contain at least one integer")
    return gains


def resolve_dataset_path(dataset: Path | None, *, method: str) -> Path:
    return dataset or PROJECT_ROOT / "diagnostics" / "ml" / method / "rank_dataset.csv"


def resolve_output_dir(output_dir: Path | None, *, method: str) -> Path:
    return output_dir or PROJECT_ROOT / "diagnostics" / "ml" / method / "model"


def train_model(
    train_rows: Sequence[dict[str, Any]],
    test_rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    num_leaves: int,
    min_data_in_leaf: int,
    num_boost_round: int,
    learning_rate: float,
    label_column: str,
    num_threads: int,
    label_gain: Sequence[int] | None = None,
    lambdarank_truncation_level: int = 0,
    fixed_categorical_levels: dict[str, list[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    result = train_model_result(
        train_rows,
        test_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        num_leaves=num_leaves,
        min_data_in_leaf=min_data_in_leaf,
        num_boost_round=num_boost_round,
        learning_rate=learning_rate,
        label_column=label_column,
        num_threads=num_threads,
        label_gain=label_gain,
        lambdarank_truncation_level=lambdarank_truncation_level,
        fixed_categorical_levels=fixed_categorical_levels,
    )
    return result.train_scored, result.test_scored, result.top_features, result.feature_count


def train_model_result(
    train_rows: Sequence[dict[str, Any]],
    test_rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    num_leaves: int,
    min_data_in_leaf: int,
    num_boost_round: int,
    learning_rate: float,
    label_column: str,
    num_threads: int,
    label_gain: Sequence[int] | None = None,
    lambdarank_truncation_level: int = 0,
    fixed_categorical_levels: dict[str, list[str]] | None = None,
) -> TrainedModelResult:
    import lightgbm as lgb
    import numpy as np

    if not train_rows or not test_rows:
        return TrainedModelResult([], [], [], 0, None, [], [], {})
    resolved_label_gain = list(label_gain or DEFAULT_LABEL_GAIN)
    levels = category_levels(
        train_rows,
        categorical_columns,
        fixed_categorical_levels=fixed_categorical_levels,
    )
    train_matrix, feature_names = build_feature_matrix(train_rows, numeric_columns=numeric_columns, categorical_columns=categorical_columns, levels=levels)
    test_matrix, _feature_names = build_feature_matrix(test_rows, numeric_columns=numeric_columns, categorical_columns=categorical_columns, levels=levels)
    lightgbm_feature_names = safe_feature_names(feature_names)

    train_array = np.array(train_matrix, dtype=float)
    test_array = np.array(test_matrix, dtype=float)
    train_dataset = lgb.Dataset(
        train_array,
        label=np.array(labels(train_rows, label_column=label_column), dtype=int),
        group=group_sizes_by_date(train_rows),
        feature_name=lightgbm_feature_names,
        free_raw_data=False,
    )
    params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "learning_rate": learning_rate,
            "num_leaves": num_leaves,
            "min_data_in_leaf": min_data_in_leaf,
            "label_gain": resolved_label_gain,
            "seed": 17,
            "verbosity": -1,
            **({"num_threads": num_threads} if num_threads > 0 else {}),
    }
    if lambdarank_truncation_level > 0:
        params["lambdarank_truncation_level"] = lambdarank_truncation_level
    model = lgb.train(
        params,
        train_dataset,
        num_boost_round=num_boost_round,
    )

    train_scored = assign_scores(train_rows, model.predict(train_array))
    test_scored = assign_scores(test_rows, model.predict(test_array))
    importances = sorted(zip(feature_names, model.feature_importance()), key=lambda item: (-int(item[1]), item[0]))
    top_features = [{"feature": feature, "importance": int(value)} for feature, value in importances[:50]]
    return TrainedModelResult(
        train_scored=train_scored,
        test_scored=test_scored,
        top_features=top_features,
        feature_count=len(feature_names),
        model=model,
        feature_names=feature_names,
        lightgbm_feature_names=lightgbm_feature_names,
        category_levels=levels,
    )


def train_and_report(
    dataset: Path,
    output_dir: Path,
    *,
    test_ratio: float,
    feature_set: str = "all",
    train_mode: str = "overall",
    feature_manifest: Path | None = None,
    num_leaves: int = 15,
    min_data_in_leaf: int = 20,
    num_boost_round: int = 120,
    learning_rate: float = 0.05,
    rolling_folds: int = 0,
    rolling_train_dates: int = 0,
    rolling_test_dates: int = 0,
    label_column: str = "rank_label_3d",
    num_threads: int = 0,
    label_gain: Sequence[int] | None = None,
    lambdarank_truncation_level: int = 0,
    method: str = DEFAULT_METHOD,
    rf_diagnostics: bool = True,
    rf_n_estimators: int = DEFAULT_RF_N_ESTIMATORS,
    rf_max_depth: int | None = None,
    rf_min_samples_leaf: int = DEFAULT_RF_MIN_SAMPLES_LEAF,
    rf_max_features: str | int | float | None = DEFAULT_RF_MAX_FEATURES,
    rf_min_oob_score: float | None = None,
    rf_min_test_rank_ic_ret3: float | None = None,
) -> dict[str, Any]:
    if train_mode not in TRAIN_MODES:
        raise ValueError(f"unsupported train_mode: {train_mode}")
    if label_column not in TRAIN_LABEL_COLUMNS:
        raise ValueError(f"unsupported label_column: {label_column}")
    resolved_label_gain = list(label_gain or DEFAULT_LABEL_GAIN)

    rows = read_dataset(dataset)
    train_dates, test_dates = walk_forward_split_dates([str(row.get("date")) for row in rows], test_ratio=test_ratio)
    train_rows = rows_for_dates(rows, set(train_dates), label_column=label_column)
    test_rows = rows_for_dates(rows, set(test_dates), label_column=label_column)
    if not train_rows or not test_rows:
        raise ValueError(f"dataset must contain both train and test rows with {label_column}")

    if feature_manifest is not None:
        numeric_columns, categorical_columns, fixed_categorical_levels = load_feature_manifest_with_levels(
            feature_manifest,
            available_columns=set(rows[0].keys()),
            method=method,
        )
    else:
        numeric_columns, categorical_columns = select_feature_columns(
            rows[0].keys(),
            feature_set=feature_set,
            method=method,
        )
        fixed_categorical_levels = {}

    rf_config = RandomForestDiagnosticsConfig(
        enabled=rf_diagnostics,
        n_estimators=rf_n_estimators,
        max_depth=rf_max_depth,
        min_samples_leaf=rf_min_samples_leaf,
        max_features=rf_max_features,
        min_oob_score=rf_min_oob_score,
        min_test_rank_ic_ret3=rf_min_test_rank_ic_ret3,
    )
    if rf_config.enabled:
        rf_payload = run_random_forest_diagnostics(
            train_rows,
            test_rows,
            numeric_columns=numeric_columns,
            categorical_columns=categorical_columns,
            label_column=label_column,
            label_gain=resolved_label_gain,
            num_threads=num_threads,
            fixed_categorical_levels=fixed_categorical_levels,
            config=rf_config,
        )
        rf_payload, rf_json_path, _rf_markdown_path = write_rf_diagnostics_artifacts(rf_payload, output_dir)
        rf_summary = rf_diagnostics_summary(rf_payload, rf_json_path)
    else:
        rf_payload = {"enabled": False, "status": "skipped", "output_paths": {}}
        rf_summary = rf_diagnostics_summary(rf_payload, None)

    if train_mode == "overall":
        model_result = train_model_result(
            train_rows,
            test_rows,
            numeric_columns=numeric_columns,
            categorical_columns=categorical_columns,
            num_leaves=num_leaves,
            min_data_in_leaf=min_data_in_leaf,
            num_boost_round=num_boost_round,
            learning_rate=learning_rate,
            label_column=label_column,
            num_threads=num_threads,
            label_gain=resolved_label_gain,
            lambdarank_truncation_level=lambdarank_truncation_level,
            fixed_categorical_levels=fixed_categorical_levels,
        )
        train_scored = model_result.train_scored
        test_scored = model_result.test_scored
        top_features = model_result.top_features
        feature_count = model_result.feature_count
        env_metrics = {}
    else:
        train_scored = []
        test_scored = []
        top_features = []
        feature_count = 0
        env_metrics = {}
        model_result = None
        train_by_env = env_partitions(train_rows)
        test_by_env = env_partitions(test_rows)
        for env in sorted(set(train_by_env) | set(test_by_env)):
            env_train = train_by_env.get(env, [])
            env_test = test_by_env.get(env, [])
            if not env_train or not env_test:
                continue
            env_train_scored, env_test_scored, env_top_features, env_feature_count = train_model(
                env_train,
                env_test,
                numeric_columns=numeric_columns,
                categorical_columns=categorical_columns,
                num_leaves=num_leaves,
                min_data_in_leaf=min_data_in_leaf,
                num_boost_round=num_boost_round,
                learning_rate=learning_rate,
                label_column=label_column,
                num_threads=num_threads,
                label_gain=resolved_label_gain,
                lambdarank_truncation_level=lambdarank_truncation_level,
                fixed_categorical_levels=fixed_categorical_levels,
            )
            train_scored.extend(env_train_scored)
            test_scored.extend(env_test_scored)
            feature_count = max(feature_count, env_feature_count)
            env_metrics[env] = {
                "train_row_count": len(env_train_scored),
                "test_row_count": len(env_test_scored),
                "metrics": evaluate_model(env_test_scored, top_n=3),
                "top_features": env_top_features[:20],
            }
            if not top_features:
                top_features = env_top_features

    model_artifacts = None
    feature_manifest_output = write_feature_manifest(
        output_dir,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        fixed_categorical_levels=fixed_categorical_levels,
    )
    if model_result is not None and model_result.model is not None:
        metadata = build_model_metadata(
            feature_manifest=str(feature_manifest_output),
            train_rows=train_rows,
            score_rows=test_rows,
            numeric_columns=numeric_columns,
            categorical_columns=categorical_columns,
            levels=model_result.category_levels,
            feature_names=model_result.feature_names,
            lightgbm_feature_names=model_result.lightgbm_feature_names,
            label_column=label_column,
            model_params={
                "num_leaves": num_leaves,
                "min_data_in_leaf": min_data_in_leaf,
                "num_boost_round": num_boost_round,
                "learning_rate": learning_rate,
                "num_threads": num_threads,
                "label_gain": resolved_label_gain,
                "lambdarank_truncation_level": lambdarank_truncation_level,
            },
        )
        model_artifacts = write_model_artifacts(model_result.model, metadata, output_dir)

    report = {
        "method": method,
        "dataset": str(dataset),
        "train_date_count": len(train_dates),
        "test_date_count": len(test_dates),
        "train_row_count": len(train_rows),
        "test_row_count": len(test_rows),
        "feature_count": feature_count,
        "feature_set": feature_set,
        "train_mode": train_mode,
        "label_column": label_column,
        "feature_manifest": str(feature_manifest_output),
        "model_params": {
            "num_leaves": num_leaves,
            "min_data_in_leaf": min_data_in_leaf,
            "num_boost_round": num_boost_round,
            "learning_rate": learning_rate,
            "num_threads": num_threads,
            "label_gain": resolved_label_gain,
            "lambdarank_truncation_level": lambdarank_truncation_level,
        },
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "fixed_categorical_levels": fixed_categorical_levels,
        "metrics": {
            "train": evaluate_model(train_scored, top_n=3),
            "test": evaluate_model(test_scored, top_n=3),
        },
        "env_metrics": env_metrics,
        "top_features": top_features,
        "rf_diagnostics": rf_summary,
    }
    if model_artifacts is not None:
        report["model_artifacts"] = model_artifacts
    if rolling_folds:
        if train_mode != "overall":
            raise ValueError("rolling validation currently supports train_mode=overall only")
        splits = rolling_walk_forward_splits(
            [str(row.get("date")) for row in rows],
            train_date_count=rolling_train_dates,
            test_date_count=rolling_test_dates,
            fold_count=rolling_folds,
        )
        fold_reports = []
        for fold_index, (fold_train_dates, fold_test_dates) in enumerate(splits, start=1):
            fold_train_rows = rows_for_dates(rows, set(fold_train_dates), label_column=label_column)
            fold_test_rows = rows_for_dates(rows, set(fold_test_dates), label_column=label_column)
            if not fold_train_rows or not fold_test_rows:
                continue
            fold_train_scored, fold_test_scored, _fold_features, _fold_feature_count = train_model(
                fold_train_rows,
                fold_test_rows,
                numeric_columns=numeric_columns,
                categorical_columns=categorical_columns,
                num_leaves=num_leaves,
                min_data_in_leaf=min_data_in_leaf,
                num_boost_round=num_boost_round,
                learning_rate=learning_rate,
                label_column=label_column,
                num_threads=num_threads,
                label_gain=resolved_label_gain,
                lambdarank_truncation_level=lambdarank_truncation_level,
                fixed_categorical_levels=fixed_categorical_levels,
            )
            fold_report = {
                "fold": fold_index,
                "train_start_date": fold_train_dates[0],
                "train_end_date": fold_train_dates[-1],
                "test_start_date": fold_test_dates[0],
                "test_end_date": fold_test_dates[-1],
                "train_date_count": len(fold_train_dates),
                "test_date_count": len(fold_test_dates),
                "train_row_count": len(fold_train_rows),
                "test_row_count": len(fold_test_rows),
                "metrics": {
                    "train": evaluate_model(fold_train_scored, top_n=3),
                    "test": evaluate_model(fold_test_scored, top_n=3),
                },
                "by_env": partition_diagnostics(fold_test_scored, partition="env"),
                "by_month": partition_diagnostics(fold_test_scored, partition="month"),
            }
            fold_reports.append(fold_report)
        report["rolling_folds"] = fold_reports
        report["rolling_summary"] = {
            "fold_count": len(fold_reports),
            "train_date_count": rolling_train_dates,
            "test_date_count": rolling_test_dates,
            "test_avg": average_metric_dicts([fold["metrics"]["test"] for fold in fold_reports]),
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = report_paths(output_dir, feature_set, train_mode, label_column)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train offline LightGBM ranker.")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--feature-set", choices=sorted(FEATURE_SETS), default="all")
    parser.add_argument("--train-mode", choices=sorted(TRAIN_MODES), default="overall")
    parser.add_argument("--feature-manifest", type=Path)
    parser.add_argument("--num-leaves", type=int, default=15)
    parser.add_argument("--min-data-in-leaf", type=int, default=20)
    parser.add_argument("--num-boost-round", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--num-threads", type=int, default=0)
    parser.add_argument("--label-column", choices=sorted(TRAIN_LABEL_COLUMNS), default="rank_label_3d")
    parser.add_argument("--label-gain", type=parse_label_gain, default=DEFAULT_LABEL_GAIN)
    parser.add_argument("--lambdarank-truncation-level", type=int, default=0)
    parser.add_argument("--rolling-folds", type=int, default=0)
    parser.add_argument("--rolling-train-dates", type=int, default=240)
    parser.add_argument("--rolling-test-dates", type=int, default=40)
    rf_group = parser.add_mutually_exclusive_group()
    rf_group.add_argument("--rf-diagnostics", dest="rf_diagnostics", action="store_true", default=True)
    rf_group.add_argument("--skip-rf-diagnostics", dest="rf_diagnostics", action="store_false")
    parser.add_argument("--rf-n-estimators", type=int, default=DEFAULT_RF_N_ESTIMATORS)
    parser.add_argument("--rf-max-depth", type=int)
    parser.add_argument("--rf-min-samples-leaf", type=int, default=DEFAULT_RF_MIN_SAMPLES_LEAF)
    parser.add_argument("--rf-max-features", default=DEFAULT_RF_MAX_FEATURES)
    parser.add_argument("--rf-min-oob-score", type=float)
    parser.add_argument("--rf-min-test-rank-ic-ret3", type=float)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    dataset = resolve_dataset_path(args.dataset, method=args.method)
    output_dir = resolve_output_dir(args.output_dir, method=args.method)
    report = train_and_report(
        dataset,
        output_dir,
        test_ratio=args.test_ratio,
        feature_set=args.feature_set,
        train_mode=args.train_mode,
        feature_manifest=args.feature_manifest,
        num_leaves=args.num_leaves,
        min_data_in_leaf=args.min_data_in_leaf,
        num_boost_round=args.num_boost_round,
        learning_rate=args.learning_rate,
        num_threads=args.num_threads,
        label_column=args.label_column,
        label_gain=args.label_gain,
        lambdarank_truncation_level=args.lambdarank_truncation_level,
        rolling_folds=args.rolling_folds,
        rolling_train_dates=args.rolling_train_dates,
        rolling_test_dates=args.rolling_test_dates,
        method=args.method,
    )
    json_path, _markdown_path = report_paths(output_dir, args.feature_set, args.train_mode, args.label_column)
    print(f"wrote report to {json_path}")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
