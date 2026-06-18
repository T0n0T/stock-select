from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence

from .evaluation import assign_scores
from .features import CATEGORICAL_ENCODINGS, DEFAULT_CATEGORICAL_ENCODING
from .labels import labels
from .matrices import build_feature_matrix, category_levels, safe_feature_names


DEFAULT_LABEL_GAIN = [0, 1, 3, 7]


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
    categorical_code_maps: dict[str, dict[str, int]]
    best_iteration: int | None = None


def group_sizes_by_date(rows: Sequence[dict[str, Any]]) -> list[int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("date"))] += 1
    return [counts[date] for date in sorted(counts)]


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
) -> TrainedModelResult:
    import lightgbm as lgb
    import numpy as np

    if categorical_encoding not in CATEGORICAL_ENCODINGS:
        raise ValueError(f"unsupported categorical_encoding: {categorical_encoding}")
    if not train_rows or not test_rows:
        return TrainedModelResult([], [], [], 0, None, [], [], {}, {})

    resolved_label_gain = list(label_gain or DEFAULT_LABEL_GAIN)
    resolved_eval_at = [int(value) for value in (eval_at or [5, 10, 20])]
    levels = category_levels(
        train_rows,
        categorical_columns,
        fixed_categorical_levels=fixed_categorical_levels,
    )
    train_matrix, feature_names, code_maps = build_feature_matrix(
        train_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
        categorical_encoding=categorical_encoding,
    )
    test_matrix, _feature_names, _test_code_maps = build_feature_matrix(
        test_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
        categorical_encoding=categorical_encoding,
    )
    lightgbm_feature_names = safe_feature_names(feature_names)

    train_array = np.array(train_matrix, dtype=float)
    test_array = np.array(test_matrix, dtype=float)
    dataset_kwargs = {
        "label": np.array(labels(train_rows, label_column=label_column), dtype=int),
        "group": group_sizes_by_date(train_rows),
        "feature_name": lightgbm_feature_names,
        "free_raw_data": False,
    }
    if categorical_encoding == "native" and categorical_columns:
        categorical_start = len(numeric_columns)
        categorical_end = categorical_start + len(categorical_columns)
        dataset_kwargs["categorical_feature"] = lightgbm_feature_names[categorical_start:categorical_end]
    train_dataset = lgb.Dataset(train_array, **dataset_kwargs)
    params = {
        "objective": "lambdarank",
        "boosting_type": boosting_type,
        "metric": "ndcg",
        "learning_rate": learning_rate,
        "num_leaves": num_leaves,
        "min_data_in_leaf": min_data_in_leaf,
        "bagging_fraction": bagging_fraction,
        "bagging_freq": bagging_freq,
        "feature_fraction": feature_fraction,
        "lambda_l1": lambda_l1,
        "lambda_l2": lambda_l2,
        "min_gain_to_split": min_gain_to_split,
        "label_gain": resolved_label_gain,
        "eval_at": resolved_eval_at,
        "seed": seed,
        "verbosity": -1,
        **({"num_threads": num_threads} if num_threads > 0 else {}),
    }
    if lambdarank_truncation_level > 0:
        params["lambdarank_truncation_level"] = lambdarank_truncation_level
    if early_stopping_rounds > 0:
        valid_kwargs = {
            "label": np.array(labels(test_rows, label_column=label_column), dtype=int),
            "group": group_sizes_by_date(test_rows),
            "free_raw_data": False,
        }
        if categorical_encoding == "native" and categorical_columns:
            categorical_start = len(numeric_columns)
            categorical_end = categorical_start + len(categorical_columns)
            valid_kwargs["categorical_feature"] = lightgbm_feature_names[categorical_start:categorical_end]
        valid_dataset = lgb.Dataset(test_array, reference=train_dataset, **valid_kwargs)
        model = lgb.train(
            params,
            train_dataset,
            num_boost_round=num_boost_round,
            valid_sets=[valid_dataset],
            valid_names=["valid"],
            callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
        )
    else:
        model = lgb.train(
            params,
            train_dataset,
            num_boost_round=num_boost_round,
        )

    best_iteration = getattr(model, "best_iteration", None) or None
    train_scored = assign_scores(train_rows, predict_with_best_iteration(model, train_array, best_iteration))
    test_scored = assign_scores(test_rows, predict_with_best_iteration(model, test_array, best_iteration))
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
        categorical_code_maps=code_maps,
        best_iteration=best_iteration,
    )


def predict_with_best_iteration(model: Any, matrix: Any, best_iteration: int | None) -> Sequence[float]:
    if best_iteration is not None:
        try:
            return model.predict(matrix, num_iteration=best_iteration)
        except TypeError:
            pass
    return model.predict(matrix)
