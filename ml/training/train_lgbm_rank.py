from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Sequence

from ml.paths import PROJECT_ROOT

from .artifacts import build_model_metadata, write_feature_manifest, write_model_artifacts
from .evaluation import average_metric_dicts, env_partitions, evaluate_model, partition_diagnostics
from .features import (
    CATEGORICAL_ENCODINGS,
    DEFAULT_CATEGORICAL_ENCODING,
    DEFAULT_METHOD,
    FEATURE_SETS,
    RF_FEATURE_SELECTION_MODES,
    load_feature_manifest_with_levels,
    select_feature_columns,
    select_features_by_rf_importance,
    validate_selected_feature_coverage,
)
from .labels import TRAIN_LABEL_COLUMNS, rows_for_dates
from .lgbm_ranker import DEFAULT_LABEL_GAIN, train_model_result
from .reports import markdown_report, report_paths
from .rf_diagnostics import (
    DEFAULT_RF_MAX_FEATURES,
    DEFAULT_RF_MIN_SAMPLES_LEAF,
    DEFAULT_RF_N_ESTIMATORS,
    RandomForestDiagnosticsConfig,
    RandomForestThresholdError,
    random_forest_threshold_failures,
    rf_diagnostics_summary,
    run_random_forest_diagnostics,
    write_rf_diagnostics_artifacts,
)


TRAIN_MODES = {"overall", "by_env"}


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


def parse_label_gain(value: str) -> list[int]:
    try:
        gains = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("label gain must be comma-separated integers") from exc
    if not gains:
        raise argparse.ArgumentTypeError("label gain must contain at least one integer")
    return gains


def parse_int_list(value: str) -> list[int]:
    try:
        parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be comma-separated integers") from exc
    if not parsed:
        raise argparse.ArgumentTypeError("value must contain at least one integer")
    if any(item <= 0 for item in parsed):
        raise argparse.ArgumentTypeError("values must be positive integers")
    return parsed


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
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
    boosting_type: str = "gbdt",
    bagging_fraction: float = 1.0,
    bagging_freq: int = 0,
    feature_fraction: float = 1.0,
    lambda_l1: float = 0.0,
    lambda_l2: float = 0.0,
    min_gain_to_split: float = 0.0,
    eval_at: Sequence[int] | None = None,
    early_stopping_rounds: int = 0,
    seed: int = 17,
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
        categorical_encoding=categorical_encoding,
        boosting_type=boosting_type,
        bagging_fraction=bagging_fraction,
        bagging_freq=bagging_freq,
        feature_fraction=feature_fraction,
        lambda_l1=lambda_l1,
        lambda_l2=lambda_l2,
        min_gain_to_split=min_gain_to_split,
        eval_at=eval_at,
        early_stopping_rounds=early_stopping_rounds,
        seed=seed,
    )
    return result.train_scored, result.test_scored, result.top_features, result.feature_count


def lgbm_model_params(
    *,
    boosting_type: str,
    num_leaves: int,
    min_data_in_leaf: int,
    num_boost_round: int,
    learning_rate: float,
    bagging_fraction: float,
    bagging_freq: int,
    feature_fraction: float,
    lambda_l1: float,
    lambda_l2: float,
    min_gain_to_split: float,
    num_threads: int,
    label_gain: Sequence[int],
    lambdarank_truncation_level: int,
    eval_at: Sequence[int],
    early_stopping_rounds: int,
    seed: int,
    best_iteration: int | None = None,
) -> dict[str, Any]:
    return {
        "boosting_type": boosting_type,
        "num_leaves": num_leaves,
        "min_data_in_leaf": min_data_in_leaf,
        "num_boost_round": num_boost_round,
        "learning_rate": learning_rate,
        "bagging_fraction": bagging_fraction,
        "bagging_freq": bagging_freq,
        "feature_fraction": feature_fraction,
        "lambda_l1": lambda_l1,
        "lambda_l2": lambda_l2,
        "min_gain_to_split": min_gain_to_split,
        "num_threads": num_threads,
        "label_gain": list(label_gain),
        "lambdarank_truncation_level": lambdarank_truncation_level,
        "eval_at": list(eval_at),
        "early_stopping_rounds": early_stopping_rounds,
        "seed": seed,
        "best_iteration": best_iteration,
    }


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
    boosting_type: str = "gbdt",
    bagging_fraction: float = 1.0,
    bagging_freq: int = 0,
    feature_fraction: float = 1.0,
    lambda_l1: float = 0.0,
    lambda_l2: float = 0.0,
    min_gain_to_split: float = 0.0,
    top_k: Sequence[int] | None = None,
    eval_at: Sequence[int] | None = None,
    early_stopping_rounds: int = 0,
    seed: int = 17,
    rf_diagnostics: bool = True,
    rf_n_estimators: int = DEFAULT_RF_N_ESTIMATORS,
    rf_max_depth: int | None = None,
    rf_min_samples_leaf: int = DEFAULT_RF_MIN_SAMPLES_LEAF,
    rf_max_features: str | int | float | None = DEFAULT_RF_MAX_FEATURES,
    rf_min_oob_score: float | None = None,
    rf_min_test_rank_ic_ret3: float | None = None,
    rf_feature_selection: str = "none",
    rf_cumulative_importance_threshold: float = 0.85,
    rf_min_selected_features: int = 12,
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
) -> dict[str, Any]:
    if train_mode not in TRAIN_MODES:
        raise ValueError(f"unsupported train_mode: {train_mode}")
    if label_column not in TRAIN_LABEL_COLUMNS:
        raise ValueError(f"unsupported label_column: {label_column}")
    if rf_feature_selection not in RF_FEATURE_SELECTION_MODES:
        raise ValueError(f"unsupported RF feature selection mode: {rf_feature_selection}")
    if categorical_encoding not in CATEGORICAL_ENCODINGS:
        raise ValueError(f"unsupported categorical_encoding: {categorical_encoding}")
    if rf_feature_selection != "none" and not rf_diagnostics:
        raise ValueError("RF feature selection requires RF diagnostics")
    resolved_label_gain = list(label_gain or DEFAULT_LABEL_GAIN)
    resolved_top_k = [int(value) for value in (top_k or [3, 5, 10, 20])]
    resolved_eval_at = [int(value) for value in (eval_at or [5, 10, 20])]

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
    candidate_numeric_columns = list(numeric_columns)
    candidate_categorical_columns = list(categorical_columns)
    feature_coverage = validate_selected_feature_coverage(
        train_rows + test_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
    )
    feature_selection_payload = {
        "mode": "none",
        "candidate_feature_count": len(candidate_numeric_columns) + len(candidate_categorical_columns),
        "selected_feature_count": len(candidate_numeric_columns) + len(candidate_categorical_columns),
        "dropped_feature_count": 0,
        "selected_features": candidate_numeric_columns + candidate_categorical_columns,
        "dropped_features": [],
    }

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
        failures = random_forest_threshold_failures(rf_payload)
        if failures:
            rf_payload["status"] = "failed_threshold"
            rf_payload, rf_json_path, _rf_markdown_path = write_rf_diagnostics_artifacts(rf_payload, output_dir)
            raise RandomForestThresholdError(
                f"random forest diagnostics failed thresholds: {', '.join(failures)}; report={rf_json_path}"
            )
        if rf_feature_selection == "cumulative_importance":
            feature_selection_payload = select_features_by_rf_importance(
                rf_payload,
                numeric_columns=candidate_numeric_columns,
                categorical_columns=candidate_categorical_columns,
                threshold=rf_cumulative_importance_threshold,
                min_selected_features=rf_min_selected_features,
            )
            numeric_columns = list(feature_selection_payload["numeric_columns"])
            categorical_columns = list(feature_selection_payload["categorical_columns"])
            if not numeric_columns and not categorical_columns:
                raise ValueError("RF feature selection produced no training features")
            feature_coverage = validate_selected_feature_coverage(
                train_rows + test_rows,
                numeric_columns=numeric_columns,
                categorical_columns=categorical_columns,
            )
            if fixed_categorical_levels:
                fixed_categorical_levels = {
                    column: levels for column, levels in fixed_categorical_levels.items() if column in set(categorical_columns)
                }
        rf_payload["feature_selection"] = feature_selection_payload
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
            categorical_encoding=categorical_encoding,
            boosting_type=boosting_type,
            bagging_fraction=bagging_fraction,
            bagging_freq=bagging_freq,
            feature_fraction=feature_fraction,
            lambda_l1=lambda_l1,
            lambda_l2=lambda_l2,
            min_gain_to_split=min_gain_to_split,
            eval_at=resolved_eval_at,
            early_stopping_rounds=early_stopping_rounds,
            seed=seed,
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
                categorical_encoding=categorical_encoding,
                boosting_type=boosting_type,
                bagging_fraction=bagging_fraction,
                bagging_freq=bagging_freq,
                feature_fraction=feature_fraction,
                lambda_l1=lambda_l1,
                lambda_l2=lambda_l2,
                min_gain_to_split=min_gain_to_split,
                eval_at=resolved_eval_at,
                early_stopping_rounds=early_stopping_rounds,
                seed=seed,
            )
            train_scored.extend(env_train_scored)
            test_scored.extend(env_test_scored)
            feature_count = max(feature_count, env_feature_count)
            env_metrics[env] = {
                "train_row_count": len(env_train_scored),
                "test_row_count": len(env_test_scored),
                "metrics": evaluate_model(env_test_scored, top_k=resolved_top_k, label_column=label_column, ndcg_at=resolved_eval_at),
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
        categorical_encoding=categorical_encoding,
    )
    if model_result is not None and model_result.model is not None:
        model_params = lgbm_model_params(
            boosting_type=boosting_type,
            num_leaves=num_leaves,
            min_data_in_leaf=min_data_in_leaf,
            num_boost_round=num_boost_round,
            learning_rate=learning_rate,
            bagging_fraction=bagging_fraction,
            bagging_freq=bagging_freq,
            feature_fraction=feature_fraction,
            lambda_l1=lambda_l1,
            lambda_l2=lambda_l2,
            min_gain_to_split=min_gain_to_split,
            num_threads=num_threads,
            label_gain=resolved_label_gain,
            lambdarank_truncation_level=lambdarank_truncation_level,
            eval_at=resolved_eval_at,
            early_stopping_rounds=early_stopping_rounds,
            seed=seed,
            best_iteration=model_result.best_iteration,
        )
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
            model_params=model_params,
            feature_selection=feature_selection_payload,
            categorical_encoding=categorical_encoding,
            categorical_code_maps=model_result.categorical_code_maps,
        )
        model_artifacts = write_model_artifacts(model_result.model, metadata, output_dir)
    else:
        model_params = lgbm_model_params(
            boosting_type=boosting_type,
            num_leaves=num_leaves,
            min_data_in_leaf=min_data_in_leaf,
            num_boost_round=num_boost_round,
            learning_rate=learning_rate,
            bagging_fraction=bagging_fraction,
            bagging_freq=bagging_freq,
            feature_fraction=feature_fraction,
            lambda_l1=lambda_l1,
            lambda_l2=lambda_l2,
            min_gain_to_split=min_gain_to_split,
            num_threads=num_threads,
            label_gain=resolved_label_gain,
            lambdarank_truncation_level=lambdarank_truncation_level,
            eval_at=resolved_eval_at,
            early_stopping_rounds=early_stopping_rounds,
            seed=seed,
        )

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
        "categorical_encoding": categorical_encoding,
        "feature_manifest": str(feature_manifest_output),
        "model_params": model_params,
        "top_k": resolved_top_k,
        "eval_at": resolved_eval_at,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "candidate_numeric_columns": candidate_numeric_columns,
        "candidate_categorical_columns": candidate_categorical_columns,
        "fixed_categorical_levels": fixed_categorical_levels,
        "feature_selection": feature_selection_payload,
        "feature_coverage": feature_coverage,
        "metrics": {
            "train": evaluate_model(train_scored, top_k=resolved_top_k, label_column=label_column, ndcg_at=resolved_eval_at),
            "test": evaluate_model(test_scored, top_k=resolved_top_k, label_column=label_column, ndcg_at=resolved_eval_at),
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
                categorical_encoding=categorical_encoding,
                boosting_type=boosting_type,
                bagging_fraction=bagging_fraction,
                bagging_freq=bagging_freq,
                feature_fraction=feature_fraction,
                lambda_l1=lambda_l1,
                lambda_l2=lambda_l2,
                min_gain_to_split=min_gain_to_split,
                eval_at=resolved_eval_at,
                early_stopping_rounds=early_stopping_rounds,
                seed=seed,
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
                    "train": evaluate_model(fold_train_scored, top_k=resolved_top_k, label_column=label_column, ndcg_at=resolved_eval_at),
                    "test": evaluate_model(fold_test_scored, top_k=resolved_top_k, label_column=label_column, ndcg_at=resolved_eval_at),
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


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("lgbm-rank", description="Train offline LightGBM ranker.")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--feature-set", choices=sorted(FEATURE_SETS), default="all")
    parser.add_argument("--train-mode", choices=sorted(TRAIN_MODES), default="overall")
    parser.add_argument("--feature-manifest", type=Path)
    parser.add_argument("--categorical-encoding", choices=sorted(CATEGORICAL_ENCODINGS), default=DEFAULT_CATEGORICAL_ENCODING)
    parser.add_argument("--num-leaves", type=int, default=15)
    parser.add_argument("--min-data-in-leaf", type=int, default=20)
    parser.add_argument("--num-boost-round", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--boosting-type", choices=["gbdt", "dart"], default="gbdt")
    parser.add_argument("--bagging-fraction", type=float, default=1.0)
    parser.add_argument("--bagging-freq", type=int, default=0)
    parser.add_argument("--feature-fraction", type=float, default=1.0)
    parser.add_argument("--lambda-l1", type=float, default=0.0)
    parser.add_argument("--lambda-l2", type=float, default=0.0)
    parser.add_argument("--min-gain-to-split", type=float, default=0.0)
    parser.add_argument("--num-threads", type=int, default=0)
    parser.add_argument("--label-column", choices=sorted(TRAIN_LABEL_COLUMNS), default="rank_label_3d")
    parser.add_argument("--label-gain", type=parse_label_gain, default=DEFAULT_LABEL_GAIN)
    parser.add_argument("--lambdarank-truncation-level", type=int, default=0)
    parser.add_argument("--top-k", type=parse_int_list, default=[3, 5, 10, 20])
    parser.add_argument("--eval-at", type=parse_int_list, default=[5, 10, 20])
    parser.add_argument("--early-stopping-rounds", type=int, default=0)
    parser.add_argument("--seed", type=int, default=17)
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
    parser.add_argument("--rf-feature-selection", choices=sorted(RF_FEATURE_SELECTION_MODES), default="none")
    parser.add_argument("--rf-cumulative-importance-threshold", type=float, default=0.85)
    parser.add_argument("--rf-min-selected-features", type=int, default=12)
    parser.set_defaults(handler=main_from_args)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train offline LightGBM ranker.")
    add_parser(parser.add_subparsers(dest="command"))
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train offline LightGBM ranker.")
    add_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["lgbm-rank", *(list(argv) if argv is not None else [])])
    return args


def main_from_args(args: argparse.Namespace) -> int:
    dataset = resolve_dataset_path(args.dataset, method=args.method)
    output_dir = resolve_output_dir(args.output_dir, method=args.method)
    report = train_and_report(
        dataset,
        output_dir,
        test_ratio=args.test_ratio,
        feature_set=args.feature_set,
        train_mode=args.train_mode,
        feature_manifest=args.feature_manifest,
        categorical_encoding=args.categorical_encoding,
        num_leaves=args.num_leaves,
        min_data_in_leaf=args.min_data_in_leaf,
        num_boost_round=args.num_boost_round,
        learning_rate=args.learning_rate,
        boosting_type=args.boosting_type,
        bagging_fraction=args.bagging_fraction,
        bagging_freq=args.bagging_freq,
        feature_fraction=args.feature_fraction,
        lambda_l1=args.lambda_l1,
        lambda_l2=args.lambda_l2,
        min_gain_to_split=args.min_gain_to_split,
        num_threads=args.num_threads,
        label_column=args.label_column,
        label_gain=args.label_gain,
        lambdarank_truncation_level=args.lambdarank_truncation_level,
        top_k=args.top_k,
        eval_at=args.eval_at,
        early_stopping_rounds=args.early_stopping_rounds,
        seed=args.seed,
        rolling_folds=args.rolling_folds,
        rolling_train_dates=args.rolling_train_dates,
        rolling_test_dates=args.rolling_test_dates,
        method=args.method,
        rf_diagnostics=args.rf_diagnostics,
        rf_n_estimators=args.rf_n_estimators,
        rf_max_depth=args.rf_max_depth,
        rf_min_samples_leaf=args.rf_min_samples_leaf,
        rf_max_features=args.rf_max_features,
        rf_min_oob_score=args.rf_min_oob_score,
        rf_min_test_rank_ic_ret3=args.rf_min_test_rank_ic_ret3,
        rf_feature_selection=args.rf_feature_selection,
        rf_cumulative_importance_threshold=args.rf_cumulative_importance_threshold,
        rf_min_selected_features=args.rf_min_selected_features,
    )
    json_path, _markdown_path = report_paths(output_dir, args.feature_set, args.train_mode, args.label_column)
    print(f"wrote report to {json_path}")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return main_from_args(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
