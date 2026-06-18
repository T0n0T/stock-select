from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .evaluation import assign_scores, evaluate_model
from .labels import as_float, labels
from .matrices import build_feature_matrix, category_levels


DEFAULT_RF_N_ESTIMATORS = 300
DEFAULT_RF_MIN_SAMPLES_LEAF = 20
DEFAULT_RF_MAX_FEATURES = "sqrt"
LOW_IMPORTANCE_THRESHOLD = 1e-6


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
    train_matrix, feature_names, _code_maps = build_feature_matrix(
        train_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
    )
    test_matrix, _feature_names, _test_code_maps = build_feature_matrix(
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
        "feature_importances": [
            {"feature": feature, "importance": round(importance, 8)} for feature, importance in ranked_features
        ],
        "low_importance_features": [
            {"feature": feature, "importance": round(importance, 8)} for feature, importance in low_features
        ],
        "output_paths": {},
    }


def rf_diagnostic_paths(output_dir: Path) -> tuple[Path, Path]:
    return output_dir / "rf_feature_diagnostics.json", output_dir / "rf_feature_diagnostics.md"


def rf_diagnostics_summary(diagnostics: dict[str, Any], json_path: Path | None = None) -> dict[str, Any]:
    summary = {
        "enabled": bool(diagnostics.get("enabled")),
        "path": str(json_path) if json_path is not None else None,
        "status": diagnostics.get("status"),
        "oob_score": diagnostics.get("oob_score"),
        "metrics": {"test": (diagnostics.get("metrics") or {}).get("test") or {}},
        "top_features": list(diagnostics.get("top_features") or [])[:20],
        "low_importance_feature_count": len(diagnostics.get("low_importance_features") or []),
    }
    if diagnostics.get("feature_selection") is not None:
        summary["feature_selection"] = diagnostics.get("feature_selection")
    return summary


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


def random_forest_threshold_failures(diagnostics: dict[str, Any]) -> list[str]:
    thresholds = diagnostics.get("thresholds") or {}
    failures: list[str] = []
    min_oob = as_float(thresholds.get("min_oob_score"))
    oob_score = as_float(diagnostics.get("oob_score"))
    if min_oob is not None and (oob_score is None or oob_score < min_oob):
        failures.append(f"oob_score {oob_score} < {min_oob}")
    min_rank_ic = as_float(thresholds.get("min_test_rank_ic_ret3"))
    test_metrics = ((diagnostics.get("metrics") or {}).get("test") or {})
    rank_ic = as_float(test_metrics.get("rank_ic_ret3"))
    if min_rank_ic is not None and (rank_ic is None or rank_ic < min_rank_ic):
        failures.append(f"test rank_ic_ret3 {rank_ic} < {min_rank_ic}")
    return failures
