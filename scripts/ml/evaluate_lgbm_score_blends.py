# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "lightgbm",
#   "numpy",
# ]
# ///
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ml.train_rank_lgbm import (
    DEFAULT_LABEL_GAIN,
    as_float,
    average_metric_dicts,
    evaluate_model,
    load_feature_manifest_with_levels,
    partition_diagnostics,
    read_dataset,
    rolling_walk_forward_splits,
    rows_for_dates,
    train_model,
)


DEFAULT_METHOD = "b2"
DEFAULT_DATASET = PROJECT_ROOT / "diagnostics" / "ml" / DEFAULT_METHOD / "rank_dataset.csv"


def score_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("date") or ""), str(row.get("code") or "")


def normalized_scores_by_key(rows: Sequence[dict[str, Any]]) -> dict[tuple[str, str], float]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("date") or ""), []).append(row)

    scores: dict[tuple[str, str], float] = {}
    for _date, day_rows in sorted(grouped.items()):
        ordered = sorted(day_rows, key=lambda row: (-(as_float(row.get("model_score")) or 0.0), str(row.get("code") or "")))
        if len(ordered) == 1:
            scores[score_key(ordered[0])] = 1.0
            continue
        denominator = len(ordered) - 1
        for index, row in enumerate(ordered):
            scores[score_key(row)] = (denominator - index) / denominator
    return scores


def blend_model_scores(
    base_rows: Sequence[dict[str, Any]],
    score_sets: dict[str, Sequence[dict[str, Any]]],
    *,
    weights: dict[str, float],
    apply_env: str | None = None,
) -> list[dict[str, Any]]:
    normalized = {name: normalized_scores_by_key(rows) for name, rows in score_sets.items()}
    base_name = next(iter(score_sets))
    blended: list[dict[str, Any]] = []
    for row in base_rows:
        item = dict(row)
        key = score_key(row)
        active_names = [base_name]
        if apply_env is None or str(row.get("env") or "") == apply_env:
            active_names = list(score_sets.keys())
        score = 0.0
        for name in active_names:
            score += float(weights.get(name, 0.0)) * normalized.get(name, {}).get(key, 0.0)
        item["model_score"] = score
        blended.append(item)
    return blended


def rows_by_fold(rows: Sequence[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row.get("fold") or 0), []).append(row)
    return grouped


def average_partition_metrics(fold_values: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    row_counts: dict[str, int] = {}
    for value in fold_values:
        for key, diagnostics in (value or {}).items():
            by_key.setdefault(key, []).append(diagnostics.get("metrics") or {})
            row_counts[key] = row_counts.get(key, 0) + int(diagnostics.get("row_count") or 0)
    return {
        key: {
            "row_count": row_counts.get(key, 0),
            "metrics": average_metric_dicts(metrics),
        }
        for key, metrics in sorted(by_key.items())
    }


def evaluate_blended_score_sets(
    score_sets: dict[str, Sequence[dict[str, Any]]],
    *,
    weights: dict[str, float],
    apply_env: str | None = None,
) -> dict[str, Any]:
    if not score_sets:
        raise ValueError("score sets cannot be empty")
    base_name = next(iter(score_sets))
    base_by_fold = rows_by_fold(score_sets[base_name])
    other_by_fold = {name: rows_by_fold(rows) for name, rows in score_sets.items()}

    blended_rows: list[dict[str, Any]] = []
    fold_reports: list[dict[str, Any]] = []
    for fold in sorted(base_by_fold):
        fold_score_sets = {
            name: grouped.get(fold, [])
            for name, grouped in other_by_fold.items()
        }
        blended = blend_model_scores(
            base_by_fold[fold],
            fold_score_sets,
            weights=weights,
            apply_env=apply_env,
        )
        blended_rows.extend(blended)
        fold_reports.append(
            {
                "fold": fold,
                "metrics": evaluate_model(blended, top_n=3),
                "by_env": partition_diagnostics(blended, partition="env"),
            }
        )
    return {
        "weights": weights,
        "apply_env": apply_env,
        "metrics": average_metric_dicts([fold["metrics"] for fold in fold_reports]),
        "by_env": average_partition_metrics([fold["by_env"] for fold in fold_reports]),
        "folds": fold_reports,
        "row_count": len(blended_rows),
    }


def parse_model_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("model spec must use name=trial_dir")
    name, raw_path = value.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("model name cannot be empty")
    return name, Path(raw_path)


def parse_weight_spec(value: str) -> tuple[str, float]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("weight spec must use name=value")
    name, raw_weight = value.split("=", 1)
    try:
        return name.strip(), float(raw_weight)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("weight must be numeric") from exc


def load_trial_config(trial_dir: Path) -> dict[str, Any]:
    reports = sorted(trial_dir.glob("lgbm_rank_report*.json"))
    if not reports:
        raise FileNotFoundError(f"no lgbm_rank_report*.json under {trial_dir}")
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    params = payload.get("model_params") or {}
    return {
        "feature_manifest": trial_dir / "feature_manifest.json",
        "label_column": str(payload.get("label_column") or "rank_label_3d"),
        "num_leaves": int(params.get("num_leaves", 9)),
        "min_data_in_leaf": int(params.get("min_data_in_leaf", 120)),
        "num_boost_round": int(params.get("num_boost_round", 60)),
        "learning_rate": float(params.get("learning_rate", 0.05)),
        "num_threads": int(params.get("num_threads", 0)),
        "label_gain": list(params.get("label_gain") or DEFAULT_LABEL_GAIN),
        "lambdarank_truncation_level": int(params.get("lambdarank_truncation_level", 0)),
    }


def rolling_scores_for_trial(
    rows: Sequence[dict[str, Any]],
    *,
    trial_dir: Path,
    method: str,
    rolling_train_dates: int,
    rolling_test_dates: int,
    rolling_folds: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = load_trial_config(trial_dir)
    numeric_columns, categorical_columns, fixed_levels = load_feature_manifest_with_levels(
        Path(config["feature_manifest"]),
        available_columns=set(rows[0].keys()),
        method=method,
    )
    splits = rolling_walk_forward_splits(
        [str(row.get("date")) for row in rows],
        train_date_count=rolling_train_dates,
        test_date_count=rolling_test_dates,
        fold_count=rolling_folds,
    )

    scored_rows: list[dict[str, Any]] = []
    fold_reports: list[dict[str, Any]] = []
    feature_count = 0
    label_column = str(config["label_column"])
    for fold_index, (train_dates, test_dates) in enumerate(splits, start=1):
        train_rows = rows_for_dates(rows, set(train_dates), label_column=label_column)
        test_rows = rows_for_dates(rows, set(test_dates), label_column=label_column)
        if not train_rows or not test_rows:
            continue
        _train_scored, test_scored, _top_features, fold_feature_count = train_model(
            train_rows,
            test_rows,
            numeric_columns=numeric_columns,
            categorical_columns=categorical_columns,
            num_leaves=int(config["num_leaves"]),
            min_data_in_leaf=int(config["min_data_in_leaf"]),
            num_boost_round=int(config["num_boost_round"]),
            learning_rate=float(config["learning_rate"]),
            label_column=label_column,
            num_threads=int(config["num_threads"]),
            label_gain=list(config["label_gain"]),
            lambdarank_truncation_level=int(config["lambdarank_truncation_level"]),
            fixed_categorical_levels=fixed_levels,
        )
        feature_count = max(feature_count, fold_feature_count)
        for row in test_scored:
            item = dict(row)
            item["fold"] = fold_index
            scored_rows.append(item)
        fold_reports.append(
            {
                "fold": fold_index,
                "train_start_date": train_dates[0],
                "train_end_date": train_dates[-1],
                "test_start_date": test_dates[0],
                "test_end_date": test_dates[-1],
                "metrics": evaluate_model(test_scored, top_n=3),
                "by_env": partition_diagnostics(test_scored, partition="env"),
            }
        )
    summary = {
        "trial_dir": str(trial_dir),
        "label_column": label_column,
        "feature_manifest": str(config["feature_manifest"]),
        "feature_count": feature_count,
        "numeric_feature_count": len(numeric_columns),
        "categorical_features": categorical_columns,
        "model_params": {key: config[key] for key in ["num_leaves", "min_data_in_leaf", "num_boost_round", "learning_rate", "num_threads", "label_gain", "lambdarank_truncation_level"]},
        "folds": fold_reports,
        "metrics": average_metric_dicts([fold["metrics"] for fold in fold_reports]),
        "by_env": average_partition_metrics([fold["by_env"] for fold in fold_reports]),
    }
    return scored_rows, summary


def evaluate_blend_grid(
    *,
    dataset: Path,
    model_specs: Sequence[tuple[str, Path]],
    aux_weights: Sequence[float],
    method: str,
    apply_env: str | None,
    rolling_train_dates: int,
    rolling_test_dates: int,
    rolling_folds: int,
) -> dict[str, Any]:
    rows = read_dataset(dataset)
    if not rows:
        raise ValueError("dataset is empty")
    if len(model_specs) < 2:
        raise ValueError("at least two model specs are required")

    score_sets: dict[str, list[dict[str, Any]]] = {}
    model_summaries: dict[str, Any] = {}
    for name, trial_dir in model_specs:
        scored_rows, summary = rolling_scores_for_trial(
            rows,
            trial_dir=trial_dir,
            method=method,
            rolling_train_dates=rolling_train_dates,
            rolling_test_dates=rolling_test_dates,
            rolling_folds=rolling_folds,
        )
        score_sets[name] = scored_rows
        model_summaries[name] = summary

    base_name = model_specs[0][0]
    aux_name = model_specs[1][0]
    results = []
    for aux_weight in aux_weights:
        weights = {base_name: 1.0, aux_name: aux_weight}
        results.append(
            evaluate_blended_score_sets(
                score_sets,
                weights=weights,
                apply_env=apply_env,
            )
        )
    return {
        "dataset": str(dataset),
        "method": method,
        "rolling": {
            "train_date_count": rolling_train_dates,
            "test_date_count": rolling_test_dates,
            "fold_count": rolling_folds,
        },
        "models": model_summaries,
        "results": results,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate offline LightGBM score blends on rolling folds.")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model", action="append", type=parse_model_spec, required=True)
    parser.add_argument("--aux-weight", action="append", type=float, required=True)
    parser.add_argument("--apply-env")
    parser.add_argument("--rolling-folds", type=int, default=5)
    parser.add_argument("--rolling-train-dates", type=int, default=240)
    parser.add_argument("--rolling-test-dates", type=int, default=40)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = evaluate_blend_grid(
        dataset=args.dataset,
        model_specs=args.model,
        aux_weights=args.aux_weight,
        method=args.method,
        apply_env=args.apply_env,
        rolling_train_dates=args.rolling_train_dates,
        rolling_test_dates=args.rolling_test_dates,
        rolling_folds=args.rolling_folds,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
